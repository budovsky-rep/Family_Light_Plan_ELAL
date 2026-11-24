/**
 * Safe Auto-Pilot & Network/DOM Reader Content Script (`chrome_extension/content.js` — v2.1)
 *
 * Key design for 100% stability and zero Reblaze blocks on `https://www.elal.com/rbddataclients/`:
 * 1. All 45 supported `DESTINATION_CATALOG` IATA codes (`PRIORITY_IATAS` — excluding unsupported `"ZRH"`).
 * 2. Uses El Al's genuine calculator RBD codes: `rbd: "E"` for Economy and `rbd: "A"` for Premium.
 * 3. Supports all 4 sync modes directly from the floating RTL widget:
 *    - Daily Shard (`auto` or `0..4`): 1/5 of the rolling year (~20 polite requests, ~1.5 min).
 *    - Specific Date (`date`): Single 14-day window across all 45 destinations (4 requests, ~15s).
 *    - All Holidays (`holidays`): 16 Israeli holiday & MoE vacation windows with 35s breather pauses.
 *    - Full Year (`all`): All 25 rolling 14-day windows (350 days) with 45s breather pauses.
 * 4. Distinguishes transient El Al DPEL gateway hiccups (`502`/`503`/`504`/`TIMEOUT` -> 10s wait +
 *    automatic half-batch split retry) from Reblaze WAAP blocks (`403`/`429`/HTML challenge -> strict
 *    zero-retry Fail-Fast abort), plus one-click Resume from the exact stopped window.
 */

