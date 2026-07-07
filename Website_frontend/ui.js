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

/* SAVE STATE — sourced entirely from window.SensioSavedIds (loaded from
   saved_tenders.xlsx via the backend in data.js). No localStorage. */
function isTenderSaved(id) {
  return window.SensioSavedIds ? window.SensioSavedIds.has(String(id)) : false;
}

// function handleSaveToggle(tenderId, element) {
//   const nextSaved = !isTenderSaved(tenderId);

//   // Prevent a double-click firing two toggles before the first response lands.
//   element.disabled = true;

//   fetch('http://127.0.0.1:5001/api/save-tender', {
//     method: 'POST',
//     headers: { 'Content-Type': 'application/json' },
//     body: JSON.stringify({ tenderId: tenderId, isSaved: nextSaved })
//   })
//     .then(response => {
//       if (!response.ok) throw new Error(`Server returned ${response.status}`);
//       return response.json();
//     })
//     .then(data => {
//       // Only flip local/UI state once the server has actually confirmed
//       // the write to saved_tenders.xlsx succeeded.
//       if (nextSaved) window.SensioSavedIds.add(String(tenderId));
//       else window.SensioSavedIds.delete(String(tenderId));

//       element.classList.toggle('saved', nextSaved);
//       element.innerHTML = nextSaved ? '⭐' : '☆';
//       element.title = nextSaved ? 'Remove from Saved' : 'Save Tender';
//       console.log('[Sync Server App State]: Cache updated, saved count is', data.savedCount);

//       if (typeof executePipelineQueryRender === 'function') executePipelineQueryRender();
//       if (typeof renderSavedTenders === 'function') renderSavedTenders();
//       if (typeof renderTopTenWidget === 'function') renderTopTenWidget();
//     })
//     .catch(err => {
//       console.error('[Sync Server App Failure]: Could not connect to notification pipeline.', err);
//       alert('Could not update the saved list — the server did not confirm the change. Please try again.');
//     })
//     .finally(() => {
//       element.disabled = false;
//     });
// }

function handleSaveToggle(tenderId, element) {
  const founderName = getCurrentFounder();
  if (!founderName) {
    ensureFounderIdentity().then(() => handleSaveToggle(tenderId, element));
    return;
  }

  const nextSaved = !isTenderSaved(tenderId);
  element.disabled = true;

  fetch(`${window.location.origin}/api/save-tender`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tenderId: tenderId, isSaved: nextSaved, founderName: founderName })
  })
    .then(response => {
      if (!response.ok) throw new Error(`Server returned ${response.status}`);
      return response.json();
    })
    .then(data => {
      if (nextSaved) window.SensioSavedIds.add(String(tenderId));
      else window.SensioSavedIds.delete(String(tenderId));
      element.classList.toggle('saved', nextSaved);
      element.innerHTML = nextSaved ? '⭐' : '☆';
      element.title = nextSaved ? 'Remove from Saved' : 'Save Tender';
      if (typeof executePipelineQueryRender === 'function') executePipelineQueryRender();
      if (typeof renderSavedTenders === 'function') renderSavedTenders();
      if (typeof renderTopTenWidget === 'function') renderTopTenWidget();
    })
    .catch(err => {
      console.error('[Sync Server App Failure]:', err);
      alert('Could not update the saved list — the server did not confirm the change. Please try again.');
    })
    .finally(() => { element.disabled = false; });
}

