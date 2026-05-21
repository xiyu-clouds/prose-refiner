function connectGlobalSSE() {
    if (window.__globalSSE && window.__globalSSE.readyState !== EventSource.CLOSED) {
        return window.__globalSSE;
    }

    const es = new EventSource('/api/sse-proxy');
    window.__globalSSE = es;

    const events = [
        'connection_start', 'task_started', 'preprocessing_progress',
        'pipeline_progress', 'metacognition_progress', 'task_completed',
        'task_failed', 'connection_close', 'human_intervention_required'
    ];

    events.forEach(type => {
        es.addEventListener(type, (e) => {
            try {
                const data = JSON.parse(e.data);
                window.dispatchEvent(new CustomEvent('psytext:' + type, { detail: data }));
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

const stageMap = {
    'connection_start': '连接阶段',
    'connection_close': '连接阶段',
    'task_started': '任务启动',
    'preprocessing_progress': '预处理阶段',
    'pipeline_progress': '流程阶段',
    'metacognition_progress': '元认知阶段',
    'task_completed': '任务完成',
    'task_failed': '任务失败',
    'serial_adaptation': '场景适配',
    'serial_preprocessing': '预处理',
    'parallel_analysis': '并行分析',
    'serial_aggregation': '聚合处理',
    'serial_polish': '润色阶段',
    'serial_enhance': '增强阶段'
};

const statusMap = {
    'start': '开始',
    'running': '执行中',
    'completed': '完成',
    'failed': '失败'
};

const levelMap = {
    'full_text': '全文级',
    'paragraph': '段落级'
};

function getEventTypeIcon(eventType) {
    const iconMap = {
        'connection_start': '🌐',
        'connection_close': '🌐',
        'task_started': '🚀',
        'preprocessing_progress': '📝',
        'pipeline_progress': '⚙️',
        'metacognition_progress': '🧠',
        'task_completed': '✅',
        'task_failed': '❌'
    };
    return iconMap[eventType] || '📌';
}

function getLogType(eventType, rawStatus) {
    if (eventType === 'connection_start') return 'success';
    if (eventType === 'task_completed') return 'success';
    if (eventType === 'task_failed') return 'error';
    if (rawStatus === 'completed') return 'success';
    if (rawStatus === 'failed') return 'error';
    return 'info';
}

function parseSSEEvent(data) {
    if (typeof data === 'string') {
        return JSON.parse(data);
    }
    return data;
}

function formatSSEMessage(eventType, data) {
    const parsedData = parseSSEEvent(data);
    const { title, content, task_id, meta } = parsedData;
    const rawStage = meta?.stage || '';
    const rawStatus = meta?.status || '';
    const rawLevel = meta?.level || '';

    const stage = stageMap[rawStage] || rawStage;
    const status = statusMap[rawStatus] || rawStatus;
    const level = levelMap[rawLevel] || rawLevel;

    const parts = [];
    if (title) parts.push(title);
    if (content) parts.push(content);
    if (level) parts.push(level);
    if (stage) parts.push(stage);
    if (status) parts.push(status);

    let message = parts.join(' | ');
    if (task_id) {
        message += ` | ID:${task_id}`;
    }

    const icon = getEventTypeIcon(eventType);
    const logType = getLogType(eventType, rawStatus);

    return { message: `${icon} ${message}`, logType, task_id, title, status };
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

    logLine.textContent = `[${timestamp}] ${message}`;
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

function showSSENotification(message) {
    let notifContainer = document.getElementById('sse-notifications');
    if (!notifContainer) {
        notifContainer = document.createElement('div');
        notifContainer.id = 'sse-notifications';
        notifContainer.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 10001; max-width: 300px;';
        document.body.appendChild(notifContainer);
    }

    const notif = document.createElement('div');
    notif.style.cssText = 'background: #fff; border-left: 4px solid #8e2de2; padding: 12px 16px; margin-bottom: 8px; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); font-size: 14px; animation: fadeIn 0.3s ease;';
    notif.innerHTML = message;
    notifContainer.appendChild(notif);

    setTimeout(() => {
        notif.style.animation = 'fadeOut 0.3s ease';
        setTimeout(() => notif.remove(), 300);
    }, 5000);
}

function showInterventionModal(data) {
    const existingModal = document.getElementById('intervention-modal');
    if (existingModal) {
        existingModal.remove();
    }

    const modal = document.createElement('div');
    modal.id = 'intervention-modal';
    modal.innerHTML = `
        <div class="intervention-overlay" onclick="closeInterventionModal()"></div>
        <div class="intervention-content">
            <h3>⚠️ 需要人为干预</h3>
            <div class="intervention-info">
                <p><strong>任务ID:</strong> ${data.task_id || '未知'}</p>
                <p><strong>时间:</strong> ${new Date(data.timestamp ? data.timestamp * 1000 : Date.now()).toLocaleString()}</p>
                <p><strong>提示:</strong> ${data.content || data.title || '请补充所需信息'}</p>
            </div>
            <textarea id="clarification-input" placeholder="请输入需要补充的信息..."></textarea>
            <div class="intervention-actions">
                <button onclick="resumeTask('${data.task_id}')">恢复执行</button>
                <button onclick="closeInterventionModal()">关闭</button>
            </div>
        </div>
    `;

    const style = document.createElement('style');
    style.textContent = `
        @keyframes fadeIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes fadeOut { from { opacity: 1; } to { opacity: 0; } }
        #intervention-modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 9999;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .intervention-overlay {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
        }
        .intervention-content {
            position: relative;
            background: white;
            border-radius: 12px;
            padding: 24px;
            width: 90%;
            max-width: 500px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
        }
        .intervention-content h3 {
            margin: 0 0 16px 0;
            color: #d9534f;
            font-size: 18px;
        }
        .intervention-info {
            background: #f8f9fa;
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 16px;
        }
        .intervention-info p {
            margin: 6px 0;
            font-size: 14px;
            color: #333;
        }
        #clarification-input {
            width: 100%;
            height: 120px;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 14px;
            resize: vertical;
            box-sizing: border-box;
            margin-bottom: 16px;
        }
        .intervention-actions {
            display: flex;
            gap: 12px;
            justify-content: flex-end;
        }
        .intervention-actions button {
            padding: 10px 24px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .intervention-actions button:first-child {
            background: #6a5af9;
            color: white;
        }
        .intervention-actions button:first-child:hover {
            background: #5a4ad9;
        }
        .intervention-actions button:last-child {
            background: #e0e0e0;
            color: #333;
        }
        .intervention-actions button:last-child:hover {
            background: #d0d0d0;
        }
    `;
    document.head.appendChild(style);
    document.body.appendChild(modal);
}

function closeInterventionModal() {
    const modal = document.getElementById('intervention-modal');
    if (modal) {
        modal.remove();
    }
}

function showStatus(options, type) {
    let message, statusType = 'info', duration = 3000, containerId = 'statusBox', container = null;

    if (typeof options === 'string') {
        message = options;
        statusType = type || 'info';
    } else {
        message = options.message;
        statusType = options.type || 'info';
        duration = options.duration || 3000;
        containerId = options.containerId || 'statusBox';
        container = options.container || null;
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

async function resumeTask(taskId) {
    const input = document.getElementById('clarification-input');
    const clarification = input?.value?.trim() || '';

    if (!clarification) {
        showStatus('请输入需要补充的信息', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/resume/${taskId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ user_clarification: clarification })
        });

        const result = await response.json();
        if (response.ok) {
            closeInterventionModal();
            addLog(`[INFO] 任务 ${taskId} 已恢复执行`, 'success');
            showStatus('任务已恢复执行', 'success');
        } else {
            showStatus('恢复失败: ' + result.message, 'error');
        }
    } catch (error) {
        console.error('恢复任务失败:', error);
        showStatus('恢复任务失败，请重试', 'error');
    }
}

function initSSEForNotifications() {
    connectGlobalSSE();

    const events = [
        'task_started', 'task_completed', 'task_failed',
        'preprocessing_progress', 'pipeline_progress',
        'metacognition_progress', 'human_intervention_required'
    ];

    events.forEach(eventType => {
        listenSSE(eventType, (data) => {
            if (window.TaskNotifications) {
                const { title, status } = formatSSEMessage(eventType, data);
                if (title) {
                    window.TaskNotifications.add(title, status);
                }
            }
        });
    });

    listenSSE('connection_start', () => {
        if (window.TaskNotifications) {
            window.TaskNotifications.add('SSE 连接已建立', 'connected');
        }
    });
}


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

window.showStatus = showStatus;
window.resumeTask = resumeTask;
window.showConfirm = showConfirm;
window.closeInterventionModal = closeInterventionModal;
window.initSSEForNotifications = initSSEForNotifications;
window.showInterventionModal = showInterventionModal;
window.showSSENotification = showSSENotification;
window.hideResult = hideResult;
window.showResult = showResult;
window.hideError = hideError;
window.showError = showError;
window.showMessage = showMessage;
window.updateSSEStatus = updateSSEStatus;
window.addLog = addLog;
window.formatSSEMessage = formatSSEMessage;
window.parseSSEEvent = parseSSEEvent;
window.getLogType = getLogType;
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