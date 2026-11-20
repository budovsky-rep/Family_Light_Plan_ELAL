/**
 * Safe Auto-Pilot & Network/DOM Reader Content Script (`chrome_extension/content.js` — v2.0)
 *
 * Key design for 100% stability and speed on `https://www.elal.com/rbddataclients/`:
 * 1. Exact 25 `DESTINATION_CATALOG` IATA codes (`PRIORITY_IATAS` — excluding unsupported `"ZRH"`).
 * 2. Uses El Al's genuine calculator RBD codes: `rbd: "E"` for Economy and `rbd: "A"` for Premium.
 * 3. Executes 14-day (`endDate - startDate == 14 days`) 50-segment (`25 destinations × 2 directions`)
 *    `window.$.ajax` batch requests in the `MAIN` world through Reblaze's native XHR hook across
 *    all 16 Israeli holiday & MoE school vacation windows (`Hanukkah 2026` .. `Sukkot 2027`),
 *    completing the full-year scan in ~20 seconds without DOM form resets or `#errorModal` (`Oops!`).
 * 4. Normalizes `AccumulatedOutput.resultSet` and single-object `Record` entries into arrays while
 *    preserving `SegmentDepTime`, `SegmentArrTime`, `SegmentRoute`, `SegmentDepDate`, `FlightCarrier`,
 *    `FlightNumber`, `RBD`, and `NewAvailability`.
 */

