"""Application Entrypoint, HTTP Server & In-Process TestClient (`F29`, `F31`, `F32`).

Provides:
1. `VacationPlannerTestClient`: In-process HTTP-like client supporting `.get()`,
   `.post()`, and `.put()` for fast hermetic E2E testing without external
   dependencies.
2. `create_http_server(host, port, db_path)`: Multi-threaded HTTP server
   (`ThreadingHTTPServer`) serving both `/api/v1/*` REST endpoints and static
   PWA/Web UI assets from `frontend/` with strict path-traversal protection.
3. CLI entrypoint: `python3 -m backend.app.main --host 0.0.0.0 --port 8000`
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
from typing import Any, Optional
import urllib.parse

from backend.app.api.v1.endpoints import VacationPlannerAPIRouter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = (PROJECT_ROOT / "frontend").resolve()


_MIME_OVERRIDES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".ics": "text/calendar; charset=utf-8",
    ".ts": "text/plain; charset=utf-8",
    ".tsx": "text/plain; charset=utf-8",
}


def serve_static_asset(raw_path: str) -> tuple[int, dict[str, str], str | bytes]:
    """Resolve and return a static frontend asset with strict path-traversal rejection."""
    parsed = urllib.parse.urlsplit(raw_path)
    unquoted = urllib.parse.unquote(parsed.path)

    # Reject any raw or URL-decoded path traversal tokens immediately
    if ".." in parsed.path or ".." in unquoted or "\x00" in unquoted:
        return (
            403,
            {"Content-Type": "application/json; charset=utf-8"},
            json.dumps({"error": "Path traversal forbidden"}),
        )

    clean_path = unquoted.strip("/")
    if clean_path in ("", "index.html"):
        candidate = FRONTEND_DIR / "index.html"
    elif clean_path == "manifest.webmanifest":
        candidate = FRONTEND_DIR / "public" / "manifest.webmanifest"
    elif clean_path == "sw.js":
        candidate = FRONTEND_DIR / "public" / "sw.js"
    else:
        candidate = FRONTEND_DIR / clean_path
        if not candidate.exists():
            alt = FRONTEND_DIR / "public" / clean_path
            if alt.exists():
                candidate = alt

    try:
        resolved = candidate.resolve()
        resolved.relative_to(FRONTEND_DIR)
    except Exception:
        return (
            403,
            {"Content-Type": "application/json; charset=utf-8"},
            json.dumps({"error": "Forbidden path outside frontend directory"}),
        )

    if not resolved.exists() or not resolved.is_file():
        return (
            404,
            {"Content-Type": "application/json; charset=utf-8"},
            json.dumps({"error": f"Static asset not found: /{clean_path}"}),
        )

    ext = resolved.suffix.lower()
    content_type = _MIME_OVERRIDES.get(ext) or (
        mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
    )
    headers = {
        "Content-Type": content_type,
        "Cache-Control": "no-cache",
    }
    raw_bytes = resolved.read_bytes()
    try:
        return 200, headers, raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return 200, headers, raw_bytes


@dataclass
class TestResponse:
    """HTTP-like response object returned by `VacationPlannerTestClient`."""

    status_code: int
    headers: dict[str, str]
    text: str
    content: bytes

    def json(self) -> Any:
        return json.loads(self.text)


class VacationPlannerTestClient:
    """In-process test client for `/api/v1/*` and static frontend routes."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        resolved_db = db_path or os.environ.get("VACATION_PLANNER_DB_PATH")
        self.router = VacationPlannerAPIRouter(db_path=resolved_db)

    def request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> TestResponse:
        parsed = urllib.parse.urlsplit(path)
        if parsed.path.startswith("/api/"):
            q_params = (
                {str(k): str(v) for k, v in params.items()} if params else None
            )
            status, headers, body_text = self.router.dispatch(
                method=method,
                raw_path=path,
                query_params=q_params,
                json_body=json_body,
            )
            return TestResponse(
                status_code=status,
                headers=headers,
                text=body_text,
                content=body_text.encode("utf-8"),
            )

        status, headers, body = serve_static_asset(path)
        if isinstance(body, bytes):
            text_val = body.decode("utf-8", errors="replace")
            content_bytes = body
        else:
            text_val = body
            content_bytes = body.encode("utf-8")
        return TestResponse(
            status_code=status,
            headers=headers,
            text=text_val,
            content=content_bytes,
        )

    def get(
        self, path: str, params: Optional[dict[str, Any]] = None
    ) -> TestResponse:
        return self.request("GET", path, params=params)

    def post(
        self,
        path: str,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> TestResponse:
        return self.request("POST", path, params=params, json_body=json)

    def put(
        self,
        path: str,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> TestResponse:
        return self.request("PUT", path, params=params, json_body=json)


def create_http_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    db_path: Optional[str | Path] = None,
) -> ThreadingHTTPServer:
    """Create a configured `ThreadingHTTPServer` instance."""
    resolved_db = db_path or os.environ.get("VACATION_PLANNER_DB_PATH")
    router = VacationPlannerAPIRouter(db_path=resolved_db)

    class VacationPlannerRequestHandler(BaseHTTPRequestHandler):
        def _send_response(
            self, status: int, headers: dict[str, str], body: str | bytes
        ) -> None:
            payload_bytes = (
                body.encode("utf-8") if isinstance(body, str) else body
            )
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header(
                "Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS"
            )
            self.send_header(
                "Access-Control-Allow-Headers", "Content-Type, Authorization"
            )
            self.send_header("Content-Length", str(len(payload_bytes)))
            self.end_headers()
            self.wfile.write(payload_bytes)

        def _read_json_body(self) -> Optional[dict[str, Any]]:
            length_str = self.headers.get("Content-Length", "0")
            try:
                length = int(length_str)
            except ValueError:
                length = 0
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            if not raw.strip():
                return {}
            return json.loads(raw)

        def _normalized_headers(self) -> dict[str, str]:
            return {str(k).lower(): str(v) for k, v in self.headers.items()}

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._send_response(204, {}, b"")

        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/api/"):
                status, headers, body = router.dispatch(
                    "GET", self.path, request_headers=self._normalized_headers()
                )
            else:
                status, headers, body = serve_static_asset(self.path)
            self._send_response(status, headers, body)

        def do_POST(self) -> None:  # noqa: N802
            try:
                json_body = self._read_json_body()
            except Exception as exc:
                self._send_response(
                    400,
                    {"Content-Type": "application/json; charset=utf-8"},
                    json.dumps({"error": f"Invalid JSON body: {exc}"}),
                )
                return
            status, headers, body = router.dispatch(
                "POST",
                self.path,
                json_body=json_body,
                request_headers=self._normalized_headers(),
            )
            self._send_response(status, headers, body)

        def do_PUT(self) -> None:  # noqa: N802
            try:
                json_body = self._read_json_body()
            except Exception as exc:
                self._send_response(
                    400,
                    {"Content-Type": "application/json; charset=utf-8"},
                    json.dumps({"error": f"Invalid JSON body: {exc}"}),
                )
                return
            status, headers, body = router.dispatch(
                "PUT",
                self.path,
                json_body=json_body,
                request_headers=self._normalized_headers(),
            )
            self._send_response(status, headers, body)

        def log_message(self, format: str, *args: Any) -> None:
            # Keep server stdout/stderr clean during automated runs
            return

    return ThreadingHTTPServer((host, port), VacationPlannerRequestHandler)


def run_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    db_path: Optional[str | Path] = None,
) -> None:
    """Start the HTTP server and block until interrupted."""
    server = create_http_server(host=host, port=port, db_path=db_path)
    print(
        f"Family Vacation Planner server listening on http://{host}:{port}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: Optional[list[str]] = None) -> int:
    default_host = os.environ.get("HOST", "0.0.0.0")
    default_port = int(os.environ.get("PORT", "8000"))
    parser = argparse.ArgumentParser(
        description="Family Vacation Planner Web & API Server"
    )
    parser.add_argument("--host", default=default_host, help="Bind host address")
    parser.add_argument(
        "--port", type=int, default=default_port, help="Bind TCP port"
    )
    parser.add_argument(
        "--db-path", default=None, help="Optional SQLite database file path"
    )
    args = parser.parse_args(argv)
    run_server(host=args.host, port=args.port, db_path=args.db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
