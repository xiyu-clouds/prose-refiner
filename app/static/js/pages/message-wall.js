const BARRAGE_COLORS = [
  { start: 'rgba(255,255,255,0.95)', end: 'rgba(0,191,255,0.85)' },
  { start: 'rgba(255,255,255,0.9)', end: 'rgba(30,144,255,0.8)' },
  { start: 'rgba(240,240,255,0.95)', end: 'rgba(65,105,225,0.85)' },
  { start: 'rgba(230,230,255,0.9)', end: 'rgba(100,149,237,0.8)' },
  { start: 'rgba(255,255,255,0.95)', end: 'rgba(50,205,50,0.85)' },
  { start: 'rgba(255,255,255,0.9)', end: 'rgba(0,255,127,0.8)' },
  { start: 'rgba(240,255,240,0.95)', end: 'rgba(144,238,144,0.85)' },
  { start: 'rgba(230,255,230,0.9)', end: 'rgba(127,255,0,0.8)' },
  { start: 'rgba(255,255,255,0.95)', end: 'rgba(138,43,226,0.85)' },
  { start: 'rgba(255,255,255,0.9)', end: 'rgba(148,0,211,0.8)' },
  { start: 'rgba(250,240,255,0.95)', end: 'rgba(218,112,214,0.85)' },
  { start: 'rgba(245,230,255,0.9)', end: 'rgba(186,85,211,0.8)' },
  { start: 'rgba(255,255,255,0.95)', end: 'rgba(255,99,71,0.85)' },
  { start: 'rgba(255,255,255,0.9)', end: 'rgba(255,69,0,0.8)' },
  { start: 'rgba(255,240,240,0.95)', end: 'rgba(255,105,180,0.85)' },
  { start: 'rgba(255,230,230,0.9)', end: 'rgba(255,20,147,0.8)' },
  { start: 'rgba(255,255,255,0.95)', end: 'rgba(255,165,0,0.85)' },
  { start: 'rgba(255,255,255,0.9)', end: 'rgba(255,140,0,0.8)' },
  { start: 'rgba(255,245,230,0.95)', end: 'rgba(255,215,0,0.85)' },
  { start: 'rgba(255,235,220,0.9)', end: 'rgba(255,160,122,0.8)' },
  { start: 'rgba(255,255,255,0.95)', end: 'rgba(0,255,255,0.85)' },
  { start: 'rgba(255,255,255,0.9)', end: 'rgba(72,209,204,0.8)' },
  { start: 'rgba(240,255,255,0.95)', end: 'rgba(0,255,255,0.85)' },
  { start: 'rgba(230,255,255,0.9)', end: 'rgba(176,224,230,0.8)' },
  { start: 'rgba(255,255,255,0.95)', end: 'rgba(255,255,0,0.85)' },
  { start: 'rgba(255,255,255,0.9)', end: 'rgba(255,215,0,0.8)' },
  { start: 'rgba(255,255,240,0.95)', end: 'rgba(255,255,0,0.85)' },
  { start: 'rgba(255,255,230,0.9)', end: 'rgba(255,228,181,0.8)' },
  { start: 'rgba(255,255,255,0.95)', end: 'rgba(255,182,193,0.85)' },
  { start: 'rgba(255,255,255,0.9)', end: 'rgba(255,192,203,0.8)' },
  { start: 'rgba(255,245,248,0.95)', end: 'rgba(255,182,193,0.85)' },
  { start: 'rgba(255,235,242,0.9)', end: 'rgba(255,192,203,0.8)' },
];

const DEFAULT_MAX_VISIBLE = 30;
const DEFAULT_BASE_SPEED = 40;
const CACHE_KEY_MESSAGE_WALL_BG = 'card_config_message_wall_bg';

class MessageWall {
  constructor() {
    this.quotes = [];
    this.isEnabled = true;
    this.isPaused = false;
    this.maxVisible = 10;
    this.maxChars = 100;
    this.baseSpeed = DEFAULT_BASE_SPEED;
    this.activeBarrages = new Map();
    this.barrageQueue = [];
    this.animationFrame = null;
    this.lastSpawnTime = 0;
    this.spawnInterval = 2000;
    this.verticalSlots = [];
    this.speedUpdateTimeout = null;
    this.init();
  }

