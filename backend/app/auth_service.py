"""Pure-stdlib Google OAuth 2.0 / OIDC Authentication, Session & CSRF Service (`M5`).

Implements:
1. Server-side OAuth 2.0 Authorization Code Flow + PKCE (`S256`) + `state` +
   `fvp_oauth_bind` browser-binding cookie + OIDC `nonce`.
2. Direct TLS-verified token exchange at `https://oauth2.googleapis.com/token`
   (OIDC Core 1.0 §3.1.3.7 Rule 6) using Python 3 standard library only
   (`urllib.request`, `ssl`, `hmac`, `hashlib`, `secrets`, `base64`, `http.cookies`),
   immediately discarding `access_token` / `refresh_token`.
3. Revocable SHA-256-hashed sessions in `auth_sessions` (`__Host-fvp_session`
   on HTTPS; `fvp_session` on local loopback HTTP) with `HttpOnly`, `SameSite=Lax`,
   `Path=/`, plus `X-CSRF-Token` + `Origin` CSRF validation.
4. Dependency-injected `token_exchanger` for hermetic unit/E2E testing AND a
   strictly triple-gated local test-only OAuth flow (`VACATION_PLANNER_AUTH_TEST_MODE=1`
   AND `ELAL_LIVE_FETCH_ENABLED != "1"` AND loopback/in-process host only).
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
from http.cookies import SimpleCookie
import html
import json
import os
import re
import secrets
import ssl
import threading
import time
from typing import Any, Callable, Optional
import urllib.error
import urllib.parse
import urllib.request

from backend.app.storage_cache.repository import SQLiteRepository

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
VALID_GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})

SESSION_COOKIE_SECURE = "__Host-fvp_session"
SESSION_COOKIE_LOCAL = "fvp_session"
OAUTH_BIND_COOKIE = "fvp_oauth_bind"

DEFAULT_SESSION_TTL_SECONDS = 14 * 86400  # 14 days
OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes
LOCAL_TEST_CLIENT_ID = "local-test-google-client-id.apps.googleusercontent.com"

_EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,63}$")
_PII_EMAIL_SCAN_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,63}")
_PII_SECRET_SCAN_RE = re.compile(
    r"(?i)((?:__Host-fvp_session|fvp_session|fvp_oauth_bind|id_token|access_token|refresh_token|client_secret|code|bearer)\s*[=:]\s*)([^\s&;\"',]+)"
)

TokenExchangerFn = Callable[[str, str, str, str, str], dict[str, Any]]


def redact_pii(message: str) -> str:
    """Redact emails, session tokens, OAuth codes, and secrets from error/log strings."""
    if not message:
        return ""
    scrubbed = _PII_SECRET_SCAN_RE.sub(r"\1[REDACTED]", str(message))
    scrubbed = _PII_EMAIL_SCAN_RE.sub("[REDACTED_EMAIL]", scrubbed)
    return scrubbed


class AuthError(Exception):
    """Structured authentication/authorization error with safe HTTP status and redacted message."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = int(status_code)
        self.safe_message = redact_pii(message)
        super().__init__(self.safe_message)


def sha256_hex(raw_value: str) -> str:
    """Return hex-encoded SHA-256 digest of `raw_value`."""
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


def _const_time_str_eq(left_val: str, right_val: str) -> bool:
    """Constant-time UTF-8 byte comparison safe for arbitrary Unicode strings."""
    return hmac.compare_digest(left_val.encode("utf-8"), right_val.encode("utf-8"))


