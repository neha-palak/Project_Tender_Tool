/* ═══════════════════════════════════════
   LIVE SPREADSHEET STORAGE ENGINE LINK
   ════════════════════════════════════════ */
let resolveSensioDataReady;
window.SensioData = {
  sourceFile: "Sensio Excel Data Hub",
  tenders: [],
  ready: new Promise(resolve => { resolveSensioDataReady = resolve; })
};

// Single source of truth for "is this tender starred BY ME" — pulled from the
// backend scoped to the current founder, never from localStorage. A star is only
// filled for tenders the signed-in founder saved, not ones teammates saved.
window.SensioSavedIds = new Set();

// (Re)load the current founder's own saved ids. Call again after the founder
// switches so the stars update to that person's saves.
async function reloadSavedIdsForCurrentFounder() {
  const founder = localStorage.getItem('sensio_founder_identity') || '';
  try {
    const idsRes = await fetch(
      `http://127.0.0.1:5001/api/saved-ids?founder=${encodeURIComponent(founder)}`,
      { method: 'GET', mode: 'cors', headers: { 'Accept': 'application/json' } }
    );
    if (idsRes.ok) {
      const idsPayload = await idsRes.json();
      window.SensioSavedIds = new Set((idsPayload.savedIds || []).map(String));
    }
  } catch (err) {
    console.error('[Saved IDs]: Could not load saved-ids from backend.', err);
  }
}

(async function initializeSensioExcelStream() {
  const endpoint = 'http://127.0.0.1:5001/api/sensio-stream';

  try {
    const response = await fetch(endpoint, {
      method: 'GET', mode: 'cors', headers: { 'Accept': 'application/json' }
    });
    if (!response.ok) throw new Error(`Server returned invalid status code: ${response.status}`);
    const streamPayload = await response.json();
    window.SensioData.tenders = Array.isArray(streamPayload.tenders) ? streamPayload.tenders : [];
    window.SensioData.sourceFile = streamPayload.sourceFile || window.SensioData.sourceFile;
    console.log(`⚡ Excel Sheet connected successfully! Loaded ${window.SensioData.tenders.length} active rows into UI.`);
  } catch (err) {
    console.error('Dashboard failed to read from Excel API Bridge. Ensure server.py is running! Error: ', err);
    window.SensioData.tenders = [];
  }

  // Load the current founder's own saved-ids from the backend (per-user star
  // state). If no founder is chosen yet, this returns empty and the identity
  // modal will trigger a reload once they pick who they are.
  await reloadSavedIdsForCurrentFounder();

  if (typeof resolveSensioDataReady === 'function') {
    resolveSensioDataReady(window.SensioData);
  }
})();

// /* ═══════════════════════════════════════
//    LIVE SPREADSHEET STORAGE ENGINE LINK
//    ════════════════════════════════════════ */
// let resolveSensioDataReady;
// window.SensioData = {
//   sourceFile: "Sensio Excel Data Hub",
//   tenders: [],
//   ready: new Promise(resolve => { resolveSensioDataReady = resolve; })
// };

// // Sync and read rows out of your generated spreadsheet before charts render
// (async function initializeSensioExcelStream() {
//   const endpoint = 'http://127.0.0.1:5001/api/sensio-stream';

//   try {
//     const response = await fetch(endpoint, {
//       method: 'GET',
//       mode: 'cors',
//       headers: {
//         'Accept': 'application/json'
//       }
//     });

//     if (!response.ok) {
//       throw new Error(`Server returned invalid status code: ${response.status}`);
//     }

//     const streamPayload = await response.json();
//     console.log('Received data stream from Excel API Bridge:', streamPayload);

//     // Inject the Excel rows straight into your Sensio interface object
//     window.SensioData.tenders = Array.isArray(streamPayload.tenders) ? streamPayload.tenders : [];
//     window.SensioData.sourceFile = streamPayload.sourceFile || window.SensioData.sourceFile;

//     console.log(`⚡ Excel Sheet connected successfully! Loaded ${window.SensioData.tenders.length} active rows into UI.`);

//     // ──── AUTOMATED WATCHLIST RE-SYNC WITH PYTHON BACKEND FOR GMAIL ALERTS ────
//     const saved = localStorage.getItem('sensio_saved_tenders');
//     const savedIds = saved ? JSON.parse(saved) : [];

//     savedIds.forEach(id => {
//       fetch('http://127.0.0.1:5001/api/save-tender', {
//         method: 'POST',
//         mode: 'cors',
//         headers: { 'Content-Type': 'application/json' },
//         body: JSON.stringify({ tenderId: id, isSaved: true })
//       })
//       .then(res => res.json())
//       .then(() => console.log(`[Startup Sync]: Watchlist asset ${id} aligned with Gmail pipeline.`))
//       .catch(err => console.error('[Startup Sync Failure]: Couldn\'t reach email engine node:', err));
//     });

//   } catch (err) {
//     console.error('Dashboard failed to read from Excel API Bridge. Ensure server.py is running! Error: ', err);
//     window.SensioData.tenders = [];
//     window.SensioData.sourceFile = window.SensioData.sourceFile;
//   } finally {
//     if (typeof resolveSensioDataReady === 'function') {
//       resolveSensioDataReady(window.SensioData);
//     }
//   }
// })();