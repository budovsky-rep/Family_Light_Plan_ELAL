"""Authenticated Vacation Plan Email Sharing Service (SMTP + Bilingual RTL/LTR Templates).

Provides:
- Pure-stdlib `smtplib` + `email.message.EmailMessage` delivery over STARTTLS (`587`) or SMTPS (`465`).
- Strict recipient email validation (1..3 addresses, zero CRLF/header-injection risk).
- Per-user rolling-hour rate limiting (`MAX_EMAILS_PER_USER_PER_HOUR`, default `10`).
- Bilingual Hebrew (`dir="rtl"`) and English (`dir="ltr"`) HTML + plain-text vacation plan emails.
- Safe `SMTP_TEST_MODE=1` in-memory outbox (strictly gated off in production when
  `ELAL_LIVE_FETCH_ENABLED=1` or non-loopback `PUBLIC_BASE_URL` / `Host` is active).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr
import html
import os
import re
import smtplib
import ssl
import threading
import time
import urllib.parse
from typing import Any, Callable, Optional


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,253}\.[A-Za-z]{2,24}$")
_CONTROL_RE = re.compile(r"[\r\n\x00-\x08\x0b\x0c\x0e-\x1f]")
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver", ""}


class ShareEmailError(Exception):
    """Structured HTTP-mapped error raised by `ShareEmailService`."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        error_code: str = "share_email_error",
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = int(status_code)
        self.detail = str(detail)
        self.error_code = str(error_code)
        self.extra = dict(extra or {})


def _clean_single_line(val: Any, max_len: int = 180) -> str:
    txt = _CONTROL_RE.sub(" ", str(val or "")).strip()
    txt = re.sub(r"\s+", " ", txt)
    return txt[:max_len]


def _clean_multiline(val: Any, max_len: int = 320) -> str:
    raw = str(val or "").replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw).strip()
    return raw[:max_len]


def _safe_http_url(val: Any, max_len: int = 1200) -> str:
    raw = _clean_single_line(val, max_len=max_len)
    if not raw:
        return ""
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        return ""
    return raw


def _parse_host_only(host_header: str) -> str:
    raw = str(host_header or "").strip().lower()
    if raw.startswith("[") and "]" in raw:
        return raw[1 : raw.index("]")]
    return raw.split(":", 1)[0].strip()


