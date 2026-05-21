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
    <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48"><g fill="#000"><path d="M29.004 13.674L25 12.97l.346-1.97l4.136.727A3.5 3.5 0 0 1 32.5 10h3.885c.34 0 .615.275.615.615v5.77c0 .34-.276.615-.615.615H32.5a3.5 3.5 0 0 1-3.496-3.326"/><path fill-rule="evenodd" d="M30.805 18.563L29.875 26H23v-1.28c0-.398-.378-.72-.844-.72h-8.07C8.516 24 4 27.85 4 32.6c0 .22.21.4.47.4h4.552a5.5 5.5 0 0 0 10.956 0h.91q.057 0 .112-.002V33h10.366c.202.68.783 1.115 1.418 1.25a5.5 5.5 0 0 0 10.703-2.137c.445-.464.669-1.145.395-1.882A6.5 6.5 0 0 0 35 26.628V19h-2.5a3.5 3.5 0 0 1-1.695-.437M16.95 33h-4.9a2.5 2.5 0 0 0 4.9 0m18.944.848a2.501 2.501 0 0 0 4.546-.801z" clip-rule="evenodd"/><path d="M9.17 20a3 3 0 0 1 .063-.162M9.17 20c-.11.313-.17.65-.17 1v1h15v-1q-.002-.507-.158-.962L23.83 20A3 3 0 0 0 21 18h-9a3 3 0 0 0-2.764 1.832"/></g></svg>
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