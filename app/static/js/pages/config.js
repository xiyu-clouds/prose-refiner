(function () {
    const statusBox = document.getElementById('statusBox');
    let globalConfigData = null;
    let statusQueue = [];
    let statusTimer = null;

    function processStatusQueue() {
        if (statusQueue.length === 0) {
            statusTimer = null;
            return;
        }
        const { message, type, timeout } = statusQueue.shift();
        statusBox.textContent = message;
        statusBox.style.display = 'block';
        statusBox.style.background = type === 'success' ? '#28a745' : (type === 'error' ? '#dc3545' : '#6c757d');

        if (statusTimer) clearTimeout(statusTimer);
        statusTimer = setTimeout(() => {
            statusBox.style.display = 'none';
            processStatusQueue();
        }, timeout);
    }

    function showStatus(message, type = 'info', timeout = 3000) {
        if (!statusBox) return;
        if (timeout === 3000) {
            timeout = type === 'success' ? 5000 : (type === 'error' ? 8000 : 5000);
        }
        statusQueue.push({ message, type, timeout });
        if (!statusTimer) processStatusQueue();
    }

    let vendorModelData = { vendor_by_domain: {}, model_by_domain_vendor: {} };
    let reasoningTypes = [];
    let reasoningAutoInject = false;

    async function fetchVendorModel() {
        try {
            const data = await AppCache.swrFetch('/api/vendor-model', { ttl: AppCache.TTL_STATIC });
            vendorModelData = {
                vendor_by_domain: data.vendor_by_domain || {},
                model_by_domain_vendor: data.model_by_domain_vendor || {}
            };
        } catch (error) {
            console.error('获取厂商和模型失败:', error);
            vendorModelData = { vendor_by_domain: {}, model_by_domain_vendor: {} };
        }
    }

    async function fetchReasoningTypes() {
        try {
            const data = await AppCache.swrFetch('/api/reasoning-types', { ttl: AppCache.TTL_CONFIG });
            // 后端返回 {types: [{id: "extract_session_memory", name: "创作设定提取"}, ...]}
            const rawTypes = data.types || [];
            reasoningTypes = rawTypes.map(t => typeof t === 'object' ? t : { id: t, name: t });
            // 空数据不长期缓存：失效 SWR，下次访问强制重新拉取（自愈，避免旧空数据卡 30 分钟 TTL）
            if (reasoningTypes.length === 0 && window.AppCache && typeof AppCache.invalidate === 'function') {
                AppCache.invalidate('/api/reasoning-types');
            }
        } catch (error) {
            console.error('获取推理类型失败:', error);
            reasoningTypes = [];
        }
    }

    const CONFIG_SECTIONS = [
        {
            name: '厂商密钥',
            fields: [
                { key: 'XINHAI_DEEPSEEK_API_KEY', type: 'password', label: 'DeepSeek 密钥', sensitive: true, placeholder: '请输入密钥' },
                { key: 'XINHAI_TONGYI_API_KEY', type: 'password', label: '通义密钥', sensitive: true, placeholder: '请输入密钥（文本/音频/图像共用）' }
            ]
        },
        {
            name: '文本生成配置',
            fields: [
                { key: 'XINHAI_TEXT_DEFAULT_VENDOR', type: 'vendor_select', label: '模型提供商', domain: 'text' },
                { key: 'XINHAI_TEXT_DEFAULT_MODEL', type: 'model_select', label: '模型名称', domain: 'text' },
                { key: 'XINHAI_TEXT_API_TIMEOUT', type: 'number', label: '文本超时时间（秒）' },
                { key: 'XINHAI_TEXT_PARAMS', type: 'json', label: '文本参数', rows: 5, fullWidth: true },
                { key: 'XINHAI_MAX_TOKENS_EXPANSION_FACTOR', type: 'float', label: '推理模型输出Token扩容比率' },
                { key: 'XINHAI_FULL_TEXT_TOKENS_RATIO', type: 'float', label: '基础max_token扩容比率' },
                { key: 'XINHAI_MAX_LENGTH_RETRIES', type: 'number', label: '自动扩容的最大重试次数' },
                { key: 'XINHAI_FACTOR_INCREMENT', type: 'float', label: '自动扩容每次重试时增加的比率值' },
                { key: 'XINHAI_REASONING_AUTO_INJECT', type: 'bool', label: '是否开启推理模式' },
                { key: 'XINHAI_REASONING_EFFORT_MAP', type: 'reasoning_effort', label: '各能力推理强度配置', fullWidth: true }
            ]
        },
        {
            name: '音频生成配置',
            fields: [
                { key: 'XINHAI_AUDIO_DEFAULT_VENDOR', type: 'vendor_select', label: '音频厂商', domain: 'audio_tts' },
                { key: 'XINHAI_AUDIO_DEFAULT_MODEL', type: 'model_select', label: '音频模型', domain: 'audio_tts' }
            ]
        },
        {
            name: '图像生成配置',
            fields: [
                { key: 'XINHAI_IMAGE_DEFAULT_VENDOR', type: 'vendor_select', label: '图像厂商', domain: 'image' },
                { key: 'XINHAI_IMAGE_DEFAULT_MODEL', type: 'model_select', label: '图像模型', domain: 'image' }
            ]
        },
        {
            name: '本地轻量模型管理',
            fields: [
                { key: 'XINHAI_LOCAL_MODEL_MAX_MEMORY_MB', type: 'number', label: '进程内存上限（MB）' },
                { key: 'XINHAI_LOCAL_MODEL_MONITOR_INTERVAL', type: 'number', label: '内存监控间隔（秒）' },
                { key: 'XINHAI_LOCAL_MODEL_MEMORY_THRESHOLD', type: 'float', label: '内存告警阈值（比例，如 0.9）' },
                { key: 'XINHAI_LOCAL_MODEL_MAX_EVICTION_ATTEMPTS', type: 'number', label: '最大连续卸载尝试次数' },
                { key: 'XINHAI_LOCAL_MODEL_CONCURRENCY', type: 'number', label: '本地模型推理最大并发数' },
                { key: 'XINHAI_ENABLE_TEXT_ANALYSIS_TASKS', type: 'bool', label: '默认启用本地文本模型分析' },
                { key: 'XINHAI_TEXT_ANALYSIS_TASKS', type: 'list', label: '文本分析任务列表', hint: '逗号分隔' },
                { key: 'XINHAI_LOCAL_MODELS_DEFINITION', type: 'model_definition_list', label: '模型定义列表', fullWidth: true }
            ]
        },
        {
            name: '并发控制',
            fields: [
                { key: 'XINHAI_MAX_LLM_STEP_CONCURRENCY', type: 'number', label: '全局最大LLM并行数' },
                { key: 'XINHAI_CURRENT_LLM_STEP_CONCURRENCY', type: 'number', label: '当前环境的LLM并行数' },
                { key: 'XINHAI_MEDIUM_LLM_STEP_CONCURRENCY', type: 'number', label: '推荐的中等LLM并行数' },
                { key: 'XINHAI_MAX_BATCH_TASK_CONCURRENCY', type: 'number', label: '批量任务最大并行数' },
                { key: 'XINHAI_CURRENT_BATCH_TASK_CONCURRENCY', type: 'number', label: '当前环境的批量任务并行数' },
                { key: 'XINHAI_MEDIUM_BATCH_TASK_CONCURRENCY', type: 'number', label: '推荐的中等批量任务并行数' }
            ]
        },
        {
            name: '存储与缓存',
            fields: [
                { key: 'XINHAI_STORAGE_BACKEND', type: 'text', label: '存储后端类型', placeholder: 'redis / local' },
                { key: 'XINHAI_LLM_CACHE_MAX_SIZE', type: 'number', label: 'LLM缓存最大容量' },
                { key: 'XINHAI_LLM_CACHE_TTL', type: 'number', label: 'LLM缓存过期时间（秒）' },
                { key: 'XINHAI_REDIS_HOST', type: 'text', label: 'Redis主机地址', placeholder: '127.0.0.1' },
                { key: 'XINHAI_REDIS_PORT', type: 'number', label: 'Redis服务端口' },
                { key: 'XINHAI_REDIS_DB', type: 'number', label: 'Redis数据库索引' },
                { key: 'XINHAI_REDIS_PASSWORD', type: 'password', label: 'Redis访问密码', sensitive: true, placeholder: '请输入密码' },
                { key: 'XINHAI_REDIS_TIMEOUT', type: 'number', label: 'Redis操作超时时间（秒）' }
            ]
        },
        {
            name: '通知系统',
            fields: [
                { key: 'XINHAI_NOTIFICATION_ENABLED', type: 'bool', label: '是否启用消息通知' },
                { key: 'XINHAI_NOTIFICATION_CHANNELS', type: 'list', label: '启用的通知渠道列表', hint: '逗号分隔' },
                { key: 'XINHAI_EMAIL_SMTP_SERVER', type: 'text', label: '邮箱SMTP服务器地址', placeholder: '请输入邮箱SMTP服务器地址' },
                { key: 'XINHAI_EMAIL_PORT', type: 'number', label: '邮箱 SMTP 服务端口' },
                { key: 'XINHAI_EMAIL_USERNAME', type: 'text', label: '发件邮箱账号', placeholder: '请输入发件邮箱账号' },
                { key: 'XINHAI_EMAIL_PASSWORD', type: 'password', label: '邮箱授权码', sensitive: true, placeholder: '请输入授权码' },
                { key: 'XINHAI_EMAIL_TO', type: 'list', label: '邮件接收人列表', hint: '逗号分隔', placeholder: '请输入邮件接收人列表' },
                { key: 'XINHAI_FEISHU_WEBHOOK_URL', type: 'text', label: '飞书Webhook地址', placeholder: '请输入飞书Webhook地址' },
                { key: 'XINHAI_FEISHU_AT_USER_IDS', type: 'list', label: '飞书@用户ID列表', hint: '逗号分隔', placeholder: '请输入飞书@用户ID列表' },
                { key: 'XINHAI_WECOM_WEBHOOK_URL', type: 'text', label: '企业微信Webhook地址', placeholder: '请输入企业微信的Webhook地址' },
                { key: 'XINHAI_WECOM_AT_USER_IDS', type: 'list', label: '企业微信@用户ID 列表', hint: '逗号分隔', placeholder: '请输入企业微信@用户ID列表' }
            ]
        },
        {
            name: '图片平台',
            fields: [
                { key: 'XINHAI_UNSPLASH_ACCESS_KEY', type: 'password', label: 'Unsplash图片平台密钥', sensitive: true, placeholder: '请输入密钥' },
                { key: 'XINHAI_UNSPLASH_BASIC_PATH', type: 'text', label: 'Unsplash接口基础路径', placeholder: 'https://api.unsplash.com' },
                { key: 'XINHAI_PEXELS_ACCESS_KEY', type: 'password', label: 'Pexels图片平台密钥', sensitive: true, placeholder: '请输入密钥' },
                { key: 'XINHAI_PEXELS_BASIC_PATH', type: 'text', label: 'Pexels接口基础路径', placeholder: 'https://api.pexels.com' }
            ]
        },
        {
            name: 'LangSmith 可观测性',
            fields: [
                { key: 'XINHAI_LANGSMITH_ENABLED', type: 'bool', label: '是否启用LangSmith追踪' },
                { key: 'XINHAI_LANGSMITH_API_KEY', type: 'password', label: 'LangSmith API 密钥', sensitive: true, placeholder: '请输入密钥' },
                { key: 'XINHAI_LANGSMITH_PROJECT', type: 'text', label: 'LangSmith项目名称', placeholder: 'my-prose-project' },
                { key: 'XINHAI_LANGSMITH_ENDPOINT', type: 'text', label: 'LangSmith服务端点', placeholder: 'https://api.smith.langchain.com' }
            ]
        },
        {
            name: '翻译API',
            fields: [
                { key: 'XINHAI_TENCENT_TMT_SECRET_ID', type: 'password', label: '腾讯云TMT SecretId', sensitive: true, placeholder: '请输入腾讯云SecretId' },
                { key: 'XINHAI_TENCENT_TMT_SECRET_KEY', type: 'password', label: '腾讯云TMT SecretKey', sensitive: true, placeholder: '请输入腾讯云SecretKey' }
            ]
        },
        {
            name: '运行监控 & 日志',
            fields: [
                { key: 'XINHAI_LOG_KEEP_DAYS', type: 'number', label: '日志保留天数' },
                { key: 'XINHAI_LOG_MAX_BYTES', type: 'number', label: '单个日志文件最大大小（字节）' },
                { key: 'XINHAI_LOG_BACKUP_COUNT', type: 'number', label: '日志备份保留数量' },
                { key: 'XINHAI_GLOBAL_ENABLE_METRICS', type: 'bool', label: '是否启用全局指标统计' },
                { key: 'XINHAI_GLOBAL_MAX_RETRIES', type: 'number', label: '全局最大重试次数' },
                { key: 'XINHAI_DEFAULT_RETRY_CONFIG', type: 'json', label: '全局默认重试策略配置', rows: 5, fullWidth: true },
                { key: 'XINHAI_PROXY_BACKEND_SSE_URL', type: 'text', label: 'SSE代理后端地址' },
                { key: 'XINHAI_SSE_HEARTBEAT_INTERVAL', type: 'number', label: 'SSE心跳间隔（秒）' },
            ]
        },
        {
            name: '文本处理与分析',
            fields: [
                { key: 'XINHAI_PARAGRAPH_TARGET_CHARS', type: 'number', label: '智能合并段落的目标字符数' },
                { key: 'XINHAI_PARAGRAPH_TOLERANCE', type: 'number', label: '智能合并段落的偏移量' },
                { key: 'XINHAI_PARAGRAPH_SPLIT_MIN_CHARS', type: 'number', label: '段落拆分器过短合并阈值' },
                { key: 'XINHAI_PARAGRAPH_SPLIT_TARGET_CHARS', type: 'number', label: '段落拆分器目标字符数' },
                { key: 'XINHAI_PARAGRAPH_SPLIT_SENTENCE_PATTERN', type: 'text', label: '段落拆分器句子结束正则' },
                { key: 'XINHAI_JIEBA_FILTER_STOPWORDS_DEFAULT', type: 'bool', label: '默认启用停用词过滤' },
                { key: 'XINHAI_JIEBA_MIN_WORD_LEN', type: 'number', label: '分词后保留的最小词长度' },
                { key: 'XINHAI_TEXTRANK_TOP_K', type: 'number', label: 'TextRank 提取关键词数量' },
                { key: 'XINHAI_VOCAB_FILTER_MAX_WORDS', type: 'number', label: '词库过滤时每个类别最多输出的词数' },
                { key: 'XINHAI_VOCAB_FILTER_MAX_FREQWORDS', type: 'number', label: '高频词最多输出的词数' },
                { key: 'XINHAI_SEMANTIC_SIMILARITY_THRESHOLD', type: 'float', label: '语义相似度阈值' }
            ]
        },
        {
            name: 'UI 与展示',
            fields: [
                { key: 'XINHAI_IMAGE_COUNT', type: 'number', label: '背景图片总数' },
                { key: 'XINHAI_REFRESH_INTERVAL_MS', type: 'number', label: '归墟页卡片背景刷新频率（毫秒）' },
                { key: 'XINHAI_HEADER_BG_IMAGE_ID', type: 'number', label: '头部背景图片ID' },
                { key: 'XINHAI_FOOTER_BG_IMAGE_ID', type: 'number', label: '底部背景图片ID' },
                { key: 'XINHAI_DEFAULT_BG_IMAGE_ID', type: 'number', label: '默认背景图片ID' },
                { key: 'XINHAI_NOVEL_BG_IMAGE_ID', type: 'number', label: '铸神页面背景图片ID' },
                { key: 'XINHAI_MESSAGE_WALL_BG_IMAGE_ID', type: 'number', label: '流萤页面背景图片ID' }
            ]
        }
    ];

    const FIELD_TYPE_MAP = {};
    const SENSITIVE_KEYS = new Set();
    CONFIG_SECTIONS.forEach(section => {
        section.fields.forEach(field => {
            FIELD_TYPE_MAP[field.key] = field.type;
            if (field.sensitive) SENSITIVE_KEYS.add(field.key);
        });
    });

    const SENSITIVE_TOKENS = new Set([
        'API_KEY', 'PASSWORD', 'SECRET', 'TOKEN'
    ]);
    function isSensitiveKey(key) {
        if (!key) return false;
        if (SENSITIVE_KEYS.has(key)) return true;
        const upper = String(key).trim().toUpperCase();
        const tokens = new Set(upper.split(/_+/).filter(Boolean));
        for (const t of SENSITIVE_TOKENS) {
            if (tokens.has(t)) return true;
        }
        return false;
    }

    const REASONING_EFFORTS = ['low', 'medium', 'high', 'max'];

    function isSensitivePlaceholder(value) {
        if (value === null || value === undefined) return true;
        const s = String(value).trim();
        if (!s) return true;
        return /^\*{3,}$/.test(s);
    }

    const PLACEHOLDER_RE_CN = /请(?:输入|填写|选择|设置|替换)/;
    const PLACEHOLDER_RE_EN = /<your[-_]|(?<![a-zA-Z])your[-_]|<todo>|(?<![a-zA-Z])todo(?![a-zA-Z])/i;
    function containsPlaceholder(value) {
        if (value === null || value === undefined) return false;
        if (typeof value === 'boolean' || typeof value === 'number') return false;
        if (typeof value === 'string') {
            const s = value.trim();
            if (!s) return false;
            return PLACEHOLDER_RE_CN.test(s) || PLACEHOLDER_RE_EN.test(s);
        }
        if (Array.isArray(value)) return value.some(containsPlaceholder);
        if (typeof value === 'object') return Object.values(value).some(containsPlaceholder);
        try {
            const s = String(value);
            return PLACEHOLDER_RE_CN.test(s) || PLACEHOLDER_RE_EN.test(s);
        } catch (e) {
            return false;
        }
    }

    function renderReasoningEffortField(inputId, key, value) {
        const effortMap = typeof value === 'object' && value !== null ? value : {};
        const disabled = !reasoningAutoInject;
        let html = `<div id="${inputId}" data-key="${key}" class="reasoning-effort-container">`;

        if (disabled) {
            html += `<div style="color: #999; font-size: 13px; margin-top: 8px;">⚠️ 请先开启「是否开启推理模式」才能配置各能力的推理等级</div>`;
        }

        html += `<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 10px;">`;

        reasoningTypes.forEach(type => {
            const typeId = type.id;
            const typeName = type.name || typeId;
            const isChecked = Object.prototype.hasOwnProperty.call(effortMap, typeId);
            const selectedEffort = isChecked ? effortMap[typeId] : 'medium';

            html += `
                <div style="display: flex; align-items: center; gap: 8px; padding: 8px 10px; background: #f8f9fa; border-radius: 6px; border: 1px solid #e9ecef;">
                    <label style="display: flex; align-items: center; gap: 6px; cursor: ${disabled ? 'not-allowed' : 'pointer'}; flex: 1; opacity: ${disabled ? 0.5 : 1};">
                        <input
                            type="checkbox"
                            class="reasoning-type-checkbox"
                            ${isChecked ? 'checked' : ''}
                            ${disabled ? 'disabled' : ''}
                            data-type="${window.esc(typeId)}"
                            style="width: 15px; height: 15px; cursor: ${disabled ? 'not-allowed' : 'pointer'};"
                        />
                        <span style="font-weight: 500; font-size: 13px; color: #444;">${window.esc(typeName)}</span>
                    </label>
                    <select
                        class="reasoning-effort-select form-control"
                        data-type="${window.esc(typeId)}"
                        ${!isChecked || disabled ? 'disabled' : ''}
                        style="width: 85px; font-size: 12px; padding: 5px 6px;"
                    >
                        ${REASONING_EFFORTS.map(effort =>
                            `<option value="${effort}" ${selectedEffort === effort ? 'selected' : ''}>${effort}</option>`
                        ).join('')}
                    </select>
                </div>
            `;
        });

        html += '</div></div>';
        return html;
    }

    function renderModelDefinitionList(inputId, key, value) {
        const models = Array.isArray(value) ? value : [];
        let html = `
            <div id="${inputId}" data-key="${key}" class="model-definition-container">
                <style>
                    .model-definition-container {
                        border: 1px solid #e9ecef;
                        border-radius: 6px;
                        padding: 12px;
                        background: #fafafa;
                    }
                    .model-definition-item {
                        background: #fff;
                        border: 1px solid #dee2e6;
                        border-radius: 6px;
                        padding: 12px;
                        margin-bottom: 10px;
                    }
                    .model-definition-item:last-child {
                        margin-bottom: 0;
                    }
                    .model-definition-header {
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 10px;
                        padding-bottom: 8px;
                        border-bottom: 1px dashed #e9ecef;
                    }
                    .model-definition-name {
                        font-weight: 600;
                        color: #495057;
                    }
                    .model-definition-fields {
                        display: grid;
                        grid-template-columns: repeat(3, 1fr);
                        gap: 12px;
                    }
                    .model-definition-field {
                        padding: 8px;
                    }
                    .model-definition-field label {
                        display: block;
                        font-size: 13px;
                        color: #6c757d;
                        margin-bottom: 5px;
                        font-weight: 500;
                    }
                    .model-definition-field input,
                    .model-definition-field textarea {
                        width: 100%;
                        padding: 8px 10px;
                        border: 1px solid #ced4da;
                        border-radius: 4px;
                        font-size: 14px;
                    }
                    .model-definition-field textarea {
                        min-height: 120px;
                        resize: vertical;
                    }
                </style>
        `;

        if (models.length === 0) {
            html += `<div style="text-align: center; color: #999; padding: 20px;">暂无模型定义</div>`;
        } else {
            models.forEach((model, index) => {
                const pipelineKwargs = typeof model.pipeline_kwargs === 'object'
                    ? JSON.stringify(model.pipeline_kwargs, null, 2)
                    : '';
                html += `
                    <div class="model-definition-item" data-index="${index}">
                        <div class="model-definition-header">
                            <span class="model-definition-name">📦 ${window.esc(model.name || '未命名模型')}</span>
                        </div>
                        <div class="model-definition-fields">
                            <div class="model-definition-field">
                                <label>名称</label>
                                <input type="text" class="model-def-input" data-field="name" value="${window.esc(model.name || '')}" disabled />
                            </div>
                            <div class="model-definition-field">
                                <label>模态类型</label>
                                <input type="text" class="model-def-input" data-field="modality" value="${window.esc(model.modality || '')}" disabled />
                            </div>
                            <div class="model-definition-field">
                                <label>加载器类型</label>
                                <input type="text" class="model-def-input" data-field="loader_type" value="${window.esc(model.loader_type || '')}" disabled />
                            </div>
                            <div class="model-definition-field">
                                <label>任务类型</label>
                                <input type="text" class="model-def-input" data-field="task" value="${window.esc(model.task || '')}" disabled />
                            </div>
                            <div class="model-definition-field">
                                <label>模型路径/名称</label>
                                <input type="text" class="model-def-input" data-field="model" value="${window.esc(model.model || '')}" />
                            </div>
                            <div class="model-definition-field">
                                <label>预估内存(MB)</label>
                                <input type="number" class="model-def-input" data-field="estimated_memory_mb" value="${model.estimated_memory_mb ?? ''}" />
                            </div>
                            <div class="model-definition-field" style="grid-column: 1 / -1;">
                                <label>额外参数 (JSON)</label>
                                <textarea class="model-def-input" data-field="pipeline_kwargs">${window.esc(pipelineKwargs)}</textarea>
                            </div>
                        </div>
                    </div>
                `;
            });
        }

        html += '</div>';
        return html;
    }

    document.addEventListener('change', (e) => {
        if (e.target.classList.contains('vendor-select')) {
            const domain = e.target.dataset.domain;
            const selectedVendor = e.target.value.toLowerCase();
            const formGrid = e.target.closest('.form-grid');
            if (!formGrid) return;
            const modelSelect = formGrid.querySelector(`.model-select[data-domain="${domain}"]`);
            if (!modelSelect) return;
            const models = (vendorModelData.model_by_domain_vendor[domain] || {})[selectedVendor] || [];
            const currentModel = modelSelect.value;
            modelSelect.innerHTML = models.map(m =>
                `<option value="${window.esc(m)}" ${String(currentModel).toLowerCase() === String(m).toLowerCase() ? 'selected' : ''}>${window.esc(m)}</option>`
            ).join('');
            return;
        }

        if (e.target.classList.contains('reasoning-type-checkbox')) {
            const type = e.target.dataset.type;
            const container = e.target.closest('.reasoning-effort-container');
            const select = container.querySelector(`.reasoning-effort-select[data-type="${type}"]`);
            if (select) {
                select.disabled = !e.target.checked;
                if (e.target.checked && !select.value) {
                    select.value = 'medium';
                }
            }
        }

        if (e.target.id === 'cfg-XINHAI_REASONING_AUTO_INJECT') {
            reasoningAutoInject = e.target.value === 'true';
            const reasoningContainer = document.querySelector('.reasoning-effort-container');
            if (reasoningContainer) {
                const key = reasoningContainer.dataset.key;
                const value = globalConfigData ? globalConfigData[key] : {};
                reasoningContainer.outerHTML = renderReasoningEffortField(reasoningContainer.id, key, value);
            }
        }
    });

    // 🔑 密码/密钥字段的交互委托（事件绑定到 document，动态 DOM 也命中）
    document.addEventListener('click', (e) => {
        const eyeBtn = e.target.closest('.pwd-toggle-eye');
        if (eyeBtn) {
            e.preventDefault();
            const targetId = eyeBtn.getAttribute('data-target');
            const input = targetId ? document.getElementById(targetId) : null;
            const icon = eyeBtn.querySelector('i');
            // 锁图标 / 隐藏图标：不切换密文/明文，只给用户提示
            if (eyeBtn.classList.contains('pwd-eye-locked')) {
                showStatus(
                    '🔐 已保存真实密钥，这里仅显示掩码。如需修改请直接在输入框中输入新值覆盖。',
                    'info',
                );
                return;
            }
            if (eyeBtn.classList.contains('pwd-eye-hidden')) {
                showStatus('⚠️ 该密钥未设置，请先在输入框中填写。', 'info');
                return;
            }
            if (!input) return;
            const isPwd = input.type === 'password';
            input.type = isPwd ? 'text' : 'password';
            if (icon) {
                icon.className = isPwd ? 'fas fa-eye' : 'fas fa-eye-slash';
            }
            eyeBtn.title = isPwd ? '隐藏密码' : '显示密码';
        }
    });

    document.addEventListener('input', (e) => {
        const input = e.target;
        if (!input || !input.matches || !input.matches('.pwd-field-wrap input[data-key][type="password"], .pwd-field-wrap input[data-key][type="text"]')) return;
        const wrap = input.closest('.pwd-field-wrap');
        if (!wrap) return;
        const badge = wrap.querySelector('.pwd-badge');
        const eyeBtn = wrap.querySelector('.pwd-toggle-eye');
        const rawValue = (input.value || '').trim();
        const originMasked = input.getAttribute('data-origin-masked') === '1';
        input.classList.remove('pwd-saved', 'pwd-empty', 'pwd-modified');
        if (!badge) return;
        if (rawValue === '' || rawValue === '********' || rawValue === '***') {
            if (originMasked && rawValue !== '') {
                input.classList.add('pwd-saved');
                badge.className = 'pwd-badge pwd-badge-saved';
                badge.title = '已保存真实密钥（显示掩码，点击输入框输入新值覆盖）';
                badge.textContent = '🔐 已保存真实密钥（掩码显示）';
                if (eyeBtn) {
                    eyeBtn.classList.remove('pwd-eye-hidden');
                    eyeBtn.classList.add('pwd-eye-locked');
                    eyeBtn.title = '已保存真实密钥，这里仅显示掩码。如需修改请直接在框中输入新值覆盖';
                    eyeBtn.textContent = '🔒';
                }
            } else {
                input.classList.add('pwd-empty');
                const ph = input.getAttribute('placeholder') || '请输入密钥';
                badge.className = 'pwd-badge pwd-badge-empty';
                badge.title = ph;
                badge.textContent = `⚠️ 未设置，${ph}`;
                if (eyeBtn) {
                    eyeBtn.classList.remove('pwd-eye-locked');
                    eyeBtn.classList.add('pwd-eye-hidden');
                    eyeBtn.title = '⚠️ 未设置，请先在框中输入';
                    eyeBtn.innerHTML = '<i class="fas fa-lock"></i>';
                }
            }
        } else {
            input.classList.add('pwd-modified');
            badge.className = 'pwd-badge pwd-badge-modified';
            badge.textContent = '✏️ 编辑中（点击保存生效）';
            if (eyeBtn) {
                eyeBtn.classList.remove('pwd-eye-locked', 'pwd-eye-hidden');
                eyeBtn.title = input.type === 'password' ? '显示密码' : '隐藏密码';
                eyeBtn.innerHTML = `<i class="fas fa-eye${input.type === 'password' ? '-slash' : ''}"></i>`;
            }
        }
    });

    function parseCommaList(value) {
        if (value === null || value === undefined) return [];
        if (Array.isArray(value)) {
            return value.map(function (s) {
                return s === null || s === undefined ? '' : String(s);
            }).map(function (s) { return s.trim(); }).filter(Boolean);
        }
        var s = String(value).trim();
        if (!s) return [];
        if (s.charAt(0) === '[') {
            try {
                var parsed = JSON.parse(s);
                if (Array.isArray(parsed)) return parseCommaList(parsed);
            } catch (e) { /* fallthrough */ }
        }
        var normalized = s.replace(/，/g, ',').replace(/、/g, ',');
        return normalized.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    }

    function normalizeValue(key, value) {
        const fieldType = FIELD_TYPE_MAP[key];
        if (fieldType === 'list') {
            if (Array.isArray(value)) {
                return value.map(function (s) {
                    return s === null || s === undefined ? '' : String(s);
                }).map(function (s) { return s.trim(); }).filter(Boolean);
            }
            if (typeof value === 'string') {
                return parseCommaList(value);
            }
            return [];
        }
        if (fieldType === 'reasoning_effort') {
            if (typeof value === 'object' && value !== null) return value;
            return {};
        }
        if (fieldType === 'model_definition_list') {
            if (Array.isArray(value)) return value;
            return [];
        }
        return value;
    }

    function getDisplayValue(key, value) {
        const fieldType = FIELD_TYPE_MAP[key];
        if (fieldType === 'list') {
            const arr = normalizeValue(key, value);
            return Array.isArray(arr) ? arr.join(', ') : '';
        }
        if (fieldType === 'model_definition_list') {
            return JSON.stringify(value, null, 2);
        }
        if (typeof value === 'object' && value !== null) {
            return JSON.stringify(value, null, 2);
        }
        if (isSensitiveKey(key) && containsPlaceholder(value)) {
            return '';
        }
        if (!isSensitiveKey(key) && isSensitivePlaceholder(value)) {
            return '';
        }
        return value ?? '';
    }

    function renderConfig(data) {
        const container = document.getElementById('configContainer');
        if (!container) return;
        container.innerHTML = '';

        CONFIG_SECTIONS.forEach((section, sIdx) => {
            const cardDiv = document.createElement('div');
            cardDiv.className = 'config-card';

            const isExpanded = sIdx === 0;
            let bodyHtml = '<div class="form-grid">';

            section.fields.forEach((field) => {
                const value = normalizeValue(field.key, data[field.key]);
                const inputId = 'cfg-' + field.key.replace(/[^a-zA-Z0-9]/g, '_');
                const displayValue = getDisplayValue(field.key, value);
                let inputHtml;

                if (field.type === 'bool') {
                    const isEnabled = value === true;
                    inputHtml = `<select class="form-control" id="${inputId}" data-key="${field.key}">
                        <option value="true" ${isEnabled ? 'selected' : ''}>启用</option>
                        <option value="false" ${!isEnabled ? 'selected' : ''}>禁用</option>
                    </select>`;
                } else if (field.type === 'password') {
                    const isEmpty = isSensitivePlaceholder(displayValue);
                    const isMaskedSentinel = displayValue === '***' || displayValue === '********';
                    // ⚠️ 关键区分：
                    //   - 真·空值（isEmpty && !isMaskedSentinel）：未设置 → 显示 placeholder + 红色「未设置」徽章
                    //   - mask sentinel：后端明确返回 *** → 已保存真实值 → 显示 8 星 + 绿色「🔐 已保存」徽章
                    //   - 其它字符串：用户显式在框里填的内容 → 直接显示
                    let showVal;
                    let badge;
                    let inputCls = 'form-control';
                    if (isMaskedSentinel) {
                        showVal = '********';
                        badge = `<span class="pwd-badge pwd-badge-saved" title="已保存真实密钥，这里仅显示掩码。如需修改请直接输入新值覆盖">🔐 已保存真实密钥（掩码显示）</span>`;
                        inputCls += ' pwd-saved';
                    } else if (isEmpty) {
                        showVal = '';
                        badge = `<span class="pwd-badge pwd-badge-empty" title="${window.esc(field.placeholder || '请输入密钥')}">⚠️ 未设置，${window.esc(field.placeholder || '请输入密钥')}</span>`;
                        inputCls += ' pwd-empty';
                    } else {
                        showVal = displayValue === null || displayValue === undefined ? '' : String(displayValue);
                        badge = `<span class="pwd-badge pwd-badge-modified">✏️ 编辑中（点击保存生效）</span>`;
                        inputCls += ' pwd-modified';
                    }
                    const placeholder = field.placeholder || '请输入密钥';
                    let eyeHtml;
                    if (isMaskedSentinel) {
                        // 🔐 已保存真实密钥（掩码显示）：显示 🔒 锁图标，禁用密码/文本切换（仅作说明
                        // 避免"8 星号跟点号互相切来切去的奇怪现象；用户要改直接输入
                        eyeHtml = `<button type="button" class="pwd-toggle-eye pwd-eye-locked" data-target="${inputId}" aria-label="已保存真实密钥，显示为掩码" title="已保存真实密钥，这里仅显示掩码。如需修改请直接在框中输入新值覆盖">
                            🔒
                        </button>`;
                    } else if (!isEmpty) {
                        // 只有用户正在编辑新值（✏️ 编辑中）：才显示 👁 显示/隐藏密码
                        eyeHtml = `<button type="button" class="pwd-toggle-eye" data-target="${inputId}" aria-label="显示/隐藏密码" title="显示/隐藏密码">
                            <i class="fas fa-eye-slash"></i>
                        </button>`;
                    } else {
                        // ⚠️ 未设置（空框）：没有值可看，也不需要眼睛按钮
                        eyeHtml = `<button type="button" class="pwd-toggle-eye pwd-eye-hidden" data-target="${inputId}" aria-label="未设置，请先输入" title="⚠️ 未设置，请先在框中输入" tabindex="-1">
                            <i class="fas fa-lock"></i>
                        </button>`;
                    }
                    inputHtml = `
                        <div class="pwd-field-wrap">
                            <input
                                type="password"
                                class="${inputCls}"
                                id="${inputId}"
                                value="${window.esc(showVal)}"
                                data-key="${field.key}"
                                data-origin-masked="${isMaskedSentinel ? '1' : '0'}"
                                placeholder="${window.esc(placeholder)}"
                                autocomplete="new-password"
                            />
                            ${eyeHtml}
                            ${badge}
                        </div>`;
                } else if (field.type === 'list') {
                    inputHtml = `<input type="text" class="form-control" id="${inputId}" value="${window.esc(String(displayValue ?? ''))}" data-key="${field.key}" placeholder="${window.esc(field.placeholder || '')}">`;
                } else if (field.type === 'model_definition_list') {
                    inputHtml = renderModelDefinitionList(inputId, field.key, value);
                } else if (field.type === 'json') {
                    const rows = field.rows || 5;
                    inputHtml = `<textarea class="form-control" id="${inputId}" data-key="${field.key}" rows="${rows}" placeholder="${window.esc(field.placeholder || '请输入 JSON 格式内容，如 {}')}">${window.esc(String(displayValue ?? ''))}</textarea>`;
                } else if (field.type === 'float') {
                    const numStr = typeof displayValue === 'number'
                        ? String(displayValue)
                        : ((typeof displayValue === 'string' && displayValue.trim() !== '' && !isNaN(parseFloat(displayValue)))
                            ? String(parseFloat(displayValue))
                            : '');
                    inputHtml = `<input type="number" step="any" class="form-control" id="${inputId}" value="${numStr}" data-key="${field.key}" placeholder="${window.esc(field.placeholder || '')}">`;
                } else if (field.type === 'number') {
                    const numStr = typeof displayValue === 'number'
                        ? String(displayValue)
                        : ((typeof displayValue === 'string' && /^-?\d+$/.test(displayValue.trim()))
                            ? displayValue.trim()
                            : '');
                    inputHtml = `<input type="number" step="1" class="form-control" id="${inputId}" value="${numStr}" data-key="${field.key}" placeholder="${window.esc(field.placeholder || '')}">`;
                } else if (field.type === 'reasoning_effort') {
                    inputHtml = renderReasoningEffortField(inputId, field.key, value);
                } else if (field.type === 'vendor_select') {
                    const domain = field.domain || 'text';
                    const vendors = vendorModelData.vendor_by_domain[domain] || [];
                    inputHtml = `<select class="form-control vendor-select" id="${inputId}" data-key="${field.key}" data-domain="${domain}">
                        ${vendors.map(v =>
                            `<option value="${window.esc(v)}" ${String(displayValue ?? '').toLowerCase() === String(v).toLowerCase() ? 'selected' : ''}>${window.esc(v)}</option>`
                        ).join('')}
                    </select>`;
                } else if (field.type === 'model_select') {
                    const domain = field.domain || 'text';
                    const vendorField = section.fields.find(f => f.type === 'vendor_select' && f.domain === domain);
                    const vendorValue = vendorField ? String(data[vendorField.key] || '').toLowerCase() : '';
                    const models = (vendorModelData.model_by_domain_vendor[domain] || {})[vendorValue] || [];
                    inputHtml = `<select class="form-control model-select" id="${inputId}" data-key="${field.key}" data-domain="${domain}">
                        ${models.map(m =>
                            `<option value="${window.esc(m)}" ${String(displayValue ?? '').toLowerCase() === String(m).toLowerCase() ? 'selected' : ''}>${window.esc(m)}</option>`
                        ).join('')}
                    </select>`;
                } else {
                    inputHtml = `<input type="text" class="form-control" id="${inputId}" value="${window.esc(String(displayValue ?? ''))}" data-key="${field.key}" placeholder="${window.esc(field.placeholder || '')}">`;
                }

                const labelHtml = `<label title="${window.esc(field.label)}"><span class="label-text">${window.esc(field.label)}</span>${field.hint ? `<span class="field-hint">（${window.esc(field.hint)}）</span>` : ''}</label>`;

                if (field.fullWidth) {
                    bodyHtml += `<div class="form-group full-width">${labelHtml}${inputHtml}</div>`;
                } else {
                    bodyHtml += `<div class="form-group">${labelHtml}${inputHtml}</div>`;
                }
            });

            bodyHtml += '</div>';

            cardDiv.innerHTML =
                '<div class="config-header" onclick="toggleCard(this)">' +
                    `<span>${section.name}</span>` +
                    `<i class="fas fa-chevron-${isExpanded ? 'up' : 'down'}"></i>` +
                '</div>' +
                '<div class="config-body ' + (isExpanded ? 'open' : '') + '">' +
                    bodyHtml +
                '</div>';

            container.appendChild(cardDiv);
        });
    }

    function parseConfigValue(str) {
        if (str === "true") return true;
        if (str === "false") return false;
        if (/^-?\d+\.\d+$/.test(str)) return parseFloat(str);
        if (/^-?\d+$/.test(str)) return parseInt(str, 10);
        if (str === '') return '';
        try {
            const parsed = JSON.parse(str);
            if (parsed && typeof parsed === 'object') return parsed;
        } catch (e) {}
        return str;
    }

    window.parseConfigValue = parseConfigValue;

    document.addEventListener('DOMContentLoaded', () => {
        const loadBtn = document.getElementById('loadBtn');
        const saveBtn = document.getElementById('saveBtn');

        loadBtn?.addEventListener('click', async () => {
            try {
                await fetchReasoningTypes();
                await fetchVendorModel();
                const response = await axios.get('/api/global-configs/');
                globalConfigData = response.data || {};
                reasoningAutoInject = response.data?.['XINHAI_REASONING_AUTO_INJECT'] === true;
                renderConfig(response.data || {});
                showStatus('配置加载成功', 'success');
            } catch (error) {
                showStatus(`加载失败: ${error.response?.data?.detail || error.message}`, 'error');
            }
        });

        saveBtn?.addEventListener('click', async () => {
            if (!globalConfigData) return showStatus('请先加载配置', 'error');

            const inputs = document.querySelectorAll('#configContainer [data-key]');
            const patchData = {};

            const getLabel = (key) => {
                for (const section of CONFIG_SECTIONS) {
                    const field = section.fields.find(f => f.key === key);
                    if (field) return field.label;
                }
                return key;
            };

            const reasoningContainers = document.querySelectorAll('.reasoning-effort-container');
            reasoningContainers.forEach(container => {
                const key = container.dataset.key;
                const result = {};
                const checkboxes = container.querySelectorAll('.reasoning-type-checkbox');

                checkboxes.forEach(checkbox => {
                    if (checkbox.checked) {
                        const type = checkbox.dataset.type;
                        const select = container.querySelector(`.reasoning-effort-select[data-type="${type}"]`);
                        result[type] = select ? select.value : 'medium';
                    }
                });

                const oldValue = globalConfigData[key];
                if (JSON.stringify(result) !== JSON.stringify(oldValue || {})) {
                    patchData[key] = result;
                }
            });

            const modelDefContainers = document.querySelectorAll('.model-definition-container');
            modelDefContainers.forEach(container => {
                const key = container.dataset.key;
                const items = container.querySelectorAll('.model-definition-item');
                const result = [];

                items.forEach(item => {
                    const model = {};
                    const modelInputs = item.querySelectorAll('.model-def-input');
                    modelInputs.forEach(modelInput => {
                        const field = modelInput.dataset.field;
                        let value = modelInput.value.trim();

                        if (field === 'estimated_memory_mb') {
                            model[field] = value ? parseInt(value, 10) : 0;
                        } else if (field === 'pipeline_kwargs') {
                            try {
                                model[field] = value ? JSON.parse(value) : {};
                            } catch (e) {
                                model[field] = {};
                            }
                        } else {
                            model[field] = value;
                        }
                    });

                    if (Object.keys(model).length > 0) {
                        result.push(model);
                    }
                });

                const oldValue = globalConfigData[key];
                if (JSON.stringify(result) !== JSON.stringify(oldValue || [])) {
                    patchData[key] = result;
                }
            });

            for (const el of inputs) {
                const key = el.dataset.key;
                const fieldType = FIELD_TYPE_MAP[key];
                const sensitive = isSensitiveKey(key);

                if (fieldType === 'reasoning_effort') continue;
                if (fieldType === 'model_definition_list') continue;

                let rawValue = (el.value === undefined || el.value === null) ? '' : String(el.value).trim();
                const oldValue = globalConfigData[key];
                let newValue;

                // 🔐 密码字段特殊处理：
                //   - 原本是 mask sentinel（🔐 已保存）且用户输入仍为 ******** 或 空：
                //     → 跳过，不要把假掩码写回引擎
                //   - 原本是 mask 但用户改了内容且输入非空：按敏感字段正常提交
                if (fieldType === 'password' || sensitive) {
                    const originMasked = el.dataset.originMasked === '1' || el.getAttribute('data-origin-masked') === '1';
                    const looksLikeMaskedPlaceholder = rawValue === ''
                        || rawValue === '********'
                        || rawValue === '***';
                    if (originMasked && looksLikeMaskedPlaceholder) {
                        continue;
                    }
                }

                if (isSensitivePlaceholder(rawValue)) {
                    if (!sensitive) {
                        if (oldValue !== '' && oldValue !== undefined && oldValue !== null && !isSensitivePlaceholder(oldValue)) {
                            continue;
                        }
                    }
                    continue;
                }

                if (fieldType === 'bool') {
                    newValue = el.value === 'true';
                    if (newValue !== oldValue) patchData[key] = newValue;
                    continue;
                }

                if (sensitive) {
                    const oldStr = String(oldValue ?? '');
                    if (oldStr && !isSensitivePlaceholder(oldStr) && rawValue === oldStr) {
                        continue;
                    }
                    patchData[key] = rawValue;
                    continue;
                }

                if (fieldType === 'number') {
                    if (rawValue !== '' && !/^-?\d+$/.test(rawValue)) {
                        showStatus(`❌ "${getLabel(key)}" 包含无效字符，只允许整数`, 'error');
                        return;
                    }
                    newValue = rawValue === '' ? 0 : parseInt(rawValue, 10);
                    if (newValue !== oldValue) patchData[key] = newValue;
                    continue;
                }

                if (fieldType === 'float') {
                    if (rawValue !== '' && !/^-?\d+(\.\d+)?$/.test(rawValue)) {
                        showStatus(`❌ "${getLabel(key)}" 包含无效字符，只允许数字（整数或小数均可）`, 'error');
                        return;
                    }
                    newValue = rawValue === '' ? 0.0 : parseFloat(rawValue);
                    if (newValue !== oldValue) patchData[key] = newValue;
                    continue;
                }

                if (fieldType === 'list') {
                    let processed;
                    if (rawValue && (/[，、]/.test(rawValue))) {
                        const fixedValue = rawValue.replace(/，/g, ',').replace(/、/g, ',');
                        el.value = fixedValue;
                        showStatus(`🔧 “${getLabel(key)}” 中的中文逗号/顿号已自动替换为英文逗号`, 'info', 3000);
                        processed = parseCommaList(fixedValue);
                    } else {
                        processed = parseCommaList(rawValue);
                    }
                    if (JSON.stringify(processed) !== JSON.stringify(oldValue || [])) {
                        patchData[key] = processed;
                    }
                    continue;
                }

                if (fieldType === 'json') {
                    if (rawValue) {
                        try {
                            newValue = JSON.parse(rawValue);
                        } catch (e) {
                            showStatus(`❌ "${getLabel(key)}" JSON 格式错误: ${e.message}`, 'error');
                            return;
                        }
                    } else {
                        newValue = {};
                    }
                    if (JSON.stringify(newValue) !== JSON.stringify(oldValue || {})) {
                        patchData[key] = newValue;
                    }
                    continue;
                }

                if (rawValue === '') {
                    if (oldValue !== '') patchData[key] = '';
                } else if (rawValue === 'true') {
                    if (oldValue !== true) patchData[key] = true;
                } else if (rawValue === 'false') {
                    if (oldValue !== false) patchData[key] = false;
                } else if (/^-?\d+$/.test(rawValue)) {
                    newValue = parseInt(rawValue, 10);
                    if (newValue !== oldValue) patchData[key] = newValue;
                } else if (/^-?\d+\.\d+$/.test(rawValue)) {
                    newValue = parseFloat(rawValue);
                    if (newValue !== oldValue) patchData[key] = newValue;
                } else if (rawValue.startsWith('{') || rawValue.startsWith('[')) {
                    try {
                        newValue = JSON.parse(rawValue);
                        if (JSON.stringify(newValue) !== JSON.stringify(oldValue)) {
                            patchData[key] = newValue;
                        }
                    } catch (e) {
                        if (rawValue !== oldValue) patchData[key] = rawValue;
                    }
                } else {
                    if (rawValue !== oldValue) patchData[key] = rawValue;
                }
            }

            if (Object.keys(patchData).length > 0) {
                for (const key of Object.keys(patchData)) {
                    if (isSensitiveKey(key) && containsPlaceholder(patchData[key])) {
                        delete patchData[key];
                        continue;
                    }
                    if (!isSensitiveKey(key) && typeof patchData[key] === 'string' && containsPlaceholder(patchData[key])) {
                        showStatus(`❌ "${getLabel(key)}"（非敏感配置）包含占位符关键词，请输入真实值或留空（禁止：请输入 / 请填写 / 请选择 / 请设置 / 请替换 / your- / YOUR_ / <your- / TODO / <todo> 等）`, 'error');
                        return;
                    }
                }
            }

            if (Object.keys(patchData).length === 0) {
                showStatus('没有检测到配置变更，无需保存', 'info');
                return;
            }

            try {
                await axios.patch('/api/global-configs/', patchData);
                Object.assign(globalConfigData, patchData);
                // 对写入成功的敏感字段：同步把输入框视觉状态切回 🔐 已保存 + 🔒 锁眼睛
                for (const key of Object.keys(patchData)) {
                    if (!isSensitiveKey(key)) continue;
                    const input = document.querySelector(`input[data-key="${key}"]`);
                    if (!input) continue;
                    input.setAttribute('data-origin-masked', '1');
                    input.type = 'password';
                    input.value = '********';
                    input.classList.remove('pwd-empty', 'pwd-modified');
                    input.classList.add('pwd-saved');
                    const wrap = input.closest('.pwd-field-wrap');
                    const badge = wrap ? wrap.querySelector('.pwd-badge') : null;
                    const eyeBtn = wrap ? wrap.querySelector('.pwd-toggle-eye') : null;
                    if (badge) {
                        badge.className = 'pwd-badge pwd-badge-saved';
                        badge.textContent = '🔐 已保存真实密钥（掩码显示）';
                        badge.title = '已保存真实密钥，显示为掩码；需修改请直接输入新值';
                    }
                    if (eyeBtn) {
                        eyeBtn.classList.remove('pwd-eye-hidden', 'pwd-eye-modified');
                        eyeBtn.classList.add('pwd-eye-locked');
                        eyeBtn.title = '已保存真实密钥，这里仅显示掩码。如需修改请直接在框中输入新值覆盖';
                        eyeBtn.textContent = '🔒';
                    }
                }
                if (window.AppCache && typeof AppCache.invalidate === 'function') {
                    AppCache.invalidate('/api/vendor-model');
                    AppCache.invalidate('/api/reasoning-types');
                    AppCache.invalidate('/api/card-config');
                    AppCache.invalidate('card_config_header_bg');
                    AppCache.invalidate('card_config_footer_bg');
                    AppCache.invalidate('card_config_novel_bg');
                    AppCache.invalidate('card_config_message_wall_bg');
                }
                showStatus(`配置保存成功（更新 ${Object.keys(patchData).length} 项）`, 'success');
            } catch (error) {
                showStatus(`保存失败: ${error.response?.data?.detail || error.message}`, 'error');
            }
        });

        loadBtn?.click();
    });

    window.addEventListener('DOMContentLoaded', () => {
        const toolbar = document.querySelector('.page-actions');
        const targetBtn = document.getElementById('loadBtn');

        if (toolbar && targetBtn) {
            if (window.__bikeAnim) window.__bikeAnim.destroy();

            const toolbarRect = toolbar.getBoundingClientRect();
            const btnRect = targetBtn.getBoundingClientRect();
            const anchorRightInContainer = btnRect.right - toolbarRect.left;
            const anchorLeftInContainer = btnRect.left - toolbarRect.left;

            window.__bikeAnim = new BikeAnimation({
                container: toolbar,
                anchorElement: targetBtn,
                offsetStart: 20 - anchorRightInContainer,
                offsetEnd: toolbar.clientWidth - anchorLeftInContainer + 20,
                duration: 12000,
                verticalOffset: 35
            });
        }
    });
})();
