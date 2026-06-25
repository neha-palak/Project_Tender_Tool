/* ═══════════════════════════════════════
   CENTRALIZED INTERACTIVE DOM ENGINE & PERSISTENCE
   ════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  setupSidebarControls();
  setupModalDismissals();
});

function setupSidebarControls() {
  const toggleBtn = document.getElementById('sidebarToggleBtn');
  const sidebar = document.getElementById('sidebar');
  const mainContent = document.getElementById('mainContent');
  
  if (toggleBtn && sidebar && mainContent) {
    toggleBtn.addEventListener('click', () => {
      sidebar.classList.toggle('collapsed');
      mainContent.classList.toggle('collapsed');
      toggleBtn.querySelector('span').textContent = sidebar.classList.contains('collapsed') ? '▶' : '◀';
    });
  }
}

/* LOCALSTORAGE STORAGE PORTFOLIO CONTROLS */
function getSavedTenders() {
  const saved = localStorage.getItem('sensio_saved_tenders');
  return saved ? JSON.parse(saved) : [];
}

function toggleSaveTender(id) {
  let saved = getSavedTenders();
  if (saved.includes(id)) {
    saved = saved.filter(savedId => savedId !== id);
  } else {
    saved.push(id);
  }
  localStorage.setItem('sensio_saved_tenders', JSON.stringify(saved));
  return saved.includes(id);
}

function isTenderSaved(id) {
  return getSavedTenders().includes(id);
}

/* CROSS-COMPATIBLE ACTION DISPATCHER FOR SAVE EVENT CLICK */
/* CROSS-COMPATIBLE ACTION DISPATCHER FOR SAVE EVENT CLICK */
function handleSaveToggle(tenderId, element) {
  const isSaved = toggleSaveTender(tenderId);
  if (isSaved) {
    element.classList.add('saved');
    element.innerHTML = '⭐';
    element.title = 'Remove from Saved';
  } else {
    element.classList.remove('saved');
    element.innerHTML = '☆';
    element.title = 'Save Tender';
  }
  
  // ──── SYNC SAVE STATE WITH PYTHON FLASK BACKEND FOR GMAIL TRIGGERS ────
  fetch('http://127.0.0.1:5001/api/save-tender', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      tenderId: tenderId,
      isSaved: isSaved
    })
  })
  .then(response => response.json())
  .then(data => console.log('[Sync Server App State]: Cache updated, saved count is', data.savedCount))
  .catch(err => console.error('[Sync Server App Failure]: Could not connect to notification pipeline.', err));

  // Conditionally refresh active page rendering pipelines
  if (typeof executePipelineQueryRender === 'function') executePipelineQueryRender();
  if (typeof renderSavedTenders === 'function') renderSavedTenders();
  if (typeof renderTopTenWidget === 'function') renderTopTenWidget();
}

function openTenderModal(tenderId) {
  const tenders = window.SensioData?.tenders || [];
  const tender = tenders.find(t => t.id === tenderId);
  if (!tender) return;

  const overlay = document.getElementById('tenderModalOverlay');
  if (!overlay) return;

  // Map Data Properties Directly Into Elements
  document.getElementById('modalTitle').textContent = tender.title;
  document.getElementById('modalDescription').textContent = tender.description;
  document.getElementById('modalEligibility').textContent = tender.eligibility;
  
  const grid = document.getElementById('modalGrid');
  if (grid) {
    grid.innerHTML = `
      <div class="modal-section"><div class="modal-section-label">Country</div><div><strong>${tender.country}</strong></div></div>
      <div class="modal-section"><div class="modal-section-label">Category</div><div style="text-transform: capitalize;">${tender.category}</div></div>
      <div class="modal-section"><div class="modal-section-label">Budget Range</div><div>₹${tender.budgetINR.toLocaleString('en-IN')}</div></div>
      <div class="modal-section"><div class="modal-section-label">Relevancy Weight</div><div><strong>${(tender.relevancyScore * 100).toFixed(0)}% Match</strong></div></div>
    `;
  }

  // Inject Dedicated External Link Actions
  const linkWrap = document.getElementById('modalLink');
  if (linkWrap) {
    linkWrap.innerHTML = `<a href="${tender.link}" target="_blank" class="btn btn-primary" style="margin-top:6px; font-size:13px;">🌐 View Raw Source File Portal</a>`;
  }

  overlay.style.display = 'flex';
}

function setupModalDismissals() {
  document.querySelectorAll('[data-modal-close]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const targetId = btn.getAttribute('data-modal-close');
      const targetEl = document.getElementById(targetId);
      if (targetEl) targetEl.style.display = 'none';
    });
  });
  
  const overlay = document.getElementById('tenderModalOverlay');
  if (overlay) {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.style.display = 'none';
    });
  }
}

// Global Core Time Logic Calculators
function calculateDaysRemaining(targetDateStr) {
  const target = new Date(targetDateStr);
  const current = new Date("2026-05-21"); // Synchronized Anchor Time context
  const diffTime = target - current;
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
}
