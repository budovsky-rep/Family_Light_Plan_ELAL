/**
 * Safe Auto-Pilot & Network/DOM Reader Content Script (`chrome_extension/content.js` — v1.3)
 *
 * Key design for 100% stability on `https://www.elal.com/rbddataclients/`:
 * 1. Loops by Holiday -> Cabin (`Economy`, then `Premium`) -> Destination so `Travel Class`
 *    is only changed twice per holiday instead of on every destination.
 * 2. Selects `Travel Class` FIRST and waits 450ms before selecting `From`/`To` airports,
 *    because changing `Travel Class` on El Al's form resets the airport dropdowns.
 * 3. Strictly validates that all 4 airport dropdowns (`TLV -> DEST` and `DEST -> TLV`) have
 *    valid selections before clicking `Search` — preventing El Al's "Oops! Something went wrong" modal.
 * 4. In the `MAIN`-world XHR/fetch interceptor for `GeneralRestServices-GetRbdAvailability`,
 *    rewrites ONLY `input.startDate` and `input.endDate` to the active Holiday window while
 *    preserving El Al's native `seg`, `rbd`, headers, and tokens untouched.
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

  // ============================================================================
  // MAIN WORLD INTERCEPTOR & FORM DRIVER
  // ============================================================================
  function installMainWorldInterceptorAndDriver() {
    if (window.__fvpMainWorldInstalled) return;
    window.__fvpMainWorldInstalled = true;
    window.__fvpActiveOverride = null;

    function rewriteOutgoingElAlPayload(rawBody) {
      const ov = window.__fvpActiveOverride;
      if (!ov || !ov.active || typeof rawBody !== "string") return rawBody;
      try {
        const parsed = JSON.parse(rawBody);
        if (!parsed || !parsed.input) return rawBody;

        const seg0 = parsed.input.seg && parsed.input.seg[0] ? parsed.input.seg[0] : null;
        const isInbound = seg0 && String(seg0.dest || "").toUpperCase() === "TLV";

        // Rewrite ONLY startDate and endDate so El Al's form-signed seg & rbd stay 100% consistent
        if (isInbound) {
          if (ov.retStartIso) parsed.input.startDate = ov.retStartIso;
          if (ov.retEndIso) parsed.input.endDate = ov.retEndIso;
        } else {
          if (ov.depStartIso) parsed.input.startDate = ov.depStartIso;
          if (ov.depEndIso) parsed.input.endDate = ov.depEndIso;
        }

        window.postMessage(
          {
            source: "FVP_MAIN_XHR_REWRITTEN",
            direction: isInbound ? "INBOUND" : "OUTBOUND",
            rbd: parsed.input.rbd,
            startDate: parsed.input.startDate,
            endDate: parsed.input.endDate
          },
          "*"
        );
        return JSON.stringify(parsed);
      } catch (_e) {
        return rawBody;
      }
    }

    function parseAndForwardAccumulatedOutput(rawJsonText) {
      try {
        const data = typeof rawJsonText === "string" ? JSON.parse(rawJsonText) : rawJsonText;
        if (!data || !data.AccumulatedOutput || !Array.isArray(data.AccumulatedOutput.resultSet)) {
          return;
        }
        const extractedRows = [];
        for (const rs of data.AccumulatedOutput.resultSet) {
          const records = rs && Array.isArray(rs.Record) ? rs.Record : [];
          for (const rec of records) {
            if (!rec) continue;
            const avail = parseInt(String(rec.NewAvailability || "0").trim(), 10);
            if (isNaN(avail) || avail <= 0) continue;
            const route = String(rec.SegmentRoute || "").trim().toUpperCase();
            if (route.length !== 6) continue;
            const orig = route.slice(0, 3);
            const dest = route.slice(3, 6);
            const fDate = String(rec.SegmentDepDate || "").slice(0, 10);
            if (!/^\d{4}-\d{2}-\d{2}$/.test(fDate)) continue;
            const carrier = String(rec.FlightCarrier || "LY").trim().toUpperCase();
            const numPart = String(rec.FlightNumber || "").trim();
            const rbdCode = String(rec.RBD || "E").trim().toUpperCase();
            if (rbdCode === "I" || rbdCode === "W" || rbdCode === "BUSINESS") continue;

            extractedRows.push({
              destination_iata: orig === "TLV" ? dest : orig,
              direction: dest === "TLV" ? "INBOUND" : "OUTBOUND",
              flight_number: `${carrier}${numPart}`,
              flight_date: fDate,
              economy_seats: rbdCode === "E" || rbdCode === "X" || rbdCode === "U" ? avail : 0,
              premium_seats: rbdCode === "P" || rbdCode === "A" || rbdCode === "R" ? avail : 0,
              business_seats: 0
            });
          }
        }
        if (extractedRows.length > 0) {
          window.postMessage(
            {
              source: "FVP_MAIN_CAPTURED_ROWS",
              rows: extractedRows
            },
            "*"
          );
        }
      } catch (_err) {}
    }

    // 1. Hook XMLHttpRequest
    const origOpen = XMLHttpRequest.prototype.open;
    const origSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (method, url) {
      this.__fvpUrl = String(url || "");
      return origOpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function (body) {
      const urlStr = String(this.__fvpUrl || "");
      if (urlStr.includes("GetRbdAvailability")) {
        const newBody = rewriteOutgoingElAlPayload(body);
        this.addEventListener("load", function () {
          try {
            if (this.responseText) {
              parseAndForwardAccumulatedOutput(this.responseText);
            }
          } catch (_e) {}
        });
        return origSend.call(this, newBody);
      }
      return origSend.apply(this, arguments);
    };

    // 2. Hook window.fetch
    if (typeof window.fetch === "function") {
      const origFetch = window.fetch;
      window.fetch = async function (input, init) {
        const urlStr = typeof input === "string" ? input : (input && input.url) || "";
        if (urlStr.includes("GetRbdAvailability") && init && typeof init.body === "string") {
          init = Object.assign({}, init, {
            body: rewriteOutgoingElAlPayload(init.body)
          });
        }
        const resp = await origFetch.call(this, input, init);
        if (urlStr.includes("GetRbdAvailability")) {
          try {
            const clone = resp.clone();
            clone.text().then((txt) => parseAndForwardAccumulatedOutput(txt)).catch(() => {});
          } catch (_e) {}
        }
        return resp;
      };
    }

    function findFormElementsInMain() {
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

      let depInput = document.querySelector("input[data-fvp-date-role='departure']");
      let retInput = document.querySelector("input[data-fvp-date-role='return']");
      if (!depInput || !retInput) {
        const visibleInputs = Array.from(document.querySelectorAll("input")).filter((inp) => {
          const t = (inp.type || "text").toLowerCase();
          if (t === "hidden" || t === "checkbox" || t === "radio" || t === "submit" || t === "button") return false;
          const r = inp.getBoundingClientRect();
          return r.width > 30 && r.height > 15;
        });
        const matched = visibleInputs.filter((inp) => /\d{1,2}-[A-Za-z]{3,9}-\d{4}/.test((inp.value || "").trim()));
        const pair = matched.length >= 2 ? matched.slice(0, 2) : visibleInputs.slice(0, 2);
        depInput = pair[0] || null;
        retInput = pair[1] || null;
        if (depInput) depInput.setAttribute("data-fvp-date-role", "departure");
        if (retInput) retInput.setAttribute("data-fvp-date-role", "return");
      }

      const searchBtn = Array.from(
        document.querySelectorAll("button, input[type='button'], input[type='submit'], a.btn")
      ).find((b) => {
        const r = b.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return false;
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
        depDateInput: depInput,
        retDateInput: retInput,
        searchBtn: searchBtn || null
      };
    }

    function getSelectedOptionText(selectEl) {
      if (!selectEl || !selectEl.options || selectEl.selectedIndex < 0) return "";
      return (selectEl.options[selectEl.selectedIndex].text || "").trim();
    }

    function setSelectOptionInMain(selectEl, matcherFn) {
      if (!selectEl || !selectEl.options) return false;
      for (let i = 0; i < selectEl.options.length; i++) {
        const opt = selectEl.options[i];
        if (matcherFn(opt)) {
          if (selectEl.selectedIndex === i) {
            return true;
          }
          selectEl.selectedIndex = i;
          try {
            const desc = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value");
            if (desc && desc.set) desc.set.call(selectEl, opt.value);
            else selectEl.value = opt.value;
          } catch (_e) {
            selectEl.value = opt.value;
          }
          selectEl.dispatchEvent(new Event("input", { bubbles: true }));
          selectEl.dispatchEvent(new Event("change", { bubbles: true }));
          return true;
        }
      }
      return false;
    }

    function setVisualDateInMain(inp, dateStr) {
      if (!inp || !dateStr) return;
      try {
        const desc = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
        if (desc && desc.set) desc.set.call(inp, dateStr);
        else inp.value = dateStr;
        inp.setAttribute("value", dateStr);
      } catch (_e) {
        inp.value = dateStr;
      }
    }

    window.addEventListener("message", async (ev) => {
      if (!ev.data || ev.data.source !== "FVP_ISO_TO_MAIN") return;

      if (ev.data.type === "SET_FORM_AND_SEARCH") {
        const {
          reqId,
          destIata,
          cabinName,
          rbdCode,
          depDate,
          retDate,
          depStartIso,
          depEndIso,
          retStartIso,
          retEndIso
        } = ev.data;

        window.__fvpActiveOverride = {
          active: true,
          destIata: String(destIata || "FCO").toUpperCase(),
          rbd: rbdCode || (String(cabinName).toLowerCase().includes("premium") ? "P" : "E"),
          depStartIso: depStartIso,
          depEndIso: depEndIso,
          retStartIso: retStartIso,
          retEndIso: retEndIso
        };

        const sleepMain = (ms) => new Promise((r) => setTimeout(r, ms));
        const targetToken = `[${String(destIata || "").toUpperCase()}]`;

        // STEP 1: Select Travel Class FIRST (because changing Travel Class on El Al resets the airport dropdowns!)
        const c0 = findFormElementsInMain();
        const curDepClassTxt = getSelectedOptionText(c0.depClassSelect).toLowerCase();
        const curRetClassTxt = getSelectedOptionText(c0.retClassSelect).toLowerCase();
        const wantCabinLower = String(cabinName || "economy").toLowerCase();

        if (!curDepClassTxt.includes(wantCabinLower) || !curRetClassTxt.includes(wantCabinLower)) {
          const okClass1 = setSelectOptionInMain(
            c0.depClassSelect,
            (opt) => (opt.text || "").toLowerCase().includes(wantCabinLower)
          );
          await sleepMain(250);
          const c0b = findFormElementsInMain();
          const okClass2 = setSelectOptionInMain(
            c0b.retClassSelect,
            (opt) => (opt.text || "").toLowerCase().includes(wantCabinLower)
          );
          if (!okClass1 || !okClass2) {
            window.postMessage({ source: "FVP_MAIN_TO_ISO", reqId: reqId, okOut: false, reason: "CABIN_NOT_AVAILABLE" }, "*");
            return;
          }
          await sleepMain(450);
        }

        // STEP 2: Select Departure From [TLV] -> To [DEST]
        const c1 = findFormElementsInMain();
        const okDepFrom = setSelectOptionInMain(
          c1.depFromSelect,
          (opt) => (opt.text || "").toUpperCase().includes("[TLV]")
        );
        await sleepMain(220);

        const c1b = findFormElementsInMain();
        const okDepTo = setSelectOptionInMain(
          c1b.depToSelect,
          (opt) => (opt.text || "").toUpperCase().includes(targetToken)
        );
        if (!okDepFrom || !okDepTo) {
          window.postMessage({ source: "FVP_MAIN_TO_ISO", reqId: reqId, okOut: false, reason: "DEST_NOT_IN_DEP" }, "*");
          return;
        }
        await sleepMain(380);

        // STEP 3: Select Return From [DEST] -> To [TLV]
        const c2 = findFormElementsInMain();
        const okRetFrom = setSelectOptionInMain(
          c2.retFromSelect,
          (opt) => (opt.text || "").toUpperCase().includes(targetToken)
        );
        await sleepMain(220);

        const c2b = findFormElementsInMain();
        const okRetTo = setSelectOptionInMain(
          c2b.retToSelect,
          (opt) => (opt.text || "").toUpperCase().includes("[TLV]")
        );
        if (!okRetFrom || !okRetTo) {
          window.postMessage({ source: "FVP_MAIN_TO_ISO", reqId: reqId, okOut: false, reason: "DEST_NOT_IN_RET" }, "*");
          return;
        }
        await sleepMain(280);

        // STEP 4: Final safety check that all 4 airport boxes are non-empty and match before clicking Search
        const cFinal = findFormElementsInMain();
        const validDepFrom = getSelectedOptionText(cFinal.depFromSelect).toUpperCase().includes("[TLV]");
        const validDepTo = getSelectedOptionText(cFinal.depToSelect).toUpperCase().includes(targetToken);
        const validRetFrom = getSelectedOptionText(cFinal.retFromSelect).toUpperCase().includes(targetToken);
        const validRetTo = getSelectedOptionText(cFinal.retToSelect).toUpperCase().includes("[TLV]");

        if (!validDepFrom || !validDepTo || !validRetFrom || !validRetTo) {
          window.postMessage({ source: "FVP_MAIN_TO_ISO", reqId: reqId, okOut: false, reason: "VALIDATION_FAILED" }, "*");
          return;
        }

        if (cFinal.depDateInput && depDate) setVisualDateInMain(cFinal.depDateInput, depDate);
        if (cFinal.retDateInput && retDate) setVisualDateInMain(cFinal.retDateInput, retDate);

        if (cFinal.searchBtn) {
          cFinal.searchBtn.click();
        }

        window.postMessage(
          {
            source: "FVP_MAIN_TO_ISO",
            reqId: reqId,
            okOut: true,
            actualDep: depDate,
            actualRet: retDate
          },
          "*"
        );
      } else if (ev.data.type === "CLEAR_OVERRIDE") {
        window.__fvpActiveOverride = null;
      }
    });
  }

  if (!isIsolatedExtensionWorld) {
    installMainWorldInterceptorAndDriver();
    return;
  }

  // ============================================================================
  // ISOLATED EXTENSION WORLD: Widget UI, Auto-Pilot Loop & Server Sync
  // ============================================================================

  const YEARLY_HOLIDAY_WINDOWS = [
    {
      label: "חנוכה 2026",
      dep: "06-December-2026",
      ret: "13-December-2026",
      depStartIso: "2026-12-02T21:00:00.000Z",
      depEndIso: "2026-12-16T21:00:00.000Z",
      retStartIso: "2026-12-06T21:00:00.000Z",
      retEndIso: "2026-12-20T21:00:00.000Z"
    },
    {
      label: "פורים 2027",
      dep: "22-March-2027",
      ret: "28-March-2027",
      depStartIso: "2027-03-16T21:00:00.000Z",
      depEndIso: "2027-03-30T21:00:00.000Z",
      retStartIso: "2027-03-20T21:00:00.000Z",
      retEndIso: "2027-04-03T21:00:00.000Z"
    },
    {
      label: "פסח 2027 (לפני ליל הסדר וחג ראשון)",
      dep: "11-April-2027",
      ret: "18-April-2027",
      depStartIso: "2027-04-07T21:00:00.000Z",
      depEndIso: "2027-04-21T21:00:00.000Z",
      retStartIso: "2027-04-14T21:00:00.000Z",
      retEndIso: "2027-04-28T21:00:00.000Z"
    },
    {
      label: "פסח 2027 (חול המועד וחג שני)",
      dep: "20-April-2027",
      ret: "28-April-2027",
      depStartIso: "2027-04-16T21:00:00.000Z",
      depEndIso: "2027-04-30T21:00:00.000Z",
      retStartIso: "2027-04-21T21:00:00.000Z",
      retEndIso: "2027-05-05T21:00:00.000Z"
    },
    {
      label: "יום העצמאות 2027",
      dep: "10-May-2027",
      ret: "16-May-2027",
      depStartIso: "2027-05-05T21:00:00.000Z",
      depEndIso: "2027-05-19T21:00:00.000Z",
      retStartIso: "2027-05-09T21:00:00.000Z",
      retEndIso: "2027-05-23T21:00:00.000Z"
    },
    {
      label: "שבועות ויוני 2027",
      dep: "10-June-2027",
      ret: "24-June-2027",
      depStartIso: "2027-06-08T21:00:00.000Z",
      depEndIso: "2027-06-22T21:00:00.000Z",
      retStartIso: "2027-06-15T21:00:00.000Z",
      retEndIso: "2027-06-29T21:00:00.000Z"
    },
    {
      label: "החופש הגדול — יולי 2027",
      dep: "12-July-2027",
      ret: "20-July-2027",
      depStartIso: "2027-07-07T21:00:00.000Z",
      depEndIso: "2027-07-21T21:00:00.000Z",
      retStartIso: "2027-07-14T21:00:00.000Z",
      retEndIso: "2027-07-28T21:00:00.000Z"
    },
    {
      label: "החופש הגדול — אוגוסט 2027",
      dep: "16-August-2027",
      ret: "24-August-2027",
      depStartIso: "2027-08-10T21:00:00.000Z",
      depEndIso: "2027-08-24T21:00:00.000Z",
      retStartIso: "2027-08-17T21:00:00.000Z",
      retEndIso: "2027-08-31T21:00:00.000Z"
    },
    {
      label: "ראש השנה וסוכות 2027",
      dep: "01-October-2027",
      ret: "24-October-2027",
      depStartIso: "2027-09-29T21:00:00.000Z",
      depEndIso: "2027-10-13T21:00:00.000Z",
      retStartIso: "2027-10-10T21:00:00.000Z",
      retEndIso: "2027-10-24T21:00:00.000Z"
    }
  ];

  const PRIORITY_IATAS = [
    "FCO", "ATH", "LCA", "RHO", "PFO", "MAD", "BCN", "CDG", "LHR", "LTN",
    "AMS", "BER", "MUC", "VIE", "BUD", "PRG", "MXP", "ZRH", "TBS",
    "BKK", "HKT", "NRT", "JFK", "EWR", "MIA", "FLL"
  ];

  const TARGET_CABINS = [
    { name: "Economy", rbd: "E" },
    { name: "Premium", rbd: "P" }
  ];

  let autoPilotRunning = false;
  let totalSyncedCount = 0;
  let lastSyncedSignature = "";
  let bridgeReqSeq = 0;
  let lastRewrittenRangeLabel = "";

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

  window.addEventListener("message", (ev) => {
    if (!ev.data) return;
    if (ev.data.source === "FVP_MAIN_XHR_REWRITTEN") {
      const s = String(ev.data.startDate || "").slice(0, 10);
      const e = String(ev.data.endDate || "").slice(0, 10);
      lastRewrittenRangeLabel = `${s}..${e}`;
    } else if (ev.data.source === "FVP_MAIN_CAPTURED_ROWS" && Array.isArray(ev.data.rows)) {
      if (ev.data.rows.length > 0) {
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

  function discoverAvailableDestinations() {
    const selects = Array.from(document.querySelectorAll("select")).filter((s) => {
      const r = s.getBoundingClientRect();
      return r.width > 30 && r.height > 15;
    });
    const airportSelects = selects.filter((s) =>
      Array.from(s.options || []).some((o) => /\[[A-Z]{3}\]/.test(o.text) || /choose airport/i.test(o.text))
    );
    const depToSelect = airportSelects[1] || null;
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

  function triggerMainWorldFormStep(destIata, cabinObj, win) {
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
          cabinName: cabinObj.name,
          rbdCode: cabinObj.rbd,
          depDate: win.dep,
          retDate: win.ret,
          depStartIso: win.depStartIso,
          depEndIso: win.depEndIso,
          retStartIso: win.retStartIso,
          retEndIso: win.retEndIso
        },
        "*"
      );

      setTimeout(() => {
        if (settled) return;
        settled = true;
        window.removeEventListener("message", onMsg);
        resolve({ okOut: false, reason: "TIMEOUT" });
      }, 2800);
    });
  }

  async function runAutoPilot() {
    const statusEl = document.getElementById("fvp-sync-status");
    const btnEl = document.getElementById("fvp-sync-btn");

    if (autoPilotRunning) {
      autoPilotRunning = false;
      window.postMessage({ source: "FVP_ISO_TO_MAIN", type: "CLEAR_OVERRIDE" }, "*");
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
      const destinations = discoverAvailableDestinations();
      autoPilotRunning = true;
      if (btnEl) {
        btnEl.textContent = "⏹️ עצור סריקה אוטומטית (Auto-Pilot פעיל)";
        btnEl.style.background = "#ef4444";
      }

      const windowsToScan = YEARLY_HOLIDAY_WINDOWS;

      // Loop: Holiday -> Cabin (Economy across all destinations, then Premium) -> Destination
      for (let wIdx = 0; wIdx < windowsToScan.length && autoPilotRunning; wIdx++) {
        const win = windowsToScan[wIdx];

        for (const cabinObj of TARGET_CABINS) {
          if (!autoPilotRunning) break;

          for (let dIdx = 0; dIdx < destinations.length && autoPilotRunning; dIdx++) {
            const destIata = destinations[dIdx];
            const stepRes = await triggerMainWorldFormStep(destIata, cabinObj, win);
            if (!stepRes || !stepRes.okOut) {
              continue;
            }

            if (statusEl) {
              const rangeNote = lastRewrittenRangeLabel || `${win.depStartIso.slice(0, 10)}..${win.depEndIso.slice(0, 10)}`;
              statusEl.textContent = `🤖 חג [${wIdx + 1}/${windowsToScan.length}] ${win.label} (${rangeNote}) | ${cabinObj.name} | יעד ${dIdx + 1}/${destinations.length}: ${destIata} | סונכרנו: ${totalSyncedCount}`;
            }

            const politeWaitMs = 5600 + Math.floor(Math.random() * 1400);
            await sleep(politeWaitMs);

            if (!autoPilotRunning) break;

            const rows = extractVisibleTableRows(cabinObj.name.toUpperCase(), win);
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
      window.postMessage({ source: "FVP_ISO_TO_MAIN", type: "CLEAR_OVERRIDE" }, "*");
      if (btnEl) {
        btnEl.textContent = "🤖 הפעל סריקת חגים אוטומטית (Economy + Premium)";
        btnEl.style.background = "#10b981";
      }
      if (statusEl) {
        statusEl.textContent = `🎉 סריקת החגים הושלמה! סה"כ סונכרנו ${totalSyncedCount} טיסות חגים אמיתיות לשרת.`;
      }
    } catch (err) {
      autoPilotRunning = false;
      window.postMessage({ source: "FVP_ISO_TO_MAIN", type: "CLEAR_OVERRIDE" }, "*");
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
      "min-width: 300px",
      "max-width: 380px",
      "border: 1px solid rgba(56,189,248,0.4)"
    ].join(";");

    box.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
        <strong>✈️ סנכרון חגים (Economy + Premium) v1.3</strong>
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
