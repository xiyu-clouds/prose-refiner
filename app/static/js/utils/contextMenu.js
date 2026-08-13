// contextMenu.js
(function () {
  // 防止重复加载
  if (window.CustomContextMenuLoaded) return;
  window.CustomContextMenuLoaded = true;

  // ====== 1. 创建菜单 DOM ======
  const menuHTML = buildMenuHTML()

  const styleCSS = `
/* === 彻底重置 === */
.custom-context-menu.card,
.custom-context-menu.card *,
.custom-context-menu.card *::before,
.custom-context-menu.card *::after {
  box-sizing: border-box;
}

div.custom-context-menu.card {
  position: fixed !important;
  top: 0;
  left: 0;
  z-index: 10000 !important;
  width: 210px !important;
  height: auto !important;
  background: #1e222a !important;
  border-radius: 10px !important;
  padding: 4px 0 !important;
  display: flex !important;
  flex-direction: column !important;
  flex-wrap: nowrap !important;
  gap: 0 !important;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.5) !important;
  opacity: 0;
  transform: scale(0.95);
  transition: opacity 0.2s ease, transform 0.2s ease;
  pointer-events: none;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
  max-height: calc(100vh - 40px) !important;
  overflow-y: auto !important;
}

.custom-context-menu.card::-webkit-scrollbar {
  width: 0;
  height: 0;
  background: transparent;
}

.custom-context-menu.card .element:hover {
  background-color: #4a90e2 !important;
  color: #ffffff !important;
}

/* 分隔线 */
.custom-context-menu.card .separator {
  height: 1px !important;
  background: #3a3f4b;
  margin: 3px 8px !important;
}

/* 列表：现在由列表自身控制上下内边距 */
.custom-context-menu.card .list {
  list-style: none;
  padding: 2px 8px !important;
  margin: 0 !important;
  display: flex;
  flex-direction: column;
  gap: 1px !important;
}

/* 子菜单项 */
.custom-context-menu.card .element {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px !important;
  border-radius: 5px;
  cursor: pointer;
  color: #cfd2d7;
  height: auto;
  min-height: 32px;
  line-height: 1.4 !important;
  font-size: 13px !important;
  font-weight: 500;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
  transition: background-color 0.2s ease, color 0.2s ease;
  background: transparent !important;
  border: none !important;
  outline: none !important;
  box-shadow: none !important;
  margin: 0 !important;
}

.custom-context-menu.card .element > * {
  margin: 0 !important;
  padding: 0 !important;
  background: transparent !important;
  border: none !important;
  outline: none !important;
  box-shadow: none !important;
  color: inherit;
}

.custom-context-menu.card .element svg {
  width: 19px;
  height: 19px;
  stroke: currentColor;
  stroke-width: 2;
  flex-shrink: 0;
}

/* 上半区 hover */
.custom-context-menu.card .list:first-child .element:hover {
  background-color: #5353ff;
  color: #ffffff;
}

/* 下半区样式 */
.custom-context-menu.card .list:last-child .element {
  color: #d1aaff;
}
.custom-context-menu.card .list:last-child .element:hover {
  background-color: #463264;
  color: #ffffff;
}

.custom-context-menu.card .element:active {
  opacity: 0.92;
}
`;

  // 插入样式
  const styleEl = document.createElement('style');
  styleEl.textContent = styleCSS;
  document.head.appendChild(styleEl);

  // 创建菜单
  const menuDiv = document.createElement('div');
  menuDiv.innerHTML = menuHTML.trim();
  const menu = menuDiv.firstElementChild;
  document.body.appendChild(menu);

  // ====== 2. 菜单显示/隐藏逻辑 ======
  function showMenu(x, y) {
    // 防止超出视口
    const rect = menu.getBoundingClientRect();
    const maxX = window.innerWidth - rect.width - 10;
    const maxY = window.innerHeight - rect.height - 10;
    const posX = Math.min(x, maxX);
    const posY = Math.min(y, maxY);

    menu.style.left = `${posX}px`;
    menu.style.top = `${posY}px`;
    menu.style.opacity = '1';
    menu.style.transform = 'scale(1)';
    menu.style.pointerEvents = 'auto';
  }

  function hideMenu() {
    menu.style.opacity = '0';
    menu.style.pointerEvents = 'none';
  }

// ====== 稳定可靠的菜单显示/关闭逻辑（基于 pointerdown） ======
let isMenuVisible = false;

// 单一全局监听器（capture 阶段，抗干扰）
document.addEventListener('pointerdown', function (e) {
  // 忽略非左键
  if (e.button !== 0) return;

  // 精准排除原生滚动条点击
  const clickedElement = document.elementFromPoint(e.clientX, e.clientY);
  // 如果获取不到元素，或者获取到的元素不是当前鼠标坐标下的真实元素（说明点在了滚动条等非DOM区域）
  if (!clickedElement || !clickedElement.contains(e.target)) {
    return;
  }

  // 排除避免点击弹出菜单栏的区域
  if (
    e.target.closest('.modal-overlay') ||
    e.target.closest('.modal-box') ||
    e.target.closest('.scroll-button') ||
    e.target.closest('.meta-header-details') ||
    e.target.closest('.psy-glass-nav') ||
    e.target.closest('#psytext-global-nav') ||
    e.target.closest('.container') ||
    e.target.closest('#minimized-hints') ||
    e.target.closest('#task-notifications') ||
    e.target.closest('#psytext-header-typewriter') ||
    e.target.closest('#psytext-footer') ||
    e.target.closest('.psytext-injected') ||
    e.target.closest('.xh-confirm-overlay') ||
    e.target.closest('.xh-confirm-modal')  ||
    e.target.closest('.intervention-modal') ||
    e.target.closest('.edit-modal') ||
    e.target.closest('.edit-overlay') ||
    e.target.closest('.preview-modal') ||
    e.target.closest('.preview-overlay') ||
    e.target.closest('.hero-loader-wrapper')
  ) {
    return;
  }

  const clickedOnMenu = e.target.closest('.custom-context-menu');

  if (clickedOnMenu) {
    // 点击菜单项：由 menu.click 处理，这里不干预
    return;
  }

  if (isMenuVisible) {
    // 菜单已打开，现在点外部 → 关闭
    hideMenu();
    isMenuVisible = false;
  } else {
    // 菜单未打开 → 显示
    showMenu(e.clientX, e.clientY);
    isMenuVisible = true;
  }
}, true);

// 菜单项点击（只需 hide + 执行，不用管监听器）
menu.addEventListener('click', (e) => {
  e.preventDefault();
  const action = e.target.closest('.element')?.dataset.action;
  if (!action) return;

  hideMenu();
  isMenuVisible = false; // 👈 关键：同步状态

  console.log('Triggered:', action);
  switch (action) {
    case 'playMusic': showPlayMusic(); break;
    case 'pexelesImage': showPexelesImage(); break;
    case 'unsplashImage': showUnsplashImage(); break;
    case 'earthRotation': showEarthRotation();  break;
    case 'cubeRotation': showCubeRotation(); break;
    case 'box3d': showBox3d(); break;
    case 'terminal': showTerminal(); break;
    case 'deviceAuth': showDeviceAuth(); break;
    // case 'scheduleTask':
    //   showScheduleTask();
    //   break;
    // case 'notificationSettings':
    //   showNotificationSettings();
    //   break;
  }
});

function buildMenuHTML() {
  return `
<div class="custom-context-menu card">
  <ul class="list">
    <li class="element" data-action="playMusic">
      <svg xmlns="http://www.w3.org/2000/svg" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M9 18V5l12-2v13"></path>
        <circle cx="6" cy="18" r="3"></circle>
        <circle cx="18" cy="16" r="3"></circle>
      </svg>
      <span class="label">Play Music</span>
    </li>
    <li class="element" data-action="pexelesImage">
      <svg xmlns="http://www.w3.org/2000/svg" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
        <circle cx="9" cy="9" r="2"></circle>
        <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"></path>
      </svg>
      <span class="label">Pexeles Image</span>
    </li>
    <li class="element" data-action="unsplashImage">
      <svg xmlns="http://www.w3.org/2000/svg" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 18V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14c0 1.1.9 2 2 2h14a2 2 0 0 0 2-2z"></path>
        <circle cx="9" cy="9" r="2"></circle>
        <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"></path>
      </svg>
      <span class="label">Unsplash Image</span>
    </li>
  </ul>
  <div class="separator"></div>
  <ul class="list">
    <li class="element" data-action="earthRotation">
      <svg xmlns="http://www.w3.org/2000/svg" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="2" x2="22" y1="12" y2="12"></line>
        <path d="m9 2 3 18 3-18"></path>
      </svg>
      <span class="label">Earth Rotation</span>
    </li>
    <li class="element" data-action="cubeRotation">
      <svg xmlns="http://www.w3.org/2000/svg" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
        <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
        <line x1="12" x2="12" y1="22.08" y2="12"></line>
      </svg>
      <span class="label">Cube Rotation</span>
    </li>
    <li class="element" data-action="box3d">
      <svg xmlns="http://www.w3.org/2000/svg" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"></path>
        <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
        <line x1="12" x2="12" y1="22.08" y2="12"></line>
      </svg>
      <span class="label">3D Box</span>
    </li>
  </ul>
  <div class="separator"></div>
  <ul class="list">
    <li class="element" data-action="terminal">
      <svg xmlns="http://www.w3.org/2000/svg" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="4 17 10 11 4 5"></polyline>
        <line x1="12" x2="20" y1="19" y2="19"></line>
      </svg>
      <span class="label">终端日志</span>
    </li>
    <li class="element" data-action="deviceAuth">
      <svg xmlns="http://www.w3.org/2000/svg" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect width="18" height="11" x="3" y="11" rx="2" ry="2"></rect>
        <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
      </svg>
      <span class="label">设备授权</span>
    </li>
  </ul>
</div>
`;
}

/**
 * 创建支持多窗口最小化的处理器
 * @param {string} message - 提示文本（建议 ≤ 20 字）
 * @param {function} onRestore - 恢复回调
 * @param {Object} restoreConfig - 跨页面重建所需配置（纯数据）
 */
function createMinimizableHandler(message, onRestore, restoreConfig = null) {
  return (hideModal, hintContainerParent) => {
    const container = hintContainerParent || ensureMinimizedHintsContainer();
    if (!container) return;

    const item = document.createElement('div');
    item.className = 'minimized-hint-item';
    item.title = message;
    item.textContent = message;

    const restore = () => {
      item.remove();
      // 清理 localStorage（无论同页还是跨页）
      if (restoreConfig?.id) {
        const tasks = JSON.parse(localStorage.getItem('__minimized_tasks') || '[]');
        const updated = tasks.filter(t => t.id !== restoreConfig.id);
        localStorage.setItem('__minimized_tasks', JSON.stringify(updated));
        if (restoreConfig?.modalOptions?.url?.includes('/play-music.html')) {
          localStorage.removeItem(`__music_state_${restoreConfig.id}`);
        }
        if (restoreConfig?.modalOptions?.url?.includes('/unsplash-image.html')) {
          localStorage.removeItem(`__unsplash_state__${restoreConfig.id}`);
        }
        if (restoreConfig?.modalOptions?.url?.includes('/pexels-image.html')) {
        localStorage.removeItem(`__pexels_state__${restoreConfig.id}`);
      }
      }

      try {
        if (typeof onRestore === 'function') {
          onRestore();
          return;
        }
      } catch (e) {
        console.warn('onRestore 执行失败:', e);
      }

      if (restoreConfig?.id) {
        // ✅ 跨页面恢复：查找已存在的 overlay
        const existingOverlay = document.querySelector(`[data-task-id="${restoreConfig.id}"]`);
        if (existingOverlay) {
          document.body.appendChild(existingOverlay);
          existingOverlay.style.display = 'flex';
          existingOverlay.style.opacity = '1';
        } else if (restoreConfig.restoreFn && typeof window[restoreConfig.restoreFn] === 'function') {
          // 特殊处理：使用全局函数恢复（如终端日志）
          window[restoreConfig.restoreFn]();
        } else if (restoreConfig?.modalOptions) {
          // 极端情况：DOM 被清了（比如页面刷新过），才 fallback 重建
          showModal({
            ...restoreConfig.modalOptions,
            onMinimize: createMinimizableHandler(
              restoreConfig.message || '任务 · 后台运行',
              null,
              restoreConfig
            )
          });
        }
      }
    };

    item.addEventListener('click', (e) => {
      e.stopPropagation();
      restore();
    });

    container.appendChild(item);
    hideModal();
    hideModal.restore = restore;

    // === 写入 localStorage（用于跨页面）===
    if (restoreConfig) {
      const tasks = JSON.parse(localStorage.getItem('__minimized_tasks') || '[]');
      // 防重复
      if (!tasks.some(t => t.id === restoreConfig.id)) {
        tasks.push({ ...restoreConfig, message });
        localStorage.setItem('__minimized_tasks', JSON.stringify(tasks));
      }
    }
  };
}

function ensureMinimizedHintsContainer() {
  let container = document.getElementById('minimized-hints');
  if (!container) {
    container = document.createElement('div');
    container.id = 'minimized-hints';
    Object.assign(container.style, {
      position: 'fixed',
      bottom: '16px',
      left: '16px',
      zIndex: '10000',
      display: 'flex',
      gap: '8px',
      flexWrap: 'wrap',
      maxWidth: 'calc(100vw - 32px)',
      pointerEvents: 'auto',
      width: 'auto',
      flexDirection: 'row',
      alignItems: 'flex-start'
    });
    document.body.appendChild(container);
  } else {
    Object.assign(container.style, {
      position: 'fixed',
      bottom: '16px',
      left: '16px',
      zIndex: '10000',
      display: 'flex',
      gap: '8px',
      flexWrap: 'wrap',
      maxWidth: 'calc(100vw - 32px)',
      pointerEvents: 'auto',
      width: 'auto',
      flexDirection: 'row',
      alignItems: 'flex-start'
    });
  }
  return container;
}

/**
 * 通用模态弹窗加载器
 * @param {Object} options - 配置项
 * @param {string} options.url - 要加载的 HTML 文件路径
 * @param {string} [options.title] - 可选标题
 * @param {number} [options.width=640] - 弹窗宽度（px）
 * @param {number} [options.height=480] - 弹窗高度（px）
 * @param {boolean} [options.closable=true] - 是否可关闭
 * @param {boolean} [options.minimizable=true] - 是否显示最小化按钮
 * @param {function} [options.onMinimize=null] - 最小化回调
 * @param {function} [options.onCloseAttempt=null] - 尝试关闭时的钩子（用于确认）
 * @param {function} [options.onLoad=null] - 是否执行特定js逻辑
 * @param {function} [options.onUnload=null] - 弹窗关闭前执行的清理逻辑
 */
function showModal({ url, title = '', width = 640, height = 480, closable = true, minimizable = true, onMinimize = null, onCloseAttempt = null, onLoad = null, onUnload=null}) {
  // 遮罩层
  const overlay = document.createElement('div');
  overlay.style.cssText = `
    position: fixed;
    top: 0; left: 0; width: 100vw; height: 100vh;
    background: rgba(0, 0, 0, 0.85);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 20000;
    opacity: 0;
    transition: opacity 0.3s ease;
  `;

  // 内容容器
  const modalBox = document.createElement('div');
  modalBox.style.cssText = `
    background: #1e1e1e;
    color: white;
    border-radius: 12px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.6);
    width: ${Math.min(width, window.innerWidth * 0.9)}px;
    max-width: 90vw;
    height: ${Math.min(height, window.innerHeight * 0.9)}px;
    max-height: 90vh;
    overflow-y: auto;
    overflow-x: hidden;
    position: relative;
    opacity: 0;
    transform: scale(0.95);
    transition: opacity 0.3s ease, transform 0.3s ease;
  `;

  overlay.className = 'modal-overlay'; // ← 加 class
  modalBox.className = 'modal-box';   // ← 加 class

  // 添加状态显示容器
  const statusBox = document.createElement('div');
  statusBox.id = 'statusBox';
  statusBox.style.cssText = `
    position: absolute;
    bottom: 20px;
    right: 20px;
    padding: 8px 16px;
    border-radius: 6px;
    color: white;
    font-size: 12px;
    z-index: 10;
    display: none;
    transition: opacity 0.3s ease, transform 0.3s ease;
    pointer-events: none;
  `;

  const globalError = document.createElement('div');
  globalError.id = 'globalError';
  globalError.style.cssText = `
    position: absolute;
    bottom: 20px;
    right: 20px;
    padding: 8px 16px;
    border-radius: 6px;
    color: white;
    font-size: 12px;
    z-index: 10;
    display: none;
    background: #dc3545;
    pointer-events: none;
  `;

  // 创建蒙层（仅在需要时显示）
  const titleBarScrim = document.createElement('div');
  titleBarScrim.style.cssText = `
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 48px;
    background: rgba(0, 0, 0, 0.4);
    backdrop-filter: blur(4px);
    z-index: 1;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.2s ease;
  `;
  modalBox.appendChild(titleBarScrim);

  // ===== 仅在标题区域 hover 时显示蒙层 =====
  let isMouseNearTitle = false;
  let scrimUpdateTimer = null;
  const updateScrimOpacity = () => {
    clearTimeout(scrimUpdateTimer);
    scrimUpdateTimer = setTimeout(() => {
      titleBarScrim.style.opacity = isMouseNearTitle ? '0.8' : '0';
    }, 10);
  };

  // 只在鼠标靠近顶部标题区域时显示蒙层
  modalBox.addEventListener('mousemove', (e) => {
    isMouseNearTitle = e.clientY < modalBox.getBoundingClientRect().top + 60;
    updateScrimOpacity();
  });

  modalBox.addEventListener('mouseleave', () => {
    isMouseNearTitle = false;
    updateScrimOpacity();
  });

  // 标题
  if (title) {
    const titleElement = document.createElement('div');
    titleElement.style.cssText = `
      position: absolute;
      top: 12px;
      left: 16px;
      color: white;
      font-weight: bold;
      z-index: 2;
    `;
    titleElement.textContent = title;
    modalBox.appendChild(titleElement);
  }

  // 最小化按钮
  if (minimizable) {
    const minimizeButton = document.createElement('button');
    minimizeButton.textContent = '—';
    minimizeButton.title = '最小化';
    minimizeButton.style.cssText = `
      position: absolute;
      top: 12px;
      right: ${closable ? '48px' : '16px'};
      background: none;
      border: none;
      color: white;
      font-size: 14px;
      width: 24px;
      height: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      z-index: 2;
    `;
    minimizeButton.addEventListener('click', (e) => {
      e.stopPropagation();
      if (typeof onMinimize === 'function') {
        const hintContainer = document.getElementById('minimized-hints');
        onMinimize(() => {
          overlay.style.display = 'none';
        }, hintContainer);
      } else {
        // 默认行为：仅隐藏弹窗，不操作 #minimized-hints
        overlay.style.display = 'none';
      }
    });
    modalBox.appendChild(minimizeButton);
  }

  // 关闭按钮
  if (closable) {
    const closeButton = document.createElement('button');
    closeButton.textContent = '×';
    closeButton.title = '关闭';
    closeButton.style.cssText = `
      position: absolute;
      top: 12px;
      right: 16px;
      background: none;
      border: none;
      color: white;
      font-size: 24px;
      cursor: pointer;
      z-index: 2;
    `;
    closeButton.addEventListener('click', (e) => {
      e.stopPropagation();
      attemptClose();
    });
    modalBox.appendChild(closeButton);
  }

  // 点击遮罩关闭（仅当 closable 且无阻止）
  if (closable) {
    overlay.addEventListener('click', (e) => {
      if (e.target !== overlay) return;
      if (window.getSelection && window.getSelection().toString().trim()) return;
      attemptClose();
    });
  }

  modalBox.appendChild(statusBox);
  modalBox.appendChild(globalError);
  overlay.appendChild(modalBox);

  // 开始加载内容
  fetch(url)
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      return res.text();
    })
    .then(html => {
      console.log('[DEBUG] HTML loaded, about to append overlay');
      modalBox.insertAdjacentHTML('beforeend', html);
      document.body.appendChild(overlay);
      // 如果提供了 onLoad，就调用它，并传入 modalBox 作为上下文
      if (typeof onLoad === 'function') {
        // 等 DOM 渲染完再执行
        setTimeout(() => {
          onLoad(modalBox);
        }, 0);
      }
      requestAnimationFrame(() => {
        overlay.style.opacity = '1';
        modalBox.style.opacity = '1';
        modalBox.style.transform = 'scale(1)';
      });
    })
    .catch(err => {
      console.error('Modal load failed:', err);
      window.showError(`加载失败：${url}`);
      if (overlay.parentNode) {
        doClose();
      }
    });

  function attemptClose() {
    if (typeof onCloseAttempt === 'function') {
      const result = onCloseAttempt();
      if (result instanceof Promise) {
        result.then(shouldClose => {
          if (shouldClose !== false) {
            doClose();
          }
        });
        return;
      } else if (result === false) {
        return;
      }
    }
    doClose();
  }

  function doClose() {
    if (typeof onUnload === 'function') {
      onUnload(modalBox);
    }

    const taskId = overlay.dataset.taskId;
    if (taskId) {
      const tasks = JSON.parse(localStorage.getItem('__minimized_tasks') || '[]');
      const updated = tasks.filter(t => t.id !== taskId);
      localStorage.setItem('__minimized_tasks', JSON.stringify(updated));

      localStorage.removeItem(`__music_state_${taskId}`);
      localStorage.removeItem(`__unsplash_state__${taskId}`);
      localStorage.removeItem(`__pexels_state__${taskId}`);
    }

    overlay.style.opacity = '0';
    modalBox.style.opacity = '0';
    modalBox.style.transform = 'scale(0.9)';
    setTimeout(() => {
      if (overlay.parentNode) overlay.remove();
    }, 300);
  }

  // 返回 close 方法（可选，用于外部控制）
  return { close: doClose, overlay, modalBox };
}