def pkce_s256_challenge(code_verifier: str) -> str:
    """Compute RFC 7636 S256 `code_challenge` from `code_verifier`."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padded = segment + "=" * ((4 - len(segment) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def build_unsigned_or_hs256_jwt_for_test(
    claims: dict[str, Any], alg: str = "RS256"
) -> str:
    """Construct a standard 3-part base64url JWT string for offline test token exchangers."""
    header_b64 = (
        base64.urlsafe_b64encode(
            json.dumps({"alg": alg, "typ": "JWT"}, separators=(",", ":")).encode("utf-8")
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    payload_b64 = (
        base64.urlsafe_b64encode(
            json.dumps(claims, separators=(",", ":")).encode("utf-8")
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    sig_b64 = (
        base64.urlsafe_b64encode(b"tls-token-endpoint-verified-sig")
        .rstrip(b"=")
        .decode("ascii")
    )
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def sanitize_return_to(raw_target: Optional[str]) -> str:
    """Ensure post-login redirect stays strictly on a local relative path."""
    if not raw_target or not isinstance(raw_target, str):
        return "/"
    if any(ord(ch) < 0x20 or ord(ch) >= 0x7F for ch in raw_target):
        return "/"
    cleaned = raw_target.strip()[:256]
    if (
        not cleaned.startswith("/")
        or (len(cleaned) > 1 and cleaned[1] in ("/", "\\"))
        or any(ord(ch) <= 0x20 or ord(ch) >= 0x7F for ch in cleaned)
        or "\\" in cleaned
        or "://" in cleaned.split("?", 1)[0]
    ):
        return "/"
    unquoted = urllib.parse.unquote(cleaned)
    if (
        not unquoted.startswith("/")
        or (len(unquoted) > 1 and unquoted[1] in ("/", "\\"))
        or any(ord(ch) < 0x20 or ord(ch) >= 0x7F for ch in unquoted)
        or "\\" in unquoted.split("?", 1)[0]
        or "://" in unquoted.split("?", 1)[0]
    ):
        return "/"
    parsed = urllib.parse.urlsplit(cleaned)
    if (
        parsed.scheme
        or parsed.netloc
        or not parsed.path.startswith("/")
        or parsed.path.startswith("//")
    ):
        return "/"
    return cleaned


def parse_cookies_header(raw_cookie_header: Optional[str]) -> dict[str, str]:
    """Safely parse HTTP `Cookie` header into a dict without raising on malformed neighbours."""
    if not raw_cookie_header:
        return {}
    result: dict[str, str] = {}
    try:
        sc = SimpleCookie()
        sc.load(raw_cookie_header)
        for k, morsel in sc.items():
            result[k] = morsel.value
    except Exception:
        pass
    for part in raw_cookie_header.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            k_clean = k.strip()
            v_clean = v.strip().strip('"')
            if k_clean and k_clean not in result:
                result[k_clean] = v_clean
    return result


def _normalize_headers(headers: Optional[dict[str, str]]) -> dict[str, str]:
    if not headers:
        return {}
    return {str(k).strip().lower(): str(v).strip() for k, v in headers.items()}


def _is_loopback_host(host_value: str) -> bool:
    if not host_value:
        return True
    raw = host_value.strip().lower()
    if "://" in raw:
        parsed = urllib.parse.urlsplit(raw)
        hostname = (parsed.hostname or "").lower()
    else:
        if raw.startswith("["):
            end_bracket = raw.find("]")
            hostname = raw[1:end_bracket] if end_bracket != -1 else raw
        else:
            hostname = raw.split(":", 1)[0]
    return hostname in ("", "127.0.0.1", "localhost", "::1", "testserver")


def _default_google_token_exchanger(
    code: str,
    code_verifier: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    """Exchange authorization `code` + PKCE `code_verifier` at `https://oauth2.googleapis.com/token` over verified TLS."""
    form_data = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        GOOGLE_TOKEN_ENDPOINT,
        data=form_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    ssl_ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=10.0) as resp:
            raw_bytes = resp.read(65536)
            parsed = json.loads(raw_bytes.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise AuthError(401, "Invalid token response from Google OAuth endpoint.")
            return parsed
    except AuthError:
        raise
    except urllib.error.HTTPError as exc:
        raise AuthError(401, f"Google OAuth token exchange rejected ({exc.code}).") from exc
    except Exception as exc:
        raise AuthError(503, "Unable to reach Google OAuth token endpoint.") from exc


class GoogleOAuthService:
    """Pure-stdlib Google OAuth 2.0 + PKCE + Session + CSRF service."""

    def __init__(
        self,
        repository: SQLiteRepository,
        token_exchanger: Optional[TokenExchangerFn] = None,
    ) -> None:
        self.repository = repository
        self.token_exchanger = token_exchanger
        self.client_id: Optional[str] = None
        self.client_secret: Optional[str] = None
        self.redirect_uri: Optional[str] = None
        # Ephemeral bounded store used ONLY when triple-gated local test mode is active
        self._local_test_codes: dict[str, dict[str, Any]] = {}
        self._test_codes_lock = threading.RLock()

    # ------------------------------------------------------------------
    # Dynamic Environment & Transport Resolution
    # ------------------------------------------------------------------
    def get_client_id(self) -> str:
        if self.client_id and str(self.client_id).strip():
            return str(self.client_id).strip()
        return os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()

    def get_client_secret(self) -> str:
        if self.client_secret and str(self.client_secret).strip():
            return str(self.client_secret).strip()
        return os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()

    @staticmethod
    def get_public_base_url() -> str:
        return os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")

    @staticmethod
    def get_session_ttl_seconds() -> int:
        raw = os.environ.get("SESSION_TTL_SECONDS", "").strip()
        if raw:
            try:
                return max(60, int(raw))
            except ValueError:
                pass
        return DEFAULT_SESSION_TTL_SECONDS

    @staticmethod
    def get_allowed_email_domains() -> set[str]:
        raw = os.environ.get(
            "GOOGLE_OAUTH_ALLOWED_DOMAINS", "gmail.com,googlemail.com"
        ).strip()
        if not raw:
            return {"gmail.com", "googlemail.com"}
        return {part.strip().lower() for part in raw.split(",") if part.strip()}

    def is_oauth_configured(self) -> bool:
        return bool(self.get_client_id() and self.get_client_secret())

    def is_https_request(self, request_headers: Optional[dict[str, str]] = None) -> bool:
        hdrs = _normalize_headers(request_headers)
        xf_proto = hdrs.get("x-forwarded-proto", "")
        if xf_proto:
            first_proto = xf_proto.split(",", 1)[0].strip().lower()
            if first_proto == "https":
                return True
        pub = self.get_public_base_url().lower()
        return pub.startswith("https://")

    def is_test_mode_allowed(
        self, request_headers: Optional[dict[str, str]] = None
    ) -> bool:
        """Strictly triple-gated local test-only mock OAuth check:
        1. `VACATION_PLANNER_AUTH_TEST_MODE == "1"`
        2. `ELAL_LIVE_FETCH_ENABLED` is NOT `"1"` / `"true"`
        3. Both `PUBLIC_BASE_URL` and request `Host` / `X-Forwarded-Host` are loopback/in-process.
        """
        if os.environ.get("VACATION_PLANNER_AUTH_TEST_MODE", "").strip() != "1":
            return False
        if os.environ.get("ELAL_LIVE_FETCH_ENABLED", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            return False
        pub = self.get_public_base_url()
        if pub and not _is_loopback_host(pub):
            return False
        hdrs = _normalize_headers(request_headers)
        for h_key in ("x-forwarded-host", "host"):
            h_val = hdrs.get(h_key, "")
            if h_val:
                first_host = h_val.split(",", 1)[0].strip()
                if not _is_loopback_host(first_host):
                    return False
        return True

    def resolve_redirect_uri(
        self, request_headers: Optional[dict[str, str]] = None
    ) -> str:
        if self.redirect_uri and str(self.redirect_uri).strip():
            return str(self.redirect_uri).strip()
        explicit = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
        if explicit:
            return explicit
        pub = self.get_public_base_url()
        if pub:
            return f"{pub}/api/v1/auth/google/callback"
        hdrs = _normalize_headers(request_headers)
        host = (
            hdrs.get("x-forwarded-host", "").split(",", 1)[0].strip()
            or hdrs.get("host", "").strip()
            or "127.0.0.1:8000"
        )
        scheme = "https" if self.is_https_request(request_headers) else "http"
        return f"{scheme}://{host}/api/v1/auth/google/callback"

    # ------------------------------------------------------------------
    # Cookie Builders & Session / CSRF Resolution
    # ------------------------------------------------------------------
    def build_session_set_cookie(
        self, raw_token: str, is_https: bool, max_age: Optional[int] = None
    ) -> str:
        ttl = self.get_session_ttl_seconds() if max_age is None else int(max_age)
        cookie_name = SESSION_COOKIE_SECURE if is_https else SESSION_COOKIE_LOCAL
        parts = [
            f"{cookie_name}={raw_token}",
            "HttpOnly",
            "SameSite=Lax",
            "Path=/",
            f"Max-Age={ttl}",
        ]
        if is_https:
            parts.insert(2, "Secure")
        return "; ".join(parts)

    @staticmethod
    def build_oauth_bind_set_cookie(raw_bind: str, is_https: bool) -> str:
        parts = [
            f"{OAUTH_BIND_COOKIE}={raw_bind}",
            "HttpOnly",
            "SameSite=Lax",
            "Path=/",
            f"Max-Age={OAUTH_STATE_TTL_SECONDS}",
        ]
        if is_https:
            parts.insert(2, "Secure")
        return "; ".join(parts)

    @staticmethod
    def build_clear_oauth_bind_cookie(is_https: bool) -> str:
        parts = [
            f"{OAUTH_BIND_COOKIE}=",
            "HttpOnly",
            "SameSite=Lax",
            "Path=/",
            "Max-Age=0",
        ]
        if is_https:
            parts.insert(2, "Secure")
        return "; ".join(parts)

    @staticmethod
    def build_clear_session_cookies(is_https: bool) -> list[str]:
        cleared = [
            f"{SESSION_COOKIE_LOCAL}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"
        ]
        if is_https:
            cleared.insert(
                0,
                f"{SESSION_COOKIE_SECURE}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0",
            )
        else:
            cleared.append(
                f"{SESSION_COOKIE_SECURE}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0"
            )
        return cleared

    def extract_raw_session_token(
        self, request_headers: Optional[dict[str, str]] = None
    ) -> Optional[str]:
        hdrs = _normalize_headers(request_headers)
        cookies = parse_cookies_header(hdrs.get("cookie"))
        if SESSION_COOKIE_SECURE in cookies and cookies[SESSION_COOKIE_SECURE]:
            return cookies[SESSION_COOKIE_SECURE]
        # Allow local cookie name only when PUBLIC_BASE_URL is not HTTPS
        if not self.get_public_base_url().lower().startswith("https://"):
            if SESSION_COOKIE_LOCAL in cookies and cookies[SESSION_COOKIE_LOCAL]:
                return cookies[SESSION_COOKIE_LOCAL]
        return None

    def resolve_session(
        self, request_headers: Optional[dict[str, str]] = None
    ) -> Optional[dict[str, Any]]:
        """Return active `{session_id, user_id, csrf_token, expires_at, user}` or `None`."""
        raw_token = self.extract_raw_session_token(request_headers)
        if not raw_token or len(raw_token) > 256:
            return None
        return self.repository.get_active_session_by_token_hash(sha256_hex(raw_token))

    def require_session(
        self, request_headers: Optional[dict[str, str]] = None
    ) -> dict[str, Any]:
        session = self.resolve_session(request_headers)
        if session is None:
            raise AuthError(401, "Authentication required. Please sign in with Gmail.")
        return session

    def verify_csrf(
        self,
        session: dict[str, Any],
        request_headers: Optional[dict[str, str]] = None,
    ) -> None:
        """Enforce `X-CSRF-Token` constant-time match and same-origin `Origin` check (`403` on failure)."""
        hdrs = _normalize_headers(request_headers)
        provided_csrf = hdrs.get("x-csrf-token", "")
        expected_csrf = str(session.get("csrf_token") or "")
        if (
            not provided_csrf
            or not expected_csrf
            or not _const_time_str_eq(provided_csrf, expected_csrf)
        ):
            raise AuthError(403, "CSRF validation failed: missing or invalid X-CSRF-Token.")

        origin = hdrs.get("origin", "")
        if origin:
            if origin.strip().lower() == "null" or any(
                ord(ch) <= 0x20 or ord(ch) == 0x7F for ch in origin.strip()
            ):
                raise AuthError(403, "CSRF validation failed: null Origin header rejected.")
            try:
                parsed_origin = urllib.parse.urlsplit(origin.strip())
            except Exception as exc:
                raise AuthError(403, "CSRF validation failed: malformed Origin header.") from exc
            origin_scheme = (parsed_origin.scheme or "").strip().lower()
            origin_netloc = (parsed_origin.netloc or "").strip().lower()
            if origin_scheme not in ("http", "https") or not origin_netloc:
                raise AuthError(403, "CSRF validation failed: malformed Origin header.")
            if self.is_https_request(request_headers) and origin_scheme != "https":
                raise AuthError(
                    403,
                    "CSRF validation failed: Origin scheme must be https.",
                )

            pub = self.get_public_base_url()
            pub_netloc = (
                (urllib.parse.urlsplit(pub).netloc or "").strip().lower() if pub else ""
            )
            if pub_netloc:
                allowed_netlocs = {pub_netloc}
            else:
                host_hdr = hdrs.get("host", "").split(",", 1)[0].strip().lower()
                if host_hdr:
                    allowed_netlocs = {host_hdr}
                else:
                    allowed_netlocs = {
                        "127.0.0.1",
                        "localhost",
                        "127.0.0.1:8000",
                        "localhost:8000",
                        "testserver",
                    }

            if origin_netloc not in allowed_netlocs:
                raise AuthError(
                    403, "CSRF validation failed: Origin does not match server host."
                )

    # ------------------------------------------------------------------
    # OAuth 2.0 + PKCE Login Initiation & Callback Verification
    # ------------------------------------------------------------------
    def start_login(
        self,
        request_headers: Optional[dict[str, str]] = None,
        query_params: Optional[dict[str, str]] = None,
    ) -> tuple[int, dict[str, Any], str]:
        q = query_params or {}
        oauth_ok = self.is_oauth_configured()
        test_ok = self.is_test_mode_allowed(request_headers)
        if not oauth_ok and not test_ok:
            raise AuthError(
                503,
                "Google OAuth 2.0 is not configured on this server (missing GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET).",
            )

        return_to = sanitize_return_to(q.get("return_to") or "/")
        is_https = self.is_https_request(request_headers)

        raw_state = secrets.token_urlsafe(32)
        raw_bind = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(48)
        code_challenge = pkce_s256_challenge(code_verifier)
        nonce = secrets.token_urlsafe(24)
        expires_at = (
            datetime.now(UTC).replace(microsecond=0)
            + timedelta(seconds=OAUTH_STATE_TTL_SECONDS)
        ).isoformat().replace("+00:00", "Z")

        self.repository.create_oauth_login_state(
            state_sha256=sha256_hex(raw_state),
            code_verifier=code_verifier,
            nonce=nonce,
            browser_binding_sha256=sha256_hex(raw_bind),
            return_to=return_to,
            expires_at=expires_at,
        )

        redirect_uri = self.resolve_redirect_uri(request_headers)
        use_local_mock = test_ok and (
            not oauth_ok
            or q.get("mock_oauth") == "1"
            or bool(q.get("test_email"))
        )

        if use_local_mock:
            client_id = self.get_client_id() or LOCAL_TEST_CLIENT_ID
            mock_params: dict[str, str] = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": raw_state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
            if q.get("test_email"):
                mock_params["test_email"] = str(q["test_email"]).strip()
            if q.get("test_name"):
                mock_params["test_name"] = str(q["test_name"]).strip()
            if q.get("test_sub"):
                mock_params["test_sub"] = str(q["test_sub"]).strip()
            if q.get("lang") in ("he", "en"):
                mock_params["lang"] = str(q["lang"])
            target_url = f"/api/v1/auth/test-oauth-authorize?{urllib.parse.urlencode(mock_params)}"
        else:
            client_id = self.get_client_id()
            auth_params = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": raw_state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
            target_url = f"{GOOGLE_AUTH_ENDPOINT}?{urllib.parse.urlencode(auth_params)}"

        headers: dict[str, Any] = {
            "Location": target_url,
            "Set-Cookie": [self.build_oauth_bind_set_cookie(raw_bind, is_https)],
            "Cache-Control": "no-store, private",
            "Vary": "Cookie",
            "Content-Type": "application/json; charset=utf-8",
        }
        return 302, headers, json.dumps({"redirect": target_url})

    def handle_test_oauth_authorize(
        self,
        request_headers: Optional[dict[str, str]] = None,
        query_params: Optional[dict[str, str]] = None,
    ) -> tuple[int, dict[str, Any], str]:
        """Strictly triple-gated local loopback OAuth consent screen & code issuer (`404` otherwise)."""
        if not self.is_test_mode_allowed(request_headers):
            return (
                404,
                {
                    "Content-Type": "application/json; charset=utf-8",
                    "Cache-Control": "no-store, private",
                },
                json.dumps({"error": "Not found"}),
            )

        q = query_params or {}
        state_val = str(q.get("state") or "").strip()
        nonce_val = str(q.get("nonce") or "").strip()
        code_challenge = str(q.get("code_challenge") or "").strip()
        challenge_method = str(q.get("code_challenge_method") or "S256").strip()
        client_id = str(q.get("client_id") or self.get_client_id() or LOCAL_TEST_CLIENT_ID).strip()
        lang = "en" if q.get("lang") == "en" else "he"

        if not state_val or not nonce_val or not code_challenge or challenge_method != "S256":
            raise AuthError(400, "Invalid test OAuth authorization parameters.")

        chosen_email = str(q.get("test_email") or "").strip().lower()
        if chosen_email:
            if not _EMAIL_RE.match(chosen_email):
                raise AuthError(400, "Invalid test Gmail address format.")
            chosen_sub = str(q.get("test_sub") or f"google-sub-{sha256_hex(chosen_email)[:24]}").strip()
            chosen_name = str(q.get("test_name") or chosen_email.split("@", 1)[0]).strip()[:120]

            now_ts = time.time()
            raw_code = f"local_test_code_{secrets.token_urlsafe(24)}"
            with self._test_codes_lock:
                # Evict expired or excess test codes atomically
                expired_keys = [
                    k
                    for k, v in self._local_test_codes.items()
                    if v["expires_epoch"] <= now_ts
                ]
                for k in expired_keys:
                    self._local_test_codes.pop(k, None)
                if len(self._local_test_codes) >= 256:
                    oldest_key = next(iter(self._local_test_codes))
                    self._local_test_codes.pop(oldest_key, None)

                self._local_test_codes[raw_code] = {
                    "code_challenge": code_challenge,
                    "nonce": nonce_val,
                    "client_id": client_id,
                    "email": chosen_email,
                    "sub": chosen_sub,
                    "name": chosen_name,
                    "expires_epoch": now_ts + 300.0,
                }
            cb_qs = urllib.parse.urlencode({"code": raw_code, "state": state_val})
            cb_loc = f"/api/v1/auth/google/callback?{cb_qs}"
            return (
                302,
                {
                    "Location": cb_loc,
                    "Cache-Control": "no-store, private",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json.dumps({"redirect": cb_loc}),
            )

        # Render minimal local-only offline account chooser HTML for Headless Chrome verification
        dir_attr = "ltr" if lang == "en" else "rtl"
        title_txt = (
            "Sign in with Gmail (Local Test Mode)"
            if lang == "en"
            else "התחברות עם Gmail (מצב בדיקה מקומי)"
        )
        btn_txt = "Continue" if lang == "en" else "המשך לחשבון"
        hidden_inputs = "".join(
            f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(str(q.get(k, "")))}" />'
            for k in (
                "client_id",
                "redirect_uri",
                "response_type",
                "scope",
                "state",
                "nonce",
                "code_challenge",
                "code_challenge_method",
                "lang",
            )
        )
        chooser_html = f"""<!DOCTYPE html>
