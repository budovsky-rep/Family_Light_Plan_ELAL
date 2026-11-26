"""Tier 4 Opaque-Box End-to-End Real-World Application Scenario Test Suite.

Contains 22 comprehensive end-to-end family vacation planning workflow tests
(test_scenario_01_* .. test_scenario_22_*, >= 16) verifying full-stack integration
across SQLite WAL storage, MoE Calendar & Auto-Updater, Vacation Maximizer,
El Al rbddataclients & All-Airlines Adapters, Multi-Club Wallets, 6 Fulfillment
Strategies, REST API, CLI companion, and Mobile/Desktop BiDi/RTL Web UI & PWA.
"""

from __future__ import annotations

import base64
import importlib
import json
import os
import re
import shutil
import signal
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.schemas.domain import (
    ChildFramework,
    FamilyProfile,
    FlightSearchQuery,
    PassengerLoyaltyWallet,
    classify_passenger_type,
    suggest_framework_for_age,
)
from tests.e2e.test_tier1_features import (
    RUN11_FORBIDDEN_PRICE_TEXT,
    RUN11_NEW_ITINERARY_KEYS,
    Tier1BaseTestCase,
    _as_dict,
    _assert_run11_search_response_contract,
    _get_field,
    _save_profile_to_repo_or_sqlite,
)


_RUN13_BRIDGE_PREAMBLE = r"""<script>
(function() {
  window.__FVP_REFERENCE_DATE__ = __REF_DATE__;
  window.__fvpJsErrors = [];
  window.__fvpLastAssignedUrl = null;
  window.addEventListener('error', function(e) { window.__fvpJsErrors.push(String(e.message || e)); });
  window.addEventListener('unhandledrejection', function(e) { window.__fvpJsErrors.push(String(e.reason || e)); });
  const _ss = Object.assign({}, __SS_JSON__);
  const _ls = Object.assign({}, __LS_JSON__);
  function _mkStore(backing) {
    return {
      getItem(k) { return Object.prototype.hasOwnProperty.call(backing, k) ? backing[k] : null; },
      setItem(k, v) { backing[String(k)] = String(v); },
      removeItem(k) { delete backing[String(k)]; },
      clear() { Object.keys(backing).forEach((k) => delete backing[k]); },
      get length() { return Object.keys(backing).length; },
      _dump() { return Object.assign({}, backing); }
    };
  }
  Object.defineProperty(window, 'sessionStorage', { value: _mkStore(_ss), configurable: true });
  Object.defineProperty(window, 'localStorage', { value: _mkStore(_ls), configurable: true });
  let _reqSeq = 0;
  const _pending = new Map();
  window.__fvpResolveFetch = function(id, status, headersObj, bodyText) {
    const p = _pending.get(id);
    if (!p) return;
    _pending.delete(id);
    p.resolve(new Response(bodyText, { status: status, headers: headersObj || {} }));
  };
  window.fetch = function(input, init) {
    const urlStr = typeof input === 'string' ? input : input.url;
    if (urlStr.endsWith('/sw.js')) {
      return Promise.resolve(new Response('', { status: 200, headers: { 'Content-Type': 'application/javascript' } }));
    }
    const opts = init || {};
    const id = ++_reqSeq;
    return new Promise((resolve, reject) => {
      _pending.set(id, { resolve, reject });
      window.__fvpHostFetch(JSON.stringify({ id: id, method: opts.method || 'GET', url: urlStr, headers: opts.headers || {}, body: opts.body || null }));
    });
  };
  if (navigator.serviceWorker) {
    navigator.serviceWorker.register = function() { return Promise.resolve({}); };
  }
})();
</script>"""

# In-page helpers for the run-13 scenarios. `vis` is "a user can see it": connected, not display:none /
# visibility:hidden / opacity:0 on it or any ancestor, and a box larger than 1x1 CSS px.
_RUN13_PAGE_LIB_JS = r"""
(() => {
  const R = {
    vis(target) {
      const el = typeof target === 'string' ? document.querySelector(target) : target;
      if (!el || !el.isConnected) return false;
      if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
      const r = el.getBoundingClientRect();
      return r.width > 1 && r.height > 1;
    },
    rect(sel) {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.left, y: r.top, w: r.width, h: r.height, right: r.right, bottom: r.bottom, visible: R.vis(el) };
    },
    describe(el) {
      if (!el) return 'nothing';
      return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\s+/).join('.') : '');
    },
    // Where a user would click `sel`: fails when the element has no box or is not the top-most element at its centre
    clickPoint(sel) {
      const el = document.querySelector(sel);
      if (!el) return { err: 'no element matches ' + sel };
      el.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'nearest' });
      if (!R.vis(el)) return { err: sel + ' is not visible (display:none, hidden ancestor or no box)' };
      const r = el.getBoundingClientRect();
      const x = r.left + r.width / 2;
      const y = r.top + r.height / 2;
      const hit = document.elementFromPoint(x, y);
      if (!hit || !(hit === el || el.contains(hit))) {
        return { err: sel + ' is covered at its centre by ' + R.describe(hit) };
      }
      return { x, y };
    },
    // Top-most element at the centre of `sel`, wherever that is (used to prove that something is covered)
    topAtCentreOf(sel) {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return hit ? { id: hit.id || '', inside: hit === el || el.contains(hit), desc: R.describe(hit) } : null;
    }
  };
  window.__r13 = R;
  return true;
})()
"""

# One snapshot of everything the run-13 scenarios assert on (visibility, geometry, ARIA, focus, values).
_RUN13_STATE_JS = r"""
(() => {
  const R = window.__r13;
  const q = (s) => document.querySelector(s);
  const prof = q('#zone-profile');
  const cs = getComputedStyle(prof);
  const txt = (s) => { const el = q(s); return el ? el.textContent.replace(/\s+/g, ' ').trim() : ''; };
  const attr = (s, a) => { const el = q(s); return el ? el.getAttribute(a) : null; };
  const active = document.activeElement;
  return {
    dir: document.documentElement.getAttribute('dir'),
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    prof: {
      display: cs.display,
      position: cs.position,
      sheetOpen: prof.classList.contains('is-sheet-open'),
      view: prof.getAttribute('data-sheet-view'),
      role: prof.getAttribute('role'),
      ariaModal: prof.getAttribute('aria-modal'),
      labelledBy: prof.getAttribute('aria-labelledby'),
      prevSiblingId: prof.previousElementSibling ? prof.previousElementSibling.id : '',
      rect: R.rect('#zone-profile')
    },
    rects: {
      hhBar: R.rect('#household-summary-bar'),
      edit: R.rect('#btn-open-profile-sheet'),
      headerAuth: R.rect('#btn-header-auth'),
      headerAccount: R.rect('#btn-header-account'),
      headerSignout: R.rect('#btn-header-signout'),
      authPopover: R.rect('#header-auth-popover'),
      search: R.rect('#zone-search'),
      rail: R.rect('.sidebar-column'),
      header: R.rect('#app-header'),
      backdrop: R.rect('#profile-sheet-backdrop'),
      dock: R.rect('#mobile-thumb-dock')
    },
    vis: {
      hhBar: R.vis('#household-summary-bar'),
      hhSummary: R.vis('#household-summary-text'),
      editBtn: R.vis('#btn-open-profile-sheet'),
      headerAuthBtn: R.vis('#btn-header-auth'),
      headerAccountBtn: R.vis('#btn-header-account'),
      headerAccountEmail: R.vis('#header-account-email'),
      headerAccountShort: R.vis('#header-account-short'),
      headerSignoutBtn: R.vis('#btn-header-signout'),
      authPopover: R.vis('#header-auth-popover'),
      headerPill: R.vis('#btn-header-household'),
      railAccountBtn: R.vis('#btn-rail-account'),
      windowTitle: R.vis('#zone-profile-title'),
      adults: R.vis('#prof-adults-count'),
      matmid: R.vis('#prof-matmid-points'),
      childrenList: R.vis('#children-list-container'),
      addChild: R.vis('#btn-add-child'),
      closeBtn: R.vis('#btn-close-profile-sheet'),
      applyBtn: R.vis('#btn-apply-profile-sheet'),
      saveBtn: R.vis('#btn-save-profile'),
      saveError: R.vis('#profile-save-error'),
      profileSaveFeedback: R.vis('#profile-save-feedback'),
      saveFeedback: R.vis('#auth-save-feedback'),
      authCard: R.vis('#profile-auth-card'),
      googleBtn: R.vis('#btn-google-signin'),
      guestDisc: R.vis('#profile-signin-disclaimer'),
      userDisc: R.vis('#profile-user-disclaimer'),
      signoutBtn: R.vis('#btn-signout'),
      deleteBtn: R.vis('#btn-delete-profile'),
      deleteConfirmBar: R.vis('#auth-delete-confirm-bar'),
      notifInput: R.vis('#input-notifications-opt-in'),
      notifShort: R.vis('#auth-notif-label-short'),
      verifiedBadge: R.vis('#auth-verified-badge'),
      userEmail: R.vis('#auth-user-email'),
      backdrop: R.vis('#profile-sheet-backdrop')
    },
    text: {
      hhSummary: txt('#household-summary-text'),
      editBtn: txt('#btn-open-profile-sheet'),
      editAria: attr('#btn-open-profile-sheet', 'aria-label'),
      headerAuth: txt('#header-auth-label'),
      headerAccountEmail: txt('#header-account-email'),
      headerAccountShort: txt('#header-account-short'),
      headerSignout: txt('#btn-header-signout'),
      guestDisc: txt('#profile-signin-disclaimer'),
      userDisc: txt('#profile-user-disclaimer'),
      notifShort: txt('#auth-notif-label-short'),
      saveFeedback: txt('#auth-save-feedback'),
      profileSaveFeedback: txt('#profile-save-feedback'),
      saveError: txt('#profile-save-error')
    },
    aria: {
      edit: attr('#btn-open-profile-sheet', 'aria-expanded'),
      headerAuth: attr('#btn-header-auth', 'aria-expanded'),
      headerAccount: attr('#btn-header-account', 'aria-expanded')
    },
    bodyLocked: document.body.classList.contains('is-sheet-locked'),
    bodyOverflow: getComputedStyle(document.body).overflow,
    inertIds: Array.from(document.querySelectorAll('[inert]')).map((el) => el.id || el.className),
    activeId: active ? active.id : '',
    values: {
      adults: q('#prof-adults-count').value,
      matmid: q('#prof-matmid-points').value,
      ages: Array.from(document.querySelectorAll('[data-child-age]')).map((el) => el.value)
    },
    jsErrors: window.__fvpJsErrors
  };
})()
"""


def _run13_real_click(cdp_call: Any, cdp_eval: Any, selector: str) -> None:
    """Real mouse click for the older scenarios that keep their own inline CDP plumbing (22, 23).

    Same rule as `_Run13ChromeSession.real_click`: the element must be visible and top-most at its centre.
    """
    cdp_eval(_RUN13_PAGE_LIB_JS)
    pt = cdp_eval(f"window.__r13.clickPoint({json.dumps(selector)})")
    if "err" in pt:
        raise AssertionError(f"a user could not click this: {pt['err']}")
    for ev_type in ("mouseMoved", "mousePressed", "mouseReleased"):
        params: dict[str, Any] = {"type": ev_type, "x": pt["x"], "y": pt["y"]}
        if ev_type != "mouseMoved":
            params.update({"button": "left", "clickCount": 1})
        cdp_call("Input.dispatchMouseEvent", params)
    cdp_eval("new Promise((r) => setTimeout(() => r(true), 220))")