function showEarthRotation() {
  const taskId = `task-${Date.now()}`;
  const modalOptions = {
    url: '/static/components/earth-rotation.html',
    title: '心海 · 3D 地球展示',
    width: 640,
    height: 480,
    minimizable: true
  };

  const modal = showModal({
    ...modalOptions,
    onMinimize: createMinimizableHandler(
      '地球动画 · 点击恢复',
      // 同页面恢复（快路径）
      () => {
        document.body.appendChild(modal.overlay);
        modal.overlay.style.display = 'flex';
        modal.overlay.style.opacity = '1';
        modal.modalBox.style.opacity = '1';
        modal.modalBox.style.transform = 'scale(1)';
      },
      // 跨页面重建配置（纯数据）
      {
        id: taskId,
        modalOptions: modalOptions,
        message: "地球动画 · 点击恢复"
      }
    )
  });
  modal.overlay.dataset.taskId = taskId;
}

function showCubeRotation() {
  const taskId = `task-${Date.now()}`;
  const modalOptions = {
    url: '/static/components/cube-rotation.html',
    title: '心海 · 3D 魔方展示',
    width: 520,
    height: 360,
    minimizable: true
  };

  const modal = showModal({
    ...modalOptions,
    onMinimize: createMinimizableHandler(
      '魔方动画 · 点击恢复',
      // 同页面恢复（快路径）
      () => {
        document.body.appendChild(modal.overlay);
        modal.overlay.style.display = 'flex';
        modal.overlay.style.opacity = '1';
        modal.modalBox.style.opacity = '1';
        modal.modalBox.style.transform = 'scale(1)';
      },
      // 跨页面重建配置（纯数据）
      {
        id: taskId,
        modalOptions: modalOptions,
        message: "魔方动画 · 点击恢复"
      }
    )
  });
  modal.overlay.dataset.taskId = taskId;
}

function showBox3d() {
  const taskId = `task-${Date.now()}`;
  const modalOptions = {
    url: '/static/components/box3d.html',
    title: '心海 · 3D 盒子展示',
    width: 800,
    height: 660,
    minimizable: true
  };

  const modal = showModal({
    ...modalOptions,
    onMinimize: createMinimizableHandler(
      '3D动画 · 点击恢复',
      // 同页面恢复（快路径）
      () => {
        document.body.appendChild(modal.overlay);
        modal.overlay.style.display = 'flex';
        modal.overlay.style.opacity = '1';
        modal.modalBox.style.opacity = '1';
        modal.modalBox.style.transform = 'scale(1)';
      },
      // 跨页面重建配置（纯数据）
      {
        id: taskId,
        modalOptions: modalOptions,
        message: "3D动画 · 点击恢复"
      }
    )
  });
  modal.overlay.dataset.taskId = taskId;
}



// function showScheduleTask() {
//   showModal({
//     url: '/static/components/schedule-task.html',
//     title: '心海 · 定时任务',
//     width: 800,
//     height: 660
//   });
// }

// function showNotificationSettings() {
//   showModal({
//     url: '/static/components/notification-settings.html',
//     title: '心海 · 通知设置',
//     width: 800,
//     height: 660
//   });
// }

function showPlayMusic() {
  const taskId = `task-${Date.now()}`;
  let playerApi = null;

  const baseOptions = {
    url: `/static/components/play-music.html`,
    title: '心海 · 音乐播放器',
    width: 900,
    height: 600,
    minimizable: true,
    closable: true,
  };

  const modal = showModal({
    ...baseOptions,
    onMinimize: createMinimizableHandler(
      '音乐播放器 · 点击恢复',
      () => {
        document.body.appendChild(modal.overlay);
        modal.overlay.style.display = 'flex';
        modal.overlay.style.opacity = '1';
        modal.modalBox.style.opacity = '1';
        modal.modalBox.style.transform = 'scale(1)';
      },
      {
        id: taskId,
        modalOptions: baseOptions,
        message: "音乐播放器 · 点击恢复"
      }
    ),
    onCloseAttempt: () => {
      return new Promise(resolve => {
        showConfirm({
          title: '确认关闭',
          message: '关闭后音乐将停止，且无法后台播放。\n\n建议点"—"最小化以继续听歌。\n\nℹ️ 跨页面恢复时需点击弹窗才能播放（浏览器安全限制）\n\n确定要关闭吗？',
          confirmText: '确定',
          cancelText: '取消',
          onConfirm: () => resolve(true),
          onCancel: () => resolve(false)
        });
      });
    },
    onLoad: (modalBox) => {
      playerApi = initMusicPlayer(modalBox,null, taskId);
    },
    onUnload: () => {
      if (playerApi && typeof playerApi.cleanup === 'function') {
        playerApi.cleanup();
      }
      // 清理快照
      localStorage.removeItem(`__music_state_${taskId}`);
    }
  });
  modal.overlay.dataset.taskId = taskId;
}

/**
 * @param {HTMLElement} modalBox
 * @param {Object|null} [restoredState=null] - 从缓存恢复的完整状态
 * @param {String|null} [taskId=null] - 从缓存恢复的完整状态
 * @returns {{ cleanup: Function, getState: Function }}
 */
