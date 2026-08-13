function connectGlobalSSE() {
    if (window.__globalSSE) {
        if (window.__globalSSE.readyState === EventSource.OPEN) {
            updateSSEStatus('success', '🟢 已连接');
            return window.__globalSSE;
        }
        if (window.__globalSSE.readyState === EventSource.CONNECTING) {
            updateSSEStatus('warning', '🟡 连接中...');
            return window.__globalSSE;
        }
    }

    const es = new EventSource('/api/sse');
    window.__globalSSE = es;

    es.onopen = () => {
        updateSSEStatus('success', '🟢 已连接');
        addLog('[INFO] SSE 连接已建立', 'success');
    };

    const events = ['upload_progress', 'task_progress', 'feature_model_download_progress'];

    events.forEach(type => {
        es.addEventListener(type, (e) => {
            try {
                const data = JSON.parse(e.data);
                window.dispatchEvent(new CustomEvent('psytext:' + type, { detail: { eventType: type, data } }));
            } catch (err) {
                console.warn('SSE 事件解析失败:', type, e.data);
            }
        });
    });

    es.onerror = () => {
        window.__globalSSE = null;
        updateSSEStatus('error', '❌ 已断开');
        addLog('[ERROR] SSE 连接异常，正在重连...', 'error');
        setTimeout(connectGlobalSSE, 5000);
    };

    return es;
}

function listenSSE(eventType, handler) {
    const fullType = 'psytext:' + eventType;
    const wrapper = (e) => handler(e.detail);
    window.addEventListener(fullType, wrapper);
    return () => window.removeEventListener(fullType, wrapper);
}

function parseSSEEvent(data) {
    if (typeof data === 'string') {
        return JSON.parse(data);
    }
    return data;
}

function getEventTypeIcon(eventType) {
    const iconMap = {
        'upload_progress': '📤',
        'task_progress': '⚡',
        'feature_model_download_progress': '📥'
    };
    return iconMap[eventType] || '📌';
}

function formatSSEMessage(eventType, data) {
    const parsedData = parseSSEEvent(data);
    const { title, content, meta } = parsedData;
    const icon = getEventTypeIcon(eventType);

    let message = `${icon} ${title || ''}`;
    if (content) message += ` | ${content}`;

    if (meta) {
        if (meta.progress !== undefined) message += ` [${meta.progress}%]`;
        if (meta.success !== undefined) message += meta.success ? ' ✅' : ' ❌';
    }

    return { message, title, eventType };
}

function renderProgressBar(percent, width = 20) {
    const filled = Math.round((percent / 100) * width);
    const empty = width - filled;
    return '<span style="color:#87CEEB;letter-spacing:2px;">' + '█'.repeat(filled) + '</span>' + '<span style="color:#FFFFFF;letter-spacing:2px;">' + '█'.repeat(empty) + '</span>';
}

function addLog(message, type = 'info') {
    const logBox = document.getElementById('progressLog');
    if (!logBox) return;

    const logLine = document.createElement('div');
    logLine.className = `log-line ${type}`;

    const timestamp = new Date().toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });

    logLine.innerHTML = `[${timestamp}] ${message}`;
    logBox.appendChild(logLine);
    logBox.scrollTop = logBox.scrollHeight;
}

function updateSSEStatus(status, text) {
    const statusEl = document.getElementById('sseStatus');
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.className = `status-indicator ${status}`;
}

let autoHideTimer = null;

function showMessage(msg, elementId, displayProp = 'block', autoHideDelay = null, container = null) {
    if (autoHideTimer) {
        clearTimeout(autoHideTimer);
        autoHideTimer = null;
    }

    const el = container?.querySelector('#' + elementId) || document.getElementById(elementId);
    if (!el) return;

    el.innerHTML = msg;
    el.style.display = displayProp;
    el.scrollIntoView({ behavior: "smooth", block: "nearest" });

    if (autoHideDelay) {
        autoHideTimer = setTimeout(() => {
            el.style.display = 'none';
            autoHideTimer = null;
        }, autoHideDelay);
    }
}