  init() {
    this.initElements();
    this.bindEvents();
    this.initVerticalSlots();
    this.initApp();
  }

  async initApp() {
    await this.loadConfigs();
    await this.loadQuotes();
    this.startAnimation();
  }

  initElements() {
    this.container = document.getElementById('message-wall-container');
    this.barrageLayer = document.getElementById('barrage-layer');
    this.input = document.getElementById('barrage-input');
    this.sendBtn = document.getElementById('send-btn');
    this.toggleBtn = document.getElementById('toggle-btn');
    this.pauseBtn = document.getElementById('pause-btn');
    this.refreshBtn = document.getElementById('refresh-btn');
    this.countSlider = document.getElementById('count-slider');
    this.countValue = document.getElementById('count-value');
    this.speedSlider = document.getElementById('speed-slider');
    this.speedValue = document.getElementById('speed-value');
    this.quotesGrid = document.getElementById('quotesGrid');
  }

  bindEvents() {
    this.sendBtn.addEventListener('click', () => this.sendQuote());
    this.input.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') this.sendQuote();
    });

    this.input.addEventListener('focus', () => {
      this.container.classList.add('has-focus');
    });

    this.input.addEventListener('blur', () => {
      this.container.classList.remove('has-focus');
    });

    this.toggleBtn.addEventListener('click', () => {
      this.isEnabled = !this.isEnabled;
      const icon = this.toggleBtn.querySelector('i');
      if (this.isEnabled) {
        icon.className = 'fas fa-eye';
        this.toggleBtn.classList.add('active');
        window.showStatus('弹幕已开启', 'success');
      } else {
        icon.className = 'fas fa-eye-slash';
        this.toggleBtn.classList.remove('active');
        this.clearBarrages();
        window.showStatus('弹幕已关闭', 'info');
      }
    });

    this.pauseBtn.addEventListener('click', () => {
      this.isPaused = !this.isPaused;
      const icon = this.pauseBtn.querySelector('i');
      if (this.isPaused) {
        icon.className = 'fas fa-play';
        window.showStatus('弹幕已暂停', 'info');
      } else {
        icon.className = 'fas fa-pause';
        window.showStatus('弹幕已继续', 'info');
      }
    });

    this.refreshBtn.addEventListener('click', () => {
      window.showStatus('正在刷新弹幕...', 'info');
      this.loadQuotes();
    });

    this.countSlider.addEventListener('input', (e) => {
      this.maxVisible = parseInt(e.target.value);
      this.countValue.textContent = this.maxVisible;
    });

    this.speedSlider.addEventListener('input', (e) => {
      this.baseSpeed = parseInt(e.target.value);
      this.speedValue.textContent = this.baseSpeed;
      this.debouncedUpdateSpeed();
    });

    window.addEventListener('resize', () => {
      this.initVerticalSlots();
    });
  }

  initVerticalSlots() {
    const layerHeight = this.barrageLayer.clientHeight;
    const slotHeight = 50;
    this.verticalSlots = [];
    const slots = Math.floor(layerHeight / slotHeight) - 2;
    for (let i = 0; i < slots; i++) {
      this.verticalSlots.push((i + 1) * slotHeight);
    }
  }

  async loadConfigs() {
    const cachedBgUrl = window.AppCache?.get(CACHE_KEY_MESSAGE_WALL_BG);
    if (cachedBgUrl) {
      this.container.style.backgroundImage = `url(${cachedBgUrl})`;
    }

    try {
      const [cardRes, thresholdsRes] = await Promise.all([
        fetch('/api/card-config'),
        fetch('/api/meta/frontend-thresholds')
      ]);
      const cardConfig = await cardRes.json();
      const thresholds = await thresholdsRes.json();

      const savedMaxChars = thresholds.danmaku_max_chars;
      if (savedMaxChars) {
        this.maxChars = savedMaxChars;
        this.input.maxLength = this.maxChars;
      }

      const savedMaxBaseSpeed = thresholds.danmaku_max_base_speed;
      if (savedMaxBaseSpeed && this.speedSlider) {
        this.speedSlider.max = savedMaxBaseSpeed;
      }

      const bgImageUrl = cardConfig.message_wall_bg_image_url;
      if (bgImageUrl && bgImageUrl.length > 0) {
        window.AppCache?.set(CACHE_KEY_MESSAGE_WALL_BG, bgImageUrl, 1800);
        if (cachedBgUrl !== bgImageUrl) {
          this.container.style.backgroundImage = `url(${bgImageUrl})`;
        }
      }
    } catch (error) {
      console.error('加载配置失败:', error);
    }
  }

  async loadQuotes() {
    try {
      const response = await fetch('/api/quotes?only_active=true');
      const quotes = await response.json();
      this.quotes = Array.isArray(quotes) ? quotes : [];
      this.barrageQueue = [...this.quotes];
      window.showStatus(`已加载 ${this.quotes.length} 条弹幕`, 'success');
    } catch (error) {
      console.error('加载弹幕失败:', error);
      window.showStatus('加载弹幕失败', 'error');
    } finally {
      this.renderQuotesGrid();
    }
  }

  renderQuotesGrid() {
    if (!this.quotesGrid) return;

    const countEl = document.getElementById('quotes-count');
    if (countEl) {
      countEl.textContent = this.quotes.length;
    }

    this.quotesGrid.innerHTML = '';

    if (this.quotes.length === 0) {
      this.quotesGrid.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; color: #888; padding: 40px;">暂无留言记录</div>';
      return;
    }

    this.quotes.forEach(quote => {
      const card = this.createQuoteCard(quote);
      this.quotesGrid.appendChild(card);
    });
  }

  createQuoteCard(quote) {
    const card = document.createElement('div');
    card.className = 'quote-card';
    card.dataset.id = quote.id;

    const charCount = (quote.content || '').length;
    const isOver = charCount > this.maxChars;

    card.innerHTML = `
      <div class="quote-header">
        <div class="quote-actions">
          <button class="quote-action-btn edit-btn" title="编辑" onclick="messageWall.editQuote(${quote.id})">
            <i class="fas fa-edit"></i>
          </button>
          <button class="quote-action-btn delete-btn" title="删除" onclick="messageWall.deleteQuote(${quote.id})">
            <i class="fas fa-trash"></i>
          </button>
        </div>
      </div>
      <div class="quote-content">
        <span class="quote-text">${this.escapeHtml(quote.content)}</span>
      </div>
      <div class="quote-meta">
        <span>展示 ${quote.display_count || 0} 次</span>
        <span class="quote-char-counter ${isOver ? 'quote-char-counter--over' : ''}">
          ${charCount} / ${this.maxChars}
        </span>
      </div>
    `;

    return card;
  }

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  async editQuote(id) {
    const quote = this.quotes.find(q => String(q.id) === String(id));
    if (!quote) return;

    const card = document.querySelector(`.quote-card[data-id="${id}"]`);
    if (!card) return;

    card.classList.add('editing');
    const charCount = (quote.content || '').length;

    card.innerHTML = `
      <div class="quote-header">
        <div class="quote-actions">
          <button class="quote-action-btn" title="保存" onclick="messageWall.saveQuote(${id})">
            <i class="fas fa-save"></i>
          </button>
          <button class="quote-action-btn delete-btn" title="取消" onclick="messageWall.renderQuotesGrid()">
            <i class="fas fa-times"></i>
          </button>
        </div>
      </div>
      <div class="quote-content">
        <textarea id="quote-edit-${id}" maxlength="${this.maxChars}" oninput="messageWall.updateEditCharCounter(${id})">${this.escapeHtml(quote.content)}</textarea>
      </div>
      <div class="quote-meta">
        <span>展示 ${quote.display_count || 0} 次</span>
        <span class="quote-char-counter" id="quote-edit-counter-${id}">${charCount} / ${this.maxChars}</span>
      </div>
    `;

    const textarea = document.getElementById(`quote-edit-${id}`);
    textarea.focus();
    textarea.select();
  }

  updateEditCharCounter(id) {
    const textarea = document.getElementById(`quote-edit-${id}`);
    const counter = document.getElementById(`quote-edit-counter-${id}`);
    if (textarea && counter) {
      const count = textarea.value.length;
      counter.textContent = `${count} / ${this.maxChars}`;
      if (count > this.maxChars) {
        counter.classList.add('quote-char-counter--over');
      } else {
        counter.classList.remove('quote-char-counter--over');
      }
    }
  }

  async saveQuote(id) {
    const textarea = document.getElementById(`quote-edit-${id}`);
    if (!textarea) return;

    const content = textarea.value.trim();
    if (!content) {
      window.showStatus('请输入留言内容', 'warning');
      return;
    }

    if (content.length > this.maxChars) {
      window.showStatus(`留言内容不能超过 ${this.maxChars} 个字符`, 'warning');
      return;
    }

    try {
      const response = await fetch(`/api/quotes/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        const errorMsg = errorData?.detail || `修改失败，HTTP ${response.status}`;
        window.showStatus(errorMsg, 'error');
        return;
      }

      const quote = this.quotes.find(q => String(q.id) === String(id));
      if (quote) {
        quote.content = content;
      }

      this.renderQuotesGrid();
      window.showStatus('留言修改成功', 'success');
    } catch (error) {
      console.error('修改留言失败:', error);
      window.showStatus('修改留言失败', 'error');
    }
  }

  async deleteQuote(id) {
    window.showConfirm({
      title: '确认删除',
      message: '确定要删除这条留言吗？',
      confirmText: '删除',
      cancelText: '取消',
      onConfirm: async () => {
        try {
          const response = await fetch(`/api/quotes/${id}`, {
            method: 'DELETE'
          });

          if (!response.ok) {
            const errorData = await response.json().catch(() => null);
            const errorMsg = errorData?.detail || `删除失败，HTTP ${response.status}`;
            window.showStatus(errorMsg, 'error');
            return;
          }

          this.quotes = this.quotes.filter(q => String(q.id) !== String(id));
          this.barrageQueue = this.barrageQueue.filter(q => String(q.id) !== String(id));
          this.renderQuotesGrid();
          window.showStatus('留言删除成功', 'success');
        } catch (error) {
          console.error('删除留言失败:', error);
          window.showStatus('删除留言失败', 'error');
        }
      }
    });
  }

  async sendQuote() {
    const content = this.input.value.trim();
    if (!content) {
      window.showStatus('请输入留言内容', 'warning');
      return;
    }

    if (content.length > this.maxChars) {
      window.showStatus(`留言内容不能超过 ${this.maxChars} 个字符`, 'warning');
      return;
    }

    try {
      const lengthFactor = 0.7 + Math.min(content.length, 100) / 200;
      const randomFactor = 0.85 + Math.random() * 0.3;
      const speed = Math.round(this.baseSpeed * lengthFactor * randomFactor);
      const gradientIndex = Math.floor(Math.random() * BARRAGE_COLORS.length);

      await fetch('/api/quotes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content,
          is_active: true,
          priority: 0,
          display_count: 0,
          speed,
          font_size: 18,
          gradient_index: gradientIndex
        })
      });
      this.input.value = '';
      await this.loadQuotes();
      window.showStatus('留言发送成功', 'success');
    } catch (error) {
      console.error('发送留言失败:', error);
      window.showStatus('发送留言失败', 'error');
    }
  }

  getAvailableSlot() {
    if (this.verticalSlots.length === 0) return 50;

    const usedSlots = Array.from(this.activeBarrages.values()).map(b => b.top);
    const available = this.verticalSlots.filter(slot =>
      !usedSlots.some(used => Math.abs(used - slot) < 40)
    );

    return available.length > 0
      ? available[Math.floor(Math.random() * available.length)]
      : this.verticalSlots[Math.floor(Math.random() * this.verticalSlots.length)];
  }

  spawnBarrage() {
    if (!this.isEnabled || this.isPaused) return;
    if (this.activeBarrages.size >= this.maxVisible) return;
    if (this.barrageQueue.length === 0) {
      this.barrageQueue = [...this.quotes];
    }

    const now = Date.now();
    if (now - this.lastSpawnTime < this.spawnInterval) return;

    const quote = this.barrageQueue.shift();
    if (!quote) return;

    const slot = quote.top ?? this.getAvailableSlot();
    const gradientIndex = quote.gradient_index ?? Math.floor(Math.random() * BARRAGE_COLORS.length);
    const colors = BARRAGE_COLORS[gradientIndex];

    const contentLength = (quote.content || '').length;
    const lengthFactor = 0.7 + Math.min(contentLength, 100) / 200;
    const randomFactor = 0.85 + Math.random() * 0.3;
    const speed = Math.round(this.baseSpeed * lengthFactor * randomFactor);

    const fontSize = quote.font_size ?? 18;
    const displayCount = quote.display_count ?? 0;

    const el = document.createElement('div');
    el.className = 'barrage-item';
    el.innerHTML = `${quote.content}<span class="barrage-count">${displayCount}</span>`;
    el.style.background = `linear-gradient(135deg, ${colors.start}, ${colors.end})`;
    el.style.fontSize = `${fontSize}px`;
    el.style.top = `${slot}px`;
    el.style.left = `${window.innerWidth}px`;

    this.barrageLayer.appendChild(el);

    const barrageId = `barrage-${Date.now()}-${Math.random()}`;
    this.activeBarrages.set(barrageId, {
      id: barrageId,
      el,
      quote,
      top: slot,
      x: window.innerWidth,
      speed,
      lengthFactor,
      randomFactor,
      gradientIndex
    });

    this.lastSpawnTime = now;
  }

  updateBarrages() {
    if (this.isPaused) return;

    const toRemove = [];
    this.activeBarrages.forEach((barrage, id) => {
      if (barrage.lengthFactor !== undefined && barrage.randomFactor !== undefined) {
        barrage.speed = Math.round(this.baseSpeed * barrage.lengthFactor * barrage.randomFactor);
      }
      barrage.x -= barrage.speed * 0.05;
      barrage.el.style.left = `${barrage.x}px`;

      if (barrage.x < -barrage.el.offsetWidth - 50) {
        toRemove.push(id);
        barrage.el.remove();

        if (barrage.quote.id) {
          this.updateDisplayCount(barrage.quote.id, (barrage.quote.display_count || 0) + 1);
        }
      }
    });

    toRemove.forEach(id => {
      this.activeBarrages.delete(id);
    });
  }

  async updateDisplayCount(quoteId, count) {
    try {
      await fetch(`/api/quotes/${quoteId}/display-fields`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_count: count })
      });

      const quote = this.quotes.find(q => String(q.id) === String(quoteId));
      if (quote) {
        quote.display_count = count;
      }

      const card = document.querySelector(`.quote-card[data-id="${quoteId}"]`);
      if (card) {
        const metaSpan = card.querySelector('.quote-meta span:first-child');
        if (metaSpan) {
          metaSpan.textContent = `展示 ${count} 次`;
        }
      }
    } catch (error) {
      console.error('更新弹幕计数失败:', error);
    }
  }

  startAnimation() {
    const animate = () => {
      this.spawnBarrage();
      this.updateBarrages();
      this.animationFrame = requestAnimationFrame(animate);
    };
    animate();
  }

  clearBarrages() {
    this.activeBarrages.forEach(barrage => barrage.el.remove());
    this.activeBarrages.clear();
  }

  debouncedUpdateSpeed() {
    if (this.speedUpdateTimeout) {
      clearTimeout(this.speedUpdateTimeout);
    }
    this.speedUpdateTimeout = setTimeout(() => {
      this.updateSpeedInBackend();
    }, 500);
  }

  async updateSpeedInBackend() {
    try {
      await fetch('/api/quotes/speed', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ base_speed: this.baseSpeed })
      });
    } catch (error) {
      console.error('更新弹幕速度失败:', error);
    }
  }
}

let messageWall;
document.addEventListener('DOMContentLoaded', () => {
  messageWall = new MessageWall();
});