function initMusicPlayer(modalBox, restoredState = null, taskId= null) {
  // ======================
  // 配置 & 状态（略，和之前一样）
  // ======================
  let backgroundImages = [];
  let musicTracks = [];

  async function loadBackgroundImages() {
    try {
      const res = await fetch('/api/images/available-ids');
      if (res.ok) {
        const data = await res.json();
        if (data.ids && data.ids.length > 0) {
          backgroundImages = data.ids.map(id => `/media/image/${id}.png`);
        }
      }
    } catch (e) {
      console.warn('加载背景图片列表失败', e);
    }
  }

  async function loadMusicTracks() {
    try {
      const res = await fetch('/api/audios/');
      if (res.ok) {
        const data = await res.json();
        // 兼容多种响应格式：纯数组 / {items:[]} / {data:[]}
        const list = Array.isArray(data) ? data : (data?.items || data?.data || []);
        if (list.length > 0) {
          // 仅筛选音乐类型（audio_type='music'）且格式为 mp3 的音频
          musicTracks = list
            .filter(audio => audio.audio_type === 'music' && audio.file_format === 'mp3')
            .map(audio => {
              // 使用 file_path 构造媒体 URL（优先），回退到 file_name
              let mediaPath;
              if (audio.file_path && audio.file_path.startsWith('audio/')) {
                mediaPath = `/media/${audio.file_path}`;
              } else if (audio.file_path) {
                mediaPath = `/media/audio/${audio.file_path}`;
              } else {
                mediaPath = `/media/audio/${audio.file_name}`;
              }
              return {
                path: mediaPath,
                name: audio.title || audio.file_name || '未知歌曲',
                artist: audio.artist || '未知艺术家',
                album: audio.album || '',
                duration: audio.duration || 0,
                audioType: audio.audio_type || 'music',
              };
            });
          state.trackBackgrounds = musicTracks.map((_, i) => {
            if (backgroundImages.length === 0) return -1;
            return i % backgroundImages.length;
          });
        } else {
          showEmptyState('暂无音频');
        }
      } else if (res.status === 500) {
        const err = await res.json().catch(() => ({}));
        showEmptyState(err.detail || '加载失败');
      }
    } catch (e) {
      console.warn('加载音频列表失败', e);
      showEmptyState('加载失败');
    }
  }

  function showEmptyState(message) {
    const track = { name: message || '暂无音频', artist: '', path: null };
    musicTracks = [track];
    state.trackBackgrounds = [-1];
    if (dom.playPauseBtn) {
      dom.playPauseBtn.style.opacity = '0.5';
      dom.playPauseBtn.style.pointerEvents = 'none';
    }
  }

  const PLAY_MODE = {
    ORDER: 'order',
    SHUFFLE: 'shuffle',
    SINGLE: 'single'
  };

  const state = {
    currentTrackIndex: restoredState?.currentTrackIndex ?? 0,
    isPlaying: false,
    volume: restoredState?.volume ?? 0.7,
    mode: restoredState?.mode ?? PLAY_MODE.ORDER,
    audio: null,
    lyricLines: [],
    trackBackgrounds: restoredState?.trackBackgrounds || [],
    _restoreTime: restoredState?.currentTime ?? 0
  };

  const dom = {
    trackTitle: modalBox.querySelector('#trackTitle'),
    artistName: modalBox.querySelector('#artistName'),
    lyricDisplay: modalBox.querySelector('#lyricDisplay'),
    playPauseBtn: modalBox.querySelector('#playPauseBtn'),
    prevBtn: modalBox.querySelector('#prevBtn'),
    nextBtn: modalBox.querySelector('#nextBtn'),
    modeBtn: modalBox.querySelector('#modeBtn'),
    modeIcon: modalBox.querySelector('#modeIcon'),
    listBtn: modalBox.querySelector('#listBtn'),
    closeListBtn: modalBox.querySelector('#closeListBtn'),
    changeBgBtn: modalBox.querySelector('#changeBgBtn'),
    volumeToggleBtn: modalBox.querySelector('#volumeToggleBtn'),
    volumeSliderContainer: modalBox.querySelector('#volumeSliderContainer'),
    volumeSlider: modalBox.querySelector('#volumeSlider'),
    volumeValue: modalBox.querySelector('#volumeValue'),
    progressBar: modalBox.querySelector('.progress-bar'),
    progressFill: modalBox.querySelector('.progress-fill'),
    progressHandle: modalBox.querySelector('.progress-handle'),
    currentTime: modalBox.querySelector('.current-time'),
    remainingTime: modalBox.querySelector('.remaining-time'),
    playlistPanel: modalBox.querySelector('#playlistPanel'),
    playlistList: modalBox.querySelector('#playlistList')
  };

  // ======================
  // 工具函数（略）
  // ======================
  function formatTime(seconds) {
    if (isNaN(seconds) || seconds < 0) return '0:00';
    const min = Math.floor(seconds / 60);
    const sec = Math.floor(seconds % 60);
    return `${min}:${sec < 10 ? '0' : ''}${sec}`;
  }

  function parseLRC(lrcText) {
    if (!lrcText || typeof lrcText !== 'string') return [];

    // 关键修复：将字面量的 \\r\\n 和 \\n 转为真实换行
    let cleanText = lrcText
      .replace(/\\r\\n/g, '\n')   // 处理 "\\r\\n"
      .replace(/\\n/g, '\n')      // 处理 "\\n"
      .replace(/\r\n|\r/g, '\n'); // 再处理真实的 \r\n（防御性）

    const lines = cleanText.split('\n').map(line => line.trim()).filter(Boolean);
    const result = [];

    for (const line of lines) {
      // 跳过纯元信息行（如 [offset:0]）
      if (/^\[[a-zA-Z]+:[^\]]*]$/.test(line)) continue;

      // 提取所有时间戳（支持一行多个）
      const timeMatches = [...line.matchAll(/\[(\d{1,3}):(\d{1,2})(?:\.(\d{1,3}))?]/g)];
      if (timeMatches.length === 0) continue;

      // 提取歌词内容（移除所有 [mm:ss.xx]）
      const content = line.replace(/\[\d{1,3}:\d{1,2}(?:\.\d{1,3})?]/g, '').trim();
      if (!content) continue;

      for (const match of timeMatches) {
        const [, min, sec, ms = '0'] = match;
        const time = (parseInt(min) || 0) * 60 + (parseInt(sec) || 0) + (parseInt(ms.padEnd(3, '0')) / 1000);
        if (!isNaN(time)) {
          result.push({ time, text: content });
        }
      }
    }

    return result.sort((a, b) => a.time - b.time);
  }

  async function loadLyric(songName) {
    let safeSongName = songName.trim().replace(/[<>:"/\\|?*]/g, '_');
    safeSongName = safeSongName.replace(/\.[^.]+$/, '');
    const filename = `${safeSongName}.lrc`;
    const url = `/media/lyric/${encodeURIComponent(filename)}`;

    try {
      const res = await fetch(url);
      if (!res.ok) return "[00:00.00]暂无歌词";

      let text = await res.text();
      // 仅移除 BOM
      if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);

      return text;
    } catch {
      return "[00:00.00]暂无歌词";
    }
  }

  // ======================
  // UI 更新（略）
  // ======================
  function updateProgressUI(currentTime, duration) {
    const percent = duration ? (currentTime / duration) * 100 : 0;
    dom.progressFill.style.width = `${percent}%`;
    dom.progressHandle.style.left = `${percent}%`;
    dom.currentTime.textContent = formatTime(currentTime);
    dom.remainingTime.textContent = formatTime(duration - currentTime);
    if (state.isPlaying || state.audio?.currentTime > 0) {
      renderLyrics(currentTime);
    }
  }

  function updateVolumeUI() {
    const vol = state.volume;
    dom.volumeSlider.value = vol;
    dom.volumeValue.textContent = Math.round(vol * 100) + "";
    dom.volumeSlider.style.setProperty('--progress', (vol * 100) + '%');
  }

  function updatePlayModeIcon() {
    const icons = {
      order: '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24"><path fill="#fff" d="M8 20v1.932a.5.5 0 0 1-.82.385l-4.12-3.433A.5.5 0 0 1 3.382 18H18a2 2 0 0 0 2-2V8h2v8a4 4 0 0 1-4 4zm8-16V2.068a.5.5 0 0 1 .82-.385l4.12 3.433a.5.5 0 0 1-.321.884H6a2 2 0 0 0-2 2v8H2V8a4 4 0 0 1 4-4z"/></svg>',
      shuffle: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 16 16"><path fill="#fff" d="M13 12h-2c-1 0-1.7-1.2-2.4-2.7c-.3.7-.6 1.5-1 2.3C8.4 13 9.4 14 11 14h2v2l3-3l-3-3zM5.4 6.6c.3-.7.6-1.5 1-2.2C5.6 3 4.5 2 3 2H0v2h3c1 0 1.7 1.2 2.4 2.6"/><path fill="#fff" d="m16 3l-3-3v2h-2C8.3 2 7.1 5 6 7.7C5.2 9.8 4.3 12 3 12H0v2h3c2.6 0 3.8-2.8 4.9-5.6C8.8 6.2 9.7 4 11 4h2v2z"/></svg>',
      single: '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24"><path fill="#fff" d="M8 20v1.933a.5.5 0 0 1-.82.384l-4.12-3.433A.5.5 0 0 1 3.382 18H18a2 2 0 0 0 2-2V8h2v8a4 4 0 0 1-4 4zm8-16V2.068a.5.5 0 0 1 .82-.385l4.12 3.433a.5.5 0 0 1-.321.884H6a2 2 0 0 0-2 2v8H2V8a4 4 0 0 1 4-4zm-5 4h2v8h-2v-6H9V9z"/></svg>'
    };
    dom.modeIcon.innerHTML = icons[state.mode];
    dom.modeBtn.title = {
      order: "顺序播放",
      shuffle: "随机播放",
      single: "单曲循环"
    }[state.mode];
  }

  function updateTrackInfo() {
    const track = musicTracks[state.currentTrackIndex];
    if (!track) return;
    dom.trackTitle.textContent = track.name || '未知歌曲';
    dom.artistName.textContent = track.artist || '未知艺术家';
  }

  function updatePlaylistHighlight() {
    modalBox.querySelectorAll('#playlistList li').forEach((li, i) => {
      li.classList.toggle('active', i === state.currentTrackIndex);
    });
  }

  // ======================
  // 核心逻辑
  // ======================
  function initAudio() {
    const track = musicTracks[state.currentTrackIndex];
    if (!track) return;
    updateTrackInfo();

    // 如果没有可播放的音频（空状态），不创建 Audio 对象
    if (!track.path) {
      if (state.audio) {
        state.audio.pause();
        URL.revokeObjectURL(state.audio.src);
        state.audio = null;
      }
      return;
    }

    if (state.audio) {
      state.audio.pause();
      URL.revokeObjectURL(state.audio.src);
      state.audio = null;
    }

    state.audio = new Audio(track.path);
    state.audio.volume = state.volume;

    // 仅当快照中的歌曲索引 == 当前要播放的索引时，才恢复时间
    let initialTime = 0;
    if (restoredState && restoredState.currentTrackIndex === state.currentTrackIndex) {
      initialTime = Math.min(restoredState.currentTime || 0, state.audio.duration || Infinity);
    }
    // 注意：此时 audio 还没 loadedmetadata，不能直接设 currentTime！
    state._restoreTime = initialTime;

    // 设置背景图
    const bgIndex = state.trackBackgrounds?.[state.currentTrackIndex];
    const playerContainer = modalBox.querySelector('.music-player-container');
    if (playerContainer) {
      if (bgIndex !== undefined && bgIndex >= 0 && backgroundImages[bgIndex]) {
        playerContainer.style.backgroundImage = `url(${backgroundImages[bgIndex]})`;
        playerContainer.style.backgroundSize = 'cover';
        playerContainer.style.backgroundPosition = 'center';
      } else {
        playerContainer.style.backgroundImage = '';
      }
    }

    addListener(state.audio, 'timeupdate', () => {
      if (state.audio && state.audio.duration) {
        updateProgressUI(state.audio.currentTime, state.audio.duration);
      }
    });

    // 注册 loadedmetadata 处理进度和自动播放
    addListener(state.audio, 'loadedmetadata', () => {
      if (!state.audio) return;
      // 恢复播放进度
      if (state._restoreTime > 0 && state._restoreTime <= state.audio.duration) {
        state.audio.currentTime = state._restoreTime;
      }
      updateProgressUI(state.audio.currentTime, state.audio.duration);

      // 如果需要自动播放
      if (restoredState?.isPlaying) {
        play();
      }
    }, { once: true });

    addListener(state.audio, 'ended', () => {
      if (!state.audio) return;
      if (state.mode === PLAY_MODE.SINGLE) {
        state.audio.currentTime = 0;
        play();
      } else {
        nextTrack();
      }
    });

    loadLyric(track.name).then(lrc => {
      state.lyricLines = parseLRC(lrc);
    });

    updatePlaylistHighlight();
  }

  function play() {
    if (!state.audio || !state.audio.src) return;
    state.audio.play().then(() => {
      state.isPlaying = true;
      dom.playPauseBtn.classList.add('playing');
    }).catch(e => console.error('播放失败:', e));
  }

  function pause() {
    if (state.audio) {
      state.audio.pause();
      state.isPlaying = false;
      dom.playPauseBtn.classList.remove('playing');
    }
  }

  function togglePlayPause() {
    if (!state.audio || !state.audio.src) return;
    if (state.isPlaying) {
      pause();
    } else {
      play();
    }
  }

  function nextTrack() {
    if (state.mode === PLAY_MODE.SHUFFLE) {
      state.currentTrackIndex = Math.floor(Math.random() * musicTracks.length);
    } else {
      state.currentTrackIndex = (state.currentTrackIndex + 1) % musicTracks.length;
    }
    initAudio();
    if (state.isPlaying && musicTracks[state.currentTrackIndex]?.path) play();
  }

  function prevTrack() {
    state.currentTrackIndex = (state.currentTrackIndex - 1 + musicTracks.length) % musicTracks.length;
    initAudio();
    if (state.isPlaying && musicTracks[state.currentTrackIndex]?.path) play();
  }

  function togglePlayMode() {
    const modes = Object.values(PLAY_MODE);
    const currentIndex = modes.indexOf(state.mode);
    state.mode = modes[(currentIndex + 1) % modes.length];
    updatePlayModeIcon();
  }

  function setAudioTimeFromPosition(clientX) {
    if (!state.audio || !state.audio.duration) return;
    const rect = dom.progressBar.getBoundingClientRect();
    let percent = (clientX - rect.left) / rect.width;
    percent = Math.max(0, Math.min(1, percent));
    const newTime = percent * state.audio.duration;
    state.audio.currentTime = newTime;
    updateProgressUI(newTime, state.audio.duration);
  }

  function renderLyrics(currentTime) {
    const lines = state.lyricLines;
    if (lines.length === 0) {
      dom.lyricDisplay.innerHTML = '<div class="lyric-line" data-offset="0">暂无歌词</div>';
      return;
    }

    let currentIndex = -1;
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].time <= currentTime) {
        currentIndex = i;
      } else {
        break;
      }
    }

    if (currentIndex === -1) {
      dom.lyricDisplay.innerHTML = '<div class="lyric-line" data-offset="0">...</div>';
      return;
    }

    const start = Math.max(0, currentIndex - 3);
    const end = Math.min(lines.length - 1, currentIndex + 3);

    let html = '';
    for (let i = start; i <= end; i++) {
      const offset = i - currentIndex;
      const text = lines[i].text || '...';
      html += `<div class="lyric-line" data-offset="${offset}">${text}</div>`;
    }

    dom.lyricDisplay.innerHTML = html;
  }

  // ======================
  // 事件绑定 + 清理记录
  // ======================
  let isDragging = false;
  const eventListeners = [];

  function addListener(target, event, handler, options) {
    if (!target) return;
    target.addEventListener(event, handler, options);
    eventListeners.push({ target, event, handler, options });
  }

  function bindEvents() {
  // 播放控制
  addListener(dom.playPauseBtn, 'click', togglePlayPause);
  addListener(dom.prevBtn, 'click', prevTrack);
  addListener(dom.nextBtn, 'click', nextTrack);
  addListener(dom.modeBtn, 'click', togglePlayMode);

  // 更换背景
  // 随机切换
  addListener(dom.changeBgBtn, 'click', () => {
    const newIndex = Math.floor(Math.random() * backgroundImages.length);
    state.trackBackgrounds[state.currentTrackIndex] = newIndex;
    const playerContainer = modalBox.querySelector('.music-player-container');
    if (playerContainer) {
      playerContainer.style.backgroundImage = `url(${backgroundImages[newIndex]})`;
    }
  });
  // 顺序切换
  // addListener(dom.changeBgBtn, 'click', () => {
  //   const total = backgroundImages.length;
  //   // 获取当前歌曲当前的背景索引
  //   let currentIndex = state.trackBackgrounds[state.currentTrackIndex];
  //   // 顺序切换：+1 循环
  //   const newIndex = (currentIndex + 1) % total;
  //   // 更新状态
  //   state.trackBackgrounds[state.currentTrackIndex] = newIndex;
  //   // 应用新背景
  //   const playerContainer = modalBox.querySelector('.music-player-container');
  //   if (playerContainer) {
  //     playerContainer.style.backgroundImage = `url(${backgroundImages[newIndex]})`;
  //   }
  // });

  // 音量面板开关
  addListener(dom.volumeToggleBtn, 'click', (e) => {
    e.stopPropagation();
    dom.volumeSliderContainer.classList.toggle('hidden');
  });

  // 点击外部关闭音量面板
  const clickOutsideHandler = (e) => {
    if (!modalBox.contains(e.target)) {
      dom.volumeSliderPanel?.classList?.add('hidden');
    }
  };
  addListener(document, 'click', clickOutsideHandler);

  // 音量滑块
  addListener(dom.volumeSlider, 'input', () => {
    state.volume = parseFloat(dom.volumeSlider.value);
    updateVolumeUI();
    if (state.audio) state.audio.volume = state.volume;
  });

  // 进度条点击跳转
  addListener(dom.progressBar, 'click', (e) => setAudioTimeFromPosition(e.clientX));

  // 鼠标拖拽进度
  const handleMouseDown = (e) => {
    isDragging = true;
    e.preventDefault();
  };
  addListener(dom.progressHandle, 'mousedown', handleMouseDown);

  const handleMouseMove = (e) => {
    if (isDragging) setAudioTimeFromPosition(e.clientX);
  };
  addListener(document, 'mousemove', handleMouseMove);

  const handleMouseUp = () => {
    isDragging = false;
  };
  addListener(document, 'mouseup', handleMouseUp);

  // 触摸拖拽进度（移动端）
  addListener(dom.progressBar, 'touchstart', (e) => {
    setAudioTimeFromPosition(e.touches[0].clientX);
    isDragging = true;
    e.preventDefault();
  }, { passive: false });

  addListener(dom.progressBar, 'touchmove', (e) => {
    if (isDragging) {
      setAudioTimeFromPosition(e.touches[0].clientX);
      e.preventDefault();
    }
  }, { passive: false });

  addListener(dom.progressBar, 'touchend', () => {
    isDragging = false;
  });

  // 歌单面板开关 & 动态生成列表
  addListener(dom.listBtn, 'click', () => {
    const isHidden = dom.playlistPanel.classList.contains('hidden');
    if (isHidden) {
      // 清空并重建列表（每次点击都重建，简单可靠）
      dom.playlistList.innerHTML = '';
      musicTracks.forEach((track, index) => {
        const li = document.createElement('li');
        li.textContent = `${track.artist} - ${track.name}`;
        // 空状态（path=null）的条目禁用点击
        if (!track.path) {
          li.style.opacity = '0.5';
          li.style.pointerEvents = 'none';
        }
        // 注意：这里不单独管理 <li> 的监听器，因为 cleanup 时会清空 innerHTML
        li.addEventListener('click', () => {
          state.currentTrackIndex = index;
          initAudio();
          if (state.isPlaying) play();
          dom.playlistPanel.classList.add('hidden');
        });
        dom.playlistList.appendChild(li);
      });
      updatePlaylistHighlight();
      dom.playlistPanel.classList.remove('hidden');
    } else {
      dom.playlistPanel.classList.add('hidden');
    }
  });

  // 关闭歌单
  addListener(dom.closeListBtn, 'click', () => {
    dom.playlistPanel.classList.add('hidden');
  });
}

  // ======================
  // 初始化
  // ======================
  loadBackgroundImages().then(() => {
    return loadMusicTracks();
  }).then(() => {
    initAudio();
    updateVolumeUI();
    updatePlayModeIcon();
    bindEvents();
  });

  let syncInterval = null;
  const SYNC_DELAY = 8000;
  const storageId = taskId;

  function syncStateToStorage() {
    if (!storageId) return;

    const snapshot = {
      currentTrackIndex: state.currentTrackIndex,
      isPlaying: state.isPlaying,
      volume: state.volume,
      mode: state.mode,
      currentTime: state.audio ? state.audio.currentTime : 0,
      trackBackgrounds: state.trackBackgrounds,
      id: storageId
    };

    try {
      localStorage.setItem(`__music_state_${storageId}`, JSON.stringify(snapshot));
    } catch (e) {
      console.warn('同步音乐状态失败', e);
    }
  }

  // 启动自动同步
  if (storageId) {
    syncInterval = setInterval(syncStateToStorage, SYNC_DELAY);
    syncStateToStorage(); // 立即同步一次
  }

  return {
  cleanup: function() {
    // 停止并销毁 audio
    if (state.audio) {
      state.audio.pause();
      state.audio.src = ''; // 撤销 novel 可触发资源释放
      state.audio = null;
    }

    // 清空 playlist（可选，但安全）
    if (dom.playlistList) {
      dom.playlistList.innerHTML = '';
    }

    // 移除所有事件监听器（统一！）
    eventListeners.forEach(({ target, event, handler, options }) => {
      target.removeEventListener(event, handler, options);
    });
    eventListeners.length = 0;

    // 清理定时器
    if (syncInterval) {
      clearInterval(syncInterval);
      syncInterval = null;
    }
    // 最后同步状态
    if (storageId) {
      syncStateToStorage();
    }

    console.log('音乐播放器已完全清理');
  },
  getState: function() {
    return {
      currentTrackIndex: state.currentTrackIndex,
      isPlaying: state.isPlaying,
      volume: state.volume,
      mode: state.mode,
      currentTime: state.audio ? state.audio.currentTime : 0,
      trackBackgrounds: state.trackBackgrounds,
    };
  }
};
}