<html lang="{lang}" dir="{dir_attr}">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(title_txt)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background: #F2F5F9; color: #0B1F3A; margin: 0; padding: 24px; }}
    .box {{ max-width: 420px; margin-inline: auto; background: #FFFFFF; border: 1px solid #B4C5DC; border-radius: 12px; padding: 20px; }}
    h1 {{ font-size: 1.15rem; margin-block: 0 12px; }}
    label {{ display: block; font-weight: 600; margin-block-end: 6px; }}
    input[type="email"], input[type="text"] {{ width: 100%; box-sizing: border-box; min-height: 38px; padding-inline: 10px; margin-block-end: 12px; border: 1px solid #B4C5DC; border-radius: 8px; font-size: 14px; }}
    button {{ min-height: 38px; width: 100%; border-radius: 8px; border: 1px solid #0B2E63; background: #1452A6; color: #FFFFFF; font-weight: 700; font-size: 14px; cursor: pointer; }}
  </style>
</head>
<body>
  <main class="box">
    <h1>{html.escape(title_txt)}</h1>
    <form method="GET" action="/api/v1/auth/test-oauth-authorize" id="test-oauth-form">
      {hidden_inputs}
      <label for="test-oauth-email-input">Gmail:</label>
      <input type="email" id="test-oauth-email-input" name="test_email" value="alice@gmail.com" dir="ltr" required />
      <label for="test-oauth-name-input">Name:</label>
      <input type="text" id="test-oauth-name-input" name="test_name" value="Alice" />
      <button type="submit" id="btn-test-oauth-continue">{html.escape(btn_txt)}</button>
    </form>
  </main>
</body>
</html>"""
        return (
            200,
            {
                "Content-Type": "text/html; charset=utf-8",
                "Cache-Control": "no-store, private",
            },
            chooser_html,
        )

    def handle_callback(
        self,
        request_headers: Optional[dict[str, str]] = None,
        query_params: Optional[dict[str, str]] = None,
    ) -> tuple[int, dict[str, Any], str]:
        q = query_params or {}
        is_https = self.is_https_request(request_headers)

        if q.get("error"):
            raise AuthError(400, "Google OAuth login was cancelled or denied.")

        raw_code = str(q.get("code") or "").strip()
        raw_state = str(q.get("state") or "").strip()
        if not raw_code or not raw_state:
            raise AuthError(400, "Missing OAuth authorization code or state parameter.")

        # 1. Atomically consume single-use state row (prevents replay even on downstream failure)
        state_row = self.repository.consume_oauth_login_state(sha256_hex(raw_state))
        if state_row is None:
            raise AuthError(400, "Invalid, unknown, or replayed OAuth state parameter.")

        # 2. Check 10-minute state expiration
        now_dt = datetime.now(UTC).replace(microsecond=0)
        exp_str = str(state_row.get("expires_at") or "")
        if exp_str.endswith("Z"):
            exp_str = exp_str[:-1] + "+00:00"
        try:
            exp_dt = datetime.fromisoformat(exp_str)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=UTC)
        except ValueError as exc:
            raise AuthError(400, "Corrupted OAuth state expiration timestamp.") from exc
        if exp_dt <= now_dt:
            raise AuthError(400, "Expired OAuth login state; please start sign-in again.")

        # 3. Constant-time Login-CSRF browser binding cookie check
        hdrs = _normalize_headers(request_headers)
        cookies = parse_cookies_header(hdrs.get("cookie"))
        raw_bind_cookie = cookies.get(OAUTH_BIND_COOKIE, "")
        expected_bind_hash = str(state_row.get("browser_binding_sha256") or "")
        if not raw_bind_cookie or not _const_time_str_eq(
            sha256_hex(raw_bind_cookie), expected_bind_hash
        ):
            raise AuthError(
                400,
                "OAuth browser binding cookie missing or mismatched (Login-CSRF check failed).",
            )

        redirect_uri = self.resolve_redirect_uri(request_headers)
        code_verifier = str(state_row["code_verifier"])
        expected_nonce = str(state_row["nonce"])

        # 4. Exchange authorization code + PKCE code_verifier
        test_ok = self.is_test_mode_allowed(request_headers)
        local_code_meta: Optional[dict[str, Any]] = None
        if self.token_exchanger is None and test_ok:
            with self._test_codes_lock:
                local_code_meta = self._local_test_codes.pop(raw_code, None)

        if self.token_exchanger is not None:
            expected_client_id = self.get_client_id() or LOCAL_TEST_CLIENT_ID
            client_secret = self.get_client_secret() or "injected-test-secret"
            token_resp = self.token_exchanger(
                raw_code,
                code_verifier,
                redirect_uri,
                expected_client_id,
                client_secret,
            )
        elif local_code_meta is not None:
            code_meta = local_code_meta
            if code_meta["expires_epoch"] <= time.time():
                raise AuthError(401, "Expired local test authorization code.")
            computed_challenge = pkce_s256_challenge(code_verifier)
            if not _const_time_str_eq(
                computed_challenge, str(code_meta["code_challenge"])
            ):
                raise AuthError(401, "PKCE S256 code_verifier mismatch.")
            expected_client_id = code_meta["client_id"]
            now_epoch = int(time.time())
            id_token_jwt = build_unsigned_or_hs256_jwt_for_test(
                {
                    "iss": "https://accounts.google.com",
                    "aud": expected_client_id,
                    "sub": code_meta["sub"],
                    "email": code_meta["email"],
                    "email_verified": True,
                    "name": code_meta["name"],
                    "nonce": code_meta["nonce"],
                    "iat": now_epoch,
                    "exp": now_epoch + 3600,
                }
            )
            token_resp = {
                "id_token": id_token_jwt,
                "access_token": "discarded-ephemeral-access-token",
                "token_type": "Bearer",
                "expires_in": 3599,
            }
        else:
            expected_client_id = self.get_client_id()
            client_secret = self.get_client_secret()
            if not expected_client_id or not client_secret:
                raise AuthError(503, "Google OAuth credentials are not configured.")
            token_resp = _default_google_token_exchanger(
                raw_code,
                code_verifier,
                redirect_uri,
                expected_client_id,
                client_secret,
            )

        if not isinstance(token_resp, dict) or not token_resp.get("id_token"):
            raise AuthError(401, "OAuth token response did not include an OIDC id_token.")

        id_token_raw = str(token_resp["id_token"])
        # Explicitly discard access_token / refresh_token immediately (data minimization)
        token_resp.clear()

        # 5. Validate OIDC ID Token claims (OIDC Core 1.0 §3.1.3.7)
        claims = self.validate_oidc_id_token(
            id_token_raw=id_token_raw,
            expected_client_id=expected_client_id,
            expected_nonce=expected_nonce,
        )

        # 6. Upsert verified user & issue revocable SHA-256-hashed session
        try:
            user = self.repository.upsert_google_user(
                google_sub=claims["sub"],
                email=claims["email"],
                email_verified=True,
                display_name=claims["name"],
            )
        except ValueError as exc:
            raise AuthError(403, str(exc)) from exc
        raw_session_token = f"fvp_{secrets.token_urlsafe(32)}"
        csrf_token = secrets.token_urlsafe(32)
        ttl_seconds = self.get_session_ttl_seconds()
        sess_expires_at = (
            now_dt + timedelta(seconds=ttl_seconds)
        ).isoformat().replace("+00:00", "Z")
        self.repository.create_auth_session(
            user_id=user["id"],
            token_sha256=sha256_hex(raw_session_token),
            csrf_token=csrf_token,
            expires_at=sess_expires_at,
        )

        safe_target = sanitize_return_to(str(state_row.get("return_to") or "/"))
        headers = {
            "Location": safe_target,
            "Set-Cookie": [
                self.build_session_set_cookie(raw_session_token, is_https, ttl_seconds),
                self.build_clear_oauth_bind_cookie(is_https),
            ],
            "Cache-Control": "no-store, private",
            "Vary": "Cookie",
            "Content-Type": "application/json; charset=utf-8",
        }
        return 302, headers, json.dumps({"authenticated": True, "redirect": safe_target})

    def validate_oidc_id_token(
        self,
        id_token_raw: str,
        expected_client_id: str,
        expected_nonce: str,
    ) -> dict[str, str]:
        """Validate Google OIDC `id_token` structure and claims (`iss`, `aud`, `exp`, `iat`, `nonce`, `sub`, `email_verified`, domain)."""
        parts = id_token_raw.split(".")
        if len(parts) != 3 or not all(parts):
            raise AuthError(401, "Malformed OIDC id_token JWT structure.")
        try:
            header = json.loads(_b64url_decode(parts[0]).decode("utf-8"))
            claims = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
        except Exception as exc:
            raise AuthError(401, "Invalid base64url or JSON in OIDC id_token.") from exc

        if not isinstance(header, dict) or not isinstance(claims, dict):
            raise AuthError(401, "Invalid JWT header or payload object.")

        alg = str(header.get("alg") or "").upper()
        if alg not in ("RS256", "ES256"):
            raise AuthError(401, f"Unsupported or insecure JWT alg: {alg!r}.")

        iss = str(claims.get("iss") or "")
        if iss not in VALID_GOOGLE_ISSUERS:
            raise AuthError(401, "Invalid OIDC token issuer.")

        aud = claims.get("aud")
        if isinstance(aud, str):
            aud_ok = _const_time_str_eq(aud, expected_client_id)
        elif isinstance(aud, list):
            aud_ok = any(
                _const_time_str_eq(str(a), expected_client_id) for a in aud
            ) and _const_time_str_eq(str(claims.get("azp") or ""), expected_client_id)
        else:
            aud_ok = False
        if not aud_ok:
            raise AuthError(401, "OIDC audience mismatch.")

        now_epoch = int(time.time())
        try:
            exp = int(claims["exp"])
            iat = int(claims["iat"])
        except Exception as exc:
            raise AuthError(401, "Missing or non-integer exp/iat claim in id_token.") from exc

        if exp <= now_epoch:
            raise AuthError(401, "OIDC id_token has expired.")
        if iat <= 0 or iat > now_epoch + 300:
            raise AuthError(401, "OIDC id_token issued-at timestamp is out of bounds.")

        token_nonce = str(claims.get("nonce") or "")
        if (
            not expected_nonce
            or not token_nonce
            or not _const_time_str_eq(token_nonce, expected_nonce)
        ):
            raise AuthError(401, "OIDC nonce claim mismatch.")

        sub = str(claims.get("sub") or "").strip()
        if not sub or len(sub) > 255:
            raise AuthError(401, "Missing or invalid Google subject (sub) claim.")

        raw_ev = claims.get("email_verified")
        email_verified = raw_ev is True or (
            isinstance(raw_ev, str) and raw_ev.strip().lower() == "true"
        )
        if not email_verified:
            raise AuthError(403, "Google account email is not verified.")

        email = str(claims.get("email") or "").strip().lower()
        if not email or len(email) > 254 or not _EMAIL_RE.match(email):
            raise AuthError(403, "Missing or invalid email address in Google account.")

        domain = email.rsplit("@", 1)[-1]
        allowed_domains = self.get_allowed_email_domains()
        if "*" not in allowed_domains and domain not in allowed_domains:
            raise AuthError(
                403,
                "Only verified Gmail accounts (@gmail.com / @googlemail.com) are permitted.",
            )

        display_name = str(claims.get("name") or "").strip()[:120]
        return {
            "sub": sub,
            "email": email,
            "name": display_name,
        }

    def handle_test_login_direct(
        self,
        json_body: Optional[dict[str, Any]],
        request_headers: Optional[dict[str, str]] = None,
    ) -> tuple[int, dict[str, Any], str]:
        """Triple-gated `POST /api/v1/auth/test-login` endpoint (`404` whenever any gate fails)."""
        if not self.is_test_mode_allowed(request_headers):
            return (
                404,
                {
                    "Content-Type": "application/json; charset=utf-8",
                    "Cache-Control": "no-store, private",
                },
                json.dumps({"error": "Not found"}),
            )
        if not isinstance(json_body, dict):
            raise AuthError(400, "Request body must be a JSON object.")
        email = str(json_body.get("email") or "").strip().lower()
        if not email or not _EMAIL_RE.match(email):
            raise AuthError(400, "Valid email is required.")
        domain = email.rsplit("@", 1)[-1]
        allowed_domains = self.get_allowed_email_domains()
        if "*" not in allowed_domains and domain not in allowed_domains:
            raise AuthError(403, "Disallowed email domain.")
        sub = str(
            json_body.get("google_sub") or f"google-sub-{sha256_hex(email)[:24]}"
        ).strip()
        display_name = str(json_body.get("display_name") or "").strip()[:120]
        try:
            user = self.repository.upsert_google_user(
                google_sub=sub,
                email=email,
                email_verified=True,
                display_name=display_name,
            )
        except ValueError as exc:
            raise AuthError(403, str(exc)) from exc
        is_https = self.is_https_request(request_headers)
        raw_session_token = f"fvp_{secrets.token_urlsafe(32)}"
        csrf_token = secrets.token_urlsafe(32)
        ttl_seconds = self.get_session_ttl_seconds()
        expires_at = (
            datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=ttl_seconds)
        ).isoformat().replace("+00:00", "Z")
        self.repository.create_auth_session(
            user_id=user["id"],
            token_sha256=sha256_hex(raw_session_token),
            csrf_token=csrf_token,
            expires_at=expires_at,
        )
        headers: dict[str, Any] = {
            "Set-Cookie": [
                self.build_session_set_cookie(raw_session_token, is_https, ttl_seconds)
            ],
            "Cache-Control": "no-store, private",
            "Vary": "Cookie",
            "Content-Type": "application/json; charset=utf-8",
        }
        payload = {
            "authenticated": True,
            "csrf_token": csrf_token,
            "user": user,
        }
        return 200, headers, json.dumps(payload, ensure_ascii=False)
