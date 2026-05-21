(function () {
  if (document.getElementById('psytext-global-nav')) return;

  const navHTML = `
    <div class="psy-glass-nav">
      <input type="radio" name="nav" id="nav-home" />
      <label for="nav-home">首页</label>

      <input type="radio" name="nav" id="nav-holo" />
      <label for="nav-holo">全息感知基底</label>

      <input type="radio" name="nav" id="nav-rules" />
      <label for="nav-rules">规则结晶提炼</label>

      <input type="radio" name="nav" id="nav-ontology" />
      <label for="nav-ontology">本体论总结</label>

      <input type="radio" name="nav" id="nav-resources" />
      <label for="nav-resources">资源查看</label>

      <input type="radio" name="nav" id="nav-config" />
      <label for="nav-config">配置</label>

      <div class="psy-glider"></div>
    </div>
  `;

  const navContainer = document.createElement('div');
  navContainer.id = 'psytext-global-nav';
  navContainer.innerHTML = navHTML;
  document.body.appendChild(navContainer);

  const routes = {
    'nav-home': '/',
    'nav-holo': '/holo',
    'nav-rules': '/rules',
    'nav-ontology': '/ontology',
    'nav-resources': '/resources',
    'nav-config': '/config'
  };

  // ✅ 柔和渐变悬停背景（核心更新）
  const hoverGradients = {
    'nav-home':      'linear-gradient(135deg, rgba(220, 225, 235, 0.32), rgba(250, 250, 255, 0.22))',
    'nav-holo':      'linear-gradient(135deg, rgba(255, 230, 130, 0.42), rgba(255, 248, 200, 0.28))',
    'nav-rules':     'linear-gradient(135deg, rgba(160, 220, 255, 0.42), rgba(210, 245, 255, 0.28))',
    'nav-ontology':  'linear-gradient(135deg, rgba(180, 235, 200, 0.42), rgba(220, 250, 230, 0.28))',
    'nav-resources': 'linear-gradient(135deg, rgba(255, 200, 200, 0.42), rgba(255, 235, 235, 0.28))',
    'nav-config':    'linear-gradient(135deg, rgba(180, 230, 255, 0.42), rgba(220, 248, 255, 0.32))'
  };

  // 注入样式
  if (!document.getElementById('psy-glass-nav-style')) {
    const style = document.createElement('style');
    style.id = 'psy-glass-nav-style';
    let hoverCSS = '';
    for (const [id, gradient] of Object.entries(hoverGradients)) {
      hoverCSS += `.psy-glass-nav label[data-hover="${id}"]:hover { background: ${gradient}; }`;
    }

    style.textContent = `
      #psytext-global-nav {
        position: fixed;
        top: 0;
        right: 16px;
        z-index: 9999;
        transform: translateY(16px); /* ← 初始偏移 16px，等效于 top:16px */
        transition: transform 0.3s cubic-bezier(0.36, 0.07, 0.19, 0.97); /* ← 加过渡 */
        will-change: transform; /* 提升合成层 */
      }

      .psy-glass-nav {
        --bg: rgba(30, 30, 40, 0.7);
        --text: #e5e5e5;
        display: flex;
        position: relative;
        background: var(--bg);
        border-radius: 1rem;
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        box-shadow:
          inset 1px 1px 4px rgba(255, 255, 255, 0.2),
          inset -1px -1px 6px rgba(0, 0, 0, 0.3),
          0 4px 12px rgba(0, 0, 0, 0.15);
        overflow: hidden;
        width: 642px;
        height: 44px;
      }

      .psy-glass-nav input { display: none; }

      .psy-glass-nav label {
        display: flex;
        align-items: center;
        justify-content: center;
        min-width: 107px;
        font-size: 14px;
        padding: 0.8rem 0;
        cursor: pointer;
        font-weight: 600;
        letter-spacing: 0.3px;
        color: var(--text);
        position: relative;
        z-index: 2;
        transition: all 0.3s ease-in-out;
        white-space: nowrap;
        border-radius: 1rem;
      }

      .psy-glass-nav label:hover {
        color: white;
      }

      /* ========== 果冻动画 ========== */
      @keyframes jelly-shake {
        0%, 100% { transform: scale(1); }
        20% { transform: scale(0.95); }
        40% { transform: scale(1.05); }
        60% { transform: scale(0.98); }
        80% { transform: scale(1.02); }
      }
      .jelly-effect {
        animation: jelly-shake 0.6s cubic-bezier(0.36, 0.07, 0.19, 0.97);
      }

      /* ========== 悬停渐变背景（动态生成） ========== */
      ${hoverCSS}

      /* ========== 滑块 ========== */
      .psy-glider {
        position: absolute;
        top: 0;
        bottom: 0;
        width: calc(100% / 6);
        border-radius: 1rem;
        z-index: 1;
        transition:
          transform 0.5s cubic-bezier(0.37, 1.95, 0.66, 0.56),
          background 0.4s ease-in-out,
          box-shadow 0.4s ease-in-out;
      }

      #nav-home:checked ～ .psy-glider {
        transform: translateX(0%);
        background: linear-gradient(135deg, #c0c0c055, #e0e0e0);
        box-shadow: 0 0 18px rgba(192,192,192,0.5), 0 0 10px rgba(255,255,255,0.4) inset;
      }
      #nav-holo:checked ～ .psy-glider {
        transform: translateX(100%);
        background: linear-gradient(135deg, #ffd70055, #ffcc00);
        box-shadow: 0 0 18px rgba(255,215,0,0.5), 0 0 10px rgba(255,235,150,0.4) inset;
      }
      #nav-rules:checked ～ .psy-glider {
        transform: translateX(200%);
        background: linear-gradient(135deg, #d0e7ff55, #a0d8ff);
        box-shadow: 0 0 18px rgba(160,216,255,0.5), 0 0 10px rgba(200,240,255,0.4) inset;
      }
      #nav-ontology:checked ～ .psy-glider {
        transform: translateX(300%);
        background: linear-gradient(135deg, #b3d9b355, #cce6cc);
        box-shadow: 0 0 18px rgba(179,217,179,0.5), 0 0 10px rgba(204,230,204,0.4) inset;
      }
      #nav-resources:checked ～ .psy-glider {
        transform: translateX(400%);
        background: linear-gradient(135deg, #ffcccc55, #ffdddd);
        box-shadow: 0 0 18px rgba(255,204,204,0.5), 0 0 10px rgba(255,221,221,0.4) inset;
      }
      #nav-config:checked ～ .psy-glider {
        transform: translateX(500%);
        background: linear-gradient(135deg, #ccccff55, #dddee0);
        box-shadow: 0 0 18px rgba(204,204,255,0.5), 0 0 10px rgba(221,221,224,0.4) inset;
      }
    `;
    document.head.appendChild(style);
  }

  // 自动高亮当前页
  const path = window.location.pathname;
  let checkedId = 'nav-home';
  if (path.includes('/holo')) checkedId = 'nav-holo';
  else if (path.includes('/rules')) checkedId = 'nav-rules';
  else if (path.includes('/ontology')) checkedId = 'nav-ontology';
  else if (path.includes('/resources')) checkedId = 'nav-resources';
  else if (path.includes('/config')) checkedId = 'nav-config';

  document.getElementById(checkedId).checked = true;

  // 设置 data-hover 属性
  Object.keys(routes).forEach(id => {
    const label = document.querySelector(`label[for="${id}"]`);
    if (label) label.setAttribute('data-hover', id);
  });

  // 事件绑定
  const labels = document.querySelectorAll('#psytext-global-nav label');
  labels.forEach(label => {
    label.addEventListener('mouseenter', function () {
      this.classList.add('jelly-effect');
      setTimeout(() => this.classList.remove('jelly-effect'), 600);
    });

    label.addEventListener('click', function () {
      const id = this.getAttribute('for');
      window.location.href = routes[id];
    });
  });

  // ========== 智能滚动导航 - 极简克制版 ==========
  let lastScrollY = window.scrollY;
  let isNavVisible = true;
  const nav = document.getElementById('psytext-global-nav');

  // 配置
  const HIDE_THRESHOLD = 30;      // 向下滚超过 60px 隐藏
  const SHOW_TOP_THRESHOLD = 80; // 滚到距离顶部 <120px 时显示
  const MIN_SCROLL_DELTA = 8;    // 忽略小于 20px 的微小滚动（防抖）

  function updateNavVisibility() {
    const currentScrollY = window.scrollY;
    const scrollDelta = currentScrollY - lastScrollY;
    const isScrollingDown = scrollDelta > 0;

    // 如果滚动幅度太小，直接忽略
    if (Math.abs(scrollDelta) < MIN_SCROLL_DELTA) {
      lastScrollY = currentScrollY;
      return;
    }

    // 情况1：靠近顶部 → 强制显示
    if (currentScrollY <= SHOW_TOP_THRESHOLD) {
      if (!isNavVisible) {
        nav.style.transform = 'translateY(16px)';
        isNavVisible = true;
      }
    }
    // 情况2：远离顶部 且 向下滚动 → 隐藏
    else if (isScrollingDown && currentScrollY > HIDE_THRESHOLD) {
      if (isNavVisible) {
        nav.style.transform = 'translateY(-150%)';
        isNavVisible = false;
      }
    }
    // 情况3：远离顶部 且 向上滚动 → 保持隐藏（关键！）
    // 不做任何事，导航继续藏住

    lastScrollY = currentScrollY;
  }

  // 节流
  let ticking = false;
  window.addEventListener('scroll', () => {
    if (!ticking) {
      requestAnimationFrame(() => {
        updateNavVisibility();
        ticking = false;
      });
      ticking = true;
    }
  });

  // 初始化
  nav.style.transform = 'translateY(16px)';
  isNavVisible = true;
})();