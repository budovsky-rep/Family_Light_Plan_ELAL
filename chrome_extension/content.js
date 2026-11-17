/**
 * Safe Auto-Pilot & Passive DOM Table Reader Content Script (`chrome_extension/content.js`)
 *
 * Runs on `https://www.elal.com/rbddataclients/*`:
 * - Makes ZERO direct `fetch` or `XHR` requests to `elal.com` (preventing 401/474 WAF blocks).
 * - Focuses strictly on Israeli Holidays & Ministry of Education Vacations (`YEARLY_HOLIDAY_WINDOWS`),
 *   strictly on `Economy` and `Premium` cabins (skipping `Business`), and strictly on our 26 core El Al destinations.
 * - Drives El Al's own form dropdowns & blue "Search" button at a safe, human pace (5.2s–6.4s per step),
 *   lets El Al render the table normally, reads the visible DOM rows, and sends them to
 *   `http://34.165.250.15:8080/api/v1/elal-bonus/sync`.
 */

(function () {
  "use strict";

  const MONTHS_MAP = {
    jan: "01", feb: "02", mar: "03", apr: "04", may: "05", jun: "06",
    jul: "07", aug: "08", sep: "09", oct: "10", nov: "11", dec: "12"
  };

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

  // Core El Al destinations supported by Family Vacation Planner
  const PRIORITY_IATAS = [
    "FCO", "ATH", "LCA", "RHO", "PFO", "MAD", "BCN", "CDG", "LHR", "LTN",
    "AMS", "BER", "MUC", "VIE", "BUD", "PRG", "MXP", "ZRH", "TBS",
    "BKK", "HKT", "NRT", "JFK", "EWR", "MIA", "FLL"
  ];

  // Scan only Economy and Premium cabins as requested
  const TARGET_CABINS = ["Economy", "Premium"];

  let autoPilotRunning = false;
  let totalSyncedCount = 0;
  let lastSyncedSignature = "";

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

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

  function extractVisibleTableRows(explicitCabinUpper) {
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

  function findElAlFormControls() {
    const selects = Array.from(document.querySelectorAll("select"));
    const airportSelects = selects.filter((s) =>
      Array.from(s.options || []).some((o) => /\[[A-Z]{3}\]/.test(o.text) || /choose airport/i.test(o.text))
    );
    const classSelects = selects.filter((s) =>
      Array.from(s.options || []).some((o) => /economy|premium|business|תיירים|פרימיום|עסקים/i.test(o.text))
    );
    const allInputs = Array.from(document.querySelectorAll("input"));
    const strictDateInputs = allInputs.filter((inp) => {
      const v = (inp.value || "") + " " + (inp.placeholder || "") + " " + (inp.id || "") + " " + (inp.name || "");
      return /\d{1,2}-[A-Za-z]+-\d{4}/.test(v) || /date/i.test(v);
    });
    const dateInputs =
      strictDateInputs.length >= 2
        ? strictDateInputs
        : allInputs.filter((inp) => inp.type === "text" || inp.type === "date");

    const searchBtn = Array.from(document.querySelectorAll("button, input[type='button'], input[type='submit'], a.btn")).find(
      (b) => /^\s*search\s*$/i.test(b.innerText || b.value || "") || /חיפוש/.test(b.innerText || b.value || "")
    );

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

  function setFormElementValue(el, newValue) {
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
    el.dispatchEvent(new Event("focus", { bubbles: true }));
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, key: "Enter", keyCode: 13 }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
    return true;
  }

  function selectAirportByIata(selectEl, iataCode) {
    if (!selectEl || !selectEl.options) return false;
    const targetToken = `[${iataCode.toUpperCase()}]`;
    for (let i = 0; i < selectEl.options.length; i++) {
      const opt = selectEl.options[i];
      if ((opt.text || "").toUpperCase().includes(targetToken) || (opt.value || "").toUpperCase() === iataCode.toUpperCase()) {
        selectEl.selectedIndex = i;
        setFormElementValue(selectEl, opt.value);
        return true;
      }
    }
    return false;
  }

  function selectCabinClass(selectEl, cabinName) {
    if (!selectEl || !selectEl.options) return false;
    for (let i = 0; i < selectEl.options.length; i++) {
      const opt = selectEl.options[i];
      if ((opt.text || "").toLowerCase().includes(cabinName.toLowerCase())) {
        selectEl.selectedIndex = i;
        setFormElementValue(selectEl, opt.value);
        return true;
      }
    }
    return false;
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
    // Strictly scan our 26 core El Al destinations (`PRIORITY_IATAS`) so we don't waste time on secondary codeshares
    const priorityAvailable = PRIORITY_IATAS.filter((c) => foundIatas.includes(c));
    return priorityAvailable.length > 0 ? priorityAvailable : PRIORITY_IATAS;
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

            const cStep = findElAlFormControls();
            selectAirportByIata(cStep.depFromSelect, "TLV");
            const okOut = selectAirportByIata(cStep.depToSelect, destIata);
            await sleep(120);

            const cAfterOut = findElAlFormControls();
            selectAirportByIata(cAfterOut.retFromSelect, destIata);
            selectAirportByIata(cAfterOut.retToSelect, "TLV");
            selectCabinClass(cAfterOut.depClassSelect, cabinName);
            selectCabinClass(cAfterOut.retClassSelect, cabinName);

            // Always set holiday dates AFTER airport & cabin selection so El Al's form does not reset them
            if (cAfterOut.depDateInput && win.dep) setFormElementValue(cAfterOut.depDateInput, win.dep);
            if (cAfterOut.retDateInput && win.ret) setFormElementValue(cAfterOut.retDateInput, win.ret);
            await sleep(120);

            if (!okOut) continue;

            if (statusEl) {
              statusEl.textContent = `🤖 חג [${wIdx + 1}/${windowsToScan.length}] ${win.label} (${win.dep}) | יעד ${dIdx + 1}/${destinations.length}: ${destIata} (${cabinName}) | סונכרנו: ${totalSyncedCount}`;
            }

            if (cAfterOut.searchBtn) {
              cAfterOut.searchBtn.click();
            }

            const politeWaitMs = 5200 + Math.floor(Math.random() * 1200);
            await sleep(politeWaitMs);

            if (!autoPilotRunning) break;

            const rows = extractVisibleTableRows(cabinName.toUpperCase());
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
        statusEl.textContent = `🎉 סריקת החגים הושלמה! סה"כ סונכרנו ${totalSyncedCount} טיסות אמיתיות לשרת.`;
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
