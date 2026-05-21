(function () {
  const container = document.getElementById('global-header');
  if (!container) return;
  if (container.children.length > 0) return; // 防止重复注入

  // === 注入 Header 背景容器===
  const headerBg = document.createElement('div');
  headerBg.id = 'psytext-header-bg';
  headerBg.style.cssText = `
    position: relative;
    height: 350px;
    width: 100%;
    background: url("/static/images/164.png") no-repeat center / cover;
    background-blend-mode: overlay;
    margin: 0;
    padding: 0;
    border-radius: 10px;
    box-sizing: border-box;
    z-index: 1;
  `;
  container.appendChild(headerBg);

  // --- 打字机容器（居中）---
  const typewriterEl = document.createElement('div');
  typewriterEl.id = 'psytext-header-typewriter';
  typewriterEl.style.cssText = `
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    display: inline-block;
    background-color: rgba(80, 80, 80, 0.7);
    border-radius: 15px;
    padding: 15px 20px;
    text-align: center;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    font-family: "Courier New", monospace;
    font-size: 24px;
    color: #f8f7f7;
    white-space: pre-wrap;
    line-height: 1.4;
    z-index: 3;
    pointer-events: auto;
  `;
  headerBg.appendChild(typewriterEl);

  // --- 云容器（底部上方 80px）---
  const cloudContainer = document.createElement('div');
  cloudContainer.id = 'psytext-header-clouds';
  cloudContainer.style.cssText = `
    position: absolute;
    bottom: 0;
    left: 0;
    width: 100%;
    height: 100px;
    overflow: hidden;
    z-index: 2;
    pointer-events: none;
  `;
  headerBg.appendChild(cloudContainer);

  // --- 双层云 ---
  const whiteCloud = document.createElement('div');
  whiteCloud.style.cssText = `
    position: absolute;
    top: 28px;
    height: 84px;
    width: 32880px;
    background-image: url("/static/images/whiteCloud.png");
    background-repeat: repeat-x;
    background-size: auto 100%;
    animation: cloudFlowWhite 180s linear infinite;
    will-change: transform;
    backface-visibility: hidden;
  `;

  const grayCloud = document.createElement('div');
  grayCloud.style.cssText = `
    position: absolute;
    top: 8px;
    height: 100px;
    width: 32880px;
    background-image: url("/static/images/grayCloud.png");
    background-repeat: repeat-x;
    background-size: auto 100%;
    animation: cloudFlowGray 160s linear infinite;
    will-change: transform;
    backface-visibility: hidden;
    mix-blend-mode: multiply;
  `;

  cloudContainer.appendChild(whiteCloud);
  cloudContainer.appendChild(grayCloud);

  // --- 注入动画样式（全局唯一）---
  if (!document.getElementById('psytext-cloud-animations')) {
    const animStyle = document.createElement('style');
    animStyle.id = 'psytext-cloud-animations';
    animStyle.textContent = `
      @keyframes cloudFlowWhite {
        0%, 100% { transform: translateX(0); }
        50% { transform: translateX(-16440px); }
      }
      @keyframes cloudFlowGray {
        0%, 100% { transform: translateX(0); }
        50% { transform: translateX(-16440px); }
      }
    `;
    document.head.appendChild(animStyle);
  }

  // --- 内联打字机逻辑（无外部依赖）---
  const poems = [
  "喜欢就是喜欢，不要让外界想法影响了你内心的真实感受。",
  "心诚则灵伤深也，若无其事否？诚幽则踽无行也，未雨绸缪否？俭入奢易，奢入俭难，其亦如此。",
  "忠于心者亦迷于心也。",
  "安以虚静，然以明心，是谓安然；心若止水，意自澄明，方得始终；虚静以安，明心以然，周流往复，心宽地广。",
  "虚构的世界可以反映出现实中最真实的情感。",
  "了解自己比了解世界更重要。",
  "虽不知此情是否非彼情，但殊途同归，皆是一往而深。",
  "馒头就水也能活，山珍海味亦无妨。",
  "我在此处，但不止于此处；我似常人，却远非常人。",
  "阁楼的小窗被风搅得不停吱呀作响，雨珠顺着窗棂缓缓滑落，像是正在哭诉的少女...",
  "不迷信形式，强调心性的纯粹与觉知。",
  "天国之恋，只有境界到了，消除了贪嗔痴，仅保留欲望本身的自然的天国儿女方能演绎。",
  "人是矛盾和不清醒的，既要也要才是常态。用感性去选择，用理性来分析，综合考量，既不忽略真实的情感，亦不忽视客观的事实。",
  "绿萝襟里藏春，雁叫三声长别，青衣红袖，洗尽尘冬霜雪，桃花谢了又红。",
  "真正的信任不是毫无保留的信任对方，而是彼此理解基础上的选择性开放。",
  "人心如海，暗流之下皆是未诉之言...",
  "即便世界是假的，但至少这一刻的痛是真的。",
  "我们都是戏子……演给谁看？",
  "心海之外，仍有心海。",
  "整个乌尔姆斯都说安芮是一个无心之人，可老主教却说他是乌尔姆斯唯一有心之人。",
  "即便是最深的黑暗，也会有一丝光明穿透。",
  "我们所追求的天堂，其实就存在于心中。",
  "细雨蒙蒙，打湿了古老的石板路，水珠顺着屋檐滴答作响，似是岁月滴落的记忆，每一声都是往昔故事的回响。",
  "其实，掉落在山洞里的那个郗煜是否死去并不重要，真正重要的是：你心中的那个郗煜还活着吗？",
  "温一壶杏花微雨入喉，坐拥青山听笙歌。",
  "离愁碾作檐下雨，砚池墨涸犹待续。",
  "今朝有酒今朝醉，桃夭灼灼笺成烬。",
  "离愁别恨碎碎扰，又与谁人说诉？",
  "晨露坠叶间，凉意忽沾襟，鸟欢啼，风舞叶；漫步廊间晓月，满地黄花堆积，过小桥，听流水。风走过，雨走过，笑曳如花；小道里，风诉叶语，絮儿叨叨。百八十步，鸟鹊声起，盈步轻轻，心事重重；光洒下，影班驳，似是而非。",
  "囚笼内外，谁分得清？",
  "行为与内心相互映射，推演的可靠性取决于我们对心理和行为的理解深度，以及对客观存在和个体不可控因素的掌握程度。可有些事情并不受个人意志控制，即使暂时超越了人性也难以持久。真能彻底跳脱人性者，已非人类，而是神、仙、妖、魔、佛、道，就是不是人。",
  "当剥离社会身份与叙事伪装，你的本质还剩什么？",
  "陶碗落桌的闷响惊起一旭尘烟...",
  "当一个人学会与矛盾共舞，在动态平衡中创造独属自己的生存语法，他便超越了和解与否的二元困境，成为活着的悖论，流动的哲学，未完成却完满的生命诗篇。他的平衡不是终点，而是永动的钟摆——向左摆是人性，向右摆是神性，而他在摆动的轨迹中，写满了凡人不敢直视的真相。这样的存在或许痛苦，却美得惊心动魄。就像深秋最后一片悬在枝头的叶，不坠落不是畏惧寒冬，而是要以摇摇欲坠的姿态，完成对季节最深刻的注解。",
  "你总在避免直视自己的心海，就像作者害怕面对笔下角色的质问。",
  "每个人都是自己故事中的主角，同时也是别人故事里的配角。",
  "突然间，所有的碎片都拼合在一起，那隐藏在表象之下的真相如同黎明的曙光般清晰可见。",
  "当映射体开始质疑自身的存在性，本体将听见心海涨潮的声音。"
];
  let currentText = "";
  let currentIndex = 0;
  const typingSpeed = 150;
  const erasingSpeed = 100;
  const showDelay = 2000;
  const eraseDelay = 2000;

  const textSpan = document.createElement('span');
  typewriterEl.appendChild(textSpan);

  const cursor = document.createElement('span');
  cursor.textContent = '|';
  cursor.style.cssText = `
    display: inline-block;
    font-size: 36px;
    color: #08ebeb;
    margin-left: 4px;
    animation: blinkCursor 1s infinite;
    vertical-align: middle;
  `;
  typewriterEl.appendChild(cursor);

  if (!document.getElementById('psytext-blink-style')) {
    const blinkStyle = document.createElement('style');
    blinkStyle.id = 'psytext-blink-style';
    blinkStyle.textContent = `
      @keyframes blinkCursor {
        0%, 100% { opacity: 1; }
        50% { opacity: 0; }
      }
    `;
    document.head.appendChild(blinkStyle);
  }

  function type() {
    if (currentIndex >= poems.length) currentIndex = 0;
    const line = poems[currentIndex];
    let i = 0;
    const typing = () => {
      if (i < line.length) {
        currentText += line.charAt(i);
        textSpan.textContent = currentText;
        i++;
        setTimeout(typing, typingSpeed);
      } else {
        setTimeout(erase, showDelay);
      }
    };
    typing();
  }

  function erase() {
    const line = poems[currentIndex];
    let i = line.length;
    const erasing = () => {
      if (i > 0) {
        i--;
        currentText = line.substring(0, i);
        textSpan.textContent = currentText;
        setTimeout(erasing, erasingSpeed);
      } else {
        currentIndex = (currentIndex + 1) % poems.length;
        setTimeout(type, eraseDelay);
      }
    };
    erasing();
  }

  setTimeout(type, 300);

  // === 注入 PSYTEXT 按钮 ===
  if (!document.querySelector('.button.psytext-injected')) {
    const style = document.createElement('style');
    style.textContent = `
      .button.psytext-injected {
        position: absolute;
        top: 30px;
        left: 20px;
        display: flex;
        gap: 0;
        border-radius: 4px;
        overflow: hidden;
        z-index: 1000;
        pointer-events: auto;
      }
      .button.psytext-injected .box {
        width: 32px;
        height: 38px;
        display: flex;
        justify-content: center;
        align-items: center;
        font-size: 14px;
        font-weight: 700;
        color: #fff;
        transition: all 0.8s;
        cursor: pointer;
        position: relative;
        background-color: #6a5af9;
        overflow: hidden;
      }
      .button.psytext-injected:hover .box {
        box-shadow: inset 0 0 8px rgba(255, 255, 255, 0.3);
      }
      .button.psytext-injected .box::before {
        content: "";
        position: absolute;
        top: 0;
        background: rgba(15, 15, 15, 0.6);
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        transform: translateY(100%);
        transition: transform 0.4s;
        color: white;
        font-weight: bold;
      }
      .button.psytext-injected .box:nth-child(1)::before { content: "P"; transform: translateY(-100%); }
      .button.psytext-injected .box:nth-child(2)::before { content: "S"; transform: translateY(100%); }
      .button.psytext-injected .box:nth-child(3)::before { content: "Y"; transform: translateY(-100%); }
      .button.psytext-injected .box:nth-child(4)::before { content: "T"; transform: translateY(100%); }
      .button.psytext-injected .box:nth-child(5)::before { content: "E"; transform: translateY(-100%); }
      .button.psytext-injected .box:nth-child(6)::before { content: "X"; transform: translateY(100%); }
      .button.psytext-injected .box:nth-child(7)::before { content: "T"; transform: translateY(-100%); }
      .button.psytext-injected:hover .box::before {
        transform: translateY(0);
      }
    `;
    document.head.appendChild(style);

    const btnWrapper = document.createElement('div');
    btnWrapper.className = 'button psytext-injected';
    ['P','S','Y','T','E','X','T'].forEach(letter => {
      const box = document.createElement('div');
      box.className = 'box';
      box.textContent = letter;
      btnWrapper.appendChild(box);
    });
    container.appendChild(btnWrapper);
  }

  // === 注入 Navbar ===
  if (!document.getElementById('psytext-global-nav')) {
    // 直接复用你提供的完整 navbar 逻辑（一字不改）
    (function () {
      const navHTML = `
        <div class="psy-glass-nav">
          <input type="radio" name="nav" id="nav-home" />
          <label for="nav-home">首页</label>
          <input type="radio" name="nav" id="nav-novel" />
          <label for="nav-novel">灵渊工坊</label>
          <input type="radio" name="nav" id="nav-resources" />
          <label for="nav-resources">心海书阁</label>
          <input type="radio" name="nav" id="nav-config" />
          <label for="nav-config">中枢控制台</label>
          <input type="radio" name="nav" id="nav-prompt" />
          <label for="nav-prompt">指令工坊</label>
          <input type="radio" name="nav" id="nav-plugin" />
          <label for="nav-plugin">智略库</label>
          <input type="radio" name="nav" id="nav-dao" />
          <label for="nav-dao">道之元典</label>
          <input type="radio" name="nav" id="nav-rule" />
          <label for="nav-rule">规则工坊</label>
          <div class="psy-glider"></div>
        </div>
      `;

      const navContainer = document.createElement('div');
      navContainer.id = 'psytext-global-nav';
      navContainer.innerHTML = navHTML;
      container.appendChild(navContainer);

      const routes = {
        'nav-home': '/',
        'nav-novel': '/novel',
        'nav-resources': '/resources',
        'nav-config': '/config',
        'nav-prompt': '/prompt',
        'nav-plugin': '/plugin',
        'nav-dao': '/dao',
        'nav-rule': '/rule'
      };

      const hoverGradients = {
        'nav-home': 'linear-gradient(135deg, rgba(220, 225, 235, 0.32), rgba(250, 250, 255, 0.22))',
        'nav-novel': 'linear-gradient(135deg, rgba(255, 230, 130, 0.42), rgba(255, 248, 200, 0.28))',
        'nav-resources': 'linear-gradient(135deg, rgba(160, 220, 255, 0.42), rgba(210, 245, 255, 0.28))',
        'nav-config': 'linear-gradient(135deg, rgba(180, 235, 200, 0.42), rgba(220, 250, 230, 0.28))',
        'nav-prompt': 'linear-gradient(135deg, rgba(255, 200, 200, 0.42), rgba(255, 235, 235, 0.28))',
        'nav-plugin': 'linear-gradient(135deg, rgba(200, 210, 255, 0.42), rgba(235, 240, 255, 0.28))',
        'nav-dao': 'linear-gradient(135deg, rgba(212, 180, 140, 0.45), rgba(245, 225, 190, 0.32))',
        'nav-rule': 'linear-gradient(135deg, rgba(180, 200, 190, 0.42), rgba(225, 240, 230, 0.28))'
      };

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
            top: 15px;
            right: 20px;
            z-index: 9999;
            transform: none;
            transition: transform 0.3s cubic-bezier(0.36, 0.07, 0.19, 0.97);
            will-change: transform;
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
            width: 856px;
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
          ${hoverCSS}
          .psy-glider {
            position: absolute;
            top: 0;
            bottom: 0;
            width: calc(100% / 8);
            border-radius: 1rem;
            z-index: 1;
            transition: transform 0.5s cubic-bezier(0.37, 1.95, 0.66, 0.56), background 0.4s, box-shadow 0.4s;
          }
          #nav-home:checked ～ .psy-glider { transform: translateX(0%); background: linear-gradient(135deg, #c0c0c055, #e0e0e0); box-shadow: 0 0 18px rgba(192,192,192,0.5), 0 0 10px rgba(255,255,255,0.4) inset; }
          #nav-novel:checked ～ .psy-glider { transform: translateX(100%); background: linear-gradient(135deg, #ffd70055, #ffcc00); box-shadow: 0 0 18px rgba(255,215,0,0.5), 0 0 10px rgba(255,235,150,0.4) inset; }
          #nav-resources:checked ～ .psy-glider { transform: translateX(200%); background: linear-gradient(135deg, #d0e7ff55, #a0d8ff); box-shadow: 0 0 18px rgba(160,216,255,0.5), 0 0 10px rgba(200,240,255,0.4) inset; }
          #nav-config:checked ～ .psy-glider { transform: translateX(300%); background: linear-gradient(135deg, #b3d9b355, #cce6cc); box-shadow: 0 0 18px rgba(179,217,179,0.5), 0 0 10px rgba(204,230,204,0.4) inset; }
          #nav-prompt:checked ～ .psy-glider { transform: translateX(400%); background: linear-gradient(135deg, #ffcccc55, #ffdddd); box-shadow: 0 0 18px rgba(255,204,204,0.5), 0 0 10px rgba(255,221,221,0.4) inset; }
          #nav-plugin:checked ～ .psy-glider { transform: translateX(500%); background: linear-gradient(135deg, #ccccff55, #dddee0); box-shadow: 0 0 18px rgba(200, 210, 255, 0.5), 0 0 10px rgba(235, 240, 255, 0.4) inset;}
          #nav-dao:checked ～ .psy-glider { transform: translateX(500%); background: linear-gradient(135deg, #ccccff55, #dddee0); box-shadow: 0 0 18px rgba(212, 180, 140, 0.5), 0 0 10px rgba(245, 225, 190, 0.4) inset;}
          #nav-rule:checked ～ .psy-glider { transform: translateX(500%); background: linear-gradient(135deg, #ccccff55, #dddee0); box-shadow: 0 0 18px rgba(180, 200, 190, 0.5), 0 0 10px rgba(225, 240, 230, 0.4) inset;}
        `;
        document.head.appendChild(style);
      }

      const path = window.location.pathname;
      let checkedId = 'nav-home';
      if (path.includes('/novel')) checkedId = 'nav-novel';
      else if (path.includes('/resources')) checkedId = 'nav-resources';
      else if (path.includes('/config')) checkedId = 'nav-config';
      else if (path.includes('/prompt')) checkedId = 'nav-prompt';
      else if (path.includes('/plugin')) checkedId = 'nav-plugin';
      else if (path.includes('/dao')) checkedId = 'nav-dao';
      else if (path.includes('/rule')) checkedId = 'nav-rule';
      document.getElementById(checkedId).checked = true;

      Object.keys(routes).forEach(id => {
        const label = document.querySelector(`label[for="${id}"]`);
        if (label) label.setAttribute('data-hover', id);
      });

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

      // ========== 智能滚动导航（完全保留你的逻辑）==========
      let lastScrollY = window.scrollY;
      let isNavVisible = true;
      const nav = document.getElementById('psytext-global-nav');
      const HIDE_THRESHOLD = 30;
      const SHOW_TOP_THRESHOLD = 80;
      const MIN_SCROLL_DELTA = 8;

      function updateNavVisibility() {
        const currentScrollY = window.scrollY;
        const scrollDelta = currentScrollY - lastScrollY;
        const isScrollingDown = scrollDelta > 0;
        if (Math.abs(scrollDelta) < MIN_SCROLL_DELTA) {
          lastScrollY = currentScrollY;
          return;
        }
        if (currentScrollY <= SHOW_TOP_THRESHOLD) {
          if (!isNavVisible) {
            nav.style.transform = 'translateY(16px)';
            isNavVisible = true;
          }
        } else if (isScrollingDown && currentScrollY > HIDE_THRESHOLD) {
          if (isNavVisible) {
            nav.style.transform = 'translateY(-150%)';
            isNavVisible = false;
          }
        }
        lastScrollY = currentScrollY;
      }

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

      nav.style.transform = 'translateY(16px)';
      isNavVisible = true;
    })();
  }
})();