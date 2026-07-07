/* ═══════════════════════════════════════
   SAVED PORTFOLIO GRAPHICS GENERATION ENGINE
   ════════════════════════════════════════ */

// Authoritative saved-tenders list, loaded from saved_tenders.xlsx via the
// backend. The Excel file (written server-side on every star click) is the
// single source of truth for "what's saved" — not localStorage.
window.SensioSavedData = { tenders: [] };

document.addEventListener('DOMContentLoaded', async () => {
  await loadSavedTendersFromServer();
  initializeSavedCountryDropdown();
  renderSavedTenders();
  registerSavedListeners();
});

async function loadSavedTendersFromServer() {
  const endpoint = `${window.location.origin}/api/saved-tenders`;

  try {
    const response = await fetch(endpoint, {
      method: 'GET',
      mode: 'cors',
      headers: { 'Accept': 'application/json' }
    });

    if (!response.ok) {
      throw new Error(`Server returned invalid status code: ${response.status}`);
    }

    const payload = await response.json();
    window.SensioSavedData.tenders = Array.isArray(payload.tenders) ? payload.tenders : [];

    // Merge into the shared dataset (dedup by id) so openTenderModal() in
    // ui.js keeps working for saved items even if a tender has since
    // fallen out of the live scraper sweep.
    if (window.SensioData) {
      await window.SensioData.ready;
      const existingIds = new Set(window.SensioData.tenders.map(t => t.id));
      window.SensioSavedData.tenders.forEach(t => {
        if (!existingIds.has(t.id)) window.SensioData.tenders.push(t);
      });
    }

    console.log(`⭐ Loaded ${window.SensioSavedData.tenders.length} saved tender(s) from saved_tenders.xlsx.`);
  } catch (err) {
    console.error('[Saved Tenders]: Could not reach backend. Ensure server.py is running!', err);
    window.SensioSavedData.tenders = [];
  }
}

function initializeSavedCountryDropdown() {
  const select = document.getElementById('savedCountrySelector');
  if (!select) return;

  const dataset = window.SensioSavedData.tenders;
  const uniqueCountries = [...new Set(dataset.map(item => item.country).filter(Boolean))].sort();

  select.innerHTML = '<option value="all">🌍 All Countries</option>';
  uniqueCountries.forEach(country => {
    const opt = document.createElement('option');
    opt.value = country.toLowerCase();
    opt.textContent = country;
    select.appendChild(opt);
  });
}

function registerSavedListeners() {
  const elements = ['savedSearchInput', 'savedCountrySelector', 'savedSectorSelector'];
  elements.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', renderSavedTenders);
  });
}

function renderSavedTenders() {
  const grid = document.getElementById('savedGridDisplay');
  if (!grid) return;

  const searchVal  = document.getElementById('savedSearchInput')?.value.toLowerCase() || '';
  const countryVal = document.getElementById('savedCountrySelector')?.value || 'all';
  const sectorVal  = document.getElementById('savedSectorSelector')?.value || 'all';

  let filtered = [...window.SensioSavedData.tenders];

  if (searchVal.trim() !== '') {
    filtered = filtered.filter(item =>
      (item.title || '').toLowerCase().includes(searchVal) ||
      (item.description || '').toLowerCase().includes(searchVal)
    );
  }

  if (countryVal !== 'all') {
    filtered = filtered.filter(item => (item.country || '').toLowerCase() === countryVal);
  }

  if (sectorVal !== 'all') {
    filtered = filtered.filter(item => (item.category || '').toLowerCase() === sectorVal);
  }

  const counter = document.getElementById('savedCounterMetric');
  if (counter) counter.textContent = filtered.length;

  if (filtered.length === 0) {
    grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 48px; color: var(--text-muted);">No saved tenders match the selection, or your portfolio is empty. Bookmark items from the dashboard or repository tabs.</div>`;
    return;
  }

  grid.innerHTML = filtered.map(item => {
    const daysLeft = calculateDaysRemaining(item.closingDate);
    let badgeHtml = '';

    if (daysLeft < 0) {
      badgeHtml = `<div class="urgency-badge" style="background-color:#fee2e2; color:#ef4444;">Expired</div>`;
    } else if (daysLeft <= 7) {
      badgeHtml = `<div class="urgency-badge urgency-closing">⏰ Closing Soon (${daysLeft}d remaining)</div>`;
    } else {
      badgeHtml = `<div class="urgency-badge urgency-active">✅ Active (${daysLeft}d remaining)</div>`;
    }

    return `
      <div class="tender-card fade-in-up">
        <button class="save-btn saved" onclick="unsaveTenderFromSavedPage('${item.id}', this)" title="Remove from Saved">⭐</button>
        <div>
          <h3 class="tender-card-title">${item.title}</h3>
          ${badgeHtml}
          <div class="tender-card-dates">
            <div class="date-row"><span class="date-label">Opening Phase:</span><span class="date-val">${item.openingDate}</span></div>
            <div class="date-row"><span class="date-label">Deadline Phase:</span><span class="date-val">${item.closingDate}</span></div>
            ${item.starredBy ? `<div class="date-row"><span class="date-label">Starred by:</span><span class="date-val">${item.starredBy}</span></div>` : ''}
          </div>
        </div>
        <div class="relevancy-score-container">
          <span class="relevancy-label">Relevancy Core</span>
          <span class="relevancy-pill">${(item.relevancyScore * 100).toFixed(0)}%</span>
        </div>
        <button class="btn btn-ghost" onclick="openTenderModal('${item.id}')" style="margin-top:14px; width:100%; justify-content:center; font-size:13px;">View Specifications</button>
      </div>
    `;
  }).join('');
}

/*
  Unsave waits for the server to confirm the row was actually updated in
  saved_tenders.xlsx before touching the UI. If the request fails or gets
  cut off (e.g. by navigation), the card stays put and the button
  re-enables — so the UI can never silently drift ahead of the Excel file.
*/
function unsaveTenderFromSavedPage(tenderId, buttonEl) {
  const founderName = typeof getCurrentFounder === 'function' ? getCurrentFounder() : null;
  if (buttonEl) buttonEl.disabled = true;

  fetch(`${window.location.origin}/api/save-tender`, {
    method: 'POST',
    mode: 'cors',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tenderId: tenderId, isSaved: false, founderName: founderName })
  })
    .then(res => {
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      return res.json();
    })
    .then(data => {
      console.log('[Saved Tenders]: Removed, saved count is now', data.savedCount);
      if (window.SensioSavedIds) window.SensioSavedIds.delete(String(tenderId));
      window.SensioSavedData.tenders = window.SensioSavedData.tenders.filter(t => t.id !== tenderId);
      renderSavedTenders();
      initializeSavedCountryDropdown();
    })
    .catch(err => {
      console.error('[Saved Tenders]: Failed to remove from backend.', err);
      alert('Could not remove this tender — the server did not confirm the change. Please try again.');
      if (buttonEl) buttonEl.disabled = false;
    });
}