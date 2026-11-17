/**
 * Passive DOM Table Reader Content Script (`chrome_extension/content.js`)
 *
 * Runs on `https://www.elal.com/rbddataclients/*`:
 * - Does NOT modify `window.fetch` or `XMLHttpRequest` and makes ZERO network requests to `elal.com`.
 * - Reads the visible HTML table rows rendered by El Al on the page (`LY0397`, `TLV-MAD`, `2`, `Mon, 26 Apr 2027`)
 *   and forwards them to `background.js` -> `http://34.165.250.15:8080/api/v1/elal-bonus/sync`.
 */

(function () {
  "use strict";

  const MONTHS_MAP = {
    jan: "01", feb: "02", mar: "03", apr: "04", may: "05", jun: "06",
    jul: "07", aug: "08", sep: "09", oct: "10", nov: "11", dec: "12"
  };

  function parseElAlTableDate(rawDateStr) {
    if (!rawDateStr) return null;
    const s = String(rawDateStr).trim();
    // Match e.g. "Mon, 26 Apr 2027" or "26 Apr 2027" or "2027-04-26"
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
    const bodyText = document.body ? document.body.innerText : "";
    for (const sel of selects) {
      const val = (sel.value || "").toLowerCase();
      const txt = (sel.options && sel.selectedIndex >= 0 ? sel.options[sel.selectedIndex].text : "").toLowerCase();
      const combined = `${val} ${txt}`;
      if (combined.includes("business") || combined.includes("עסקים")) return "BUSINESS";
      if (combined.includes("premium") || combined.includes("פרימיום")) return "PREMIUM";
      if (combined.includes("economy") || combined.includes("תיירים")) return "ECONOMY";
    }
    if (bodyText.includes("Business")) return "ECONOMY";
    return "ECONOMY";
  }

  function extractVisibleTableRows() {
    const cabin = detectSelectedCabinOnPage();
    const extracted = [];
    const trList = Array.from(document.querySelectorAll("table tr, .table tr, [role='row']"));

    for (const tr of trList) {
      const cells = Array.from(tr.querySelectorAll("td, [role='cell']")).map((c) =>
        (c.innerText || c.textContent || "").trim()
      );
      if (cells.length < 4) continue;

      // Standard El Al 7-column split row:
      // [0] Outbound Flight (e.g. LY0397) | [1] Outbound Route (TLV-MAD) | [2] Outbound Avail (2)
      // | [3] Date (Mon, 26 Apr 2027) |
      // [4] Return Flight (LY0398)       | [5] Return Route (MAD-TLV)   | [6] Return Avail (2)
      if (cells.length >= 7) {
        const rowDate = parseElAlTableDate(cells[3]);
        if (!rowDate) continue;

        // Check Outbound columns (0, 1, 2)
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
            business_seats: cabin === "BUSINESS" ? outAvail : 0
          });
        }

        // Check Inbound columns (4, 5, 6)
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
            business_seats: cabin === "BUSINESS" ? inAvail : 0
          });
        }
      }
    }
    return extracted;
  }

  let lastSyncedSignature = "";

  function syncVisibleRows(isManualClick) {
    const statusEl = document.getElementById("fvp-sync-status");
    const rows = extractVisibleTableRows();
    if (rows.length === 0) {
      if (isManualClick && statusEl) {
        statusEl.textContent = "⚠️ לא נמצאו טיסות בטבלה שעל המסך כרגע";
      }
      return;
    }

    const sig = JSON.stringify(rows);
    if (!isManualClick && sig === lastSyncedSignature) {
      return;
    }
    lastSyncedSignature = sig;

    if (statusEl) {
      statusEl.textContent = `⏳ מסנכרן ${rows.length} טיסות לשרת...`;
    }

    chrome.runtime.sendMessage(
      {
        action: "SYNC_ELAL_ROWS",
        serverUrl: "http://34.165.250.15:8080",
        rows: rows
      },
      (resp) => {
        if (!statusEl) return;
        if (resp && resp.ok) {
          statusEl.textContent = `✅ סונכרנו ${resp.records_synced} טיסות (${(resp.destinations || []).join(", ")}) לשרת!`;
        } else {
          statusEl.textContent = `❌ שגיאה: ${(resp && resp.error) || "נכשל"}`;
        }
      }
    );
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
      "padding: 12px 16px",
      "border-radius: 14px",
      "box-shadow: 0 10px 25px rgba(15,23,42,0.35)",
      "font-family: -apple-system, BlinkMacSystemFont, sans-serif",
      "font-size: 13px",
      "display: flex",
      "flex-direction: column",
      "gap: 8px",
      "min-width: 260px",
      "border: 1px solid rgba(56,189,248,0.4)"
    ].join(";");

    box.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
        <strong>✈️ סנכרון מתכנן חופשות</strong>
        <span style="font-size:11px;background:#0284c7;padding:2px 8px;border-radius:999px;">פסיבי ובטוח</span>
      </div>
      <div id="fvp-sync-status" style="font-size:12px;color:#cbd5e1;">
        ממתין לתוצאות חיפוש בטבלה של אל על...
      </div>
      <button id="fvp-sync-btn" type="button" style="background:#10b981;color:#fff;border:none;border-radius:8px;padding:7px 12px;font-weight:700;cursor:pointer;font-size:12.5px;">
        📤 שלח את הטבלה שעל המסך לשרת עכשיו
      </button>
    `;
    document.body.appendChild(box);

    const btn = document.getElementById("fvp-sync-btn");
    if (btn) {
      btn.addEventListener("click", () => syncVisibleRows(true));
    }
  }

  createFloatingBadge();

  // Passively observe DOM changes so whenever you click "Search" on El Al's page
  // and the table renders, it automatically syncs the visible rows to your server!
  const observer = new MutationObserver(() => {
    createFloatingBadge();
    syncVisibleRows(false);
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();