function showUnsplashImage() {
  const taskId = `task-${Date.now()}`;
  let unsplashApi = null;
  const baseOptions = {
    url: `/static/components/unsplash-image.html`,
    title: '心海 · Unsplash图片平台',
    width: 1200,
    height: 650,
    minimizable: true,
    closable: true,
  };

  const modal = showModal({
    ...baseOptions,
    onMinimize: createMinimizableHandler(
      'Unsplash · 点击恢复',
      () => {
        document.body.appendChild(modal.overlay);
        modal.overlay.style.display = 'flex';
        modal.overlay.style.opacity = '1';
        modal.modalBox.style.opacity = '1';
        modal.modalBox.style.transform = 'scale(1)';
      },
      {
        id: taskId,
        modalOptions: baseOptions,
        message: "Unsplash · 点击恢复"
      }
    ),
    onLoad: (modalBox) => {
      // 🔥 关键：确保在 axios 加载完成后才初始化
      function initializeAfterAxios() {
        // 再次确认 DOM 子元素已存在（防极端 race condition）
        if (!modalBox.querySelector('[data-unsplash-init]')) {
          // 或者至少等一个 tick
          setTimeout(() => {
            unsplashApi = initUnsplashSearch(modalBox);
          }, 0);
        } else {
          unsplashApi = initUnsplashSearch(modalBox);
        }
      }

      if (typeof window.axios === 'function') {
        // axios 已存在，直接初始化
        initializeAfterAxios();
      } else {
        // 动态加载 axios
        const script = document.createElement('script');
        script.src = '/static/js/vendors/axios.min.js';
        script.onload = () => {
          console.log('axios loaded for Unsplash');
          initializeAfterAxios();
        };
        script.onerror = () => {
          window.showError('加载网络库失败，请检查网络或刷新页面', container);
        };
        // 👇 插入到 head（正确位置）
        document.head.appendChild(script);
      }
    },
    onUnload: () => {
      if (unsplashApi && typeof unsplashApi.cleanup === 'function') {
        unsplashApi.cleanup();
      }
      // 清理快照
      const state = unsplashApi.getState();
      localStorage.setItem('__unsplash_state__', JSON.stringify(state));
    }
  });
  modal.overlay.dataset.taskId = taskId;
}

/**
 * 初始化 Unsplash 搜索组件
 * @param {HTMLElement} container - 包裹整个搜索 UI 的容器
 * @param {Object|null} [restoredState=null] - 从缓存恢复的状态
 * @returns {{ cleanup: Function, getState: Function }}
 */
