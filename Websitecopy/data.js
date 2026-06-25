/* ═══════════════════════════════════════
   LIVE SPREADSHEET STORAGE ENGINE LINK
   ════════════════════════════════════════ */
let resolveSensioDataReady;
window.SensioData = {
  sourceFile: "Sensio Excel Data Hub",
  tenders: [],
  ready: new Promise(resolve => { resolveSensioDataReady = resolve; })
};

// Sync and read rows out of your generated spreadsheet before charts render
(async function initializeSensioExcelStream() {
  const endpoint = 'http://127.0.0.1:5001/api/sensio-stream';

  try {
    const response = await fetch(endpoint, {
      method: 'GET',
      mode: 'cors',
      headers: {
        'Accept': 'application/json'
      }
    });

    if (!response.ok) {
      throw new Error(`Server returned invalid status code: ${response.status}`);
    }

    const streamPayload = await response.json();
    console.log('Received data stream from Excel API Bridge:', streamPayload);

    // Inject the Excel rows straight into your Sensio interface object
    window.SensioData.tenders = Array.isArray(streamPayload.tenders) ? streamPayload.tenders : [];
    window.SensioData.sourceFile = streamPayload.sourceFile || window.SensioData.sourceFile;

    console.log(`⚡ Excel Sheet connected successfully! Loaded ${window.SensioData.tenders.length} active rows into UI.`);

    // ──── AUTOMATED WATCHLIST RE-SYNC WITH PYTHON BACKEND FOR GMAIL ALERTS ────
    const saved = localStorage.getItem('sensio_saved_tenders');
    const savedIds = saved ? JSON.parse(saved) : [];

    savedIds.forEach(id => {
      fetch('http://127.0.0.1:5001/api/save-tender', {
        method: 'POST',
        mode: 'cors',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tenderId: id, isSaved: true })
      })
      .then(res => res.json())
      .then(() => console.log(`[Startup Sync]: Watchlist asset ${id} aligned with Gmail pipeline.`))
      .catch(err => console.error('[Startup Sync Failure]: Couldn\'t reach email engine node:', err));
    });

  } catch (err) {
    console.error('Dashboard failed to read from Excel API Bridge. Ensure server.py is running! Error: ', err);
    window.SensioData.tenders = [];
    window.SensioData.sourceFile = window.SensioData.sourceFile;
  } finally {
    if (typeof resolveSensioDataReady === 'function') {
      resolveSensioDataReady(window.SensioData);
    }
  }
})();