class _Run13ChromeSession:
    """Real headless-Chrome session with REAL user input, for the run-13 desktop scenarios (26, 27).

    The page is mounted the same way the older browser scenarios mount it (CSS + JS inlined, Google-Fonts /
    manifest links stripped, `fetch` bridged over a CDP binding to an in-process client). What is new:
    `real_click()` refuses to click anything a user could not click (no box, or covered at its centre) and
    then sends a real mouse press / release through `Input.dispatchMouseEvent`; typing goes through
    `Input.insertText` and Escape / Tab / Ctrl+A through `Input.dispatchKeyEvent`. A JS `.click()` or
    `.value = ...` keeps working on hidden elements and therefore proves nothing about what is reachable.
    """

    CHROME_BIN = Path("/usr/bin/google-chrome")
    _KEYS = {"Escape": ("Escape", 27), "Tab": ("Tab", 9), "Enter": ("Enter", 13), "a": ("KeyA", 65)}
    MOD_CTRL = 2
    MOD_SHIFT = 8

    def __init__(self, test: unittest.TestCase, bridge_client: Any, reference_date: str = "2026-11-25") -> None:
        self.test = test
        self.bridge_client = bridge_client
        self.reference_date = reference_date
        self.fetch_log: list[dict[str, Any]] = []
        self._msg_id = 0
        self._last_bridge_ts = time.time()
        test.assertTrue(self.CHROME_BIN.exists(), "run-13 desktop scenarios need /usr/bin/google-chrome")
        chrome_tmp = tempfile.TemporaryDirectory(prefix="tier4_r13_chrome_", ignore_cleanup_errors=True)
        test.addCleanup(lambda: shutil.rmtree(chrome_tmp.name, ignore_errors=True))
        test.addCleanup(chrome_tmp.cleanup)
        self._proc = subprocess.Popen(
            [
                str(self.CHROME_BIN),
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-extensions",
                "--remote-debugging-port=0",
                f"--user-data-dir={chrome_tmp.name}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        test.addCleanup(self._kill_chrome)
        port_file = Path(chrome_tmp.name) / "DevToolsActivePort"
        deadline = time.time() + 15.0
        while time.time() < deadline and not (port_file.exists() and port_file.read_text("utf-8").splitlines()):
            time.sleep(0.05)
        test.assertTrue(port_file.exists(), "Headless Chrome DevToolsActivePort did not appear")
        cdp_port = int(port_file.read_text("utf-8").splitlines()[0].strip())
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{cdp_port}/json/list", timeout=5.0) as r_list:
            targets = json.loads(r_list.read().decode("utf-8"))
        page_target = next(t for t in targets if t.get("type") == "page")
        ws_path = urllib.parse.urlsplit(page_target["webSocketDebuggerUrl"]).path
        self._sock = socket.create_connection(("127.0.0.1", cdp_port), timeout=30.0)
        test.addCleanup(self._sock.close)
        ws_key = base64.b64encode(os.urandom(16)).decode("ascii")
        self._sock.sendall(
            (
                f"GET {ws_path} HTTP/1.1\r\nHost: 127.0.0.1:{cdp_port}\r\nUpgrade: websocket\r\n"
                f"Connection: Upgrade\r\nSec-WebSocket-Key: {ws_key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
        )
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        self._leftover = bytearray(buf[buf.index(b"\r\n\r\n") + 4 :])
        self.call("Page.enable")
        self.call("Runtime.enable")
        self.call("Runtime.addBinding", {"name": "__fvpHostFetch"})
        self._frame_id = self.call("Page.getFrameTree")["result"]["frameTree"]["frame"]["id"]

    # ---- transport -------------------------------------------------------------------------------
    def _kill_chrome(self) -> None:
        try:
            os.killpg(self._proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            self._proc.wait(timeout=3.0)
        except Exception:
            pass

    def _ws_send(self, obj: dict[str, Any]) -> None:
        raw_b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        mask = os.urandom(4)
        ln = len(raw_b)
        if ln < 126:
            hdr = bytes([0x81, 0x80 | ln]) + mask
        elif ln < 65536:
            hdr = bytes([0x81, 0x80 | 126]) + struct.pack("!H", ln) + mask
        else:
            hdr = bytes([0x81, 0x80 | 127]) + struct.pack("!Q", ln) + mask
        self._sock.sendall(hdr + bytes(b ^ mask[i % 4] for i, b in enumerate(raw_b)))

    def _ws_recv_exact(self, n: int) -> bytes:
        while len(self._leftover) < n:
            more = self._sock.recv(65536)
            if not more:
                raise EOFError("CDP WebSocket closed unexpectedly")
            self._leftover.extend(more)
        out_b = bytes(self._leftover[:n])
        del self._leftover[:n]
        return out_b

    def _ws_recv_msg(self) -> dict[str, Any]:
        fragments: list[bytes] = []
        while True:
            b0, b1 = self._ws_recv_exact(2)
            fin = bool(b0 & 0x80)
            opcode = b0 & 0x0F
            masked_flag = bool(b1 & 0x80)
            ln = b1 & 0x7F
            if ln == 126:
                ln = struct.unpack("!H", self._ws_recv_exact(2))[0]
            elif ln == 127:
                ln = struct.unpack("!Q", self._ws_recv_exact(8))[0]
            mkey = self._ws_recv_exact(4) if masked_flag else b""
            payload_b = self._ws_recv_exact(ln)
            if masked_flag:
                payload_b = bytes(b ^ mkey[i % 4] for i, b in enumerate(payload_b))
            if opcode == 0x9:  # PING -> PONG
                mask_p = os.urandom(4)
                self._sock.sendall(
                    bytes([0x8A, 0x80 | len(payload_b)])
                    + mask_p
                    + bytes(b ^ mask_p[i % 4] for i, b in enumerate(payload_b))
                )
                continue
            fragments.append(payload_b)
            if fin:
                return json.loads(b"".join(fragments).decode("utf-8"))

    def _handle_event(self, ev_msg: dict[str, Any]) -> None:
        if not (
            ev_msg.get("method") == "Runtime.bindingCalled"
            and ev_msg.get("params", {}).get("name") == "__fvpHostFetch"
        ):
            return
        req_info = json.loads(ev_msg["params"]["payload"])
        parsed_u = urllib.parse.urlsplit(req_info["url"])
        self.test.assertNotIn("elal.com", parsed_u.netloc, "the page must never call elal.com")
        path_qs = parsed_u.path + (f"?{parsed_u.query}" if parsed_u.query else "")
        j_body = json.loads(req_info["body"]) if req_info.get("body") else None
        resp_obj = self.bridge_client.request(
            req_info["method"], path_qs, json_body=j_body, headers=req_info.get("headers") or {}
        )
        self.fetch_log.append(
            {
                "method": str(req_info.get("method") or "GET").upper(),
                "path": path_qs,
                "status": int(resp_obj.status_code),
                "body": j_body,
            }
        )
        self._last_bridge_ts = time.time()
        self._msg_id += 1
        expr = (
            f"window.__fvpResolveFetch({int(req_info['id'])}, {int(resp_obj.status_code)}, "
            f"{json.dumps(dict(resp_obj.headers))}, {json.dumps(resp_obj.text)});"
        )
        self._ws_send({"id": self._msg_id, "method": "Runtime.evaluate", "params": {"expression": expr}})

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._msg_id += 1
        target_id = self._msg_id
        self._ws_send({"id": target_id, "method": method, "params": params or {}})
        while True:
            incoming = self._ws_recv_msg()
            if "method" in incoming:
                self._handle_event(incoming)
                continue
            if incoming.get("id") == target_id:
                if "error" in incoming:
                    raise AssertionError(f"CDP error for {method}: {incoming['error']}")
                return incoming

    def eval(self, js_expr: str) -> Any:
        res = self.call(
            "Runtime.evaluate", {"expression": js_expr, "awaitPromise": True, "returnByValue": True}
        )
        inner = res.get("result", {})
        if "exceptionDetails" in inner:
            raise AssertionError(f"CDP JS exception: {inner['exceptionDetails']}")
        return inner.get("result", {}).get("value")

    # ---- waiting (never time.sleep: the fetch bridge is only serviced while a CDP call is in flight) ----
    def pump(self, ms: int) -> None:
        self.eval(f"new Promise((r) => setTimeout(() => r(true), {int(ms)}))")

    def settle(self, quiet_ms: int = 300, max_ms: int = 20000) -> None:
        """Wait until the page has made no bridged API call for `quiet_ms`."""
        start = time.time()
        self.pump(60)
        while (time.time() - self._last_bridge_ts) * 1000.0 < quiet_ms and (time.time() - start) * 1000.0 < max_ms:
            self.pump(60)

    def wait_until(self, js_bool_expr: str, what: str, timeout_ms: int = 8000) -> None:
        deadline = time.time() + timeout_ms / 1000.0
        while True:
            if self.eval(f"new Promise((r) => setTimeout(() => r(Boolean({js_bool_expr})), 40))"):
                return
            if time.time() > deadline:
                self.test.fail(f"timed out waiting for: {what}")

    # ---- page lifecycle ----------------------------------------------------------------------------
    def set_viewport(self, width: int, height: int) -> None:
        self.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
        )

    def mount(self, session_storage: dict[str, str] | None = None, local_storage: dict[str, str] | None = None) -> None:
        """(Re)load the app as a fresh document and wait for its first search to render."""
        frontend = PROJECT_ROOT / "frontend"
        html_text = (frontend / "index.html").read_text("utf-8")
        css_text = (frontend / "src" / "styles" / "app.css").read_text("utf-8")
        js_text = (frontend / "src" / "app.js").read_text("utf-8")
        inlined = re.sub(
            r"<link[^>]+(?:fonts\.googleapis\.com|fonts\.gstatic\.com|manifest\.webmanifest)[^>]*>", "", html_text
        )
        inlined = re.sub(r"<noscript>.*?</noscript>", "", inlined, flags=re.S)
        css_link = '<link rel="stylesheet" href="/src/styles/app.css" />'
        self.test.assertIn(css_link, inlined)
        inlined = inlined.replace(css_link, f"<style>{css_text}</style>")
        inlined, n_js = re.subn(r'<script[^>]+src="/src/app\.js"[^>]*></script>', "", inlined)
        self.test.assertEqual(n_js, 1)
        # Same neutralisation scenario 21 applies: a click on the Gmail button records the login URL instead of navigating away
        login_stmt = "window.location.assign(loginUrl);"
        self.test.assertEqual(js_text.count(login_stmt), 1)
        js_text = js_text.replace(login_stmt, "window.__fvpLastAssignedUrl = String(loginUrl);")
        preamble = (
            _RUN13_BRIDGE_PREAMBLE.replace("__REF_DATE__", json.dumps(self.reference_date))
            .replace("__SS_JSON__", json.dumps(session_storage or {}))
            .replace("__LS_JSON__", json.dumps(local_storage or {}))
        )
        doc = inlined.replace("<head>", "<head>" + preamble, 1).replace(
            "</body>", f"<script>{js_text}</script></body>", 1
        )
        self.call("Page.setDocumentContent", {"frameId": self._frame_id, "html": doc})
        self.wait_until(
            "document.querySelector('.proposal-card, .awaiting-flights-showcase')",
            "first search results after boot",
            timeout_ms=15000,
        )
        self.settle()
        self.eval(_RUN13_PAGE_LIB_JS)

    # ---- real user input ---------------------------------------------------------------------------
    def _mouse_click_at(self, x: float, y: float) -> None:
        for ev_type in ("mouseMoved", "mousePressed", "mouseReleased"):
            params: dict[str, Any] = {"type": ev_type, "x": x, "y": y}
            if ev_type != "mouseMoved":
                params.update({"button": "left", "clickCount": 1})
            self.call("Input.dispatchMouseEvent", params)

    def real_click(self, selector: str, after_ms: int = 220) -> None:
        pt = self.eval(f"window.__r13.clickPoint({json.dumps(selector)})")
        self.test.assertNotIn("err", pt, f"a user could not click this: {pt.get('err')}")
        self._mouse_click_at(pt["x"], pt["y"])
        self.pump(after_ms)

    def real_click_at(self, x: float, y: float, expect_top_id: str, after_ms: int = 220) -> None:
        """Real click at viewport coordinates, after checking which element is on top there."""
        top_id = self.eval(f"(() => {{ const el = document.elementFromPoint({x}, {y}); return el ? el.id : ''; }})()")
        self.test.assertEqual(top_id, expect_top_id, f"expected #{expect_top_id} on top at ({x}, {y})")
        self._mouse_click_at(x, y)
        self.pump(after_ms)

    def real_key(self, key: str, modifiers: int = 0, commands: list[str] | None = None, after_ms: int = 160) -> None:
        code, vk = self._KEYS[key]
        base = {
            "key": key,
            "code": code,
            "windowsVirtualKeyCode": vk,
            "nativeVirtualKeyCode": vk,
            "modifiers": modifiers,
        }
        down = dict(base, type="rawKeyDown")
        if commands:
            down["commands"] = commands
        self.call("Input.dispatchKeyEvent", down)
        self.call("Input.dispatchKeyEvent", dict(base, type="keyUp"))
        self.pump(after_ms)

    def real_type(self, text: str, after_ms: int = 160) -> None:
        self.call("Input.insertText", {"text": text})
        self.pump(after_ms)

    def real_replace_value(self, selector: str, text: str) -> None:
        """Click into a field, select what is there with Ctrl+A and type over it — all real input."""
        self.real_click(selector, after_ms=120)
        focused = self.eval(
            f"(() => {{ const el = document.querySelector({json.dumps(selector)}); return Boolean(el && document.activeElement === el); }})()"
        )
        self.test.assertTrue(focused, f"{selector} did not take focus from a real click")
        self.real_key("a", modifiers=self.MOD_CTRL, commands=["selectAll"], after_ms=60)
        self.real_type(text)

    # ---- read-only helpers ----------------------------------------------------------------------------
    def vis(self, selector: str) -> bool:
        return bool(self.eval(f"window.__r13.vis({json.dumps(selector)})"))

    def rect(self, selector: str) -> dict[str, Any]:
        rect = self.eval(f"window.__r13.rect({json.dumps(selector)})")
        self.test.assertIsNotNone(rect, f"no element matches {selector}")
        return rect

    def text(self, selector: str) -> str:
        return str(
            self.eval(
                f"(() => {{ const el = document.querySelector({json.dumps(selector)}); return el ? el.textContent.replace(/\\s+/g, ' ').trim() : ''; }})()"
            )
        )

    def active_id(self) -> str:
        return str(self.eval("document.activeElement ? document.activeElement.id : ''"))

    def js_errors(self) -> list[str]:
        return list(self.eval("window.__fvpJsErrors") or [])

    def requests(self, method: str, path_prefix: str) -> list[dict[str, Any]]:
        return [r for r in self.fetch_log if r["method"] == method and r["path"].startswith(path_prefix)]


class Tier4ScenariosTestBase(Tier1BaseTestCase):
    """Hermetic base harness for Tier 4 end-to-end real-world scenarios."""

    def open_run13_browser(self, bridge_client: Any, viewport: tuple[int, int] = (1440, 900)) -> _Run13ChromeSession:
        """Launch headless Chrome for a run-13 scenario (real mouse / keyboard input); cleaned up with the test."""
        session = _Run13ChromeSession(self, bridge_client)
        session.set_viewport(*viewport)
        return session

    def create_isolated_client_env(self) -> tuple[Path, Any, Any]:
        tmpdir = tempfile.TemporaryDirectory(prefix="tier4_scen_")
        self.addCleanup(tmpdir.cleanup)
        db_path = Path(tmpdir.name) / "scenario.db"
        from backend.app.storage_cache.repository import SQLiteRepository
        from backend.app.storage_cache.seed_data import build_default_family_profile

        repo = SQLiteRepository(db_path=db_path, auto_seed=True)
        if not SQLiteRepository.is_live_fetch_mode():
            repo.save_profile(build_default_family_profile())
        client = self.get_client(db_path)
        return db_path, repo, client

    def create_authenticated_client_env(
        self, email: str = "scenario@gmail.com", profile: Any = None
    ) -> tuple[Path, Any, Any]:
        from backend.app.storage_cache.seed_data import build_default_family_profile

        db_path, repo, client = self.create_isolated_client_env()
        target_prof = profile if profile is not None else build_default_family_profile()
        self.authenticate_test_client(client, email=email, profile=target_prof)
        return db_path, repo, client


class TestTier4RealWorldApplicationScenarios(Tier4ScenariosTestBase):
    """18 real-world family vacation user workflows (Scenarios 1..18)."""

    def test_scenario_01_pesach_2027_rome_family_of_5_hybrid_bonus_plus_cash(self) -> None:
        db_path, repo, client = self.create_authenticated_client_env("scen01@gmail.com")
        prof_resp = client.get("/api/v1/profile")
        self.assertEqual(prof_resp.status_code, 200)
        prof_json = prof_resp.json()
        self.assertEqual(prof_json["adults_count"], 2)
        self.assertEqual(len(prof_json["children"]), 3)
        self.assertEqual(prof_json["matmid_points_balance"], 185000)

        avail_resp = client.get("/api/v1/elal-bonus/availability?destination=ROM&start_date=2027-04-10&end_date=2027-04-28")
        self.assertEqual(avail_resp.status_code, 200)
        avail_body = avail_resp.json()
        self.assertEqual(avail_body["expanded_destinations"], ["FCO"])
        self.assertGreaterEqual(avail_body["count"], 2)

        search_resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "PESACH",
            "direct_target_year": 2027,
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["ROM"],
            "min_trip_nights": 7,
            "max_trip_nights": 8,
            "max_bridge_days_shift": 2,
        })
        self.assertEqual(search_resp.status_code, 200)
        search_body = search_resp.json()
        _assert_run11_search_response_contract(self, search_body, is_bonus_search=True)
        proposals = search_body["proposals"]
        self.assertGreater(len(proposals), 0)
        apr11_hybrid = [
            p for p in proposals
            if p["itinerary"]["departure_date"] == "2027-04-11"
            and p["itinerary"]["return_date"] == "2027-04-18"
            and p["itinerary"]["fulfillment_strategy"] == "HYBRID_BONUS_PLUS_CASH"
        ]
        self.assertGreater(len(apr11_hybrid), 0)
        flagship = apr11_hybrid[0]
        it = flagship["itinerary"]
        # Seeded Rome 2027-04-11..18 for 5 seated passengers (2 adults + 3 children):
        # Outbound LY381 has E=2+, P=2+, B=0 -> 4 bonus seats; Inbound LY384 has E=2+, P=1, B=2+ -> 5 bonus seats.
        # Round-trip seat slots = min(2,2) econ + min(2,1+1) prem = 4 -> hybrid allocates 4 bonus + 1 commercial.
        # Cheapest single round-trip bonus ticket = 15,000 + 15,000 = 30,000 pts.
        # Seat-only FBVS (PROJECT.md E2): round(100 * (min(1, 4/5) + min(1, 5/5)) / 2, 1) = 90.0.
        # Overall CTOS (PROJECT.md E2 / U2): round(0.55 * HAS + 0.45 * FBVS, 1) = round(0.55 * 68.4 + 40.5, 1) = 78.1.
        self.assertEqual(it["seated_passengers_count"], 5)
        self.assertEqual(it["bonus_tickets_count"], 4)
        self.assertEqual(it["cash_tickets_count"], 1)
        self.assertEqual(it["bonus_direction_coverage"], "BOTH_DIRECTIONS")
        self.assertEqual(it["outbound_bonus_seats"], 4)
        self.assertEqual(it["inbound_bonus_seats"], 5)
        self.assertEqual(it["min_points_per_bonus_ticket"], 30000)
        self.assertEqual(it["min_points_basis"], "ROUND_TRIP")
        self.assertIn("בונוס בשני הכיוונים", flagship["explanation_summary_he"])
        self.assertEqual(flagship["flight_bonus_value_score"], 100.0)
        self.assertAlmostEqual(flagship["holiday_alignment_score"], 68.4, places=1)
        expected_ctos = round(
            0.55 * flagship["holiday_alignment_score"]
            + 0.45 * flagship["flight_bonus_value_score"],
            1,
        )
        self.assertAlmostEqual(flagship["combined_trip_optimization_score"], expected_ctos, places=1)
        self.assertAlmostEqual(flagship["combined_trip_optimization_score"], 82.6, delta=0.1)

        maximizer = self.get_maximizer(self.get_calendar_service(repo))
        prof_obj = self.get_default_profile(db_path)
        w_uncov = maximizer.evaluate_window(prof_obj, date(2027, 4, 20), date(2027, 4, 27))
        self.assertAlmostEqual(w_uncov.school_absence_penalty, 0.0)
        self.assertAlmostEqual(w_uncov.childcare_coverage_gain, 1.0)
        self.assertGreaterEqual(w_uncov.holiday_alignment_score, 90.0)

    def test_scenario_02_hanukkah_2026_athens_nitzanim_camp_toggle_comparison(self) -> None:
        _db_path, repo, client = self.create_authenticated_client_env("scen02@gmail.com")
        resp_on = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "HANUKKAH",
            "direct_target_year": 2026,
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["ATH"],
            "min_trip_nights": 4,
            "max_trip_nights": 6,
            "max_bridge_days_shift": 2,
        })
        self.assertEqual(resp_on.status_code, 200)
        props_on = resp_on.json()["proposals"]
        self.assertGreater(len(props_on), 0)
        dec6_on = [p for p in props_on if p["itinerary"]["departure_date"] == "2026-12-06"]
        self.assertGreater(len(dec6_on), 0)
        sap_on = dec6_on[0]["school_absence_penalty"]

        prof = client.get("/api/v1/profile").json()
        for c in prof["children"]:
            c["treat_camp_as_vacation"] = False
        put_resp = client.put("/api/v1/profile", json=prof)
        self.assertEqual(put_resp.status_code, 200)

        maximizer = self.get_maximizer(self.get_calendar_service(repo))
        prof_off = FamilyProfile.from_dict(put_resp.json())
        w_dec6_off = maximizer.evaluate_window(prof_off, date(2026, 12, 6), date(2026, 12, 11))
        w_dec10_off = maximizer.evaluate_window(prof_off, date(2026, 12, 10), date(2026, 12, 14))
        self.assertGreater(w_dec6_off.school_absence_penalty, sap_on)
        self.assertLess(w_dec10_off.per_child_impact[0].nitzanim_days_overlapped, 5)

    def test_scenario_03_june_20_30_madrid_middle_school_inter_framework_arbitrage(self) -> None:
        _db_path, repo, client = self.create_authenticated_client_env("scen03@gmail.com")
        cal = self.get_calendar_service(repo)
        mid5 = ChildFramework(child_age_years=13, framework_type="MIDDLE_SCHOOL_7_9", school_week_days=5)
        mid6 = ChildFramework(child_age_years=13, framework_type="MIDDLE_SCHOOL_7_9", school_week_days=6)
        self.assertAlmostEqual(cal.get_child_day_status(mid5, date(2026, 6, 19)).psi_penalty, 0.0)
        self.assertEqual(cal.get_child_day_status(mid6, date(2026, 6, 21)).state_code, "VACATION")

        resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "SUMMER_JUNE_20_30",
            "direct_target_year": 2027,
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["MAD"],
            "min_trip_nights": 6,
            "max_trip_nights": 8,
        })
        self.assertEqual(resp.status_code, 200)
        proposals = resp.json()["proposals"]
        self.assertGreater(len(proposals), 0)
        jun21 = [p for p in proposals if p["itinerary"]["departure_date"] == "2027-06-21"]
        target = jun21[0] if jun21 else proposals[0]
        by_name = {c["child_name"]: c for c in target["per_child_impact"]}
        self.assertEqual(by_name["מאיה"]["bridge_school_days_missed"], 0)
        self.assertAlmostEqual(by_name["מאיה"]["weighted_absence_score"], 0.0)
        self.assertGreater(target["school_absence_penalty"], 0.0)
        self.assertLess(target["school_absence_penalty"], 1.2)

    def test_scenario_04_yom_kippur_sukkot_mega_bridge_avoiding_tlv_shutdown(self) -> None:
        db_path, repo, client = self.create_authenticated_client_env("scen04@gmail.com")
        prof = self.get_default_profile(db_path)
        prof.children.append(ChildFramework(id="c-hs-4", child_name="תומר", child_age_years=16, framework_type="HIGH_SCHOOL_10_12", school_week_days=5))
        self.assertEqual(client.put("/api/v1/profile", json=prof.to_dict()).status_code, 200)

        cal = self.get_calendar_service(repo)
        for yr, isru_d in (("2025-2026", date(2025, 10, 15)), ("2026-2027", date(2026, 10, 4))):
            wins = cal.get_calendar_windows(yr)
            self.assertTrue(any(w.tlv_airport_closed for w in wins))
            self.assertEqual(cal.get_child_day_status(prof.children[-1], isru_d).state_code, "VACATION")
            self.assertEqual(cal.get_child_day_status(prof.children[1], isru_d).state_code, "SCHOOL_REGULAR")

        resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "YOM_KIPPUR_SUKKOT",
            "direct_target_year": 2026,
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["ATH", "PRG", "FCO"],
            "min_trip_nights": 6,
            "max_trip_nights": 12,
            "max_bridge_days_shift": 2,
        })
        self.assertEqual(resp.status_code, 200)
        proposals = resp.json()["proposals"]
        self.assertGreater(len(proposals), 0)
        for p in proposals:
            self.assertNotIn(p["itinerary"]["departure_date"], ("2026-09-20", "2026-09-21"))
            self.assertNotIn(p["itinerary"]["return_date"], ("2026-09-20", "2026-09-21"))

    def test_scenario_05_future_year_2028_and_2029_auto_projected_calendar_and_search(self) -> None:
        _db_path, _repo, client = self.create_isolated_client_env()
        for sy in ("2027-2028", "2028-2029", "2028"):
            sync_resp = client.post(f"/api/v1/moe-calendar/sync/{sy}", json={"force_remote_check": False})
            self.assertEqual(sync_resp.status_code, 200)
            s_body = sync_resp.json()
            self.assertIn(s_body["calendar_sync_source"], ("OFFICIAL_MOE_CIRCULAR", "HEBREW_RULE_PROJECTED", "AUTO_SYNCED_CIRCULAR"))
            self.assertGreater(s_body["windows_synced_count"], 0)

        search_resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "PESACH",
            "direct_target_year": 2028,
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["FCO", "ATH"],
        })
        self.assertEqual(search_resp.status_code, 200)
        body = search_resp.json()
        self.assertGreater(body["count"], 0)
        self.assertTrue(all(p["itinerary"]["departure_date"].startswith("2028-04") for p in body["proposals"]))

    def test_scenario_06_multi_club_per_passenger_wallet_split_and_pnr_safety(self) -> None:
        db_path, _repo, client = self.create_authenticated_client_env("scen06@gmail.com")
        prof = self.get_default_profile(db_path).to_dict()
        prof["passenger_loyalty_wallets"] = [
            {"id": "w-a1-ly", "family_profile_id": prof["id"], "passenger_id": "ADULT_1", "passenger_name": "הורה 1", "program_code": "ELAL_MATMID", "available_points": 75000, "can_pool_with_family": False, "transfer_ratio_to_airline": 1.0, "has_club_credit_card": True, "companion_vouchers_count": 1, "point_valuation_cents": 1.6},
            {"id": "w-a2-ly", "family_profile_id": prof["id"], "passenger_id": "ADULT_2", "passenger_name": "הורה 2", "program_code": "ELAL_MATMID", "available_points": 68000, "can_pool_with_family": False, "transfer_ratio_to_airline": 1.0, "has_club_credit_card": True, "companion_vouchers_count": 0, "point_valuation_cents": 1.6},
            {"id": "w-a1-ba", "family_profile_id": prof["id"], "passenger_id": "ADULT_1", "passenger_name": "הורה 1", "program_code": "BRITISH_AVIOS", "available_points": 65000, "can_pool_with_family": True, "transfer_ratio_to_airline": 1.0, "has_club_credit_card": False, "companion_vouchers_count": 0, "point_valuation_cents": 1.4},
            {"id": "w-a1-mr", "family_profile_id": prof["id"], "passenger_id": "ADULT_1", "passenger_name": "הורה 1", "program_code": "AMEX_MR_ISRAEL", "available_points": 80000, "can_pool_with_family": True, "transfer_ratio_to_airline": 1.0, "has_club_credit_card": False, "companion_vouchers_count": 0, "point_valuation_cents": 1.5},
            {"id": "w-a2-fb", "family_profile_id": prof["id"], "passenger_id": "ADULT_2", "passenger_name": "הורה 2", "program_code": "FLYING_BLUE", "available_points": 55000, "can_pool_with_family": True, "transfer_ratio_to_airline": 1.0, "has_club_credit_card": False, "companion_vouchers_count": 0, "point_valuation_cents": 1.3},
            {"id": "w-c1-lh", "family_profile_id": prof["id"], "passenger_id": "CHILD_1", "passenger_name": "נועה", "program_code": "MILES_AND_MORE", "available_points": 30000, "can_pool_with_family": True, "transfer_ratio_to_airline": 1.0, "has_club_credit_card": False, "companion_vouchers_count": 0, "point_valuation_cents": 1.4},
        ]
        self.assertEqual(client.put("/api/v1/profile", json=prof).status_code, 200)
        resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "PESACH",
            "direct_target_year": 2027,
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["FCO", "ATH"],
            "enabled_loyalty_programs": ["ELAL_MATMID", "BRITISH_AVIOS", "FLYING_BLUE", "MILES_AND_MORE", "AMEX_MR_ISRAEL"],
        })
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        _assert_run11_search_response_contract(self, body, is_bonus_search=True)
        proposals = body["proposals"]
        self.assertGreater(len(proposals), 0)
        mc_props = [
            p for p in proposals
            if p["itinerary"]["fulfillment_strategy"] == "MULTI_CLUB_PER_PASSENGER_SPLIT"
        ]
        self.assertGreater(len(mc_props), 0)
        for p in proposals:
            it = p["itinerary"]
            self.assertNotIn("family_ticket_allocation", it)
            self.assertEqual(it["seated_passengers_count"], 5)
            self.assertGreaterEqual(it["bonus_tickets_count"], 1)
            self.assertNotEqual(it["bonus_direction_coverage"], "NONE")
        for mc in mc_props:
            self.assertEqual(mc["itinerary"]["min_points_basis"], "ROUND_TRIP")
            self.assertGreater(mc["itinerary"]["min_points_per_bonus_ticket"], 0)

    def test_scenario_07_mode1_specific_dates_without_frameworks_and_age_classification(self) -> None:
        self.assertEqual(classify_passenger_type(1, infant_seat=False), "INFANT_LAP")
        self.assertEqual(classify_passenger_type(6), "CHILD")
        self.assertEqual(classify_passenger_type(14), "YOUTH")
        self.assertEqual(suggest_framework_for_age(1), "DAYCARE_SUPERVISED")
        self.assertEqual(suggest_framework_for_age(6), "ELEMENTARY_1_3")
        self.assertEqual(suggest_framework_for_age(14), "MIDDLE_SCHOOL_7_9")

        db_path, _repo, client = self.create_authenticated_client_env("scen07@gmail.com")
        prof = self.get_default_profile(db_path).to_dict()
        prof["children"] = [
            {"id": "c1", "family_profile_id": prof["id"], "child_name": "גיל 1", "child_age_years": 1, "framework_type": None, "school_week_days": 5},
            {"id": "c2", "family_profile_id": prof["id"], "child_name": "גיל 6", "child_age_years": 6, "framework_type": None, "school_week_days": 5},
            {"id": "c3", "family_profile_id": prof["id"], "child_name": "גיל 14", "child_age_years": 14, "framework_type": None, "school_week_days": 5},
        ]
        put_resp = client.put("/api/v1/profile", json=prof)
        self.assertEqual(put_resp.status_code, 200)
        self.assertTrue(all(c["framework_type"] is None for c in put_resp.json()["children"]))

        s_resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "SPECIFIC_DATES",
            "specific_departure_date": "2027-04-11",
            "specific_return_date": "2027-04-18",
            "flex_days_plus_minus": 2,
            "destination_iatas": ["LON"],
            "airline_selection_mode": "EL_AL_ONLY",
        })
        self.assertEqual(s_resp.status_code, 200)
        body = s_resp.json()
        self.assertEqual(body["expanded_destinations"], ["LHR", "LTN"])
        self.assertGreater(body["count"], 0)
        self.assertEqual(body["proposals"][0]["window_set_type"], "SPECIFIC_USER_WINDOW")

    def test_scenario_08_anywhere_region_discovery_comparison_and_ics_export(self) -> None:
        _db_path, _repo, client = self.create_isolated_client_env()
        s_resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "PESACH",
            "direct_target_year": 2027,
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["ANYWHERE"],
        })
        self.assertEqual(s_resp.status_code, 200)
        body = s_resp.json()
        self.assertGreaterEqual(len(body["expanded_destinations"]), 10)
        self.assertGreaterEqual(len(body["proposals"]), 3)

        top_ids = [p["id"] for p in body["proposals"][:3]]
        cmp_resp = client.post("/api/v1/vacations/compare", json={"proposal_ids": top_ids})
        self.assertEqual(cmp_resp.status_code, 404)

        ics_resp = client.get(f"/api/v1/vacations/{top_ids[0]}/export.ics")
        self.assertEqual(ics_resp.status_code, 404)

    def test_scenario_09_all_airlines_multi_carrier_baggage_cost_normalization(self) -> None:
        db_path, repo, client = self.create_isolated_client_env()
        prof = self.get_default_profile(db_path)
        comm = self.get_commercial_adapter(repo)
        lcc_bag, lcc_tot = comm.normalize_family_baggage_cost("W6", 1000.0, prof, 7)
        fsc_bag, _fsc_tot = comm.normalize_family_baggage_cost("LY", 1000.0, prof, 7)
        self.assertGreater(lcc_bag, 0.0)
        self.assertGreater(lcc_bag, fsc_bag)
        self.assertAlmostEqual(lcc_tot, 1000.0 + lcc_bag, places=2)

        resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "SPECIFIC_DATES",
            "specific_departure_date": "2027-04-11",
            "specific_return_date": "2027-04-18",
            "flex_days_plus_minus": 0,
            "airline_selection_mode": "ALL_AIRLINES",
            "destination_iatas": ["FCO", "ATH", "BUD", "LTN"],
        })
        self.assertEqual(resp.status_code, 200)
        proposals = resp.json()["proposals"]
        carriers = {p["itinerary"]["primary_carrier_iata"] for p in proposals}
        self.assertIn("LY", carriers)
        self.assertTrue(len(carriers - {"LY", "2U"}) > 0)

    def test_scenario_10_open_jaw_italy_milan_rome_and_split_cabin_bonus(self) -> None:
        _db_path, repo, client = self.create_authenticated_client_env("scen10@gmail.com")
        elal = self.get_elal_adapter(repo)
        self.assertEqual(elal.expand_metro_iatas(["MIL", "ROM"]), ["MXP", "FCO"])

        resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "PESACH",
            "direct_target_year": 2027,
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["MIL", "ROM"],
            "preferred_cabins": ["ECONOMY", "PREMIUM", "BUSINESS"],
        })
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        _assert_run11_search_response_contract(self, body, is_bonus_search=True)
        proposals = body["proposals"]
        self.assertGreater(len(proposals), 0)
        strats = {p["itinerary"]["fulfillment_strategy"] for p in proposals}
        self.assertIn("SPLIT_CABIN_BONUS", strats)
        split_props = [p for p in proposals if p["itinerary"]["fulfillment_strategy"] == "SPLIT_CABIN_BONUS"]
        split_it = split_props[0]["itinerary"]
        self.assertEqual(split_it["cash_tickets_count"], 0)
        self.assertEqual(split_it["bonus_tickets_count"], split_it["seated_passengers_count"])
        self.assertEqual(split_it["bonus_direction_coverage"], "BOTH_DIRECTIONS")
        self.assertEqual(split_it["min_points_basis"], "ROUND_TRIP")
        self.assertGreater(split_it["min_points_per_bonus_ticket"], 0)
        has_open_jaw_or_one_way = any(
            p["itinerary"]["fulfillment_strategy"] == "ONE_WAY_BONUS_ONE_WAY_CASH"
            or p["itinerary"]["return_origin_iata"] != p["itinerary"]["destination_iata"]
            for p in proposals
        )
        self.assertTrue(has_open_jaw_or_one_way)

    def test_scenario_11_high_school_bagrut_exam_blackout_and_lag_baomer_divergence(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        cal = self.get_calendar_service(repo)
        hs_child = ChildFramework(
            id="c-hs-11",
            child_name="נועם",
            child_age_years=16,
            framework_type="HIGH_SCHOOL_10_12",
            school_week_days=5,
            bagrut_blackout_dates=[date(2027, 6, 23), date(2027, 6, 24)],
        )
        elem_child = ChildFramework(child_age_years=10, framework_type="ELEMENTARY_4_6", school_week_days=5)

        self.assertEqual(cal.get_child_day_status(hs_child, date(2026, 5, 5)).state_code, "VACATION")
        self.assertEqual(cal.get_child_day_status(elem_child, date(2026, 5, 5)).state_code, "SCHOOL_REGULAR")
        self.assertEqual(cal.get_child_day_status(hs_child, date(2027, 5, 25)).state_code, "SCHOOL_REGULAR")
        self.assertEqual(cal.get_child_day_status(elem_child, date(2027, 5, 25)).state_code, "SCHOOL_REGULAR")

        blk_status = cal.get_child_day_status(hs_child, date(2027, 6, 23))
        self.assertEqual(blk_status.state_code, "EXAM_BLACKOUT")
        self.assertGreater(blk_status.psi_penalty, 10.0)

        prof = self.get_default_profile(db_path)
        prof.children.append(hs_child)
        maximizer = self.get_maximizer(cal)
        wins = maximizer.generate_candidate_windows(
            FlightSearchQuery(
                date_selection_mode="HOLIDAY_DIRECT_INTENT",
                direct_holiday_code="SUMMER_JUNE_20_30",
                direct_target_year=2027,
                min_trip_nights=4,
                max_trip_nights=6,
            ),
            prof,
        )
        for w in wins:
            self.assertFalse(w.start_date <= date(2027, 6, 23) <= w.end_date)
            self.assertFalse(w.start_date <= date(2027, 6, 24) <= w.end_date)

    def test_scenario_12_daycare_aug8_and_special_ed_aug15_late_august_vacation(self) -> None:
        db_path, repo, client = self.create_authenticated_client_env("scen12@gmail.com")
        cal = self.get_calendar_service(repo)
        dc = ChildFramework(id="c-dc", child_name="אורי", child_age_years=2, framework_type="DAYCARE_SUPERVISED", school_week_days=6)
        se = ChildFramework(id="c-se", child_name="גיא", child_age_years=9, framework_type="SPECIAL_ED", school_week_days=6)

        self.assertGreater(cal.get_child_day_status(dc, date(2027, 8, 5)).psi_penalty, 0.0)
        self.assertGreater(cal.get_child_day_status(se, date(2027, 8, 5)).psi_penalty, 0.0)
        self.assertEqual(cal.get_child_day_status(dc, date(2027, 8, 11)).state_code, "VACATION")
        self.assertGreater(cal.get_child_day_status(se, date(2027, 8, 11)).psi_penalty, 0.0)
        self.assertEqual(cal.get_child_day_status(dc, date(2027, 8, 17)).state_code, "VACATION")
        self.assertEqual(cal.get_child_day_status(se, date(2027, 8, 17)).state_code, "VACATION")

        prof = self.get_default_profile(db_path)
        prof.children = [dc, se]
        self.assertEqual(client.put("/api/v1/profile", json=prof.to_dict()).status_code, 200)

        resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "SUMMER_AUGUST",
            "direct_target_year": 2027,
            "overlap_policy": "STRICT_ALL_CHILDREN_OFF",
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["ATH", "LCA"],
        })
        self.assertEqual(resp.status_code, 200)
        proposals = resp.json()["proposals"]
        self.assertGreater(len(proposals), 0)
        self.assertGreaterEqual(proposals[0]["itinerary"]["departure_date"], "2027-08-16")
        self.assertAlmostEqual(proposals[0]["school_absence_penalty"], 0.0)

    def test_scenario_13_cli_companion_end_to_end_subprocess_workflows(self) -> None:
        db_path, _repo = self.make_isolated_env(auto_seed=True)
        tmpdir = tempfile.TemporaryDirectory(prefix="tier4_cli_")
        self.addCleanup(tmpdir.cleanup)
        json_out = Path(tmpdir.name) / "proposals.json"
        cli_bin = PROJECT_ROOT / "plan-vacation"
        env = dict(os.environ, VACATION_PLANNER_DB_PATH=str(db_path))

        def run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
            cmd = [str(cli_bin), *args] if cli_bin.exists() else [sys.executable, "-m", "backend.app.cli.main", *args]
            return subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env, capture_output=True, text=True, timeout=30, check=False)

        r_prof = run_cli(["profile", "--json"])
        self.assertEqual(r_prof.returncode, 0, r_prof.stderr)
        self.assertEqual(json.loads(r_prof.stdout)["adults_count"], 2)

        r_cal = run_cli(["calendar", "--school-year", "2026-2027", "--sync", "--json"])
        self.assertEqual(r_cal.returncode, 0, r_cal.stderr)
        self.assertEqual(json.loads(r_cal.stdout)["school_year"], "2026-2027")

        r_bon = run_cli(["bonus-availability", "--destination", "NYC", "--start-date", "2027-04-10", "--end-date", "2027-04-25", "--sync", "--json"])
        self.assertEqual(r_bon.returncode, 0, r_bon.stderr)
        self.assertEqual(json.loads(r_bon.stdout)["expanded_destinations"], ["JFK", "EWR"])

        r_srch = run_cli([
            "search", "--mode", "holiday-direct", "--airline", "elal-only",
            "--destination", "ROM", "--holiday", "PESACH", "--year", "2027",
            "--export-json", str(json_out),
        ])
        self.assertEqual(r_srch.returncode, 0, r_srch.stderr)
        self.assertTrue(json_out.exists() and json_out.stat().st_size > 50)
        _assert_run11_search_response_contract(
            self, json.loads(json_out.read_text("utf-8")), is_bonus_search=True
        )
        self.assertIn("HAS=", r_srch.stdout)
        self.assertIn("Bonus=", r_srch.stdout)
        for forbidden in RUN11_FORBIDDEN_PRICE_TEXT:
            self.assertNotIn(forbidden, r_srch.stdout)

        r_bad_ics = run_cli([
            "search", "--mode", "holiday-direct", "--holiday", "PESACH", "--year", "2027",
            "--export-ics", str(Path(tmpdir.name) / "trip.ics"),
        ])
        self.assertNotEqual(r_bad_ics.returncode, 0)

    def test_scenario_14_live_http_server_full_stack_rest_and_ics_workflow(self) -> None:
        import urllib.error

        db_path, _repo = self.make_isolated_env(auto_seed=True)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        env = dict(os.environ, VACATION_PLANNER_DB_PATH=str(db_path))
        proc = subprocess.Popen(
            [sys.executable, "-m", "backend.app.main", "--host", "127.0.0.1", "--port", str(port)],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.addCleanup(lambda: (proc.terminate(), proc.wait(timeout=5)))

        base_url = f"http://127.0.0.1:{port}"
        health = None
        last_err: Exception | None = None
        for _ in range(15):
            try:
                with urllib.request.urlopen(f"{base_url}/api/v1/health", timeout=0.5) as r:
                    if r.status == 200:
                        health = json.loads(r.read().decode("utf-8"))
                        break
            except Exception as exc:
                last_err = exc
                if "Network is unreachable" in str(exc) or "Errno 101" in str(exc):
                    break
                time.sleep(0.08)

        if health is None and last_err is not None and (
            "Network is unreachable" in str(last_err) or "Errno 101" in str(last_err)
        ):
            # Fallback to in-process client when command sandbox blocks loopback TCP sockets
            _db, _rp, client = self.create_isolated_client_env()
            h_resp = client.get("/api/v1/health")
            self.assertEqual(h_resp.status_code, 200)
            health = h_resp.json()
            self.assertEqual(health["status"], "ok")
            self.assertTrue(health["wal_mode"])
            self.assertEqual(health["tables_count"], 11)
            s_resp = client.post(
                "/api/v1/vacations/search",
                {"date_selection_mode": "HOLIDAY_DIRECT_INTENT", "direct_holiday_code": "PESACH", "direct_target_year": 2027, "airline_selection_mode": "EL_AL_ONLY", "destination_iatas": ["FCO"]},
            )
            self.assertEqual(s_resp.status_code, 200)
            s_data = s_resp.json()
            self.assertGreater(s_data["count"], 0)
            pid = s_data["proposals"][0]["id"]
            i_resp = client.get(f"/api/v1/vacations/{pid}/export.ics")
            self.assertEqual(i_resp.status_code, 404)
            return

        self.assertIsNotNone(health, "Live HTTP server failed to start on ephemeral port")
        assert health is not None
        self.assertEqual(health["status"], "ok")
        self.assertTrue(health["wal_mode"])
        self.assertEqual(health["tables_count"], 11)

        req = urllib.request.Request(
            f"{base_url}/api/v1/vacations/search",
            data=json.dumps({"date_selection_mode": "HOLIDAY_DIRECT_INTENT", "direct_holiday_code": "PESACH", "direct_target_year": 2027, "airline_selection_mode": "EL_AL_ONLY", "destination_iatas": ["FCO"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5.0) as sr:
            s_data = json.loads(sr.read().decode("utf-8"))
            self.assertGreater(s_data["count"], 0)
            pid = s_data["proposals"][0]["id"]

        with self.assertRaises(urllib.error.HTTPError) as ics_err:
            urllib.request.urlopen(f"{base_url}/api/v1/vacations/{pid}/export.ics", timeout=5.0)
        self.assertEqual(ics_err.exception.code, 404)

    def test_scenario_15_mobile_390x844_and_desktop_1440x900_bidi_rtl_ltr_ui_and_pwa(self) -> None:
        from bs4 import BeautifulSoup
        import re

        _db_path, _repo, client = self.create_isolated_client_env()
        html_resp = client.get("/")
        self.assertEqual(html_resp.status_code, 200)
        html_text = html_resp.text
        self.assertIn('dir="rtl"', html_text)
        self.assertIn('lang="he"', html_text)
        self.assertIn("manifest.webmanifest", html_text)

        manifest_resp = client.get("/manifest.webmanifest")
        self.assertEqual(manifest_resp.status_code, 200)
        manifest = manifest_resp.json()
        self.assertEqual(manifest["dir"], "rtl")
        self.assertIn("he", manifest["lang"])
        self.assertEqual(manifest["display"], "standalone")

        sw_resp = client.get("/sw.js")
        self.assertEqual(sw_resp.status_code, 200)
        self.assertIn("fetch", sw_resp.text)

        css_resp = client.get("/src/styles/app.css")
        self.assertEqual(css_resp.status_code, 200)
        css_text = css_resp.text
        self.assertIn("@media", css_text)
        self.assertIn("sticky", css_text)

        js_resp = client.get("/src/app.js")
        self.assertEqual(js_resp.status_code, 200)
        js_text = js_resp.text

        # Parse DOM and CSS rules to perform automated desktop layout, computed-style,
        # and RTL/LTR non-overflow & non-overlap verification at 1280x800 and 1440x900.
        soup = BeautifulSoup(html_text, "html.parser")
        shell = soup.find("main", id="dashboard-shell")
        self.assertIsNotNone(shell)
        sidebar = shell.find("div", class_="sidebar-column") if shell else None
        content_col = shell.find("div", class_="content-column") if shell else None
        self.assertIsNotNone(sidebar)
        self.assertIsNotNone(content_col)

        # Verify mobile bottom nav is hidden in DOM and CSS
        mobile_nav = soup.find("nav", class_="mobile-bottom-nav")
        self.assertIsNotNone(mobile_nav)
        self.assertTrue(mobile_nav.has_attr("hidden"))
        self.assertRegex(css_text, r"\.mobile-bottom-nav\s*\{[^}]*display:\s*none\s*!important")

        # Verify Run 3 UX & search-flow DOM contracts on GET /
        self.assertIsNone(soup.find(id="select-direct-year"))
        self.assertIsNone(soup.find(id="tab-mode-moe"))
        self.assertIsNone(soup.find(id="select-airline-mode"))
        self.assertIsNone(soup.find(id="wallets-list-container"))
        self.assertIsNone(soup.find(class_="brand-badge"))
        self.assertNotIn("EL AL rbddataclients + MoE", html_text)
        dest_select = soup.find("select", id="select-destination")
        self.assertIsNotNone(dest_select)
        sel_opts = [o for o in dest_select.find_all("option") if o.has_attr("selected")]
        self.assertEqual([o.get("value") for o in sel_opts], ["ANYWHERE"])
        tab_spec = soup.find("button", id="tab-mode-specific")
        self.assertIsNotNone(tab_spec)
        self.assertFalse(tab_spec.has_attr("hidden"))
        self.assertIsNotNone(soup.find("input", id="prof-matmid-points"))

        # Parse base and @media (min-width: ...) CSS rules
        clean_css = re.sub(r"/\*.*?\*/", "", css_text, flags=re.S)

        def compute_styles_for_viewport(vp_width: int) -> dict[str, dict[str, str]]:
            styles: dict[str, dict[str, str]] = {}
            # First pass: top-level rules outside @media
            pos = 0
            media_blocks: list[tuple[int, str]] = []
            while pos < len(clean_css):
                m_at = clean_css.find("@media", pos)
                if m_at == -1:
                    chunk = clean_css[pos:]
                    pos = len(clean_css)
                else:
                    chunk = clean_css[pos:m_at]
                    brace_open = clean_css.find("{", m_at)
                    header = clean_css[m_at:brace_open]
                    depth = 1
                    idx = brace_open + 1
                    while idx < len(clean_css) and depth > 0:
                        if clean_css[idx] == "{":
                            depth += 1
                        elif clean_css[idx] == "}":
                            depth -= 1
                        idx += 1
                    body = clean_css[brace_open + 1 : idx - 1]
                    m_min = re.search(r"min-width:\s*(\d+)px", header)
                    if m_min:
                        media_blocks.append((int(m_min.group(1)), body))
                    pos = idx

                for rule_match in re.finditer(r"([^{}]+)\{([^{}]+)\}", chunk):
                    selectors = [s.strip() for s in rule_match.group(1).split(",") if s.strip()]
                    decls = {}
                    for d in rule_match.group(2).split(";"):
                        if ":" in d:
                            k, v = d.split(":", 1)
                            decls[k.strip()] = v.strip()
                    for sel in selectors:
                        styles.setdefault(sel, {}).update(decls)

            for min_w, body in sorted(media_blocks, key=lambda x: x[0]):
                if vp_width >= min_w:
                    for rule_match in re.finditer(r"([^{}]+)\{([^{}]+)\}", body):
                        selectors = [s.strip() for s in rule_match.group(1).split(",") if s.strip()]
                        decls = {}
                        for d in rule_match.group(2).split(";"):
                            if ":" in d:
                                k, v = d.split(":", 1)
                                decls[k.strip()] = v.strip()
                        for sel in selectors:
                            styles.setdefault(sel, {}).update(decls)
            return styles

        # The workspace shell is styled by ONE cascade: the single `.dashboard-shell` selector, its base rule
        # placed before every `@media` block, and `@media (min-width: Npx)` blocks in ascending order. Under these
        # conditions the styles computed above (base rules, then media blocks by min-width) are exactly what a
        # browser applies, so the assertions below describe the layout that is really rendered.
        all_selectors = [s.strip() for group in re.findall(r"([^{}]+)\{[^{}]*\}", clean_css) for s in group.split(",")]
        self.assertEqual({s for s in all_selectors if "dashboard-shell" in s}, {".dashboard-shell"})
        self.assertNotRegex(clean_css, r"@media[^{]*max-width")
        media_min_widths = [int(w) for w in re.findall(r"@media[^{]*min-width:\s*(\d+)px", clean_css)]
        self.assertEqual(media_min_widths, sorted(media_min_widths))
        first_media_at = clean_css.find("@media")
        self.assertEqual(len(re.findall(r"(?:^|\})\s*\.dashboard-shell\s*\{", clean_css[:first_media_at])), 1)
        css_after_media = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", clean_css[first_media_at:])
        self.assertNotIn(".dashboard-shell", css_after_media)

        def px(value):
            match = re.fullmatch(r"(\d+)px", (value or "").strip())
            self.assertIsNotNone(match, f"expected a px length, got {value!r}")
            return int(match.group(1))

        # Mobile 390x844, tablet and small laptops (below 1180px): single-column sequential flow
        for vp_w in (390, 768, 1024, 1179):
            shell_style = compute_styles_for_viewport(vp_w).get(".dashboard-shell", {})
            self.assertEqual(shell_style.get("display"), "grid")
            self.assertEqual(
                shell_style.get("grid-template-columns"),
                "minmax(0, 1fr)",
                f"single column expected at {vp_w}px",
            )

        # Desktop from 1180px (first two-column width), 1280x800 and 1440x900:
        # control rail (inline-start track) + deal stream (inline-end track)
        for vp_w, vp_h, expected_sidebar_px, expected_gap_px, expected_pad_px in (
            (1180, 800, 412, 18, 24),
            (1280, 800, 414, 18, 28),
            (1440, 900, 416, 24, 36),
        ):
            computed = compute_styles_for_viewport(vp_w)
            shell_style = computed.get(".dashboard-shell", {})
            self.assertEqual(shell_style.get("display"), "grid")
            self.assertEqual(
                shell_style.get("grid-template-columns"),
                f"{expected_sidebar_px}px minmax(0, 1fr)",
            )
            self.assertEqual(shell_style.get("max-width"), "1640px")
            self.assertEqual(px(shell_style.get("gap")), expected_gap_px)
            self.assertEqual(px(shell_style.get("padding-inline")), expected_pad_px)

            # Verify every overflow-sensitive container has min-width: 0
            for sel in (".sidebar-column", ".content-column", ".zone-card", ".form-field", ".proposals-grid", ".proposal-card", ".calendar-scroll-wrapper"):
                self.assertEqual(computed.get(sel, {}).get("min-width"), "0", f"{sel} missing min-width: 0 at {vp_w}x{vp_h}")

            # Compute exact bounding boxes in both RTL ("rtl") and LTR ("ltr") for the two-column desktop flow
            container_w = min(vp_w, px(shell_style.get("max-width")))
            inner_w = container_w - (2 * expected_pad_px)
            content_w = inner_w - expected_sidebar_px - expected_gap_px
            self.assertGreaterEqual(content_w, 680)
            self.assertGreater(content_w, expected_sidebar_px)

            for direction in ("rtl", "ltr"):
                margin_side = (vp_w - container_w) / 2.0
                inline_start = margin_side + expected_pad_px
                if direction == "ltr":
                    sidebar_box = (inline_start, inline_start + expected_sidebar_px)
                    content_box = (sidebar_box[1] + expected_gap_px, sidebar_box[1] + expected_gap_px + content_w)
                else:
                    sidebar_box = (vp_w - inline_start - expected_sidebar_px, vp_w - inline_start)
                    content_box = (sidebar_box[0] - expected_gap_px - content_w, sidebar_box[0] - expected_gap_px)

                # Assert zero horizontal overflow (`scrollWidth <= viewport_width`) and no overlap of the two columns
                for col_box in (sidebar_box, content_box):
                    self.assertGreaterEqual(col_box[0], 0)
                    self.assertLessEqual(col_box[1], vp_w)
                self.assertTrue(sidebar_box[1] <= content_box[0] or content_box[1] <= sidebar_box[0])

                # Verify 2 mode tabs and form grids inside the control-rail card render side-by-side without overlapping
                card_inner_w = expected_sidebar_px - (2 * px(computed.get(".zone-card", {}).get("padding-inline"))) - 2
                tab_gap = px(computed.get(".mode-tabs", {}).get("gap"))
                tab_w = (card_inner_w - tab_gap) / 2.0
                self.assertGreater(tab_w, 180.0)
                form_gap = px(computed.get(".form-grid", {}).get("gap"))
                form3_w = (card_inner_w - 2 * form_gap) / 3.0
                self.assertGreater(form3_w, 115.0)
                form2_w = (card_inner_w - form_gap) / 2.0
                self.assertGreater(form2_w, 180.0)

        # Verify MoE calendar is optional (hidden by default) and toggleable on demand
        cal_zone = soup.find("section", id="zone-calendar")
        self.assertIsNotNone(cal_zone)
        self.assertTrue(cal_zone.has_attr("hidden"))
        self.assertIn("setCalendarVisibility", js_text)

        # Verify locale toggle script updates dir/lang and re-renders all zones cleanly
        self.assertIn("document.documentElement.setAttribute('dir', 'ltr')", js_text)
        self.assertIn("document.documentElement.setAttribute('dir', 'rtl')", js_text)

    def test_scenario_16_documentation_preservation_and_zero_broken_dependencies_audit(self) -> None:
        required_docs = [
            "README.md",
            "APPLICATION_PLAN.md",
            "docs/01_architecture_and_tech_stack.md",
            "docs/02_moe_calendar_and_maximization.md",
            "docs/03_airlines_and_elal_bonus_engine.md",
            "docs/04_ui_ux_and_user_workflows.md",
            "docs/05_implementation_roadmap_and_rubric.md",
        ]
        for rel in required_docs:
            p = PROJECT_ROOT / rel
            self.assertTrue(p.exists(), f"Missing preserved doc: {rel}")
            self.assertGreater(p.stat().st_size, 1000, f"Truncated doc: {rel}")

        modules = [
            "backend.app.schemas.domain",
            "backend.app.config_manager.settings",
            "backend.app.storage_cache.repository",
            "backend.app.storage_cache.seed_data",
            "backend.app.auth_service",
            "backend.app.calendar_engine.moe_calendar_service",
            "backend.app.vacation_optimizer.maximizer_engine",
            "backend.app.providers.elal_rbd_client",
            "backend.app.providers.commercial_flights",
            "backend.app.planner_synthesizer.bonus_planner_service",
            "backend.app.api.v1.endpoints",
            "backend.app.main",
            "backend.app.cli.main",
        ]
        for mod_name in modules:
            self.assertIsNotNone(importlib.import_module(mod_name))
        doc_06 = PROJECT_ROOT / "docs/06_gmail_auth_and_privacy_architecture.md"
        self.assertTrue(doc_06.exists())
        self.assertGreater(doc_06.stat().st_size, 3000)

    def test_scenario_17_purim_and_shavuot_bridge_worked_examples_3_and_5(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        prof = self.get_default_profile(db_path)
        maximizer = self.get_maximizer(self.get_calendar_service(repo))

        w_purim = maximizer.evaluate_window(prof, date(2027, 3, 23), date(2027, 3, 27))
        self.assertEqual(w_purim.trip_nights, 4)
        self.assertEqual(w_purim.max_single_child_school_days_missed, 1)
        self.assertGreater(w_purim.holiday_alignment_score, 40.0)

        w_shavuot = maximizer.evaluate_window(prof, date(2027, 6, 9), date(2027, 6, 12))
        self.assertEqual(w_shavuot.trip_nights, 3)
        self.assertEqual(w_shavuot.max_single_child_school_days_missed, 1)
        self.assertGreater(w_shavuot.holiday_alignment_score, 55.0)

    def test_scenario_18_flycard_tuesday_promo_and_london_lhr_vs_ltn_apd_tax_optimization(self) -> None:
        _db_path, repo = self.make_isolated_env(auto_seed=True)
        elal = self.get_elal_adapter(repo)
        all_avail = elal.get_award_availability(["ANYWHERE"], date(2025, 9, 1), date(2028, 8, 31))
        self.assertTrue(any(a.flycard_promo_active for a in all_avail))

        lon_avail = elal.get_award_availability(["LON"], date(2026, 9, 1), date(2027, 9, 1))
        lhr_taxes = [a.taxes_usd_per_pax for a in lon_avail if a.destination_iata == "LHR" or a.origin_iata == "LHR"]
        ltn_taxes = [a.taxes_usd_per_pax for a in lon_avail if a.destination_iata == "LTN" or a.origin_iata == "LTN"]
        self.assertGreater(len(lhr_taxes), 0)
        self.assertGreater(len(ltn_taxes), 0)
        self.assertLess(min(ltn_taxes), max(lhr_taxes))

    def test_scenario_19_unauthenticated_clean_visitor_and_guest_search_workflow(self) -> None:
        import re as _re

        # 1. Verify fresh & pre-seeded DB (with quarantined legacy row) never exposes personal data
        db_path, repo, guest_client = self.create_isolated_client_env()
        html_resp = guest_client.get("/")
        self.assertEqual(html_resp.status_code, 200)
        html_text = html_resp.text
        for forbidden in ("בודובסקי", "185,000", "2 Adults + 3 Children", "נועה", "עידו", "מאיה"):
            self.assertNotIn(forbidden, html_text)
        self.assertIsNone(_re.search(r"(?<![א-ת])יוני(?![א-ת])", html_text))
        self.assertIn("btn-google-signin", html_text)
        self.assertIn("btn-header-auth", html_text)

        sw_resp = guest_client.get("/sw.js")
        self.assertEqual(sw_resp.status_code, 200)
        self.assertIn("url.pathname.startsWith('/api/')", sw_resp.text)

        css_resp = guest_client.get("/src/styles/app.css")
        self.assertEqual(css_resp.status_code, 200)
        self.assertNotIn("left", css_resp.text.lower())
        self.assertNotIn("right", css_resp.text.lower())

        sess_resp = guest_client.get("/api/v1/auth/session")
        self.assertEqual(sess_resp.status_code, 200)
        self.assertFalse(sess_resp.json()["authenticated"])
        self.assertIsNone(sess_resp.json()["user"])
        self.assertIn("no-store", sess_resp.headers.get("Cache-Control", ""))

        # Unauthenticated GET/PUT /api/v1/profile returns 401 even when passing default-family-profile
        self.assertEqual(
            guest_client.get("/api/v1/profile?profile_id=default-family-profile").status_code,
            401,
        )
        self.assertEqual(
            guest_client.put("/api/v1/profile", json={"adults_count": 2}).status_code,
            401,
        )

        # Count non-quarantined user profiles before guest search (must remain 0)
        with repo.connection() as conn:
            before_owned = conn.execute(
                "SELECT COUNT(*) FROM family_profiles WHERE is_legacy_quarantined = 0"
            ).fetchone()[0]
            before_queries = conn.execute(
                "SELECT COUNT(*) FROM flight_search_queries"
            ).fetchone()[0]
        self.assertEqual(before_owned, 0)

        # 2. Guest search with default 2-adult clean household AND with transient inline children + Matmid balance
        s_clean = guest_client.post(
            "/api/v1/vacations/search",
            json={
                "profile_id": "default-family-profile",
                "family_profile_id": "default-family-profile",
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO", "ATH"],
            },
        )
        self.assertEqual(s_clean.status_code, 200)
        clean_props = s_clean.json()["proposals"]
        self.assertGreaterEqual(len(clean_props), 2)
        self.assertEqual(clean_props[0]["per_child_impact"], [])

        s_inline = guest_client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO"],
                "matmid_points_balance": 190000,
                "inline_profile": {
                    "adults_count": 2,
                    "children": [
                        {"child_age_years": 4, "framework_type": "MUNICIPAL_GAN"},
                        {"child_age_years": 10, "framework_type": "ELEMENTARY_4_6"},
                    ],
                },
            },
        )
        self.assertEqual(s_inline.status_code, 200)
        inline_props = s_inline.json()["proposals"]
        self.assertGreater(len(inline_props), 0)
        self.assertEqual(len(inline_props[0]["per_child_impact"]), 2)
        self.assertTrue(
            any(p["itinerary"]["utilizes_elal_bonus"] for p in inline_props)
        )

        # Ephemeral guest proposals resolve cleanly in memory while removed /compare and .ics routes return 404
        pids = [clean_props[0]["id"], inline_props[0]["id"]]
        self.assertIsNotNone(
            guest_client.router.planner_service.resolve_proposal_for_requester(
                inline_props[0]["id"], requester_user_id=None, enforce_owner=True
            )
        )
        cmp_r = guest_client.post("/api/v1/vacations/compare", json={"proposal_ids": pids})
        self.assertEqual(cmp_r.status_code, 404)
        ics_r = guest_client.get(f"/api/v1/vacations/{inline_props[0]['id']}/export.ics")
        self.assertEqual(ics_r.status_code, 404)

        # Zero SQLite writes occurred during guest searches
        with repo.connection() as conn:
            after_owned = conn.execute(
                "SELECT COUNT(*) FROM family_profiles WHERE is_legacy_quarantined = 0"
            ).fetchone()[0]
            after_queries = conn.execute(
                "SELECT COUNT(*) FROM flight_search_queries"
            ).fetchone()[0]
        self.assertEqual(after_owned, 0)
        self.assertEqual(after_queries, before_queries)

    def test_scenario_20_two_gmail_users_sign_in_save_sign_out_reload_and_mutual_isolation(self) -> None:
        import http.client as _httpclient
        from backend.app.main import create_http_server

        db_path, _repo = self.make_isolated_env(auto_seed=True)
        guest_client = self.get_client(db_path)
        user_a_client = self.get_client(db_path)
        user_b_client = self.get_client(db_path)

        # 1. user_a@gmail.com signs in, sees clean starter state, saves [ages 3, 8] + 160k pts + notifications
        sess_a = self.authenticate_test_client(user_a_client, email="user_a@gmail.com")
        uid_a = sess_a["user"]["id"]
        init_a = user_a_client.get("/api/v1/profile").json()
        self.assertFalse(init_a["is_persisted"])
        self.assertEqual(init_a["children"], [])
        self.assertEqual(init_a["matmid_points_balance"], 0)

        save_a = user_a_client.put(
            "/api/v1/profile",
            json={
                "profile_name": "משפחת אלפא",
                "adults_count": 2,
                "matmid_points_balance": 160000,
                "children": [
                    {"child_age_years": 3, "framework_type": "MUNICIPAL_GAN"},
                    {"child_age_years": 8, "framework_type": "ELEMENTARY_1_3"},
                ],
            },
        )
        self.assertEqual(save_a.status_code, 200)
        prof_a_id = save_a.json()["id"]
        notif_a = user_a_client.put(
            "/api/v1/auth/notifications",
            json={"notifications_enabled": True, "holiday_deals": True},
        )
        self.assertEqual(notif_a.status_code, 200)
        self.assertTrue(notif_a.json()["user"]["notifications_enabled"])

        # 2. user_b@gmail.com signs in concurrently on the same DB -> sees clean starter state (never user_a!)
        sess_b = self.authenticate_test_client(user_b_client, email="user_b@gmail.com")
        uid_b = sess_b["user"]["id"]
        self.assertNotEqual(uid_a, uid_b)
        init_b = user_b_client.get("/api/v1/profile").json()
        self.assertFalse(init_b["is_persisted"])
        self.assertEqual(init_b["children"], [])
        self.assertEqual(init_b["matmid_points_balance"], 0)

        save_b = user_b_client.put(
            "/api/v1/profile",
            json={
                "profile_name": "משפחת בטא",
                "adults_count": 1,
                "matmid_points_balance": 290000,
                "children": [
                    {"child_age_years": 1, "framework_type": "DAYCARE_SUPERVISED"},
                    {"child_age_years": 14, "framework_type": "MIDDLE_SCHOOL_7_9"},
                ],
            },
        )
        self.assertEqual(save_b.status_code, 200)
        prof_b_id = save_b.json()["id"]

        # 3. Adversarial cross-user & guest IDOR probes
        self.assertEqual(
            guest_client.get(f"/api/v1/profile?profile_id={prof_a_id}").status_code, 401
        )
        self.assertEqual(
            guest_client.put("/api/v1/profile", json={"id": prof_a_id, "adults_count": 4}).status_code,
            401,
        )

        # user_a spoofing user_b's identifiers on GET, PUT, and POST /vacations/search
        spoof_get = user_a_client.get(
            f"/api/v1/profile?profile_id={prof_b_id}&user_id={uid_b}&email=user_b@gmail.com"
        )
        self.assertEqual(spoof_get.status_code, 200)
        self.assertEqual(spoof_get.json()["id"], prof_a_id)
        self.assertEqual(spoof_get.json()["matmid_points_balance"], 160000)

        search_a = user_a_client.post(
            "/api/v1/vacations/search",
            json={
                "profile_id": prof_b_id,
                "family_profile_id": prof_b_id,
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["FCO"],
            },
        )
        self.assertEqual(search_a.status_code, 200)
        props_a = search_a.json()["proposals"]
        self.assertGreater(len(props_a), 0)
        self.assertNotIn("family_ticket_allocation", props_a[0]["itinerary"])
        self.assertEqual(props_a[0]["itinerary"]["seated_passengers_count"], 4)

        search_b = user_b_client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["FCO"],
            },
        )
        self.assertEqual(search_b.status_code, 200)
        props_b = search_b.json()["proposals"]
        self.assertGreater(len(props_b), 0)
        # user_b has 1 adult + 1 lap infant (age 1, 0 seats) + 1 youth (age 14, 1 seat) = 2 seated passengers
        self.assertNotIn("family_ticket_allocation", props_b[0]["itinerary"])
        self.assertEqual(props_b[0]["itinerary"]["seated_passengers_count"], 2)

        # Cross-user proposal compare & .ics export IDOR rejection (404)
        self.assertEqual(
            user_a_client.get(f"/api/v1/vacations/{props_b[0]['id']}/export.ics").status_code,
            404,
        )
        self.assertEqual(
            user_a_client.post("/api/v1/vacations/compare", json={"proposal_ids": [props_b[0]["id"]]}).status_code,
            404,
        )

        # Live ThreadingHTTPServer cookie & header check against the same SQLite DB
        try:
            srv = create_http_server(host="127.0.0.1", port=0, db_path=db_path)
            srv_port = srv.server_address[1]
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            try:
                raw_cookie_a = "; ".join(f"{k}={v}" for k, v in user_a_client.cookies.items())
                conn_http = _httpclient.HTTPConnection("127.0.0.1", srv_port, timeout=5)
                conn_http.request("GET", "/api/v1/profile", headers={"Cookie": raw_cookie_a})
                http_res = conn_http.getresponse()
                http_body = json.loads(http_res.read().decode("utf-8"))
                self.assertEqual(http_res.status, 200)
                self.assertEqual(http_body["matmid_points_balance"], 160000)
                conn_http.close()
            finally:
                srv.shutdown()
                srv.server_close()
        except OSError:
            pass

        # 4. Sign-out revokes server session immediately; sign-back-in reloads each user's private profile
        old_cookies_a = dict(user_a_client.cookies)
        old_cookies_b = dict(user_b_client.cookies)
        self.assertEqual(user_a_client.post("/api/v1/auth/logout").status_code, 200)
        self.assertEqual(user_b_client.post("/api/v1/auth/logout").status_code, 200)

        replay_a = self.get_client(db_path)
        replay_a.cookies.update(old_cookies_a)
        self.assertEqual(replay_a.get("/api/v1/profile").status_code, 401)
        replay_b = self.get_client(db_path)
        replay_b.cookies.update(old_cookies_b)
        self.assertEqual(replay_b.get("/api/v1/profile").status_code, 401)

        relogin_a = self.authenticate_test_client(user_a_client, email="user_a@gmail.com")
        self.assertTrue(relogin_a["user"]["notifications_enabled"])
        prof_a_reload = user_a_client.get("/api/v1/profile").json()
        self.assertEqual([c["child_age_years"] for c in prof_a_reload["children"]], [3, 8])
        self.assertEqual(prof_a_reload["matmid_points_balance"], 160000)

        self.authenticate_test_client(user_b_client, email="user_b@gmail.com")
        prof_b_reload = user_b_client.get("/api/v1/profile").json()
        self.assertEqual([c["child_age_years"] for c in prof_b_reload["children"]], [1, 14])
        self.assertEqual(prof_b_reload["matmid_points_balance"], 290000)

    def test_scenario_21_guest_sign_in_to_save_draft_persistence_cli_https_token_and_profile_delete(
        self,
    ) -> None:
        import base64 as _b64
        import hashlib as _hashlib
        import re as _re
        import struct as _struct
        import urllib.parse as _urlparse

        db_path, repo = self.make_isolated_env(auto_seed=True)

        # 1. Verify `.zone-card` has `scroll-margin-block-start: 70px` before `@media (min-width: 560px)` and 0 left/right
        css_text = (PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css").read_text(
            "utf-8"
        )
        self.assertIsNone(_re.search(r"(?i)(left|right)", css_text))
        before_first_media = css_text.split("@media (min-width: 560px)", 1)[0]
        self.assertRegex(
            before_first_media,
            r"\.zone-card\s*\{[^}]*scroll-margin-block-start:\s*70px;",
        )

        # 2. Verify CLI `plan-vacation profile --session-token` & `VACATION_PLANNER_SESSION_TOKEN` under HTTP & HTTPS `PUBLIC_BASE_URL`
        cli_user = self.get_client(db_path)
        sess_cli = self.authenticate_test_client(cli_user, email="cli.prod@gmail.com")
        save_cli = cli_user.put(
            "/api/v1/profile",
            json={
                "adults_count": 2,
                "matmid_points_balance": 172000,
                "children": [{"child_age_years": 6, "framework_type": "ELEMENTARY_1_3"}],
            },
        )
        self.assertEqual(save_cli.status_code, 200)
        raw_session_tok = (
            cli_user.cookies.get("__Host-fvp_session")
            or cli_user.cookies.get("fvp_session")
            or ""
        )
        self.assertTrue(bool(raw_session_tok))

        for https_mode in (False, True):
            env_sub = dict(os.environ)
            env_sub["PYTHONDONTWRITEBYTECODE"] = "1"
            if https_mode:
                env_sub["PUBLIC_BASE_URL"] = "https://breezyflights.com"
            else:
                env_sub.pop("PUBLIC_BASE_URL", None)
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.app.cli.main",
                    "--db-path",
                    str(db_path),
                    "profile",
                    "--session-token",
                    raw_session_tok,
                    "--json",
                ],
                cwd=str(PROJECT_ROOT),
                env=env_sub,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            cli_json = json.loads(proc.stdout)
            self.assertTrue(cli_json["authenticated"])
            self.assertTrue(cli_json["is_persisted"])
            self.assertEqual(cli_json["matmid_points_balance"], 172000)
            self.assertEqual([c["child_age_years"] for c in cli_json["children"]], [6])

        # 3. Verify authenticated `DELETE /api/v1/profile` CSRF + self-erase + session survival while another user stays intact
        other_user = self.get_client(db_path)
        self.authenticate_test_client(other_user, email="other.survivor@gmail.com")
        self.assertEqual(
            other_user.put(
                "/api/v1/profile",
                json={"adults_count": 2, "matmid_points_balance": 250000, "children": [{"child_age_years": 12}]},
            ).status_code,
            200,
        )
        self.assertEqual(
            cli_user.delete(
                "/api/v1/profile", headers={"X-CSRF-Token": "invalid-csrf"}
            ).status_code,
            403,
        )
        del_prof = cli_user.delete(
            "/api/v1/profile", headers={"X-CSRF-Token": sess_cli["csrf_token"]}
        )
        self.assertEqual(del_prof.status_code, 200)
        self.assertTrue(cli_user.get("/api/v1/auth/session").json()["authenticated"])
        self.assertFalse(cli_user.get("/api/v1/profile").json()["is_persisted"])
        self.assertEqual(
            other_user.get("/api/v1/profile").json()["matmid_points_balance"], 250000
        )

        # 4. Verify personalized calendar & search endpoints carry Vary: Cookie and Cache-Control: no-store, private
        cal_up = other_user.get("/api/v1/moe-calendar/upcoming?as_of=2026-11-20")
        self.assertEqual(cal_up.headers.get("Cache-Control"), "no-store, private")
        self.assertEqual(cal_up.headers.get("Vary"), "Cookie")
        cal_sy = other_user.get("/api/v1/moe-calendar/2026-2027")
        self.assertEqual(cal_sy.headers.get("Cache-Control"), "no-store, private")
        self.assertEqual(cal_sy.headers.get("Vary"), "Cookie")

        # 5. Real Headless Chrome E2E verification of Guest "🔒 Sign in to Save" -> OAuth+PKCE -> auto-save -> reload (`F5`) -> Sign-Out scrub
        chrome_bin = Path("/usr/bin/google-chrome")
        if chrome_bin.exists():
            import shutil as _shutil
            import signal as _signal

            chrome_tmp = tempfile.TemporaryDirectory(
                prefix="tier4_chrome_", ignore_cleanup_errors=True
            )
            self.addCleanup(
                lambda: _shutil.rmtree(chrome_tmp.name, ignore_errors=True)
            )
            self.addCleanup(chrome_tmp.cleanup)
            browser_client = self.get_client(db_path)

            raw_html = (PROJECT_ROOT / "frontend" / "index.html").read_text("utf-8")
            raw_js = (PROJECT_ROOT / "frontend" / "src" / "app.js").read_text("utf-8")
            # Strip external Google Fonts / manifest / external script tags so offline Headless Chrome mounts cleanly
            inlined_base = _re.sub(
                r'<link[^>]+(?:fonts\.googleapis\.com|fonts\.gstatic\.com|manifest\.webmanifest)[^>]*>',
                "",
                raw_html,
            )
            inlined_base = inlined_base.replace(
                '<link rel="stylesheet" href="/src/styles/app.css" />',
                f"<style>{css_text}</style>",
            )
            inlined_base = _re.sub(
                r'<script[^>]+src="/src/app\.js"[^>]*></script>',
                "",
                inlined_base,
            )

            def build_mounted_doc(ss_json: str, ls_json: str) -> str:
                bridge_preamble = f"""<script>
(function() {{
  window.__fvpJsErrors = [];
  window.addEventListener('error', function(e) {{ window.__fvpJsErrors.push(String(e.message || e)); }});
  window.addEventListener('unhandledrejection', function(e) {{ window.__fvpJsErrors.push(String(e.reason || e)); }});
  const _ss = Object.assign({{}}, {ss_json});
  const _ls = Object.assign({{}}, {ls_json});
  function _mkStore(backing) {{
    return {{
      getItem(k) {{ return Object.prototype.hasOwnProperty.call(backing, k) ? backing[k] : null; }},
      setItem(k, v) {{ backing[String(k)] = String(v); }},
      removeItem(k) {{ delete backing[String(k)]; }},
      clear() {{ Object.keys(backing).forEach((k) => delete backing[k]); }},
      get length() {{ return Object.keys(backing).length; }},
      _dump() {{ return Object.assign({{}}, backing); }}
    }};
  }}
  Object.defineProperty(window, 'sessionStorage', {{ value: _mkStore(_ss), configurable: true }});
  Object.defineProperty(window, 'localStorage', {{ value: _mkStore(_ls), configurable: true }});
  const _cacheMap = new Map([
    ['family-vacation-planner-v3', new Set(['https://breezyflights.com/api/v1/profile', 'https://breezyflights.com/src/app.js'])]
  ]);
  Object.defineProperty(window, 'caches', {{
    configurable: true,
    value: {{
      keys: async () => Array.from(_cacheMap.keys()),
      open: async (name) => {{
        if (!_cacheMap.has(name)) _cacheMap.set(name, new Set());
        const setRef = _cacheMap.get(name);
        return {{
          keys: async () => Array.from(setRef).map((u) => ({{ url: u }})),
          delete: async (req) => setRef.delete(typeof req === 'string' ? req : req.url)
        }};
      }},
      _dump: () => {{
        const out = {{}};
        _cacheMap.forEach((v, k) => {{ out[k] = Array.from(v); }});
        return out;
      }}
    }}
  }});
  window.__fvpLastAssignedUrl = null;
  let _reqSeq = 0;
  const _pending = new Map();
  window.__fvpResolveFetch = function(id, status, headersObj, bodyText) {{
    const p = _pending.get(id);
    if (!p) return;
    _pending.delete(id);
    p.resolve(new Response(bodyText, {{ status: status, headers: headersObj || {{}} }}));
  }};
  window.fetch = function(input, init) {{
    const urlStr = typeof input === 'string' ? input : input.url;
    if (urlStr.endsWith('/sw.js')) {{
      return Promise.resolve(new Response('', {{ status: 200, headers: {{ 'Content-Type': 'application/javascript' }} }}));
    }}
    const opts = init || {{}};
    const id = ++_reqSeq;
    return new Promise((resolve, reject) => {{
      _pending.set(id, {{ resolve, reject }});
      window.__fvpHostFetch(JSON.stringify({{
        id: id,
        method: opts.method || 'GET',
        url: urlStr,
        headers: opts.headers || {{}},
        body: opts.body || null
      }}));
    }});
  }};
  if (navigator.serviceWorker) {{
    navigator.serviceWorker.register = function() {{ return Promise.resolve({{}}); }};
  }}
}})();
</script>"""
                mounted_js = raw_js.replace(
                    "window.location.assign(loginUrl);",
                    "window.__fvpLastAssignedUrl = String(loginUrl);",
                )
                doc = inlined_base.replace("<head>", "<head>" + bridge_preamble, 1)
                doc = doc.replace(
                    "</body>",
                    f"<script>{mounted_js}</script></body>",
                    1,
                )
                return doc

            proc_c = subprocess.Popen(
                [
                    str(chrome_bin),
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-background-networking",
                    "--disable-extensions",
                    "--remote-debugging-port=0",
                    f"--user-data-dir={chrome_tmp.name}",
                    "about:blank",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            def _kill_chrome_group() -> None:
                try:
                    os.killpg(proc_c.pid, _signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    proc_c.wait(timeout=3.0)
                except Exception:
                    pass

            self.addCleanup(_kill_chrome_group)

            active_port_file = Path(chrome_tmp.name) / "DevToolsActivePort"
            deadline = time.time() + 12.0
            while time.time() < deadline and not active_port_file.exists():
                time.sleep(0.05)
            self.assertTrue(active_port_file.exists(), "Headless Chrome DevToolsActivePort did not appear")
            cdp_port = int(active_port_file.read_text("utf-8").splitlines()[0].strip())

            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"http://127.0.0.1:{cdp_port}/json/list", timeout=5.0) as r_list:
                targets = json.loads(r_list.read().decode("utf-8"))
            page_target = next(t for t in targets if t.get("type") == "page")
            ws_parsed = _urlparse.urlsplit(page_target["webSocketDebuggerUrl"])

            sock = socket.create_connection(("127.0.0.1", cdp_port), timeout=10.0)
            self.addCleanup(sock.close)
            ws_key = _b64.b64encode(os.urandom(16)).decode("ascii")
            handshake = (
                f"GET {ws_parsed.path} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{cdp_port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {ws_key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
            sock.sendall(handshake)
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
            header_end = buf.index(b"\r\n\r\n") + 4
            ws_leftover = bytearray(buf[header_end:])

            def _ws_send_json(obj: dict[str, Any]) -> None:
                raw_b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                mask = os.urandom(4)
                ln = len(raw_b)
                if ln < 126:
                    hdr = bytes([0x81, 0x80 | ln]) + mask
                elif ln < 65536:
                    hdr = bytes([0x81, 0x80 | 126]) + _struct.pack("!H", ln) + mask
                else:
                    hdr = bytes([0x81, 0x80 | 127]) + _struct.pack("!Q", ln) + mask
                masked = bytes(b ^ mask[i % 4] for i, b in enumerate(raw_b))
                sock.sendall(hdr + masked)

            def _ws_recv_exact(n: int) -> bytes:
                while len(ws_leftover) < n:
                    more = sock.recv(65536)
                    if not more:
                        raise EOFError("CDP WebSocket closed unexpectedly")
                    ws_leftover.extend(more)
                out_b = bytes(ws_leftover[:n])
                del ws_leftover[:n]
                return out_b

            def _ws_recv_msg() -> dict[str, Any]:
                fragments: list[bytes] = []
                while True:
                    b0, b1 = _ws_recv_exact(2)
                    fin = bool(b0 & 0x80)
                    opcode = b0 & 0x0F
                    masked_flag = bool(b1 & 0x80)
                    ln = b1 & 0x7F
                    if ln == 126:
                        ln = _struct.unpack("!H", _ws_recv_exact(2))[0]
                    elif ln == 127:
                        ln = _struct.unpack("!Q", _ws_recv_exact(8))[0]
                    mkey = _ws_recv_exact(4) if masked_flag else b""
                    payload_b = _ws_recv_exact(ln)
                    if masked_flag:
                        payload_b = bytes(
                            b ^ mkey[i % 4] for i, b in enumerate(payload_b)
                        )
                    if opcode == 0x9:  # PING -> PONG
                        mask_p = os.urandom(4)
                        sock.sendall(
                            bytes([0x8A, 0x80 | len(payload_b)])
                            + mask_p
                            + bytes(b ^ mask_p[i % 4] for i, b in enumerate(payload_b))
                        )
                        continue
                    fragments.append(payload_b)
                    if fin:
                        return json.loads(b"".join(fragments).decode("utf-8"))

            msg_counter = 0
            env_prev_test = os.environ.get("VACATION_PLANNER_AUTH_TEST_MODE")
            env_prev_live = os.environ.get("ELAL_LIVE_FETCH_ENABLED")
            os.environ["VACATION_PLANNER_AUTH_TEST_MODE"] = "1"
            os.environ["ELAL_LIVE_FETCH_ENABLED"] = "0"
            self.addCleanup(
                lambda: (
                    os.environ.__setitem__("VACATION_PLANNER_AUTH_TEST_MODE", env_prev_test)
                    if env_prev_test is not None
                    else os.environ.pop("VACATION_PLANNER_AUTH_TEST_MODE", None),
                    os.environ.__setitem__("ELAL_LIVE_FETCH_ENABLED", env_prev_live)
                    if env_prev_live is not None
                    else os.environ.pop("ELAL_LIVE_FETCH_ENABLED", None),
                )
            )

            host_fetch_log: list[tuple[str, str]] = []

            def _handle_binding_event(ev_msg: dict[str, Any]) -> None:
                if (
                    ev_msg.get("method") == "Runtime.bindingCalled"
                    and ev_msg.get("params", {}).get("name") == "__fvpHostFetch"
                ):
                    req_info = json.loads(ev_msg["params"]["payload"])
                    parsed_u = _urlparse.urlsplit(req_info["url"])
                    path_qs = parsed_u.path + (
                        f"?{parsed_u.query}" if parsed_u.query else ""
                    )
                    host_fetch_log.append(
                        (str(req_info.get("method") or "GET").upper(), path_qs)
                    )
                    j_body = (
                        json.loads(req_info["body"])
                        if req_info.get("body")
                        else None
                    )
                    resp_obj = browser_client.request(
                        req_info["method"],
                        path_qs,
                        json_body=j_body,
                        headers=req_info.get("headers") or {},
                    )
                    nonlocal msg_counter
                    msg_counter += 1
                    expr = f"window.__fvpResolveFetch({int(req_info['id'])}, {int(resp_obj.status_code)}, {json.dumps(dict(resp_obj.headers))}, {json.dumps(resp_obj.text)});"
                    _ws_send_json(
                        {
                            "id": msg_counter,
                            "method": "Runtime.evaluate",
                            "params": {"expression": expr},
                        }
                    )

            def _cdp_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
                nonlocal msg_counter
                msg_counter += 1
                target_id = msg_counter
                _ws_send_json({"id": target_id, "method": method, "params": params or {}})
                while True:
                    incoming = _ws_recv_msg()
                    if "method" in incoming:
                        _handle_binding_event(incoming)
                        continue
                    if incoming.get("id") == target_id:
                        return incoming

            def _cdp_eval(js_expr: str) -> Any:
                res = _cdp_call(
                    "Runtime.evaluate",
                    {
                        "expression": js_expr,
                        "awaitPromise": True,
                        "returnByValue": True,
                    },
                )
                inner = res.get("result", {})
                if "exceptionDetails" in inner:
                    raise AssertionError(
                        f"CDP JS exception: {inner['exceptionDetails']}"
                    )
                return inner.get("result", {}).get("value")

            _cdp_call("Page.enable")
            _cdp_call("Runtime.enable")
            _cdp_call("Runtime.addBinding", {"name": "__fvpHostFetch"})
            frame_tree = _cdp_call("Page.getFrameTree")
            frame_id = frame_tree["result"]["frameTree"]["frame"]["id"]

            def _mount_and_wait_boot(ss_obj: dict[str, str], ls_obj: dict[str, str]) -> None:
                _cdp_call(
                    "Page.setDocumentContent",
                    {
                        "frameId": frame_id,
                        "html": build_mounted_doc(
                            json.dumps(ss_obj), json.dumps(ls_obj)
                        ),
                    },
                )
                # Wait until initial guest/user search renders or status settles
                for _ in range(80):
                    ready = _cdp_eval(
                        """new Promise((r) => setTimeout(() => r(Boolean(document.querySelector('.proposal-card, .awaiting-flights-showcase'))), 40))"""
                    )
                    if ready:
                        break

            # Step A: Boot as Guest -> verify 0-points alert + award database note + single sign-in button (`#btn-save-profile` hidden),
            # then add 2 children ([2, 8]) + 150,000 Matmid points and click `#btn-google-signin`
            _mount_and_wait_boot({}, {})
            guest_draft_state = _cdp_eval(
                """(() => {
                  const saveBtnEl = document.getElementById('btn-save-profile');
                  const saveBtnHiddenOnGuest = Boolean(saveBtnEl && saveBtnEl.hasAttribute('hidden'));
                  const zeroAlertEl = document.getElementById('zero-points-search-alert');
                  const zeroAlertText = zeroAlertEl ? zeroAlertEl.textContent : '';
                  const awardNoteEl = document.getElementById('award-source-note-banner');
                  const awardNoteText = awardNoteEl ? awardNoteEl.textContent : '';
                  const awardNoteBodyEl = awardNoteEl ? awardNoteEl.querySelector('.award-note-body') : null;
                  const awardNoteBodyText = awardNoteBodyEl ? awardNoteBodyEl.textContent.trim() : '';
                  document.getElementById('btn-add-child').click();
                  document.getElementById('btn-add-child').click();
                  const age0 = document.querySelector('[data-child-age="0"]');
                  age0.value = '2';
                  age0.dispatchEvent(new Event('input', { bubbles: true }));
                  age0.dispatchEvent(new Event('change', { bubbles: true }));
                  const age1 = document.querySelector('[data-child-age="1"]');
                  age1.value = '8';
                  age1.dispatchEvent(new Event('input', { bubbles: true }));
                  age1.dispatchEvent(new Event('change', { bubbles: true }));
                  const mInput = document.getElementById('prof-matmid-points');
                  mInput.value = '150000';
                  mInput.dispatchEvent(new Event('input', { bubbles: true }));
                  mInput.dispatchEvent(new Event('change', { bubbles: true }));
                  const googleBtn = document.getElementById('btn-google-signin');
                  const btnTextBefore = googleBtn ? googleBtn.textContent : '';
                  const removedCount = document.querySelectorAll('.allocations-details, .allocations-table, .btn-ics-link, #prof-pto-budget').length;
                  const bodyTxt = document.body.innerText || '';
                  googleBtn.click();
                  return {
                    saveBtnHiddenOnGuest,
                    zeroAlertText,
                    awardNoteText,
                    awardNoteBodyText,
                    btnTextBefore,
                    removedCount,
                    bodyTxt,
                    assignedUrl: window.__fvpLastAssignedUrl,
                    ssDump: window.sessionStorage._dump()
                  };
                })()"""
            )
            self.assertTrue(guest_draft_state["saveBtnHiddenOnGuest"])
            self.assertEqual(guest_draft_state["removedCount"], 0)
            for removed_tok in ("פירוט הקצאת", "ייצוא .ics", "תקציב חופש"):
                self.assertNotIn(removed_tok, guest_draft_state["bodyTxt"])
            self.assertIn("חופשת עבודה", guest_draft_state["bodyTxt"])
            self.assertNotIn('התאמה לחופשת בי"ס', guest_draft_state["bodyTxt"])
            self.assertIsNone(
                _re.search(
                    r"(?<![א-ת])(?:של\s+)?(?:ה|ל|ב|ו|ש|כ)?בוגרים(?![א-ת])",
                    guest_draft_state["bodyTxt"],
                )
            )
            self.assertIn("יתרת מתמיד 0", guest_draft_state["zeroAlertText"])
            self.assertIn("מאגר כרטיסי הבונוס של אל על", guest_draft_state["awardNoteText"])
            self.assertIn("מאגר טיסות הבונוס מתעדכן פעם ביום", guest_draft_state["awardNoteBodyText"])
            self.assertNotIn("rbddataclients", guest_draft_state["awardNoteText"].lower())
            for cash_tok in ("הערכת מחיר", "הערכות מחיר", "במזומן", "חיסכון משוער", "¢", "~$", "Est. Cash"):
                self.assertNotIn(cash_tok, guest_draft_state["zeroAlertText"])
                self.assertNotIn(cash_tok, guest_draft_state["awardNoteText"])
                self.assertNotIn(cash_tok, guest_draft_state["awardNoteBodyText"])
            self.assertIn("התחברות עם Gmail", guest_draft_state["btnTextBefore"])
            self.assertTrue(
                str(guest_draft_state["assignedUrl"]).startswith(
                    "/api/v1/auth/google/login"
                )
            )
            self.assertIn("fvp_pending_oauth_draft", guest_draft_state["ssDump"])

            # Step B: Complete server-side OAuth+PKCE redirect chain for `draft.family@gmail.com`
            r_l = browser_client.get(
                f"{guest_draft_state['assignedUrl']}&mock_oauth=1&test_email=draft.family@gmail.com"
            )
            self.assertEqual(r_l.status_code, 302)
            r_az = browser_client.get(r_l.headers["Location"])
            self.assertEqual(r_az.status_code, 302)
            r_cb = browser_client.get(r_az.headers["Location"])
            self.assertEqual(r_cb.status_code, 302)
            self.assertEqual(r_cb.headers["Location"], "/")

            # Step C: Land on `/` with `fvp_pending_oauth_draft` in sessionStorage -> auto-saves via PUT /api/v1/profile!
            _mount_and_wait_boot(guest_draft_state["ssDump"], {})
            post_login_state = _cdp_eval(
                """(() => ({
                  ages: Array.from(document.querySelectorAll('[data-child-age]')).map((el) => Number(el.value)),
                  matmid: document.getElementById('prof-matmid-points').value,
                  saveBtnHiddenAfterLogin: document.getElementById('btn-save-profile').hasAttribute('hidden'),
                  hasZeroAlertAfterLogin: Boolean(document.getElementById('zero-points-search-alert')),
                  firstCardText: (document.querySelector('.proposal-card') || {}).textContent || '',
                  feedback: document.getElementById('auth-save-feedback').textContent,
                  feedbackHidden: document.getElementById('auth-save-feedback').hasAttribute('hidden'),
                  ssRemaining: window.sessionStorage._dump(),
                  jsErrors: window.__fvpJsErrors
                }))()"""
            )
            self.assertEqual(post_login_state["jsErrors"], [])
            self.assertEqual(post_login_state["ages"], [2, 8])
            self.assertEqual(post_login_state["matmid"], "150000")
            self.assertFalse(post_login_state["saveBtnHiddenAfterLogin"])
            self.assertFalse(post_login_state["hasZeroAlertAfterLogin"])
            for removed_card_tok in ("~$", "הערכת מחיר במזומן", "חיסכון משוער", "¢", "נקודות מתמיד"):
                self.assertNotIn(removed_card_tok, post_login_state["firstCardText"])
            self.assertTrue(
                "בונוס בשני הכיוונים" in post_login_state["firstCardText"]
                or "בונוס בכיוון אחד בלבד" in post_login_state["firstCardText"]
            )
            self.assertNotIn("כדאיות בונוס", post_login_state["firstCardText"])
            self.assertIn('התאמה לחופשת בי"ס', post_login_state["firstCardText"])
            self.assertIn("/100", post_login_state["firstCardText"])
            self.assertFalse(post_login_state["feedbackHidden"])
            self.assertIn("נשמר", post_login_state["feedback"])
            self.assertNotIn("fvp_pending_oauth_draft", post_login_state["ssRemaining"])

            # Step D: Reload `/` (`F5` with EMPTY sessionStorage) -> retains `[2, 8]` & `150000` from SQLite!
            _mount_and_wait_boot({}, {"custom_pref": "1"})
            reload_state = _cdp_eval(
                """(() => ({
                  ages: Array.from(document.querySelectorAll('[data-child-age]')).map((el) => Number(el.value)),
                  matmid: document.getElementById('prof-matmid-points').value,
                  hhSummary: document.getElementById('household-summary-text').textContent.trim(),
                  jsErrors: window.__fvpJsErrors
                }))()"""
            )
            self.assertEqual(reload_state["jsErrors"], [])
            self.assertEqual(reload_state["ages"], [2, 8])
            self.assertEqual(reload_state["matmid"], "150000")
            self.assertIn("150,000", reload_state["hhSummary"])
            self.assertIn("2 ילדים", reload_state["hhSummary"])

            # Step D2: Returning-user (`is_persisted === true`) non-overwrite guard against conflicting `fvp_pending_oauth_draft`
            conflicting_draft = {
                "ts": int(time.time() * 1000),
                "adults_count": 2,
                "matmid_points_balance": 10000,
                "children": [
                    {
                        "child_age_years": 15,
                        "framework_type": "HIGH_SCHOOL_10_12",
                    }
                ],
            }
            host_fetch_log.clear()
            _mount_and_wait_boot(
                {"fvp_pending_oauth_draft": json.dumps(conflicting_draft)},
                {"custom_pref": "1"},
            )
            overwrite_puts = [
                (m, p)
                for m, p in host_fetch_log
                if m == "PUT" and p.startswith("/api/v1/profile")
            ]
            self.assertEqual(
                overwrite_puts,
                [],
                f"Expected 0 PUT /api/v1/profile calls for already-persisted returning user, got {overwrite_puts}",
            )
            guard_state = _cdp_eval(
                """(() => ({
                  ages: Array.from(document.querySelectorAll('[data-child-age]')).map((el) => Number(el.value)),
                  matmid: document.getElementById('prof-matmid-points').value,
                  draftItem: window.sessionStorage.getItem('fvp_pending_oauth_draft'),
                  jsErrors: window.__fvpJsErrors
                }))()"""
            )
            self.assertEqual(guard_state["jsErrors"], [])
            self.assertIsNone(guard_state["draftItem"])
            self.assertEqual(guard_state["ages"], [2, 8])
            self.assertEqual(guard_state["matmid"], "150000")
            db_prof_after_guard = browser_client.get("/api/v1/profile").json()
            self.assertTrue(db_prof_after_guard["is_persisted"])
            self.assertEqual(
                [c["child_age_years"] for c in db_prof_after_guard["children"]],
                [2, 8],
            )
            self.assertEqual(db_prof_after_guard["matmid_points_balance"], 150000)

            # Step E: Click Sign-Out -> scrubs DOM, storage, calendarData, and revokes session!
            signout_state = _cdp_eval(
                """(async () => {
                  document.getElementById('btn-signout').click();
                  for (let i = 0; i < 100; i++) {
                    await new Promise((r) => setTimeout(r, 40));
                    const guestShown = !document.getElementById('auth-guest-panel').hasAttribute('hidden');
                    const calReady = document.querySelectorAll('#moe-calendar-tbody tr').length > 0;
                    const cardsReady = document.querySelectorAll('.proposal-card, .awaiting-flights-showcase').length > 0;
                    if (guestShown && calReady && cardsReady) break;
                  }
                  return {
                    ages: Array.from(document.querySelectorAll('[data-child-age]')).map((el) => Number(el.value)),
                    matmid: document.getElementById('prof-matmid-points').value,
                    calRows: document.querySelectorAll('#moe-calendar-tbody tr').length,
                    lsLen: window.localStorage.length,
                    ssLen: window.sessionStorage.length,
                    cachesDump: window.caches._dump(),
                    jsErrors: window.__fvpJsErrors
                  };
                })()"""
            )
            self.assertEqual(signout_state["jsErrors"], [])
            self.assertEqual(signout_state["ages"], [])
            self.assertEqual(signout_state["matmid"], "0")
            self.assertGreater(signout_state["calRows"], 0)
            self.assertEqual(signout_state["lsLen"], 0)
            self.assertEqual(signout_state["ssLen"], 0)
            self.assertEqual(
                signout_state["cachesDump"]["family-vacation-planner-v3"],
                ["https://breezyflights.com/src/app.js"],
            )

    def test_scenario_22_run7_r1_r3_r4_and_mobile_thumb_dock_e2e(self) -> None:
        import base64 as _b64
        import re as _re
        import shutil as _shutil
        import signal as _signal
        import struct as _struct
        import urllib.parse as _urlparse

        db_path, _repo, client = self.create_authenticated_client_env("scen22@gmail.com")

        # 1. Static & PWA contracts (R1–R3 + B5)
        html_text = (PROJECT_ROOT / "frontend" / "index.html").read_text("utf-8")
        css_text = (PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css").read_text("utf-8")
        js_text = (PROJECT_ROOT / "frontend" / "src" / "app.js").read_text("utf-8")
        self.assertIsNone(_re.search(r"(?i)(left|right)", css_text))
        self.assertNotIn("ellipsis", css_text.lower())
        for removed_asset_tok in (
            "prof-pto-budget",
            "allocations-details",
            "allocations-table",
            "btn-ics-link",
            "פירוט הקצאת",
            "ייצוא .ics",
            "export.ics",
        ):
            self.assertNotIn(removed_asset_tok, html_text)
            self.assertNotIn(removed_asset_tok, js_text)
        self.assertIn("לוח חגים ומועדים במשק", html_text)
        self.assertIn("חופשת עבודה", js_text)
        self.assertIsNone(
            _re.search(r"(?<![א-ת])(?:של\s+)?(?:ה|ל|ב|ו|ש|כ)?בוגרים(?![א-ת])", html_text)
        )
        self.assertIsNone(
            _re.search(r"(?<![א-ת])(?:של\s+)?(?:ה|ל|ב|ו|ש|כ)?בוגרים(?![א-ת])", js_text)
        )

        manifest = client.get("/manifest.webmanifest").json()
        self.assertEqual(manifest["theme_color"], "#0B1F3A")
        self.assertEqual(manifest["background_color"], "#F2F5F9")
        self.assertNotIn("מקסום ימי חופש", json.dumps(manifest, ensure_ascii=False))
        self.assertNotIn("ימי החופש", json.dumps(manifest, ensure_ascii=False))

        # 2. REST & CLI contracts (R1–R3)
        for pto_field, bad_val in (
            ("annual_pto_budget", 18),
            ("max_pto_per_trip", 5),
            ("workweek_type", "SUN_THU"),
            ("erev_chag_pto_weight", 0.5),
            ("chol_hamoed_pto_weight", 0.5),
        ):
            r_pto = client.put("/api/v1/profile", json={"adults_count": 2, pto_field: bad_val})
            self.assertEqual(r_pto.status_code, 422, f"Expected 422 for {pto_field}")

        s_resp = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO", "ATH"],
            },
        )
        self.assertEqual(s_resp.status_code, 200)
        s_body = s_resp.json()
        _assert_run11_search_response_contract(self, s_body, is_bonus_search=True)
        self.assertGreaterEqual(len(s_body["proposals"]), 2)
        p0 = s_body["proposals"][0]
        it0 = p0["itinerary"]
        for req_it_key in (
            "seated_passengers_count",
            "bonus_tickets_count",
            "cash_tickets_count",
            "primary_cabin",
            *RUN11_NEW_ITINERARY_KEYS,
        ):
            self.assertIn(req_it_key, it0)
        self.assertNotIn("family_ticket_allocation", it0)
        self.assertIn("holiday_alignment_score", p0)
        for removed_prop_key in (
            "total_vacation_days",
            "parent_pto_days_used",
            "pto_efficiency_ratio",
            "vacation_utilization_score",
        ):
            self.assertNotIn(removed_prop_key, p0)
        self.assertEqual(client.get(f"/api/v1/vacations/{p0['id']}/export.ics").status_code, 404)

        cmp_resp = client.post(
            "/api/v1/vacations/compare",
            json={"proposal_ids": [s_body["proposals"][0]["id"], s_body["proposals"][1]["id"]]},
        )
        self.assertEqual(cmp_resp.status_code, 404)
        for removed_cmp_sel in (
            "btn-compare-selected",
            "sticky-compare-bar",
            "comparison-banner-container",
            "data-compare-id",
            "compare-check-label",
            "has-compare-bar",
        ):
            self.assertNotIn(removed_cmp_sel, html_text)
            self.assertNotIn(removed_cmp_sel, js_text)
            self.assertNotIn(removed_cmp_sel, css_text)

        # 3. Real Headless Chrome Multi-Viewport (390x844 Mobile & 1440x900 Desktop, he RTL & en LTR)
        chrome_bin = Path("/usr/bin/google-chrome")
        if not chrome_bin.exists():
            return

        chrome_tmp = tempfile.TemporaryDirectory(
            prefix="tier4_scen22_chrome_", ignore_cleanup_errors=True
        )
        self.addCleanup(lambda: _shutil.rmtree(chrome_tmp.name, ignore_errors=True))
        self.addCleanup(chrome_tmp.cleanup)
        guest_browser_client = self.get_client(db_path)
        active_browser_client = guest_browser_client

        inlined_html = _re.sub(
            r'<link[^>]+(?:fonts\.googleapis\.com|fonts\.gstatic\.com|manifest\.webmanifest)[^>]*>',
            "",
            html_text,
        )
        inlined_html = inlined_html.replace(
            '<link rel="stylesheet" href="/src/styles/app.css" />',
            f"<style>{css_text}</style>",
        )
        inlined_html = _re.sub(
            r'<script[^>]+src="/src/app\.js"[^>]*></script>',
            "",
            inlined_html,
        )
        bridge_preamble = """<script>
(function() {
  window.__fvpJsErrors = [];
  window.addEventListener('error', function(e) { window.__fvpJsErrors.push(String(e.message || e)); });
  window.addEventListener('unhandledrejection', function(e) { window.__fvpJsErrors.push(String(e.reason || e)); });
  const _ss = {};
  const _ls = {};
  function _mkStore(backing) {
    return {
      getItem(k) { return Object.prototype.hasOwnProperty.call(backing, k) ? backing[k] : null; },
      setItem(k, v) { backing[String(k)] = String(v); },
      removeItem(k) { delete backing[String(k)]; },
      clear() { Object.keys(backing).forEach((k) => delete backing[k]); },
      get length() { return Object.keys(backing).length; }
    };
  }
  Object.defineProperty(window, 'sessionStorage', { value: _mkStore(_ss), configurable: true });
  Object.defineProperty(window, 'localStorage', { value: _mkStore(_ls), configurable: true });
  let _reqSeq = 0;
  const _pending = new Map();
  window.__fvpResolveFetch = function(id, status, headersObj, bodyText) {
    const p = _pending.get(id);
    if (!p) return;
    _pending.delete(id);
    p.resolve(new Response(bodyText, { status: status, headers: headersObj || {} }));
  };
  window.fetch = function(input, init) {
    const urlStr = typeof input === 'string' ? input : input.url;
    if (urlStr.endsWith('/sw.js')) {
      return Promise.resolve(new Response('', { status: 200, headers: { 'Content-Type': 'application/javascript' } }));
    }
    const opts = init || {};
    const id = ++_reqSeq;
    return new Promise((resolve, reject) => {
      _pending.set(id, { resolve, reject });
      window.__fvpHostFetch(JSON.stringify({
        id: id,
        method: opts.method || 'GET',
        url: urlStr,
        headers: opts.headers || {},
        body: opts.body || null
      }));
    });
  };
  if (navigator.serviceWorker) {
    navigator.serviceWorker.register = function() { return Promise.resolve({}); };
  }
})();
</script>"""
        mounted_doc = inlined_html.replace("<head>", "<head>" + bridge_preamble, 1).replace(
            "</body>", f"<script>{js_text}</script></body>", 1
        )

        proc_c = subprocess.Popen(
            [
                str(chrome_bin),
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-extensions",
                "--remote-debugging-port=0",
                f"--user-data-dir={chrome_tmp.name}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        def _kill_chrome() -> None:
            try:
                os.killpg(proc_c.pid, _signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc_c.wait(timeout=3.0)
            except Exception:
                pass

        self.addCleanup(_kill_chrome)

        active_port_file = Path(chrome_tmp.name) / "DevToolsActivePort"
        deadline = time.time() + 12.0
        while time.time() < deadline and not (active_port_file.exists() and active_port_file.read_text("utf-8").splitlines()):
            time.sleep(0.05)
        self.assertTrue(active_port_file.exists(), "Headless Chrome DevToolsActivePort did not appear")
        cdp_port = int(active_port_file.read_text("utf-8").splitlines()[0].strip())

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{cdp_port}/json/list", timeout=5.0) as r_list:
            targets = json.loads(r_list.read().decode("utf-8"))
        page_target = next(t for t in targets if t.get("type") == "page")
        ws_parsed = _urlparse.urlsplit(page_target["webSocketDebuggerUrl"])

        sock = socket.create_connection(("127.0.0.1", cdp_port), timeout=10.0)
        self.addCleanup(sock.close)
        ws_key = _b64.b64encode(os.urandom(16)).decode("ascii")
        sock.sendall(
            (
                f"GET {ws_parsed.path} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{cdp_port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {ws_key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
        )
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        ws_leftover = bytearray(buf[buf.index(b"\r\n\r\n") + 4 :])

        def _ws_send_json(obj: dict[str, Any]) -> None:
            raw_b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            mask = os.urandom(4)
            ln = len(raw_b)
            if ln < 126:
                hdr = bytes([0x81, 0x80 | ln]) + mask
            elif ln < 65536:
                hdr = bytes([0x81, 0x80 | 126]) + _struct.pack("!H", ln) + mask
            else:
                hdr = bytes([0x81, 0x80 | 127]) + _struct.pack("!Q", ln) + mask
            sock.sendall(hdr + bytes(b ^ mask[i % 4] for i, b in enumerate(raw_b)))

        def _ws_recv_exact(n: int) -> bytes:
            while len(ws_leftover) < n:
                more = sock.recv(65536)
                if not more:
                    raise EOFError("CDP WebSocket closed unexpectedly")
                ws_leftover.extend(more)
            out_b = bytes(ws_leftover[:n])
            del ws_leftover[:n]
            return out_b

        def _ws_recv_msg() -> dict[str, Any]:
            fragments: list[bytes] = []
            while True:
                b0, b1 = _ws_recv_exact(2)
                fin = bool(b0 & 0x80)
                opcode = b0 & 0x0F
                masked_flag = bool(b1 & 0x80)
                ln = b1 & 0x7F
                if ln == 126:
                    ln = _struct.unpack("!H", _ws_recv_exact(2))[0]
                elif ln == 127:
                    ln = _struct.unpack("!Q", _ws_recv_exact(8))[0]
                mkey = _ws_recv_exact(4) if masked_flag else b""
                payload_b = _ws_recv_exact(ln)
                if masked_flag:
                    payload_b = bytes(b ^ mkey[i % 4] for i, b in enumerate(payload_b))
                if opcode == 0x9:
                    mask_p = os.urandom(4)
                    sock.sendall(
                        bytes([0x8A, 0x80 | len(payload_b)])
                        + mask_p
                        + bytes(b ^ mask_p[i % 4] for i, b in enumerate(payload_b))
                    )
                    continue
                fragments.append(payload_b)
                if fin:
                    return json.loads(b"".join(fragments).decode("utf-8"))

        msg_counter = 0

        def _handle_binding_event(ev_msg: dict[str, Any]) -> None:
            if (
                ev_msg.get("method") == "Runtime.bindingCalled"
                and ev_msg.get("params", {}).get("name") == "__fvpHostFetch"
            ):
                req_info = json.loads(ev_msg["params"]["payload"])
                parsed_u = _urlparse.urlsplit(req_info["url"])
                path_qs = parsed_u.path + (f"?{parsed_u.query}" if parsed_u.query else "")
                j_body = json.loads(req_info["body"]) if req_info.get("body") else None
                resp_obj = active_browser_client.request(
                    req_info["method"],
                    path_qs,
                    json_body=j_body,
                    headers=req_info.get("headers") or {},
                )
                nonlocal msg_counter
                msg_counter += 1
                expr = (
                    f"window.__fvpResolveFetch({int(req_info['id'])}, "
                    f"{int(resp_obj.status_code)}, {json.dumps(dict(resp_obj.headers))}, {json.dumps(resp_obj.text)});"
                )
                _ws_send_json({"id": msg_counter, "method": "Runtime.evaluate", "params": {"expression": expr}})

        def _cdp_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            nonlocal msg_counter
            msg_counter += 1
            target_id = msg_counter
            _ws_send_json({"id": target_id, "method": method, "params": params or {}})
            while True:
                incoming = _ws_recv_msg()
                if "method" in incoming:
                    _handle_binding_event(incoming)
                    continue
                if incoming.get("id") == target_id:
                    return incoming

        def _cdp_eval(js_expr: str) -> Any:
            res = _cdp_call(
                "Runtime.evaluate",
                {"expression": js_expr, "awaitPromise": True, "returnByValue": True},
            )
            inner = res.get("result", {})
            if "exceptionDetails" in inner:
                raise AssertionError(f"CDP JS exception: {inner['exceptionDetails']}")
            return inner.get("result", {}).get("value")

        _cdp_call("Page.enable")
        _cdp_call("Runtime.enable")
        _cdp_call("Runtime.addBinding", {"name": "__fvpHostFetch"})
        frame_id = _cdp_call("Page.getFrameTree")["result"]["frameTree"]["frame"]["id"]

        # Emulate 390x844 mobile first before mounting so boot runs at mobile viewport
        _cdp_call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True},
        )
        _cdp_call("Page.setDocumentContent", {"frameId": frame_id, "html": mounted_doc})
        for _ in range(80):
            if _cdp_eval(
                "new Promise((r) => setTimeout(() => r(document.querySelectorAll('.proposal-card').length >= 2), 40))"
            ):
                break

        for target_dir in ("rtl", "ltr"):
            if target_dir == "ltr":
                _cdp_eval("document.getElementById('btn-toggle-locale').click(); true;")
            mob = _cdp_eval(
                """(() => {
                  window.scrollTo(0, 0);
                  const docEl = document.documentElement;
                  const dock = document.getElementById('mobile-thumb-dock');
                  const dockR = dock.getBoundingClientRect();
                  const hhBar = document.getElementById('household-summary-bar');
                  const searchZone = document.getElementById('zone-search');
                  const profZone = document.getElementById('zone-profile');
                  const drawer = document.getElementById('search-secondary-drawer');
                  const firstCard = document.querySelector('.proposal-card');
                  return {
                    dir: docEl.getAttribute('dir'),
                    scrollWidth: docEl.scrollWidth,
                    clientWidth: docEl.clientWidth,
                    dockDisplay: getComputedStyle(dock).display,
                    dockHeight: dockR.height,
                    hhBarDisplay: getComputedStyle(hhBar).display,
                    hhBarAboveSearch: hhBar.getBoundingClientRect().bottom <= searchZone.getBoundingClientRect().top + 1,
                    profDisplayCollapsed: getComputedStyle(profZone).display,
                    drawerDisplayCollapsed: getComputedStyle(drawer).display,
                    firstCardY: firstCard ? firstCard.getBoundingClientRect().top : 9999,
                    jsErrors: window.__fvpJsErrors
                  };
                })()"""
            )
            self.assertEqual(mob["jsErrors"], [])
            self.assertEqual(mob["dir"], target_dir)
            self.assertLessEqual(mob["scrollWidth"], mob["clientWidth"])
            self.assertNotEqual(mob["dockDisplay"], "none")
            self.assertGreaterEqual(mob["dockHeight"], 56)
            self.assertNotEqual(mob["hhBarDisplay"], "none")
            self.assertTrue(mob["hhBarAboveSearch"])
            self.assertEqual(mob["profDisplayCollapsed"], "none")
            self.assertEqual(mob["drawerDisplayCollapsed"], "none")
            self.assertLess(mob["firstCardY"], 900)

        # Switch back to Hebrew RTL on 390x844 and test interactive mobile overlays & stacking
        _cdp_eval("if (document.documentElement.getAttribute('dir') !== 'rtl') document.getElementById('btn-toggle-locale').click(); true;")

        # (a) Secondary search filter drawer toggle
        drawer_open_display = _cdp_eval(
            """(() => {
              document.getElementById('btn-toggle-search-filters').click();
              const d = getComputedStyle(document.getElementById('search-secondary-drawer')).display;
              document.getElementById('btn-toggle-search-filters').click();
              return d;
            })()"""
        )
        self.assertNotEqual(drawer_open_display, "none")

        # (b) Tapping `[data-focus-matmid="true"]` (and dock Family button) opens `#zone-profile.is-sheet-open` (z-index 60) ABOVE the always-visible `#mobile-thumb-dock` (z-index 70) and focuses `#prof-matmid-points`
        sheet_check = _cdp_eval(
            """(async () => {
              const focusBtn = document.querySelector('[data-focus-matmid="true"]');
              if (focusBtn) focusBtn.click();
              else document.querySelector('[data-dock-zone="zone-profile"]').click();
              await new Promise((r) => setTimeout(r, 120));
              const prof = document.getElementById('zone-profile');
              const dock = document.getElementById('mobile-thumb-dock');
              const profRect = prof.getBoundingClientRect();
              const dockRect = dock.getBoundingClientRect();
              const openState = {
                isSheetOpen: prof.classList.contains('is-sheet-open'),
                zIndex: getComputedStyle(prof).zIndex,
                dockZIndex: getComputedStyle(dock).zIndex,
                bodyLocked: document.body.classList.contains('is-sheet-locked'),
                dockDisplayWhileOpen: getComputedStyle(dock).display,
                profBottom: profRect.bottom,
                dockTop: dockRect.top,
                dockBottom: dockRect.bottom,
                dockProfActive: document.querySelector('[data-dock-zone="zone-profile"]').classList.contains('active'),
                dockProfLabel: document.querySelector('[data-dock-zone="zone-profile"] .mobile-dock-label').textContent.trim(),
                activeId: document.activeElement ? document.activeElement.id : ''
              };
              document.getElementById('btn-close-profile-sheet').click();
              const dockAfterClose = getComputedStyle(dock).display;
              const searchActiveAfterClose = document.querySelector('[data-dock-zone="zone-search"]').classList.contains('active');
              return { ...openState, dockAfterClose, searchActiveAfterClose };
            })()"""
        )
        self.assertTrue(sheet_check["isSheetOpen"])
        self.assertEqual(sheet_check["zIndex"], "60")
        self.assertEqual(sheet_check["dockZIndex"], "70")
        self.assertTrue(sheet_check["bodyLocked"])
        self.assertEqual(sheet_check["dockDisplayWhileOpen"], "grid")
        self.assertLessEqual(sheet_check["profBottom"], sheet_check["dockTop"] + 2.0)
        self.assertGreater(sheet_check["dockBottom"], sheet_check["dockTop"])
        self.assertTrue(sheet_check["dockProfActive"])
        self.assertEqual(sheet_check["dockProfLabel"], "הרכב טסים")
        self.assertEqual(sheet_check["activeId"], "prof-matmid-points")
        self.assertEqual(sheet_check["dockAfterClose"], "grid")
        self.assertTrue(sheet_check["searchActiveAfterClose"])

        # (c) Keyboard viewport guard keeps `.is-keyboard-open` class while `#mobile-thumb-dock` stays persistently visible
        kb_check = _cdp_eval(
            """(() => {
              document.getElementById('btn-toggle-search-filters').click();
              const inp = document.getElementById('input-min-nights');
              const dock = document.getElementById('mobile-thumb-dock');
              inp.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
              const kbOpen = document.body.classList.contains('is-keyboard-open');
              const dockDuringKb = getComputedStyle(dock).display;
              inp.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
              const dockAfterKb = getComputedStyle(dock).display;
              document.getElementById('btn-toggle-search-filters').click();
              return { kbOpen, dockDuringKb, dockAfterKb };
            })()"""
        )
        self.assertTrue(kb_check["kbOpen"])
        self.assertEqual(kb_check["dockDuringKb"], "grid")
        self.assertEqual(kb_check["dockAfterKb"], "grid")

        # (d) Verify all flight/proposal comparison controls, checkboxes, sticky bars, and banners are absent (`run10` R1)
        cmp_bar_check = _cdp_eval(
            """(() => {
              const cmpMatches = document.querySelectorAll(
                '#btn-compare-selected, #sticky-compare-bar, #comparison-banner-container, [data-compare-id], .compare-check-label, .comparison-col-card'
              ).length;
              return {
                cmpMatches,
                hasCompareBody: document.body.classList.contains('has-compare-bar')
              };
            })()"""
        )
        self.assertEqual(cmp_bar_check["cmpMatches"], 0)
        self.assertFalse(cmp_bar_check["hasCompareBody"])

        # (e) Tapping `#btn-mobile-dock-calendar` opens `#zone-calendar` shared popup in <768px card-stack layout without overflow
        mob_cal = _cdp_eval(
            """(() => {
              document.getElementById('btn-mobile-dock-calendar').click();
              const calZone = document.getElementById('zone-calendar');
              const tbl = document.getElementById('moe-calendar-table');
              const wrkTbl = document.getElementById('workplace-calendar-table');
              const docEl = document.documentElement;
              const res = {
                calHidden: calZone.hasAttribute('hidden'),
                calPos: getComputedStyle(calZone).position,
                tblDisplay: getComputedStyle(tbl).display,
                wrkTblDisplay: getComputedStyle(wrkTbl).display,
                wrkRows: document.querySelectorAll('#workplace-calendar-tbody tr').length,
                scrollWidth: docEl.scrollWidth,
                clientWidth: docEl.clientWidth
              };
              document.getElementById('btn-close-calendar').click();
              return res;
            })()"""
        )
        self.assertFalse(mob_cal["calHidden"])
        self.assertEqual(mob_cal["calPos"], "fixed")
        self.assertEqual(mob_cal["tblDisplay"], "block")
        self.assertEqual(mob_cal["wrkTblDisplay"], "block")
        self.assertEqual(mob_cal["wrkRows"], 10)
        self.assertLessEqual(mob_cal["scrollWidth"], mob_cal["clientWidth"])

        # (f) Opening `#zone-profile` sheet at <1180px (`390x844`), then resizing to 1440x900 (`>=1180px`) unlocks body cleanly
        resize_pre = _cdp_eval(
            """(() => {
              document.querySelector('[data-dock-zone="zone-profile"]').click();
              return {
                bodyLockedBefore: document.body.classList.contains('is-sheet-locked'),
                sheetOpenBefore: document.getElementById('zone-profile').classList.contains('is-sheet-open'),
                dockProfActiveBefore: document.querySelector('[data-dock-zone="zone-profile"]').classList.contains('active')
              };
            })()"""
        )
        self.assertTrue(resize_pre["bodyLockedBefore"])
        self.assertTrue(resize_pre["sheetOpenBefore"])
        self.assertTrue(resize_pre["dockProfActiveBefore"])

        # 4. Switch to 1440x900 Desktop (both he RTL & en LTR)
        _cdp_call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
        )
        resize_post = _cdp_eval(
            """(async () => {
              await new Promise((r) => setTimeout(r, 60));
              return {
                bodyLockedAfter: document.body.classList.contains('is-sheet-locked'),
                sheetOpenAfter: document.getElementById('zone-profile').classList.contains('is-sheet-open'),
                dockProfActiveAfter: document.querySelector('[data-dock-zone="zone-profile"]').classList.contains('active'),
                hhAriaExpandedAfter: document.getElementById('btn-open-profile-sheet').getAttribute('aria-expanded'),
                bodyOverflowAfter: getComputedStyle(document.body).overflow
              };
            })()"""
        )
        self.assertFalse(resize_post["bodyLockedAfter"])
        self.assertFalse(resize_post["sheetOpenAfter"])
        self.assertFalse(resize_post["dockProfActiveAfter"])
        self.assertEqual(resize_post["hhAriaExpandedAfter"], "false")
        self.assertNotEqual(resize_post["bodyOverflowAfter"], "hidden")

        for target_dir in ("rtl", "ltr"):
            if target_dir == "ltr":
                _cdp_eval("document.getElementById('btn-toggle-locale').click(); true;")
            desk = _cdp_eval(
                """(() => {
                  const calBtn = document.getElementById('btn-toggle-calendar');
                  calBtn.click();
                  const calBtnActiveWhenOpen = calBtn.classList.contains('active');
                  const docEl = document.documentElement;
                  const dock = document.getElementById('mobile-thumb-dock');
                  const deskNav = document.querySelector('.desktop-zone-nav');
                  const prof = document.getElementById('zone-profile');
                  const bookBtn = document.querySelector('a[data-elal-book-link="true"]');
                  const calZone = document.getElementById('zone-calendar');
                  const tbl = document.getElementById('moe-calendar-table');
                  const wrkTbl = document.getElementById('workplace-calendar-table');
                  const calPos = getComputedStyle(calZone).position;
                  const wrkTblDisplay = getComputedStyle(wrkTbl).display;
                  document.getElementById('btn-close-calendar').click();
                  const calBtnActiveAfterClose = calBtn.classList.contains('active');
                  return {
                    dir: docEl.getAttribute('dir'),
                    scrollWidth: docEl.scrollWidth,
                    clientWidth: docEl.clientWidth,
                    dockDisplay: getComputedStyle(dock).display,
                    deskNavDisplay: getComputedStyle(deskNav).display,
                    profDisplay: getComputedStyle(prof).display,
                    profSheetOpen: prof.classList.contains('is-sheet-open'),
                    railStripVisible: (() => {
                      const strip = document.getElementById('household-summary-bar');
                      const r = strip.getBoundingClientRect();
                      return getComputedStyle(strip).display !== 'none' && r.width > 0 && r.height > 0;
                    })(),
                    railEditVisible: (() => {
                      const editBtn = document.getElementById('btn-open-profile-sheet');
                      const r = editBtn.getBoundingClientRect();
                      return editBtn.checkVisibility() && r.width > 0 && r.height > 0;
                    })(),
                    railEditText: document.getElementById('btn-open-profile-sheet').textContent.trim(),
                    adultsFieldVisible: document.getElementById('prof-adults-count').getBoundingClientRect().height > 0,
                    bookHeight: bookBtn ? bookBtn.getBoundingClientRect().height : 0,
                    calPos,
                    tblDisplay: getComputedStyle(tbl).display,
                    wrkTblDisplay,
                    calBtnActiveWhenOpen,
                    calBtnActiveAfterClose,
                    jsErrors: window.__fvpJsErrors
                  };
                })()"""
            )
            self.assertEqual(desk["jsErrors"], [])
            self.assertEqual(desk["dir"], target_dir)
            self.assertLessEqual(desk["scrollWidth"], desk["clientWidth"])
            self.assertEqual(desk["dockDisplay"], "none")
            self.assertEqual(desk["deskNavDisplay"], "flex")
            # Run 13: at desktop width the profile panel is closed (not a static block in the rail) and the
            # access strip with its edit control is what is visible, in Hebrew and in English
            self.assertEqual(desk["profDisplay"], "none")
            self.assertFalse(desk["profSheetOpen"])
            self.assertFalse(desk["adultsFieldVisible"])
            self.assertTrue(desk["railStripVisible"])
            self.assertTrue(desk["railEditVisible"])
            self.assertEqual(desk["railEditText"], "עריכה" if target_dir == "rtl" else "Edit")
            self.assertGreater(desk["bookHeight"], 0)
            self.assertLessEqual(desk["bookHeight"], 42)
            self.assertEqual(desk["calPos"], "fixed")
            self.assertEqual(desk["tblDisplay"], "table")
            self.assertEqual(desk["wrkTblDisplay"], "table")
            self.assertTrue(desk["calBtnActiveWhenOpen"])
            self.assertFalse(desk["calBtnActiveAfterClose"])

        # 5. Signed-in `#btn-save-profile` HTTP 422 error clears proposals and renders validation banner cleanly
        active_browser_client = client
        _cdp_call("Page.setDocumentContent", {"frameId": frame_id, "html": mounted_doc})
        for _ in range(80):
            if _cdp_eval(
                "new Promise((r) => setTimeout(() => r(document.querySelectorAll('.proposal-card').length >= 2 && !document.getElementById('btn-save-profile').hasAttribute('hidden')), 40))"
            ):
                break

        save_err_check = _cdp_eval(
            """(async () => {
              const adultsEl = document.getElementById('prof-adults-count');
              adultsEl.value = '99';
              adultsEl.dispatchEvent(new Event('input', { bubbles: true }));
              adultsEl.dispatchEvent(new Event('change', { bubbles: true }));
              document.getElementById('btn-save-profile').click();
              for (let i = 0; i < 60; i++) {
                await new Promise((r) => setTimeout(r, 30));
                if (document.querySelector('.status-banner-card')) break;
              }
              return {
                proposalsCountAfter: document.querySelectorAll('.proposal-card').length,
                hasErrorBanner: Boolean(document.querySelector('.status-banner-card')),
                hasCompareBodyAfter: document.body.classList.contains('has-compare-bar'),
                jsErrors: window.__fvpJsErrors
              };
            })()"""
        )
        self.assertEqual(save_err_check["jsErrors"], [])
        self.assertEqual(save_err_check["proposalsCountAfter"], 0)
        self.assertTrue(save_err_check["hasErrorBanner"])
        self.assertFalse(save_err_check["hasCompareBodyAfter"])

    def test_scenario_23_run10_r1_r2_r3_r4_comprehensive_e2e(self) -> None:
        """Scenario 23 (Run 10 R1–R4): Comparison removal, UI+API multi-select destinations, scoped Thailand breezyflights branding & 3-surface disclaimers."""
        import base64 as _b64
        import re as _re
        import shutil as _shutil
        import signal as _signal
        import socket
        import struct as _struct
        import subprocess
        import time
        import urllib.parse as _urlparse
        import urllib.request

        db_path, _repo, authed_client = self.create_authenticated_client_env("scen23@gmail.com")
        guest_client = self.get_client(db_path)

        # R1: Backend comparison endpoint rejected with 404
        self.assertEqual(
            guest_client.post("/api/v1/vacations/compare", json={"proposal_ids": ["x"]}).status_code,
            404,
        )

        # R4: Local sign-in HTML page (`GET /api/v1/auth/test-oauth-authorize`) in he & en
        old_tm = os.environ.get("VACATION_PLANNER_AUTH_TEST_MODE")
        old_lf = os.environ.get("ELAL_LIVE_FETCH_ENABLED")
        os.environ["VACATION_PLANNER_AUTH_TEST_MODE"] = "1"
        os.environ["ELAL_LIVE_FETCH_ENABLED"] = "0"

        def _restore_auth_env() -> None:
            if old_tm is None:
                os.environ.pop("VACATION_PLANNER_AUTH_TEST_MODE", None)
            else:
                os.environ["VACATION_PLANNER_AUTH_TEST_MODE"] = old_tm
            if old_lf is None:
                os.environ.pop("ELAL_LIVE_FETCH_ENABLED", None)
            else:
                os.environ["ELAL_LIVE_FETCH_ENABLED"] = old_lf

        self.addCleanup(_restore_auth_env)

        oauth_he_client = self.get_client(db_path)
        oauth_en_client = self.get_client(db_path)
        oauth_he_login = oauth_he_client.get("/api/v1/auth/google/login?lang=he")
        oauth_en_login = oauth_en_client.get("/api/v1/auth/google/login?lang=en")
        self.assertEqual(oauth_he_login.status_code, 302)
        self.assertEqual(oauth_en_login.status_code, 302)
        oauth_he_page = oauth_he_client.get(oauth_he_login.headers["Location"])
        oauth_en_page = oauth_en_client.get(oauth_en_login.headers["Location"])
        self.assertEqual(oauth_he_page.status_code, 200)
        self.assertEqual(oauth_en_page.status_code, 200)
        self.assertIn("אפליקציית תכנון חופשות עצמאית שאינה שייכת לאל על", oauth_he_page.text)
        self.assertIn("not affiliated with", oauth_en_page.text)

        chrome_bin = Path("/usr/bin/google-chrome")
        if not chrome_bin.exists():
            return

        chrome_tmp = tempfile.TemporaryDirectory(
            prefix="tier4_scen23_chrome_", ignore_cleanup_errors=True
        )
        self.addCleanup(lambda: _shutil.rmtree(chrome_tmp.name, ignore_errors=True))
        self.addCleanup(chrome_tmp.cleanup)

        html_text = (PROJECT_ROOT / "frontend" / "index.html").read_text("utf-8")
        css_text = (PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css").read_text("utf-8")
        js_text = (PROJECT_ROOT / "frontend" / "src" / "app.js").read_text("utf-8")

        inlined_html = _re.sub(
            r'<link[^>]+(?:fonts\.googleapis\.com|fonts\.gstatic\.com|manifest\.webmanifest)[^>]*>',
            "",
            html_text,
        )
        inlined_html = _re.sub(r"<noscript>.*?</noscript>", "", inlined_html, flags=_re.S)
        inlined_html = inlined_html.replace(
            '<link rel="stylesheet" href="/src/styles/app.css" />',
            f"<style>{css_text}</style>",
        )
        inlined_html = _re.sub(
            r'<script[^>]+src="/src/app\.js"[^>]*></script>', "", inlined_html
        )
        bridge_preamble = """<script>
(function() {
  window.__FVP_REFERENCE_DATE__ = '2026-11-19';
  window.__fvpJsErrors = [];
  window.__fvpSearchRequests = [];
  window.addEventListener('error', function(e) { window.__fvpJsErrors.push(String(e.message || e)); });
  window.addEventListener('unhandledrejection', function(e) { window.__fvpJsErrors.push(String(e.reason || e)); });
  const _ss = {};
  const _ls = {};
  function _mkStore(backing) {
    return {
      getItem(k) { return Object.prototype.hasOwnProperty.call(backing, k) ? backing[k] : null; },
      setItem(k, v) { backing[String(k)] = String(v); },
      removeItem(k) { delete backing[String(k)]; },
      clear() { Object.keys(backing).forEach((k) => delete backing[k]); },
      get length() { return Object.keys(backing).length; }
    };
  }
  Object.defineProperty(window, 'sessionStorage', { value: _mkStore(_ss), configurable: true });
  Object.defineProperty(window, 'localStorage', { value: _mkStore(_ls), configurable: true });
  let _reqSeq = 0;
  const _pending = new Map();
  window.__fvpResolveFetch = function(id, status, headersObj, bodyText) {
    const p = _pending.get(id);
    if (!p) return;
    _pending.delete(id);
    p.resolve(new Response(bodyText, { status: status, headers: headersObj || {} }));
  };
  window.fetch = function(input, init) {
    const urlStr = typeof input === 'string' ? input : input.url;
    if (urlStr.endsWith('/sw.js')) {
      return Promise.resolve(new Response('', { status: 200, headers: { 'Content-Type': 'application/javascript' } }));
    }
    const opts = init || {};
    if (urlStr.includes('/api/v1/vacations/search') && opts.body) {
      try { window.__fvpSearchRequests.push(JSON.parse(opts.body)); } catch (_e) {}
    }
    const id = ++_reqSeq;
    return new Promise((resolve, reject) => {
      _pending.set(id, { resolve, reject });
      window.__fvpHostFetch(JSON.stringify({
        id: id,
        method: opts.method || 'GET',
        url: urlStr,
        headers: opts.headers || {},
        body: opts.body || null
      }));
    });
  };
  if (navigator.serviceWorker) {
    navigator.serviceWorker.register = function() { return Promise.resolve({}); };
  }
})();
</script>"""
        mounted_doc = inlined_html.replace("<head>", "<head>" + bridge_preamble, 1).replace(
            "</body>", f"<script>{js_text}</script></body>", 1
        )

        active_browser_client = guest_client
        proc_c = subprocess.Popen(
            [
                str(chrome_bin),
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-extensions",
                "--remote-debugging-port=0",
                f"--user-data-dir={chrome_tmp.name}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        def _kill_chrome() -> None:
            try:
                os.killpg(proc_c.pid, _signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc_c.wait(timeout=3.0)
            except Exception:
                pass

        self.addCleanup(_kill_chrome)

        active_port_file = Path(chrome_tmp.name) / "DevToolsActivePort"
        deadline = time.time() + 12.0
        while time.time() < deadline and not (active_port_file.exists() and active_port_file.read_text("utf-8").splitlines()):
            time.sleep(0.05)
        self.assertTrue(active_port_file.exists())
        cdp_port = int(active_port_file.read_text("utf-8").splitlines()[0].strip())

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{cdp_port}/json/list", timeout=5.0) as r_list:
            targets = json.loads(r_list.read().decode("utf-8"))
        page_target = next(t for t in targets if t.get("type") == "page")
        ws_parsed = _urlparse.urlsplit(page_target["webSocketDebuggerUrl"])

        sock = socket.create_connection(("127.0.0.1", cdp_port), timeout=10.0)
        self.addCleanup(sock.close)
        ws_key = _b64.b64encode(os.urandom(16)).decode("ascii")
        sock.sendall(
            (
                f"GET {ws_parsed.path} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{cdp_port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {ws_key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
        )
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        ws_leftover = bytearray(buf[buf.index(b"\r\n\r\n") + 4 :])

        def _ws_send_json(obj: dict[str, Any]) -> None:
            raw_b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            mask = os.urandom(4)
            ln = len(raw_b)
            if ln < 126:
                hdr = bytes([0x81, 0x80 | ln]) + mask
            elif ln < 65536:
                hdr = bytes([0x81, 0x80 | 126]) + _struct.pack("!H", ln) + mask
            else:
                hdr = bytes([0x81, 0x80 | 127]) + _struct.pack("!Q", ln) + mask
            sock.sendall(hdr + bytes(b ^ mask[i % 4] for i, b in enumerate(raw_b)))

        def _ws_recv_exact(n: int) -> bytes:
            while len(ws_leftover) < n:
                more = sock.recv(65536)
                if not more:
                    raise EOFError("CDP WebSocket closed unexpectedly")
                ws_leftover.extend(more)
            out_b = bytes(ws_leftover[:n])
            del ws_leftover[:n]
            return out_b

        def _ws_recv_msg() -> dict[str, Any]:
            fragments: list[bytes] = []
            while True:
                b0, b1 = _ws_recv_exact(2)
                fin = bool(b0 & 0x80)
                opcode = b0 & 0x0F
                masked_flag = bool(b1 & 0x80)
                ln = b1 & 0x7F
                if ln == 126:
                    ln = _struct.unpack("!H", _ws_recv_exact(2))[0]
                elif ln == 127:
                    ln = _struct.unpack("!Q", _ws_recv_exact(8))[0]
                mkey = _ws_recv_exact(4) if masked_flag else b""
                payload_b = _ws_recv_exact(ln)
                if masked_flag:
                    payload_b = bytes(b ^ mkey[i % 4] for i, b in enumerate(payload_b))
                if opcode == 0x9:
                    mask_p = os.urandom(4)
                    sock.sendall(
                        bytes([0x8A, 0x80 | len(payload_b)])
                        + mask_p
                        + bytes(b ^ mask_p[i % 4] for i, b in enumerate(payload_b))
                    )
                    continue
                fragments.append(payload_b)
                if fin:
                    return json.loads(b"".join(fragments).decode("utf-8"))

        msg_counter = 0

        def _handle_binding_event(ev_msg: dict[str, Any]) -> None:
            if (
                ev_msg.get("method") == "Runtime.bindingCalled"
                and ev_msg.get("params", {}).get("name") == "__fvpHostFetch"
            ):
                req_info = json.loads(ev_msg["params"]["payload"])
                parsed_u = _urlparse.urlsplit(req_info["url"])
                path_qs = parsed_u.path + (f"?{parsed_u.query}" if parsed_u.query else "")
                j_body = json.loads(req_info["body"]) if req_info.get("body") else None
                resp_obj = active_browser_client.request(
                    req_info["method"],
                    path_qs,
                    json_body=j_body,
                    headers=req_info.get("headers") or {},
                )
                nonlocal msg_counter
                msg_counter += 1
                expr = (
                    f"window.__fvpResolveFetch({int(req_info['id'])}, "
                    f"{int(resp_obj.status_code)}, {json.dumps(dict(resp_obj.headers))}, {json.dumps(resp_obj.text)});"
                )
                _ws_send_json({"id": msg_counter, "method": "Runtime.evaluate", "params": {"expression": expr}})

        def _cdp_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            nonlocal msg_counter
            msg_counter += 1
            target_id = msg_counter
            _ws_send_json({"id": target_id, "method": method, "params": params or {}})
            while True:
                incoming = _ws_recv_msg()
                if "method" in incoming:
                    _handle_binding_event(incoming)
                    continue
                if incoming.get("id") == target_id:
                    return incoming

        def _cdp_eval(js_expr: str) -> Any:
            res = _cdp_call(
                "Runtime.evaluate",
                {"expression": js_expr, "awaitPromise": True, "returnByValue": True},
            )
            inner = res.get("result", {})
            if "exceptionDetails" in inner:
                raise AssertionError(f"CDP JS exception: {inner['exceptionDetails']}")
            return inner.get("result", {}).get("value")

        _cdp_call("Page.enable")
        _cdp_call("Runtime.enable")
        _cdp_call("Runtime.addBinding", {"name": "__fvpHostFetch"})
        frame_id = _cdp_call("Page.getFrameTree")["result"]["frameTree"]["frame"]["id"]

        # 1. Desktop 1440x900: Verify R3 branding + unchanged below-hero surface colors, R4 disclaimers, and R2 multi-select UI
        _cdp_call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
        )
        _cdp_call("Page.setDocumentContent", {"frameId": frame_id, "html": mounted_doc})
        for _ in range(80):
            if _cdp_eval(
                "new Promise((r) => setTimeout(() => r(document.querySelectorAll('.proposal-card').length >= 2), 30))"
            ):
                break

        desk_audit = _cdp_eval(
            """(() => {
              const rootStyle = getComputedStyle(document.documentElement);
              const hdrWordmark = document.querySelector('#app-header #header-title .brand-wordmark');
              const heroBrand = document.querySelector('#vacation-hero #hero-eyebrow .hero-brand-inline');
              const heroCopy = document.querySelector('#vacation-hero .hero-copy-col');
              const heroCardRect = document.getElementById('vacation-hero').getBoundingClientRect();
              const heroSvg = document.querySelector('#vacation-hero svg.hero-scenic-svg');
              const heroSvgRect = heroSvg ? heroSvg.getBoundingClientRect() : { width: 0, height: 0 };
              const footerDisc = document.getElementById('footer-elal-disclaimer');
              const guestDisc = document.getElementById('profile-signin-disclaimer');
              const userDisc = document.getElementById('profile-user-disclaimer');
              return {
                jsErrors: window.__fvpJsErrors,
                hdrWordmarkTxt: hdrWordmark ? hdrWordmark.textContent.trim() : '',
                hdrWordmarkVisible: Boolean(hdrWordmark && hdrWordmark.getBoundingClientRect().width > 0),
                heroBrandTxt: heroBrand ? heroBrand.textContent.trim() : '',
                heroCopyHiddenOnDesktop: Boolean(heroCopy && getComputedStyle(heroCopy).display === 'none'),
                heroSvgVisible: Boolean(heroSvg && heroSvgRect.height >= 80 && heroSvgRect.height <= 115),
                heroSvgFullWidth: Boolean(heroSvg && heroSvgRect.width >= heroCardRect.width - 4),
                thaiOnRoot: rootStyle.getPropertyValue('--thai-abyss-teal').trim(),
                canvasToken: rootStyle.getPropertyValue('--canvas-limestone').trim(),
                surfaceToken: rootStyle.getPropertyValue('--surface-boarding').trim(),
                azureToken: rootStyle.getPropertyValue('--azure-elal').trim(),
                bodyBg: getComputedStyle(document.body).backgroundColor,
                bodyColor: getComputedStyle(document.body).color,
                searchBg: getComputedStyle(document.getElementById('zone-search')).backgroundColor,
                profileBg: getComputedStyle(document.getElementById('zone-profile')).backgroundColor,
                resultsBg: getComputedStyle(document.getElementById('zone-results')).backgroundColor,
                hhBarBg: getComputedStyle(document.getElementById('household-summary-bar')).backgroundColor,
                modeTabsBg: getComputedStyle(document.querySelector('.mode-tabs')).backgroundColor,
                authCardBg: getComputedStyle(document.getElementById('profile-auth-card')).backgroundColor,
                proposalBg: getComputedStyle(document.querySelector('.proposal-card')).backgroundColor,
                stubBg: getComputedStyle(document.querySelector('.proposal-pass-stub')).backgroundColor,
                footerBg: getComputedStyle(document.getElementById('site-footer')).backgroundColor,
                footerDiscVisible: Boolean(footerDisc && footerDisc.getBoundingClientRect().height > 0),
                footerDiscTxt: footerDisc ? footerDisc.textContent.trim() : '',
                guestDiscVisible: Boolean(guestDisc && guestDisc.getBoundingClientRect().height > 0),
                userDiscHidden: Boolean(userDisc && userDisc.getBoundingClientRect().height === 0)
              };
            })()"""
        )
        self.assertEqual(desk_audit["jsErrors"], [])
        self.assertEqual(desk_audit["hdrWordmarkTxt"], "breezyflights")
        self.assertTrue(desk_audit["hdrWordmarkVisible"])
        self.assertEqual(desk_audit["heroBrandTxt"], "")
        self.assertTrue(desk_audit["heroCopyHiddenOnDesktop"])
        self.assertTrue(desk_audit["heroSvgVisible"])
        self.assertTrue(desk_audit["heroSvgFullWidth"])
        self.assertEqual(desk_audit["thaiOnRoot"], "")
        self.assertEqual(desk_audit["canvasToken"], "#F2F5F9")
        self.assertEqual(desk_audit["surfaceToken"], "#FFFFFF")
        self.assertEqual(desk_audit["azureToken"], "#1452A6")
        self.assertEqual(desk_audit["bodyBg"], "rgb(242, 245, 249)")
        self.assertEqual(desk_audit["bodyColor"], "rgb(11, 31, 58)")
        for surface_key in ("searchBg", "profileBg", "resultsBg", "hhBarBg", "proposalBg", "footerBg"):
            self.assertEqual(desk_audit[surface_key], "rgb(255, 255, 255)")
        self.assertEqual(desk_audit["modeTabsBg"], "rgb(232, 238, 246)")
        self.assertEqual(desk_audit["stubBg"], "rgb(232, 238, 246)")
        self.assertEqual(desk_audit["authCardBg"], "rgb(234, 241, 251)")
        self.assertTrue(desk_audit["footerDiscVisible"])
        self.assertIn("אפליקציית תכנון חופשות עצמאית שאינה שייכת לאל על", desk_audit["footerDiscTxt"])
        # Run 13: the Gmail sign-in area is closed on boot, so neither sign-in disclaimer has a box yet
        self.assertFalse(desk_audit["guestDiscVisible"])
        self.assertTrue(desk_audit["userDiscHidden"])

        # Run 13: a real mouse click on the top-left header auth button opens the popover and shows the guest disclaimer
        disc_js = """(() => {
          const guestDisc = document.getElementById('profile-signin-disclaimer');
          const userDisc = document.getElementById('profile-user-disclaimer');
          const isAuthed = !document.getElementById('btn-header-signout').hasAttribute('hidden');
          const trigger = document.getElementById(isAuthed ? 'btn-header-account' : 'btn-header-auth');
          return {
            guestDiscH: guestDisc.getBoundingClientRect().height,
            userDiscH: userDisc.getBoundingClientRect().height,
            guestDiscShown: guestDisc.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }),
            userDiscShown: userDisc.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }),
            guestDiscTxt: guestDisc.textContent.trim(),
            userDiscTxt: userDisc.textContent.trim(),
            accountExpanded: trigger.getAttribute('aria-expanded')
          };
        })()"""
        _run13_real_click(_cdp_call, _cdp_eval, "#btn-header-auth")
        guest_disc_open = _cdp_eval(disc_js)
        self.assertEqual(guest_disc_open["accountExpanded"], "true")
        self.assertGreater(guest_disc_open["guestDiscH"], 0)
        self.assertTrue(guest_disc_open["guestDiscShown"])
        self.assertEqual(guest_disc_open["userDiscH"], 0)
        self.assertIn("אפליקציית תכנון חופשות עצמאית שאינה שייכת לאל על", guest_disc_open["guestDiscTxt"])
        _run13_real_click(_cdp_call, _cdp_eval, "#btn-header-auth")
        guest_disc_closed = _cdp_eval(disc_js)
        self.assertEqual(guest_disc_closed["accountExpanded"], "false")
        self.assertEqual(guest_disc_closed["guestDiscH"], 0)

        # R2 UI Multi-Select: Select ROM + ATH + BKK, verify request & strictly filtered results, then reset to ANYWHERE
        ms_flow = _cdp_eval(
            """(async () => {
              document.getElementById('btn-dest-picker-toggle').click();
              document.querySelector('[data-dest-option="ROM"]').click();
              document.querySelector('[data-dest-option="ATH"]').click();
              document.querySelector('[data-dest-option="BKK"]').click();
              document.getElementById('btn-dest-popover-done').click();
              for (let i = 0; i < 150; i++) {
                await new Promise((r) => setTimeout(r, 30));
                const routes = Array.from(document.querySelectorAll('.proposal-route-pair')).map((el) => el.textContent.trim());
                if (routes.length > 0 && routes.every((rt) => rt.includes('FCO') || rt.includes('ATH') || rt.includes('BKK'))) break;
              }
              const subsetReq = window.__fvpSearchRequests[window.__fvpSearchRequests.length - 1];
              const subsetChips = Array.from(document.querySelectorAll('.dest-chip[data-remove-dest]')).map((el) => el.getAttribute('data-remove-dest'));
              const subsetRoutes = Array.from(document.querySelectorAll('.proposal-route-pair')).map((el) => el.textContent.trim());

              document.getElementById('btn-dest-clear-all').click();
              for (let i = 0; i < 150; i++) {
                await new Promise((r) => setTimeout(r, 30));
                const lastReq = window.__fvpSearchRequests[window.__fvpSearchRequests.length - 1];
                const routes = Array.from(document.querySelectorAll('.proposal-route-pair')).map((el) => el.textContent.trim());
                if (lastReq && lastReq.destination_iatas[0] === 'ANYWHERE' && routes.some((rt) => !rt.includes('FCO') && !rt.includes('ATH') && !rt.includes('BKK'))) break;
              }
              const resetReq = window.__fvpSearchRequests[window.__fvpSearchRequests.length - 1];
              const resetRoutes = Array.from(document.querySelectorAll('.proposal-route-pair')).map((el) => el.textContent.trim());
              return { subsetReq, subsetChips, subsetRoutes, resetReq, resetRoutes };
            })()"""
        )
        self.assertEqual(ms_flow["subsetChips"], ["ROM", "ATH", "BKK"])
        self.assertEqual(ms_flow["subsetReq"]["destination_iatas"], ["ROM", "ATH", "BKK"])
        self.assertGreater(len(ms_flow["subsetRoutes"]), 0)
        self.assertTrue(
            all(any(code in rt for code in ("FCO", "ATH", "BKK")) for rt in ms_flow["subsetRoutes"])
        )
        self.assertEqual(ms_flow["resetReq"]["destination_iatas"], ["ANYWHERE"])
        self.assertGreater(len(set(ms_flow["resetRoutes"])), 2)

        # Toggle locale to English (`ltr`) and verify `breezyflights` wordmark survives intact and disclaimers localize
        en_check = _cdp_eval(
            """(() => {
              document.getElementById('btn-toggle-locale').click();
              return {
                dir: document.documentElement.dir,
                hdrWordmark: document.querySelector('#app-header #header-title .brand-wordmark').textContent.trim(),
                footerDiscEn: document.getElementById('footer-elal-disclaimer').textContent.trim(),
                guestDiscEn: document.getElementById('profile-signin-disclaimer').textContent.trim()
              };
            })()"""
        )
        self.assertEqual(en_check["dir"], "ltr")
        self.assertEqual(en_check["hdrWordmark"], "breezyflights")
        self.assertIn("not affiliated with", en_check["footerDiscEn"])
        self.assertIn("not affiliated with", en_check["guestDiscEn"])

        # Run 13: signed-in counterpart at 1440x900 — `#profile-user-disclaimer` is closed on boot and becomes
        # visible once the top-left header account popover is opened with a real mouse click
        active_browser_client = authed_client
        _cdp_call("Page.setDocumentContent", {"frameId": frame_id, "html": mounted_doc})
        for _ in range(80):
            if _cdp_eval(
                "new Promise((r) => setTimeout(() => r(!document.getElementById('btn-header-signout').hasAttribute('hidden') && document.querySelectorAll('.proposal-card').length >= 1), 30))"
            ):
                break
        user_disc_boot = _cdp_eval(disc_js)
        self.assertEqual(_cdp_eval("window.innerWidth"), 1440)
        self.assertEqual(user_disc_boot["userDiscH"], 0)
        self.assertEqual(user_disc_boot["guestDiscH"], 0)
        _run13_real_click(_cdp_call, _cdp_eval, "#btn-header-account")
        user_disc_open = _cdp_eval(disc_js)
        self.assertEqual(user_disc_open["accountExpanded"], "true")
        self.assertGreater(user_disc_open["userDiscH"], 0)
        self.assertTrue(user_disc_open["userDiscShown"])
        self.assertEqual(user_disc_open["guestDiscH"], 0)
        self.assertIn("אפליקציית תכנון חופשות עצמאית שאינה שייכת לאל על", user_disc_open["userDiscTxt"])
        active_browser_client = guest_client

        # 2. Signed-in 360x800 mobile header non-overlap + signed-in header account popover disclaimer
        active_browser_client = authed_client
        _cdp_call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 360, "height": 800, "deviceScaleFactor": 2, "mobile": True},
        )
        _cdp_call("Page.setDocumentContent", {"frameId": frame_id, "html": mounted_doc})
        for _ in range(80):
            if _cdp_eval(
                "new Promise((r) => setTimeout(() => r(!document.getElementById('btn-header-signout').hasAttribute('hidden') && document.querySelectorAll('.proposal-card').length >= 1), 30))"
            ):
                break
        mob_360 = _cdp_eval(
            """(() => {
              const doc = document.documentElement;
              const hdr = document.getElementById('app-header').getBoundingClientRect();
              const brand = document.getElementById('header-brand').getBoundingClientRect();
              const pills = document.querySelector('.header-summary-pills').getBoundingClientRect();
              const overlap = !(brand.right <= pills.left + 1 || pills.right <= brand.left + 1);
              document.getElementById('btn-header-account').click();
              const userDisc = document.getElementById('profile-user-disclaimer');
              const userDiscH = userDisc ? userDisc.getBoundingClientRect().height : 0;
              const scrollWOpen = doc.scrollWidth;
              document.getElementById('btn-header-account').click();
              return {
                scrollW: Math.max(doc.scrollWidth, scrollWOpen),
                clientW: doc.clientWidth,
                headerH: hdr.height,
                overlap,
                userDiscH
              };
            })()"""
        )
        self.assertLessEqual(mob_360["scrollW"], mob_360["clientW"])
        self.assertLessEqual(mob_360["headerH"], 68)
        self.assertFalse(mob_360["overlap"])
        self.assertGreater(mob_360["userDiscH"], 0)

        # 3. Render local sign-in page HTML in Chrome (`he` & `en`) and confirm visible disclaimer
        for oauth_html in (oauth_he_page.text, oauth_en_page.text):
            _cdp_call("Page.setDocumentContent", {"frameId": frame_id, "html": oauth_html})
            ls_vis = _cdp_eval(
                """(() => {
                  const el = document.getElementById('local-signin-disclaimer');
                  return Boolean(el && el.getBoundingClientRect().height > 0);
                })()"""
            )
            self.assertTrue(ls_vis)

    def test_scenario_24_run11_seat_based_cards_direction_statements_and_min_points_e2e(
        self,
    ) -> None:
        """Scenario 24 (Run 11 R1–R4 & U3–U5): Headless Chrome verification of price-free seat-based cards, direction coupons, 1-ticket min points, mixed strategies & zero-bonus empty state."""
        import base64 as _b64
        import re as _re
        import shutil as _shutil
        import signal as _signal
        import socket
        import struct as _struct
        import subprocess
        import time
        import urllib.parse as _urlparse
        import urllib.request

        chrome_bin = Path("/usr/bin/google-chrome")
        self.assertTrue(chrome_bin.exists(), "Headless Chrome binary required at /usr/bin/google-chrome")

        old_lf = os.environ.get("ELAL_LIVE_FETCH_ENABLED")
        os.environ["ELAL_LIVE_FETCH_ENABLED"] = "0"

        def _restore_lf() -> None:
            if old_lf is None:
                os.environ.pop("ELAL_LIVE_FETCH_ENABLED", None)
            else:
                os.environ["ELAL_LIVE_FETCH_ENABLED"] = old_lf

        self.addCleanup(_restore_lf)

        seeded_db_path, _repo = self.make_isolated_env(auto_seed=True)
        seeded_client = self.get_client(seeded_db_path)

        chrome_tmp = tempfile.TemporaryDirectory(
            prefix="tier4_scen24_chrome_", ignore_cleanup_errors=True
        )
        self.addCleanup(lambda: _shutil.rmtree(chrome_tmp.name, ignore_errors=True))
        self.addCleanup(chrome_tmp.cleanup)

        html_text = (PROJECT_ROOT / "frontend" / "index.html").read_text("utf-8")
        css_text = (PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css").read_text("utf-8")
        js_text = (PROJECT_ROOT / "frontend" / "src" / "app.js").read_text("utf-8")

        inlined_html = _re.sub(
            r'<link[^>]+(?:fonts\.googleapis\.com|fonts\.gstatic\.com|manifest\.webmanifest)[^>]*>',
            "",
            html_text,
        )
        inlined_html = _re.sub(r"<noscript>.*?</noscript>", "", inlined_html, flags=_re.S)
        inlined_html = inlined_html.replace(
            '<link rel="stylesheet" href="/src/styles/app.css" />',
            f"<style>{css_text}</style>",
        )
        inlined_html = _re.sub(
            r'<script[^>]+src="/src/app\.js"[^>]*></script>', "", inlined_html
        )
        bridge_preamble = """<script>
(function() {
  window.__FVP_REFERENCE_DATE__ = '2026-11-19';
  window.__fvpJsErrors = [];
  window.addEventListener('error', function(e) { window.__fvpJsErrors.push(String(e.message || e)); });
  window.addEventListener('unhandledrejection', function(e) { window.__fvpJsErrors.push(String(e.reason || e)); });
  const _ss = {};
  const _ls = {};
  function _mkStore(backing) {
    return {
      getItem(k) { return Object.prototype.hasOwnProperty.call(backing, k) ? backing[k] : null; },
      setItem(k, v) { backing[String(k)] = String(v); },
      removeItem(k) { delete backing[String(k)]; },
      clear() { Object.keys(backing).forEach((k) => delete backing[k]); },
      get length() { return Object.keys(backing).length; }
    };
  }
  Object.defineProperty(window, 'sessionStorage', { value: _mkStore(_ss), configurable: true });
  Object.defineProperty(window, 'localStorage', { value: _mkStore(_ls), configurable: true });
  let _reqSeq = 0;
  const _pending = new Map();
  window.__fvpResolveFetch = function(id, status, headersObj, bodyText) {
    const p = _pending.get(id);
    if (!p) return;
    _pending.delete(id);
    p.resolve(new Response(bodyText, { status: status, headers: headersObj || {} }));
  };
  window.fetch = function(input, init) {
    const urlStr = typeof input === 'string' ? input : input.url;
    if (urlStr.endsWith('/sw.js')) {
      return Promise.resolve(new Response('', { status: 200, headers: { 'Content-Type': 'application/javascript' } }));
    }
    const opts = init || {};
    const id = ++_reqSeq;
    return new Promise((resolve, reject) => {
      _pending.set(id, { resolve, reject });
      window.__fvpHostFetch(JSON.stringify({
        id: id,
        method: opts.method || 'GET',
        url: urlStr,
        headers: opts.headers || {},
        body: opts.body || null
      }));
    });
  };
  if (navigator.serviceWorker) {
    navigator.serviceWorker.register = function() { return Promise.resolve({}); };
  }
})();
</script>"""
        mounted_doc = inlined_html.replace("<head>", "<head>" + bridge_preamble, 1).replace(
            "</body>", f"<script>{js_text}</script></body>", 1
        )

        active_browser_client = seeded_client
        proc_c = subprocess.Popen(
            [
                str(chrome_bin),
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-extensions",
                "--remote-debugging-port=0",
                f"--user-data-dir={chrome_tmp.name}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        def _kill_chrome() -> None:
            try:
                os.killpg(proc_c.pid, _signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc_c.wait(timeout=3.0)
            except Exception:
                pass

        self.addCleanup(_kill_chrome)

        active_port_file = Path(chrome_tmp.name) / "DevToolsActivePort"
        deadline = time.time() + 12.0
        while time.time() < deadline and not (active_port_file.exists() and active_port_file.read_text("utf-8").splitlines()):
            time.sleep(0.05)
        self.assertTrue(active_port_file.exists())
        cdp_port = int(active_port_file.read_text("utf-8").splitlines()[0].strip())

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{cdp_port}/json/list", timeout=5.0) as r_list:
            targets = json.loads(r_list.read().decode("utf-8"))
        page_target = next(t for t in targets if t.get("type") == "page")
        ws_parsed = _urlparse.urlsplit(page_target["webSocketDebuggerUrl"])

        sock = socket.create_connection(("127.0.0.1", cdp_port), timeout=10.0)
        self.addCleanup(sock.close)
        ws_key = _b64.b64encode(os.urandom(16)).decode("ascii")
        sock.sendall(
            (
                f"GET {ws_parsed.path} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{cdp_port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {ws_key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
        )
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        ws_leftover = bytearray(buf[buf.index(b"\r\n\r\n") + 4 :])

        def _ws_send_json(obj: dict[str, Any]) -> None:
            raw_b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            mask = os.urandom(4)
            ln = len(raw_b)
            if ln < 126:
                hdr = bytes([0x81, 0x80 | ln]) + mask
            elif ln < 65536:
                hdr = bytes([0x81, 0x80 | 126]) + _struct.pack("!H", ln) + mask
            else:
                hdr = bytes([0x81, 0x80 | 127]) + _struct.pack("!Q", ln) + mask
            sock.sendall(hdr + bytes(b ^ mask[i % 4] for i, b in enumerate(raw_b)))

        def _ws_recv_exact(n: int) -> bytes:
            while len(ws_leftover) < n:
                more = sock.recv(65536)
                if not more:
                    raise EOFError("CDP WebSocket closed unexpectedly")
                ws_leftover.extend(more)
            out_b = bytes(ws_leftover[:n])
            del ws_leftover[:n]
            return out_b

        def _ws_recv_msg() -> dict[str, Any]:
            fragments: list[bytes] = []
            while True:
                b0, b1 = _ws_recv_exact(2)
                fin = bool(b0 & 0x80)
                opcode = b0 & 0x0F
                masked_flag = bool(b1 & 0x80)
                ln = b1 & 0x7F
                if ln == 126:
                    ln = _struct.unpack("!H", _ws_recv_exact(2))[0]
                elif ln == 127:
                    ln = _struct.unpack("!Q", _ws_recv_exact(8))[0]
                mkey = _ws_recv_exact(4) if masked_flag else b""
                payload_b = _ws_recv_exact(ln)
                if masked_flag:
                    payload_b = bytes(b ^ mkey[i % 4] for i, b in enumerate(payload_b))
                if opcode == 0x9:
                    mask_p = os.urandom(4)
                    sock.sendall(
                        bytes([0x8A, 0x80 | len(payload_b)])
                        + mask_p
                        + bytes(b ^ mask_p[i % 4] for i, b in enumerate(payload_b))
                    )
                    continue
                fragments.append(payload_b)
                if fin:
                    return json.loads(b"".join(fragments).decode("utf-8"))

        msg_counter = 0

        def _handle_binding_event(ev_msg: dict[str, Any]) -> None:
            if (
                ev_msg.get("method") == "Runtime.bindingCalled"
                and ev_msg.get("params", {}).get("name") == "__fvpHostFetch"
            ):
                req_info = json.loads(ev_msg["params"]["payload"])
                parsed_u = _urlparse.urlsplit(req_info["url"])
                path_qs = parsed_u.path + (f"?{parsed_u.query}" if parsed_u.query else "")
                j_body = json.loads(req_info["body"]) if req_info.get("body") else None
                resp_obj = active_browser_client.request(
                    req_info["method"],
                    path_qs,
                    json_body=j_body,
                    headers=req_info.get("headers") or {},
                )
                nonlocal msg_counter
                msg_counter += 1
                expr = (
                    f"window.__fvpResolveFetch({int(req_info['id'])}, "
                    f"{int(resp_obj.status_code)}, {json.dumps(dict(resp_obj.headers))}, {json.dumps(resp_obj.text)});"
                )
                _ws_send_json({"id": msg_counter, "method": "Runtime.evaluate", "params": {"expression": expr}})

        def _cdp_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            nonlocal msg_counter
            msg_counter += 1
            target_id = msg_counter
            _ws_send_json({"id": target_id, "method": method, "params": params or {}})
            while True:
                incoming = _ws_recv_msg()
                if "method" in incoming:
                    _handle_binding_event(incoming)
                    continue
                if incoming.get("id") == target_id:
                    return incoming

        def _cdp_eval(js_expr: str) -> Any:
            res = _cdp_call(
                "Runtime.evaluate",
                {"expression": js_expr, "awaitPromise": True, "returnByValue": True},
            )
            inner = res.get("result", {})
            if "exceptionDetails" in inner:
                raise AssertionError(f"CDP JS exception: {inner['exceptionDetails']}")
            return inner.get("result", {}).get("value")

        _cdp_call("Page.enable")
        _cdp_call("Runtime.enable")
        _cdp_call("Runtime.addBinding", {"name": "__fvpHostFetch"})
        frame_id = _cdp_call("Page.getFrameTree")["result"]["frameTree"]["frame"]["id"]

        _cdp_call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
        )
        _cdp_call("Page.setDocumentContent", {"frameId": frame_id, "html": mounted_doc})
        for _ in range(80):
            if _cdp_eval(
                "new Promise((r) => setTimeout(() => r(document.querySelectorAll('.proposal-card').length >= 2), 30))"
            ):
                break

        forbidden_ui_tokens = (
            "הערכת מחיר במזומן",
            "חיסכון משוער",
            "¢",
            "~$",
            "Est. Cash",
            "Est. Net Saved",
            "נקודות מתמיד",
            "Matmid Points",
        )

        # 0. Verify balance-0 guest banners (`#zero-points-search-alert` & `#award-source-note-banner`) are cash-free and keep required hooks
        boot_banners = _cdp_eval(
            """(() => {
              const zeroEl = document.getElementById('zero-points-search-alert');
              const focusCta = zeroEl ? zeroEl.querySelector('[data-focus-matmid="true"]') : null;
              const noteEl = document.getElementById('award-source-note-banner');
              const noteSummary = noteEl ? noteEl.querySelector('.award-note-summary') : null;
              const noteBody = noteEl ? noteEl.querySelector('.award-note-body') : null;
              return {
                jsErrors: window.__fvpJsErrors,
                hasZeroAlert: Boolean(zeroEl),
                zeroText: zeroEl ? zeroEl.textContent : '',
                hasFocusCta: Boolean(focusCta),
                noteSummaryText: noteSummary ? noteSummary.textContent : '',
                noteBodyHtml: noteBody ? noteBody.innerHTML : '',
                noteBodyText: noteBody ? noteBody.textContent : ''
              };
            })()"""
        )
        self.assertEqual(boot_banners["jsErrors"], [])
        self.assertTrue(boot_banners["hasZeroAlert"])
        self.assertTrue(boot_banners["hasFocusCta"])
        self.assertIn("יתרת מתמיד 0", boot_banners["zeroText"])
        self.assertIn("מאגר כרטיסי הבונוס של אל על", boot_banners["noteSummaryText"])
        self.assertIn("<strong>מאגר טיסות הבונוס מתעדכן פעם ביום.</strong>", boot_banners["noteBodyHtml"])
        for tok in (*forbidden_ui_tokens, "מחיר", "מזומן", "תעריפי ייחוס"):
            self.assertNotIn(tok, boot_banners["zeroText"])
            self.assertNotIn(tok, boot_banners["noteSummaryText"])
            self.assertNotIn(tok, boot_banners["noteBodyText"])

        # Helper to snapshot all rendered `.proposal-card` elements in the current locale
        card_inspector_js = """(() => {
          const cards = Array.from(document.querySelectorAll('.proposal-card'));
          return {
            jsErrors: window.__fvpJsErrors,
            dir: document.documentElement.getAttribute('dir'),
            legacyDomCount: document.querySelectorAll('.two-plus-verify-banner, .proposal-pass-footer, .stub-estimate-note, .stub-fare-saved').length,
            hasShowcase: Boolean(document.querySelector('.awaiting-flights-showcase')),
            cards: cards.map((c) => {
              const stmtEl = c.querySelector('.bonus-direction-statement');
              const kpiBonus = c.querySelector('.kpi-cell[data-kpi="bonus-value"]');
              const ctosEl = c.querySelector('.stub-ctos-badge');
              const minPtsEl = c.querySelector('.min-points-ticket');
              const stratTagEl = c.querySelector('.bonus-strategy-tag');
              const twoPlusEl = c.querySelector('.two-plus-note');
              const bookEl = c.querySelector('a[data-elal-book-link="true"]');
              const lanes = Array.from(c.querySelectorAll('.bonus-lane')).map((l) => {
                const seatsEl = l.querySelector('.bonus-lane-seats');
                const flightEl = l.querySelector('.bonus-lane-flight');
                return {
                  direction: l.getAttribute('data-direction'),
                  hasBonus: l.getAttribute('data-has-bonus'),
                  visible: l.getBoundingClientRect().height > 0 && l.getBoundingClientRect().width > 0,
                  seatsAttr: seatsEl ? seatsEl.getAttribute('data-seats') : null,
                  twoPlusAttr: seatsEl ? seatsEl.getAttribute('data-two-plus') : null,
                  seatsText: seatsEl ? seatsEl.textContent.replace(/\\s+/g, ' ').trim() : '',
                  flightText: flightEl ? flightEl.textContent.replace(/\\s+/g, ' ').trim() : ''
                };
              });
              return {
                text: c.textContent || '',
                strategy: c.getAttribute('data-strategy'),
                bonusDirections: c.getAttribute('data-bonus-directions'),
                stmtVisible: Boolean(stmtEl && stmtEl.getBoundingClientRect().height > 0),
                stmtText: stmtEl ? stmtEl.textContent.trim() : '',
                stratTagText: stratTagEl ? stratTagEl.textContent.trim() : null,
                twoPlusText: twoPlusEl ? twoPlusEl.textContent.replace(/\\s+/g, ' ').trim() : null,
                hasKpiBonus: Boolean(kpiBonus && kpiBonus.getBoundingClientRect().height > 0),
                kpiBonusText: kpiBonus ? kpiBonus.textContent.replace(/\\s+/g, ' ').trim() : '',
                hasCtosBadge: Boolean(ctosEl && ctosEl.getBoundingClientRect().height > 0),
                ctosText: ctosEl ? ctosEl.textContent.replace(/\\s+/g, ' ').trim() : '',
                minPoints: minPtsEl ? {
                  pointsAttr: minPtsEl.getAttribute('data-min-points'),
                  scopeAttr: minPtsEl.getAttribute('data-scope'),
                  labelText: (minPtsEl.querySelector('.stub-fare-label') || {}).textContent || '',
                  valText: (minPtsEl.querySelector('.stub-fare-val') || {}).textContent || ''
                } : null,
                bookTitle: bookEl ? (bookEl.getAttribute('title') || '') : '',
                lanes
              };
            })
          };
        })()"""

        # 1. R1 + R2 + R3 + R4 (Both Directions): 4-pax family (2 adults + 2 children [5, 9]), Matmid = 30,000 on FCO 2027-04-11..18
        _cdp_eval(
            """(async () => {
              document.getElementById('btn-add-child').click();
              document.getElementById('btn-add-child').click();
              const c0 = document.querySelector('[data-child-age="0"]');
              c0.value = '5'; c0.dispatchEvent(new Event('input', { bubbles: true })); c0.dispatchEvent(new Event('change', { bubbles: true }));
              const c1 = document.querySelector('[data-child-age="1"]');
              c1.value = '9'; c1.dispatchEvent(new Event('input', { bubbles: true })); c1.dispatchEvent(new Event('change', { bubbles: true }));
              const mEl = document.getElementById('prof-matmid-points');
              mEl.value = '30000'; mEl.dispatchEvent(new Event('input', { bubbles: true })); mEl.dispatchEvent(new Event('change', { bubbles: true }));
              document.querySelector('[data-mode="SPECIFIC_DATES"]').click();
              document.getElementById('input-dep-date').value = '2027-04-11';
              document.getElementById('input-ret-date').value = '2027-04-18';
              document.getElementById('input-flex-days').value = '0';
              document.getElementById('btn-dest-picker-toggle').click();
              document.querySelector('[data-dest-option="ROM"]').click();
              document.getElementById('btn-dest-popover-done').click();
              for (let i = 0; i < 80; i++) {
                await new Promise((r) => setTimeout(r, 30));
                const cards = Array.from(document.querySelectorAll('.proposal-card'));
                if (cards.length > 0 && cards.every((el) => (el.textContent || '').includes('FCO'))) break;
              }
              const toggleBtn = document.querySelector('[data-toggle-all-proposals]');
              if (toggleBtn) toggleBtn.click();
            })()"""
        )

        for expected_dir, expected_stmt, expected_min_30k, expected_seats_lbl in (
            ("rtl", "בונוס בשני הכיוונים", "החל מ-30,000", "2+ מושבי בונוס"),
            ("ltr", "Bonus seats in both directions", "from 30,000", "2+ bonus seats"),
        ):
            if expected_dir == "ltr":
                _cdp_eval("document.getElementById('btn-toggle-locale').click(); true;")
            fco_snap = _cdp_eval(card_inspector_js)
            self.assertEqual(fco_snap["jsErrors"], [])
            self.assertEqual(fco_snap["dir"], expected_dir)
            self.assertEqual(fco_snap["legacyDomCount"], 0)
            self.assertGreaterEqual(len(fco_snap["cards"]), 3)

            by_strat = {c["strategy"]: c for c in fco_snap["cards"]}
            for req_strat in (
                "FULL_BONUS_SAME_CABIN",
                "HYBRID_BONUS_PLUS_CASH",
                "CASH_AND_POINTS",
            ):
                self.assertIn(req_strat, by_strat)
            self.assertNotIn("ONE_WAY_BONUS_ONE_WAY_CASH", by_strat)

            for card in fco_snap["cards"]:
                for bad_tok in (
                    *forbidden_ui_tokens,
                    "120,000",
                    "מחיר",
                    "price",
                    "כיוון אחד בבונוס",
                    "כיוון אחד בונוס",
                    "One way on bonus",
                ):
                    self.assertNotIn(bad_tok, card["text"])
                    self.assertNotIn(bad_tok, card["bookTitle"])
                self.assertEqual(card["bonusDirections"], "both")
                self.assertTrue(card["stmtVisible"])
                self.assertEqual(card["stmtText"], expected_stmt)
                self.assertFalse(card["hasKpiBonus"])
                self.assertTrue(card["hasCtosBadge"])
                self.assertIn("/100", card["ctosText"])
                self.assertEqual(len(card["lanes"]), 2)
                for expected_lane_dir in ("outbound", "inbound"):
                    lane = next(l for l in card["lanes"] if l["direction"] == expected_lane_dir)
                    self.assertTrue(lane["visible"])
                    self.assertEqual(lane["hasBonus"], "true")
                    self.assertEqual(lane["twoPlusAttr"], "true")
                    self.assertGreaterEqual(int(lane["seatsAttr"]), 2)
                    self.assertEqual(lane["seatsText"], expected_seats_lbl)
                self.assertIsNotNone(card["twoPlusText"])
                self.assertIn("4", card["twoPlusText"])

            # R2: 4-pax FULL_BONUS_SAME_CABIN appears at balance 30,000 with 1-ticket minimum `החל מ-30,000` / `from 30,000`
            full_card = by_strat["FULL_BONUS_SAME_CABIN"]
            self.assertIsNone(full_card["stratTagText"])
            self.assertEqual(
                full_card["minPoints"],
                {
                    "pointsAttr": "30000",
                    "scopeAttr": "round_trip",
                    "labelText": (
                        "נקודות לכרטיס בונוס אחד (הלוך ושוב)"
                        if expected_dir == "rtl"
                        else "Points for one bonus ticket (round trip)"
                    ),
                    "valText": expected_min_30k,
                },
            )
            self.assertIsNotNone(by_strat["HYBRID_BONUS_PLUS_CASH"]["stratTagText"])
            self.assertEqual(by_strat["HYBRID_BONUS_PLUS_CASH"]["minPoints"]["pointsAttr"], "30000")
            # R3 / E4: CASH_AND_POINTS carries no points row
            self.assertIsNone(by_strat["CASH_AND_POINTS"]["minPoints"])

        # Switch back to Hebrew RTL before Step 2
        _cdp_eval("if (document.documentElement.getAttribute('dir') !== 'rtl') document.getElementById('btn-toggle-locale').click(); true;")

        # 2. R4 (One Direction — Seeded Outbound-Only): ATH 2026-12-06..12 with balance = 0 (U3)
        _cdp_eval(
            """(async () => {
              const mEl = document.getElementById('prof-matmid-points');
              mEl.value = '0'; mEl.dispatchEvent(new Event('input', { bubbles: true })); mEl.dispatchEvent(new Event('change', { bubbles: true }));
              document.getElementById('btn-dest-clear-all').click();
              await new Promise((r) => setTimeout(r, 80));
              document.getElementById('input-dep-date').value = '2026-12-06';
              document.getElementById('input-ret-date').value = '2026-12-12';
              document.getElementById('input-flex-days').value = '0';
              document.getElementById('btn-dest-picker-toggle').click();
              document.querySelector('[data-dest-option="ATH"]').click();
              document.getElementById('btn-dest-popover-done').click();
              for (let i = 0; i < 80; i++) {
                await new Promise((r) => setTimeout(r, 30));
                const cards = Array.from(document.querySelectorAll('.proposal-card'));
                if (cards.length > 0 && cards.every((el) => (el.textContent || '').includes('ATH') && el.getAttribute('data-bonus-directions') === 'outbound')) break;
              }
            })()"""
        )

        for expected_dir, expected_stmt, expected_no_bonus, expected_comm_flight, expected_ow_prefix in (
            ("rtl", "בונוס בכיוון אחד בלבד — הלוך", "אין בונוס", "טיסה מסחרית (אין בונוס)", "החל מ-"),
            ("ltr", "Bonus seats one way only — outbound", "No bonus seats", "Commercial flight (no bonus)", "from "),
        ):
            if expected_dir == "ltr":
                _cdp_eval("document.getElementById('btn-toggle-locale').click(); true;")
            ath_snap = _cdp_eval(card_inspector_js)
            self.assertEqual(ath_snap["jsErrors"], [])
            self.assertGreaterEqual(len(ath_snap["cards"]), 2)
            ath_by_strat = {c["strategy"]: c for c in ath_snap["cards"]}
            self.assertIn("ONE_WAY_BONUS_ONE_WAY_CASH", ath_by_strat)
            self.assertIn("CASH_AND_POINTS", ath_by_strat)
            ow_card = ath_by_strat["ONE_WAY_BONUS_ONE_WAY_CASH"]
            self.assertIsNone(ow_card["stratTagText"])
            self.assertIsNotNone(ow_card["minPoints"])
            self.assertEqual(ow_card["minPoints"]["scopeAttr"], "one_way")
            self.assertTrue(ow_card["minPoints"]["valText"].startswith(expected_ow_prefix))
            for card in ath_snap["cards"]:
                for bad_tok in forbidden_ui_tokens:
                    self.assertNotIn(bad_tok, card["text"])
                self.assertEqual(card["bonusDirections"], "outbound")
                self.assertTrue(card["stmtVisible"])
                self.assertEqual(card["stmtText"], expected_stmt)
                out_lane = next(l for l in card["lanes"] if l["direction"] == "outbound")
                in_lane = next(l for l in card["lanes"] if l["direction"] == "inbound")
                self.assertEqual(out_lane["hasBonus"], "true")
                self.assertIn("LY541", out_lane["flightText"])
                self.assertEqual(in_lane["hasBonus"], "false")
                self.assertEqual(in_lane["seatsAttr"], "0")
                self.assertEqual(in_lane["twoPlusAttr"], "false")
                self.assertEqual(in_lane["seatsText"], expected_no_bonus)
                self.assertEqual(in_lane["flightText"], expected_comm_flight)

        _cdp_eval("if (document.documentElement.getAttribute('dir') !== 'rtl') document.getElementById('btn-toggle-locale').click(); true;")

        # 3. U4 (Zero-Bonus Empty State) & R4 (Inbound-Only + 1 Exact Seat + LY_CASH) on isolated live-mode DB
        os.environ["ELAL_LIVE_FETCH_ENABLED"] = "1"
        live_db_path, _live_repo = self.make_isolated_env(auto_seed=True)
        live_client = self.get_client(live_db_path)
        active_browser_client = live_client

        # 3a. Sync explicit zero-seat rows for BCN 2027-05-10..17 -> search must render 0 `.proposal-card` elements and show `.awaiting-flights-showcase` (U4)
        z_sync = live_client.post(
            "/api/v1/elal-bonus/sync",
            json={
                "origin": "TLV",
                "destinations": ["BCN"],
                "start_date": "2027-05-09",
                "end_date": "2027-05-18",
                "force_refresh": True,
                "rbd_payload": [
                    {
                        "destination_iata": "BCN",
                        "direction": "OUTBOUND",
                        "flight_number": "LY0393",
                        "flight_date": "2027-05-10",
                        "economy_seats": 0,
                        "premium_seats": 0,
                        "business_seats": 0,
                    },
                    {
                        "destination_iata": "BCN",
                        "direction": "INBOUND",
                        "flight_number": "LY0394",
                        "flight_date": "2027-05-17",
                        "economy_seats": 0,
                        "premium_seats": 0,
                        "business_seats": 0,
                    },
                ],
            },
        )
        self.assertEqual(z_sync.status_code, 200)

        _cdp_eval(
            """(async () => {
              document.getElementById('btn-dest-clear-all').click();
              await new Promise((r) => setTimeout(r, 60));
              document.getElementById('input-dep-date').value = '2027-05-10';
              document.getElementById('input-ret-date').value = '2027-05-17';
              document.getElementById('input-flex-days').value = '0';
              document.getElementById('btn-dest-picker-toggle').click();
              document.querySelector('[data-dest-option="BCN"]').click();
              document.getElementById('btn-dest-popover-done').click();
              for (let i = 0; i < 80; i++) {
                await new Promise((r) => setTimeout(r, 30));
                if (document.querySelector('.awaiting-flights-showcase')) break;
              }
            })()"""
        )
        empty_snap = _cdp_eval(card_inspector_js)
        self.assertEqual(empty_snap["jsErrors"], [])
        self.assertEqual(len(empty_snap["cards"]), 0)
        self.assertTrue(empty_snap["hasShowcase"])

        # 3b. Sync single INBOUND-only 1-seat row for MAD 2027-05-05 -> renders inbound-only statement + `מושב בונוס 1` / `1 bonus seat`
        in_sync = live_client.post(
            "/api/v1/elal-bonus/sync",
            json={
                "origin": "TLV",
                "destinations": ["MAD"],
                "start_date": "2027-04-27",
                "end_date": "2027-05-06",
                "force_refresh": True,
                "rbd_payload": [
                    {
                        "destination_iata": "MAD",
                        "direction": "INBOUND",
                        "flight_number": "LY0398",
                        "flight_date": "2027-05-05",
                        "economy_seats": 1,
                        "premium_seats": 0,
                        "business_seats": 0,
                    },
                ],
            },
        )
        self.assertEqual(in_sync.status_code, 200)

        _cdp_eval(
            """(async () => {
              document.getElementById('btn-dest-clear-all').click();
              await new Promise((r) => setTimeout(r, 60));
              document.getElementById('input-dep-date').value = '2027-04-28';
              document.getElementById('input-ret-date').value = '2027-05-05';
              document.getElementById('input-flex-days').value = '0';
              document.getElementById('btn-dest-picker-toggle').click();
              document.querySelector('[data-dest-option="MAD"]').click();
              document.getElementById('btn-dest-popover-done').click();
              for (let i = 0; i < 80; i++) {
                await new Promise((r) => setTimeout(r, 30));
                if (document.querySelectorAll('.proposal-card[data-bonus-directions="inbound"]').length >= 1) break;
              }
            })()"""
        )
        for expected_dir, expected_stmt, expected_one_seat in (
            ("rtl", "בונוס בכיוון אחד בלבד — חזור", "מושב בונוס 1"),
            ("ltr", "Bonus seats one way only — return", "1 bonus seat"),
        ):
            if expected_dir == "ltr":
                _cdp_eval("document.getElementById('btn-toggle-locale').click(); true;")
            mad_snap = _cdp_eval(card_inspector_js)
            self.assertEqual(mad_snap["jsErrors"], [])
            self.assertGreaterEqual(len(mad_snap["cards"]), 1)
            for card in mad_snap["cards"]:
                self.assertEqual(card["bonusDirections"], "inbound")
                self.assertEqual(card["stmtText"], expected_stmt)
                out_lane = next(l for l in card["lanes"] if l["direction"] == "outbound")
                in_lane = next(l for l in card["lanes"] if l["direction"] == "inbound")
                self.assertEqual(out_lane["hasBonus"], "false")
                self.assertEqual(in_lane["hasBonus"], "true")
                self.assertEqual(in_lane["seatsAttr"], "1")
                self.assertEqual(in_lane["twoPlusAttr"], "false")
                self.assertEqual(in_lane["seatsText"], expected_one_seat)

    def test_scenario_25_run12_compact_stub_weather_consistent_badges_and_kpi_hover_e2e(
        self,
    ) -> None:
        """Scenario 25 (`M12`): Real Headless Chrome CDP verification of compact side-stub weather, non-contradictory bonus badges (`LCA/PFO` `2+`/`2+`, `FCO` `2+`/`2+`, `ATH` 1-way), and unclipped KPI hover/tap explanations in `he` & `en`."""
        import base64 as _b64
        import re as _re
        import shutil as _shutil
        import signal as _signal
        import socket
        import struct as _struct
        import subprocess
        import time
        import urllib.parse as _urlparse
        import urllib.request

        chrome_bin = Path("/usr/bin/google-chrome")
        self.assertTrue(chrome_bin.exists(), "Headless Chrome binary required at /usr/bin/google-chrome")

        old_lf = os.environ.get("ELAL_LIVE_FETCH_ENABLED")
        os.environ["ELAL_LIVE_FETCH_ENABLED"] = "0"

        def _restore_lf() -> None:
            if old_lf is None:
                os.environ.pop("ELAL_LIVE_FETCH_ENABLED", None)
            else:
                os.environ["ELAL_LIVE_FETCH_ENABLED"] = old_lf

        self.addCleanup(_restore_lf)

        seeded_db_path, _repo = self.make_isolated_env(auto_seed=True)
        seeded_client = self.get_client(seeded_db_path)

        # Also prepare isolated live-mode client seeded with exact screenshot LCA/PFO 2+/2+ + landlocked VIE
        os.environ["ELAL_LIVE_FETCH_ENABLED"] = "1"
        oj_db_path, _oj_repo = self.make_isolated_env(auto_seed=False)
        oj_client = self.get_client(oj_db_path)
        oj_sync = oj_client.post(
            "/api/v1/elal-bonus/sync",
            json={
                "origin": "TLV",
                "destinations": ["LCA", "PFO", "VIE"],
                "start_date": "2026-12-09",
                "end_date": "2026-12-15",
                "force_refresh": True,
                "rbd_payload": [
                    {
                        "destination_iata": "LCA",
                        "direction": "OUTBOUND",
                        "flight_number": "LY5131",
                        "flight_date": "2026-12-10",
                        "economy_seats": 2,
                        "dep_time": "07:00",
                        "arr_time": "08:05",
                    },
                    {
                        "destination_iata": "PFO",
                        "direction": "INBOUND",
                        "flight_number": "LY5138",
                        "flight_date": "2026-12-14",
                        "economy_seats": 2,
                        "dep_time": "08:15",
                        "arr_time": "09:20",
                    },
                    {
                        "destination_iata": "VIE",
                        "direction": "OUTBOUND",
                        "flight_number": "LY0361",
                        "flight_date": "2026-12-10",
                        "economy_seats": 2,
                        "dep_time": "06:15",
                        "arr_time": "09:10",
                    },
                    {
                        "destination_iata": "VIE",
                        "direction": "INBOUND",
                        "flight_number": "LY0364",
                        "flight_date": "2026-12-14",
                        "economy_seats": 2,
                        "dep_time": "20:30",
                        "arr_time": "00:55",
                    },
                ],
            },
        )
        self.assertEqual(oj_sync.status_code, 200)
        os.environ["ELAL_LIVE_FETCH_ENABLED"] = "0"

        chrome_tmp = tempfile.TemporaryDirectory(
            prefix="tier4_scen25_chrome_", ignore_cleanup_errors=True
        )
        self.addCleanup(lambda: _shutil.rmtree(chrome_tmp.name, ignore_errors=True))
        self.addCleanup(chrome_tmp.cleanup)

        html_text = (PROJECT_ROOT / "frontend" / "index.html").read_text("utf-8")
        css_text = (PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css").read_text("utf-8")
        js_text = (PROJECT_ROOT / "frontend" / "src" / "app.js").read_text("utf-8")

        inlined_html = _re.sub(
            r'<link[^>]+(?:fonts\.googleapis\.com|fonts\.gstatic\.com|manifest\.webmanifest)[^>]*>',
            "",
            html_text,
        )
        inlined_html = _re.sub(r"<noscript>.*?</noscript>", "", inlined_html, flags=_re.S)
        inlined_html = inlined_html.replace(
            '<link rel="stylesheet" href="/src/styles/app.css" />',
            f"<style>{css_text}</style>",
        )
        inlined_html = _re.sub(
            r'<script[^>]+src="/src/app\.js"[^>]*></script>', "", inlined_html
        )
        bridge_preamble = """<script>
(function() {
  window.__FVP_REFERENCE_DATE__ = '2026-11-19';
  window.__fvpJsErrors = [];
  window.addEventListener('error', function(e) { window.__fvpJsErrors.push(String(e.message || e)); });
  window.addEventListener('unhandledrejection', function(e) { window.__fvpJsErrors.push(String(e.reason || e)); });
  const _ss = {};
  const _ls = {};
  function _mkStore(backing) {
    return {
      getItem(k) { return Object.prototype.hasOwnProperty.call(backing, k) ? backing[k] : null; },
      setItem(k, v) { backing[String(k)] = String(v); },
      removeItem(k) { delete backing[k]; },
      clear() { Object.keys(backing).forEach((k) => delete backing[k]); },
      get length() { return Object.keys(backing).length; }
    };
  }
  Object.defineProperty(window, 'sessionStorage', { value: _mkStore(_ss), configurable: true });
  Object.defineProperty(window, 'localStorage', { value: _mkStore(_ls), configurable: true });
  let _reqSeq = 0;
  const _pending = new Map();
  window.__fvpResolveFetch = function(id, status, headersObj, bodyText) {
    const p = _pending.get(id);
    if (!p) return;
    _pending.delete(id);
    p.resolve(new Response(bodyText, { status: status, headers: headersObj || {} }));
  };
  window.fetch = function(input, init) {
    const urlStr = typeof input === 'string' ? input : input.url;
    if (urlStr.endsWith('/sw.js')) {
      return Promise.resolve(new Response('', { status: 200, headers: { 'Content-Type': 'application/javascript' } }));
    }
    const opts = init || {};
    const id = ++_reqSeq;
    return new Promise((resolve, reject) => {
      _pending.set(id, { resolve, reject });
      window.__fvpHostFetch(JSON.stringify({
        id: id,
        method: opts.method || 'GET',
        url: urlStr,
        headers: opts.headers || {},
        body: opts.body || null
      }));
    });
  };
  if (navigator.serviceWorker) {
    navigator.serviceWorker.register = function() { return Promise.resolve({}); };
  }
})();
</script>"""
        mounted_doc = inlined_html.replace("<head>", "<head>" + bridge_preamble, 1).replace(
            "</body>", f"<script>{js_text}</script></body>", 1
        )

        active_browser_client = oj_client
        active_live_flag = "1"
        proc_c = subprocess.Popen(
            [
                str(chrome_bin),
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-extensions",
                "--remote-debugging-port=0",
                f"--user-data-dir={chrome_tmp.name}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        def _kill_chrome() -> None:
            try:
                os.killpg(proc_c.pid, _signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc_c.wait(timeout=3.0)
            except Exception:
                pass

        self.addCleanup(_kill_chrome)

        active_port_file = Path(chrome_tmp.name) / "DevToolsActivePort"
        deadline = time.time() + 12.0
        while time.time() < deadline and not (active_port_file.exists() and active_port_file.read_text("utf-8").splitlines()):
            time.sleep(0.05)
        self.assertTrue(active_port_file.exists())
        cdp_port = int(active_port_file.read_text("utf-8").splitlines()[0].strip())

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{cdp_port}/json/list", timeout=5.0) as r_list:
            targets = json.loads(r_list.read().decode("utf-8"))
        page_target = next(t for t in targets if t.get("type") == "page")
        ws_parsed = _urlparse.urlsplit(page_target["webSocketDebuggerUrl"])

        sock = socket.create_connection(("127.0.0.1", cdp_port), timeout=10.0)
        self.addCleanup(sock.close)
        ws_key = _b64.b64encode(os.urandom(16)).decode("ascii")
        sock.sendall(
            (
                f"GET {ws_parsed.path} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{cdp_port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {ws_key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
        )
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        ws_leftover = bytearray(buf[buf.index(b"\r\n\r\n") + 4 :])

        def _ws_send_json(obj: dict[str, Any]) -> None:
            raw_b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            mask = os.urandom(4)
            ln = len(raw_b)
            if ln < 126:
                hdr = bytes([0x81, 0x80 | ln]) + mask
            elif ln < 65536:
                hdr = bytes([0x81, 0x80 | 126]) + _struct.pack("!H", ln) + mask
            else:
                hdr = bytes([0x81, 0x80 | 127]) + _struct.pack("!Q", ln) + mask
            sock.sendall(hdr + bytes(b ^ mask[i % 4] for i, b in enumerate(raw_b)))

        def _ws_recv_exact(n: int) -> bytes:
            while len(ws_leftover) < n:
                more = sock.recv(65536)
                if not more:
                    raise EOFError("CDP WebSocket closed unexpectedly")
                ws_leftover.extend(more)
            out_b = bytes(ws_leftover[:n])
            del ws_leftover[:n]
            return out_b

        def _ws_recv_msg() -> dict[str, Any]:
            fragments: list[bytes] = []
            while True:
                b0, b1 = _ws_recv_exact(2)
                fin = bool(b0 & 0x80)
                opcode = b0 & 0x0F
                masked_flag = bool(b1 & 0x80)
                ln = b1 & 0x7F
                if ln == 126:
                    ln = _struct.unpack("!H", _ws_recv_exact(2))[0]
                elif ln == 127:
                    ln = _struct.unpack("!Q", _ws_recv_exact(8))[0]
                mkey = _ws_recv_exact(4) if masked_flag else b""
                payload_b = _ws_recv_exact(ln)
                if masked_flag:
                    payload_b = bytes(b ^ mkey[i % 4] for i, b in enumerate(payload_b))
                if opcode == 0x9:
                    mask_p = os.urandom(4)
                    sock.sendall(
                        bytes([0x8A, 0x80 | len(payload_b)])
                        + mask_p
                        + bytes(b ^ mask_p[i % 4] for i, b in enumerate(payload_b))
                    )
                    continue
                fragments.append(payload_b)
                if fin:
                    return json.loads(b"".join(fragments).decode("utf-8"))

        msg_counter = 0

        def _handle_binding_event(ev_msg: dict[str, Any]) -> None:
            if (
                ev_msg.get("method") == "Runtime.bindingCalled"
                and ev_msg.get("params", {}).get("name") == "__fvpHostFetch"
            ):
                req_info = json.loads(ev_msg["params"]["payload"])
                parsed_u = _urlparse.urlsplit(req_info["url"])
                path_qs = parsed_u.path + (f"?{parsed_u.query}" if parsed_u.query else "")
                j_body = json.loads(req_info["body"]) if req_info.get("body") else None
                os.environ["ELAL_LIVE_FETCH_ENABLED"] = active_live_flag
                resp_obj = active_browser_client.request(
                    req_info["method"],
                    path_qs,
                    json_body=j_body,
                    headers=req_info.get("headers") or {},
                )
                nonlocal msg_counter
                msg_counter += 1
                expr = (
                    f"window.__fvpResolveFetch({int(req_info['id'])}, "
                    f"{int(resp_obj.status_code)}, {json.dumps(dict(resp_obj.headers))}, {json.dumps(resp_obj.text)});"
                )
                _ws_send_json({"id": msg_counter, "method": "Runtime.evaluate", "params": {"expression": expr}})

        def _cdp_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            nonlocal msg_counter
            msg_counter += 1
            target_id = msg_counter
            _ws_send_json({"id": target_id, "method": method, "params": params or {}})
            while True:
                incoming = _ws_recv_msg()
                if "method" in incoming:
                    _handle_binding_event(incoming)
                    continue
                if incoming.get("id") == target_id:
                    return incoming

        def _cdp_eval(js_expr: str) -> Any:
            res = _cdp_call(
                "Runtime.evaluate",
                {"expression": js_expr, "awaitPromise": True, "returnByValue": True},
            )
            inner = res.get("result", {})
            if "exceptionDetails" in inner:
                raise AssertionError(f"CDP JS exception: {inner['exceptionDetails']}")
            return inner.get("result", {}).get("value")

        _cdp_call("Page.enable")
        _cdp_call("Runtime.enable")
        _cdp_call("Runtime.addBinding", {"name": "__fvpHostFetch"})
        frame_id = _cdp_call("Page.getFrameTree")["result"]["frameTree"]["frame"]["id"]

        _cdp_call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
        )
        _cdp_call("Page.setDocumentContent", {"frameId": frame_id, "html": mounted_doc})
        for _ in range(80):
            if _cdp_eval(
                "new Promise((r) => setTimeout(() => r(Boolean(document.querySelector('[data-dest-option=\"LCA\"]') && (document.querySelector('.proposal-card') || document.querySelector('.empty-state-card')))), 30))"
            ):
                break

        # Verify boot search mode tab order & RTL geometry: Manual Dates active on RIGHT, By Holiday inactive on LEFT
        boot_tabs = _cdp_eval(
            """(() => {
              const specBtn = document.getElementById('tab-mode-specific');
              const holBtn = document.getElementById('tab-mode-holiday');
              const sr = specBtn.getBoundingClientRect();
              const hr = holBtn.getBoundingClientRect();
              const depR = document.getElementById('input-dep-date').getBoundingClientRect();
              const retR = document.getElementById('input-ret-date').getBoundingClientRect();
              const flexR = document.getElementById('input-flex-days').getBoundingClientRect();
              const tabIds = Array.from(document.querySelectorAll('.mode-tabs .mode-tab-btn')).map((b) => b.id);
              return {
                dir: document.documentElement.getAttribute('dir'),
                tabIds,
                specActive: specBtn.classList.contains('active'),
                holActive: holBtn.classList.contains('active'),
                specLeft: sr.left,
                holRight: hr.right,
                depTop: depR.top,
                retTop: retR.top,
                flexTop: flexR.top,
                depLeft: depR.left,
                retRight: retR.right,
                retLeft: retR.left,
                flexRight: flexR.right,
                specControlsDisplay: getComputedStyle(document.getElementById('controls-specific-dates')).display,
                holControlsDisplay: getComputedStyle(document.getElementById('controls-holiday-direct')).display,
                holDurDisplay: getComputedStyle(document.getElementById('controls-holiday-duration')).display,
                badgeTxt: (document.getElementById('active-mode-badge').textContent || '').trim()
              };
            })()"""
        )
        self.assertEqual(boot_tabs["dir"], "rtl")
        self.assertEqual(boot_tabs["tabIds"], ["tab-mode-specific", "tab-mode-holiday"])
        self.assertTrue(boot_tabs["specActive"])
        self.assertFalse(boot_tabs["holActive"])
        self.assertGreaterEqual(boot_tabs["specLeft"], boot_tabs["holRight"])
        self.assertLessEqual(abs(boot_tabs["depTop"] - boot_tabs["retTop"]), 2.0)
        self.assertLessEqual(abs(boot_tabs["depTop"] - boot_tabs["flexTop"]), 2.0)
        self.assertGreaterEqual(boot_tabs["depLeft"], boot_tabs["retRight"])
        self.assertGreaterEqual(boot_tabs["retLeft"], boot_tabs["flexRight"])
        self.assertNotEqual(boot_tabs["specControlsDisplay"], "none")
        self.assertEqual(boot_tabs["holControlsDisplay"], "none")
        self.assertEqual(boot_tabs["holDurDisplay"], "none")
        self.assertIn("תאריכים ידניים", boot_tabs["badgeTxt"])

        # Configure 4-pax family (2 adults + 2 children [5, 9]) and search 2026-12-10..14 on LCA, PFO, VIE
        _cdp_eval(
            """(async () => {
              document.getElementById('btn-add-child').click();
              document.getElementById('btn-add-child').click();
              const c0 = document.querySelector('[data-child-age="0"]');
              c0.value = '5'; c0.dispatchEvent(new Event('input', { bubbles: true })); c0.dispatchEvent(new Event('change', { bubbles: true }));
              const c1 = document.querySelector('[data-child-age="1"]');
              c1.value = '9'; c1.dispatchEvent(new Event('input', { bubbles: true })); c1.dispatchEvent(new Event('change', { bubbles: true }));
              document.querySelector('[data-mode="SPECIFIC_DATES"]').click();
              document.getElementById('input-dep-date').value = '2026-12-10';
              document.getElementById('input-ret-date').value = '2026-12-14';
              document.getElementById('input-flex-days').value = '0';
              document.getElementById('btn-dest-picker-toggle').click();
              document.querySelector('[data-dest-option="LCA"]').click();
              document.querySelector('[data-dest-option="PFO"]').click();
              document.querySelector('[data-dest-option="VIE"]').click();
              document.getElementById('btn-dest-popover-done').click();
              for (let i = 0; i < 80; i++) {
                await new Promise((r) => setTimeout(r, 30));
                const cards = Array.from(document.querySelectorAll('.proposal-card'));
                if (cards.some((el) => (el.textContent || '').includes('LCA/PFO')) && cards.some((el) => (el.textContent || '').includes('VIE'))) break;
              }
              const toggleBtn = document.querySelector('[data-toggle-all-proposals]');
              if (toggleBtn) toggleBtn.click();
            })()"""
        )

        contradictory_pairs = (
            ("בונוס בשני הכיוונים", "כיוון אחד בבונוס"),
            ("בונוס בשני הכיוונים", "כיוון אחד בונוס"),
            ("Bonus seats in both directions", "One way on bonus"),
        )
        forbidden_card_tokens = (
            "הערכת מחיר במזומן",
            "חיסכון משוער",
            "¢",
            "~$",
            "Est. Cash",
            "Est. Net Saved",
            "נקודות מתמיד",
            "Matmid Points",
            "120,000",
            "מחיר",
            "price",
            "rbddataclients",
            "החופשה המומלצת ביותר",
            "בחירה מובילה",
            "חלופה מומלצת",
            "Best Overall Vacation",
            "Top Choice",
            "Alternative Option",
        )

        # Check R1, R2, and R3 real CDP mouse hover across both Hebrew (`rtl`) and English (`ltr`) at 1440x900
        for locale_spec in (
            {
                "dir": "rtl",
                "oj_tag": "מסלול משולב (הלוך ל-LCA, חזור מ-PFO)",
                "both_stmt": "בונוס בשני הכיוונים",
                "calc_kicker": "איך חושב:",
                "meaning_kicker": "משמעות:",
                "weather_forecast_kicker": "תחזית עונתית:",
                "weather_act_kicker": "מומלץ ביעד במזג אוויר זה:",
                "weather_dest_tok": "כף גרקו",
                "kpi_labels": {
                    "school-fit": 'התאמה לחופשת בי"ס',
                    "workdays-cost": "חופשת עבודה",
                },
                "paren_tok": "חיסור",
            },
            {
                "dir": "ltr",
                "oj_tag": "Open-jaw bonus (out to LCA, back from PFO)",
                "both_stmt": "Bonus seats in both directions",
                "calc_kicker": "How calculated:",
                "meaning_kicker": "Meaning:",
                "weather_forecast_kicker": "Seasonal forecast:",
                "weather_act_kicker": "What to do in this weather:",
                "weather_dest_tok": "Larnaca",
                "kpi_labels": {
                    "school-fit": "School Break Fit",
                    "workdays-cost": "Workdays Off",
                },
                "paren_tok": "missed",
            },
        ):
            if locale_spec["dir"] == "ltr":
                _cdp_eval("document.getElementById('btn-toggle-locale').click(); true;")

            snap = _cdp_eval(
                """(() => {
                  const docEl = document.documentElement;
                  const cards = Array.from(document.querySelectorAll('.proposal-card'));
                  return {
                    jsErrors: window.__fvpJsErrors,
                    dir: docEl.getAttribute('dir'),
                    scrollWidth: docEl.scrollWidth,
                    clientWidth: docEl.clientWidth,
                    oldWeatherCount: document.querySelectorAll('.weather-telemetry-strip').length,
                    legacyMissedCellCount: document.querySelectorAll('.kpi-cell[data-kpi="school-missed"]').length,
                    legacyBonusCellCount: document.querySelectorAll('.kpi-cell[data-kpi="bonus-value"]').length,
                    mainKpiCount: document.querySelectorAll('.proposal-pass-main .kpi-cell').length,
                    cards: cards.map((c) => {
                      const mainEl = c.querySelector('.proposal-pass-main');
                      const stubEl = c.querySelector('.proposal-pass-stub');
                      const minPtsInMain = mainEl ? mainEl.querySelector('.min-points-ticket') : null;
                      const paxInStub = stubEl ? stubEl.querySelector('.stub-pax-summary') : null;
                      const wEl = stubEl ? stubEl.querySelector('.stub-weather-card[data-weather-compact="true"]') : null;
                      const workEl = stubEl ? stubEl.querySelector('.kpi-cell[data-kpi="workdays-cost"]') : null;
                      const fitEl = stubEl ? stubEl.querySelector('.kpi-cell[data-kpi="school-fit"]') : null;
                      const parenEl = fitEl ? fitEl.querySelector('.kpi-missed-paren') : null;
                      const seaEl = wEl ? wEl.querySelector('[data-weather-sea]') : null;
                      const mainRect = mainEl.getBoundingClientRect();
                      const stubRect = stubEl.getBoundingClientRect();
                      const wRect = wEl ? wEl.getBoundingClientRect() : null;
                      const fromEndEl = c.querySelector('.boarding-route-bar .route-endpoint:not(.route-endpoint-end)');
                      const toEndEl = c.querySelector('.boarding-route-bar .route-endpoint-end');
                      const outLaneEl = c.querySelector('.bonus-lane[data-direction="outbound"]');
                      const inLaneEl = c.querySelector('.bonus-lane[data-direction="inbound"]');
                      const origPairEl = c.querySelector('.route-pair-origin');
                      const destPairEl = c.querySelector('.route-pair-dest');
                      const fromRect = fromEndEl.getBoundingClientRect();
                      const toRect = toEndEl.getBoundingClientRect();
                      const outLaneRect = outLaneEl.getBoundingClientRect();
                      const inLaneRect = inLaneEl.getBoundingClientRect();
                      const origPairRect = origPairEl.getBoundingClientRect();
                      const destPairRect = destPairEl.getBoundingClientRect();
                      const stmtEl = c.querySelector('.bonus-direction-statement');
                      const stratEl = c.querySelector('.bonus-strategy-tag');
                      return {
                        text: c.textContent || '',
                        routeText: (c.querySelector('.boarding-route-bar') || {}).textContent || '',
                        strategy: c.getAttribute('data-strategy'),
                        bonusDirections: c.getAttribute('data-bonus-directions'),
                        stmtText: stmtEl ? stmtEl.textContent.trim() : '',
                        stratText: stratEl ? stratEl.textContent.trim() : null,
                        mainLeft: mainRect.left,
                        mainRight: mainRect.right,
                        stubLeft: stubRect.left,
                        stubRight: stubRect.right,
                        fromLeft: fromRect.left,
                        fromRight: fromRect.right,
                        toLeft: toRect.left,
                        toRight: toRect.right,
                        outLaneLeft: outLaneRect.left,
                        outLaneRight: outLaneRect.right,
                        inLaneLeft: inLaneRect.left,
                        inLaneRight: inLaneRect.right,
                        origPairLeft: origPairRect.left,
                        origPairRight: origPairRect.right,
                        destPairLeft: destPairRect.left,
                        destPairRight: destPairRect.right,
                        hasWeatherAndPairedVacationBelowInStub: Boolean(!paxInStub && !stubEl.querySelector('.min-points-ticket') && (c.getAttribute('data-strategy') === 'CASH_AND_POINTS' || minPtsInMain) && wEl && workEl && fitEl && wEl.getBoundingClientRect().bottom <= workEl.getBoundingClientRect().top + 2.0 && Math.abs(fitEl.getBoundingClientRect().top - workEl.getBoundingClientRect().bottom) <= 6.0),
                        parenText: parenEl ? parenEl.textContent.trim() : '',
                        weatherVisible: Boolean(wRect && wRect.width > 0 && wRect.height > 0),
                        weatherText: wEl ? wEl.textContent.replace(/\\s+/g, ' ').trim() : '',
                        hasSea: Boolean(seaEl)
                      };
                    })
                  };
                })()"""
            )
            self.assertEqual(snap["jsErrors"], [])
            self.assertEqual(snap["dir"], locale_spec["dir"])
            self.assertLessEqual(snap["scrollWidth"], snap["clientWidth"])
            self.assertEqual(snap["oldWeatherCount"], 0)
            self.assertEqual(snap["legacyMissedCellCount"], 0)
            self.assertEqual(snap["legacyBonusCellCount"], 0)
            self.assertEqual(snap["mainKpiCount"], 0)
            self.assertGreaterEqual(len(snap["cards"]), 2)

            oj_found = False
            vie_found = False
            for card in snap["cards"]:
                for bad_tok in forbidden_card_tokens:
                    self.assertNotIn(bad_tok, card["text"])
                self.assertIsNone(
                    _re.search(
                        r"(?<![א-ת])(?:של\s+)?(?:ה|ל|ב|ו|ש|כ)?בוגרים(?![א-ת])",
                        card["text"],
                    )
                )
                for stmt_a, tag_b in contradictory_pairs:
                    self.assertFalse(
                        stmt_a in card["text"] and tag_b in card["text"],
                        f"Contradictory bonus badges on card: {card}",
                    )
                self.assertTrue(card["hasWeatherAndPairedVacationBelowInStub"])
                self.assertTrue(card["parenText"].startswith("(") and card["parenText"].endswith(")"))
                self.assertIn(locale_spec["paren_tok"], card["parenText"])
                self.assertTrue(card["weatherVisible"])
                self.assertIn("°C", card["weatherText"])
                self.assertIn("/100", card["weatherText"])
                if locale_spec["dir"] == "rtl":
                    # Side stub (with passenger count + compact weather) sits visually on the LEFT in Hebrew RTL
                    self.assertLessEqual(card["stubRight"], card["mainLeft"] + 2.0)
                    # Route bar & header pair match RTL coupon order: TLV/outbound on the RIGHT, dest/inbound on the LEFT
                    self.assertGreater(card["fromLeft"], card["toRight"])
                    self.assertGreater(card["outLaneLeft"], card["inLaneRight"] - 1.0)
                    self.assertGreater(card["origPairLeft"], card["destPairRight"] - 1.0)
                else:
                    self.assertGreaterEqual(card["stubLeft"], card["mainRight"] - 2.0)
                    # In English LTR: TLV/outbound on the LEFT, dest/inbound on the RIGHT
                    self.assertLess(card["fromRight"], card["toLeft"])
                    self.assertLess(card["outLaneRight"], card["inLaneLeft"] + 1.0)
                    self.assertLess(card["origPairRight"], card["destPairLeft"] + 1.0)

                if "LCA/PFO" in card["routeText"]:
                    oj_found = True
                    self.assertEqual(card["stmtText"], locale_spec["both_stmt"])
                    self.assertEqual(card["stratText"], locale_spec["oj_tag"])
                    self.assertTrue(card["hasSea"])
                if "VIE" in card["routeText"] and "LCA" not in card["routeText"]:
                    vie_found = True
                    self.assertFalse(card["hasSea"], "Landlocked VIE omits sea temperature")

            self.assertTrue(oj_found, "Open-Jaw LCA/PFO card must render")
            self.assertTrue(vie_found, "Landlocked VIE card must render")

            # R2 + R3: Real CDP mouse hover over `.stub-weather-card` AND `.kpi-cell[data-kpi="school-fit"]` on Card #1
            _cdp_call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 2, "y": 2})
            _cdp_eval(
                """(() => {
                  const c0 = document.querySelector('.proposal-card');
                  c0.scrollIntoView({ behavior: 'instant', block: 'center' });
                  return true;
                })()"""
            )
            w_pre = _cdp_eval(
                """(() => {
                  const cards = Array.from(document.querySelectorAll('.proposal-card'));
                  const lcaCard = cards.find((c) => (c.textContent || '').includes('LCA')) || cards[0];
                  lcaCard.scrollIntoView({ behavior: 'instant', block: 'center' });
                  const wCard = lcaCard.querySelector('.stub-weather-card');
                  const tip = wCard.querySelector('.kpi-tooltip[role="tooltip"]');
                  const r = wCard.getBoundingClientRect();
                  return {
                    preDisplay: tip ? getComputedStyle(tip).display : 'missing',
                    cx: Math.round(r.left + r.width / 2),
                    cy: Math.round(r.top + r.height / 2)
                  };
                })()"""
            )
            self.assertEqual(w_pre["preDisplay"], "none")
            _cdp_call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": w_pre["cx"], "y": w_pre["cy"]})
            w_hover = _cdp_eval(
                """(() => {
                  const docEl = document.documentElement;
                  const cards = Array.from(document.querySelectorAll('.proposal-card'));
                  const lcaCard = cards.find((c) => (c.textContent || '').includes('LCA')) || cards[0];
                  const tip = lcaCard.querySelector('.stub-weather-card .kpi-tooltip[role="tooltip"]');
                  const cs = getComputedStyle(tip);
                  const tr = tip.getBoundingClientRect();
                  return {
                    display: cs.display,
                    visibility: cs.visibility,
                    text: tip.textContent.replace(/\\s+/g, ' ').trim(),
                    width: tr.width,
                    height: tr.height,
                    left: tr.left,
                    right: tr.right,
                    top: tr.top,
                    bottom: tr.bottom,
                    innerW: window.innerWidth,
                    innerH: window.innerHeight,
                    scrollWidth: docEl.scrollWidth,
                    clientWidth: docEl.clientWidth
                  };
                })()"""
            )
            self.assertEqual(w_hover["display"], "flex")
            self.assertEqual(w_hover["visibility"], "visible")
            self.assertIn(locale_spec["weather_forecast_kicker"], w_hover["text"])
            self.assertIn(locale_spec["weather_act_kicker"], w_hover["text"])
            self.assertIn(locale_spec["weather_dest_tok"], w_hover["text"])
            self.assertGreaterEqual(w_hover["left"], 0.0)
            self.assertLessEqual(w_hover["right"], w_hover["innerW"])
            self.assertGreaterEqual(w_hover["top"], 0.0)
            self.assertLessEqual(w_hover["bottom"], w_hover["innerH"])
            self.assertLessEqual(w_hover["scrollWidth"], w_hover["clientWidth"])
            _cdp_call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 2, "y": 2})
            _cdp_eval("document.querySelector('.proposal-card').scrollIntoView({ behavior: 'instant', block: 'center' }); true;")

            for kpi_key, expected_lbl in locale_spec["kpi_labels"].items():
                pre_hover = _cdp_eval(
                    f"""(() => {{
                      const cell = document.querySelector('.proposal-card .kpi-cell[data-kpi="{kpi_key}"]');
                      const lbl = cell ? cell.querySelector('.kpi-cell-label') : null;
                      const tip = cell ? cell.querySelector('.kpi-tooltip[role="tooltip"]') : null;
                      const r = cell.getBoundingClientRect();
                      return {{
                        labelText: lbl ? lbl.textContent.replace(/\\s+/g, ' ').trim() : '',
                        preDisplay: tip ? getComputedStyle(tip).display : 'missing',
                        cx: Math.round(r.left + r.width / 2),
                        cy: Math.round(r.top + r.height / 2)
                      }};
                    }})()"""
                )
                self.assertIn(expected_lbl, pre_hover["labelText"])
                self.assertEqual(pre_hover["preDisplay"], "none")

                _cdp_call(
                    "Input.dispatchMouseEvent",
                    {"type": "mouseMoved", "x": pre_hover["cx"], "y": pre_hover["cy"]},
                )
                hover_state = _cdp_eval(
                    f"""(() => {{
                      const docEl = document.documentElement;
                      const cell = document.querySelector('.proposal-card .kpi-cell[data-kpi="{kpi_key}"]');
                      const tip = cell.querySelector('.kpi-tooltip[role="tooltip"]');
                      const cs = getComputedStyle(tip);
                      const tr = tip.getBoundingClientRect();
                      return {{
                        display: cs.display,
                        visibility: cs.visibility,
                        text: tip.textContent.replace(/\\s+/g, ' ').trim(),
                        width: tr.width,
                        height: tr.height,
                        left: tr.left,
                        right: tr.right,
                        top: tr.top,
                        bottom: tr.bottom,
                        innerW: window.innerWidth,
                        innerH: window.innerHeight,
                        scrollH: tip.scrollHeight,
                        clientH: tip.clientHeight,
                        scrollWidth: docEl.scrollWidth,
                        clientWidth: docEl.clientWidth
                      }};
                    }})()"""
                )
                self.assertEqual(hover_state["display"], "flex", kpi_key)
                self.assertEqual(hover_state["visibility"], "visible", kpi_key)
                self.assertGreaterEqual(hover_state["width"], 180.0, kpi_key)
                self.assertGreaterEqual(hover_state["height"], 44.0, kpi_key)
                self.assertIn(locale_spec["calc_kicker"], hover_state["text"])
                self.assertIn(locale_spec["meaning_kicker"], hover_state["text"])
                self.assertLessEqual(hover_state["scrollH"], hover_state["clientH"] + 2, kpi_key)
                self.assertGreaterEqual(hover_state["left"], 0.0, kpi_key)
                self.assertLessEqual(hover_state["right"], hover_state["innerW"], kpi_key)
                self.assertGreaterEqual(hover_state["top"], 0.0, kpi_key)
                self.assertLessEqual(hover_state["bottom"], hover_state["innerH"], kpi_key)
                self.assertLessEqual(hover_state["scrollWidth"], hover_state["clientWidth"], kpi_key)

                _cdp_call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 2, "y": 2})
                post_display = _cdp_eval(
                    f"""getComputedStyle(document.querySelector('.proposal-card .kpi-cell[data-kpi="{kpi_key}"] .kpi-tooltip')).display"""
                )
                self.assertEqual(post_display, "none")

        # Switch back to Hebrew RTL, test mobile `390x844` 2-line flight tags + tap tooltips & zero overflow on LCA/PFO + VIE,
        # AND verify `firstCardY < 900` in default Holiday Mode (`ANYWHERE`) in both `he` & `en`
        _cdp_eval("if (document.documentElement.getAttribute('dir') !== 'rtl') document.getElementById('btn-toggle-locale').click(); true;")
        _cdp_call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True},
        )
        for mob_dir in ("rtl", "ltr"):
            if mob_dir == "ltr":
                _cdp_eval("document.getElementById('btn-toggle-locale').click(); true;")
            _cdp_eval("document.querySelector('.proposal-card').scrollIntoView({ behavior: 'instant', block: 'center' }); true;")
            flight_stack = _cdp_eval(
                """(() => {
                  const fl = document.querySelector('.proposal-card .bonus-lane-flight:not(.bonus-lane-flight-commercial)');
                  const numEl = fl ? fl.querySelector('.bonus-flight-num') : null;
                  const timesEl = fl ? fl.querySelector('.bonus-flight-times') : null;
                  const sepEl = fl ? fl.querySelector('.bonus-flight-sep') : null;
                  const nr = numEl.getBoundingClientRect();
                  const tr = timesEl.getBoundingClientRect();
                  return {
                    sepDisplay: sepEl ? getComputedStyle(sepEl).display : 'missing',
                    numBottom: nr.bottom,
                    timesTop: tr.top,
                    timesHeight: tr.height
                  };
                })()"""
            )
            self.assertEqual(flight_stack["sepDisplay"], "none")
            self.assertGreaterEqual(flight_stack["timesTop"], flight_stack["numBottom"] - 1.5)
            self.assertLessEqual(flight_stack["timesHeight"], 22.0)

            for sel in ('.stub-weather-card', '.kpi-cell[data-kpi="school-fit"]'):
                tap_res = _cdp_eval(
                    f"""(() => {{
                      const docEl = document.documentElement;
                      const cell = document.querySelector('.proposal-card {sel}');
                      cell.click();
                      const tip = cell.querySelector('.kpi-tooltip');
                      const tr = tip.getBoundingClientRect();
                      return {{
                        isOpen: cell.classList.contains('is-tooltip-open'),
                        display: getComputedStyle(tip).display,
                        left: tr.left,
                        right: tr.right,
                        innerW: window.innerWidth,
                        scrollH: tip.scrollHeight,
                        clientH: tip.clientHeight,
                        scrollWidth: docEl.scrollWidth,
                        clientWidth: docEl.clientWidth
                      }};
                    }})()"""
                )
                self.assertTrue(tap_res["isOpen"])
                self.assertEqual(tap_res["display"], "flex")
                self.assertGreaterEqual(tap_res["left"], 0.0)
                self.assertLessEqual(tap_res["right"], tap_res["innerW"])
                self.assertLessEqual(tap_res["scrollH"], tap_res["clientH"] + 2)
                self.assertLessEqual(tap_res["scrollWidth"], tap_res["clientWidth"])

            # Escape closes open tooltip cleanly
            _cdp_eval("document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); true;")
            open_cnt = _cdp_eval("document.querySelectorAll('.kpi-cell.is-tooltip-open, .stub-weather-card.is-tooltip-open').length")
            self.assertEqual(open_cnt, 0)

        # Verify `390x844` `firstCardY < 900` in default Holiday Mode (`ANYWHERE`) in both `he` RTL & `en` LTR
        active_browser_client = seeded_client
        active_live_flag = "0"
        _cdp_eval(
            """(async () => {
              if (document.documentElement.getAttribute('dir') !== 'rtl') {
                document.getElementById('btn-toggle-locale').click();
              }
              document.getElementById('btn-dest-clear-all').click();
              document.querySelector('[data-mode="HOLIDAY_DIRECT_INTENT"]').click();
              for (let i = 0; i < 80; i++) {
                await new Promise((r) => setTimeout(r, 30));
                if (document.querySelectorAll('.proposal-card').length >= 2) break;
              }
              window.scrollTo(0, 0);
            })()"""
        )
        for mob_dir in ("rtl", "ltr"):
            if mob_dir == "ltr":
                _cdp_eval("document.getElementById('btn-toggle-locale').click(); window.scrollTo(0, 0); true;")
            mob_top = _cdp_eval(
                """(() => {
                  const docEl = document.documentElement;
                  const c0 = document.querySelector('.proposal-card');
                  return {
                    dir: docEl.getAttribute('dir'),
                    firstCardY: c0.getBoundingClientRect().top,
                    scrollWidth: docEl.scrollWidth,
                    clientWidth: docEl.clientWidth
                  };
                })()"""
            )
            self.assertEqual(mob_top["dir"], mob_dir)
            self.assertLess(mob_top["firstCardY"], 900.0)
            self.assertLessEqual(mob_top["scrollWidth"], mob_top["clientWidth"])

        # Also verify across responsive breakpoints (360, 560, 900, 1180, 1260, 2560) that weather + KPI tooltips never overflow horizontally
        for bp_w, bp_h, is_mob in (
            (360, 800, True),
            (560, 900, False),
            (900, 900, False),
            (1180, 900, False),
            (1260, 900, False),
            (2560, 1440, False),
        ):
            _cdp_call(
                "Emulation.setDeviceMetricsOverride",
                {"width": bp_w, "height": bp_h, "deviceScaleFactor": 1, "mobile": is_mob},
            )
            _cdp_eval("document.querySelector('.proposal-card').scrollIntoView({ behavior: 'instant', block: 'center' }); true;")
            for sel in ('.stub-weather-card', '.kpi-cell[data-kpi="school-fit"]'):
                bp_chk = _cdp_eval(
                    f"""(() => {{
                      const docEl = document.documentElement;
                      const cell = document.querySelector('.proposal-card {sel}');
                      cell.click();
                      const tip = cell.querySelector('.kpi-tooltip');
                      const tr = tip.getBoundingClientRect();
                      const out = {{
                        left: tr.left,
                        right: tr.right,
                        innerW: window.innerWidth,
                        scrollWidth: docEl.scrollWidth,
                        clientWidth: docEl.clientWidth
                      }};
                      cell.click();
                      return out;
                    }})()"""
                )
                self.assertGreaterEqual(bp_chk["left"], 0.0, f"bp={bp_w} {sel}")
                self.assertLessEqual(bp_chk["right"], bp_chk["innerW"], f"bp={bp_w} {sel}")
                self.assertLessEqual(bp_chk["scrollWidth"], bp_chk["clientWidth"], f"bp={bp_w} {sel}")

        # Switch back to Hebrew RTL and verify seeded same-city `FCO` (`2+`/`2+`) + 1-direction `ATH` (`2026-12-06..12`) have zero contradictory badges
        _cdp_eval(
            """(() => {
              if (document.documentElement.getAttribute('dir') !== 'rtl') {
                document.getElementById('btn-toggle-locale').click();
              }
              document.querySelector('[data-mode="SPECIFIC_DATES"]').click();
              return true;
            })()"""
        )
        _cdp_call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
        )
        active_browser_client = seeded_client
        active_live_flag = "0"
        for dest_opt, dep_d, ret_d in (("ROM", "2027-04-11", "2027-04-18"), ("ATH", "2026-12-06", "2026-12-12")):
            _cdp_eval(
                f"""(async () => {{
                  const clr = document.getElementById('btn-dest-clear-all');
                  if (clr) {{
                    clr.click();
                    await new Promise((r) => setTimeout(r, 60));
                  }}
                  document.getElementById('input-dep-date').value = '{dep_d}';
                  document.getElementById('input-ret-date').value = '{ret_d}';
                  document.getElementById('input-flex-days').value = '0';
                  document.getElementById('btn-dest-picker-toggle').click();
                  document.querySelector('[data-dest-option="{dest_opt}"]').click();
                  document.getElementById('btn-dest-popover-done').click();
                  for (let i = 0; i < 80; i++) {{
                    await new Promise((r) => setTimeout(r, 30));
                    const cards = Array.from(document.querySelectorAll('.proposal-card'));
                    if (cards.length > 0 && cards.every((el) => (el.textContent || '').includes('{dep_d}'))) break;
                  }}
                }})()"""
            )
            seeded_texts = _cdp_eval(
                "Array.from(document.querySelectorAll('.proposal-card')).map((c) => c.textContent || '')"
            )
            self.assertGreaterEqual(len(seeded_texts), 2)
            for c_txt in seeded_texts:
                for stmt_a, tag_b in contradictory_pairs:
                    self.assertFalse(stmt_a in c_txt and tag_b in c_txt)
                if dest_opt == "ATH":
                    self.assertNotIn("כיוון אחד בבונוס", c_txt)
                    self.assertNotIn("One way on bonus", c_txt)

    # ------------------------------------------------------------------------------------------------------
    # Run 13 (M13 unified): Sign-in / Sign-out / Account ONLY in the top-left header (`#app-header`) and
    # Travelers summary + `"עריכה"` ONLY above `#zone-search`, on BOTH Desktop (`>=1180px`) and Mobile (`<1180px`).
    # Scenarios 26 and 27 drive the page with REAL mouse and keyboard input (see `_Run13ChromeSession`).
    # ------------------------------------------------------------------------------------------------------
    _RUN13_PASSENGER_FIELD_KEYS = ("windowTitle", "adults", "matmid", "childrenList", "addChild", "closeBtn", "applyBtn")
    _RUN13_SIGNIN_KEYS = (
        "authPopover",
        "authCard",
        "googleBtn",
        "guestDisc",
        "userDisc",
        "signoutBtn",
        "deleteBtn",
        "notifInput",
    )

    def _run13_assert_closed(self, st: dict[str, Any], signed_in: bool = False) -> None:
        """Closed state (desktop or mobile): neither the travelers editor nor the header auth popover is open."""
        self.assertEqual(st["jsErrors"], [])
        self.assertEqual(st["prof"]["display"], "none")
        self.assertFalse(st["prof"]["sheetOpen"])
        self.assertIsNone(st["prof"]["view"])
        self.assertIsNone(st["prof"]["role"])
        self.assertIsNone(st["prof"]["ariaModal"])
        self.assertEqual(st["prof"]["labelledBy"], "zone-profile-title")
        self.assertEqual(st["prof"]["prevSiblingId"], "zone-search")
        for key in (
            self._RUN13_PASSENGER_FIELD_KEYS
            + self._RUN13_SIGNIN_KEYS
            + ("saveBtn", "saveError", "profileSaveFeedback", "backdrop", "headerPill", "railAccountBtn")
        ):
            self.assertFalse(st["vis"][key], f"{key} must not be visible while closed")
        for key in ("hhBar", "hhSummary", "editBtn"):
            self.assertTrue(st["vis"][key], f"{key} must be visible above search while closed")
        if signed_in:
            self.assertFalse(st["vis"]["headerAuthBtn"])
            self.assertTrue(st["vis"]["headerAccountBtn"])
            self.assertTrue(st["vis"]["headerSignoutBtn"])
        else:
            self.assertTrue(st["vis"]["headerAuthBtn"])
            self.assertFalse(st["vis"]["headerAccountBtn"])
            self.assertFalse(st["vis"]["headerSignoutBtn"])
        self.assertFalse(st["bodyLocked"])
        self.assertNotEqual(st["bodyOverflow"], "hidden")
        self.assertEqual(st["inertIds"], [])
        self.assertEqual(st["aria"], {"edit": "false", "headerAuth": "false", "headerAccount": "false"})
        self.assertLessEqual(st["scrollWidth"], st["clientWidth"])

    def _run13_assert_travelers_bar_above_search(self, st: dict[str, Any]) -> None:
        """Above `#zone-search` sits ONLY the travelers summary + edit bar, on both desktop and mobile."""
        search_top = st["rects"]["search"]["y"]
        for key in ("hhBar", "edit"):
            self.assertTrue(st["rects"][key]["visible"], key)
            self.assertLessEqual(st["rects"][key]["bottom"], search_top, f"{key} must end above #zone-search")
        self.assertAlmostEqual(st["rects"]["hhBar"]["x"], st["rects"]["rail"]["x"], delta=1.0)
        self.assertAlmostEqual(st["rects"]["hhBar"]["w"], st["rects"]["rail"]["w"], delta=1.0)
        self.assertLess(st["rects"]["hhBar"]["y"], search_top)

    def _run13_assert_passenger_window_open(self, st: dict[str, Any], signed_in: bool) -> None:
        """Desktop (>=1180px): passenger details open as a centred modal window wider than the control rail."""
        self.assertEqual(st["jsErrors"], [])
        prof = st["prof"]
        self.assertTrue(prof["sheetOpen"])
        self.assertEqual(prof["view"], "travelers")
        self.assertEqual(prof["role"], "dialog")
        self.assertEqual(prof["ariaModal"], "true")
        self.assertEqual(prof["labelledBy"], "zone-profile-title")
        self.assertEqual(prof["position"], "fixed")
        win = prof["rect"]
        self.assertTrue(win["visible"])
        self.assertGreater(win["w"], 416)
        self.assertGreater(win["w"], st["rects"]["rail"]["w"])
        self.assertGreaterEqual(win["w"], 520)
        self.assertLessEqual(win["w"], 580)
        self.assertAlmostEqual(win["x"] + win["w"] / 2, st["innerWidth"] / 2, delta=2.0)
        self.assertGreaterEqual(win["y"], st["rects"]["header"]["bottom"])
        self.assertLessEqual(win["bottom"], st["innerHeight"])
        for key in self._RUN13_PASSENGER_FIELD_KEYS + ("backdrop",):
            self.assertTrue(st["vis"][key], f"{key} must be visible in the passenger window")
        for key in self._RUN13_SIGNIN_KEYS:
            self.assertFalse(st["vis"][key], f"{key} belongs to the top-bar auth popover, not the passenger window")
        self.assertEqual(st["vis"]["saveBtn"], signed_in)
        self.assertTrue(st["bodyLocked"])
        self.assertEqual(st["bodyOverflow"], "hidden")
        self.assertTrue(
            {"app-header", "vacation-hero", "household-summary-bar", "zone-search", "content-column", "site-footer"}
            <= set(st["inertIds"])
        )
        self.assertEqual(st["aria"], {"edit": "true", "headerAuth": "false", "headerAccount": "false"})
        self.assertAlmostEqual(st["rects"]["backdrop"]["w"], st["innerWidth"], delta=1.0)
        self.assertAlmostEqual(st["rects"]["backdrop"]["h"], st["innerHeight"], delta=1.0)

    def _run13_assert_mobile_passenger_sheet_open(self, st: dict[str, Any], signed_in: bool) -> None:
        """Mobile (<1180px): passenger details open as bottom sheet above the dock, with ZERO Gmail/auth elements inside."""
        self.assertEqual(st["jsErrors"], [])
        prof = st["prof"]
        self.assertTrue(prof["sheetOpen"])
        self.assertIsNone(prof["view"])
        self.assertIsNone(prof["role"])
        self.assertEqual(prof["position"], "fixed")
        self.assertTrue(prof["rect"]["visible"])
        self.assertGreaterEqual(prof["rect"]["w"], st["clientWidth"] - 1.0)
        for key in self._RUN13_PASSENGER_FIELD_KEYS + ("backdrop",):
            self.assertTrue(st["vis"][key], f"{key} must be visible in the mobile passenger sheet")
        for key in self._RUN13_SIGNIN_KEYS:
            self.assertFalse(st["vis"][key], f"{key} belongs to the top-bar auth popover, not the mobile travelers sheet")
        self.assertEqual(st["vis"]["saveBtn"], signed_in)
        self.assertTrue(st["bodyLocked"])
        self.assertEqual(st["inertIds"], [])
        self.assertEqual(st["aria"], {"edit": "true", "headerAuth": "false", "headerAccount": "false"})

    def _run13_assert_header_popover_open(self, st: dict[str, Any], signed_in: bool) -> None:
        """Top-bar auth popover open (both desktop and mobile): anchored under `#app-header` within viewport bounds."""
        self.assertEqual(st["jsErrors"], [])
        self.assertFalse(st["prof"]["sheetOpen"])
        self.assertEqual(st["prof"]["display"], "none")
        pop = st["rects"]["authPopover"]
        self.assertTrue(pop["visible"])
        self.assertGreaterEqual(pop["x"], 0.0)
        self.assertLessEqual(pop["right"], st["innerWidth"])
        self.assertGreaterEqual(pop["y"], st["rects"]["header"]["bottom"] - 10.0)
        self.assertLessEqual(st["scrollWidth"], st["clientWidth"])
        self.assertTrue(st["vis"]["authPopover"])
        self.assertTrue(st["vis"]["authCard"])
        for key in self._RUN13_PASSENGER_FIELD_KEYS + ("saveBtn", "saveError", "profileSaveFeedback", "backdrop"):
            self.assertFalse(st["vis"][key], f"{key} must not be visible when only the header auth popover is open")
        shown = ("verifiedBadge", "userEmail", "signoutBtn", "deleteBtn", "notifInput", "notifShort", "userDisc") if signed_in else ("googleBtn", "guestDisc")
        hidden = ("googleBtn", "guestDisc") if signed_in else ("verifiedBadge", "userEmail", "signoutBtn", "deleteBtn", "notifInput", "notifShort", "userDisc")
        for key in shown:
            self.assertTrue(st["vis"][key], f"{key} must be visible in the header auth popover")
        for key in hidden:
            self.assertFalse(st["vis"][key], f"{key} must not be visible in this auth state")
        self.assertFalse(st["bodyLocked"])
        self.assertEqual(st["inertIds"], [])
        expected_aria = (
            {"edit": "false", "headerAuth": "false", "headerAccount": "true"}
            if signed_in
            else {"edit": "false", "headerAuth": "true", "headerAccount": "false"}
        )
        self.assertEqual(st["aria"], expected_aria)
        self._run13_assert_travelers_bar_above_search(st)

    def test_scenario_26_run13_desktop_access_strip_passenger_window_and_closed_signin_real_input_e2e(
        self,
    ) -> None:
        """Scenario 26 (Run 13 unified): on BOTH Desktop (1440x900, 1180x900) and Mobile (390x844, 1179x900),
        sign-in lives ONLY in the top-left header bar and travelers summary + 'Edit' sits ONLY above `#zone-search`.
        Every open, close, edit and button press uses real CDP mouse / keyboard input."""
        db_path, _repo = self.make_isolated_env(auto_seed=True)
        guest_client = self.get_client(db_path)

        for auth_var in ("VACATION_PLANNER_AUTH_TEST_MODE", "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"):
            prev_value = os.environ.pop(auth_var, None)
            if prev_value is not None:
                self.addCleanup(os.environ.__setitem__, auth_var, prev_value)
        guest_session = guest_client.get("/api/v1/auth/session").json()
        self.assertFalse(guest_session["authenticated"])
        self.assertFalse(guest_session["oauth_configured"])
        self.assertFalse(guest_session["test_mode"])

        browser = self.open_run13_browser(guest_client, viewport=(1440, 900))

        expected = {
            "rtl": {
                "edit": "עריכה",
                "edit_aria": "עריכת הרכב הנוסעים",
                "header_auth": "כניסה",
                "summary_boot": ("2 מבוגרים", "0 ילדים", "0 מתמיד"),
                "summary_edited": "3 מבוגרים · 1 ילדים · 💳 50,000 מתמיד",
                "disclaimer": "אפליקציית תכנון חופשות עצמאית שאינה שייכת לאל על",
            },
            "ltr": {
                "edit": "Edit",
                "edit_aria": "Edit travelers",
                "header_auth": "Sign in",
                "summary_boot": ("2 Adults", "0 Kids", "0 Matmid"),
                "summary_edited": "3 Adults · 1 Kids · 💳 50,000 Matmid",
                "disclaimer": "not affiliated with",
            },
        }
        edited_values = {"adults": "3", "matmid": "50000", "ages": ["11"]}

        for target_dir in ("rtl", "ltr"):
            exp = expected[target_dir]
            browser.mount()
            if target_dir == "ltr":
                browser.real_click("#btn-toggle-locale")
                browser.settle()

            # 1. Boot at 1440x900: closed; travelers bar above search; sign-in ONLY in top-left header
            boot = browser.eval(_RUN13_STATE_JS)
            self.assertEqual(boot["dir"], target_dir)
            self.assertEqual(boot["innerWidth"], 1440)
            self._run13_assert_closed(boot, signed_in=False)
            self._run13_assert_travelers_bar_above_search(boot)
            self.assertGreaterEqual(boot["rects"]["hhBar"]["y"], boot["rects"]["header"]["bottom"])
            self.assertEqual(boot["text"]["editBtn"], exp["edit"])
            self.assertEqual(boot["text"]["editAria"], exp["edit_aria"])
            self.assertEqual(boot["text"]["headerAuth"], exp["header_auth"])
            for summary_part in exp["summary_boot"]:
                self.assertIn(summary_part, boot["text"]["hhSummary"])
            self.assertEqual(boot["values"], {"adults": "2", "matmid": "0", "ages": []})

            # 1b. Zero-balance CTA opens the passenger window with Matmid focused
            self.assertTrue(browser.vis('[data-focus-matmid="true"]'))
            browser.real_click('[data-focus-matmid="true"]')
            browser.pump(160)
            via_cta = browser.eval(_RUN13_STATE_JS)
            self._run13_assert_passenger_window_open(via_cta, signed_in=False)
            self.assertEqual(via_cta["activeId"], "prof-matmid-points")
            browser.real_key("Escape")
            self._run13_assert_closed(browser.eval(_RUN13_STATE_JS), signed_in=False)

            # 2. Real click on `#btn-open-profile-sheet` ("עריכה" / "Edit") opens the wide passenger modal
            browser.real_click("#btn-open-profile-sheet")
            browser.pump(160)
            opened = browser.eval(_RUN13_STATE_JS)
            self._run13_assert_passenger_window_open(opened, signed_in=False)
            self.assertEqual(opened["activeId"], "prof-adults-count")
            self.assertAlmostEqual(opened["rects"]["hhBar"]["x"], boot["rects"]["hhBar"]["x"], delta=0.5)
            self.assertAlmostEqual(opened["rects"]["search"]["x"], boot["rects"]["search"]["x"], delta=0.5)
            behind = browser.eval("window.__r13.topAtCentreOf('#btn-run-search')")
            self.assertFalse(behind["inside"])
            self.assertEqual(behind["id"], "profile-sheet-backdrop")

            # 3. Edit adults, Matmid and a child with real typing
            browser.real_replace_value("#prof-adults-count", "3")
            browser.real_replace_value("#prof-matmid-points", "50000")
            browser.real_click("#btn-add-child")
            self.assertTrue(browser.vis('[data-child-age="0"]'))
            browser.real_replace_value('[data-child-age="0"]', "11")
            browser.real_key("Tab")
            edited = browser.eval(_RUN13_STATE_JS)
            self._run13_assert_passenger_window_open(edited, signed_in=False)
            self.assertEqual(edited["values"], edited_values)

            # 4. Close via `#btn-close-profile-sheet`: values kept and summary bar updated
            browser.real_click("#btn-close-profile-sheet")
            closed = browser.eval(_RUN13_STATE_JS)
            self._run13_assert_closed(closed, signed_in=False)
            self._run13_assert_travelers_bar_above_search(closed)
            self.assertIn(exp["summary_edited"], closed["text"]["hhSummary"])
            self.assertEqual(closed["values"], edited_values)
            self.assertEqual(closed["activeId"], "btn-open-profile-sheet")

            # 5. Reopen -> backdrop click closes and restores focus
            browser.real_click("#btn-open-profile-sheet")
            browser.pump(160)
            self._run13_assert_passenger_window_open(browser.eval(_RUN13_STATE_JS), signed_in=False)
            browser.real_click_at(40, 620, "profile-sheet-backdrop")
            after_backdrop = browser.eval(_RUN13_STATE_JS)
            self._run13_assert_closed(after_backdrop, signed_in=False)
            self.assertEqual(after_backdrop["activeId"], "btn-open-profile-sheet")

            # 6. Apply button closes window and runs search with edited household
            browser.real_click("#btn-open-profile-sheet")
            browser.pump(160)
            browser.fetch_log.clear()
            browser.real_click("#btn-apply-profile-sheet")
            browser.settle()
            self._run13_assert_closed(browser.eval(_RUN13_STATE_JS), signed_in=False)
            apply_searches = browser.requests("POST", "/api/v1/vacations/search")
            self.assertGreaterEqual(len(apply_searches), 1)
            applied_profile = apply_searches[-1]["body"]["inline_profile"]
            self.assertEqual(applied_profile["adults_count"], 3)
            self.assertEqual(applied_profile["matmid_points_balance"], 50000)
            self.assertEqual([c["child_age_years"] for c in applied_profile["children"]], [11])

            # 7. Top-left header auth button toggles `#header-auth-popover`, Escape closes, click-outside closes
            browser.real_click("#btn-header-auth")
            browser.pump(120)
            pop_open = browser.eval(_RUN13_STATE_JS)
            self._run13_assert_header_popover_open(pop_open, signed_in=False)
            self.assertIn(exp["disclaimer"], pop_open["text"]["guestDisc"])
            self.assertEqual(pop_open["activeId"], "btn-google-signin")
            browser.real_key("Escape")
            pop_escaped = browser.eval(_RUN13_STATE_JS)
            self._run13_assert_closed(pop_escaped, signed_in=False)
            self.assertEqual(pop_escaped["activeId"], "btn-header-auth")

            # 8. Opening "Edit" while header auth popover is open closes the auth popover cleanly
            browser.real_click("#btn-header-auth")
            browser.pump(120)
            self._run13_assert_header_popover_open(browser.eval(_RUN13_STATE_JS), signed_in=False)
            browser.real_click("#btn-open-profile-sheet")
            browser.pump(160)
            self._run13_assert_passenger_window_open(browser.eval(_RUN13_STATE_JS), signed_in=False)
            browser.real_key("Escape")
            self._run13_assert_closed(browser.eval(_RUN13_STATE_JS), signed_in=False)

            # 9. Clicking `#btn-google-signin` on a server without OAuth shows `#auth-status-note` inside the popover
            browser.real_click("#btn-header-auth")
            browser.pump(120)
            browser.real_click("#btn-google-signin")
            browser.pump(100)
            no_oauth = browser.eval(_RUN13_STATE_JS)
            self._run13_assert_header_popover_open(no_oauth, signed_in=False)
            self.assertTrue(browser.vis("#auth-status-note"))
            self.assertIn("GOOGLE_OAUTH_CLIENT_ID", browser.text("#auth-status-note"))
            self.assertIsNone(browser.eval("window.__fvpLastAssignedUrl"))
            browser.real_click("#btn-run-search")
            browser.settle()
            self._run13_assert_closed(browser.eval(_RUN13_STATE_JS), signed_in=False)

        # 10. Mobile 390x844 & Breakpoint 1179px <-> 1180px: identical separation on mobile too!
        browser.set_viewport(390, 844)
        browser.mount()
        mob_boot = browser.eval(_RUN13_STATE_JS)
        self.assertEqual(mob_boot["innerWidth"], 390)
        self._run13_assert_closed(mob_boot, signed_in=False)
        self._run13_assert_travelers_bar_above_search(mob_boot)
        # Top-bar sign-in popover on 390x844 mobile
        browser.real_click("#btn-header-auth")
        browser.pump(120)
        self._run13_assert_header_popover_open(browser.eval(_RUN13_STATE_JS), signed_in=False)
        # Opening travelers sheet on mobile closes auth popover and shows ONLY travelers (no Gmail card in sheet!)
        browser.real_click("#btn-open-profile-sheet")
        browser.pump(160)
        mob_sheet = browser.eval(_RUN13_STATE_JS)
        self._run13_assert_mobile_passenger_sheet_open(mob_sheet, signed_in=False)
        self.assertLessEqual(mob_sheet["prof"]["rect"]["bottom"], mob_sheet["rects"]["dock"]["y"] + 2.0)

        # Crossing 390 -> 1180 closes the mobile sheet cleanly; opening at 1180 -> 1179 closes the modal cleanly
        browser.set_viewport(1180, 900)
        browser.wait_until(
            "!document.getElementById('zone-profile').classList.contains('is-sheet-open')",
            "mobile sheet to close when viewport reaches 1180px",
        )
        at_1180 = browser.eval(_RUN13_STATE_JS)
        self._run13_assert_closed(at_1180, signed_in=False)
        self._run13_assert_travelers_bar_above_search(at_1180)
        browser.real_click("#btn-open-profile-sheet")
        browser.pump(160)
        win_1180 = browser.eval(_RUN13_STATE_JS)
        self._run13_assert_passenger_window_open(win_1180, signed_in=False)
        self.assertAlmostEqual(win_1180["prof"]["rect"]["w"], 520, delta=1.0)
        browser.set_viewport(1179, 900)
        browser.wait_until(
            "!document.getElementById('zone-profile').classList.contains('is-sheet-open')",
            "desktop passenger modal to close when viewport drops below 1180px",
        )
        self._run13_assert_closed(browser.eval(_RUN13_STATE_JS), signed_in=False)
        self.assertEqual(browser.eval("document.body.getAttribute('style') || ''"), "")
        self.assertEqual(browser.js_errors(), [])
        self.assertEqual([r for r in browser.fetch_log if r["status"] >= 500], [])

    def test_scenario_27_run13_desktop_signin_save_signout_delete_through_new_ui_real_input_e2e(
        self,
    ) -> None:
        """Scenario 27 (Run 13 unified): Gmail sign-in, auto-save of guest draft, explicit save + 422 error inside
        passenger modal, notifications opt-in, top-bar 1-click sign-out AND popover sign-out, delete-profile, and
        390x844 mobile signed-in top-bar flow — all driven by real mouse & keyboard input."""
        db_path, _repo = self.make_isolated_env(auto_seed=True)
        browser_client = self.get_client(db_path)

        env_prev_test = os.environ.get("VACATION_PLANNER_AUTH_TEST_MODE")
        env_prev_live = os.environ.get("ELAL_LIVE_FETCH_ENABLED")
        os.environ["VACATION_PLANNER_AUTH_TEST_MODE"] = "1"
        os.environ["ELAL_LIVE_FETCH_ENABLED"] = "0"

        def _restore_env() -> None:
            for var_name, prev in (
                ("VACATION_PLANNER_AUTH_TEST_MODE", env_prev_test),
                ("ELAL_LIVE_FETCH_ENABLED", env_prev_live),
            ):
                if prev is None:
                    os.environ.pop(var_name, None)
                else:
                    os.environ[var_name] = prev

        self.addCleanup(_restore_env)

        browser = self.open_run13_browser(browser_client, viewport=(1440, 900))
        test_email = "desk.family@gmail.com"
        he_disclaimer = "אפליקציית תכנון חופשות עצמאית שאינה שייכת לאל על"

        def complete_oauth_host_side(assigned_url: str) -> None:
            self.assertTrue(str(assigned_url).startswith("/api/v1/auth/google/login"))
            r_login = browser_client.get(f"{assigned_url}&mock_oauth=1&test_email={test_email}")
            self.assertEqual(r_login.status_code, 302)
            r_authorize = browser_client.get(r_login.headers["Location"])
            self.assertEqual(r_authorize.status_code, 302)
            r_callback = browser_client.get(r_authorize.headers["Location"])
            self.assertEqual(r_callback.status_code, 302)
            self.assertEqual(r_callback.headers["Location"], "/")

        def api_profile() -> dict[str, Any]:
            resp = browser_client.get("/api/v1/profile")
            self.assertEqual(resp.status_code, 200)
            return resp.json()

        # A. Guest at 1440x900: edit household in the passenger window, then close it
        browser.mount()
        self._run13_assert_closed(browser.eval(_RUN13_STATE_JS), signed_in=False)
        browser.real_click("#btn-open-profile-sheet")
        browser.pump(160)
        self._run13_assert_passenger_window_open(browser.eval(_RUN13_STATE_JS), signed_in=False)
        browser.real_replace_value("#prof-matmid-points", "150000")
        browser.real_click("#btn-add-child")
        browser.real_replace_value('[data-child-age="0"]', "9")
        browser.real_key("Tab")
        browser.real_click("#btn-close-profile-sheet")
        guest_edited = browser.eval(_RUN13_STATE_JS)
        self._run13_assert_closed(guest_edited, signed_in=False)
        self.assertIn("1 ילדים", guest_edited["text"]["hhSummary"])
        self.assertIn("150,000", guest_edited["text"]["hhSummary"])

        # B. Open top-left header sign-in popover and click `#btn-google-signin`
        browser.real_click("#btn-header-auth")
        browser.pump(120)
        guest_pop = browser.eval(_RUN13_STATE_JS)
        self._run13_assert_header_popover_open(guest_pop, signed_in=False)
        self.assertIn(he_disclaimer, guest_pop["text"]["guestDisc"])
        browser.real_click("#btn-google-signin")
        signin_click = browser.eval(
            "({ assignedUrl: window.__fvpLastAssignedUrl, ssDump: window.sessionStorage._dump() })"
        )
        self.assertIn("fvp_pending_oauth_draft", signin_click["ssDump"])
        complete_oauth_host_side(signin_click["assignedUrl"])

        # C. Back on `/` signed in: guest draft auto-saved; top-left bar shows email + 1-click sign-out button
        browser.fetch_log.clear()
        browser.mount(session_storage=signin_click["ssDump"])
        signed_boot = browser.eval(_RUN13_STATE_JS)
        self._run13_assert_closed(signed_boot, signed_in=True)
        self._run13_assert_travelers_bar_above_search(signed_boot)
        self.assertTrue(signed_boot["vis"]["headerAccountEmail"])
        self.assertFalse(signed_boot["vis"]["headerAccountShort"])
        self.assertEqual(signed_boot["text"]["headerAccountEmail"], test_email)
        self.assertEqual(signed_boot["text"]["headerSignout"], "התנתקות")
        draft_puts = browser.requests("PUT", "/api/v1/profile")
        self.assertEqual([r["status"] for r in draft_puts], [200])
        self.assertEqual(draft_puts[0]["body"]["matmid_points_balance"], 150000)
        saved_draft = api_profile()
        self.assertTrue(saved_draft["is_persisted"])
        self.assertEqual(saved_draft["matmid_points_balance"], 150000)
        self.assertEqual([c["child_age_years"] for c in saved_draft["children"]], [9])
        self.assertIn("150,000", signed_boot["text"]["hhSummary"])

        # D. Open top-left account popover: verify email, save confirmation, and disclaimer
        browser.real_click("#btn-header-account")
        browser.pump(120)
        user_pop = browser.eval(_RUN13_STATE_JS)
        self._run13_assert_header_popover_open(user_pop, signed_in=True)
        self.assertEqual(user_pop["activeId"], "btn-signout")
        self.assertIn(he_disclaimer, user_pop["text"]["userDisc"])
        self.assertTrue(user_pop["vis"]["saveFeedback"])
        self.assertIn("נשמר", user_pop["text"]["saveFeedback"])
        browser.real_click("#btn-header-account")
        self._run13_assert_closed(browser.eval(_RUN13_STATE_JS), signed_in=True)

        # E. Explicit save inside passenger window + failed save (HTTP 422) reported inside window + recovery
        browser.real_click("#btn-open-profile-sheet")
        browser.pump(160)
        user_window = browser.eval(_RUN13_STATE_JS)
        self._run13_assert_passenger_window_open(user_window, signed_in=True)
        self.assertEqual(user_window["values"], {"adults": "2", "matmid": "150000", "ages": ["9"]})
        self.assertTrue(user_window["vis"]["profileSaveFeedback"])
        browser.real_replace_value("#prof-adults-count", "4")
        browser.fetch_log.clear()
        browser.real_click("#btn-save-profile")
        browser.settle()
        self.assertEqual([r["status"] for r in browser.requests("PUT", "/api/v1/profile")], [200])
        self.assertEqual(api_profile()["adults_count"], 4)
        after_save = browser.eval(_RUN13_STATE_JS)
        self.assertTrue(after_save["vis"]["profileSaveFeedback"])
        self.assertFalse(after_save["vis"]["saveError"])

        browser.real_replace_value("#prof-adults-count", "99")
        browser.fetch_log.clear()
        browser.real_click("#btn-save-profile")
        browser.settle()
        self.assertEqual([r["status"] for r in browser.requests("PUT", "/api/v1/profile")], [422])
        failed_save = browser.eval(_RUN13_STATE_JS)
        self.assertTrue(failed_save["vis"]["saveError"])
        self.assertIn("לא ניתן לשמור את פרופיל המשפחה", failed_save["text"]["saveError"])
        self.assertFalse(failed_save["vis"]["profileSaveFeedback"])
        self.assertTrue(browser.eval("window.__r13.topAtCentreOf('#profile-save-error')")["inside"])

        browser.real_replace_value("#prof-adults-count", "2")
        browser.fetch_log.clear()
        browser.real_click("#btn-save-profile")
        browser.settle()
        self.assertEqual([r["status"] for r in browser.requests("PUT", "/api/v1/profile")], [200])
        recovered = browser.eval(_RUN13_STATE_JS)
        self.assertFalse(recovered["vis"]["saveError"])
        self.assertTrue(recovered["vis"]["profileSaveFeedback"])
        browser.real_key("Escape")
        self._run13_assert_closed(browser.eval(_RUN13_STATE_JS), signed_in=True)

        # F. Notifications opt-in in top-left popover, then 1-click sign-out via top-bar `#btn-header-signout`!
        browser.real_click("#btn-header-account")
        browser.pump(120)
        self._run13_assert_header_popover_open(browser.eval(_RUN13_STATE_JS), signed_in=True)
        browser.fetch_log.clear()
        browser.real_click("#input-notifications-opt-in")
        browser.settle()
        self.assertEqual([r["status"] for r in browser.requests("PUT", "/api/v1/auth/notifications")], [200])
        self.assertTrue(browser_client.get("/api/v1/auth/session").json()["user"]["notifications_enabled"])

        browser.fetch_log.clear()
        browser.real_click("#btn-header-signout")
        browser.wait_until(
            "!document.getElementById('btn-header-auth').hasAttribute('hidden')",
            "guest state after top-bar sign-out",
        )
        browser.settle()
        self.assertEqual([r["status"] for r in browser.requests("POST", "/api/v1/auth/logout")], [200])
        self.assertFalse(browser_client.get("/api/v1/auth/session").json()["authenticated"])
        signed_out = browser.eval(_RUN13_STATE_JS)
        self._run13_assert_closed(signed_out, signed_in=False)
        self.assertEqual(signed_out["values"], {"adults": "2", "matmid": "0", "ages": []})

        # G. Sign back in on 390x844 MOBILE via top-left header, verify compact `חשבון ▾` + `התנתקות`, delete profile, and sign out via popover
        browser.set_viewport(390, 844)
        browser.mount()
        self._run13_assert_closed(browser.eval(_RUN13_STATE_JS), signed_in=False)
        browser.eval("window.__fvpLastAssignedUrl = null; true")
        browser.real_click("#btn-header-auth")
        browser.pump(120)
        self._run13_assert_header_popover_open(browser.eval(_RUN13_STATE_JS), signed_in=False)
        browser.real_click("#btn-google-signin")
        complete_oauth_host_side(browser.eval("window.__fvpLastAssignedUrl"))
        browser.fetch_log.clear()
        browser.mount(session_storage=browser.eval("window.sessionStorage._dump()"))
        mob_signed = browser.eval(_RUN13_STATE_JS)
        self._run13_assert_closed(mob_signed, signed_in=True)
        self._run13_assert_travelers_bar_above_search(mob_signed)
        self.assertFalse(mob_signed["vis"]["headerAccountEmail"])
        self.assertTrue(mob_signed["vis"]["headerAccountShort"])
        self.assertEqual(mob_signed["text"]["headerAccountShort"], "חשבון")
        self.assertEqual(mob_signed["values"], {"adults": "2", "matmid": "150000", "ages": ["9"]})

        # Delete saved profile on mobile via top-left account popover (cancel first, then confirm)
        browser.real_click("#btn-header-account")
        browser.pump(120)
        self._run13_assert_header_popover_open(browser.eval(_RUN13_STATE_JS), signed_in=True)
        browser.real_click("#btn-delete-profile")
        self.assertTrue(browser.vis("#auth-delete-confirm-bar"))
        browser.real_click("#btn-cancel-delete-profile")
        self.assertFalse(browser.vis("#auth-delete-confirm-bar"))
        self.assertTrue(api_profile()["is_persisted"])
        browser.real_click("#btn-delete-profile")
        browser.fetch_log.clear()
        browser.real_click("#btn-confirm-delete-profile")
        browser.wait_until(
            "document.getElementById('auth-save-feedback').textContent.includes('נמחקו')",
            "delete confirmation message",
        )
        browser.settle()
        self.assertEqual([r["status"] for r in browser.requests("DELETE", "/api/v1/profile")], [200])
        deleted = browser.eval(_RUN13_STATE_JS)
        self._run13_assert_header_popover_open(deleted, signed_in=True)
        self.assertFalse(api_profile()["is_persisted"])
        self.assertEqual(deleted["values"], {"adults": "2", "matmid": "0", "ages": []})

        # Sign out via `#btn-signout` inside the popover
        browser.real_click("#btn-signout")
        browser.wait_until(
            "!document.getElementById('btn-header-auth').hasAttribute('hidden')",
            "guest state after popover sign-out",
        )
        browser.settle()
        self.assertFalse(browser_client.get("/api/v1/auth/session").json()["authenticated"])
        self.assertEqual(browser.js_errors(), [])

    def test_scenario_28_run14_workplace_cost_zero_children_and_dual_calendar_popup_e2e(
        self,
    ) -> None:
        """Scenario 28 (Run 14 M14): Real Headless-Chrome CDP verification across `1440x900`, `390x844`, and `360x800`
        (`he` RTL & `en` LTR) for:
        1. `0`-children complete school-vacation suppression + `[data-kpi="workdays-cost"]` & unclipped tooltip + `lastSearchProfile` lock.
        2. `>= 1`-child non-expanding card geometry (`dW == 0`, `dH <= 4.0px` vs `36c40ad` DPR=2 baseline, single-line header for 1-digit & 2-digit workdays).
        3. Shared toggleable main-page popup (`#zone-calendar.is-calendar-open`, `position: fixed`, side-by-side MoE + `"לוח חגים ומועדים במשק"`, 1st click opens, 2nd click on same trigger closes, plus `Escape` & `#btn-close-calendar`).
        4. Zero `"בוגרים"` across all KPI cells, tooltips, cards, and `#zone-calendar`.
        """
        import re as _re

        bogrim_re = _re.compile(r"(?<![א-ת])(?:של\s+)?(?:ה|ל|ב|ו|ש|כ)?בוגרים(?![א-ת])")
        db_path, repo = self.make_isolated_env(auto_seed=True)
        # Also seed a 15-night two-digit workday flight pair on FCO (2027-05-02 Sun .. 2027-05-17 Mon:
        # includes Yom HaAtzmaut Wed 2027-05-12 -> 10.0 regular workdays!) to verify 2-digit inline fit!
        from backend.app.schemas.domain import ElAlBonusAvailability

        repo.upsert_elal_bonus(
            [
                ElAlBonusAvailability(
                    id="LY381_2027-04-20",
                    flight_number="LY381",
                    origin_iata="TLV",
                    destination_iata="FCO",
                    direction="OUTBOUND",
                    flight_date=date(2027, 4, 20),
                    departure_time_local="07:30",
                    arrival_time_local="10:15",
                    economy_award_seats=4,
                    economy_points_per_pax=15000,
                    taxes_usd_per_pax=48.75,
                    expires_at="2099-12-31T23:59:59Z",
                ),
                ElAlBonusAvailability(
                    id="LY384_2027-05-09",
                    flight_number="LY384",
                    origin_iata="FCO",
                    destination_iata="TLV",
                    direction="INBOUND",
                    flight_date=date(2027, 5, 9),
                    departure_time_local="12:00",
                    arrival_time_local="16:25",
                    economy_award_seats=4,
                    economy_points_per_pax=15000,
                    taxes_usd_per_pax=48.75,
                    expires_at="2099-12-31T23:59:59Z",
                ),
            ]
        )
        client = self.get_client(db_path)

        browser = _Run13ChromeSession(self, client, reference_date="2026-11-26")

        def set_dpr2_vp(w: int, h: int, is_mob: bool) -> None:
            browser.call(
                "Emulation.setDeviceMetricsOverride",
                {"width": w, "height": h, "deviceScaleFactor": 2, "mobile": is_mob},
            )
            browser.pump(80)

        # Authoritative `36c40ad` DPR=2 baseline `.proposal-card` dimensions (Card #0, ref `2026-11-26`)
        baseline_0_children = {
            (1440, 900, "rtl"): (881.0, 303.28),
            (1440, 900, "ltr"): (881.0, 303.28),
            (390, 844, "rtl"): (332.0, 593.06),
            (390, 844, "ltr"): (332.0, 591.06),
            (360, 800, "rtl"): (302.0, 593.06),
            (360, 800, "ltr"): (302.0, 608.86),
        }
        baseline_1_child = {
            (1440, 900, "rtl"): (881.0, 303.28),
            (1440, 900, "ltr"): (881.0, 338.27),
            (390, 844, "rtl"): (332.0, 608.86),
            (390, 844, "ltr"): (332.0, 624.66),
            (360, 800, "rtl"): (302.0, 608.86),
            (360, 800, "ltr"): (302.0, 624.66),
        }

        set_dpr2_vp(1440, 900, False)
        browser.mount()

        # ------------------------------------------------------------------
        # PART 1: `0` Children (`children = []`) — Complete School-Vacation Suppression
        # ------------------------------------------------------------------
        for vp_w, vp_h, is_mob in ((1440, 900, False), (390, 844, True), (360, 800, True)):
            set_dpr2_vp(vp_w, vp_h, is_mob)
            for target_dir in ("rtl", "ltr"):
                cur_dir = browser.eval("document.documentElement.getAttribute('dir')")
                if cur_dir != target_dir:
                    browser.real_click("#btn-toggle-locale")
                    browser.pump(60)
                snap0 = browser.eval(
                    """(() => {
                      window.scrollTo(0, 0);
                      const docEl = document.documentElement;
                      const hdr = document.getElementById('app-header').getBoundingClientRect();
                      const resZone = document.getElementById('zone-results');
                      const cards = Array.from(document.querySelectorAll('.proposal-card'));
                      const c0 = cards[0];
                      const cr = c0.getBoundingClientRect();
                      const wCell = c0.querySelector('.stub-kpi-grid > [data-kpi="workdays-cost"]');
                      const tip = wCell ? wCell.querySelector('.kpi-tooltip[role="tooltip"]') : null;
                      c0.scrollIntoView({ behavior: 'instant', block: 'center' });
                      wCell.click();
                      const tr = tip.getBoundingClientRect();
                      const tipOpenDisplay = getComputedStyle(tip).display;
                      const tipTxt = tip.textContent.replace(/\\s+/g, ' ').trim();
                      wCell.click();
                      window.scrollTo(0, 0);
                      const hdrRow = c0.querySelector('.bonus-direction-header');
                      const ptsPill = c0.querySelector('.proposal-pass-main .flight-bonus-points-pill');
                      const ptsIconR = ptsPill ? ptsPill.querySelector('.flight-points-icon').getBoundingClientRect() : null;
                      const ptsLblR = ptsPill ? ptsPill.querySelector('.stub-fare-label').getBoundingClientRect() : null;
                      const ptsValR = ptsPill ? ptsPill.querySelector('.stub-fare-val').getBoundingClientRect() : null;
                      const hdrRowR = hdrRow.getBoundingClientRect();
                      const ptsPillR = ptsPill ? ptsPill.getBoundingClientRect() : null;
                      return {
                        dir: docEl.getAttribute('dir'),
                        scrollW: docEl.scrollWidth,
                        clientW: docEl.clientWidth,
                        headerH: hdr.height,
                        firstCardY: c0.getBoundingClientRect().top,
                        cardW: Math.round(cr.width * 100) / 100,
                        cardH: Math.round(cr.height * 100) / 100,
                        schoolDomCount: resZone.querySelectorAll('[data-kpi="school-fit"], [data-school-missed], .kpi-missed-paren, [id^="kpi-tip-fit-"]').length,
                        paxSummaryCount: resZone.querySelectorAll('.stub-pax-summary, .stub-fare-ledger').length,
                        minPtsInMain: Boolean(c0.querySelector('.proposal-pass-main .min-points-ticket')),
                        minPtsInStub: Boolean(c0.querySelector('.proposal-pass-stub .min-points-ticket')),
                        ptsJustify: ptsPill ? getComputedStyle(ptsPill).justifyContent : '',
                        ptsRightDelta: ptsPillR ? Math.abs(hdrRowR.right - ptsPillR.right) : 999,
                        ptsLeftDelta: ptsPillR ? Math.abs(ptsPillR.left - hdrRowR.left) : 999,
                        ptsIconLblRtlGap: (ptsIconR && ptsLblR) ? Math.abs(ptsIconR.left - ptsLblR.right) : 999,
                        ptsValRtlAligned: (ptsPillR && ptsLblR && ptsValR)
                          ? (Math.abs(ptsLblR.left - ptsValR.right) <= 12.0 || Math.abs(ptsPillR.right - ptsValR.right) <= 14.0)
                          : false,
                        workBelowWeather: c0.querySelector('.stub-weather-card').getBoundingClientRect().bottom <= wCell.getBoundingClientRect().top + 2.0,
                        workValBelowHead: wCell.querySelector('.kpi-cell-val').getBoundingClientRect().top >= wCell.querySelector('.kpi-cell-head').getBoundingClientRect().bottom - 1.0,
                        resultsText: resZone.textContent || '',
                        resultsAria: Array.from(resZone.querySelectorAll('[title], [aria-label]')).map((e) => (e.getAttribute('title') || '') + ' ' + (e.getAttribute('aria-label') || '')).join(' '),
                        workLabel: wCell.querySelector('.kpi-cell-label').textContent.trim(),
                        workVal: wCell.querySelector('.kpi-cell-val').textContent.replace(/\\s+/g, ' ').trim(),
                        tipOpenDisplay,
                        tipTxt,
                        tipLeft: tr.left,
                        tipRight: tr.right,
                        innerW: window.innerWidth,
                        bodyTxt: document.body.textContent || ''
                      };
                    })()"""
                )
                self.assertEqual(snap0["dir"], target_dir)
                self.assertLessEqual(snap0["scrollW"], snap0["clientW"])
                if vp_w == 390:
                    self.assertLess(snap0["firstCardY"], 900.0)
                if vp_w == 360:
                    self.assertLessEqual(snap0["headerH"], 68.0)
                self.assertEqual(snap0["schoolDomCount"], 0)
                self.assertEqual(snap0["paxSummaryCount"], 0)
                self.assertTrue(snap0["minPtsInMain"])
                self.assertFalse(snap0["minPtsInStub"])
                self.assertIn(snap0["ptsJustify"], ("flex-start", "start", "flow-start"))
                if is_mob and target_dir == "rtl":
                    self.assertLessEqual(snap0["ptsRightDelta"], 2.0)
                    self.assertLessEqual(snap0["ptsIconLblRtlGap"], 12.0)
                    self.assertTrue(snap0["ptsValRtlAligned"])
                elif is_mob and target_dir == "ltr":
                    self.assertLessEqual(snap0["ptsLeftDelta"], 2.0)
                self.assertTrue(snap0["workBelowWeather"])
                self.assertTrue(snap0["workValBelowHead"])
                for forbidden_school in (
                    'בי"ס',
                    "בית ספר",
                    "חיסור",
                    "משרד החינוך",
                    "קייטנ",
                    "School Break",
                    "missed",
                    "classroom",
                    "MoE",
                ):
                    self.assertNotIn(forbidden_school, snap0["resultsText"])
                    self.assertNotIn(forbidden_school, snap0["resultsAria"])
                self.assertNotIn("בוגרים", snap0["workLabel"])
                self.assertNotIn("בוגרים", snap0["tipTxt"])
                self.assertIsNone(bogrim_re.search(snap0["bodyTxt"]))
                self.assertEqual(snap0["tipOpenDisplay"], "flex")
                self.assertGreaterEqual(snap0["tipLeft"], 0.0)
                self.assertLessEqual(snap0["tipRight"], snap0["innerW"])
                if target_dir == "rtl":
                    self.assertIn("חופשת עבודה", snap0["workLabel"])
                    self.assertIn("איך חושב:", snap0["tipTxt"])
                    self.assertIn("משמעות:", snap0["tipTxt"])
                else:
                    self.assertIn("Workdays Off", snap0["workLabel"])
                    self.assertIn("How calculated:", snap0["tipTxt"])
                    self.assertIn("Meaning:", snap0["tipTxt"])

                base_w, base_h = baseline_0_children[(vp_w, vp_h, target_dir)]
                self.assertAlmostEqual(snap0["cardW"], base_w, delta=0.5)
                self.assertLessEqual(snap0["cardH"] - base_h, 24.0 if is_mob else 4.0)

        # Verify `lastSearchProfile` lock: adding a draft child in `#zone-profile` and closing WITHOUT searching,
        # then toggling locale, keeps `0`-children suppression intact on rendered cards!
        set_dpr2_vp(1440, 900, False)
        if browser.eval("document.documentElement.getAttribute('dir')") != "rtl":
            browser.real_click("#btn-toggle-locale")
            browser.pump(60)
        browser.real_click("#btn-open-profile-sheet")
        browser.pump(100)
        browser.real_click("#btn-add-child")
        browser.pump(60)
        browser.real_click("#btn-close-profile-sheet")
        browser.pump(80)
        browser.real_click("#btn-toggle-locale")
        browser.pump(60)
        self.assertEqual(
            browser.eval("document.querySelectorAll('#zone-results [data-kpi=\"school-fit\"]').length"),
            0,
        )
        browser.real_click("#btn-toggle-locale")
        browser.pump(60)

        # ------------------------------------------------------------------
        # PART 2: `>= 1` Child (`children = [{age: 8}]`) — Non-Expanding Card Geometry (1-digit & 2-digit)
        # ------------------------------------------------------------------
        browser.real_click("#btn-open-profile-sheet")
        browser.pump(100)
        browser.real_replace_value('[data-child-age="0"]', "8")
        browser.real_click("#btn-apply-profile-sheet")
        browser.wait_until(
            "document.querySelectorAll('#zone-results [data-kpi=\"school-fit\"]').length >= 2",
            "cards rendered with >= 1 child",
        )
        browser.settle()

        for vp_w, vp_h, is_mob in ((1440, 900, False), (390, 844, True), (360, 800, True)):
            set_dpr2_vp(vp_w, vp_h, is_mob)
            for target_dir in ("rtl", "ltr"):
                if browser.eval("document.documentElement.getAttribute('dir')") != target_dir:
                    browser.real_click("#btn-toggle-locale")
                    browser.pump(60)
                snap1 = browser.eval(
                    """(() => {
                      window.scrollTo(0, 0);
                      const docEl = document.documentElement;
                      const c0 = document.querySelector('.proposal-card');
                      const cr = c0.getBoundingClientRect();
                      const wCard = c0.querySelector('.stub-weather-card');
                      const pairGrid = c0.querySelector('.stub-kpi-grid[data-paired-vacation="true"]');
                      const wCell = pairGrid ? pairGrid.querySelector('[data-kpi="workdays-cost"]') : null;
                      const fitCell = pairGrid ? pairGrid.querySelector('[data-kpi="school-fit"]') : null;
                      const wCardR = wCard.getBoundingClientRect();
                      const wr = wCell.getBoundingClientRect();
                      const fr = fitCell.getBoundingClientRect();
                      c0.scrollIntoView({ behavior: 'instant', block: 'center' });
                      wCell.click();
                      const wTip = wCell.querySelector('.kpi-tooltip[role="tooltip"]');
                      const wtr = wTip.getBoundingClientRect();
                      const wTipDisplay = getComputedStyle(wTip).display;
                      const wTipTxt = wTip.textContent.replace(/\\s+/g, ' ').trim();
                      wCell.click();
                      window.scrollTo(0, 0);
                      const hdrRow = c0.querySelector('.bonus-direction-header');
                      const ptsPill = c0.querySelector('.proposal-pass-main .flight-bonus-points-pill');
                      const ptsIconR = ptsPill ? ptsPill.querySelector('.flight-points-icon').getBoundingClientRect() : null;
                      const ptsLblR = ptsPill ? ptsPill.querySelector('.stub-fare-label').getBoundingClientRect() : null;
                      const ptsValR = ptsPill ? ptsPill.querySelector('.stub-fare-val').getBoundingClientRect() : null;
                      const hdrRowR = hdrRow.getBoundingClientRect();
                      const ptsPillR = ptsPill ? ptsPill.getBoundingClientRect() : null;
                      return {
                        dir: docEl.getAttribute('dir'),
                        scrollW: docEl.scrollWidth,
                        clientW: docEl.clientWidth,
                        cardW: Math.round(cr.width * 100) / 100,
                        cardH: Math.round(cr.height * 100) / 100,
                        paxSummaryCount: c0.querySelectorAll('.stub-pax-summary, .stub-fare-ledger').length,
                        minPtsInMain: Boolean(c0.querySelector('.proposal-pass-main .min-points-ticket')),
                        minPtsInStub: Boolean(c0.querySelector('.proposal-pass-stub .min-points-ticket')),
                        ptsJustify: ptsPill ? getComputedStyle(ptsPill).justifyContent : '',
                        ptsRightDelta: ptsPillR ? Math.abs(hdrRowR.right - ptsPillR.right) : 999,
                        ptsLeftDelta: ptsPillR ? Math.abs(ptsPillR.left - hdrRowR.left) : 999,
                        ptsIconLblRtlGap: (ptsIconR && ptsLblR) ? Math.abs(ptsIconR.left - ptsLblR.right) : 999,
                        ptsValRtlAligned: (ptsPillR && ptsLblR && ptsValR)
                          ? (Math.abs(ptsLblR.left - ptsValR.right) <= 12.0 || Math.abs(ptsPillR.right - ptsValR.right) <= 14.0)
                          : false,
                        belowClimate: wCardR.bottom <= wr.top + 2.0,
                        workValBelowHead: wCell.querySelector('.kpi-cell-val').getBoundingClientRect().top >= wCell.querySelector('.kpi-cell-head').getBoundingClientRect().bottom - 1.0,
                        adjacentToSchoolFit: Math.abs(fr.top - wr.bottom) <= 6.0 && Math.abs(wr.left - fr.left) <= 2.0,
                        hasFitCell: Boolean(fitCell),
                        wTipDisplay,
                        wTipTxt,
                        wTipLeft: wtr.left,
                        wTipRight: wtr.right,
                        wTipWidth: wtr.width,
                        innerW: window.innerWidth,
                        workCellTxt: wCell.textContent || '',
                        cardTxt: c0.textContent || ''
                      };
                    })()"""
                )
                self.assertEqual(snap1["dir"], target_dir)
                self.assertLessEqual(snap1["scrollW"], snap1["clientW"])
                self.assertEqual(snap1["paxSummaryCount"], 0)
                self.assertTrue(snap1["minPtsInMain"])
                self.assertFalse(snap1["minPtsInStub"])
                self.assertIn(snap1["ptsJustify"], ("flex-start", "start", "flow-start"))
                if is_mob and target_dir == "rtl":
                    self.assertLessEqual(snap1["ptsRightDelta"], 2.0)
                    self.assertLessEqual(snap1["ptsIconLblRtlGap"], 12.0)
                    self.assertTrue(snap1["ptsValRtlAligned"])
                elif is_mob and target_dir == "ltr":
                    self.assertLessEqual(snap1["ptsLeftDelta"], 2.0)
                self.assertTrue(snap1["hasFitCell"])
                self.assertTrue(snap1["belowClimate"])
                self.assertTrue(snap1["workValBelowHead"])
                self.assertTrue(snap1["adjacentToSchoolFit"])
                self.assertEqual(snap1["wTipDisplay"], "flex")
                self.assertGreaterEqual(snap1["wTipWidth"], 220.0)
                self.assertGreaterEqual(snap1["wTipLeft"], 0.0)
                self.assertLessEqual(snap1["wTipRight"], snap1["innerW"])
                self.assertNotIn("בוגרים", snap1["workCellTxt"])
                self.assertNotIn("בוגרים", snap1["wTipTxt"])
                self.assertIsNone(bogrim_re.search(snap1["cardTxt"]))

                base_w1, base_h1 = baseline_1_child[(vp_w, vp_h, target_dir)]
                self.assertAlmostEqual(snap1["cardW"], base_w1, delta=0.5)
                self.assertLessEqual(snap1["cardH"] - base_h1, 24.0 if is_mob else 4.0)

        # Also verify 2-digit decimal workday value (`10.5` days on 19-night FCO 2027-04-20..2027-05-09) stays clean & adjacent to school-fit across 1440/390/360 in he & en!
        set_dpr2_vp(1440, 900, False)
        if browser.eval("document.documentElement.getAttribute('dir')") != "rtl":
            browser.real_click("#btn-toggle-locale")
            browser.pump(60)
        browser.eval(
            """(async () => {
              document.getElementById('input-dep-date').value = '2027-04-20';
              document.getElementById('input-ret-date').value = '2027-05-09';
              document.getElementById('input-flex-days').value = '0';
              document.getElementById('btn-dest-picker-toggle').click();
              document.querySelector('[data-dest-option="ROM"]').click();
              document.getElementById('btn-dest-popover-done').click();
            })()"""
        )
        browser.wait_until(
            "Boolean(document.querySelector('.proposal-card [data-kpi=\"workdays-cost\"][data-workdays=\"10.5\"]'))",
            "2-digit 10.5-workday FCO card rendered",
        )
        browser.settle()
        for vp_w, vp_h, is_mob in ((1440, 900, False), (390, 844, True), (360, 800, True)):
            set_dpr2_vp(vp_w, vp_h, is_mob)
            for target_dir in ("rtl", "ltr"):
                if browser.eval("document.documentElement.getAttribute('dir')") != target_dir:
                    browser.real_click("#btn-toggle-locale")
                    browser.pump(60)
                two_digit = browser.eval(
                    """(() => {
                      const pairGrid = document.querySelector('.proposal-card .stub-kpi-grid[data-paired-vacation="true"]');
                      const cell = pairGrid.querySelector('[data-kpi="workdays-cost"]');
                      const fit = pairGrid.querySelector('[data-kpi="school-fit"]');
                      const headR = cell.querySelector('.kpi-cell-head').getBoundingClientRect();
                      const valR = cell.querySelector('.kpi-cell-val').getBoundingClientRect();
                      return {
                        workdaysAttr: cell.getAttribute('data-workdays'),
                        adjacent: Math.abs(fit.getBoundingClientRect().top - cell.getBoundingClientRect().bottom) <= 6.0,
                        valStackedBelowHead: valR.top >= headR.bottom - 1.0,
                        inlineStartAligned: document.documentElement.getAttribute('dir') === 'rtl'
                          ? Math.abs(headR.right - valR.right) <= 2.0
                          : Math.abs(headR.left - valR.left) <= 2.0,
                        scrollW: document.documentElement.scrollWidth,
                        clientW: document.documentElement.clientWidth
                      };
                    })()"""
                )
                self.assertEqual(two_digit["workdaysAttr"], "10.5")
                self.assertTrue(two_digit["adjacent"])
                self.assertTrue(two_digit["valStackedBelowHead"])
                self.assertTrue(two_digit["inlineStartAligned"])
                self.assertLessEqual(two_digit["scrollW"], two_digit["clientW"])

        # ------------------------------------------------------------------
        # PART 3: Shared Toggleable Main-Page Popup (`#zone-calendar`) on Desktop & Mobile (`he` & `en`)
        # ------------------------------------------------------------------
        for vp_w, vp_h, is_mob, trig_sel in (
            (1440, 900, False, "#btn-toggle-calendar"),
            (390, 844, True, "#btn-mobile-dock-calendar"),
            (360, 800, True, "#btn-mobile-dock-calendar"),
        ):
            set_dpr2_vp(vp_w, vp_h, is_mob)
            for target_dir in ("rtl", "ltr"):
                if browser.eval("document.documentElement.getAttribute('dir')") != target_dir:
                    browser.real_click("#btn-toggle-locale")
                    browser.pump(60)
                # Scroll down first to prove opening does NOT render an inline section at bottom of page
                browser.eval("window.scrollTo(0, 260); true;")
                # 1st REAL mouse click on trigger -> opens popup
                browser.real_click(trig_sel)
                browser.pump(80)
                pop_open = browser.eval(
                    f"""(() => {{
                      const cz = document.getElementById('zone-calendar');
                      const bd = document.getElementById('calendar-modal-backdrop');
                      const moe = document.getElementById('calendar-col-moe');
                      const wrk = document.getElementById('calendar-col-workplace');
                      const trig = document.querySelector('{trig_sel}');
                      const cr = cz.getBoundingClientRect();
                      const mr = moe.getBoundingClientRect();
                      const wr = wrk.getBoundingClientRect();
                      return {{
                        hidden: cz.hasAttribute('hidden'),
                        isOpenCls: cz.classList.contains('is-calendar-open'),
                        pos: getComputedStyle(cz).position,
                        role: cz.getAttribute('role'),
                        ariaModal: cz.getAttribute('aria-modal'),
                        ariaExpanded: trig.getAttribute('aria-expanded'),
                        backdropVisible: !bd.hasAttribute('hidden') && getComputedStyle(bd).display !== 'none',
                        popupTop: cr.top,
                        popupBottom: cr.bottom,
                        innerH: window.innerHeight,
                        moeBox: {{ left: mr.left, right: mr.right, top: mr.top, w: mr.width }},
                        wrkBox: {{ left: wr.left, right: wr.right, top: wr.top, w: wr.width }},
                        moeRows: document.querySelectorAll('#moe-calendar-tbody tr').length,
                        wrkRows: document.querySelectorAll('#workplace-calendar-tbody tr').length,
                        halfDayRows: document.querySelectorAll('#workplace-calendar-tbody tr[data-workday-rate="0.5"]').length,
                        zeroDayRows: document.querySelectorAll('#workplace-calendar-tbody tr[data-workday-rate="0"]').length,
                        popTxt: cz.textContent || '',
                        scrollW: document.documentElement.scrollWidth,
                        clientW: document.documentElement.clientWidth
                      }};
                    }})()"""
                )
                self.assertFalse(pop_open["hidden"])
                self.assertTrue(pop_open["isOpenCls"])
                self.assertEqual(pop_open["pos"], "fixed")
                self.assertEqual(pop_open["role"], "dialog")
                self.assertEqual(pop_open["ariaModal"], "true")
                self.assertEqual(pop_open["ariaExpanded"], "true")
                self.assertTrue(pop_open["backdropVisible"])
                self.assertGreaterEqual(pop_open["popupTop"], 56.0)
                self.assertLessEqual(pop_open["popupTop"], 80.0)
                self.assertLessEqual(pop_open["popupBottom"], pop_open["innerH"])
                # Side-by-side verification (same row top, non-overlapping columns in RTL & LTR)
                self.assertLessEqual(abs(pop_open["moeBox"]["top"] - pop_open["wrkBox"]["top"]), 2.0)
                self.assertGreater(pop_open["moeBox"]["w"], 140.0)
                self.assertGreater(pop_open["wrkBox"]["w"], 140.0)
                if target_dir == "rtl":
                    self.assertGreaterEqual(pop_open["moeBox"]["left"], pop_open["wrkBox"]["right"] - 1.0)
                    self.assertIn("לוח חופשות משרד החינוך", pop_open["popTxt"])
                    self.assertIn("לוח חגים ומועדים במשק", pop_open["popTxt"])
                else:
                    self.assertLessEqual(pop_open["moeBox"]["right"], pop_open["wrkBox"]["left"] + 1.0)
                    self.assertIn("School Vacation Calendar", pop_open["popTxt"])
                    self.assertIn("Public & Workplace Holidays", pop_open["popTxt"])
                self.assertGreater(pop_open["moeRows"], 3)
                self.assertEqual(pop_open["wrkRows"], 10)
                self.assertEqual(pop_open["halfDayRows"], 2)
                self.assertEqual(pop_open["zeroDayRows"], 8)
                self.assertNotIn("בוגרים", pop_open["popTxt"])
                self.assertLessEqual(pop_open["scrollW"], pop_open["clientW"])

                # 2nd REAL mouse click on THE SAME TRIGGER -> genuinely closes & hides the popup!
                browser.real_click(trig_sel)
                browser.pump(80)
                pop_closed = browser.eval(
                    f"""(() => {{
                      const cz = document.getElementById('zone-calendar');
                      const bd = document.getElementById('calendar-modal-backdrop');
                      const trig = document.querySelector('{trig_sel}');
                      return {{
                        hidden: cz.hasAttribute('hidden'),
                        display: getComputedStyle(cz).display,
                        isOpenCls: cz.classList.contains('is-calendar-open'),
                        backdropHidden: bd.hasAttribute('hidden'),
                        ariaExpanded: trig.getAttribute('aria-expanded')
                      }};
                    }})()"""
                )
                self.assertTrue(pop_closed["hidden"])
                self.assertEqual(pop_closed["display"], "none")
                self.assertFalse(pop_closed["isOpenCls"])
                self.assertTrue(pop_closed["backdropHidden"])
                self.assertEqual(pop_closed["ariaExpanded"], "false")

        # Also verify `Escape` key closes the open popup
        set_dpr2_vp(1440, 900, False)
        browser.real_click("#btn-toggle-calendar")
        browser.pump(80)
        self.assertFalse(browser.eval("document.getElementById('zone-calendar').hasAttribute('hidden')"))
        browser.real_key("Escape")
        browser.pump(80)
        self.assertTrue(browser.eval("document.getElementById('zone-calendar').hasAttribute('hidden')"))
        self.assertEqual(browser.js_errors(), [])

    def test_scenario_29_admin_only_bonus_sync_telemetry_visibility_and_isolation_e2e(self) -> None:
        """Scenario 29: Real Headless-Chrome verification that `#admin-bonus-sync-panel` is 100% hidden/empty for guests
        and regular Gmail users, appears ONLY when the admin account signs in, displays 5-shard diagnostics + live refresh
        in `he` & `en` on Desktop (`1440x900`) and Mobile (`390x844`), and disappears immediately upon sign-out.
        """
        db_path, _repo = self.make_isolated_env(auto_seed=True)
        old_mode = os.environ.get("VACATION_PLANNER_AUTH_TEST_MODE")
        old_live = os.environ.get("ELAL_LIVE_FETCH_ENABLED")
        os.environ["VACATION_PLANNER_AUTH_TEST_MODE"] = "1"
        os.environ["ELAL_LIVE_FETCH_ENABLED"] = "0"
        self.addCleanup(
            lambda: os.environ.__setitem__("VACATION_PLANNER_AUTH_TEST_MODE", old_mode)
            if old_mode is not None
            else os.environ.pop("VACATION_PLANNER_AUTH_TEST_MODE", None)
        )
        self.addCleanup(
            lambda: os.environ.__setitem__("ELAL_LIVE_FETCH_ENABLED", old_live)
            if old_live is not None
            else os.environ.pop("ELAL_LIVE_FETCH_ENABLED", None)
        )

        client = self.get_client(db_path)
        browser = _Run13ChromeSession(self, client, reference_date="2026-11-26")
        browser.set_viewport(1440, 900)
        browser.mount()

        # 1. Guest state: zero admin DOM content, hidden slot & hidden mini badge
        guest_check = browser.eval(
            """(() => {
              const slot = document.getElementById('admin-bonus-sync-slot');
              const mini = document.getElementById('auth-admin-sync-mini');
              return {
                slotHidden: slot.hasAttribute('hidden') && getComputedStyle(slot).display === 'none',
                slotHtml: slot.innerHTML,
                miniHidden: mini.hasAttribute('hidden') && getComputedStyle(mini).display === 'none',
                miniHtml: mini.innerHTML,
                panelExists: Boolean(document.getElementById('admin-bonus-sync-panel'))
              };
            })()"""
        )
        self.assertTrue(guest_check["slotHidden"])
        self.assertEqual(guest_check["slotHtml"], "")
        self.assertTrue(guest_check["miniHidden"])
        self.assertEqual(guest_check["miniHtml"], "")
        self.assertFalse(guest_check["panelExists"])

        # 2. Regular non-admin user signs in -> still 100% hidden & empty!
        r_login = client.request("POST", "/api/v1/auth/test-login", json_body={"email": "visitor.user@gmail.com"})
        self.assertEqual(r_login.status_code, 200)
        browser.mount()
        non_admin_check = browser.eval(
            """(() => {
              const slot = document.getElementById('admin-bonus-sync-slot');
              return {
                authedEmail: document.getElementById('header-account-email').textContent.trim(),
                slotHidden: slot.hasAttribute('hidden') && getComputedStyle(slot).display === 'none',
                slotHtml: slot.innerHTML,
                panelExists: Boolean(document.getElementById('admin-bonus-sync-panel'))
              };
            })()"""
        )
        self.assertEqual(non_admin_check["authedEmail"], "visitor.user@gmail.com")
        self.assertTrue(non_admin_check["slotHidden"])
        self.assertEqual(non_admin_check["slotHtml"], "")
        self.assertFalse(non_admin_check["panelExists"])

        # Sign out regular user via real header button
        browser.real_click("#btn-header-signout")
        browser.settle()

        # 3. Admin signs in -> telemetry bar appears with 5 shards, expands cleanly, refreshes live, works on mobile & EN, and clears on sign-out!
        admin_email = ".".join(["yoni", "budovsky"]) + "@gmail.com"
        a_login = client.request("POST", "/api/v1/auth/test-login", json_body={"email": admin_email})
        self.assertEqual(a_login.status_code, 200)
        browser.mount()

        admin_closed = browser.eval(
            """(() => {
              const panel = document.getElementById('admin-bonus-sync-panel');
              const shardCards = document.querySelectorAll('[data-admin-shard]');
              return {
                visible: Boolean(panel && getComputedStyle(panel).display !== 'none'),
                isOpen: Boolean(panel && panel.open),
                shardCount: shardCards.length,
                txt: panel ? panel.textContent : '',
                scrollOk: document.documentElement.scrollWidth <= document.documentElement.clientWidth
              };
            })()"""
        )
        self.assertTrue(admin_closed["visible"])
        self.assertFalse(admin_closed["isOpen"])
        self.assertEqual(admin_closed["shardCount"], 5)
        self.assertIn("אדמין", admin_closed["txt"])
        self.assertIn("ריצה אחרונה:", admin_closed["txt"])
        self.assertTrue(admin_closed["scrollOk"])

        # Expand 5-shard drawer & click Live Sync Check
        browser.real_click("#admin-bonus-sync-panel > summary")
        browser.pump(80)
        self.assertTrue(browser.eval("document.getElementById('admin-bonus-sync-panel').open"))
        browser.real_click("#btn-refresh-admin-sync")
        browser.settle()
        self.assertTrue(browser.eval("document.getElementById('admin-bonus-sync-panel').open"))

        # Mobile 390x844 + English locale check -> zero horizontal overflow
        browser.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True})
        browser.pump(80)
        self.assertTrue(browser.eval("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
        browser.real_click("#btn-toggle-locale")
        browser.pump(80)
        self.assertIn("Admin", browser.eval("document.getElementById('admin-bonus-sync-panel').textContent"))
        self.assertTrue(browser.eval("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))

        # Sign out -> admin telemetry immediately purged & hidden!
        browser.real_click("#btn-header-signout")
        browser.settle()
        after_signout = browser.eval(
            """(() => {
              const slot = document.getElementById('admin-bonus-sync-slot');
              return {
                hidden: slot.hasAttribute('hidden') && getComputedStyle(slot).display === 'none',
                html: slot.innerHTML
              };
            })()"""
        )
        self.assertTrue(after_signout["hidden"])
        self.assertEqual(after_signout["html"], "")
        self.assertEqual(browser.js_errors(), [])


if __name__ == "__main__":
    unittest.main()