function initUnsplashSearch(container, restoredState = null) {
  // ======================
  // 内部状态 & 配置
  // ======================
  const CACHE_KEYS = {
    UNSPLASH_PHOTO_LIST: 'psytext_unsplash_photo_list',
    UNSPLASH_PHOTO_TOTAL: 'psytext_unsplash_photo_total',
    UNSPLASH_PHOTO_TOTAL_PAGES: 'psytext_unsplash_photo_total_pages',
  };

  const placeholders = {
    photos: '搜索照片，如：nature、city、mountains',
    collections: '搜索收藏，如：travel、architecture'
  };

  const state = {
    params: restoredState?.params || {
      query: '',
      page: 1,
      per_page: 12,
      order_by: 'relevant',
      orientation: 'landscape',
      content_filter: 'low',
      color: 'black_and_white',
      collections: ''
    },
    currentMode: restoredState?.currentMode || 'photos'
  };

  // DOM 引用
  const dom = {
    imageGrid: container.querySelector('#imageGrid'),
    emptyState: container.querySelector('#emptyState'),
    paginationControls: container.querySelector('#paginationControls'),
    mainSearchInput: container.querySelector('#mainSearchInput'),
    searchTrigger: container.querySelector('#searchTrigger'),
    toggleBtn: container.querySelector('#toggleAdvanced'),
    advancedCollapse: container.querySelector('#advancedCollapse'),
    searchTypeButtons: container.querySelectorAll('#searchTypeGroup .search-type-btn'),
    sortGroup: container.querySelector('#sortGroup'),
    orientationGroup: container.querySelector('#orientationGroup'),
    safeGroup: container.querySelector('#safeGroup'),
    colorGroup: container.querySelector('#colorGroup'),
    pageInput: container.querySelector('#pageInput'),
    perPageInput: container.querySelector('#perPageInput'),
    collectionsInput: container.querySelector('#collectionsInput'),
    currentPageDisplay: container.querySelector('#currentPageDisplay'),
    totalItemsDisplay: container.querySelector('#totalItemsDisplay'),
    totalPagesDisplay: container.querySelector('#totalPagesDisplay'),
    prevPageBtn: container.querySelector('#prevPageBtn'),
    nextPageBtn: container.querySelector('#nextPageBtn'),
    tryNatureBtn: container.querySelector('#tryNatureBtn')
  };

  // ======================
  // 工具函数
  // ======================
  function setCache(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
      console.warn('缓存写入失败', e);
    }
  }

  function getCache(key) {
    try {
      const val = localStorage.getItem(key);
      return val ? JSON.parse(val) : null;
    } catch (e) {
      console.warn('缓存读取失败', e);
      return null;
    }
  }

  function updateParams(key, value) {
    state.params[key] = value;
  }

  function truncateText(text, len) {
    if (!text) return '无描述';
    return text.length > len ? text.substring(0, len) + '...' : text;
  }

  // ======================
  // 渲染 & 请求（保留 axios）
  // ======================
  function renderImages(data) {
  const results = data?.results || [];
  const total = data?.total || 0;
  const totalPages = data?.total_pages || 0;

  if (!Array.isArray(results) || results.length === 0) {
    // 清空网格
    dom.imageGrid.innerHTML = '';
    dom.emptyState.classList.remove('hidden');
    dom.paginationControls.classList.add('hidden');
    return;
  }

  // 清空之前的内容
  dom.imageGrid.innerHTML = '';

  // 创建文档片段提升性能
  const fragment = document.createDocumentFragment();

  results.forEach(img => {
    // --- photo-card ---
    const card = document.createElement('div');
    card.className = 'photo-card';

    // --- photo-wrapper ---
    const wrapper = document.createElement('div');
    wrapper.className = 'photo-wrapper';

    // --- img ---
    const imgEl = document.createElement('img');
    imgEl.src = img.thumbnail_url || '';
    imgEl.dataset.fullUrl = img.url || img.thumbnail_url; // 存大图地址
    imgEl.alt = img.title || 'Image'; // .alt 是属性，自动转义
    imgEl.className = 'photo-img';
    imgEl.loading = 'lazy';
    imgEl.dataset.previewType = 'image';
    wrapper.appendChild(imgEl);

    // --- photo-overlay ---
    const overlay = document.createElement('div');
    overlay.className = 'photo-overlay';

    // --- 作者行 ---
    const authorRow = document.createElement('div');
    authorRow.className = 'info-row';

    const authorLabel = document.createElement('span');
    authorLabel.className = 'info-label';
    authorLabel.textContent = '作者:';

    const authorLink = document.createElement('a');
    const url = img.author_url;
    if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
      authorLink.href = url;
    } else {
      authorLink.href = '#';
    }
    authorLink.target = '_blank';
    authorLink.rel = 'noopener noreferrer';
    authorLink.className = 'info-link';
    authorLink.textContent = img.author_name || 'Unknown';

    authorRow.appendChild(authorLabel);
    authorRow.appendChild(authorLink);

    // --- 描述行 ---
    const descRow = document.createElement('div');
    descRow.className = 'info-row';

    const descLabel = document.createElement('span');
    descLabel.className = 'info-label';
    descLabel.textContent = '描述:';

    const descSpan = document.createElement('span');
    descSpan.className = 'info-desc';
    const descText = img.description || img.title || '无描述';
    descSpan.textContent = truncateText(descText, 50);

    descRow.appendChild(descLabel);
    descRow.appendChild(descSpan);

    // 组装 overlay
    overlay.appendChild(authorRow);
    overlay.appendChild(descRow);

    // 组装 card
    card.appendChild(wrapper);
    card.appendChild(overlay);

    // 加入片段
    fragment.appendChild(card);
  });

  // 一次性插入
  dom.imageGrid.appendChild(fragment);

  // 显示内容区，隐藏空状态
  dom.emptyState.classList.add('hidden');
  dom.paginationControls.classList.remove('hidden');

  // 更新分页信息
  dom.totalItemsDisplay.textContent = total;
  dom.totalPagesDisplay.textContent = totalPages;
  dom.currentPageDisplay.textContent = state.params.page;
  dom.prevPageBtn.disabled = state.params.page <= 1;
  dom.nextPageBtn.disabled = state.params.page >= totalPages;
}

  async function axiosUnsplash(endpoint, query = {}) {
    const url = `/api/unsplash${endpoint}`;
    try {
      const res = await axios.get(url, { params: query });
      return res.data;
    } catch (error) {
      if (error.response) {
        const detail = error.response.data?.detail || '服务器返回错误';
        throw new Error(detail);
      } else if (error.request) {
        throw new Error('无法连接服务器，请检查网络');
      } else {
        throw new Error('请求发送失败');
      }
    }
  }

  async function handleSearch(query, p) {
    const q = (query || '').trim();
    if (!q) {
      renderImages({ results: [], total: 0, total_pages: 0 });
      window.showStatus({ message: '请输入搜索关键词', type: 'warning', container });
      return;
    }

    try {
      const data = await axiosUnsplash('/search/photos', {
        query,
        page: p.page,
        per_page: p.per_page,
        order_by: p.order_by,
        orientation: p.orientation,
        content_filter: p.content_filter,
        color: p.color,
        collections: p.collections
      });
      renderImages(data);
      setCache(CACHE_KEYS.UNSPLASH_PHOTO_LIST, data.results);
      setCache(CACHE_KEYS.UNSPLASH_PHOTO_TOTAL, data.total);
      setCache(CACHE_KEYS.UNSPLASH_PHOTO_TOTAL_PAGES, data.total_pages);
    } catch (error) {
      window.showError(error.message, container);
    }
  }

  async function handleSearchCollections(query, p) {
    const q = (query || '').trim();
    if (!q) {
      renderImages({ results: [], total: 0, total_pages: 0 });
      window.showStatus({ message: '请输入搜索关键词', type: 'warning', container });
      return;
    }

    try {
      const data = await axiosUnsplash('/search/collections', {
        query,
        page: p.page,
        per_page: p.per_page
      });
      renderImages(data);
      setCache(CACHE_KEYS.UNSPLASH_PHOTO_LIST, data.results);
      setCache(CACHE_KEYS.UNSPLASH_PHOTO_TOTAL, data.total);
      setCache(CACHE_KEYS.UNSPLASH_PHOTO_TOTAL_PAGES, data.total_pages);
    } catch (error) {
      window.showError(error.message, container);
    }
  }

  // ======================
  // UI 控制（适配新结构）
  // ======================
  function updateVisibility() {
    container.querySelectorAll('.filter-row[data-visible-for]').forEach(row => {
      const modes = row.dataset.visibleFor.split(',');
      if (modes.includes(state.currentMode)) {
        row.classList.remove('hidden');
      } else {
        row.classList.add('hidden');
      }
    });
  }

  // ======================
  // 事件处理器
  // ======================
  async function onSearchTriggerClick() {
    const q = dom.mainSearchInput.value.trim();
    if (!q) {
      window.showStatus({ message: '请输入搜索关键词', type: 'warning', container });
      dom.mainSearchInput.focus();
      return;
    }
    updateParams('query', q);
    if (state.currentMode === 'photos') {
      await handleSearch(q, state.params);
    } else if (state.currentMode === 'collections') {
      await handleSearchCollections(q, state.params);
    }
  }

  function onSearchInputChange() {
    updateParams('query', this.value.trim());
  }

  function onToggleBtnClick() {
    const isOpen = dom.advancedCollapse.classList.contains('open');
    if (isOpen) {
      dom.advancedCollapse.classList.remove('open');
      dom.toggleBtn.textContent = '▼ 展开高级选项';
    } else {
      dom.advancedCollapse.classList.add('open');
      dom.toggleBtn.textContent = '▲ 收起高级选项';
    }
  }

  function onSearchTypeChange(e) {
    const btn = e.target.closest('.search-type-btn');
    if (!btn) return;

    dom.searchTypeButtons.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.currentMode = btn.dataset.type;
    dom.mainSearchInput.placeholder = placeholders[state.currentMode];
    updateVisibility();
  }

  function setupRadioGroups() {
    const groups = [
      { el: dom.sortGroup, paramKey: 'order_by' },
      { el: dom.orientationGroup, paramKey: 'orientation' },
      { el: dom.safeGroup, paramKey: 'content_filter' }
    ];

    groups.forEach(({ el, paramKey }) => {
      if (el) {
        el.addEventListener('click', (e) => {
          if (e.target.classList.contains('radio-btn')) {
            el.querySelectorAll('.radio-btn').forEach(btn => btn.classList.remove('active'));
            e.target.classList.add('active');
            updateParams(paramKey, e.target.dataset.value);
          }
        });
      }
    });
  }

  function onColorClick(e) {
    if (e.target.classList.contains('color-swatch')) {
      dom.colorGroup.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('active'));
      e.target.classList.add('active');
      updateParams('color', e.target.dataset.value);
    }
  }

  function onCollectionsInputChange() {
    const ids = this.value
      .split(',')
      .map(id => id.trim())
      .filter(id => id !== '')
      .join(',');
    updateParams('collections', ids);
  }

  async function onTryNatureClick() {
    dom.mainSearchInput.value = 'nature';
    updateParams('query', 'nature');
    await onSearchTriggerClick(); // 触发搜索
  }

  function bindStepper(input, paramName) {
    const stepper = input.closest('.page-stepper');
    const minusBtn = stepper.querySelector('.stepper-minus');
    const plusBtn = stepper.querySelector('.stepper-plus');

    const updateValue = (delta) => {
      let val = parseInt(input.value) || 0;
      const min = parseInt(input.min) || -Infinity;
      const max = input.max ? parseInt(input.max) : Infinity;
      val += delta;
      if (val >= min && val <= max) {
        input.value = val;
        updateParams(paramName, val);
      }
    };

    minusBtn.addEventListener('click', () => updateValue(-1));
    plusBtn.addEventListener('click', () => updateValue(+1));

    input.addEventListener('change', () => {
      let val = parseInt(input.value);
      if (isNaN(val)) val = parseInt(input.min) || 1;
      const min = parseInt(input.min) || -Infinity;
      const max = input.max ? parseInt(input.max) : Infinity;
      val = Math.min(Math.max(val, min), max);
      input.value = val;
      updateParams(paramName, val);
    });
  }

  function setupPagination() {
    dom.prevPageBtn.addEventListener('click', async () => {
      if (state.params.page > 1) {
        state.params.page--;
        dom.pageInput.value = state.params.page;
        await onSearchTriggerClick();
      }
    });

    dom.nextPageBtn.addEventListener('click', async () => {
      const totalPages = parseInt(dom.totalPagesDisplay.textContent) || 0;
      if (state.params.page < totalPages) {
        state.params.page++;
        dom.pageInput.value = state.params.page;
        await onSearchTriggerClick();
      }
    });
  }

  // ======================
  // 初始化
  // ======================
  function hydrateFromCache() {
    const list = getCache(CACHE_KEYS.UNSPLASH_PHOTO_LIST);
    const total = getCache(CACHE_KEYS.UNSPLASH_PHOTO_TOTAL);
    const totalPages = getCache(CACHE_KEYS.UNSPLASH_PHOTO_TOTAL_PAGES);
    if (list && Array.isArray(list)) {
      renderImages({
        results: list,
        total: typeof total === 'number' ? total : 0,
        total_pages: typeof totalPages === 'number' ? totalPages : 0
      });
    } else {
      // 手动设置 UI 状态，避免依赖 renderImages 内部逻辑
      dom.imageGrid.innerHTML = '';
      dom.emptyState.classList.remove('hidden'); // 显示空状态
      dom.paginationControls.classList.add('hidden'); // 隐藏分页
    }
  }

  // 绑定事件（收集用于 cleanup）
  const listeners = [];

  function addListener(el, event, handler, options) {
    if (el) {
      el.addEventListener(event, handler, options);
      listeners.push({ el, event, handler, options });
    }
  }

  addListener(dom.searchTrigger, 'click', onSearchTriggerClick);
  addListener(dom.mainSearchInput, 'input', onSearchInputChange);
  addListener(dom.toggleBtn, 'click', onToggleBtnClick);
  dom.searchTypeButtons.forEach(btn => addListener(btn, 'click', onSearchTypeChange));
  addListener(dom.colorGroup, 'click', onColorClick);
  addListener(dom.collectionsInput, 'input', onCollectionsInputChange);
  addListener(dom.tryNatureBtn, 'click', onTryNatureClick);

  setupRadioGroups();
  bindStepper(dom.pageInput, 'page');
  bindStepper(dom.perPageInput, 'per_page');
  setupPagination();

  dom.mainSearchInput.placeholder = placeholders[state.currentMode];
  updateVisibility();
  hydrateFromCache();

  // ======================
  // 大图预览功能（Lightbox）
  // ======================
  let previewOverlay = null;
  let previewImg = null;
  let previewCloseBtn = null;

  function createPreviewOverlay() {
    if (previewOverlay) return; // 防重复创建
    // 👇 关键：找到 showModal 创建的 .modal-overlay
    const overlay = container.closest('.modal-overlay');
    if (!overlay) {
      console.error('Could not find modal overlay for preview');
      return;
    }

    previewOverlay = document.createElement('div');
    previewOverlay.className = 'unsplash-preview-overlay';
    previewOverlay.innerHTML = `
      <div class="unsplash-preview-wrapper">
        <img class="unsplash-preview-img" src="" alt="Preview">
        <button class="unsplash-preview-close">×</button>
      </div>
    `;
    overlay.appendChild(previewOverlay);

    previewImg = previewOverlay.querySelector('.unsplash-preview-img');
    previewCloseBtn = previewOverlay.querySelector('.unsplash-preview-close');

    // 关闭逻辑
    const closePreview = () => {
      if (previewOverlay) {
        previewOverlay.style.display = 'none';
        if (previewImg) {
          previewImg.src = ''; // 👈 清空 novel，释放资源
        }
      }
    };

    previewOverlay.addEventListener('click', (e) => {
      if (e.target === previewOverlay) closePreview();
    });

    previewCloseBtn.addEventListener('click', closePreview);

    // ESC 关闭
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && previewOverlay.style.display !== 'none') {
        closePreview();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    listeners.push({ el: document, event: 'keydown', handler: handleKeyDown });

    // 添加样式（如果尚未注入）
    if (!document.getElementById('unsplash-preview-styles')) {
      const style = document.createElement('style');
      style.id = 'unsplash-preview-styles';
      style.textContent = `
        .unsplash-preview-overlay {
          position: fixed;
          top: 0;
          left: 0;
          width: 100vw;
          height: 100vh;
          background: rgba(0, 0, 0, 0.92);
          display: none;
          justify-content: center;
          align-items: center;
          z-index: 30000;
          cursor: pointer;
        }
        .unsplash-preview-wrapper {
          position: relative;
          max-width: 95vw;
          max-height: 95vh;
          display: flex;
          justify-content: center;
          align-items: center;
        }
        .unsplash-preview-img {
          /* 优先保持原始比例 */
          width: auto;
          height: auto;
          max-width: min(90vw, 800px);
          max-height: min(90vh, 600px);
          /* 强制 4:3 比例（可选，若你希望统一） */
          /* aspect-ratio: 4 / 3; */
          object-fit: contain;
          border-radius: 8px;
          box-shadow: 0 0 25px rgba(0,0,0,0.7);
          pointer-events: none;
        }
        .unsplash-preview-close {
          position: absolute;
          top: -30px;
          right: -30px;
          background: rgba(0,0,0,0.6);
          color: white;
          border: none;
          width: 36px;
          height: 36px;
          border-radius: 50%;
          font-size: 24px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          pointer-events: auto;
          z-index: 10;
        }
        .unsplash-preview-close:hover {
          background: rgba(255,255,255,0.2);
        }
      `;
      document.head.appendChild(style);
    }
  }

  // 绑定图片点击事件（委托到 imageGrid）
  function bindImageClick() {
    const handleClick = (e) => {
      const img = e.target.closest('.photo-img');
      if (!img) return;

      const fullUrl = img.dataset.fullUrl;
      if (!fullUrl) return;

      if (!previewOverlay) createPreviewOverlay();

      previewImg.src = fullUrl;
      previewImg.alt = img.alt || 'Preview';
      previewOverlay.style.display = 'flex';
    };

    dom.imageGrid.addEventListener('click', handleClick);
    listeners.push({ el: dom.imageGrid, event: 'click', handler: handleClick });
  }

  // 初始化预览系统
  createPreviewOverlay(); // 可延迟创建，但提前建好更稳妥
  bindImageClick();

  // ======================
  // 返回接口
  // ======================
  return {
    cleanup: function () {
      listeners.forEach(({ el, event, handler, options }) => {
        el.removeEventListener(event, handler, options);
      });
      // 可选：移除预览 DOM
      if (previewOverlay && previewOverlay.parentNode) {
        previewOverlay.remove();
      }
      // 移除样式（可选）
      // const style = document.getElementById('unsplash-preview-styles');
      // if (style) style.remove();
      if (previewImg) {
        previewImg.src = '';
      }
    },
    getState: function () {
      return {
        params: { ...state.params },
        currentMode: state.currentMode
      };
    }
  };
}

