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
            processStatusQueue(); // 显示下一条
        }, timeout);
    }

    function showStatus(message, type = 'info', timeout = 3000) {
        if (!statusBox) return;
        // 直接覆盖默认时长（与之前逻辑兼容）
        if (timeout === 3000) {
            timeout = type === 'success' ? 5000 : (type === 'error' ? 8000 : 3000);
        }
        statusQueue.push({ message, type, timeout });
        if (!statusTimer) processStatusQueue();
    }

    let vendorModelData = { vendor: [], model: [] };

    async function fetchVendorModel() {
        try {
            const response = await axios.get('/api/vendor-model');
            vendorModelData = {
                vendor: response.data.vendor || [],
                model: response.data.model || []
            };
        } catch (error) {
            console.error('获取厂商和模型失败:', error);
            vendorModelData = { vendor: [], model: [] };
        }
    }

    const CONFIG_SECTIONS = [
        {
            name: 'LLM 核心配置',
            fields: [
                { key: 'XINHAI_LLM_DEFAULT_VENDOR', type: 'vendor_select', label: '模型提供商' },
                { key: 'XINHAI_LLM_DEFAULT_MODEL', type: 'model_select', label: '模型名称' },
                { key: 'XINHAI_LLM_API_TIMEOUT', type: 'number', label: 'LLM 超时时间（秒）' },
                { key: 'XINHAI_LLM_DEEPSEEK_API_KEY', type: 'password', label: 'DeepSeek 密钥', fullWidth: true },
                { key: 'XINHAI_LLM_PARAMS', type: 'json', label: 'LLM 参数', rows: 5, fullWidth: true },
                { key: 'XINHAI_REASONING_AUTO_INJECT', type: 'bool', label: '是否开启推理模式'},
                { key: 'XINHAI_REASONING_DEFAULT_EFFORT', type: 'reasoning_effort', label: '推理模式配置', fullWidth: true}
            ]
        },
        {
            name: '元认知配置',
            fields: [
                { key: 'XINHAI_METACOGNITION_ENABLED', type: 'bool', label: '元认知引擎总开关' },
                { key: 'XINHAI_METACOGNITION_MAX_LLM_CALLS', type: 'number', label: '单次元认知任务最大调用次数' },
                { key: 'XINHAI_METACOGNITION_MAX_ITERATIONS', type: 'number', label: '上帝之眼触发加载数据的最大循环次数' },
                { key: 'XINHAI_METACOGNITION_MAX_DEBATE_ROUNDS', type: 'number', label: '上帝之眼触发辩论的最大循环次数' },
                { key: 'XINHAI_METACOGNITION_QUEUE_MAXSIZE', type: 'number', label: '任务队列最大长度' },
                { key: 'XINHAI_METACOGNITION_MAX_WORKER', type: 'number', label: '元认知执行器最大并行' },
                { key: 'XINHAI_METACOGNITION_EXPIRES_AT', type: 'number', label: '元认知任务超时时间（秒）' },
                { key: 'XINHAI_METACOGNITION_MAX_CHARS_PER_TURN', type: 'number', label: '单轮辩论报告的最大字符数' },
                { key: 'XINHAI_METACOGNITION_MAX_DEBATE_TURNS_TO_INJECT', type: 'number', label: '辩论记录最大注入轮次' },
                { key: 'XINHAI_METACOGNITION_MAX_ISSUES_TO_DISPLAY', type: 'number', label: '裁决报告中问题清单最大注入条数' },
                { key: 'XINHAI_METACOGNITION_DATA_LOADER_DEFAULT_LEVEL', type: 'number', label: '默认加载的数据层级' },
                { key: 'XINHAI_METACOGNITION_MONITOR_ALERT_COOLDOWN', type: 'number', label: '队列监控告警冷却时间（秒）' },
                { key: 'XINHAI_METACOGNITION_QUEUE_HIGH_WATERMARK', type: 'float', label: '队列高水位告警阈值（0-1）' },
                { key: 'XINHAI_METACOGNITION_QUEUE_MID_WATERMARK', type: 'float', label: '队列中水位提示阈值（0-1）' },
                { key: 'XINHAI_METACOGNITION_QUEUE_CHECK_INTERVAL', type: 'number', label: '队列监控检查间隔（秒）' },
                { key: 'XINHAI_METACOGNITION_TARGET_CHARS', type: 'number', label: '智能合并段落的目标字符数' },
                { key: 'XINHAI_METACOGNITION_TOLERANCE', type: 'number', label: '智能合并段落的偏移量' }
            ]
        },
        {
            name: '并发控制',
            fields: [
                { key: 'XINHAI_MAX_LLM_STEP_CONCURRENCY', type: 'number', label: '全局最大 LLM 并行数' },
                { key: 'XINHAI_CURRENT_LLM_STEP_CONCURRENCY', type: 'number', label: '当前环境的 LLM 并行数' },
                { key: 'XINHAI_MEDIUM_LLM_STEP_CONCURRENCY', type: 'number', label: '推荐的中等 LLM 并行数' },
                { key: 'XINHAI_MAX_BATCH_TASK_CONCURRENCY', type: 'number', label: '批量任务最大并行数' },
                { key: 'XINHAI_CURRENT_BATCH_TASK_CONCURRENCY', type: 'number', label: '当前环境的批量任务并行数' },
                { key: 'XINHAI_MEDIUM_BATCH_TASK_CONCURRENCY', type: 'number', label: '推荐的中等批量任务并行数' },
                { key: 'XINHAI_MAX_BATCH_TASKS', type: 'number', label: '单次批量任务的最大任务数' },
                { key: 'XINHAI_MAX_BATCH_FILE_SIZE_BYTES', type: 'number', label: '批量任务文件最大大小（字节）' }
            ]
        },
        {
            name: '存储与缓存',
            fields: [
                { key: 'XINHAI_STORAGE_BACKEND', type: 'text', label: '存储后端类型' },
                { key: 'XINHAI_LLM_CACHE_MAX_SIZE', type: 'number', label: 'LLM 缓存最大容量' },
                { key: 'XINHAI_LLM_CACHE_TTL', type: 'number', label: 'LLM 缓存过期时间（秒）' },
                { key: 'XINHAI_REDIS_HOST', type: 'text', label: 'Redis 主机地址' },
                { key: 'XINHAI_REDIS_PORT', type: 'number', label: 'Redis 服务端口' },
                { key: 'XINHAI_REDIS_DB', type: 'number', label: 'Redis 数据库索引' },
                { key: 'XINHAI_REDIS_PASSWORD', type: 'password', label: 'Redis 访问密码' },
                { key: 'XINHAI_REDIS_TIMEOUT', type: 'number', label: 'Redis 操作超时时间（秒）' }
            ]
        },
        {
            name: '报告与水印',
            fields: [
                { key: 'XINHAI_TEXT_REPORT_TITLE', type: 'text', label: '分析报告默认标题', fullWidth: true },
                { key: 'XINHAI_WATERMARK_ENABLED', type: 'bool', label: '是否启用水印' },
                { key: 'XINHAI_WATERMARK_TEXT', type: 'text', label: '水印文本内容', fullWidth: true },
                { key: 'XINHAI_WATERMARK_COLOR', type: 'text', label: '水印文字颜色' },
                { key: 'XINHAI_WATERMARK_OPACITY', type: 'float', label: '水印透明度（0-1）' },
                { key: 'XINHAI_WATERMARK_FONT_SIZE', type: 'number', label: '水印字体大小（px）' },
                { key: 'XINHAI_WATERMARK_ANGLE', type: 'number', label: '水印旋转角度' },
                { key: 'XINHAI_WATERMARK_SPACING_COLS', type: 'number', label: '水印列间距' },
                { key: 'XINHAI_WATERMARK_SPACING_ROWS', type: 'number', label: '水印行间距' },
                { key: 'XINHAI_WATERMARK_PADDING', type: 'number', label: '水印内边距（px）' }
            ]
        },
        {
            name: '通知系统',
            fields: [
                { key: 'XINHAI_NOTIFICATION_ENABLED', type: 'bool', label: '是否启用消息通知' },
                { key: 'XINHAI_NOTIFICATION_CHANNELS', type: 'list', label: '启用的通知渠道列表', fullWidth: true },
                { key: 'XINHAI_EMAIL_SMTP_SERVER', type: 'text', label: '邮箱 SMTP 服务器地址', fullWidth: true },
                { key: 'XINHAI_EMAIL_PORT', type: 'number', label: '邮箱 SMTP 服务端口' },
                { key: 'XINHAI_EMAIL_USERNAME', type: 'text', label: '发件邮箱账号', fullWidth: true },
                { key: 'XINHAI_EMAIL_PASSWORD', type: 'password', label: '邮箱授权码（保密）', fullWidth: true },
                { key: 'XINHAI_EMAIL_TO', type: 'list', label: '邮件接收人列表', fullWidth: true },
                { key: 'XINHAI_FEISHU_WEBHOOK_URL', type: 'text', label: '飞书 Webhook 地址（保密）', fullWidth: true },
                { key: 'XINHAI_FEISHU_AT_USER_IDS', type: 'list', label: '飞书 @ 用户 ID 列表', fullWidth: true },
                { key: 'XINHAI_WECOM_WEBHOOK_URL', type: 'text', label: '企业微信 Webhook 地址（保密）', fullWidth: true },
                { key: 'XINHAI_WECOM_AT_USER_IDS', type: 'list', label: '企业微信 @ 用户 ID 列表', fullWidth: true },
                { key: 'XINHAI_SUSPEND_TIMEOUT_SECONDS', type: 'number', label: '挂起任务超时时间（秒）' }
            ]
        },
        {
            name: '图片平台',
            fields: [
                { key: 'XINHAI_UNSPLASH_ACCESS_KEY', type: 'password', label: 'Unsplash 图片平台密钥', fullWidth: true },
                { key: 'XINHAI_UNSPLASH_BASIC_PATH', type: 'text', label: 'Unsplash 接口基础路径', fullWidth: true },
                { key: 'XINHAI_PEXELS_ACCESS_KEY', type: 'password', label: 'Pexels 图片平台密钥', fullWidth: true },
                { key: 'XINHAI_PEXELS_BASIC_PATH', type: 'text', label: 'Pexels 接口基础路径', fullWidth: true }
            ]
        },
        {
            name: 'LangSmith 可观测性',
            fields: [
                { key: 'XINHAI_LANGSMITH_ENABLED', type: 'bool', label: '是否启用 LangSmith 追踪' },
                { key: 'XINHAI_LANGSMITH_API_KEY', type: 'password', label: 'LangSmith API 密钥', fullWidth: true },
                { key: 'XINHAI_LANGSMITH_PROJECT', type: 'text', label: 'LangSmith 项目名称' },
                { key: 'XINHAI_LANGSMITH_ENDPOINT', type: 'text', label: 'LangSmith 服务端点', fullWidth: true }
            ]
        },
        {
            name: '日志配置',
            fields: [
                { key: 'XINHAI_LOG_KEEP_DAYS', type: 'number', label: '日志保留天数' },
                { key: 'XINHAI_LOG_MAX_BYTES', type: 'number', label: '单个日志文件最大大小（字节）' },
                { key: 'XINHAI_LOG_BACKUP_COUNT', type: 'number', label: '日志备份保留数量' }
            ]
        },
        {
            name: '重试与监控',
            fields: [
                { key: 'XINHAI_DEFAULT_RETRY_CONFIG', type: 'json', label: '全局默认重试策略配置', rows: 5, fullWidth: true },
                { key: 'XINHAI_OLLAMA_ENABLED', type: 'bool', label: '是否启用 Ollama 本地模型' },
                { key: 'XINHAI_OLLAMA_BASE_URL', type: 'text', label: 'Ollama 服务地址', fullWidth: true },
                { key: 'XINHAI_OLLAMA_MODEL', type: 'text', label: 'Ollama 使用的模型名称' },
                { key: 'XINHAI_OLLAMA_PARAMS', type: 'json', label: 'Ollama 调用参数', rows: 5, fullWidth: true },
                { key: 'XINHAI_OLLAMA_TIMEOUT', type: 'number', label: 'Ollama 请求超时时间（秒）' },
                { key: 'XINHAI_GLOBAL_MAX_RETRIES', type: 'number', label: '全局最大重试次数' },
                { key: 'XINHAI_GLOBAL_RETRY_TIMEOUT', type: 'number', label: '全局重试熔断超时时间（秒）' },
                { key: 'XINHAI_GLOBAL_ENABLE_METRICS', type: 'bool', label: '是否启用全局指标统计' },
                { key: 'XINHAI_PROXY_BACKEND_SSE_URL', type: 'text', label: 'SSE 代理后端地址'},
                { key: 'XINHAI_SSE_HEARTBEAT_INTERVAL', type: 'number', label: 'SSE 心跳间隔（秒）' },
                { key: 'XINHAI_MAX_TOKENS_EXPANSION_FACTOR', type: 'float', label: 'deepseek-v4 系列模型输出 Token 扩容比率' },
                { key: 'XINHAI_FULL_TEXT_TOKENS_RATIO', type: 'float', label: '基础 max_token 扩容比率' },
                { key: 'XINHAI_MAX_LENGTH_RETRIES', type: 'number', label: '自动扩容的最大重试次数' },
                { key: 'XINHAI_FACTOR_INCREMENT', type: 'float', label: '自动扩容每次重试时增加的比率值' },
            ]
        },
        {
            name: '辅助任务配置',
            fields: [
                { key: 'XINHAI_POLISH_AUXILIARY_TASK_LIMIT', type: 'number', label: '串行打磨时，辅助报告最大注入条数' },
                { key: 'XINHAI_CHARACTER_PROFILES', type: 'number', label: '角色设定注入上限' },
                { key: 'XINHAI_WORLDVIEW_RULES', type: 'number', label: '世界观规则注入上限' },
                { key: 'XINHAI_RELATIONSHIP_MAP', type: 'number', label: '人物关系注入上限' },
                { key: 'XINHAI_STYLE_PREFERENCE', type: 'number', label: '风格倾向注入上限' },
                { key: 'XINHAI_IMAGE_COUNT', type: 'number', label: '背景图片总数' },
                { key: 'XINHAI_REFRESH_INTERVAL_MS', type: 'number', label: '首页卡片背景刷新频率' }
            ]
        }
    ];

    const FIELD_TYPE_MAP = {};
    CONFIG_SECTIONS.forEach(section => {
        section.fields.forEach(field => {
            FIELD_TYPE_MAP[field.key] = field.type;
        });
    });

    const REASONING_EFFORTS = ['low', 'medium', 'high', 'max'];
    const REASONING_TYPE_NAMES = {
        'internal': '元认知',
        'parallel_analysis': '并行诊断',
        'serial_adaptation': '串行场景适配',
        'serial_aggregation': '串行聚合',
        'serial_enhance': '串行增强',
        'serial_polish': '串行打磨',
        'serial_preprocessing': '串行预处理'
    };
    let reasoningTypes = [];
    let reasoningAutoInject = false;

    async function fetchReasoningTypes() {
        try {
            const response = await axios.get('/api/reasoning-types');
            reasoningTypes = response.data.types || [];
        } catch (error) {
            console.error('获取推理类型失败:', error);
            reasoningTypes = [];
        }
    }

    function renderReasoningEffortField(inputId, key, value) {
        const effortMap = typeof value === 'object' && value !== null ? value : {};
        const disabled = !reasoningAutoInject;
        let html = `<div id="${inputId}" data-key="${key}" class="reasoning-effort-container">`;

        if (disabled) {
            html += `<div style="color: #999; font-size: 13px; margin-top: 8px;">⚠️ 请先开启「是否开启推理模式」才能配置各类型的推理等级</div>`;
        }

        html += `
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 10px;">
        `;

        reasoningTypes.forEach(type => {
            const isChecked = Object.hasOwnProperty.call(effortMap, type);
            const selectedEffort = isChecked ? effortMap[type] : 'low';
            const typeName = REASONING_TYPE_NAMES[type] || type;

            html += `
                <div style="display: flex; align-items: center; gap: 8px; padding: 8px 10px; background: #f8f9fa; border-radius: 6px; border: 1px solid #e9ecef;">
                    <label style="display: flex; align-items: center; gap: 6px; cursor: ${disabled ? 'not-allowed' : 'pointer'}; flex: 1; opacity: ${disabled ? 0.5 : 1};">
                        <input 
                            type="checkbox" 
                            class="reasoning-type-checkbox" 
                            ${isChecked ? 'checked' : ''}
                            ${disabled ? 'disabled' : ''}
                            data-type="${window.esc(type)}"
                            style="width: 15px; height: 15px; cursor: ${disabled ? 'not-allowed' : 'pointer'};"
                        />
                        <span style="font-weight: 500; font-size: 13px; color: #444;">${window.esc(typeName)}</span>
                    </label>
                    <select 
                        class="reasoning-effort-select form-control" 
                        data-type="${window.esc(type)}"
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

        html += '</div>';
        html += '</div>';

        return html;
    }

    document.addEventListener('DOMContentLoaded', () => {
        fetchReasoningTypes();

        document.addEventListener('change', (e) => {
            if (e.target.classList.contains('reasoning-type-checkbox')) {
                const type = e.target.dataset.type;
                const container = e.target.closest('.reasoning-effort-container');
                const select = container.querySelector(`.reasoning-effort-select[data-type="${type}"]`);
                if (select) {
                    select.disabled = !e.target.checked;
                    if (e.target.checked && !select.value) {
                        select.value = 'low';
                    }
                }
            }

            if (e.target.id === 'cfg-XINHAI_REASONING_AUTO_INJECT') {
                reasoningAutoInject = e.target.value === 'true';
                const reasoningContainer = document.querySelector('.reasoning-effort-container');
                if (reasoningContainer) {
                    const key = reasoningContainer.dataset.key;
                    const value = globalConfigData ? globalConfigData[key] : {};
                    const newHtml = renderReasoningEffortField(reasoningContainer.id, key, value);
                    reasoningContainer.outerHTML = newHtml;
                }
            }
        });
    });

    function normalizeValue(key, value) {
        const fieldType = FIELD_TYPE_MAP[key];
        if (fieldType === 'list') {
            if (Array.isArray(value)) return value;
            if (typeof value === 'string') {
                return value ? value.split(',').map(s => s.trim()).filter(Boolean) : [];
            }
            return [];
        }
        if (fieldType === 'reasoning_effort') {
            if (typeof value === 'object' && value !== null) return value;
            return {};
        }
        return value;
    }

    function getDisplayValue(key, value) {
        const fieldType = FIELD_TYPE_MAP[key];
        if (fieldType === 'list') {
            const arr = normalizeValue(key, value);
            return Array.isArray(arr) ? arr.join(', ') : '';
        }
        if (typeof value === 'object' && value !== null) {
            return JSON.stringify(value, null, 2);
        }
        return value ?? '';
    }

    function renderConfig(data) {
        const container = document.getElementById('configContainer');
        if (!container) return;
        container.innerHTML = '';

        const predefinedKeys = new Set();
        CONFIG_SECTIONS.forEach(section => {
            section.fields.forEach(field => {
                predefinedKeys.add(field.key);
            });
        });

        CONFIG_SECTIONS.forEach((section, sIdx) => {
            const cardDiv = document.createElement('div');
            cardDiv.className = 'config-card';

            const isExpanded = sIdx === 0;
            let bodyHtml = '<div class="form-grid">';

            section.fields.forEach((field, fIdx) => {
                const value = normalizeValue(field.key, data[field.key]);
                const inputId = 'cfg-' + field.key.replace(/[^a-zA-Z0-9]/g, '_');
                const displayValue = getDisplayValue(field.key, value);
                let inputHtml = '';

                if (field.type === 'bool') {
                    const isEnabled = value === true;
                    inputHtml = `<select class="form-control" id="${inputId}" data-key="${field.key}">
                        <option value="true" ${isEnabled ? 'selected' : ''}>启用</option>
                        <option value="false" ${!isEnabled ? 'selected' : ''}>禁用</option>
                    </select>`;
                } else if (field.type === 'password') {
                    inputHtml = `<input type="password" class="form-control" id="${inputId}" value="${window.esc(String(displayValue))}" data-key="${field.key}" placeholder="请输入密钥">`;
                } else if (field.type === 'list') {
                    inputHtml = `<input type="text" class="form-control" id="${inputId}" value="${window.esc(displayValue)}" data-key="${field.key}" placeholder="多个值用英文逗号分隔">`;
                } else if (field.type === 'json') {
                    const rows = field.rows || 5;
                    inputHtml = `<textarea class="form-control" id="${inputId}" data-key="${field.key}" rows="${rows}">${window.esc(displayValue)}</textarea>`;
                } else if (field.type === 'float') {
                    const numVal = typeof displayValue === 'number' ? displayValue.toFixed(1) : (displayValue || '');
                    inputHtml = `<input type="text" class="form-control" id="${inputId}" value="${numVal}" data-key="${field.key}">`;
                } else if (field.type === 'reasoning_effort') {
                    inputHtml = renderReasoningEffortField(inputId, field.key, value);
                } else if (field.type === 'vendor_select') {
                    inputHtml = `<select class="form-control" id="${inputId}" data-key="${field.key}">
                        ${vendorModelData.vendor.map(v => 
                            `<option value="${window.esc(v)}" ${displayValue === v ? 'selected' : ''}>${window.esc(v)}</option>`
                        ).join('')}
                    </select>`;
                } else if (field.type === 'model_select') {
                    inputHtml = `<select class="form-control" id="${inputId}" data-key="${field.key}">
                        ${vendorModelData.model.map(m => 
                            `<option value="${window.esc(m)}" ${displayValue === m ? 'selected' : ''}>${window.esc(m)}</option>`
                        ).join('')}
                    </select>`;
                } else {
                    inputHtml = `<input type="text" class="form-control" id="${inputId}" value="${window.esc(String(displayValue))}" data-key="${field.key}">`;
                }

                if (field.fullWidth) {
                    bodyHtml += `<div class="form-group full-width"><label title="${window.esc(field.label)}">${window.esc(field.label)}</label>${inputHtml}</div>`;
                } else {
                    bodyHtml += `<div class="form-group"><label title="${window.esc(field.label)}">${window.esc(field.label)}</label>${inputHtml}</div>`;
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

        const extraKeys = Object.keys(data).filter(k => !predefinedKeys.has(k));
        if (extraKeys.length > 0) {
            const cardDiv = document.createElement('div');
            cardDiv.className = 'config-card';

            let bodyHtml = '<div class="form-grid">';
            extraKeys.forEach(key => {
                const value = data[key];
                const inputId = 'cfg-' + key.replace(/[^a-zA-Z0-9]/g, '_');
                let displayValue = value;

                if (typeof value === 'object' && value !== null) {
                    displayValue = JSON.stringify(value, null, 2);
                    bodyHtml += `<div class="form-group full-width"><label title="${window.esc(key)}">${window.esc(key)}</label><textarea class="form-control" id="${inputId}" data-key="${key}" rows="4">${window.esc(displayValue)}</textarea></div>`;
                } else {
                    bodyHtml += `<div class="form-group full-width"><label title="${window.esc(key)}">${window.esc(key)}</label><input type="text" class="form-control" id="${inputId}" value="${window.esc(String(displayValue ?? ''))}" data-key="${key}"></div>`;
                }
            });
            bodyHtml += '</div>';

            cardDiv.innerHTML =
                '<div class="config-header" onclick="toggleCard(this)">' +
                    '<span>其他配置</span>' +
                    '<i class="fas fa-chevron-down"></i>' +
                '</div>' +
                '<div class="config-body">' +
                    bodyHtml +
                '</div>';

            container.appendChild(cardDiv);
        }
    }

    function parseConfigValue(str, key) {
        if (str === "true") return true;
        if (str === "false") return false;
        if (str.includes('.') && !isNaN(parseFloat(str)) && isFinite(str)) {
            return parseFloat(str);
        }
        if (/^-?\d+$/.test(str)) {
            return parseInt(str, 10);
        }
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
                const response = await axios.get('/api/config');
                globalConfigData = response.data;
                reasoningAutoInject = response.data['XINHAI_REASONING_AUTO_INJECT'] === true;
                renderConfig(response.data);
                showStatus('配置加载成功', 'success');
            } catch (error) {
                showStatus(`加载失败: ${error.response?.data?.detail || error.message}`, 'error');
            }
        });

        saveBtn?.addEventListener('click', async () => {
            if (!globalConfigData) return showStatus('请先加载配置', 'error');

            const inputs = document.querySelectorAll('#configContainer [data-key]');
            const newConfig = {};

            // 辅助函数：根据 key 获取对应的 label
            const getLabel = (key) => {
                for (const section of CONFIG_SECTIONS) {
                    const field = section.fields.find(f => f.key === key);
                    if (field) return field.label;
                }
                return key; // 兜底
            };

            // 先处理 reasoning_effort 类型
            const reasoningContainers = document.querySelectorAll('.reasoning-effort-container');
            reasoningContainers.forEach(container => {
                const key = container.dataset.key;
                const result = {};
                const checkboxes = container.querySelectorAll('.reasoning-type-checkbox');

                checkboxes.forEach(checkbox => {
                    if (checkbox.checked) {
                        const type = checkbox.dataset.type;
                        const select = container.querySelector(`.reasoning-effort-select[data-type="${type}"]`);
                        result[type] = select ? select.value : 'low';
                    }
                });

                newConfig[key] = result;
            });

            for (const el of inputs) {
                const key = el.dataset.key;
                const fieldType = FIELD_TYPE_MAP[key];

                // 跳过 reasoning_effort 类型，已经在前面处理过了
                if (fieldType === 'reasoning_effort') continue;

                const rawValue = el.value.trim();

                if (fieldType === 'bool') {
                    newConfig[key] = el.value === 'true';
                } else if (fieldType === 'number') {
                    if (rawValue !== '' && !/^-?\d+$/.test(rawValue)) {
                        showStatus(`❌ "${getLabel(key)}" 包含无效字符，只允许整数`, 'error');
                        return; // 中断保存
                    }
                    newConfig[key] = rawValue === '' ? 0 : parseInt(rawValue, 10);
                } else if (fieldType === 'float') {
                     if (rawValue !== '' && !/^-?\d+\.?\d*$/.test(rawValue)) {
                        showStatus(`❌ "${getLabel(key)}" 包含无效字符，只允许数字`, 'error');
                        return;
                    }
                    newConfig[key] = rawValue === '' ? 0.0 : parseFloat(rawValue);
                } else if (fieldType === 'list') {
                    if (rawValue && rawValue.includes('，')) {
                        // 自动将中文逗号修复为英文逗号
                        const fixedValue = rawValue.replace(/，/g, ',');
                        el.value = fixedValue; // 更新输入框显示
                        showStatus(`🔧 “${getLabel(key)}” 中的中文逗号已自动替换为英文逗号`, 'info', 3000);
                        newConfig[key] = fixedValue.split(',').map(s => s.trim()).filter(Boolean);
                    } else {
                        newConfig[key] = rawValue ? rawValue.split(',').map(s => s.trim()).filter(Boolean) : [];
                    }
                } else if (fieldType === 'json') {
                    if (rawValue) {
                        try {
                            newConfig[key] = JSON.parse(rawValue);
                        } catch (e) {
                            newConfig[key] = {};
                        }
                    } else {
                        newConfig[key] = {};
                    }
                } else {
                    if (rawValue === '') {
                        newConfig[key] = '';
                    } else if (rawValue === 'true') {
                        newConfig[key] = true;
                    } else if (rawValue === 'false') {
                        newConfig[key] = false;
                    } else if (/^-?\d+$/.test(rawValue)) {
                        newConfig[key] = parseInt(rawValue, 10);
                    } else if (/^-?\d+\.\d+$/.test(rawValue)) {
                        newConfig[key] = parseFloat(rawValue);
                    } else if (rawValue.startsWith('{') || rawValue.startsWith('[')) {
                        try {
                            newConfig[key] = JSON.parse(rawValue);
                        } catch (e) {
                            newConfig[key] = rawValue;
                        }
                    } else {
                        newConfig[key] = rawValue;
                    }
                }
            }

            try {
                console.log(newConfig)
                await axios.post('/api/config', newConfig);
                globalConfigData = newConfig;
                showStatus('配置保存成功', 'success');
            } catch (error) {
                showStatus(`保存失败: ${error.response?.data?.detail || error.message}`, 'error');
            }
        });

        loadBtn?.click();

        const toolbar = document.querySelector('.page-actions');
        const targetBtn = document.getElementById('loadBtn');

        if (toolbar) {
            if (window.__bikeAnim) window.__bikeAnim.destroy();
            window.__bikeAnim = new BikeAnimation({
                container: toolbar,
                anchorElement: targetBtn,
                offsetStart: -930,
                offsetEnd: 330,
                duration: 12000,
                verticalOffset: 35
            });
        }
    });

    window.addEventListener('DOMContentLoaded', () => {
        initSSEForNotifications();
    });
})();