function openTenderModal(tenderId) {
  const tenders = window.SensioData?.tenders || [];
  const tender = tenders.find(t => t.id === tenderId);
  if (!tender) return;

  const overlay = document.getElementById('tenderModalOverlay');
  if (!overlay) return;

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

function calculateDaysRemaining(targetDateStr) {
  const target = new Date(targetDateStr);
  const current = new Date("2026-05-21");
  const diffTime = target - current;
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
}
// 👈 replace with your actual 3 founder names
const FOUNDER_NAMES = ["Venkatesh", "Kenneth", "Mohan"];

function getCurrentFounder() {
  return localStorage.getItem('sensio_founder_identity') || null;
}

function setCurrentFounder(name) {
  localStorage.setItem('sensio_founder_identity', name);
}

function ensureFounderIdentity() {
  return new Promise(resolve => {
    const existing = getCurrentFounder();
    if (existing) { resolve(existing); return; }
    showIdentityModal(resolve);
  });
}

function showIdentityModal(onSelect) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.style.display = 'flex';
  overlay.innerHTML = `
    <div class="modal" style="max-width:360px;">
      <div class="modal-header"><div class="modal-title">Who's using Sensio?</div></div>
      <div class="modal-section">
        <select id="founderIdentitySelect" class="filter-select" style="width:100%;">
          ${FOUNDER_NAMES.map(n => `<option value="${n}">${n}</option>`).join('')}
        </select>
      </div>
      <div class="modal-footer">
        <button class="btn btn-primary" id="founderIdentityConfirmBtn" style="width:100%; justify-content:center;">Continue</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  document.getElementById('founderIdentityConfirmBtn').addEventListener('click', () => {
    const name = document.getElementById('founderIdentitySelect').value;
    setCurrentFounder(name);
    document.body.removeChild(overlay);
    updateIdentityBadge();
    onSelect(name);
  });
}

function updateIdentityBadge() {
  const avatar = document.querySelector('.avatar');
  const name = getCurrentFounder();
  if (avatar && name) {
    avatar.textContent = name.charAt(0).toUpperCase();
    avatar.title = `Signed in as ${name} — click to switch`;
    avatar.style.cursor = 'pointer';
    avatar.onclick = () => showIdentityModal(() => updateIdentityBadge());
  }
}

document.addEventListener('DOMContentLoaded', () => {
  setupSidebarControls();
  setupModalDismissals();
  ensureFounderIdentity().then(updateIdentityBadge);
});
// /* ═══════════════════════════════════════
//    CENTRALIZED INTERACTIVE DOM ENGINE & PERSISTENCE
//    ════════════════════════════════════════ */
// document.addEventListener('DOMContentLoaded', () => {
//   setupSidebarControls();
//   setupModalDismissals();
// });

// function setupSidebarControls() {
//   const toggleBtn = document.getElementById('sidebarToggleBtn');
//   const sidebar = document.getElementById('sidebar');
//   const mainContent = document.getElementById('mainContent');
  
//   if (toggleBtn && sidebar && mainContent) {
//     toggleBtn.addEventListener('click', () => {
//       sidebar.classList.toggle('collapsed');
//       mainContent.classList.toggle('collapsed');
//       toggleBtn.querySelector('span').textContent = sidebar.classList.contains('collapsed') ? '▶' : '◀';
//     });
//   }
// }

// /* LOCALSTORAGE STORAGE PORTFOLIO CONTROLS */
// function getSavedTenders() {
//   const saved = localStorage.getItem('sensio_saved_tenders');
//   return saved ? JSON.parse(saved) : [];
// }

// function toggleSaveTender(id) {
//   let saved = getSavedTenders();
//   if (saved.includes(id)) {
//     saved = saved.filter(savedId => savedId !== id);
//   } else {
//     saved.push(id);
//   }
//   localStorage.setItem('sensio_saved_tenders', JSON.stringify(saved));
//   return saved.includes(id);
// }

// function isTenderSaved(id) {
//   return getSavedTenders().includes(id);
// }

// /* CROSS-COMPATIBLE ACTION DISPATCHER FOR SAVE EVENT CLICK */
// /* CROSS-COMPATIBLE ACTION DISPATCHER FOR SAVE EVENT CLICK */
// function handleSaveToggle(tenderId, element) {
//   const isSaved = toggleSaveTender(tenderId);
//   if (isSaved) {
//     element.classList.add('saved');
//     element.innerHTML = '⭐';
//     element.title = 'Remove from Saved';
//   } else {
//     element.classList.remove('saved');
//     element.innerHTML = '☆';
//     element.title = 'Save Tender';
//   }
  
//   // ──── SYNC SAVE STATE WITH PYTHON FLASK BACKEND FOR GMAIL TRIGGERS ────
//   fetch('http://127.0.0.1:5001/api/save-tender', {
//     method: 'POST',
//     headers: {
//       'Content-Type': 'application/json'
//     },
//     body: JSON.stringify({
//       tenderId: tenderId,
//       isSaved: isSaved
//     })
//   })
//   .then(response => response.json())
//   .then(data => console.log('[Sync Server App State]: Cache updated, saved count is', data.savedCount))
//   .catch(err => console.error('[Sync Server App Failure]: Could not connect to notification pipeline.', err));

//   // Conditionally refresh active page rendering pipelines
//   if (typeof executePipelineQueryRender === 'function') executePipelineQueryRender();
//   if (typeof renderSavedTenders === 'function') renderSavedTenders();
//   if (typeof renderTopTenWidget === 'function') renderTopTenWidget();
// }

// function openTenderModal(tenderId) {
//   const tenders = window.SensioData?.tenders || [];
//   const tender = tenders.find(t => t.id === tenderId);
//   if (!tender) return;

//   const overlay = document.getElementById('tenderModalOverlay');
//   if (!overlay) return;

//   // Map Data Properties Directly Into Elements
//   document.getElementById('modalTitle').textContent = tender.title;
//   document.getElementById('modalDescription').textContent = tender.description;
//   document.getElementById('modalEligibility').textContent = tender.eligibility;
  
//   const grid = document.getElementById('modalGrid');
//   if (grid) {
//     grid.innerHTML = `
//       <div class="modal-section"><div class="modal-section-label">Country</div><div><strong>${tender.country}</strong></div></div>
//       <div class="modal-section"><div class="modal-section-label">Category</div><div style="text-transform: capitalize;">${tender.category}</div></div>
//       <div class="modal-section"><div class="modal-section-label">Budget Range</div><div>₹${tender.budgetINR.toLocaleString('en-IN')}</div></div>
//       <div class="modal-section"><div class="modal-section-label">Relevancy Weight</div><div><strong>${(tender.relevancyScore * 100).toFixed(0)}% Match</strong></div></div>
//     `;
//   }

//   // Inject Dedicated External Link Actions
//   const linkWrap = document.getElementById('modalLink');
//   if (linkWrap) {
//     linkWrap.innerHTML = `<a href="${tender.link}" target="_blank" class="btn btn-primary" style="margin-top:6px; font-size:13px;">🌐 View Raw Source File Portal</a>`;
//   }

//   overlay.style.display = 'flex';
// }

// function setupModalDismissals() {
//   document.querySelectorAll('[data-modal-close]').forEach(btn => {
//     btn.addEventListener('click', (e) => {
//       const targetId = btn.getAttribute('data-modal-close');
//       const targetEl = document.getElementById(targetId);
//       if (targetEl) targetEl.style.display = 'none';
//     });
//   });
  
//   const overlay = document.getElementById('tenderModalOverlay');
//   if (overlay) {
//     overlay.addEventListener('click', (e) => {
//       if (e.target === overlay) overlay.style.display = 'none';
//     });
//   }
// }

// // Global Core Time Logic Calculators
// function calculateDaysRemaining(targetDateStr) {
//   const target = new Date(targetDateStr);
//   const current = new Date("2026-05-21"); // Synchronized Anchor Time context
//   const diffTime = target - current;
//   return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
// }