function showPexelesImage() {
  const taskId = `task-${Date.now()}`;
  let pexelesApi = null;
  const baseOptions = {
    url: `/static/components/pexels-image.html`,
    title: '心海 · Pexels图片平台',
    width: 1200,
    height: 650,
    minimizable: true,
    closable: true,
  };

  const modal = showModal({
    ...baseOptions,
    onMinimize: createMinimizableHandler(
      'Pexels · 点击恢复',
      () => {
        document.body.appendChild(modal.overlay);
        modal.overlay.style.display = 'flex';
        modal.overlay.style.opacity = '1';
        modal.modalBox.style.opacity = '1';
        modal.modalBox.style.transform = 'scale(1)';
      },
      {
        id: taskId,
        modalOptions: baseOptions,
        message: "Pexels · 点击恢复"
      }
    ),
    onLoad: (modalBox) => {
      // 🔥 关键：确保在 axios 加载完成后才初始化
      function initializeAfterAxios() {
        // 再次确认 DOM 子元素已存在（防极端 race condition）
        if (!modalBox.querySelector('[data-pexeles-init]')) {
          // 或者至少等一个 tick
          setTimeout(() => {
            pexelesApi = initPexelsSearch(modalBox);
          }, 0);
        } else {
          pexelesApi = initPexelsSearch(modalBox);
        }
      }

      if (typeof window.axios === 'function') {
        // axios 已存在，直接初始化
        initializeAfterAxios();
      } else {
        // 动态加载 axios
        const script = document.createElement('script');
        script.src = '/static/js/vendors/axios.min.js';
        script.onload = () => {
          console.log('axios loaded for Pexels');
          initializeAfterAxios();
        };
        script.onerror = () => {
          window.showError('加载网络库失败，请检查网络或刷新页面', container);
        };
        // 👇 插入到 head（正确位置）
        document.head.appendChild(script);
      }
    },
    onUnload: () => {
      if (pexelesApi && typeof pexelesApi.cleanup === 'function') {
        pexelesApi.cleanup();
      }
      // 清理快照
      const state = pexelesApi.getState();
      localStorage.setItem('__pexels_state__', JSON.stringify(state));
    }
  });
  modal.overlay.dataset.taskId = taskId;
}

/**
 * 初始化 Pexeles 搜索组件
 * @param {HTMLElement} container - 包裹整个搜索 UI 的容器
 * @param {Object|null} [restoredState=null] - 从缓存恢复的状态
 * @returns {{ cleanup: Function, getState: Function }}
 */
