/* ═══════════════════════════════════════
   SAVED PORTFOLIO GRAPHICS GENERATION ENGINE
   ════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  initializeSavedCountryDropdown();
  renderSavedTenders();
  registerSavedListeners();
});

function initializeSavedCountryDropdown() {
  const select = document.getElementById('savedCountrySelector');
  if (!select) return;

  const savedIds = getSavedTenders();
  const dataset = (window.SensioData?.tenders || []).filter(item => savedIds.includes(item.id));
  const uniqueCountries = [...new Set(dataset.map(item => item.country))].sort();

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

  const savedIds = getSavedTenders();
  let filtered = (window.SensioData?.tenders || []).filter(item => savedIds.includes(item.id));

  // Search filter
  if (searchVal.trim() !== '') {
    filtered = filtered.filter(item => 
      item.title.toLowerCase().includes(searchVal) || 
      item.description.toLowerCase().includes(searchVal)
    );
  }

  // Country filter
  if (countryVal !== 'all') {
    filtered = filtered.filter(item => item.country.toLowerCase() === countryVal);
  }

  // Sector filter
  if (sectorVal !== 'all') {
    filtered = filtered.filter(item => item.category.toLowerCase() === sectorVal);
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
        <button class="save-btn saved" onclick="handleSaveToggle('${item.id}', this)" title="Remove from Saved">⭐</button>
        <div>
          <h3 class="tender-card-title">${item.title}</h3>
          ${badgeHtml}
          <div class="tender-card-dates">
            <div class="date-row"><span class="date-label">Opening Phase:</span><span class="date-val">${item.openingDate}</span></div>
            <div class="date-row"><span class="date-label">Deadline Phase:</span><span class="date-val">${item.closingDate}</span></div>
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