function showError(msg, container = null) {
    showMessage(`❌ ${msg}`, "globalError", "block", 8000, container);
}

function hideError() {
    const el = document.getElementById("globalError");
    if (el) el.style.display = "none";
}

function showResult(msg) {
    showMessage(msg, "result", "block", 5000);
}

function hideResult() {
    const el = document.getElementById("result");
    if (el) el.style.display = "none";
}

function showStatus(options, type) {
    const TYPE_DEFAULT_DURATIONS = {
        error: 8000,
        success: 5000,
        warning: 5000,
        info: 3000,
    };

    let message, statusType = 'info', duration = null, containerId = 'statusBox', container = null;

    if (typeof options === 'string') {
        message = options;
        statusType = type || 'info';
    } else {
        message = options.message;
        statusType = options.type || 'info';
        duration = options.duration || null;
        containerId = options.containerId || 'statusBox';
        container = options.container || null;
    }

    if (duration == null || typeof duration !== 'number' || duration <= 0) {
        duration = TYPE_DEFAULT_DURATIONS[statusType] || TYPE_DEFAULT_DURATIONS.info;
    }

    let statusBox = container?.querySelector('#' + containerId) || document.getElementById(containerId);
    if (!statusBox) return;

    const colors = {
        success: '#28a745',
        error: '#dc3545',
        warning: '#ffc107',
        info: '#6c757d'
    };

    statusBox.textContent = message;
    statusBox.style.display = 'block';
    statusBox.style.background = colors[statusType] || colors.info;
    statusBox.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
    statusBox.style.opacity = '1';
    statusBox.style.transform = 'translateY(0)';

    let hideTimer = setTimeout(() => {
        statusBox.style.opacity = '0';
        statusBox.style.transform = 'translateY(-10px)';
        setTimeout(() => {
            statusBox.style.display = 'none';
        }, 300);
    }, duration);

    return {
        close: () => {
            clearTimeout(hideTimer);
            statusBox.style.opacity = '0';
            setTimeout(() => {
                statusBox.style.display = 'none';
            }, 300);
        }
    };
}