function initPexelsSearch(container, restoredState = null) {
  // ======================
  // 缓存键
  // ======================
  const CACHE_KEYS = {
    PHOTO_LIST: "psytext_pexels_photo_list",
    PHOTO_TOTAL: "psytext_pexels_photo_total",
    PHOTO_TOTAL_PAGES: "psytext_pexels_photo_total_pages",
    VIDEO_LIST: "psytext_pexels_video_list",
    VIDEO_TOTAL: "psytext_pexels_video_total",
    VIDEO_TOTAL_PAGES: "psytext_pexels_video_total_pages"
  };

  // ======================
  // 内部状态
  // ======================
  const placeholders = {
    photos: '搜索照片，如：nature、city、mountains',
    videos: '搜索视频，如：travel、architecture'
  };

  const state = {
    params: restoredState?.params || {
      query: '',
      page: 1,
      per_page: 12,
      size: 'small',
      color: 'black',
      orientation: 'landscape',
      locale: 'zh-CN'
    },
    currentMode: restoredState?.currentMode || 'photos' // 'photos' | 'videos'
  };

  // ======================
  // DOM 引用
  // ======================
  const dom = {
    mainContent: container.querySelector('.main-content'),
    imageGrid: document.getElementById('imageGrid'),
    emptyState: container.querySelector('.empty-state'),
    paginationControls: container.querySelector('.pagination-controls'),
    searchInput: container.querySelector('.main-search-input'),
    searchIcon: container.querySelector('.search-icon'),
    toggleBtn: container.querySelector('#toggleAdvanced'),
    advancedCollapse: container.querySelector('#advancedCollapse'),
    searchTypeButtons: container.querySelectorAll('.search-type-btn'),
    pageInput: container.querySelector('#pageInput'),
    perPageInput: container.querySelector('#perPageInput'),
    tryNatureBtn: container.querySelector('#tryNatureBtn'),
    totalItemsDisplay: container.querySelector('#totalItemsDisplay'),
    totalPagesDisplay: container.querySelector('#totalPagesDisplay'),
    currentPageDisplay: container.querySelector('#currentPageDisplay'),
    prevPageBtn: container.querySelector('#prevPageBtn'),
    nextPageBtn: container.querySelector('#nextPageBtn')
  };

  // ======================
  // 工具函数
  // ======================
  function setCache(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
      console.warn('缓存写入失败', e);
    }
  }

  function getCache(key) {
    try {
      const val = localStorage.getItem(key);
      return val ? JSON.parse(val) : null;
    } catch (e) {
      console.warn('缓存读取失败', e);
      return null;
    }
  }

  function updateParams(key, value) {
    state.params[key] = value;
  }

  function truncateText(text, len) {
    if (!text) return '无描述';
    return text.length > len ? text.substring(0, len) + '...' : text;
  }

  // ======================
  // API 请求
  // ======================
  async function requestPexelsAPI(endpoint, params) {
    try {
      const res = await axios.get(`/api/pexels/search${endpoint}`, { params });
      return res.data;
    } catch (error) {
      if (error.response) {
        throw new Error(error.response.data?.message || 'API 返回错误');
      } else if (error.request) {
        throw new Error('网络连接失败，请检查网络');
      } else {
        throw new Error('请求配置异常');
      }
    }
  }

  // ======================
  // 渲染函数
  // ======================
  function renderPhotos(data) {
  const results = data?.results || [];
  const total = data?.total || 0;
  const totalPages = data?.total_pages || 0;

  if (!Array.isArray(results) || results.length === 0) {
    clearGrid();
    showEmptyState('photos');
    return;
  }

  clearGrid();
  const fragment = document.createDocumentFragment();

  results.forEach(item => {
    // --- photo-card ---
    const card = document.createElement('div');
    card.className = 'photo-card';

    // --- photo-wrapper ---
    const wrapper = document.createElement('div');
    wrapper.className = 'photo-wrapper';

    const imgEl = document.createElement('img');
    imgEl.src = item.thumbnail_url || '';
    imgEl.dataset.fullUrl = item.url || item.thumbnail_url;
    imgEl.alt = item.description || item.title || 'Image';
    imgEl.className = 'photo-img';
    imgEl.loading = 'lazy';
    imgEl.dataset.previewType = 'image';
    wrapper.appendChild(imgEl);

    // --- photo-overlay ---
    const overlay = document.createElement('div');
    overlay.className = 'photo-overlay';

    // --- 作者行 ---
    const authorRow = document.createElement('div');
    authorRow.className = 'info-row';

    const authorLabel = document.createElement('span');
    authorLabel.className = 'info-label';
    authorLabel.textContent = '作者:';

    const authorLink = document.createElement('a');
    authorLink.href = (item.author_url || '').startsWith('http') ? item.author_url : '#';
    authorLink.target = '_blank';
    authorLink.rel = 'noopener noreferrer';
    authorLink.className = 'info-link';
    authorLink.textContent = item.author_name || 'Unknown';

    authorRow.appendChild(authorLabel);
    authorRow.appendChild(authorLink);

    // --- 描述行 ---
    const descRow = document.createElement('div');
    descRow.className = 'info-row';

    const descLabel = document.createElement('span');
    descLabel.className = 'info-label';
    descLabel.textContent = '描述:';

    const descSpan = document.createElement('span'); // 👈 不是 <a>！和 Unsplash 一致
    descSpan.className = 'info-desc';
    const descText = item.description || item.title || '无描述';
    descSpan.textContent = truncateText(descText, 50);

    descRow.appendChild(descLabel);
    descRow.appendChild(descSpan);

    overlay.appendChild(authorRow);
    overlay.appendChild(descRow);

    card.appendChild(wrapper);
    card.appendChild(overlay);
    fragment.appendChild(card);
  });

  dom.imageGrid.appendChild(fragment); // 👈 注意：和 Unsplash 一样 append 到 imageGrid

  dom.emptyState.classList.add('hidden');
  dom.paginationControls.classList.remove('hidden');

  // 更新分页（假设你有这些 DOM 引用）
  dom.totalItemsDisplay.textContent = total;
  dom.totalPagesDisplay.textContent = totalPages;
  dom.currentPageDisplay.textContent = state.params.page;
  dom.prevPageBtn.disabled = state.params.page <= 1;
  dom.nextPageBtn.disabled = state.params.page >= totalPages;
}

  function renderVideos(data) {
  const results = data?.results || [];
  if (results.length === 0) {
    clearGrid();
    showEmptyState('videos');
    return;
  }

  hideEmptyState();
  clearGrid();

  const fragment = document.createDocumentFragment();

  results.forEach(item => {
    const card = document.createElement('div');
    card.className = 'photo-card'; // 和图片一致

    const wrapper = document.createElement('div');
    wrapper.className = 'photo-wrapper';

    const video = document.createElement('video');
    video.src = item.thumbnail_url || '';
    video.dataset.fullUrl = item.url || item.thumbnail_url;
    video.muted = true;
    video.loop = true;
    video.playsInline = true;
    video.preload = 'metadata';
    video.className = 'photo-video';
    video.dataset.previewType = 'video';

    video.play().catch(() => {});
    video.addEventListener('mouseenter', () => video.pause());
    video.addEventListener('mouseleave', () => video.play().catch(() => {}));

    wrapper.appendChild(video);

    const authorOverlay = document.createElement('div');
    authorOverlay.className = 'video-author-overlay';
    const authorLink = document.createElement('a');
    authorLink.href = (item.author_url || '').startsWith('http') ? item.author_url : '#';
    authorLink.target = '_blank';
    authorLink.rel = 'noopener noreferrer';
    authorLink.textContent = item.author_name || 'Unknown';
    authorOverlay.appendChild(authorLink);
    wrapper.appendChild(authorOverlay);

    card.appendChild(wrapper);
    fragment.appendChild(card);
  });

  dom.imageGrid.appendChild(fragment);

  dom.paginationControls.classList.remove('hidden');
  updatePaginationUI(data);
}

  function clearGrid() {
    dom.imageGrid.innerHTML = '';
  }

  function hideEmptyState() {
    if (dom.emptyState) dom.emptyState.classList.add('hidden');
  }

  function showEmptyState(mode) {
    if (dom.emptyState) {
      // 直接选 h3 和按钮，不依赖 el-empty 类
      const h3 = dom.emptyState.querySelector('h3');
      const btn = dom.emptyState.querySelector('#tryNatureBtn');

      if (h3) {
        h3.textContent = mode === 'photos' ? '暂无图片数据' : '暂无视频数据';
      }
      if (btn) {
        btn.textContent = `试试「${mode === 'photos' ? 'nature' : 'travel'}」`;
      }

      dom.emptyState.classList.remove('hidden');
    }
    if (dom.paginationControls) dom.paginationControls.classList.add('hidden');
  }

  function updatePaginationUI(data) {
    if (dom.totalItemsDisplay) dom.totalItemsDisplay.textContent = data.total || 0;
    if (dom.totalPagesDisplay) dom.totalPagesDisplay.textContent = data.total_pages || 0;
    if (dom.currentPageDisplay) dom.currentPageDisplay.textContent = state.params.page;
    if (dom.paginationControls) dom.paginationControls.classList.remove('hidden');

    // 更新分页按钮禁用状态
    if (dom.prevPageBtn) dom.prevPageBtn.disabled = state.params.page <= 1;
    if (dom.nextPageBtn) {
      const totalPages = data.total_pages || 0;
      dom.nextPageBtn.disabled = state.params.page >= totalPages;
    }
  }

  // ======================
  // 搜索逻辑
  // ======================
  async function searchPhotos(query, p) {
    const data = await requestPexelsAPI('/photos', {
      query: query.trim(),
      page: p.page,
      per_page: p.per_page,
      size: p.size,
      color: p.color,
      orientation: p.orientation,
      locale: p.locale
    });

    setCache(CACHE_KEYS.PHOTO_LIST, data.results);
    setCache(CACHE_KEYS.PHOTO_TOTAL, data.total);
    setCache(CACHE_KEYS.PHOTO_TOTAL_PAGES, data.total_pages);

    renderPhotos(data);
    if (dom.pageInput) dom.pageInput.value = p.page;
    if (dom.perPageInput) dom.perPageInput.value = p.per_page;
  }

  async function searchVideos(query, p) {
    const data = await requestPexelsAPI('/videos', {
      query: query.trim(),
      page: p.page,
      per_page: p.per_page,
      locale: p.locale,
      size: p.size,
      orientation: p.orientation,
    });

    setCache(CACHE_KEYS.VIDEO_LIST, data.results);
    setCache(CACHE_KEYS.VIDEO_TOTAL, data.total);
    setCache(CACHE_KEYS.VIDEO_TOTAL_PAGES, data.total_pages);

    renderVideos(data);
    if (dom.pageInput) dom.pageInput.value = p.page;
    if (dom.perPageInput) dom.perPageInput.value = p.per_page;
  }

  // ======================
  // UI 控制
  // ======================
  function updateVisibility() {
    container.querySelectorAll('.filter-row[data-visible-for]').forEach(row => {
      const modes = row.dataset.visibleFor.split(',');
      if (modes.includes(state.currentMode)) {
        row.classList.remove('hidden');
      } else {
        row.classList.add('hidden');
      }
    });
  }

  // ======================
  // 事件处理器
  // ======================
  async function onSearchTrigger() {
    const q = dom.searchInput?.value.trim();
    if (!q) {
      window.showStatus({ message: '请输入搜索关键词', type: 'warning', container });
      return;
    }
    updateParams('query', q);
    try {
      if (state.currentMode === 'photos') {
        await searchPhotos(q, state.params);
      } else {
        await searchVideos(q, state.params);
      }
    } catch (err) {
      console.error('搜索失败:', err);
      window.showError(err.message, container);
      showEmptyState(state.currentMode);
    }
  }

  function onSearchTypeChange(e) {
  const btn = e.target.closest('.search-type-btn');
  if (!btn) return;

  // 更新激活状态
  dom.searchTypeButtons.forEach(b => b.classList.remove('active'));
  btn.classList.add('active');

  const newMode = btn.dataset.type; // 'photos' 或 'videos'

  // 如果模式没变，不重复处理
  if (state.currentMode === newMode) return;

  // 更新状态
  state.currentMode = newMode;
  state.params.page = 1; // 切换类型时重置页码（符合用户预期）

  // 更新输入框 placeholder
  dom.searchInput.placeholder = placeholders[state.currentMode];

  // 更新高级选项可见性
  updateVisibility();

  // 👇 关键：立即加载并渲染当前模式的数据（优先缓存，无则空状态）
  hydrateFromCacheForMode(state.currentMode);
}

  async function onTryNatureClick() {
    const keyword = state.currentMode === 'photos' ? 'nature' : 'travel';
    dom.searchInput.value = keyword;
    updateParams('query', keyword);
    await onSearchTrigger();
  }

  function onToggleAdvanced() {
    const isOpen = dom.advancedCollapse?.classList.contains('open');
    if (isOpen) {
      dom.advancedCollapse?.classList.remove('open');
      if (dom.toggleBtn) dom.toggleBtn.textContent = '▼ 展开高级选项';
    } else {
      dom.advancedCollapse?.classList.add('open');
      if (dom.toggleBtn) dom.toggleBtn.textContent = '▲ 收起高级选项';
    }
  }

  function bindStepper(input, paramName) {
    if (!input) return;
    const stepper = input.closest('.page-stepper');
    const minus = stepper?.querySelector('.stepper-minus');
    const plus = stepper?.querySelector('.stepper-plus');

    const update = (delta) => {
      let val = parseInt(input.value) || 0;
      const min = parseInt(input.min) || -Infinity;
      const max = input.max ? parseInt(input.max) : Infinity;
      val += delta;
      if (val >= min && val <= max) {
        input.value = val;
        updateParams(paramName, val);
      }
    };

    if (minus) minus.addEventListener('click', () => update(-1));
    if (plus) plus.addEventListener('click', () => update(1));

    input.addEventListener('change', () => {
      let val = parseInt(input.value);
      if (isNaN(val)) val = parseInt(input.min) || 1;
      const min = parseInt(input.min) || -Infinity;
      const max = input.max ? parseInt(input.max) : Infinity;
      val = Math.min(Math.max(val, min), max);
      input.value = val;
      updateParams(paramName, val);
    });
  }

  function setupRadioGroups() {
    // 照片参数
    const photoGroups = [
      { el: container.querySelector('[data-param="size"]'), param: 'size' },
      { el: container.querySelector('[data-param="color"]'), param: 'color' },
      { el: container.querySelector('[data-param="orientation"]'), param: 'orientation' }
    ];

    // 地区参数（通用）
    const localeGroup = container.querySelector('[data-param="locale"]');

    // 绑定照片/视频共用的 radio/color/locale
    [...photoGroups, { el: localeGroup, param: 'locale' }].forEach(({ el, param }) => {
      if (el) {
        el.addEventListener('click', (e) => {
          if (e.target.dataset.value !== undefined) {
            el.querySelectorAll('[data-value]').forEach(btn => btn.classList.remove('active'));
            e.target.classList.add('active');
            updateParams(param, e.target.dataset.value);
          }
        });
      }
    });
  }

  function setupPagination() {
    if (dom.prevPageBtn) {
      dom.prevPageBtn.addEventListener('click', async () => {
        if (state.params.page > 1) {
          state.params.page--;
          dom.pageInput.value = state.params.page;
          await onSearchTrigger();
        }
      });
    }

    if (dom.nextPageBtn) {
      dom.nextPageBtn.addEventListener('click', async () => {
        const totalPages = parseInt(dom.totalPagesDisplay?.textContent) || 0;
        if (state.params.page < totalPages) {
          state.params.page++;
          dom.pageInput.value = state.params.page;
          await onSearchTrigger();
        }
      });
    }
  }

  // =====================
  // 缓存恢复
  // =====================
  function hydrateFromCacheForMode(mode) {
  const isPhoto = mode === 'photos';
  const listKey = isPhoto ? CACHE_KEYS.PHOTO_LIST : CACHE_KEYS.VIDEO_LIST;
  const totalKey = isPhoto ? CACHE_KEYS.PHOTO_TOTAL : CACHE_KEYS.VIDEO_TOTAL;
  const totalPagesKey = isPhoto ? CACHE_KEYS.PHOTO_TOTAL_PAGES : CACHE_KEYS.VIDEO_TOTAL_PAGES;

  const list = getCache(listKey);
  const total = getCache(totalKey);
  const totalPages = getCache(totalPagesKey);

  if (Array.isArray(list) && list.length > 0) {
    const data = { results: list, total: total || 0, total_pages: totalPages || 0 };
    if (isPhoto) {
      renderPhotos(data);
    } else {
      renderVideos(data);
    }
    // 同步页码和每页数量（从缓存恢复的状态）
    if (dom.pageInput) dom.pageInput.value = state.params.page;
    if (dom.perPageInput) dom.perPageInput.value = state.params.per_page;
  } else {
    // 没有缓存 → 显示空状态
    clearGrid();
    showEmptyState(mode);
  }
}

  // ======================
  // 事件绑定
  // ======================
  const listeners = [];

  function addListener(el, event, handler) {
    if (el) {
      el.addEventListener(event, handler);
      listeners.push({ el, event, handler });
    }
  }

  addListener(dom.searchIcon, 'click', onSearchTrigger);
  addListener(dom.searchInput, 'keypress', (e) => { if (e.key === 'Enter') onSearchTrigger(); });
  dom.searchTypeButtons.forEach(btn => addListener(btn, 'click', onSearchTypeChange));
  addListener(dom.toggleBtn, 'click', onToggleAdvanced);
  addListener(dom.tryNatureBtn, 'click', onTryNatureClick);

  bindStepper(dom.pageInput, 'page');
  bindStepper(dom.perPageInput, 'per_page');
  setupRadioGroups();
  setupPagination();

  // 初始化 UI
  if (dom.searchInput) dom.searchInput.placeholder = placeholders[state.currentMode];
  updateVisibility();
  hydrateFromCacheForMode(state.currentMode);

  // ======================
  // Pexels 大图/大视频预览系统
  // ======================
  let previewOverlay = null;
  let previewContainer = null;
  let previewCloseBtn = null;

  function createPreviewOverlay() {
    if (previewOverlay) return;
    // 🔑 关键：找到 showModal 创建的 .modal-overlay
    const modalOverlay = container.closest('.modal-overlay');
    if (!modalOverlay) {
      console.error('Pexels preview: .modal-overlay not found!');
      return;
    }

    previewOverlay = document.createElement('div');
    previewOverlay.className = 'pexels-preview-overlay';
    previewOverlay.innerHTML = `
      <div class="pexels-preview-wrapper">
        <div class="pexels-preview-media-container"></div>
        <button class="pexels-preview-close">×</button>
      </div>
    `;
    modalOverlay.appendChild(previewOverlay);

    previewContainer = previewOverlay.querySelector('.pexels-preview-media-container');
    previewCloseBtn = previewOverlay.querySelector('.pexels-preview-close');

    const closePreview = () => {
      if (previewOverlay.style.display !== 'none') {
        previewOverlay.style.display = 'none';
        // 销毁所有视频
        const videos = previewContainer.querySelectorAll('video');
        videos.forEach(v => {
          v.pause();
          v.src = ''; // 断开资源
          v.load();   // 触发释放
        });
        // 清理媒体资源（防内存泄漏）
        previewContainer.innerHTML = '';
      }
    };

    previewOverlay.addEventListener('click', (e) => {
      if (e.target === previewOverlay) closePreview();
    });

    previewCloseBtn.addEventListener('click', closePreview);

    // ESC 关闭
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && previewOverlay.style.display !== 'none') {
        closePreview();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    listeners.push({ el: document, event: 'keydown', handler: handleKeyDown });

    // 注入样式（仅一次）
    if (!document.getElementById('pexels-preview-styles')) {
      const style = document.createElement('style');
      style.id = 'pexels-preview-styles';
      style.textContent = `
        .pexels-preview-overlay {
          position: fixed;
          top: 0;
          left: 0;
          width: 100vw;
          height: 100vh;
          background: rgba(0, 0, 0, 0.93);
          display: none;
          justify-content: center;
          align-items: center;
          z-index: 30000;
          cursor: pointer;
        }
        .pexels-preview-wrapper {
          position: relative;
          max-width: 95vw;
          max-height: 95vh;
          display: flex;
          justify-content: center;
          align-items: center;
        }
        .pexels-preview-media-container > img,
        .pexels-preview-media-container > video {
          /* 优先保持原始比例 */
          width: auto;
          height: auto;
          max-width: min(90vw, 800px);
          max-height: min(90vh, 600px);
          /* 强制 4:3 比例（可选，若你希望统一） */
          /* aspect-ratio: 4 / 3; */
          object-fit: contain;
          /* 防止视频控件撑大容器 */
          display: block;
          margin: 0 auto; /* 居中 */
          border-radius: 8px;
          box-shadow: 0 0 25px rgba(0,0,0,0.7);
          pointer-events: auto;
        }
        .pexels-preview-close {
          position: absolute;
          top: -30px;
          right: -30px;
          background: rgba(0,0,0,0.6);
          color: white;
          border: none;
          width: 36px;
          height: 36px;
          border-radius: 50%;
          font-size: 24px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          pointer-events: auto;
          z-index: 10;
        }
        .pexels-preview-close:hover {
          background: rgba(255,255,255,0.2);
        }
        /* 视频控制条可选 */
        .pexels-preview-media-container > video {
          outline: none;
        }
      `;
      document.head.appendChild(style);
    }
  }

  function bindMediaClick() {
    const handleClick = (e) => {
      // 支持点击 .photo-img（图片）或 .photo-video（视频）
      const target = e.target.closest('.photo-img, .photo-video');
      if (!target) return;

      const fullUrl = target.dataset.fullUrl;
      const type = target.dataset.previewType; // 必须有！

      if (!fullUrl || !type) {
        console.warn('Missing fullUrl or previewType', target);
        return;
      }

      if (!previewOverlay) createPreviewOverlay();

      previewContainer.innerHTML = ''; // 清空上次内容

      if (type === 'image') {
        const img = document.createElement('img');
        img.src = fullUrl;
        img.alt = 'Preview';
        previewContainer.appendChild(img);
      } else if (type === 'video') {
        const video = document.createElement('video');
        video.src = fullUrl;
        video.controls = true; // 显示播放控件
        video.autoplay = true;
        video.muted = false; // 允许声音（用户已主动点击）
        video.playsInline = true;
        video.preload = 'metadata';
        video.style.objectFit = 'contain';

        // 自动播放处理
        video.play().catch(() => {
          // 如果 autoplay 被阻止，至少显示控件让用户手动播放
        });

        previewContainer.appendChild(video);
      }

      previewOverlay.style.display = 'flex';
    };

    dom.imageGrid.addEventListener('click', handleClick);
    listeners.push({ el: dom.imageGrid, event: 'click', handler: handleClick });
  }

  // 初始化预览系统
  createPreviewOverlay(); // 可延迟，但提前建好更稳妥
  bindMediaClick();

  // ======================
  // 返回接口
  // ======================
  return {
    cleanup() {
      listeners.forEach(({ el, event, handler }) => {
        el.removeEventListener(event, handler);
      });
      // 清理预览 DOM
      if (previewOverlay?.parentNode) {
        previewOverlay.remove();
      }
      // 清理样式（可选）
      //const style = document.getElementById('pexels-preview-styles');
      //if (style) style.remove();
      if (previewContainer) {
        const videos = previewContainer.querySelectorAll('video');
        videos.forEach(v => {
          v.pause();
          v.src = '';
          v.load();
        });
      }
    },
    getState() {
      return {
        params: { ...state.params },
        currentMode: state.currentMode
      };
    }
  };
}