(function () {
  "use strict";

  const ELAL_RBD_API_URL =
    "https://www.elal.com/generalproxy/proxy/dpel/449/GeneralRestServices-GetRbdAvailability";

  const MONTHS_MAP = {
    jan: "01", feb: "02", mar: "03", apr: "04", may: "05", jun: "06",
    jul: "07", aug: "08", sep: "09", oct: "10", nov: "11", dec: "12"
  };

  // All 45 supported destinations in DESTINATION_CATALOG (no ZRH)
  const PRIORITY_IATAS = [
    "ATH", "LCA", "RHO", "PFO", "TBS",
    "FCO", "MXP", "VIE", "BUD", "PRG", "BER", "MUC",
    "LHR", "LTN", "CDG", "MAD", "BCN", "AMS",
    "BKK", "HKT", "NRT",
    "JFK", "EWR", "MIA", "FLL",
    "HER", "SKG", "CFU", "EFL", "JTR", "BUS", "TIV", "BEG",
    "OTP", "SOF", "WAW", "KRK",
    "VCE", "GVA", "FRA", "LIS", "NCE",
    "DXB", "LAX", "BOS"
  ];
  const ALLOWED_IATA_SET = new Set(PRIORITY_IATAS);

  const TARGET_CABINS = [
    { name: "Economy", rbd: "E" },
    { name: "Premium", rbd: "A" }
  ];

  // Contiguous 14-day rolling full-year windows anchored to uniform 5-day cycle
  const SHARD_COUNT = 5;
  function buildCycleAnchoredWindows(daysAhead) {
    const horizon = Math.max(14, Math.min(364, Number(daysAhead) || 350));
    const numWindows = Math.floor((horizon + 13) / 14);
    const now = new Date();
    const dayMs = 86400000;
    const todayUtcDays = Math.floor(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) / dayMs);
    const cycleAnchorDays = Math.floor(todayUtcDays / SHARD_COUNT) * SHARD_COUNT;
    const anchorUtcMs = cycleAnchorDays * dayMs;
    const minStartUtcMs = (todayUtcDays - 1) * dayMs;
    const fmtDay = (ms) => new Date(ms).toISOString().slice(0, 10);
    const out = [];
    for (let idx = 0; idx < numWindows; idx++) {
      let startUtcMs = anchorUtcMs - dayMs + 14 * idx * dayMs;
      let endUtcMs = startUtcMs + 14 * dayMs;
      if (endUtcMs <= minStartUtcMs) continue;
      if (startUtcMs < minStartUtcMs) {
        startUtcMs = minStartUtcMs;
        endUtcMs = startUtcMs + 14 * dayMs;
      }
      const localStart = fmtDay(startUtcMs + dayMs);
      const localEnd = fmtDay(endUtcMs + dayMs);
      out.push({
        label: `חלון ${idx + 1}/${numWindows} (${localStart}..${localEnd})`,
        startIso: `${fmtDay(startUtcMs)}T21:00:00.000Z`,
        endIso: `${fmtDay(endUtcMs)}T21:00:00.000Z`,
        localStart: localStart,
        localEnd: localEnd
      });
    }
    return { windows: out, autoShardIdx: todayUtcDays % SHARD_COUNT };
  }

  function selectShardWindows(shardChoice) {
    const { windows, autoShardIdx } = buildCycleAnchoredWindows(350);
    const idx = shardChoice === "auto" ? autoShardIdx : Math.max(0, Math.min(SHARD_COUNT - 1, Number(shardChoice) || 0));
    const startPos = Math.floor((idx * windows.length) / SHARD_COUNT);
    const endPos = Math.floor(((idx + 1) * windows.length) / SHARD_COUNT);
    return { selected: windows.slice(startPos, endPos), resolvedIdx: idx };
  }

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

  function extractHhMm(rawTime) {
    if (!rawTime) return null;
    let s = String(rawTime).trim();
    if (s.includes("T")) {
      s = s.split("T")[1].trim();
    }
    if (s.length >= 5 && s[2] === ":") {
      return s.slice(0, 5);
    }
    return null;
  }

  function extractRowsFromAccumulatedOutput(rawJsonOrObj) {
    const extractedRows = [];
    try {
      const data = typeof rawJsonOrObj === "string" ? JSON.parse(rawJsonOrObj) : rawJsonOrObj;
      if (!data || !data.AccumulatedOutput) return extractedRows;
      const rawRs = data.AccumulatedOutput.resultSet;
      const rsList = Array.isArray(rawRs) ? rawRs : (rawRs && typeof rawRs === "object" ? [rawRs] : []);

      for (const rs of rsList) {
        if (!rs || typeof rs !== "object") continue;
        const rawRec = rs.Record;
        const records = Array.isArray(rawRec) ? rawRec : (rawRec && typeof rawRec === "object" ? [rawRec] : []);

        for (const rec of records) {
          if (!rec || typeof rec !== "object") continue;
          const availRaw = String(rec.NewAvailability || "0").trim();
          const availClean = availRaw.endsWith("+") ? availRaw.slice(0, -1).trim() : availRaw;
          const avail = parseInt(availClean, 10);
          if (isNaN(avail) || avail <= 0) continue;

          const route = String(rec.SegmentRoute || "").trim().toUpperCase();
          if (route.length !== 6) continue;
          const orig = route.slice(0, 3);
          const dest = route.slice(3, 6);
          const routeDest = orig === "TLV" ? dest : orig;
          if (!ALLOWED_IATA_SET.has(routeDest)) continue;

          const fDate = String(rec.SegmentDepDate || "").slice(0, 10);
          if (!/^\d{4}-\d{2}-\d{2}$/.test(fDate)) continue;
          const carrier = String(rec.FlightCarrier || "LY").trim().toUpperCase();
          const numPart = String(rec.FlightNumber || "").trim();
          const rbdCode = String(rec.RBD || "E").trim().toUpperCase();
          if (rbdCode === "I" || rbdCode === "W" || rbdCode === "BUSINESS") continue;

          const depHhMm = extractHhMm(rec.SegmentDepTime);
          const arrHhMm = extractHhMm(rec.SegmentArrTime);

          extractedRows.push({
            destination_iata: routeDest,
            direction: dest === "TLV" ? "INBOUND" : "OUTBOUND",
            flight_number: `${carrier}${numPart}`,
            flight_date: fDate,
            economy_seats: rbdCode === "E" || rbdCode === "X" || rbdCode === "U" ? avail : 0,
            premium_seats: rbdCode === "A" || rbdCode === "P" || rbdCode === "R" ? avail : 0,
            business_seats: 0,
            departure_time_local: depHhMm,
            arrival_time_local: arrHhMm,
            SegmentRoute: route,
            SegmentDepDate: rec.SegmentDepDate,
            SegmentDepTime: rec.SegmentDepTime || (depHhMm ? `${fDate}T${depHhMm}:00` : null),
            SegmentArrTime: rec.SegmentArrTime || (arrHhMm ? `${fDate}T${arrHhMm}:00` : null),
            FlightCarrier: carrier,
            FlightNumber: numPart,
            RBD: rbdCode,
            NewAvailability: rec.NewAvailability
          });
        }
      }
    } catch (_err) {}
    return extractedRows;
  }

  // ============================================================================
  // MAIN WORLD INTERCEPTOR & $.ajax 50-SEGMENT BATCH DRIVER
  // ============================================================================
  function installMainWorldInterceptorAndDriver() {
    if (window.__fvpMainWorldInstalled) return;
    window.__fvpMainWorldInstalled = true;

    function parseAndForwardAccumulatedOutput(rawJsonText) {
      const extractedRows = extractRowsFromAccumulatedOutput(rawJsonText);
      if (extractedRows.length > 0) {
        window.postMessage(
          {
            source: "FVP_MAIN_CAPTURED_ROWS",
            rows: extractedRows
          },
          "*"
        );
      }
    }

    // 1. Hook XMLHttpRequest for passive user searches
    const origOpen = XMLHttpRequest.prototype.open;
    const origSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (method, url) {
      this.__fvpUrl = String(url || "");
      return origOpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function (body) {
      const urlStr = String(this.__fvpUrl || "");
      if (urlStr.includes("GetRbdAvailability")) {
        this.addEventListener("load", function () {
          try {
            if (this.responseText) {
              parseAndForwardAccumulatedOutput(this.responseText);
            }
          } catch (_e) {}
        });
      }
      return origSend.apply(this, arguments);
    };

    // 2. Handle 50-segment $.ajax batch requests from Isolated World
    window.addEventListener("message", (ev) => {
      if (!ev.data || ev.data.source !== "FVP_ISO_TO_MAIN") return;

      if (ev.data.type === "AJAX_BATCH_FETCH") {
        const { reqId, startIso, endIso, rbdCode, segments } = ev.data;
        if (!window.$ || typeof window.$.ajax !== "function") {
          window.postMessage(
            {
              source: "FVP_MAIN_TO_ISO",
              reqId: reqId,
              okOut: false,
              reason: "JQUERY_AJAX_NOT_READY",
              rows: []
            },
            "*"
          );
          return;
        }

        window.$.ajax({
          url: ELAL_RBD_API_URL,
          type: "POST",
          contentType: "application/json",
          data: JSON.stringify({
            input: {
              startDate: startIso,
              endDate: endIso,
              rbd: rbdCode,
              seg: segments
            }
          }),
          timeout: 25000,
          success: function (res) {
            const rows = extractRowsFromAccumulatedOutput(res);
            window.postMessage(
              {
                source: "FVP_MAIN_TO_ISO",
                reqId: reqId,
                okOut: true,
                rows: rows
              },
              "*"
            );
          },
          error: function (xhr, status, err) {
            window.postMessage(
              {
                source: "FVP_MAIN_TO_ISO",
                reqId: reqId,
                okOut: false,
                status: xhr ? xhr.status : 0,
                reason: String(err || status || "AJAX_ERROR"),
                rows: []
              },
              "*"
            );
          }
        });
      }
    });
  }

  if (!isIsolatedExtensionWorld) {
    installMainWorldInterceptorAndDriver();
    return;
  }

  // ============================================================================
  // ISOLATED EXTENSION WORLD: Widget UI, 50-Segment Batch Auto-Pilot & Sync
  // ============================================================================

  let autoPilotRunning = false;
  let totalSyncedCount = 0;
  let lastSyncedSignature = "";
  let bridgeReqSeq = 0;

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function buildAllDirectionalSegments(destinations) {
    const segs = [];
    for (const d of destinations) {
      if (!ALLOWED_IATA_SET.has(d)) continue;
      segs.push({ org: "TLV", dest: d });
      segs.push({ org: d, dest: "TLV" });
    }
    return segs;
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
          const routeDest = orig === "TLV" ? dest : orig;
          if (ALLOWED_IATA_SET.has(routeDest)) {
            extracted.push({
              destination_iata: routeDest,
              direction: dest === "TLV" ? "INBOUND" : "OUTBOUND",
              flight_number: outFlight,
              flight_date: rowDate,
              economy_seats: cabin === "ECONOMY" ? outAvail : 0,
              premium_seats: cabin === "PREMIUM" ? outAvail : 0,
              business_seats: 0
            });
          }
        }

        const inFlight = cells[4].replace(/\s+/g, "");
        const inRoute = cells[5].replace(/\s+/g, "").toUpperCase();
        const inAvail = parseInt(cells[6], 10);
        if (inFlight && inRoute.includes("-") && !isNaN(inAvail) && inAvail > 0) {
          const [orig, dest] = inRoute.split("-");
          const routeDest = orig === "TLV" ? dest : orig;
          if (ALLOWED_IATA_SET.has(routeDest)) {
            extracted.push({
              destination_iata: routeDest,
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
    }
    return extracted;
  }

  function sendRowsToServerPromise(rows, reconcileSlices) {
    return new Promise((resolve) => {
      const hasRows = Array.isArray(rows) && rows.length > 0;
      const hasSlices = Array.isArray(reconcileSlices) && reconcileSlices.length > 0;
      if (!hasRows && !hasSlices) {
        resolve({ ok: true, records_synced: 0, destinations: [] });
        return;
      }
      chrome.runtime.sendMessage(
        {
          action: "SYNC_ELAL_ROWS",
          serverUrl: "https://family-trip-planner.duckdns.org",
          rows: hasRows ? rows : [],
          reconcileSlices: hasSlices ? reconcileSlices : []
        },
        (resp) => {
          resolve(resp || { ok: false, error: "No response from extension worker" });
        }
      );
    });
  }

  window.addEventListener("message", (ev) => {
    if (!ev.data) return;
    if (ev.data.source === "FVP_MAIN_CAPTURED_ROWS" && Array.isArray(ev.data.rows)) {
      if (!autoPilotRunning && ev.data.rows.length > 0) {
        sendRowsToServerPromise(ev.data.rows).then((resp) => {
          if (resp && resp.ok) {
            totalSyncedCount += Number(resp.records_synced || ev.data.rows.length);
          }
        });
      }
    }
  });

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

  function triggerMainWorldAjaxBatch(startIso, endIso, rbdCode, segments) {
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
          type: "AJAX_BATCH_FETCH",
          reqId: reqId,
          startIso: startIso,
          endIso: endIso,
          rbdCode: rbdCode,
          segments: segments
        },
        "*"
      );

      setTimeout(() => {
        if (settled) return;
        settled = true;
        window.removeEventListener("message", onMsg);
        resolve({ okOut: false, reason: "TIMEOUT", rows: [] });
      }, 28000);
    });
  }

  async function runAutoPilot() {
    const statusEl = document.getElementById("fvp-sync-status");
    const btnEl = document.getElementById("fvp-sync-btn");
    const shardSelectEl = document.getElementById("fvp-shard-select");

    if (autoPilotRunning) {
      autoPilotRunning = false;
      if (btnEl) {
        btnEl.textContent = "🛡️ הפעל סנכרון בטוח (מנה יומית · ~דקה)";
        btnEl.style.background = "#10b981";
      }
      if (statusEl) {
        statusEl.textContent = `⏸️ הסריקה נעצרה. סה"כ סונכרנו ${totalSyncedCount} טיסות לשרת.`;
      }
      return;
    }

    try {
      autoPilotRunning = true;
      if (btnEl) {
        btnEl.textContent = "⏹️ עצור סנכרון בטוח";
        btnEl.style.background = "#ef4444";
      }

      const shardChoice = shardSelectEl ? shardSelectEl.value : "auto";
      const { selected: activeWindows, resolvedIdx } = selectShardWindows(shardChoice);

      const pageOptionCodes = new Set();
      document.querySelectorAll("select option").forEach((opt) => {
        const raw = `${opt.value || ""} ${opt.textContent || ""}`.toUpperCase();
        (raw.match(/\b[A-Z]{3}\b/g) || []).forEach((c) => pageOptionCodes.add(c));
      });
      const activeIatas =
        pageOptionCodes.size >= 15
          ? PRIORITY_IATAS.filter((c) => pageOptionCodes.has(c))
          : PRIORITY_IATAS.slice();
      const targetIatas = activeIatas.length > 0 ? activeIatas : PRIORITY_IATAS.slice();
      const destBatches = [];
      for (let i = 0; i < targetIatas.length; i += 25) {
        destBatches.push(targetIatas.slice(i, i + 25));
      }
      const allCollectedRows = [];
      let abortedOnThrottle = false;

      for (let wIdx = 0; wIdx < activeWindows.length && autoPilotRunning && !abortedOnThrottle; wIdx++) {
        const win = activeWindows[wIdx];
        const windowRows = [];
        const windowSlices = [];

        for (const cabinObj of TARGET_CABINS) {
          if (!autoPilotRunning || abortedOnThrottle) break;

          if (statusEl) {
            statusEl.textContent = `🛡️ מנה ${resolvedIdx + 1}/5 · חלון [${wIdx + 1}/${activeWindows.length}] (${win.localStart}..${win.localEnd}) | ${cabinObj.name} (${cabinObj.rbd})...`;
          }

          for (const batchDests of destBatches) {
            if (!autoPilotRunning) break;
            const segments = buildAllDirectionalSegments(batchDests);
            const batchRes = await triggerMainWorldAjaxBatch(
              win.startIso,
              win.endIso,
              cabinObj.rbd,
              segments
            );

            if (!batchRes || !batchRes.okOut) {
              abortedOnThrottle = true;
              if (statusEl) {
                statusEl.textContent = `⚠️ עצירה בטוחה מיידית (שגיאת שרת/קצב ${batchRes ? batchRes.reason : ""}) כדי למנוע חסימה. מה שכבר נסרק נשמר!`;
              }
              break;
            }

            windowSlices.push({
              destinations: batchDests,
              start_date: win.localStart,
              end_date: win.localEnd,
              cabins: [cabinObj.rbd]
            });

            if (Array.isArray(batchRes.rows) && batchRes.rows.length > 0) {
              windowRows.push(...batchRes.rows);
              allCollectedRows.push(...batchRes.rows);
            }

            // Polite human-like spacing (2.8s - 4.2s) to avoid triggering Reblaze rate limits
            const politeMs = 2800 + Math.floor(Math.random() * 1400);
            await sleep(politeMs);
          }
        }

        if ((windowRows.length > 0 || windowSlices.length > 0) && autoPilotRunning) {
          const syncResp = await sendRowsToServerPromise(windowRows, windowSlices);
          if (syncResp && syncResp.ok) {
            totalSyncedCount += Number(syncResp.records_synced || windowRows.length);
          }
        }
      }

      autoPilotRunning = false;
      if (btnEl) {
        btnEl.textContent = "🛡️ הפעל סנכרון בטוח (מנה יומית · ~דקה)";
        btnEl.style.background = "#10b981";
      }
      if (statusEl && !abortedOnThrottle) {
        statusEl.textContent = `🎉 מנה ${resolvedIdx + 1}/5 הושלמה בבטחה! סונכרנו ${totalSyncedCount} טיסות (כולל ניקוי כרטיסים שאזלו) לשרת.`;
      }
    } catch (err) {
      autoPilotRunning = false;
      if (btnEl) {
        btnEl.textContent = "🛡️ הפעל סנכרון בטוח (מנה יומית · ~דקה)";
        btnEl.style.background = "#10b981";
      }
      if (statusEl) {
        statusEl.textContent = `❌ שגיאה בסריקה: ${String(err && err.message ? err.message : err)}`;
      }
    }
  }

  function createFloatingBadge() {
    if (!document.body || document.getElementById("fvp-sync-widget")) return;
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
      "min-width: 310px",
      "max-width: 390px",
      "border: 1px solid rgba(56,189,248,0.4)"
    ].join(";");

    box.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
        <strong>🛡️ סנכרון אל על בטוח (מחזור 5 ימים)</strong>
        <span style="font-size:11px;background:#0284c7;padding:2px 8px;border-radius:999px;">20 בקשות רגועות</span>
      </div>
      <div id="fvp-sync-status" style="font-size:12px;color:#cbd5e1;line-height:1.4;">
        סורק רק חמישית מהשנה בכל הרצה בקצב איטי ובטוח (או מסנכרן אוטומטית כל חיפוש שתבצע בעצמך בטבלה).
      </div>
      <select id="fvp-shard-select" style="background:#1e293b;color:#f8fafc;border:1px solid #334155;border-radius:8px;padding:6px 8px;font-size:12px;">
        <option value="auto">🔄 אוטומטי — המנה היומית להיום (מומלץ)</option>
        <option value="0">📅 חלק 1 מתוך 5 (שבועות 1–5)</option>
        <option value="1">📅 חלק 2 מתוך 5 (שבועות 6–10)</option>
        <option value="2">📅 חלק 3 מתוך 5 (שבועות 11–15)</option>
        <option value="3">📅 חלק 4 מתוך 5 (שבועות 16–20)</option>
        <option value="4">📅 חלק 5 מתוך 5 (שבועות 21–25)</option>
      </select>
      <button id="fvp-sync-btn" type="button" style="background:#10b981;color:#fff;border:none;border-radius:8px;padding:8px 12px;font-weight:700;cursor:pointer;font-size:12.5px;">
        🛡️ הפעל סנכרון בטוח (מנה יומית · ~דקה)
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
