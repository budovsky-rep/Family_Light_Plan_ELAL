/**
 * Safe Auto-Pilot & Passive DOM Table Reader Content Script (`chrome_extension/content.js`)
 *
 * Runs in BOTH:
 * 1. Extension `ISOLATED` world (manages the UI widget & sends parsed rows to `background.js`).
 * 2. Page `MAIN` world (directly updates El Al's jQuery Datepicker & AngularJS `ngModel` state
 *    so that Departure Date & Return Date genuinely update to the target Holiday window).
 */

(function () {
  "use strict";

  const MONTHS_MAP = {
    jan: "01", feb: "02", mar: "03", apr: "04", may: "05", jun: "06",
    jul: "07", aug: "08", sep: "09", oct: "10", nov: "11", dec: "12"
  };

  const isIsolatedExtensionWorld =
    typeof chrome !== "undefined" &&
    Boolean(chrome.runtime) &&
    typeof chrome.runtime.sendMessage === "function";

  function parseElAlTableDate(rawDateStr) {
    if (!rawDateStr) return null;
    const s = String(rawDateStr).trim();
    const isoMatch = s.match(/(\d{4})-(\d{2})-(\d{2})/);
    if (isoMatch) return `${isoMatch[1]}-${isoMatch[2]}-${isoMatch[3]}`;

    const dmyMatch = s.match(/(\d{1,2})[\s\-]+([A-Za-z]{3,9})[\s\-]+(\d{4})/);
    if (dmyMatch) {
      const day = String(dmyMatch[1]).padStart(2, "0");
      const monPrefix = dmyMatch[2].slice(0, 3).toLowerCase();
      const mon = MONTHS_MAP[monPrefix];
      const year = dmyMatch[3];
      if (mon) return `${year}-${mon}-${day}`;
    }
    return null;
  }

  function parseElAlDateToJsDate(rawDateStr) {
    const iso = parseElAlTableDate(rawDateStr);
    if (!iso) return null;
    const [y, m, d] = iso.split("-").map((n) => parseInt(n, 10));
    return new Date(y, m - 1, d, 12, 0, 0);
  }

  function findVisibleElAlDateInputs(classSelects) {
    const taggedDep = document.querySelector("input[data-fvp-date-role='departure']");
    const taggedRet = document.querySelector("input[data-fvp-date-role='return']");
    if (taggedDep && taggedRet) {
      return [taggedDep, taggedRet];
    }

    const visibleInputs = Array.from(document.querySelectorAll("input")).filter((inp) => {
      const type = (inp.type || "text").toLowerCase();
      if (type === "hidden" || type === "checkbox" || type === "radio" || type === "submit" || type === "button") {
        return false;
      }
      const rect = inp.getBoundingClientRect();
      return rect.width > 30 && rect.height > 15;
    });

    // Primary match: visible inputs whose value matches El Al's DD-Month-YYYY format (e.g. "17-November-2026")
    const formatMatched = visibleInputs.filter((inp) =>
      /\d{1,2}-[A-Za-z]{3,9}-\d{4}/.test((inp.value || "").trim())
    );

    const chosen = formatMatched.length >= 2 ? formatMatched.slice(0, 2) : visibleInputs.slice(0, 2);
    if (chosen[0]) chosen[0].setAttribute("data-fvp-date-role", "departure");
    if (chosen[1]) chosen[1].setAttribute("data-fvp-date-role", "return");
    return chosen;
  }

  function findElAlFormControls() {
    const selects = Array.from(document.querySelectorAll("select")).filter((s) => {
      const rect = s.getBoundingClientRect();
      return rect.width > 30 && rect.height > 15;
    });
    const airportSelects = selects.filter((s) =>
      Array.from(s.options || []).some((o) => /\[[A-Z]{3}\]/.test(o.text) || /choose airport/i.test(o.text))
    );
    const classSelects = selects.filter((s) =>
      Array.from(s.options || []).some((o) => /economy|premium|business|תיירים|פרימיום|עסקים/i.test(o.text))
    );
    const dateInputs = findVisibleElAlDateInputs(classSelects);

    const searchBtn = Array.from(
      document.querySelectorAll("button, input[type='button'], input[type='submit'], a.btn")
    ).find((b) => {
      const rect = b.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return false;
      const txt = (b.innerText || b.value || "").trim();
      return /^search$/i.test(txt) || /חיפוש/.test(txt);
    });

    return {
      depFromSelect: airportSelects[0] || null,
      depToSelect: airportSelects[1] || null,
      retFromSelect: airportSelects[2] || null,
      retToSelect: airportSelects[3] || null,
      depClassSelect: classSelects[0] || null,
      retClassSelect: classSelects[1] || null,
      depDateInput: dateInputs[0] || null,
      retDateInput: dateInputs[1] || null,
      searchBtn: searchBtn || null
    };
  }

  function setNativeValue(el, newValue) {
    if (!el) return false;
    try {
      if (el.tagName === "INPUT") {
        el.removeAttribute("readonly");
      }
      const proto =
        el.tagName === "SELECT"
          ? window.HTMLSelectElement.prototype
          : window.HTMLInputElement.prototype;
      const desc = Object.getOwnPropertyDescriptor(proto, "value");
      if (desc && desc.set) {
        desc.set.call(el, newValue);
      } else {
        el.value = newValue;
      }
      el.setAttribute("value", newValue);
    } catch (_err) {
      el.value = newValue;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  function updateDateInputWithPageFrameworks(inp, dateStr) {
    if (!inp || !dateStr) return;
    const jsDate = parseElAlDateToJsDate(dateStr);
    setNativeValue(inp, dateStr);

    const jq = window.jQuery || window.$;
    if (typeof jq === "function") {
      try {
        const $inp = jq(inp);
        const $group = $inp.closest(".input-group, .date");
        if (typeof $inp.datepicker === "function") {
          if (jsDate) {
            try { $inp.datepicker("setDate", jsDate); } catch (_e) {}
          }
          try { $inp.datepicker("update", dateStr); } catch (_e) {}
        }
        if ($group.length && typeof $group.datepicker === "function") {
          if (jsDate) {
            try { $group.datepicker("setDate", jsDate); } catch (_e) {}
          }
          try { $group.datepicker("update", dateStr); } catch (_e) {}
        }
        $inp.val(dateStr);
        $inp.trigger("input").trigger("change").trigger("changeDate");
        jq(".datepicker, .ui-datepicker, .bootstrap-datetimepicker-widget").hide();
      } catch (_jqErr) {}
    }

    if (window.angular && typeof window.angular.element === "function") {
      try {
        const ngEl = window.angular.element(inp);
        const ngModel = ngEl.controller && ngEl.controller("ngModel");
        if (ngModel) {
          ngModel.$setViewValue(dateStr);
          if (typeof ngModel.$commitViewValue === "function") {
            ngModel.$commitViewValue();
          }
          if (typeof ngModel.$render === "function") {
            ngModel.$render();
          }
        }
        const scope =
          (ngEl.isolateScope && ngEl.isolateScope()) ||
          (ngEl.scope && ngEl.scope());
        if (scope && typeof scope.$applyAsync === "function") {
          scope.$applyAsync();
        }
      } catch (_ngErr) {}
    }

    setNativeValue(inp, dateStr);
    inp.dispatchEvent(new Event("blur", { bubbles: true }));
  }

  function selectDropdownOptionWithFrameworks(selectEl, matcherFn) {
    if (!selectEl || !selectEl.options) return false;
    for (let i = 0; i < selectEl.options.length; i++) {
      const opt = selectEl.options[i];
      if (matcherFn(opt)) {
        selectEl.selectedIndex = i;
        setNativeValue(selectEl, opt.value);
        const jq = window.jQuery || window.$;
        if (typeof jq === "function") {
          try {
            jq(selectEl).val(opt.value).trigger("change");
          } catch (_e) {}
        }
        if (window.angular && typeof window.angular.element === "function") {
          try {
            const ngEl = window.angular.element(selectEl);
            const ngModel = ngEl.controller && ngEl.controller("ngModel");
            if (ngModel) {
              ngModel.$setViewValue(opt.value);
              if (typeof ngModel.$render === "function") ngModel.$render();
            }
            const scope = (ngEl.isolateScope && ngEl.isolateScope()) || (ngEl.scope && ngEl.scope());
            if (scope && typeof scope.$applyAsync === "function") scope.$applyAsync();
          } catch (_e) {}
        }
        return true;
      }
    }
    return false;
  }

  // ============================================================================
  // MAIN WORLD BRIDGE: Executes inside El Al's page context with access to $/angular
  // ============================================================================
  if (!isIsolatedExtensionWorld) {
    window.addEventListener("message", async (ev) => {
      if (!ev.data || ev.data.source !== "FVP_ISO_TO_MAIN") return;

      if (ev.data.type === "SET_FORM_AND_SEARCH") {
        const { reqId, destIata, cabinName, depDate, retDate } = ev.data;
        const sleepMain = (ms) => new Promise((r) => setTimeout(r, ms));
        const targetToken = `[${String(destIata || "").toUpperCase()}]`;

        const c1 = findElAlFormControls();
        if (c1.depDateInput && depDate) updateDateInputWithPageFrameworks(c1.depDateInput, depDate);
        if (c1.retDateInput && retDate) updateDateInputWithPageFrameworks(c1.retDateInput, retDate);
        await sleepMain(80);

        selectDropdownOptionWithFrameworks(
          c1.depFromSelect,
          (opt) => (opt.text || "").toUpperCase().includes("[TLV]") || (opt.value || "").toUpperCase() === "TLV"
        );
        const okOut = selectDropdownOptionWithFrameworks(
          c1.depToSelect,
          (opt) => (opt.text || "").toUpperCase().includes(targetToken) || (opt.value || "").toUpperCase() === destIata.toUpperCase()
        );
        await sleepMain(120);

        const c2 = findElAlFormControls();
        selectDropdownOptionWithFrameworks(
          c2.retFromSelect,
          (opt) => (opt.text || "").toUpperCase().includes(targetToken) || (opt.value || "").toUpperCase() === destIata.toUpperCase()
        );
        selectDropdownOptionWithFrameworks(
          c2.retToSelect,
          (opt) => (opt.text || "").toUpperCase().includes("[TLV]") || (opt.value || "").toUpperCase() === "TLV"
        );
        selectDropdownOptionWithFrameworks(
          c2.depClassSelect,
          (opt) => (opt.text || "").toLowerCase().includes(cabinName.toLowerCase())
        );
        selectDropdownOptionWithFrameworks(
          c2.retClassSelect,
          (opt) => (opt.text || "").toLowerCase().includes(cabinName.toLowerCase())
        );

        // Re-apply dates right before clicking Search in case airport/cabin change reset them
        if (c2.depDateInput && depDate) updateDateInputWithPageFrameworks(c2.depDateInput, depDate);
        if (c2.retDateInput && retDate) updateDateInputWithPageFrameworks(c2.retDateInput, retDate);
        await sleepMain(120);

        const actualDep = c2.depDateInput ? c2.depDateInput.value : "";
        const actualRet = c2.retDateInput ? c2.retDateInput.value : "";

        if (okOut && c2.searchBtn) {
          c2.searchBtn.click();
        }

        window.postMessage(
          {
            source: "FVP_MAIN_TO_ISO",
            reqId: reqId,
            okOut: okOut,
            actualDep: actualDep,
            actualRet: actualRet
          },
          "*"
        );
      }
    });
    return;
  }

  // ============================================================================
  // ISOLATED EXTENSION WORLD: Widget UI, Auto-Pilot Loop & Server Sync
  // ============================================================================

  // Strictly Israeli Holiday & MoE School Vacation windows (Departure Date, Return Date in El Al format DD-Month-YYYY)
  const YEARLY_HOLIDAY_WINDOWS = [
    { label: "חנוכה 2026", dep: "06-December-2026", ret: "13-December-2026" },
    { label: "פורים 2027", dep: "22-March-2027", ret: "28-March-2027" },
    { label: "פסח 2027 (לפני ליל הסדר וחג ראשון)", dep: "11-April-2027", ret: "18-April-2027" },
    { label: "פסח 2027 (חול המועד וחג שני)", dep: "20-April-2027", ret: "28-April-2027" },
    { label: "יום העצמאות 2027", dep: "10-May-2027", ret: "16-May-2027" },
    { label: "שבועות ויוני 2027", dep: "10-June-2027", ret: "28-June-2027" },
    { label: "החופש הגדול — יולי 2027", dep: "12-July-2027", ret: "20-July-2027" },
    { label: "החופש הגדול — אוגוסט 2027", dep: "16-August-2027", ret: "24-August-2027" },
    { label: "ראש השנה וסוכות 2027", dep: "01-October-2027", ret: "24-October-2027" }
  ];

  const PRIORITY_IATAS = [
    "FCO", "ATH", "LCA", "RHO", "PFO", "MAD", "BCN", "CDG", "LHR", "LTN",
    "AMS", "BER", "MUC", "VIE", "BUD", "PRG", "MXP", "ZRH", "TBS",
    "BKK", "HKT", "NRT", "JFK", "EWR", "MIA", "FLL"
  ];

  const TARGET_CABINS = ["Economy", "Premium"];

  let autoPilotRunning = false;
  let totalSyncedCount = 0;
  let lastSyncedSignature = "";
  let bridgeReqSeq = 0;

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function isRowDateNearHolidayWindow(rowDateIso, win) {
    if (!win || !win.dep || !win.ret) return true;
    const rowDt = parseElAlDateToJsDate(rowDateIso);
    const depDt = parseElAlDateToJsDate(win.dep);
    const retDt = parseElAlDateToJsDate(win.ret);
    if (!rowDt || !depDt || !retDt) return true;
    const minMs = depDt.getTime() - 21 * 86400 * 1000;
    const maxMs = retDt.getTime() + 21 * 86400 * 1000;
    return rowDt.getTime() >= minMs && rowDt.getTime() <= maxMs;
  }

  function detectSelectedCabinOnPage() {
    const selects = Array.from(document.querySelectorAll("select"));
    for (const sel of selects) {
      const val = (sel.value || "").toLowerCase();
      const txt = (sel.options && sel.selectedIndex >= 0 ? sel.options[sel.selectedIndex].text : "").toLowerCase();
      const combined = `${val} ${txt}`;
      if (combined.includes("business") || combined.includes("עסקים")) return "BUSINESS";
      if (combined.includes("premium") || combined.includes("פרימיום")) return "PREMIUM";
      if (combined.includes("economy") || combined.includes("תיירים")) return "ECONOMY";
    }
    return "ECONOMY";
  }

  function extractVisibleTableRows(explicitCabinUpper, activeHolidayWindow) {
    const cabin = explicitCabinUpper || detectSelectedCabinOnPage();
    if (cabin === "BUSINESS") return [];
    const extracted = [];
    const trList = Array.from(document.querySelectorAll("table tr, .table tr, [role='row']"));

    for (const tr of trList) {
      const cells = Array.from(tr.querySelectorAll("td, [role='cell']")).map((c) =>
        (c.innerText || c.textContent || "").trim()
      );
      if (cells.length >= 7) {
        const rowDate = parseElAlTableDate(cells[3]);
        if (!rowDate) continue;
        if (activeHolidayWindow && !isRowDateNearHolidayWindow(rowDate, activeHolidayWindow)) {
          continue;
        }

        const outFlight = cells[0].replace(/\s+/g, "");
        const outRoute = cells[1].replace(/\s+/g, "").toUpperCase();
        const outAvail = parseInt(cells[2], 10);
        if (outFlight && outRoute.includes("-") && !isNaN(outAvail) && outAvail > 0) {
          const [orig, dest] = outRoute.split("-");
          extracted.push({
            destination_iata: orig === "TLV" ? dest : orig,
            direction: dest === "TLV" ? "INBOUND" : "OUTBOUND",
            flight_number: outFlight,
            flight_date: rowDate,
            economy_seats: cabin === "ECONOMY" ? outAvail : 0,
            premium_seats: cabin === "PREMIUM" ? outAvail : 0,
            business_seats: 0
          });
        }

        const inFlight = cells[4].replace(/\s+/g, "");
        const inRoute = cells[5].replace(/\s+/g, "").toUpperCase();
        const inAvail = parseInt(cells[6], 10);
        if (inFlight && inRoute.includes("-") && !isNaN(inAvail) && inAvail > 0) {
          const [orig, dest] = inRoute.split("-");
          extracted.push({
            destination_iata: orig === "TLV" ? dest : orig,
            direction: dest === "TLV" ? "INBOUND" : "OUTBOUND",
            flight_number: inFlight,
            flight_date: rowDate,
            economy_seats: cabin === "ECONOMY" ? inAvail : 0,
            premium_seats: cabin === "PREMIUM" ? inAvail : 0,
            business_seats: 0
          });
        }
      }
    }
    return extracted;
  }

  function sendRowsToServerPromise(rows) {
    return new Promise((resolve) => {
      if (!rows || rows.length === 0) {
        resolve({ ok: true, records_synced: 0, destinations: [] });
        return;
      }
      chrome.runtime.sendMessage(
        {
          action: "SYNC_ELAL_ROWS",
          serverUrl: "http://34.165.250.15:8080",
          rows: rows
        },
        (resp) => {
          resolve(resp || { ok: false, error: "No response from extension worker" });
        }
      );
    });
  }

  function syncVisibleRowsPassive() {
    if (autoPilotRunning) return;
    const rows = extractVisibleTableRows();
    if (rows.length === 0) return;
    const sig = JSON.stringify(rows);
    if (sig === lastSyncedSignature) return;
    lastSyncedSignature = sig;

    const statusEl = document.getElementById("fvp-sync-status");
    sendRowsToServerPromise(rows).then((resp) => {
      if (resp && resp.ok) {
        totalSyncedCount += Number(resp.records_synced || rows.length);
        if (statusEl) {
          statusEl.textContent = `✅ סונכרנו אוטומטית ${resp.records_synced} טיסות (${(resp.destinations || []).join(", ")}) לשרת!`;
        }
      }
    });
  }

  function discoverAvailableDestinations(depToSelect) {
    if (!depToSelect || !depToSelect.options) return PRIORITY_IATAS;
    const foundIatas = [];
    for (const opt of Array.from(depToSelect.options)) {
      const m = (opt.text || "").match(/\[([A-Z]{3})\]/);
      if (m && m[1] !== "TLV" && !foundIatas.includes(m[1])) {
        foundIatas.push(m[1]);
      }
    }
    if (foundIatas.length === 0) return PRIORITY_IATAS;
    const priorityAvailable = PRIORITY_IATAS.filter((c) => foundIatas.includes(c));
    return priorityAvailable.length > 0 ? priorityAvailable : PRIORITY_IATAS;
  }

  function triggerMainWorldFormStep(destIata, cabinName, depDate, retDate) {
    return new Promise((resolve) => {
      const reqId = ++bridgeReqSeq;
      let settled = false;

      const onMsg = (ev) => {
        if (!ev.data || ev.data.source !== "FVP_MAIN_TO_ISO" || ev.data.reqId !== reqId) return;
        settled = true;
        window.removeEventListener("message", onMsg);
        resolve(ev.data);
      };
      window.addEventListener("message", onMsg);

      window.postMessage(
        {
          source: "FVP_ISO_TO_MAIN",
          type: "SET_FORM_AND_SEARCH",
          reqId: reqId,
          destIata: destIata,
          cabinName: cabinName,
          depDate: depDate,
          retDate: retDate
        },
        "*"
      );

      // Fallback in case MAIN world script wasn't loaded yet
      setTimeout(() => {
        if (settled) return;
        settled = true;
        window.removeEventListener("message", onMsg);
        const c = findElAlFormControls();
        if (c.depDateInput && depDate) updateDateInputWithPageFrameworks(c.depDateInput, depDate);
        if (c.retDateInput && retDate) updateDateInputWithPageFrameworks(c.retDateInput, retDate);
        const targetToken = `[${destIata.toUpperCase()}]`;
        selectDropdownOptionWithFrameworks(c.depFromSelect, (o) => (o.text || "").includes("[TLV]"));
        const okOut = selectDropdownOptionWithFrameworks(c.depToSelect, (o) => (o.text || "").includes(targetToken));
        selectDropdownOptionWithFrameworks(c.retFromSelect, (o) => (o.text || "").includes(targetToken));
        selectDropdownOptionWithFrameworks(c.retToSelect, (o) => (o.text || "").includes("[TLV]"));
        selectDropdownOptionWithFrameworks(c.depClassSelect, (o) => (o.text || "").toLowerCase().includes(cabinName.toLowerCase()));
        selectDropdownOptionWithFrameworks(c.retClassSelect, (o) => (o.text || "").toLowerCase().includes(cabinName.toLowerCase()));
        if (c.depDateInput && depDate) updateDateInputWithPageFrameworks(c.depDateInput, depDate);
        if (c.retDateInput && retDate) updateDateInputWithPageFrameworks(c.retDateInput, retDate);
        if (okOut && c.searchBtn) c.searchBtn.click();
        resolve({
          okOut: okOut,
          actualDep: c.depDateInput ? c.depDateInput.value : depDate,
          actualRet: c.retDateInput ? c.retDateInput.value : retDate
        });
      }, 650);
    });
  }

  async function runAutoPilot() {
    const statusEl = document.getElementById("fvp-sync-status");
    const btnEl = document.getElementById("fvp-sync-btn");

    if (autoPilotRunning) {
      autoPilotRunning = false;
      if (btnEl) {
        btnEl.textContent = "🤖 הפעל סריקת חגים אוטומטית (Economy + Premium)";
        btnEl.style.background = "#10b981";
      }
      if (statusEl) {
        statusEl.textContent = `⏸️ הסריקה נעצרה. סה"כ סונכרנו ${totalSyncedCount} טיסות חגים לשרת.`;
      }
      return;
    }

    try {
      const initialControls = findElAlFormControls();
      if (!initialControls.depToSelect || !initialControls.searchBtn) {
        if (statusEl) {
          statusEl.textContent = "⚠️ לא נמצא טופס החיפוש של אל על בדף זה (וודא שהדף נטען במלואו).";
        }
        return;
      }

      autoPilotRunning = true;
      if (btnEl) {
        btnEl.textContent = "⏹️ עצור סריקה אוטומטית (Auto-Pilot פעיל)";
        btnEl.style.background = "#ef4444";
      }

      const destinations = discoverAvailableDestinations(initialControls.depToSelect);
      const windowsToScan = YEARLY_HOLIDAY_WINDOWS;

      for (let wIdx = 0; wIdx < windowsToScan.length && autoPilotRunning; wIdx++) {
        const win = windowsToScan[wIdx];

        for (let dIdx = 0; dIdx < destinations.length && autoPilotRunning; dIdx++) {
          const destIata = destinations[dIdx];
          for (const cabinName of TARGET_CABINS) {
            if (!autoPilotRunning) break;

            const stepRes = await triggerMainWorldFormStep(destIata, cabinName, win.dep, win.ret);
            if (!stepRes || !stepRes.okOut) continue;

            if (statusEl) {
              statusEl.textContent = `🤖 חג [${wIdx + 1}/${windowsToScan.length}] ${win.label} (טופס: ${stepRes.actualDep || win.dep}) | יעד ${dIdx + 1}/${destinations.length}: ${destIata} (${cabinName}) | סונכרנו: ${totalSyncedCount}`;
            }

            const politeWaitMs = 5200 + Math.floor(Math.random() * 1200);
            await sleep(politeWaitMs);

            if (!autoPilotRunning) break;

            const rows = extractVisibleTableRows(cabinName.toUpperCase(), win);
            if (rows.length > 0) {
              const resp = await sendRowsToServerPromise(rows);
              if (resp && resp.ok) {
                totalSyncedCount += Number(resp.records_synced || rows.length);
              }
            }
          }
        }
      }

      autoPilotRunning = false;
      if (btnEl) {
        btnEl.textContent = "🤖 הפעל סריקת חגים אוטומטית (Economy + Premium)";
        btnEl.style.background = "#10b981";
      }
      if (statusEl) {
        statusEl.textContent = `🎉 סריקת החגים הושלמה! סה"כ סונכרנו ${totalSyncedCount} טיסות חגים אמיתיות לשרת.`;
      }
    } catch (err) {
      autoPilotRunning = false;
      if (btnEl) {
        btnEl.textContent = "🤖 הפעל סריקת חגים אוטומטית (Economy + Premium)";
        btnEl.style.background = "#10b981";
      }
      if (statusEl) {
        statusEl.textContent = `❌ שגיאה בסריקה: ${String(err && err.message ? err.message : err)}`;
      }
    }
  }

  function createFloatingBadge() {
    if (document.getElementById("fvp-sync-widget")) return;
    const box = document.createElement("div");
    box.id = "fvp-sync-widget";
    box.dir = "rtl";
    box.style.cssText = [
      "position: fixed",
      "bottom: 18px",
      "right: 18px",
      "z-index: 999999",
      "background: #0f172a",
      "color: #ffffff",
      "padding: 14px 16px",
      "border-radius: 14px",
      "box-shadow: 0 10px 25px rgba(15,23,42,0.35)",
      "font-family: -apple-system, BlinkMacSystemFont, sans-serif",
      "font-size: 13px",
      "display: flex",
      "flex-direction: column",
      "gap: 8px",
      "min-width: 300px",
      "max-width: 380px",
      "border: 1px solid rgba(56,189,248,0.4)"
    ].join(";");

    box.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
        <strong>✈️ סנכרון חגים (Economy + Premium)</strong>
        <span style="font-size:11px;background:#0284c7;padding:2px 8px;border-radius:999px;">קצב אנושי בטוח</span>
      </div>
      <div id="fvp-sync-status" style="font-size:12px;color:#cbd5e1;line-height:1.4;">
        מוכן לסריקה אוטומטית של חגי ישראל (Economy ו-Premium) ב-26 יעדי אל על אל השרת.
      </div>
      <button id="fvp-sync-btn" type="button" style="background:#10b981;color:#fff;border:none;border-radius:8px;padding:8px 12px;font-weight:700;cursor:pointer;font-size:12.5px;">
        🤖 הפעל סריקת חגים אוטומטית (Economy + Premium)
      </button>
    `;
    document.body.appendChild(box);

    const btn = document.getElementById("fvp-sync-btn");
    if (btn) {
      btn.addEventListener("click", () => runAutoPilot());
    }
  }

  createFloatingBadge();

  const observer = new MutationObserver(() => {
    createFloatingBadge();
    syncVisibleRowsPassive();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();