function showDeviceAuth() {
  const taskId = `task-device-auth-${Date.now()}`;
  const modalOptions = {
    url: '/static/components/device-auth.html',
    title: '设备授权',
    width: 640,
    height: 560,
    minimizable: true
  };

  const modal = showModal({
    ...modalOptions,
    onMinimize: createMinimizableHandler(
      '设备授权 · 点击恢复',
      () => {
        document.body.appendChild(modal.overlay);
        modal.overlay.style.display = 'flex';
        modal.overlay.style.opacity = '1';
        modal.modalBox.style.opacity = '1';
        modal.modalBox.style.transform = 'scale(1)';
      },
      {
        id: taskId,
        modalOptions: modalOptions,
        message: '设备授权 · 点击恢复'
      }
    ),
    onLoad: (modalBox) => {
      // 设备授权面板：外壳改浅色主题，与内部内容区风格统一
      modalBox.style.background = '#f5f7fa';
      modalBox.style.color = '#111827';
      modalBox.style.boxShadow = '0 12px 36px rgba(0,0,0,0.18)';
      // 标题文字深色
      const titleEl = modalBox.querySelector('div[style*="color: white"]');
      if (titleEl) {
        titleEl.style.color = '#111827';
        titleEl.style.fontSize = '15px';
      }
      // 最小化 / 关闭按钮深色
      modalBox.querySelectorAll('button').forEach((btn) => {
        const txt = btn.textContent.trim();
        if (txt === '—' || txt === '×') {
          btn.style.color = '#4b5563';
          btn.addEventListener('mouseenter', () => { btn.style.color = '#111827'; });
          btn.addEventListener('mouseleave', () => { btn.style.color = '#4b5563'; });
        }
      });
      // 标题栏 hover 蒙层：设备授权是浅色面板，用弱蒙层避免黑色蒙层突兀
      const scrim = modalBox.querySelector('div[style*="backdrop-filter: blur"]');
      if (scrim) {
        scrim.style.background = 'rgba(255,255,255,0.5)';
      }
      initDeviceAuth(modalBox);
    }
  });
}

/**
 * 初始化设备授权面板（showModal onLoad 回调，因为 insertAdjacentHTML 不执行内联 script）。
 * @param {HTMLElement} modalBox - showModal 创建的模态窗内容容器
 */
function initDeviceAuth(modalBox) {
  const root = modalBox.querySelector('[data-device-auth-init]');
  if (!root || root.dataset.initialized) return;
  root.dataset.initialized = '1';

  const elLoading = root.querySelector('#da-loading');
  const elError = root.querySelector('#da-error');
  const elContent = root.querySelector('#da-content');
  const elUsed = root.querySelector('#da-used');
  const elMax = root.querySelector('#da-max');
  const elVerdict = root.querySelector('#da-verdict');
  const elNotice = root.querySelector('#da-notice');
  const elList = root.querySelector('#da-list');

  const VERDICT_MAP = {
    registered: { text: '已授权', cls: 'ok' },
    just_registered: { text: '新注册', cls: 'ok' },
    over_limit: { text: '已超限', cls: 'over' },
    not_registered: { text: '未注册', cls: 'warn' },
    unknown: { text: '未知', cls: 'warn' }
  };

  function showError(msg) {
    elLoading.style.display = 'none';
    elError.textContent = msg || '获取授权信息失败';
    elError.style.display = 'block';
  }

  function formatTime(s) {
    if (!s) return '未知';
    return s.length > 19 ? s.substring(0, 19) : s;
  }

  function maskHash(hash) {
    if (!hash || hash.length < 12) return hash || '-';
    return hash.substring(0, 8) + '****' + hash.substring(hash.length - 4);
  }

  function renderDeviceCard(dev, currentHash) {
    const isCurrent = currentHash && dev.fingerprint_hash === currentHash;
    const card = document.createElement('div');
    card.className = 'da-device-card' + (isCurrent ? ' current' : '');

    const info = document.createElement('div');
    info.className = 'da-device-info';

    const name = document.createElement('div');
    name.className = 'da-device-name';
    name.textContent = dev.device_nickname || ('设备 #' + dev.id);

    const meta = document.createElement('div');
    meta.className = 'da-device-meta';
    const line1 = [];
    if (dev.container_id) line1.push('容器: ' + String(dev.container_id).substring(0, 12));
    if (dev.fingerprint_mac) line1.push('MAC: ' + dev.fingerprint_mac);
    const line2 = [];
    line2.push('指纹: ' + maskHash(dev.fingerprint_hash));
    line2.push('最后使用: ' + formatTime(dev.last_seen_at));
    meta.innerHTML = line1.join('  \u00B7  ') + '<br>' + line2.join('  \u00B7  ');

    info.appendChild(name);
    info.appendChild(meta);

    card.appendChild(info);

    // 右侧操作区：当前设备标记 + ID 复制图标 + 解绑命令复制按钮
    var actions = document.createElement('div');
    actions.className = 'da-device-actions';

    if (isCurrent) {
      var tag = document.createElement('span');
      tag.className = 'da-device-current-tag';
      tag.textContent = '当前设备';
      actions.appendChild(tag);
    }

    // ID 复制图标按钮（hover 显示"复制ID"）
    var idBtn = document.createElement('button');
    idBtn.className = 'da-id-copy-btn';
    idBtn.setAttribute('data-tip', '复制ID');
    idBtn.innerHTML = '<svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
    idBtn.addEventListener('click', function () {
      _copyToClipboard(String(dev.id), idBtn, '已复制');
    });
    actions.appendChild(idBtn);

    card.appendChild(actions);

    return card;
  }

  function _copyToClipboard(text, btn, copiedText) {
    copiedText = copiedText || '已复制';
    var hasSvg = btn.querySelector('svg');
    var origHtml = null;
    var origText = null;
    if (hasSvg) {
      origHtml = btn.innerHTML;
    } else {
      origText = btn.textContent;
    }
    var done = function () {
      btn.classList.add('copied');
      if (hasSvg) {
        // SVG 图标按钮：换成对勾图标
        btn.innerHTML = '<svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
      } else {
        btn.textContent = copiedText;
      }
      setTimeout(function () {
        btn.classList.remove('copied');
        if (hasSvg) {
          btn.innerHTML = origHtml;
        } else {
          btn.textContent = origText;
        }
      }, 2000);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () {
        _copyFallback(text); done();
      });
    } else {
      _copyFallback(text); done();
    }
  }

  function _copyFallback(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) {}
    document.body.removeChild(ta);
  }

  async function init() {
    try {
      const [healthRes, listRes] = await Promise.all([
        fetch('/api/healthz'),
        fetch('/api/device-auths')
      ]);

      if (!healthRes.ok) {
        showError('健康检查接口返回 ' + healthRes.status);
        return;
      }
      const health = await healthRes.json();
      const auth = health.device_auth;

      if (!auth) {
        elLoading.style.display = 'none';
        elError.textContent = '引擎未初始化，设备授权信息暂不可用';
        elError.style.display = 'block';
        return;
      }

      let devices = [];
      if (listRes.ok) {
        const listData = await listRes.json();
        devices = listData.devices || [];
      }

      elLoading.style.display = 'none';
      elContent.style.display = 'block';

      const total = auth.total_unique_devices || devices.length || 0;
      const max = auth.max_devices || 3;
      const verdict = auth.verdict || 'unknown';
      const vInfo = VERDICT_MAP[verdict] || VERDICT_MAP.unknown;

      elUsed.textContent = total + ' / ' + max;
      elMax.textContent = max;
      elVerdict.textContent = vInfo.text;

      if (verdict === 'over_limit') {
        elNotice.style.display = 'block';
        elNotice.classList.remove('warn');
        elNotice.textContent = '当前工具包已授权 ' + total + ' 台设备（上限 ' + max + ' 台），' +
          '超出限制。如需在新设备上使用，请联系工具包作者解绑旧设备。';
      } else if (verdict === 'not_registered') {
        elNotice.style.display = 'block';
        elNotice.classList.add('warn');
        elNotice.textContent = '当前设备尚未登记，重启服务后将自动完成授权注册。';
      }

      const currentHash = auth.current_device && auth.current_device.fingerprint_hash;

      if (devices.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'da-empty';
        empty.textContent = '暂无已登记设备';
        elList.appendChild(empty);
      } else {
        devices.sort(function (a, b) {
          if (a.fingerprint_hash === currentHash) return -1;
          if (b.fingerprint_hash === currentHash) return 1;
          return (b.last_seen_at || '').localeCompare(a.last_seen_at || '');
        });
        devices.forEach(function (dev) {
          elList.appendChild(renderDeviceCard(dev, currentHash));
        });
      }
    } catch (e) {
      showError('网络异常: ' + (e.message || e));
    }
  }

  init();
}

function renderPersistedMinimizedTasks() {
  const tasks = JSON.parse(localStorage.getItem('__minimized_tasks') || '[]');
  if (tasks.length === 0) return;

  const container = document.getElementById('minimized-hints');
  if (!container) return;

  tasks.forEach(task => {

    const item = document.createElement('div');
    item.className = 'minimized-hint-item';
    item.title = task.message;
    item.textContent = task.message;

    item.addEventListener('click', function (e) {
      e.stopPropagation();
      item.remove();
      const updated = tasks.filter(t => t.id !== task.id);
      localStorage.setItem('__minimized_tasks', JSON.stringify(updated));

      // 先查是否已有该任务的 overlay
      const existingOverlay = document.querySelector(`[data-task-id="${task.id}"]`);
      if (existingOverlay) {
        document.body.appendChild(existingOverlay);
        existingOverlay.style.display = 'flex';
        existingOverlay.style.opacity = '1';
        return;
      }

      let optionsToUse = { ...task.modalOptions };
      optionsToUse.onMinimize = createMinimizableHandler(
          task.message || '任务 · 后台运行',
          null,
          {
            id: task.id,
            modalOptions: task.modalOptions,
            message: task.message || '任务 · 后台运行'
          }
      );

      if (task.modalOptions.url.includes('/play-music.html')) {
        optionsToUse.onLoad = (modalBox) => {
          const stateStr = localStorage.getItem(`__music_state_${task.id}`);
          let restoredState = null;
          if (stateStr) {
            try {
              restoredState = JSON.parse(stateStr);
            } catch (e) {
              console.warn('音乐状态解析失败', e);
            }
          }
          initMusicPlayer(modalBox, restoredState, task.id);
        };
        optionsToUse.onCloseAttempt = () => {
          return new Promise(resolve => {
            showConfirm({
              title: '确认关闭',
              message: '关闭后音乐将停止，且无法后台播放。\n\n建议点"—"最小化以继续听歌。\n\nℹ️ 跨页面恢复时需点击弹窗才能播放（浏览器安全限制）\n\n确定要关闭吗？',
              confirmText: '确定',
              cancelText: '取消',
              onConfirm: () => resolve(true),
              onCancel: () => resolve(false)
            });
          });
        };
      }

      if (task.modalOptions.url.includes('/terminal.html')) {
        optionsToUse.onLoad = (modalBox) => {
          if (!window.Terminal) {
            window.Terminal = new Terminal(modalBox);
          } else {
            window.Terminal.modalBox = modalBox;
            window.Terminal.init(true, true);
          }
        };
        optionsToUse.onCloseAttempt = () => {
          return new Promise((resolve) => {
            window.showConfirm({
              title: '关闭终端日志',
              message: '确定要关闭终端日志吗？关闭后当前会话日志将丢失。',
              confirmText: '关闭',
              cancelText: '取消',
              onConfirm: () => resolve(true),
              onCancel: () => resolve(false)
            });
          });
        };
        optionsToUse.onUnload = () => {
          if (window.Terminal && typeof window.Terminal.destroy === 'function') {
            window.Terminal.destroy();
          }
          window.Terminal = null;
        };
      }

      if (task.modalOptions.url.includes('/unsplash-image.html')) {
        optionsToUse.onLoad = (modalBox) => {
          // 从 localStorage 读取快照
          const stateStr = localStorage.getItem(`__unsplash_state__${task.id}`);
          let restoredState = null;
          if (stateStr) {
            try {
              restoredState = JSON.parse(stateStr);
            } catch (e) {
              console.warn('unsplash状态解析失败', e);
            }
          }
          // 👇 传给 initMusicPlayer
          initUnsplashSearch(modalBox, restoredState);
        }
      }

      if (task.modalOptions.url.includes('/pexels-image.html')) {
        optionsToUse.onLoad = (modalBox) => {
          // 从 localStorage 读取快照
          const stateStr = localStorage.getItem(`__pexels_state__${task.id}`);
          let restoredState = null;
          if (stateStr) {
            try {
              restoredState = JSON.parse(stateStr);
            } catch (e) {
              console.warn('pexels状态解析失败', e);
            }
          }
          // 👇 传给 initMusicPlayer
          initUnsplashSearch(modalBox, restoredState);
        }
      }

      const modal = showModal(optionsToUse);
      modal.overlay.dataset.taskId = task.id;
    });

    container.appendChild(item);
  });
}

// 立即执行一次
renderPersistedMinimizedTasks();

// 暴露公共方法到 window
window.showModal = showModal;
window.createMinimizableHandler = createMinimizableHandler;
window.showDeviceAuth = showDeviceAuth;
})();