(function () {
  "use strict";

  const ELAL_RBD_API_URL =
    "https://www.elal.com/generalproxy/proxy/dpel/449/GeneralRestServices-GetRbdAvailability";

  const MONTHS_MAP = {
    jan: "01", feb: "02", mar: "03", apr: "04", may: "05", jun: "06",
    jul: "07", aug: "08", sep: "09", oct: "10", nov: "11", dec: "12"
  };

  // All 60 supported destinations in DESTINATION_CATALOG
  const PRIORITY_IATAS = [
    "ATH", "LCA", "RHO", "PFO", "TBS",
    "FCO", "MXP", "VIE", "BUD", "PRG", "BER", "MUC",
    "LHR", "LTN", "CDG", "MAD", "BCN", "AMS",
    "BKK", "HKT", "NRT",
    "JFK", "EWR", "MIA", "FLL",
    "HER", "SKG", "CFU", "EFL", "JTR", "BUS", "TIV", "BEG",
    "OTP", "SOF", "WAW", "KRK",
    "VCE", "GVA", "FRA", "LIS", "NCE",
    "DXB", "LAX", "BOS",
    "SZG", "TIA", "ZRH", "BSL", "NAP", "VRN", "LYS", "OPO",
    "JMK", "PVK", "DBV", "ZAG", "LJU", "RMO", "SEZ"
  ];
  const ALLOWED_IATA_SET = new Set(PRIORITY_IATAS);

  const TARGET_CABINS = [
    { name: "Economy", rbd: "E" },
    { name: "Premium", rbd: "A" }
  ];

  // 16×14-day Israeli Holiday & MoE School Vacation windows (UTC start/end dates before T21:00:00.000Z)
  const HOLIDAY_14D_WINDOWS = [
    ["חנוכה 2026 א'", "2026-12-01", "2026-12-15"],
    ["חנוכה 2026 ב'", "2026-12-06", "2026-12-20"],
    ["פורים 2027", "2027-03-16", "2027-03-30"],
    ["פסח 2027 א'", "2027-04-07", "2027-04-21"],
    ["פסח 2027 ב'", "2027-04-19", "2027-05-03"],
    ["יום העצמאות 2027", "2027-05-05", "2027-05-19"],
    ["שבועות 2027", "2027-06-04", "2027-06-18"],
    ["סוף יוני 2027", "2027-06-18", "2027-07-02"],
    ["יולי 2027 א'", "2027-07-02", "2027-07-16"],
    ["יולי 2027 ב'", "2027-07-16", "2027-07-30"],
    ["אוגוסט 2027 א'", "2027-07-30", "2027-08-13"],
    ["אוגוסט 2027 ב'", "2027-08-13", "2027-08-27"],
    ["סוף אוגוסט 2027", "2027-08-20", "2027-09-03"],
    ["ראש השנה וכיפור 2027", "2027-09-26", "2027-10-10"],
    ["סוכות 2027 א'", "2027-10-08", "2027-10-22"],
    ["סוכות 2027 ב'", "2027-10-15", "2027-10-29"]
  ];

  const SHARD_COUNT = 5;
  const DAY_MS = 86400000;
  const fmtDay = (ms) => new Date(ms).toISOString().slice(0, 10);
  const parseUtcIso = (iso) => Date.parse(`${String(iso).slice(0, 10)}T00:00:00Z`);

  function buildCycleAnchoredWindows(daysAhead) {
    const horizon = Math.max(14, Math.min(364, Number(daysAhead) || 350));
    const numWindows = Math.floor((horizon + 13) / 14);
    const now = new Date();
    const todayUtcDays = Math.floor(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) / DAY_MS);
    const cycleAnchorDays = Math.floor(todayUtcDays / SHARD_COUNT) * SHARD_COUNT;
    const anchorUtcMs = cycleAnchorDays * DAY_MS;
    const minStartUtcMs = (todayUtcDays - 1) * DAY_MS;
    const out = [];
    for (let idx = 0; idx < numWindows; idx++) {
      let startUtcMs = anchorUtcMs - DAY_MS + 14 * idx * DAY_MS;
      let endUtcMs = startUtcMs + 14 * DAY_MS;
      if (endUtcMs <= minStartUtcMs) continue;
      if (startUtcMs < minStartUtcMs) {
        startUtcMs = minStartUtcMs;
        endUtcMs = startUtcMs + 14 * DAY_MS;
      }
      const localStart = fmtDay(startUtcMs + DAY_MS);
      const localEnd = fmtDay(endUtcMs + DAY_MS);
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

  function buildPlanForMode(modeChoice, customDateIso) {
    if (modeChoice === "date") {
      const cleanDate = /^\d{4}-\d{2}-\d{2}$/.test(String(customDateIso || "").trim())
        ? String(customDateIso).trim()
        : fmtDay(Date.now() + 14 * DAY_MS);
      const tMs = parseUtcIso(cleanDate);
      const sMs = tMs - DAY_MS;
      const eMs = sMs + 14 * DAY_MS;
      const locStart = fmtDay(sMs + DAY_MS);
      const locEnd = fmtDay(eMs + DAY_MS);
      return {
        modeTitle: `תאריך ממוקד (${locStart}..${locEnd})`,
        windows: [
          {
            label: `תאריך ממוקד (${locStart}..${locEnd})`,
            startIso: `${fmtDay(sMs)}T21:00:00.000Z`,
            endIso: `${fmtDay(eMs)}T21:00:00.000Z`,
            localStart: locStart,
            localEnd: locEnd
          }
        ],
        minDelayMs: 2600,
        maxDelayMs: 4000,
        cooldownEveryWindows: 0,
        cooldownMs: 0
      };
    }

    if (modeChoice === "holidays") {
      const nowMs = Date.now();
      const wins = HOLIDAY_14D_WINDOWS
        .filter(([, , eUtc]) => parseUtcIso(eUtc) > nowMs)
        .map(([lbl, sUtc, eUtc]) => ({
          label: lbl,
          startIso: `${sUtc}T21:00:00.000Z`,
          endIso: `${eUtc}T21:00:00.000Z`,
          localStart: fmtDay(parseUtcIso(sUtc) + DAY_MS),
          localEnd: fmtDay(parseUtcIso(eUtc) + DAY_MS)
        }));
      return {
        modeTitle: `כל חגי השנה (${wins.length} חלונות)`,
        windows: wins,
        minDelayMs: 3800,
        maxDelayMs: 6000,
        cooldownEveryWindows: 4,
        cooldownMs: 35000
      };
    }

    if (modeChoice === "all") {
      const { windows } = buildCycleAnchoredWindows(350);
      return {
        modeTitle: `שנה מלאה (${windows.length} חלונות)`,
        windows: windows,
        minDelayMs: 4200,
        maxDelayMs: 6800,
        cooldownEveryWindows: 5,
        cooldownMs: 45000
      };
    }

    const { windows, autoShardIdx } = buildCycleAnchoredWindows(350);
    const idx =
      modeChoice === "auto"
        ? autoShardIdx
        : Math.max(0, Math.min(SHARD_COUNT - 1, Number(modeChoice) || 0));
    const startPos = Math.floor((idx * windows.length) / SHARD_COUNT);
    const endPos = Math.floor(((idx + 1) * windows.length) / SHARD_COUNT);
    return {
      modeTitle: `מנה ${idx + 1}/5`,
      windows: windows.slice(startPos, endPos),
      minDelayMs: 2800,
      maxDelayMs: 4400,
      cooldownEveryWindows: 0,
      cooldownMs: 0
    };
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

  function parseJsonIfNeeded(rawJsonOrObj) {
    if (!rawJsonOrObj) return null;
    if (typeof rawJsonOrObj === "string") {
      try {
        return JSON.parse(rawJsonOrObj);
      } catch (_e) {
        return null;
      }
    }
    return typeof rawJsonOrObj === "object" ? rawJsonOrObj : null;
  }

  function extractRowsFromAccumulatedOutput(rawJsonOrObj) {
    const extractedRows = [];
    try {
      const data = parseJsonIfNeeded(rawJsonOrObj);
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
            economy_seats: rbdCode === "E" || rbdCode === "X" || rbdCode === "U" ? availRaw : 0,
            premium_seats: rbdCode === "A" || rbdCode === "P" || rbdCode === "R" ? availRaw : 0,
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
  // MAIN WORLD INTERCEPTOR & $.ajax BATCH DRIVER
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

    XMLHttpRequest.prototype.send = function () {
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

    // 2. Handle $.ajax batch requests from Isolated World
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
              status: 0,
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
          timeout: 26000,
          success: function (res) {
            const parsed = parseJsonIfNeeded(res);
            if (!parsed || !("AccumulatedOutput" in parsed)) {
              window.postMessage(
                {
                  source: "FVP_MAIN_TO_ISO",
                  reqId: reqId,
                  okOut: false,
                  status: 200,
                  reason: "REBLAZE_OR_INVALID_BODY",
                  rows: []
                },
                "*"
              );
              return;
            }
            const rows = extractRowsFromAccumulatedOutput(parsed);
            window.postMessage(
              {
                source: "FVP_MAIN_TO_ISO",
                reqId: reqId,
                okOut: true,
                status: 200,
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
  // ISOLATED EXTENSION WORLD: Widget UI, 4-Mode Auto-Pilot, 502 Split-Retry & Sync
  // ============================================================================

  let autoPilotRunning = false;
  let totalSyncedCount = 0;
  let lastSyncedSignature = "";
  let bridgeReqSeq = 0;
  let savedResumeState = null; // { modeChoice, customDateIso, startWindowIdx, totalWindows }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function randBetween(minMs, maxMs) {
    return minMs + Math.floor(Math.random() * (maxMs - minMs + 1));
  }

  function isTransientGatewayFailure(batchRes) {
    if (!batchRes) return false;
    const st = Number(batchRes.status || 0);
    const reason = String(batchRes.reason || "").toUpperCase();
    // 502 / 503 / 504 or XHR timeout on El Al's Amadeus/DPEL proxy (/generalproxy/proxy/dpel/449)
    // Never retry 403 / 429 / 200 REBLAZE_OR_INVALID_BODY!
    if (st === 502 || st === 503 || st === 504) return true;
    if (st === 0 && (reason.includes("TIMEOUT") || reason === "AJAX_ERROR")) return true;
    return false;
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
        const outAvailRaw = cells[2].trim();
        const outAvail = parseInt(outAvailRaw, 10);
        if (outFlight && outRoute.includes("-") && !isNaN(outAvail) && outAvail > 0) {
          const [orig, dest] = outRoute.split("-");
          const routeDest = orig === "TLV" ? dest : orig;
          if (ALLOWED_IATA_SET.has(routeDest)) {
            extracted.push({
              destination_iata: routeDest,
              direction: dest === "TLV" ? "INBOUND" : "OUTBOUND",
              flight_number: outFlight,
              flight_date: rowDate,
              economy_seats: cabin === "ECONOMY" ? outAvailRaw : 0,
              premium_seats: cabin === "PREMIUM" ? outAvailRaw : 0,
              business_seats: 0
            });
          }
        }

        const inFlight = cells[4].replace(/\s+/g, "");
        const inRoute = cells[5].replace(/\s+/g, "").toUpperCase();
        const inAvailRaw = cells[6].trim();
        const inAvail = parseInt(inAvailRaw, 10);
        if (inFlight && inRoute.includes("-") && !isNaN(inAvail) && inAvail > 0) {
          const [orig, dest] = inRoute.split("-");
          const routeDest = orig === "TLV" ? dest : orig;
          if (ALLOWED_IATA_SET.has(routeDest)) {
            extracted.push({
              destination_iata: routeDest,
              direction: dest === "TLV" ? "INBOUND" : "OUTBOUND",
              flight_number: inFlight,
              flight_date: rowDate,
              economy_seats: cabin === "ECONOMY" ? inAvailRaw : 0,
              premium_seats: cabin === "PREMIUM" ? inAvailRaw : 0,
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
          serverUrl: "https://breezyflights.com",
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
        resolve({ okOut: false, status: 0, reason: "TIMEOUT", rows: [] });
      }, 29000);
    });
  }

  function updateButtonLabelForSelection() {
    if (autoPilotRunning) return;
    const btnEl = document.getElementById("fvp-sync-btn");
    const badgePillEl = document.getElementById("fvp-mode-pill");
    const shardSelectEl = document.getElementById("fvp-shard-select");
    const dateRowEl = document.getElementById("fvp-date-row");
    const resumeBtnEl = document.getElementById("fvp-resume-btn");
    if (!btnEl || !shardSelectEl) return;

    const val = shardSelectEl.value;
    if (dateRowEl) {
      dateRowEl.style.display = val === "date" ? "flex" : "none";
    }

    if (val === "date") {
      btnEl.textContent = "🎯 סנכרן תאריך נבחר לכל היעדים (~15 שנ')";
      if (badgePillEl) badgePillEl.textContent = "4 בקשות בלבד";
    } else if (val === "holidays") {
      btnEl.textContent = "🏖️ סנכרן את כל חגי וחופשות השנה (~6 דק')";
      if (badgePillEl) badgePillEl.textContent = "16 חלונות + הפסקות";
    } else if (val === "all") {
      btnEl.textContent = "🌍 סנכרן שנה מלאה בקצב בטוח (~14 דק')";
      if (badgePillEl) badgePillEl.textContent = "25 חלונות + הפסקות";
    } else {
      btnEl.textContent = "🛡️ הפעל סנכרון בטוח (מנה יומית · ~דקה)";
      if (badgePillEl) badgePillEl.textContent = "20 בקשות רגועות";
    }
    btnEl.style.background = "#10b981";

    if (resumeBtnEl) {
      if (savedResumeState && savedResumeState.startWindowIdx < savedResumeState.totalWindows) {
        resumeBtnEl.style.display = "block";
        resumeBtnEl.textContent = `▶️ המשך מאיפה שעצר (חלון ${savedResumeState.startWindowIdx + 1}/${savedResumeState.totalWindows})`;
      } else {
        resumeBtnEl.style.display = "none";
      }
    }
  }

  async function queryDestinationsWith502SplitFallback(
    batchDests,
    win,
    cabinObj,
    minDelayMs,
    maxDelayMs,
    statusEl
  ) {
    const segments = buildAllDirectionalSegments(batchDests);
    const firstRes = await triggerMainWorldAjaxBatch(
      win.startIso,
      win.endIso,
      cabinObj.rbd,
      segments
    );
    if (firstRes && firstRes.okOut) {
      return {
        ok: true,
        rows: Array.isArray(firstRes.rows) ? firstRes.rows : [],
        slices: [
          {
            destinations: batchDests,
            start_date: win.localStart,
            end_date: win.localEnd,
            cabins: [cabinObj.rbd]
          }
        ]
      };
    }

    // Only attempt a single calm split-batch recovery on 502/503/504/TIMEOUT (El Al DPEL gateway overload)
    if (!isTransientGatewayFailure(firstRes) || batchDests.length <= 4 || !autoPilotRunning) {
      return {
        ok: false,
        status: firstRes ? firstRes.status : 0,
        reason: firstRes ? firstRes.reason : "UNKNOWN"
      };
    }

    if (statusEl) {
      statusEl.textContent = `⏳ שגיאת שער זמנית באל על (${firstRes.status || firstRes.reason}) — ממתין 10 שנ' ומפצל את המקבץ לחצי...`;
    }
    await sleep(10000);
    if (!autoPilotRunning) {
      return { ok: false, status: 0, reason: "STOPPED" };
    }

    const mid = Math.ceil(batchDests.length / 2);
    const subBatches = [batchDests.slice(0, mid), batchDests.slice(mid)];
    const combinedRows = [];
    const combinedSlices = [];

    for (let sIdx = 0; sIdx < subBatches.length; sIdx++) {
      if (!autoPilotRunning) return { ok: false, status: 0, reason: "STOPPED" };
      const subDests = subBatches[sIdx];
      const subSegs = buildAllDirectionalSegments(subDests);
      const subRes = await triggerMainWorldAjaxBatch(
        win.startIso,
        win.endIso,
        cabinObj.rbd,
        subSegs
      );
      if (!subRes || !subRes.okOut) {
        return {
          ok: false,
          status: subRes ? subRes.status : 0,
          reason: subRes ? subRes.reason : "RETRY_FAILED"
        };
      }
      if (Array.isArray(subRes.rows) && subRes.rows.length > 0) {
        combinedRows.push(...subRes.rows);
      }
      combinedSlices.push({
        destinations: subDests,
        start_date: win.localStart,
        end_date: win.localEnd,
        cabins: [cabinObj.rbd]
      });
      if (sIdx + 1 < subBatches.length) {
        await sleep(randBetween(minDelayMs, maxDelayMs));
      }
    }

    return { ok: true, rows: combinedRows, slices: combinedSlices };
  }

  async function runAutoPilot(useSavedResume = false) {
    const statusEl = document.getElementById("fvp-sync-status");
    const btnEl = document.getElementById("fvp-sync-btn");
    const shardSelectEl = document.getElementById("fvp-shard-select");
    const dateInputEl = document.getElementById("fvp-target-date");
    const resumeBtnEl = document.getElementById("fvp-resume-btn");

    if (autoPilotRunning) {
      autoPilotRunning = false;
      updateButtonLabelForSelection();
      if (statusEl) {
        statusEl.textContent = `⏸️ הסריקה נעצרה לבקשתך. סה"כ סונכרנו ${totalSyncedCount} טיסות לשרת (ניתן להמשיך מאותה נקודה).`;
      }
      return;
    }

    try {
      autoPilotRunning = true;
      if (resumeBtnEl) resumeBtnEl.style.display = "none";
      if (btnEl) {
        btnEl.textContent = "⏹️ עצור סנכרון בטוח";
        btnEl.style.background = "#ef4444";
      }

      const modeChoice =
        useSavedResume && savedResumeState
          ? savedResumeState.modeChoice
          : shardSelectEl
            ? shardSelectEl.value
            : "auto";
      const customDateIso =
        useSavedResume && savedResumeState
          ? savedResumeState.customDateIso
          : dateInputEl
            ? dateInputEl.value
            : "";

      const plan = buildPlanForMode(modeChoice, customDateIso);
      const activeWindows = plan.windows;
      const startWindowIdx =
        useSavedResume && savedResumeState ? Math.max(0, savedResumeState.startWindowIdx) : 0;

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

      // Use 20 destinations (40 directional segments) per batch for multi-window runs to keep El Al DPEL fast and avoid 502s,
      // or 25 destinations for fast 1-window / daily-shard scans (with automatic 502 split fallback).
      const batchSize = modeChoice === "all" || modeChoice === "holidays" ? 16 : 25;
      const destBatches = [];
      for (let i = 0; i < targetIatas.length; i += batchSize) {
        destBatches.push(targetIatas.slice(i, i + batchSize));
      }

      let abortedOnError = false;

      for (let wIdx = startWindowIdx; wIdx < activeWindows.length && autoPilotRunning && !abortedOnError; wIdx++) {
        if (
          plan.cooldownEveryWindows > 0 &&
          wIdx > startWindowIdx &&
          (wIdx - startWindowIdx) % plan.cooldownEveryWindows === 0
        ) {
          const totalSec = Math.round(plan.cooldownMs / 1000);
          for (let rem = totalSec; rem > 0 && autoPilotRunning; rem--) {
            if (statusEl) {
              statusEl.textContent = `☕ הפסקת התרעננות אוטומטית למניעת חסימה (${rem} שנ')... עד כה סונכרנו ${totalSyncedCount} טיסות.`;
            }
            await sleep(1000);
          }
          if (!autoPilotRunning) {
            savedResumeState = {
              modeChoice,
              customDateIso,
              startWindowIdx: wIdx,
              totalWindows: activeWindows.length
            };
            break;
          }
        }

        const win = activeWindows[wIdx];
        const windowRows = [];
        const windowSlices = [];

        for (const cabinObj of TARGET_CABINS) {
          if (!autoPilotRunning || abortedOnError) break;

          if (statusEl) {
            statusEl.textContent = `🛡️ ${plan.modeTitle} · חלון [${wIdx + 1}/${activeWindows.length}] (${win.localStart}..${win.localEnd}) | ${cabinObj.name} (${cabinObj.rbd})...`;
          }

          for (const batchDests of destBatches) {
            if (!autoPilotRunning) break;
            const batchOutcome = await queryDestinationsWith502SplitFallback(
              batchDests,
              win,
              cabinObj,
              plan.minDelayMs,
              plan.maxDelayMs,
              statusEl
            );

            if (!batchOutcome.ok) {
              savedResumeState = {
                modeChoice,
                customDateIso,
                startWindowIdx: wIdx,
                totalWindows: activeWindows.length
              };
              if (batchOutcome.reason !== "STOPPED") {
                abortedOnError = true;
                if (statusEl) {
                  statusEl.textContent = `⚠️ עצירה בטוחה בחלון ${wIdx + 1}/${activeWindows.length} (סטטוס ${batchOutcome.status || batchOutcome.reason}). כל מה שנסרק נשמר — אפשר להמשיך בלחיצה!`;
                }
              }
              break;
            }

            windowSlices.push(...batchOutcome.slices);
            if (batchOutcome.rows.length > 0) {
              windowRows.push(...batchOutcome.rows);
            }

            await sleep(randBetween(plan.minDelayMs, plan.maxDelayMs));
          }
        }

        if (windowRows.length > 0 || windowSlices.length > 0) {
          const syncResp = await sendRowsToServerPromise(windowRows, windowSlices);
          if (syncResp && syncResp.ok) {
            totalSyncedCount += Number(syncResp.records_synced || windowRows.length);
          }
        }

        if (!autoPilotRunning && !abortedOnError && wIdx + 1 < activeWindows.length) {
          savedResumeState = {
            modeChoice,
            customDateIso,
            startWindowIdx: wIdx,
            totalWindows: activeWindows.length
          };
        }
      }

      if (autoPilotRunning && !abortedOnError) {
        savedResumeState = null;
      }

      autoPilotRunning = false;
      updateButtonLabelForSelection();
      if (statusEl && !abortedOnError && !savedResumeState) {
        statusEl.textContent = `🎉 ${plan.modeTitle} הושלם בבטחה! סה"כ סונכרנו ${totalSyncedCount} טיסות (כולל ניקוי כרטיסים שאזלו) לשרת.`;
      }
    } catch (err) {
      autoPilotRunning = false;
      updateButtonLabelForSelection();
      if (statusEl) {
        statusEl.textContent = `❌ שגיאה בסריקה: ${String(err && err.message ? err.message : err)}`;
      }
    }
  }

  function createFloatingBadge() {
    if (!document.body || document.getElementById("fvp-sync-widget")) return;
    const defaultDate = fmtDay(Date.now() + 30 * DAY_MS);

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
      "min-width: 325px",
      "max-width: 405px",
      "border: 1px solid rgba(56,189,248,0.4)"
    ].join(";");

    box.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
        <strong>🛡️ סנכרון אל על בטוח (כל 45 היעדים)</strong>
        <span id="fvp-mode-pill" style="font-size:11px;background:#0284c7;padding:2px 8px;border-radius:999px;white-space:nowrap;">20 בקשות רגועות</span>
      </div>
      <div id="fvp-sync-status" style="font-size:12px;color:#cbd5e1;line-height:1.4;">
        בחר מצב סנכרון למטה (או חפש ידנית בטבלה לסנכרון אוטומטי). כולל הגנת פיצול מול שגיאות 502 של אל על.
      </div>
      <select id="fvp-shard-select" style="background:#1e293b;color:#f8fafc;border:1px solid #334155;border-radius:8px;padding:6px 8px;font-size:12px;">
        <optgroup label="מומלץ — מחזור יומי בטוח (5 חלקים)">
          <option value="auto">🔄 אוטומטי — המנה היומית להיום (מומלץ)</option>
          <option value="0">📅 חלק 1 מתוך 5 (חלונות 1–5)</option>
          <option value="1">📅 חלק 2 מתוך 5 (חלונות 6–10)</option>
          <option value="2">📅 חלק 3 מתוך 5 (חלונות 11–15)</option>
          <option value="3">📅 חלק 4 מתוך 5 (חלונות 16–20)</option>
          <option value="4">📅 חלק 5 מתוך 5 (חלונות 21–25)</option>
        </optgroup>
        <optgroup label="מצבי סנכרון נוספים לכל היעדים">
          <option value="date">🎯 תאריך ספציפי — 14 יום לכל היעדים (~15 שנ')</option>
          <option value="holidays">🏖️ כל חגי וחופשות השנה — עם הפסקות (~6 דק')</option>
          <option value="all">🌍 כל השנה המלאה (350 יום) — איטי ובטוח (~14 דק')</option>
        </optgroup>
      </select>
      <div id="fvp-date-row" style="display:none;align-items:center;justify-content:space-between;gap:8px;background:#1e293b;padding:6px 8px;border-radius:8px;border:1px solid #334155;">
        <label for="fvp-target-date" style="font-size:12px;color:#e2e8f0;white-space:nowrap;">תאריך התחלה (14 יום):</label>
        <input id="fvp-target-date" type="date" value="${defaultDate}" style="background:#0f172a;color:#f8fafc;border:1px solid #475569;border-radius:6px;padding:4px 6px;font-size:12px;direction:ltr;" />
      </div>
      <button id="fvp-sync-btn" type="button" style="background:#10b981;color:#fff;border:none;border-radius:8px;padding:8px 12px;font-weight:700;cursor:pointer;font-size:12.5px;">
        🛡️ הפעל סנכרון בטוח (מנה יומית · ~דקה)
      </button>
      <button id="fvp-resume-btn" type="button" style="display:none;background:#0284c7;color:#fff;border:none;border-radius:8px;padding:7px 12px;font-weight:700;cursor:pointer;font-size:12px;">
        ▶️ המשך מאיפה שעצר
      </button>
    `;
    document.body.appendChild(box);

    const shardSelect = document.getElementById("fvp-shard-select");
    if (shardSelect) {
      shardSelect.addEventListener("change", () => updateButtonLabelForSelection());
    }
    const btn = document.getElementById("fvp-sync-btn");
    if (btn) {
      btn.addEventListener("click", () => runAutoPilot(false));
    }
    const resumeBtn = document.getElementById("fvp-resume-btn");
    if (resumeBtn) {
      resumeBtn.addEventListener("click", () => runAutoPilot(true));
    }
  }

  createFloatingBadge();

  const observer = new MutationObserver(() => {
    createFloatingBadge();
    syncVisibleRowsPassive();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();
