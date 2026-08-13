/**
 * 自行车往返动画组件
 *
 * @param {Object} options
 * @param {HTMLElement} options.container 容器
 * @param {HTMLElement} options.anchorElement 参照物
 * @param {number} [options.offsetStart=50] 起跑线位置
 * @param {number} [options.offsetEnd=50] 终点线位置
 * @param {number} [options.duration=12000] 跑一圈要多久
 * @param {number|null} [options.verticalOffset=null] 垂直高度
 *   - 若为 null（默认）：垂直居中
 *   - 若为 number：距离容器顶部的 px 值（图标中心点位置）
 */
class BikeAnimation {
  constructor({
    container,
    anchorElement,
    offsetStart = 50,
    offsetEnd = 50,
    duration = 12000,
    verticalOffset = null
  }) {
    if (!(container instanceof HTMLElement)) throw new Error('[BikeAnimation] container must be an HTMLElement');
    if (!(anchorElement instanceof HTMLElement)) throw new Error('[BikeAnimation] anchorElement must be an HTMLElement');

    this.container = container;
    this.anchor = anchorElement;
    this.offsetStart = offsetStart;
    this.offsetEnd = offsetEnd;
    this.duration = duration;
    this.verticalOffset = verticalOffset;

    this._init();
    this._bindResize();
  }

  _init() {
    this._cleanup();

    const containerRect = this.container.getBoundingClientRect();
    const anchorRect = this.anchor.getBoundingClientRect();

    const startLeft = (anchorRect.right - containerRect.left) + this.offsetStart;
    const endRight = this.container.clientWidth - this.offsetEnd;
    const distance = endRight - startLeft;

    if (distance <= 0) return;

    // 👇 计算垂直位置：优先用用户传的，否则居中
    const bikeTop = (this.verticalOffset !== null)
      ? this.verticalOffset
      : Math.floor(this.container.clientHeight / 2);

    this.layer = document.createElement('div');
    this.layer.style.cssText = `
      position: absolute;
      top: 0; left: 0;
      width: 100%; height: 100%;
      pointer-events: none;
      z-index: 10;
    `;

    // 轨迹线：放在 bikeTop + 12px（保持在图标下方）
    this.trail = document.createElement('div');
    this.trail.style.cssText = `
      position: absolute;
      top: ${bikeTop + 12}px;
      left: ${startLeft}px;
      height: 2px;
      background: linear-gradient(to right, #ccc, #999, #ccc);
      width: 0;
      animation: extendTrail 12s linear infinite;
      border-radius: 1px;
      opacity: 0.85;
      z-index: 1;
    `;

    // 自行车图标：中心点对准 bikeTop
    this.bike = document.createElement('div');
    this.bike.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24">
        <path fill="#000" d="m18.18 10l-1.7-4.68A2.01 2.01 0 0 0 14.6 4H12v2h2.6l1.46 4h-4.81l-.36-1H12V7H7v2h1.75l1.82 5H9.9c-.44-2.23-2.31-3.88-4.65-3.99C2.45 9.87 0 12.2 0 15s2.2 5 5 5c2.46 0 4.45-1.69 4.9-4h4.2c.44 2.23 2.31 3.88 4.65 3.99c2.8.13 5.25-2.19 5.25-5c0-2.8-2.2-5-5-5h-.82zM7.82 16c-.4 1.17-1.49 2-2.82 2c-1.68 0-3-1.32-3-3s1.32-3 3-3c1.33 0 2.42.83 2.82 2H5v2zm6.28-2h-1.4l-.73-2H15c-.44.58-.76 1.25-.9 2m4.9 4c-1.68 0-3-1.32-3-3c0-.93.41-1.73 1.05-2.28l.96 2.64l1.88-.68l-.97-2.67c.03 0 .06-.01.09-.01c1.68 0 3 1.32 3 3s-1.33 3-3.01 3"/>
      </svg>
    `;
    this.bike.style.cssText = `
      position: absolute;
      top: ${bikeTop}px;
      left: ${startLeft}px;
      transform: translateY(-50%); /* 确保 center 对齐 */
      z-index: 2;
    `;

    this.layer.appendChild(this.trail);
    this.layer.appendChild(this.bike);
    this.container.appendChild(this.layer);

    const id = 'bike_' + Date.now();
    this.styleTag = document.createElement('style');
    this.styleTag.textContent = `
      @keyframes bikeMove_${id} {
        0% { left: ${startLeft}px; transform: translateY(-50%) scaleX(1); }
        49.9% { left: ${endRight}px; transform: translateY(-50%) scaleX(1); }
        50% { left: ${endRight}px; transform: translateY(-50%) scaleX(-1); }
        99.9% { left: ${startLeft}px; transform: translateY(-50%) scaleX(-1); }
        100% { left: ${startLeft}px; transform: translateY(-50%) scaleX(1); }
      }
      @keyframes trailGrow_${id} {
        0%, 100% { width: 0; }
        50% { width: ${distance}px; }
      }
    `;
    document.head.appendChild(this.styleTag);

    this.bike.style.animation = `bikeMove_${id} ${this.duration}ms linear infinite`;
    this.trail.style.animation = `trailGrow_${id} ${this.duration}ms linear infinite`;
  }

  _cleanup() {
    if (this.layer?.parentNode) this.layer.remove();
    if (this.styleTag?.parentNode) this.styleTag.remove();
    this.layer = null;
    this.trail = null;
    this.bike = null;
    this.styleTag = null;
  }

  _bindResize() {
    let tid;
    const onResize = () => {
      clearTimeout(tid);
      tid = setTimeout(() => this._init(), 150);
    };
    window.addEventListener('resize', onResize);
    this._unbind = () => {
      window.removeEventListener('resize', onResize);
      this._cleanup();
    };
  }

  destroy() {
    this._unbind?.();
  }
}