function showConfirm(options = {}) {
    const {
        title = '确认操作',
        message = '确定要继续吗？',
        confirmText = '确定',
        cancelText = '取消',
        onConfirm = null,
        onCancel = null
    } = options;

    const overlay = document.createElement('div');
    overlay.className = 'xh-confirm-overlay';
    overlay.id = 'overlay-' + Date.now();
    overlay.style.cssText = `
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100% !important;
        height: 100% !important;
        background: rgba(0, 0, 0, 0.6) !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        z-index: 99999 !important;
    `;

    const confirmId = 'confirm-' + Date.now();

    overlay.innerHTML = `
        <div class="xh-confirm-modal" style="background: #ffffff; border-radius: 12px; box-shadow: 0 10px 40px rgba(0, 0, 0, 0.25); max-width: 480px; width: 90%; max-height: 80vh; overflow: hidden; display: flex; flex-direction: column;">
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid #e5e7eb; flex-shrink: 0;">
                <h3 style="margin: 0; font-size: 16px; font-weight: 600; color: #374151;">${title}</h3>
                <button class="xh-confirm-close" style="background: none; border: none; color: #9ca3af; cursor: pointer; font-size: 20px; padding: 4px; border-radius: 4px;">&times;</button>
            </div>
            <div style="padding: 24px 20px; text-align: center; flex: 1; overflow-y: auto; min-height: 60px;">
                <p style="margin: 0; font-size: 14px; color: #4b5563; line-height: 1.6; white-space: pre-wrap;">${message}</p>
            </div>
            <div style="padding: 12px 20px; border-top: 1px solid #e5e7eb; display: flex; justify-content: flex-end; gap: 10px; flex-shrink: 0;">
                <button type="button" class="xh-confirm-cancel" style="padding: 8px 16px; background: #f3f4f6; border: 1px solid #d1d5db; border-radius: 6px; color: #4b5563; font-size: 13px; font-weight: 500; cursor: pointer; transition: background 0.2s;">${cancelText}</button>
                <button type="button" class="xh-confirm-ok" style="padding: 8px 16px; background: linear-gradient(135deg, #4a00e0, #8e2de2); border: none; border-radius: 6px; color: white; font-size: 13px; font-weight: 500; cursor: pointer; transition: box-shadow 0.2s;">${confirmText}</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);

    const confirmOverlay = { overlay, onConfirm, onCancel };

    overlay.querySelector('.xh-confirm-cancel').addEventListener('click', () => {
        window.closeConfirm(confirmId);
        if (onCancel && typeof onCancel === 'function') onCancel();
    });

    overlay.querySelector('.xh-confirm-ok').addEventListener('click', () => {
        window.closeConfirm(confirmId);
        if (onConfirm && typeof onConfirm === 'function') onConfirm();
    });

    overlay.querySelector('.xh-confirm-close').addEventListener('click', () => {
        window.closeConfirm(confirmId);
        if (onCancel && typeof onCancel === 'function') onCancel();
    });

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            window.closeConfirm(confirmId);
            if (onCancel && typeof onCancel === 'function') onCancel();
        }
    });

    const styleId = 'confirm-styles-' + confirmId;
    const styleEl = document.createElement('style');
    styleEl.id = styleId;
    styleEl.textContent = `
        .xh-confirm-cancel:hover { background: #e5e7eb !important; }
        .xh-confirm-ok:hover { box-shadow: 0 4px 12px rgba(142, 45, 226, 0.4) !important; }
    `;
    document.head.appendChild(styleEl);

    window._confirmStyles = window._confirmStyles || {};
    window._confirmStyles[confirmId] = styleId;

    window._confirmOverlays = window._confirmOverlays || {};
    window._confirmOverlays[confirmId] = { overlay, onConfirm, onCancel };

    return confirmId;
}

window.closeConfirm = function(confirmId) {
    const confirmOverlay = window._confirmOverlays?.[confirmId];
    if (confirmOverlay) {
        confirmOverlay.overlay.remove();
        delete window._confirmOverlays[confirmId];
    }
    const styleId = window._confirmStyles?.[confirmId];
    if (styleId) {
        const styleEl = document.getElementById(styleId);
        if (styleEl) styleEl.remove();
        delete window._confirmStyles[confirmId];
    }
};

function toggleCard(header) {
    const body = header?.nextElementSibling;
    const icon = header?.querySelector('i');
    if (!body || !icon) return;
    body.classList.toggle('open');
    icon.className = body.classList.contains('open') ? 'fas fa-chevron-up' : 'fas fa-chevron-down';
}

function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}

function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/"/g, '&quot;').replace(/\n/g, '&#10;');
}

function createCRUDManager(options) {
    const {
        apiPath,
        containerId,
        renderFn,
        loadBtnId = 'loadBtn',
        saveBtnId = 'saveBtn',
        onLoadSuccess,
        onSaveSuccess,
        onError,
        transformBeforeSave = (data) => data
    } = options;

    let globalData = null;

    async function load() {
        try {
            const response = await axios.get(apiPath);
            globalData = response.data;
            renderFn(response.data);
            if (onLoadSuccess) onLoadSuccess(response.data);
            else showStatus('配置加载成功', 'success');
        } catch (error) {
            const msg = error.response?.data?.detail || error.message;
            if (onError) onError(msg);
            else showStatus(`加载失败: ${msg}`, 'error');
        }
    }

    async function save() {
        if (!globalData) {
            showStatus('请先加载配置', 'error');
            return;
        }

        try {
            const dataToSave = transformBeforeSave(globalData);
            const response = await axios.post(apiPath, dataToSave);
            if (onSaveSuccess) onSaveSuccess(response.data);
            else showStatus(`保存成功: ${response.data.message || '操作完成'}`, 'success');
        } catch (error) {
            const msg = error.response?.data?.detail || error.message;
            if (onError) onError(msg);
            else showStatus(`保存失败: ${msg}`, 'error');
        }
    }

    function init() {
        const loadBtn = document.getElementById(loadBtnId);
        const saveBtn = document.getElementById(saveBtnId);

        loadBtn?.addEventListener('click', load);
        saveBtn?.addEventListener('click', save);

        loadBtn?.click();
    }

    return {
        load,
        save,
        init,
        getData: () => globalData,
        setData: (data) => { globalData = data; }
    };
}

function convertValueByType(key, value, typeMap) {
    const typeConfig = typeMap[key];
    if (!typeConfig) return value;

    const targetType = typeof typeConfig === 'string' ? typeConfig : typeConfig.type;

    if (targetType === 'number') {
        const numValue = parseInt(value, 10);
        return isNaN(numValue) ? 0 : numValue;
    } else if (targetType === 'boolean') {
        return value === true || value === 'true';
    } else if (targetType === 'array') {
        if (Array.isArray(value)) {
            return value;
        } else if (typeof value === 'string') {
            const trimmed = value.trim();
            if (!trimmed) return [];
            if (key === 'tags') {
                return trimmed.split(',').map(s => s.trim()).filter(s => s);
            } else {
                return trimmed.split('\n').map(s => s.trim()).filter(s => s);
            }
        }
        return [];
    } else if (targetType === 'object') {
        if (typeof value === 'object' && value !== null) {
            return value;
        } else if (typeof value === 'string') {
            try {
                return JSON.parse(value);
            } catch {
                return {};
            }
        }
        return {};
    }
    return value;
}

function getFieldLabel(fieldName, fieldLabels = promptFieldLabels) {
    return fieldLabels[fieldName] || promptFieldLabels[fieldName] || fieldName;
}

function parseBackendError(errorDetail, fieldLabels = null) {
    if (!errorDetail) return null;

    const fieldRegex = /'([^']+)'/g;
    const matches = errorDetail.match(fieldRegex);

    if (matches) {
        matches.forEach(match => {
            const fieldName = match.replace(/'/g, '');
            const label = getFieldLabel(fieldName, fieldLabels);
            if (label !== fieldName) {
                errorDetail = errorDetail.replace(new RegExp(`'${fieldName}'`, 'g'), `「${label}」`);
            }
        });
    }

    const typeRegex = /(int|float|bool|array|object|string)/gi;
    const typeMap = {
        'int': '数字',
        'float': '数字',
        'bool': '布尔值',
        'array': '数组',
        'object': '对象',
        'string': '字符串'
    };
    errorDetail = errorDetail.replace(typeRegex, (match) => typeMap[match.toLowerCase()] || match);

    return errorDetail;
}

function normalizeData(items, typeMap) {
    return items.map(item => {
        const normalized = { ...item };
        Object.keys(typeMap).forEach(key => {
            normalized[key] = convertValueByType(key, normalized[key], typeMap);
        });
        return normalized;
    });
}

const promptFieldLabels = {
    id: 'ID',
    name: '名称',
    type: '类型',
    version: '版本',
    index: '序号',
    enabled: '启用状态',
    meta_constitution_injected: '元规则注入',
    description: '描述',
    role: '角色',
    information_source: '信息源',
    rules: '规则',
    params: 'LLM 参数',
    output_key: '输出键名',
    output_schema: '输出结构',
    output_prefix: '输出前缀',
    output_suffix: '输出后缀',
    empty_result_fallback: '空结果回退',
    tags: '标签',
    changelog: '更新日志'
};

const daoFieldLabels = {
    title: '标题',
    version: '版本',
    statement: '道之宣言',
    elaboration: '道之阐释',
    ontological_axioms: '本体论公理',
    supreme_directive: '最高指令'
};

const ruleFieldLabels = {
    half_to_full: '半角转全角映射',
    invalid_punctuation_patterns: '无效标点模式',
    missing_space_patterns: '缺少空格模式',
    wrong_punctuation_patterns: '错误标点模式',
    patterns: '正则模式',
    sentence: '句子模式',
    word: '词语模式',
    chinese: '中文模式',
    email: '邮箱模式',
    phone: '电话模式',
    url: 'URL模式',
    thresholds: '阈值配置',
    max_sentence_length: '最大句子长度',
    min_sentence_length: '最小句子长度',
    repeated_word_min_length: '重复词最小长度',
    repeated_word_min_count: '重复词最小次数',
    repeated_phrase_min_length: '重复短语最小长度',
    repeated_phrase_max_length: '重复短语最大长度',
    repeated_phrase_limit: '重复短语限制',
    max_paragraph_length: '最大段落长度',
    min_paragraph_length: '最小段落长度',
    repeated_phrase_ngram_min: 'N-Gram最小',
    repeated_phrase_ngram_max: 'N-Gram最大',
    readability: '可读性配置',
    readability_fallback: '可读性兜底配置',
    readability_chinese_bonus: '中文可读性加成',
    readability_chinese_ratio_threshold: '中文比例阈值',
    paragraph_splitter: '段落分割配置',
    min_chars: '最小字符数',
    target_chars: '目标字符数',
    char_tolerance: '字符容差',
    style_checks: '风格检查',
    passive_voice_patterns: '被动语态模式',
    wordiness_patterns: '冗余表达模式',
    buzzword_patterns: '流行术语',
    wrong_characters: '错别字映射',
    similar_characters: '相似字映射',
    common_errors: '常见错误',
    de_fix_pairs: '的/地/得修正',
    min: '最小值',
    max: '最大值',
    score: '分数',
    level: '级别',
    suggestion: '建议'
};

const promptTypeMap = {
    index: { type: 'number', label: '序号' },
    enabled: { type: 'boolean', label: '启用状态' },
    meta_constitution_injected: { type: 'boolean', label: '元规则注入' },
    rules: { type: 'array', label: '规则' },
    params: { type: 'object', label: 'LLM 参数' },
    output_schema: { type: 'object', label: '输出结构' },
    output_prefix: { type: 'array', label: '输出前缀' },
    output_suffix: { type: 'array', label: '输出后缀' },
    tags: { type: 'array', label: '标签' },
    changelog: { type: 'array', label: '更新日志' }
};

function createPromptDataManager(dataRef, typeMap = promptTypeMap) {
    return {
        update(index, key, value) {
            if (!dataRef.current?.prompts) return;
            if (index >= dataRef.current.prompts.length) return;
            dataRef.current.prompts[index][key] = convertValueByType(key, value, typeMap);
        },
        normalize() {
            if (!dataRef.current?.prompts) return dataRef.current;
            return {
                ...dataRef.current,
                prompts: normalizeData(dataRef.current.prompts, typeMap)
            };
        }
    };
}

window.onerror = function(message, source, lineno, colno, error) {
  console.error('[全局错误]', message, 'at', source, lineno, colno, error);
  showStatus('系统发生错误，请刷新页面重试', 'error');
  return true;
};

window.addEventListener('unhandledrejection', function(event) {
  console.error('[未捕获Promise异常]', event.reason);
  showStatus('系统发生异步错误，请刷新页面重试', 'error');
});

function safeExecute(fn, errorMessage) {
  try {
    return fn();
  } catch (error) {
    console.error('[安全执行]', errorMessage, error);
    showStatus(errorMessage || '操作失败，请重试', 'error');
    return null;
  }
}

window.safeExecute = safeExecute;
window.showStatus = showStatus;
window.showConfirm = showConfirm;
window.closeConfirm = window.closeConfirm;
window.showMessage = showMessage;
window.hideResult = hideResult;
window.showResult = showResult;
window.hideError = hideError;
window.showError = showError;
window.updateSSEStatus = updateSSEStatus;
window.addLog = addLog;
window.formatSSEMessage = formatSSEMessage;
window.parseSSEEvent = parseSSEEvent;
window.getEventTypeIcon = getEventTypeIcon;
window.connectGlobalSSE = connectGlobalSSE;
window.listenSSE = listenSSE;
window.toggleCard = toggleCard;
window.escapeHtml = escapeHtml;
window.esc = esc;
window.createCRUDManager = createCRUDManager;
window.convertValueByType = convertValueByType;
window.normalizeData = normalizeData;
window.promptTypeMap = promptTypeMap;
window.promptFieldLabels = promptFieldLabels;
window.daoFieldLabels = daoFieldLabels;
window.ruleFieldLabels = ruleFieldLabels;
window.createPromptDataManager = createPromptDataManager;
window.getFieldLabel = getFieldLabel;
window.parseBackendError = parseBackendError;
window.renderProgressBar = renderProgressBar;

(function setupAxiosGuard() {
  if (!window.axios || window.__axiosNavGuardInstalled) return;
  window.__axiosNavGuardInstalled = true;

  const controllers = new Set();
  axios.defaults.timeout = 10000;

  const MAX_PARALLEL = 4;
  const sem = {
    running: 0,
    queue: []
  };

  function semRelease() {
    if (sem.running > 0) sem.running--;
    if (sem.running < 0) sem.running = 0;
    semTryFlush();
  }

  function semTryFlush() {
    while (sem.running < MAX_PARALLEL && sem.queue.length > 0) {
      const next = sem.queue.shift();
      sem.running++;
      next._started = true;
      try {
        next.resolve(next.config);
      } catch (e) {
        semRelease();
        try { next.reject(e); } catch (_) {}
      }
    }
  }

  axios.interceptors.request.use((config) => {
    if (!config.signal) {
      try {
        const ctrl = new AbortController();
        config.signal = ctrl.signal;
        controllers.add(ctrl);
        config.__ctrlRef = ctrl;
      } catch (e) {}
    }
    return new Promise((resolve, reject) => {
      const q = {
        resolve,
        reject,
        ctrl: config.__ctrlRef || null,
        config,
        _started: false
      };
      sem.queue.push(q);
      semTryFlush();
    }).then((c) => c, (err) => {
      const q = sem.__lastCanceledQueueItem;
      if (q && q._started) {
        semRelease();
        sem.__lastCanceledQueueItem = null;
      }
      return Promise.reject(err);
    });
  });

  axios.interceptors.response.use(
    (resp) => {
      if (resp && resp.config && resp.config.__ctrlRef) {
        controllers.delete(resp.config.__ctrlRef);
      }
      semRelease();
      return resp;
    },
    (err) => {
      if (err && err.config && err.config.__ctrlRef) {
        controllers.delete(err.config.__ctrlRef);
      }
      const isCancel = !!(
        (axios.isCancel && axios.isCancel(err)) ||
        (err && (err.__CANCEL__ || err.code === 'ERR_CANCELED' || err.name === 'CanceledError' || (err.message && String(err.message).indexOf('abort') !== -1)))
      );
      if (isCancel) {
        try { err.__isCancel = true; } catch (_) {
          const wrapped = new Error((err && err.message) || 'Canceled');
          wrapped.__isCancel = true;
          wrapped.__cause = err;
          err = wrapped;
        }
      }
      semRelease();
      return Promise.reject(err);
    }
  );

  function buildAbortError(reason) {
    try {
      if (axios.Cancel) return new axios.Cancel(reason || 'aborted');
    } catch (_) {}
    const e = new Error(reason || 'aborted');
    e.__CANCEL__ = true;
    return e;
  }

  function abortAllPending() {
    const head = sem.queue.slice();
    sem.queue = [];
    for (const q of head) {
      try {
        if (q.ctrl) {
          try { q.ctrl.abort('navigation-abort'); } catch (_) {}
          controllers.delete(q.ctrl);
        }
        if (q._started) {
          sem.__lastCanceledQueueItem = q;
        }
        try { q.reject(buildAbortError('navigation-abort')); } catch (_) {}
      } catch (_) {}
    }
    if (!controllers.size) return;
    const snapshot = Array.from(controllers);
    controllers.clear();
    for (const ctrl of snapshot) {
      try { ctrl.abort('navigation-abort'); } catch (e) {}
    }
  }

  window.abortAllAxiosRequests = abortAllPending;
  window.addEventListener('beforeunload', abortAllPending);
  window.addEventListener('pagehide', abortAllPending);
})();

(function setupAppCache() {
  const PREFIX = 'xinhai_cache_v1_';
  const VERSION = 2;

  function fullKey(k) { return PREFIX + k; }

  function cacheGet(key) {
    try {
      const raw = localStorage.getItem(fullKey(key));
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || parsed.v !== VERSION) return null;
      const { ttl, ts, data } = parsed;
      if (ttl > 0 && Date.now() - ts > ttl * 1000) return null;
      return data;
    } catch (_) { return null; }
  }

  function cacheSet(key, data, ttlSeconds) {
    const ttl = typeof ttlSeconds === 'number' ? ttlSeconds : 300;
    try {
      const payload = { v: VERSION, ttl, ts: Date.now(), data };
      localStorage.setItem(fullKey(key), JSON.stringify(payload));
      return true;
    } catch (_) {
      try { cacheClear(); } catch (__) {}
      return false;
    }
  }

  function cacheInvalidate() {
    const keys = Array.prototype.slice.call(arguments);
    for (const k of keys) {
      try { localStorage.removeItem(fullKey(k)); } catch (_) {}
    }
  }

  function cacheClear() {
    const toRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.indexOf(PREFIX) === 0) toRemove.push(k);
    }
    for (const k of toRemove) localStorage.removeItem(k);
  }

  async function swrFetch(url, options) {
    const opts = options || {};
    const method = (opts.fetchOptions && opts.fetchOptions.method) || 'GET';
    const ttl = typeof opts.ttl === 'number' ? opts.ttl : 300;
    const cacheKey = method + ':' + url;
    const cached = cacheGet(cacheKey);
    const doFetch = async () => {
      const resp = await fetch(url, opts.fetchOptions || {});
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const json = await resp.json();
      cacheSet(cacheKey, json, ttl);
      return json;
    };
    if (cached !== null) {
      setTimeout(() => { doFetch().catch(() => {}); }, 0);
      return cached;
    }
    return doFetch();
  }

  window.AppCache = {
    TTL_STATIC: 3600,
    TTL_CONFIG: 1800,
    TTL_DEFAULT: 300,
    get: cacheGet,
    set: cacheSet,
    invalidate: cacheInvalidate,
    clear: cacheClear,
    swrFetch: swrFetch,
    cacheKeyOf(url, method) { return (method || 'GET') + ':' + url; }
  };
})();

(function setupLazyBackground() {
  let observer = null;
  function ensureObserver() {
    if (observer) return observer;
    if (typeof IntersectionObserver === 'undefined') return null;
    observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const el = entry.target;
        const bg = el.getAttribute && el.getAttribute('data-bg');
        if (bg) {
          el.style.backgroundImage = "url('" + bg.replace(/'/g, "%27") + "')";
          el.removeAttribute('data-bg');
        }
        observer.unobserve(el);
      }
    }, { rootMargin: '200px 0px', threshold: 0 });
    return observer;
  }

  function observe(container) {
    const root = container || document;
    if (!root || !root.querySelectorAll) return;
    const obs = ensureObserver();
    const nodes = root.querySelectorAll('[data-bg]:not([data-bg=""])');
    if (!obs) {
      for (let i = 0; i < nodes.length; i++) {
        const el = nodes[i];
        const bg = el.getAttribute('data-bg');
        if (bg) el.style.backgroundImage = "url('" + bg.replace(/'/g, "%27") + "')";
      }
      return;
    }
    for (let i = 0; i < nodes.length; i++) obs.observe(nodes[i]);
  }

  window.LazyBackground = { observe };
})();