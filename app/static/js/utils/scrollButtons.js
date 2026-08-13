(function () {
  if (document.getElementById('scroll-buttons-container')) return;

  const container = document.createElement('div');
  container.id = 'scroll-buttons-container';
  container.className = 'scroll-button';
  container.style.cssText = `
    position: fixed;
    bottom: 10px;
    right: 10px;         
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    z-index: 9999;
    pointer-events: none;
  `;

  function createBtn(isTop) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.style.cssText = `
      background: transparent;
      border: none;
      outline: none;
      width: 32px;
      height: 32px;
      padding: 0;
      margin: 0;
      cursor: pointer;
      pointer-events: auto;
      transition: transform 0.2s ease, opacity 0.2s ease;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 2px;
    `;

    const arrow = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    arrow.setAttribute('width', '18');
    arrow.setAttribute('height', '18');
    arrow.setAttribute('viewBox', '0 0 24 24');
    arrow.style.transition = 'fill 0.2s ease';

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', '#000');
    path.setAttribute('stroke-width', '2');
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');

    if (isTop) {
      path.setAttribute('d', 'M12 19V5M5 12l7-7 7 7');
    } else {
      path.setAttribute('d', 'M12 5v14M5 12l7 7 7-7');
    }

    arrow.appendChild(path);
    btn.appendChild(arrow);

    btn.onmouseenter = () => {
      path.setAttribute('stroke', '#06cff3');
      btn.style.transform = 'scale(1.2)';
    };
    btn.onmouseleave = () => {
      path.setAttribute('stroke', '#000');
      btn.style.transform = 'scale(1)';
    };

    btn.onclick = (e) => {
      e.stopPropagation();
      e.preventDefault();
      if (isTop) {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } else {
        window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
      }
    };

    return btn;
  }

  const topBtn = createBtn(true);
  const bottomBtn = createBtn(false);

  topBtn.style.display = 'none';
  container.appendChild(topBtn);
  container.appendChild(bottomBtn);
  document.body.appendChild(container);

  function updateVisibility() {
    topBtn.style.display = window.scrollY > 10 ? 'flex' : 'none';
  }

  let ticking = false;
  window.addEventListener('scroll', () => {
    if (!ticking) {
      requestAnimationFrame(() => {
        updateVisibility();
        ticking = false;
      });
      ticking = true;
    }
  });

  updateVisibility();
})();
