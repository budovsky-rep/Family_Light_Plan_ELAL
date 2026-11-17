/**
 * Background Service Worker (`chrome_extension/background.js`)
 * Receives parsed El Al award flight rows from `content.js` on `elal.com/rbddataclients`
 * and POSTs them directly to the production Family Vacation Planner server.
 */

const DEFAULT_SERVER_URL = "http://34.165.250.15:8080";

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || msg.action !== "SYNC_ELAL_ROWS") {
    return false;
  }

  const serverUrl = (msg.serverUrl || DEFAULT_SERVER_URL).replace(/\/+$/, "");
  const rows = Array.isArray(msg.rows) ? msg.rows : [];
  if (rows.length === 0) {
    sendResponse({ ok: false, error: "לא נמצאו שורות טיסה בטבלה שעל המסך" });
    return false;
  }

  const dests = Array.from(
    new Set(rows.map((r) => String(r.destination_iata || "FCO").toUpperCase()))
  );
  const dates = rows.map((r) => String(r.flight_date)).sort();
  const startDate = dates[0] || "2027-04-01";
  const endDate = dates[dates.length - 1] || "2027-05-15";

  fetch(`${serverUrl}/api/v1/elal-bonus/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      origin: "TLV",
      destinations: dests,
      start_date: startDate,
      end_date: endDate,
      force_refresh: true,
      rbd_payload: rows
    })
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