@dataclass
class ShareEmailService:
    """Validates, formats, rate-limits, and dispatches shared vacation plan emails."""

    max_recipients: int = 3
    max_per_user_per_hour: int = 10
    rate_window_seconds: int = 3600
    smtp_timeout_seconds: float = 15.0
    smtp_transport_override: Optional[Callable[[EmailMessage, dict[str, Any]], None]] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _rate_buckets: dict[str, deque[float]] = field(default_factory=dict, init=False, repr=False)
    _test_outbox: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)

    @staticmethod
    def is_test_mode_allowed(request_headers: Optional[dict[str, str]] = None) -> bool:
        """Allow `SMTP_TEST_MODE=1` strictly on local loopback test environments."""
        if str(os.environ.get("SMTP_TEST_MODE", "")).strip() != "1":
            return False
        if str(os.environ.get("ELAL_LIVE_FETCH_ENABLED", "")).strip() == "1":
            return False
        pub = str(os.environ.get("PUBLIC_BASE_URL", "")).strip()
        if pub:
            pub_host = _parse_host_only(urllib.parse.urlsplit(pub).netloc)
            if pub_host not in _LOOPBACK_HOSTS:
                return False
        if request_headers:
            lowered = {str(k).lower(): str(v) for k, v in request_headers.items()}
            host = _parse_host_only(lowered.get("x-forwarded-host") or lowered.get("host", ""))
            if host and host not in _LOOPBACK_HOSTS:
                return False
        return True

    @staticmethod
    def get_smtp_config() -> dict[str, Any]:
        host = str(os.environ.get("SMTP_HOST", "")).strip()
        raw_port = str(os.environ.get("SMTP_PORT", "587")).strip()
        try:
            port = int(raw_port)
        except ValueError:
            port = 587
        username = str(os.environ.get("SMTP_USERNAME", "")).strip()
        password = str(os.environ.get("SMTP_PASSWORD", "")).strip()
        from_email = str(os.environ.get("SMTP_FROM_EMAIL", "")).strip() or username
        from_name = _clean_single_line(os.environ.get("SMTP_FROM_NAME", "breezyflights"), 80) or "breezyflights"
        use_tls_raw = str(os.environ.get("SMTP_USE_TLS", "1")).strip().lower()
        use_tls = use_tls_raw not in ("0", "false", "no", "off")
        return {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "from_email": from_email,
            "from_name": from_name,
            "use_tls": use_tls,
        }

    def is_configured(self, request_headers: Optional[dict[str, str]] = None) -> bool:
        """Return True when real SMTP credentials are present or safe local test mode is active."""
        if self.smtp_transport_override is not None:
            return True
        if self.is_test_mode_allowed(request_headers):
            return True
        cfg = self.get_smtp_config()
        return bool(cfg["host"] and cfg["from_email"] and cfg["username"] and cfg["password"])

    def get_test_outbox(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._test_outbox)

    def clear_test_outbox(self) -> None:
        with self._lock:
            self._test_outbox.clear()

    def parse_and_validate_recipients(
        self,
        raw_recipients: Any,
        default_email: str,
    ) -> list[str]:
        """Parse 1..3 recipient emails, defaulting to the verified signed-in Gmail address."""
        candidates: list[str] = []
        if raw_recipients is None:
            candidates = [default_email]
        elif isinstance(raw_recipients, str):
            parts = [p.strip() for p in re.split(r"[,;\s]+", raw_recipients) if p.strip()]
            candidates = parts if parts else [default_email]
        elif isinstance(raw_recipients, list):
            for item in raw_recipients:
                if not isinstance(item, str):
                    raise ShareEmailError(
                        422,
                        "Each recipient email must be a string.",
                        error_code="invalid_recipient",
                    )
                for part in re.split(r"[,;\s]+", item.strip()):
                    if part.strip():
                        candidates.append(part.strip())
            if not candidates:
                candidates = [default_email]
        else:
            raise ShareEmailError(
                422,
                "recipients must be an email string or list of email strings.",
                error_code="invalid_recipient",
            )

        deduped: list[str] = []
        seen: set[str] = set()
        for raw_addr in candidates:
            if _CONTROL_RE.search(raw_addr):
                raise ShareEmailError(
                    422,
                    "Recipient email contains illegal control characters.",
                    error_code="invalid_recipient",
                )
            norm = raw_addr.strip().lower()
            if len(norm) > 254 or not _EMAIL_RE.match(norm):
                raise ShareEmailError(
                    422,
                    f"Invalid recipient email address: {raw_addr[:64]}",
                    error_code="invalid_recipient",
                )
            if norm not in seen:
                seen.add(norm)
                deduped.append(norm)

        if not deduped:
            raise ShareEmailError(
                422,
                "At least one valid recipient email address is required.",
                error_code="invalid_recipient",
            )
        if len(deduped) > self.max_recipients:
            raise ShareEmailError(
                422,
                f"At most {self.max_recipients} recipients can be emailed per share.",
                error_code="too_many_recipients",
            )
        return deduped

    def _check_and_record_rate_limit(self, user_id: str, now_ts: Optional[float] = None) -> None:
        now = time.monotonic() if now_ts is None else float(now_ts)
        cutoff = now - float(self.rate_window_seconds)
        with self._lock:
            bucket = self._rate_buckets.setdefault(user_id, deque())
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_per_user_per_hour:
                raise ShareEmailError(
                    429,
                    "Hourly email share limit reached. Please try again later.",
                    error_code="rate_limit_exceeded",
                )
            bucket.append(now)

    @staticmethod
    def sanitize_plan(raw_plan: Any) -> dict[str, Any]:
        if not isinstance(raw_plan, dict):
            raise ShareEmailError(422, "plan object is required.", error_code="invalid_plan")
        dest_name = _clean_single_line(raw_plan.get("destination_name"), 100)
        origin_iata = _clean_single_line(raw_plan.get("origin_iata") or "TLV", 8).upper()
        dest_iata = _clean_single_line(raw_plan.get("destination_iata"), 8).upper()
        dep_date = _clean_single_line(raw_plan.get("departure_date"), 24)
        ret_date = _clean_single_line(raw_plan.get("return_date"), 24)
        if not dest_name or not dest_iata or not dep_date or not ret_date:
            raise ShareEmailError(
                422,
                "plan must include destination_name, destination_iata, departure_date, and return_date.",
                error_code="invalid_plan",
            )
        try:
            nights = max(1, min(60, int(raw_plan.get("trip_nights") or 1)))
        except (TypeError, ValueError):
            nights = 1
        return {
            "destination_name": dest_name,
            "origin_iata": origin_iata or "TLV",
            "destination_iata": dest_iata,
            "departure_date": dep_date,
            "return_date": ret_date,
            "trip_nights": nights,
            "outbound_flight": _clean_single_line(raw_plan.get("outbound_flight"), 160),
            "return_flight": _clean_single_line(raw_plan.get("return_flight"), 160),
            "bonus_summary": _clean_single_line(raw_plan.get("bonus_summary"), 160),
            "min_points_text": _clean_single_line(raw_plan.get("min_points_text"), 160),
            "workdays_summary": _clean_single_line(raw_plan.get("workdays_summary"), 180),
            "school_fit_summary": _clean_single_line(raw_plan.get("school_fit_summary"), 180),
            "climate_summary": _clean_single_line(raw_plan.get("climate_summary"), 160),
            "merged_holidays_text": _clean_single_line(raw_plan.get("merged_holidays_text"), 180),
            "party_summary": _clean_single_line(raw_plan.get("party_summary"), 140),
            "booking_url": _safe_http_url(raw_plan.get("booking_url")),
            "single_adult_booking_url": _safe_http_url(raw_plan.get("single_adult_booking_url")),
            "app_url": _safe_http_url(raw_plan.get("app_url")) or "https://breezyflights.com",
        }

    @classmethod
    def compose_email_content(
        cls,
        *,
        plan: dict[str, Any],
        sender_name: str,
        sender_email: str,
        locale: str = "he",
        personal_note: str = "",
    ) -> tuple[str, str, str, str]:
        """Build `(subject, plain_text_body, html_body, gmail_compose_fallback_url)`."""
        is_he = str(locale or "he").strip().lower() != "en"
        s_name = _clean_single_line(sender_name or sender_email.split("@", 1)[0], 80)
        note = _clean_multiline(personal_note, 300)
        nights_lbl = f"{plan['trip_nights']} לילות" if is_he else f"{plan['trip_nights']} nights"

        if is_he:
            subject = (
                f"תוכנית חופשה ב{plan['destination_name']} "
                f"({plan['departure_date']}–{plan['return_date']} · {nights_lbl}) | breezyflights"
            )
        else:
            subject = (
                f"Vacation Plan to {plan['destination_name']} "
                f"({plan['departure_date']}–{plan['return_date']} · {nights_lbl}) | breezyflights"
            )

        # Plain-text version
        lines: list[str] = []
        if is_he:
            lines.append(f"תוכנית חופשה משותפת מאת {s_name} ({sender_email})")
            lines.append("=" * 42)
            if note:
                lines.append(f"הערה אישית: {note}")
                lines.append("")
            lines.append(
                f"יעד: {plan['destination_name']} ({plan['origin_iata']} ⇄ {plan['destination_iata']})"
            )
            lines.append(f"תאריכים: {plan['departure_date']} עד {plan['return_date']} ({nights_lbl})")
            if plan["party_summary"]:
                lines.append(f"הרכב נוסעים: {plan['party_summary']}")
            if plan["merged_holidays_text"]:
                lines.append(f"חגים בחלון: {plan['merged_holidays_text']}")
            if plan["bonus_summary"]:
                lines.append(f"בונוס אל על: {plan['bonus_summary']}")
            if plan["min_points_text"]:
                lines.append(f"נקודות מתמיד: {plan['min_points_text']}")
            if plan["outbound_flight"]:
                lines.append(f"טיסת הלוך: {plan['outbound_flight']}")
            if plan["return_flight"]:
                lines.append(f"טיסת חזור: {plan['return_flight']}")
            if plan["workdays_summary"]:
                lines.append(f"חופשת עבודה: {plan['workdays_summary']}")
            if plan["school_fit_summary"]:
                lines.append(f"התאמה לחופשת בי\"ס: {plan['school_fit_summary']}")
            if plan["climate_summary"]:
                lines.append(f"אקלים צפוי: {plan['climate_summary']}")
            lines.append("")
            lines.append("מדריך הזמנה באל על (לפני שלוחצים על הקישור):")
            lines.append("1. עוברים ל-Google Flights, בוחרים את טיסות אל על המוצגות מעלה וממשיכים לאתר אל על.")
            lines.append("2. באתר אל על מתחברים קודם לחשבון המתמיד — ורק אז רואים את זמינות כרטיסי הבונוס.")
            lines.append("3. מעל 2 נוסעים? אם לא רואים בונוס, בדקו קודם לנוסע 1 והעלו בהדרגה (ייתכן שיש רק 1–2 כרטיסי בונוס).")
            if plan["booking_url"]:
                lines.append("")
                lines.append(f"לבדיקה והזמנה (Google Flights / אל על): {plan['booking_url']}")
            if plan["single_adult_booking_url"] and plan["single_adult_booking_url"] != plan["booking_url"]:
                lines.append(f"בדיקה מהירה לנוסע 1 בלבד: {plan['single_adult_booking_url']}")
            lines.append(f"תוכנן באמצעות breezyflights: {plan['app_url']}")
        else:
            lines.append(f"Shared vacation plan from {s_name} ({sender_email})")
            lines.append("=" * 42)
            if note:
                lines.append(f"Personal note: {note}")
                lines.append("")
            lines.append(
                f"Destination: {plan['destination_name']} ({plan['origin_iata']} ⇄ {plan['destination_iata']})"
            )
            lines.append(f"Dates: {plan['departure_date']} to {plan['return_date']} ({nights_lbl})")
            if plan["party_summary"]:
                lines.append(f"Travelers: {plan['party_summary']}")
            if plan["merged_holidays_text"]:
                lines.append(f"Holidays: {plan['merged_holidays_text']}")
            if plan["bonus_summary"]:
                lines.append(f"EL AL Award: {plan['bonus_summary']}")
            if plan["min_points_text"]:
                lines.append(f"Matmid Points: {plan['min_points_text']}")
            if plan["outbound_flight"]:
                lines.append(f"Outbound: {plan['outbound_flight']}")
            if plan["return_flight"]:
                lines.append(f"Return: {plan['return_flight']}")
            if plan["workdays_summary"]:
                lines.append(f"Workdays Off: {plan['workdays_summary']}")
            if plan["school_fit_summary"]:
                lines.append(f"School Fit: {plan['school_fit_summary']}")
            if plan["climate_summary"]:
                lines.append(f"Climate: {plan['climate_summary']}")
            lines.append("")
            lines.append("EL AL Booking Guide (before you click):")
            lines.append("1. Open Google Flights, pick the EL AL flights listed above, and continue to elal.com.")
            lines.append("2. Sign in to your Matmid account on elal.com first — award seats only appear after login.")
            lines.append("3. Searching for 3+ passengers? Check 1 passenger first and scale up, as only 1–2 award seats may be open.")
            if plan["booking_url"]:
                lines.append("")
                lines.append(f"Check & book (Google Flights / EL AL): {plan['booking_url']}")
            if plan["single_adult_booking_url"] and plan["single_adult_booking_url"] != plan["booking_url"]:
                lines.append(f"Quick 1-adult availability check: {plan['single_adult_booking_url']}")
            lines.append(f"Planned with breezyflights: {plan['app_url']}")

        plain_body = "\n".join(lines)

        # HTML version (email-safe inline styles, RTL for Hebrew, LTR for English)
        dir_attr = "rtl" if is_he else "ltr"
        align = "right" if is_he else "left"
        esc = html.escape

        detail_rows: list[tuple[str, str]] = []
        if plan["party_summary"]:
            detail_rows.append(("הרכב נוסעים" if is_he else "Travelers", plan["party_summary"]))
        if plan["merged_holidays_text"]:
            detail_rows.append(("חגים בחלון" if is_he else "Holidays", plan["merged_holidays_text"]))
        if plan["bonus_summary"]:
            detail_rows.append(("זמינות בונוס" if is_he else "EL AL Bonus", plan["bonus_summary"]))
        if plan["min_points_text"]:
            detail_rows.append(("נקודות מתמיד" if is_he else "Matmid Points", plan["min_points_text"]))
        if plan["outbound_flight"]:
            detail_rows.append(("טיסת הלוך" if is_he else "Outbound Flight", plan["outbound_flight"]))
        if plan["return_flight"]:
            detail_rows.append(("טיסת חזור" if is_he else "Return Flight", plan["return_flight"]))
        if plan["workdays_summary"]:
            detail_rows.append(("חופשת עבודה" if is_he else "Workdays Off", plan["workdays_summary"]))
        if plan["school_fit_summary"]:
            detail_rows.append(("התאמה לבי\"ס" if is_he else "School Fit", plan["school_fit_summary"]))
        if plan["climate_summary"]:
            detail_rows.append(("אקלים צפוי" if is_he else "Climate", plan["climate_summary"]))

        rows_html = "".join(
            f'<tr>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;color:#475569;font-weight:700;width:36%;text-align:{align};vertical-align:top;">{esc(lbl)}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;color:#0F172A;text-align:{align};vertical-align:top;">{esc(val)}</td>'
            f"</tr>"
            for lbl, val in detail_rows
        )

        note_html = ""
        if note:
            note_title = "הערה אישית" if is_he else "Personal note"
            note_html = (
                f'<div style="margin:0 0 16px 0;padding:12px 14px;background:#FFFBEB;border:1px solid #FDE68A;'
                f'border-radius:10px;color:#78350F;font-size:14px;line-height:1.5;text-align:{align};">'
                f"<strong>{esc(note_title)}:</strong> {esc(note).replace(chr(10), '<br/>')}</div>"
            )

        border_accent_side = "border-right" if is_he else "border-left"
        if is_he:
            guide_title = "ℹ️ מדריך הזמנה באל על — לפני שממשיכים"
            guide_steps = [
                ("1. עוברים ל-Google Flights:", "בוחרים את טיסות אל על המוצגות מעלה וממשיכים משם לאתר אל על (elal.com)."),
                ("2. מתחברים קודם לחשבון המתמיד:", "באתר אל על יש לבצע התחברות (Login) ורק לאחר מכן רואים את זמינות כרטיסי הבונוס."),
                ("3. טיפ חשוב למעל 2 נוסעים:", "אם בוחרים יותר מ-2 נוסעים ולא רואים בונוס, כדאי לבדוק קודם לנוסע 1 ולהעלות בהדרגה — כי ייתכן שיש רק 1–2 מושבי בונוס פנויים."),
            ]
        else:
            guide_title = "ℹ️ EL AL Booking Guide — Before You Book"
            guide_steps = [
                ("1. Start on Google Flights:", "Select the EL AL flights listed above and click through to elal.com."),
                ("2. Sign in to Matmid on elal.com:", "You must log in to your Matmid account first before award seat availability appears."),
                ("3. Tip for 3+ passengers:", "If no bonus seats show for a larger group, check 1 passenger first and scale up — only 1–2 award seats may be open."),
            ]

        guide_items_html = "".join(
            f'<div style="margin:0 0 6px 0;font-size:13px;line-height:1.5;color:#1E293B;text-align:{align};">'
            f'<strong style="color:#0B3B8C;">{esc(step_head)}</strong> {esc(step_body)}</div>'
            for step_head, step_body in guide_steps
        )
        booking_guide_html = (
            f'<div style="margin:18px 0 14px 0;padding:13px 15px;background:#EFF6FF;border:1px solid #BFDBFE;'
            f'{border_accent_side}:4px solid #0B3B8C;border-radius:10px;text-align:{align};">'
            f'<div style="margin:0 0 8px 0;font-size:14px;font-weight:800;color:#0B3B8C;text-align:{align};">{esc(guide_title)}</div>'
            f"{guide_items_html}"
            f"</div>"
        )

        cta_html = ""
        if plan["booking_url"]:
            cta_text = "✈️ בדיקת זמינות והזמנת טיסת אל על" if is_he else "✈️ Check availability & book EL AL flight"
            single_link_html = ""
            if plan["single_adult_booking_url"] and plan["single_adult_booking_url"] != plan["booking_url"]:
                single_text = (
                    "🔍 בדיקה מהירה לנוסע 1 בלבד (לזיהוי מדויק של מושבי בונוס)"
                    if is_he
                    else "🔍 Quick 1-adult availability check (to count exact bonus seats)"
                )
                single_link_html = (
                    f'<div style="margin-top:10px;">'
                    f'<a href="{esc(plan["single_adult_booking_url"])}" '
                    f'style="color:#0B3B8C;font-size:13px;font-weight:700;text-decoration:underline;">{esc(single_text)}</a>'
                    f"</div>"
                )
            cta_html = (
                f'<div style="margin:14px 0 8px 0;text-align:center;">'
                f'<a href="{esc(plan["booking_url"])}" '
                f'style="display:inline-block;padding:12px 22px;background:#0B3B8C;color:#FFFFFF;'
                f'text-decoration:none;border-radius:10px;font-weight:700;font-size:15px;">{esc(cta_text)}</a>'
                f"{single_link_html}"
                f"</div>"
            )

        shared_by_line = (
            f"תוכנית חופשה משותפת מאת {esc(s_name)} ({esc(sender_email)})"
            if is_he
            else f"Vacation plan shared by {esc(s_name)} ({esc(sender_email)})"
        )
        footer_note = (
            f'נשלח דרך <a href="{esc(plan["app_url"])}" style="color:#0E7490;text-decoration:none;font-weight:700;">breezyflights</a> · אפליקציית תכנון חופשות עצמאית שאינה שייכת לאל על.'
            if is_he
            else f'Sent via <a href="{esc(plan["app_url"])}" style="color:#0E7490;text-decoration:none;font-weight:700;">breezyflights</a> · Independent vacation planner not affiliated with EL AL.'
        )

        html_body = f"""<!DOCTYPE html>
<html lang="{'he' if is_he else 'en'}" dir="{dir_attr}">
<head><meta charset="utf-8" /></head>
<body style="margin:0;padding:16px;background:#F1F5F9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;direction:{dir_attr};text-align:{align};">
  <div style="max-width:600px;margin:0 auto;background:#FFFFFF;border-radius:14px;overflow:hidden;border:1px solid #CBD5E1;">
    <div style="background:#0B1F3A;padding:18px 22px;color:#FFFFFF;text-align:{align};">
      <div style="font-size:13px;color:#FBBF24;font-weight:700;letter-spacing:0.03em;">breezyflights</div>
      <div style="font-size:20px;font-weight:800;margin-top:4px;">{esc(plan['destination_name'])} · <span dir="ltr">{esc(plan['origin_iata'])} ⇄ {esc(plan['destination_iata'])}</span></div>
      <div style="font-size:14px;color:#CBD5E1;margin-top:4px;"><span dir="ltr">{esc(plan['departure_date'])} → {esc(plan['return_date'])}</span> · {esc(nights_lbl)}</div>
    </div>
    <div style="padding:18px 22px;">
      <p style="margin:0 0 14px 0;font-size:13px;color:#475569;text-align:{align};">{shared_by_line}</p>
      {note_html}
      <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;font-size:14px;border:1px solid #E2E8F0;border-radius:10px;">
        <tbody>{rows_html}</tbody>
      </table>
      {booking_guide_html}
      {cta_html}
    </div>
    <div style="background:#F8FAFC;padding:12px 22px;border-top:1px solid #E2E8F0;font-size:12px;color:#64748B;text-align:{align};">
      {footer_note}
    </div>
  </div>
</body>
</html>"""

        gmail_qs = urllib.parse.urlencode({"view": "cm", "fs": "1", "su": subject, "body": plain_body})
        gmail_compose_url = f"https://mail.google.com/mail/?{gmail_qs}"
        return subject, plain_body, html_body, gmail_compose_url

    def _send_via_smtp(self, msg: EmailMessage, cfg: dict[str, Any]) -> None:
        if self.smtp_transport_override is not None:
            self.smtp_transport_override(msg, cfg)
            return
        host = cfg["host"]
        port = int(cfg["port"])
        timeout = float(self.smtp_timeout_seconds)
        ctx = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ctx) as server:
                if cfg["username"] and cfg["password"]:
                    server.login(cfg["username"], cfg["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as server:
                server.ehlo()
                if cfg["use_tls"]:
                    server.starttls(context=ctx)
                    server.ehlo()
                if cfg["username"] and cfg["password"]:
                    server.login(cfg["username"], cfg["password"])
                server.send_message(msg)

    def send_vacation_plan_email(
        self,
        *,
        session: dict[str, Any],
        body: dict[str, Any],
        request_headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Validate, format, rate-limit, and dispatch an authenticated shared vacation plan email."""
        user = session.get("user") or {}
        user_id = str(session.get("user_id") or user.get("id") or "")
        sender_email = str(user.get("email") or "").strip().lower()
        sender_name = str(user.get("display_name") or "").strip() or sender_email.split("@", 1)[0]
        if not user_id or not sender_email:
            raise ShareEmailError(401, "Authenticated Google session required.", error_code="unauthorized")

        raw_recipients = body.get("recipients")
        if raw_recipients is None and "recipient_email" in body:
            raw_recipients = body.get("recipient_email")
        recipients = self.parse_and_validate_recipients(raw_recipients, default_email=sender_email)
        locale = "en" if str(body.get("locale") or "he").strip().lower() == "en" else "he"
        personal_note = _clean_multiline(body.get("personal_note"), 300)
        plan = self.sanitize_plan(body.get("plan"))

        subject, plain_body, html_body, gmail_compose_url = self.compose_email_content(
            plan=plan,
            sender_name=sender_name,
            sender_email=sender_email,
            locale=locale,
            personal_note=personal_note,
        )

        if not self.is_configured(request_headers):
            raise ShareEmailError(
                503,
                "Server SMTP email delivery is not configured yet. Configure SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD or use Gmail Compose.",
                error_code="email_not_configured",
                extra={"fallback_gmail_compose_url": gmail_compose_url},
            )

        self._check_and_record_rate_limit(user_id)

        cfg = self.get_smtp_config()
        from_email = cfg["from_email"] or sender_email
        from_name = cfg["from_name"] or "breezyflights"

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr((from_name, from_email))
        msg["To"] = ", ".join(recipients)
        msg["Reply-To"] = formataddr((sender_name, sender_email))
        msg.set_content(plain_body, subtype="plain", charset="utf-8")
        msg.add_alternative(html_body, subtype="html", charset="utf-8")

        if self.smtp_transport_override is None and self.is_test_mode_allowed(request_headers):
            with self._lock:
                self._test_outbox.append(
                    {
                        "user_id": user_id,
                        "sender_email": sender_email,
                        "recipients": list(recipients),
                        "subject": subject,
                        "plain_body": plain_body,
                        "html_body": html_body,
                        "reply_to": msg["Reply-To"],
                        "locale": locale,
                    }
                )
            delivery_mode = "test_outbox"
        else:
            try:
                self._send_via_smtp(msg, cfg)
            except smtplib.SMTPAuthenticationError as exc:
                raise ShareEmailError(
                    502,
                    "SMTP authentication failed on the server.",
                    error_code="smtp_auth_failed",
                    extra={"fallback_gmail_compose_url": gmail_compose_url},
                ) from exc
            except (smtplib.SMTPException, OSError) as exc:
                raise ShareEmailError(
                    502,
                    f"SMTP email delivery failed: {type(exc).__name__}",
                    error_code="smtp_delivery_failed",
                    extra={"fallback_gmail_compose_url": gmail_compose_url},
                ) from exc
            delivery_mode = "smtp"

        return {
            "status": "sent",
            "delivery_mode": delivery_mode,
            "recipients": recipients,
            "subject": subject,
            "reply_to": sender_email,
        }
