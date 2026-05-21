/**
 * 初始化云朵流动背景效果（双层视差云）
 *
 * 该函数会在指定容器底部创建一个高度可配置的云层区域，
 * 包含灰云（底层）和白云（上层），分别以不同速度水平循环流动，
 * 营造出柔和、沉浸式的动态背景氛围。
 *
 * @param {Object} options - 配置选项对象
 * @param {string|HTMLElement} options.container - 目标容器（必需）
 *        可传入 CSS 选择器字符串（如 "#my-header"）或 DOM 元素。
 *        云层将作为子元素插入此容器，并定位在底部。
 * @param {number} [options.height=100] - 云层区域的高度（单位：px）
 *        默认为 100px。建议根据设计需求调整，避免遮挡主要内容。
 *
 * @example
 * // 基础用法：注入到已有 header 容器
 * initCloudBackground({
 *   container: '#psytext-header-bg',
 *   height: 120
 * });
 *
 * // 或传入 DOM 元素
 * const header = document.querySelector('.main-header');
 * initCloudBackground({ container: header, height: 90 });
 *
 * 注意：
 * - 云图路径已硬编码，请确保以下资源存在：
 *     /psytext_analyst/static/public/assets/images/whiteCloud.png
 *     /psytext_analyst/static/public/assets/images/grayCloud.png
 * - 动画使用 CSS keyframes 实现，全局仅注入一次样式。
 * - 云层 z-index 为 1，确保打字机等交互内容设置更高 z-index（如 3+）。
 */
(function () {
  window.initCloudBackground = function (options) {
    // 解析容器：支持字符串选择器或直接传入 DOM 元素
    const container = typeof options.container === 'string'
      ? document.querySelector(options.container)
      : options.container;

    // 云层区域高度，默认 100px
    const height = options.height || 100;

    // 确保容器可定位（为 absolute/fixed 子元素提供参考）
    container.style.position = 'relative';

    // 创建根容器，用于包裹两层云
    const root = document.createElement('div');
    root.innerHTML = `
      <div id="gray-cloud" class="cloud-layer"></div>
      <div id="white-cloud" class="cloud-layer"></div>
    `;
    root.style.cssText = `
      position: absolute;
      bottom: 0;           /* 贴紧容器底部 */
      left: 0;
      width: 100%;
      height: ${height}px; /* 使用传入的高度 */
      overflow: hidden;    /* 隐藏超出部分，防止滚动条 */
      pointer-events: none;/* 不拦截鼠标事件，允许点击穿透 */
      z-index: 1;          /* 层级低于打字机等交互元素 */
    `;

    // 注入云层样式（包括动画）
    const style = document.createElement('style');
    style.textContent = `
      .cloud-layer {
        position: absolute;
        width: 32880px;          /* 足够宽以实现无缝循环 */
        height: 100%;
        background-repeat: repeat-x;
        will-change: transform;  /* 提升动画性能 */
        backface-visibility: hidden;
      }
      #white-cloud {
        top: 28px;                          /* 白云下移 28px，形成视差 */
        height: calc(100% - 28px);          /* 高度相应缩减 */
        background-image: url("/static/assets/images/whiteCloud.png");
        animation: cloudFlowWhite 180s linear infinite; /* 慢速流动 */
        z-index: 1;
      }
      #gray-cloud {
        top: 8px;                           /* 灰云下移 8px */
        height: calc(100% - 8px);
        background-image: url("/static/assets/images/grayCloud.png");
        animation: cloudFlowGray 160s linear infinite;  /* 稍快于白云 */
        z-index: 0;
        mix-blend-mode: multiply;           /* 与背景融合，增强层次感 */
      }
      /* 白云动画：180秒完成一个完整循环（含反向半程）*/
      @keyframes cloudFlowWhite {
        0%, 100% { transform: translateX(0); }
        50% { transform: translateX(-16440px); } /* 移动一半宽度实现无缝 */
      }
      /* 灰云动画：160秒循环，速度略快于白云，增强视差感 */
      @keyframes cloudFlowGray {
        0%, 100% { transform: translateX(0); }
        50% { transform: translateX(-16440px); }
      }
    `;
    document.head.appendChild(style);

    // 将云层结构挂载到目标容器
    container.appendChild(root);
  };
})();