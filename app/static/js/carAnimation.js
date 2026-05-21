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
    <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 512 512"><path fill="#000" d="M188.287 169.428c-28.644-.076-60.908 2.228-98.457 8.01c-4.432.62-47.132 24.977-58.644 41.788c-11.512 16.812-15.45 48.813-15.45 48.813c-3.108 13.105-1.22 34.766-.353 36.872c1.17 4.56 7.78 8.387 19.133 11.154C35.84 295.008 53.29 278.6 74.39 278.574c22.092 0 40 17.91 40 40a40 40 0 0 1-.392 5.272c.59.008 1.26.024 1.82.03l239.266 1.99a40 40 0 0 1-.693-7.292c0-22.09 17.91-40 40-40c22.092 0 40 17.91 40 40c0 2.668-.266 5.33-.796 7.944l62.186.517c1.318-22.812 6.86-46.77-7.024-66.72c-5.456-7.84-31.93-22.038-99.03-32.66c-34.668-17.41-68.503-37.15-105.35-48.462c-28.41-5.635-59.26-9.668-96.09-9.765m-17.197 11.984c5.998.044 11.5.29 16.014.81l7.287 48.352c-41.43-5.093-83.647-9.663-105.964-27.5c.35-5.5 7.96-13.462 16.506-16.506c4.84-1.724 40.167-5.346 66.158-5.156zm34.625.348c25.012.264 62.032 2.69 87.502 13.94c12.202 5.65 35.174 18.874 50.537 30.55l-6.35 10.535c-41.706-1.88-97.288-4.203-120.1-6.78l-11.59-48.245zM74.39 294.574a24 24 0 0 0-24 24a24 24 0 0 0 24 24a24 24 0 0 0 24-24a24 24 0 0 0-24-24m320 0a24 24 0 0 0-24 24a24 24 0 0 0 24 24a24 24 0 0 0 24-24a24 24 0 0 0-24-24"/></svg>
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