/**
 * TypewriterCore - 打字机动画组件
 *
 * 功能：在指定容器中实现逐字打字 + 逐字删除的循环动画效果。
 * 特点：
 *   - 支持注入到任意已有 DOM 容器；
 *   - 完全由 CSS 控制样式（当使用自定义容器时）；
 *   - 提供灵活参数控制内容、速度、光标等；
 *   - 向后兼容旧版全局居中模式。
 *
 * ==============================
 * ✅ 基础使用方式
 * ==============================
 *
 * 方式 1：注入到已有容器（推荐）
 * HTML:
 *   <div id="my-typewriter"></div>
 * JS:
 *   initTypewriter({
 *     container: '#my-typewriter',
 *     poems: ["你好", "世界"],
 *     typingSpeed: 100,
 *     showCursor: true
 *   });
 *
 * → 组件会清空 #my-typewriter，并插入文字 + 光标。
 * → 所有样式（字体、颜色、布局等）由你通过 CSS 控制。
 *
 * 方式 2：自动创建居中弹窗（兼容旧逻辑）
 * JS:
 *   initTypewriter({
 *     poems: ["默认诗句"]
 *   });
 *
 * → 自动创建一个居中、带背景的浮动打字机（仅当未指定 container 时）。
 *
 * ==============================
 * 📌 参数说明 (options)
 * ==============================
 * @param {string|HTMLElement} [container]
 *   - 指定打字机挂载的容器（CSS 选择器 或 DOM 元素）。
 *   - 若提供，则完全交由你控制样式；组件不添加任何布局样式。
 *   - 若未提供，则回退到旧逻辑（使用 containerId 或自动创建居中层）。
 *
 * @param {string} [containerId = 'poem-container']
 *   - 仅在未传 `container` 时生效，用于查找或创建容器 ID。
 *
 * @param {Array<string>} [poems = ["静夜思..."]]
 *   - 要循环打字的文本数组，每项为一行。
 *
 * @param {number} [typingSpeed = 150]
 *   - 打字速度（毫秒/字符），值越小越快。
 *
 * @param {number} [erasingSpeed = 100]
 *   - 删除速度（毫秒/字符）。
 *
 * @param {number} [showDelay = 2000]
 *   - 打完一行后停留时间（毫秒）。
 *
 * @param {number} [eraseDelay = 2000]
 *   - 删除完一行后，等待下一行开始的时间（毫秒）。
 *
 * @param {boolean} [showCursor = true]
 *   - 是否显示闪烁光标。
 *
 * @param {boolean} [autoStart = true]
 *   - 是否初始化后自动开始打字。
 *
 * @param {string} [textElementId = 'poem-text']
 *   - 内部文字 span 的 ID（通常无需修改）。
 *
 * ==============================
 * 🧩 返回实例方法（可选）
 * ==============================
 * const tw = initTypewriter({ ... });
 * tw.start()      // 手动开始打字（若 autoStart: false）
 * tw.setText([...]) // 动态更新内容并重置
 *
 * 注意：目前 pause() 仅为占位，如需真正暂停需扩展状态管理。
 */

(function () {
  window.TypewriterCore = function (options) {
    const opts = options || {};
    const quotes = [
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

    // === 内容与动画节奏参数 ===
    const poems = Array.isArray(opts.poems) && opts.poems.length > 0
      ? opts.poems
      : quotes;
    const typingSpeed = typeof opts.typingSpeed === 'number' ? opts.typingSpeed : 150;
    const erasingSpeed = typeof opts.erasingSpeed === 'number' ? opts.erasingSpeed : 100;
    const showDelay = typeof opts.showDelay === 'number' ? opts.showDelay : 2000;
    const eraseDelay = typeof opts.eraseDelay === 'number' ? opts.eraseDelay : 2000;

    // === 显示控制 ===
    const showCursor = opts.showCursor !== false; // 默认 true
    const autoStart = opts.autoStart !== false;   // 默认 true

    // === 容器解析逻辑 ===
    let container;
    if (opts.container) {
      // 用户显式指定了容器：支持字符串选择器或 DOM 元素
      container = typeof opts.container === 'string'
        ? document.querySelector(opts.container)
        : opts.container;
    } else {
      // 兼容旧版：通过 containerId 查找或自动创建全局居中容器
      const containerId = opts.containerId || 'poem-container';
      container = document.getElementById(containerId);
      if (!container) {
        container = document.createElement('div');
        container.id = containerId;
        // 仅自动创建时应用默认样式（保持向后兼容）
        container.style.cssText = `
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
          z-index: 2;
          font-family: "Courier New", monospace;
          font-size: 24px;
          color: #f8f7f7;
          white-space: pre-wrap;
          line-height: 1.4;
        `;
        document.body.appendChild(container);
      }
    }

    if (!container) {
      console.error('[TypewriterCore] Failed to resolve container.');
      return;
    }

    // === 清空并初始化内部结构 ===
    container.innerHTML = '';
    const textEl = document.createElement('span');
    textEl.id = opts.textElementId || 'poem-text';
    container.appendChild(textEl);

    // === 光标（可选）===
    let cursor = null;
    if (showCursor) {
      cursor = document.createElement('span');
      cursor.id = 'poem-cursor';
      cursor.style.cssText = `
        display: inline-block;
        width: 2px;
        height: 36px;
        background-color: #08ebeb;
        margin-left: 4px;
        animation: blink 1s infinite;
        vertical-align: middle;
      `;
      container.appendChild(cursor);

      // 注入光标动画（全局只注入一次）
      if (!document.getElementById('typewriter-blink-style')) {
        const style = document.createElement('style');
        style.id = 'typewriter-blink-style';
        style.textContent = `
          @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0; }
          }
        `;
        document.head.appendChild(style);
      }
    }

    // === 打字逻辑 ===
    let currentText = "";
    let currentIndex = 0;

    function type() {
      if (currentIndex >= poems.length) {
        currentIndex = 0;
      }
      const line = poems[currentIndex];
      let i = 0;
      const typing = () => {
        if (i < line.length) {
          currentText += line.charAt(i);
          textEl.textContent = currentText;
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
          textEl.textContent = currentText;
          setTimeout(erasing, erasingSpeed);
        } else {
          currentIndex = (currentIndex + 1) % poems.length;
          setTimeout(type, eraseDelay);
        }
      };
      erasing();
    }

    // === 实例方法（供外部控制）===
    this.start = type;
    this.pause = () => {
      // 当前为简化版，如需真实暂停需引入状态标志和 clearTimeout
      console.warn('[TypewriterCore] pause() is not implemented in basic version.');
    };
    this.setText = (newPoems) => {
      // 支持字符串或数组
      const updated = Array.isArray(newPoems) ? newPoems : [newPoems];
      poems.splice(0, poems.length, ...updated);
      currentIndex = 0;
      currentText = "";
      textEl.textContent = "";
      if (autoStart) type();
    };

    // === 启动 ===
    if (autoStart) {
      type();
    }
  };

  /**
   * 初始化打字机（工厂函数）
   * @param {Object} options - 配置参数（见上方说明）
   * @returns {TypewriterCore} 实例
   */
  window.initTypewriter = function (options) {
    return new window.TypewriterCore(options);
  };
})();