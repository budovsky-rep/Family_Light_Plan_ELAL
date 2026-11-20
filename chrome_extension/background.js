/**
 * Background Service Worker (`chrome_extension/background.js`)
 * Receives parsed El Al award flight rows from `content.js` on `elal.com/rbddataclients`
 * and POSTs them directly to the production Family Vacation Planner server.
 */

const DEFAULT_SERVER_URL = "https://family-trip-planner.duckdns.org";

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || msg.action !== "SYNC_ELAL_ROWS") {
    return false;
  }

  const serverUrl = (msg.serverUrl || DEFAULT_SERVER_URL).replace(/\/+$/, "");
  const rows = Array.isArray(msg.rows) ? msg.rows : [];
  const reconcileSlices = Array.isArray(msg.reconcileSlices) ? msg.reconcileSlices : [];
  const syncToken = typeof msg.syncToken === "string" ? msg.syncToken.trim() : "";

  if (rows.length === 0 && reconcileSlices.length === 0) {
    sendResponse({ ok: false, error: "לא נמצאו שורות טיסה בטבלה שעל המסך" });
    return false;
  }

  const sliceDests = reconcileSlices.flatMap((s) => Array.isArray(s.destinations) ? s.destinations : []);
  const dests = Array.from(
    new Set(
      (rows.length > 0
        ? rows.map((r) => String(r.destination_iata || "FCO").toUpperCase())
        : sliceDests.map((d) => String(d || "FCO").toUpperCase())
      ).filter(Boolean)
    )
  );
  if (dests.length === 0) dests.push("FCO");

  const dates = (
    rows.length > 0
      ? rows.map((r) => String(r.flight_date))
      : reconcileSlices.flatMap((s) => [String(s.start_date || ""), String(s.end_date || "")]).filter(Boolean)
  ).sort();
  const startDate = dates[0] || "2027-04-01";
  const endDate = dates[dates.length - 1] || startDate;

  const headers = { "Content-Type": "application/json" };
  if (syncToken) {
    headers["Authorization"] = `Bearer ${syncToken}`;
  }
  const payloadBody = {
    origin: "TLV",
    destinations: dests,
    start_date: startDate,
    end_date: endDate,
    force_refresh: true
  };
  if (rows.length > 0) {
    payloadBody.rbd_payload = rows;
  }
  if (reconcileSlices.length > 0) {
    payloadBody.reconcile_slices = reconcileSlices;
  }

  fetch(`${serverUrl}/api/v1/elal-bonus/sync`, {
    method: "POST",
    headers: headers,
    body: JSON.stringify(payloadBody)
  })
    .then(async (resp) => {
      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${txt}`);
      }
      return resp.json();
    })
    .then((data) => {
      sendResponse({
        ok: true,
        records_synced: data.records_synced || rows.length,
        destinations: dests
      });
    })
    .catch((err) => {
      sendResponse({ ok: false, error: String(err.message || err) });
    });

  return true; // Keep async message channel open
});
