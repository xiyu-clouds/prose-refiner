function buildModalContent(title, contentHtml) {
  return `
    <div class="modal-content-wrapper">
      <div class="modal-header">
        <h3 class="modal-title">${escapeHtml(title)}</h3>
        <button class="modal-close" onclick="closeModal()">×</button>
      </div>
      <div class="modal-item-form">
        ${contentHtml}
      </div>
    </div>
  `;
}

function buildModalContentWithGap(title, contentHtml) {
  return `
    <div class="modal-content-wrapper">
      <div class="modal-header">
        <h3 class="modal-title">${escapeHtml(title)}</h3>
        <button class="modal-close" onclick="closeModal()">×</button>
      </div>
      <div class="modal-item-form" style="gap: 16px;">
        ${contentHtml}
      </div>
    </div>
  `;
}

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  sidebar.classList.toggle('collapsed');
}

function closeModal() {
  const overlay = document.getElementById('modalOverlay');
  const modalContent = document.getElementById('modalContent');
  if (overlay) overlay.style.display = 'none';
  if (modalContent && window.__originalModalContent) {
    modalContent.innerHTML = window.__originalModalContent;
  }
  if (window.removeRelationshipEventDelegation) {
    window.removeRelationshipEventDelegation();
  }
}

(function() {
  const modalContent = document.getElementById('modalContent');
  if (modalContent) {
    window.__originalModalContent = modalContent.innerHTML;
  }
})();

window.buildModalContent = buildModalContent;
window.buildModalContentWithGap = buildModalContentWithGap;
window.toggleSidebar = toggleSidebar;
window.closeModal = closeModal;