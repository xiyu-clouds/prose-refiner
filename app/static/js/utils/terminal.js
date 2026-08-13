class Terminal {
    constructor(modalBox) {
        this.modalBox = modalBox;
        this.container = null;
        this.logBox = null;
        this.eventSource = null;
        this.reconnectDelay = 3000;
        this.reconnectTimer = null;
        this.logs = [];
        this.eventIds = new Set();
        this.MAX_LOGS = 1000;
        this.init();
    }

    async init(isRestore = false, isCrossPage = false) {
        this.container = this.modalBox.querySelector('#terminal-container');
        this.logBox = this.modalBox.querySelector('#progressLog');

        if (!this.container || !this.logBox) return;
        this.bindEvents();

        if (!isRestore) {
            await this.loadHistory();
            this.addLogEntry('info', { title: '正在连接 SSE 服务...', content: '' });
            this.connectSSE();
        } else if (isCrossPage) {
            await this.loadHistory();
            if (!this.eventSource || this.eventSource.readyState !== EventSource.OPEN) {
                this.addLogEntry('info', { title: '正在连接 SSE 服务...', content: '' });
                this.connectSSE();
            }
        } else {
            this.renderLogs();
        }
    }

    formatLogEntry(eventType, data) {
        const parsedData = typeof data === 'string' ? JSON.parse(data) : data;
        const { title, content, meta } = parsedData;

        const iconMap = {
            'upload_progress': '📤',
            'task_progress': '⚡',
            'feature_model_download_progress': '📥',
            'message': '📌',
            'info': 'ℹ️',
            'error': '❌'
        };
        const icon = iconMap[eventType] || '📌';

        let message = `${icon} ${title || ''}`;
        if (content) message += ` | ${content}`;

        if (meta) {
            if (meta.progress !== undefined) message += ` [${meta.progress}%]`;
            if (meta.success !== undefined) message += meta.success ? ' ✅' : ' ❌';
        }

        return message;
    }

    renderLogs() {
        if (!this.logBox) return;
        this.logBox.innerHTML = '';
        this.logs.forEach(log => {
            const logLine = document.createElement('div');
            logLine.className = `log-line ${log.eventType}`;
            const message = this.formatLogEntry(log.eventType, log.data);
            logLine.innerHTML = `[${log.timestamp}] ${message}`;
            this.logBox.appendChild(logLine);
        });
        this.logBox.scrollTop = this.logBox.scrollHeight;
    }

    bindEvents() {
        const clearBtn = this.modalBox.querySelector('#terminal-clear');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                this.clear();
            });
        }
        this.logBox.addEventListener('contextmenu', (e) => {
            e.preventDefault();
        });
    }

    clear() {
        this.logs = [];
        this.eventIds.clear();
        this.logBox.innerHTML = '<div style="color: #64748b;">终端日志已清空</div>';
    }

    async loadHistory() {
        try {
            const response = await fetch('/api/sse/history', {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' },
            });

            if (!response.ok) throw new Error('Failed to load history');

            const data = await response.json();
            if (data.ok && data.history && Array.isArray(data.history)) {
                this.logs = data.history.map(item => {
                    const parsedData = typeof item.data === 'string' ? JSON.parse(item.data) : item.data;
                    if (parsedData.id) {
                        this.eventIds.add(parsedData.id);
                    } else {
                        const fallbackId = `${item.event}-${parsedData.title}-${parsedData.content}`;
                        this.eventIds.add(fallbackId);
                    }
                    let timestamp = item.timestamp;
                    if (timestamp) {
                        timestamp = timestamp.replace(/\//g, '-');
                        const yearMatch = timestamp.match(/^(\d{4})-/);
                        if (yearMatch) {
                            timestamp = timestamp.slice(yearMatch[0].length);
                        }
                    }
                    return {
                        eventType: item.event,
                        data: item.data,
                        timestamp: timestamp
                    };
                });
                this.renderLogs();
            }
        } catch (error) {
            console.warn('Failed to load SSE history:', error);
        }
    }

    connectSSE() {
        if (this.eventSource) {
            this.eventSource.close();
        }

        this.eventSource = new EventSource('/api/sse');

        this.eventSource.addEventListener('open', () => {
            this.addLogEntry('info', { title: 'SSE 连接已建立', content: '全局事件监听已就绪' });
            this.reconnectDelay = 3000;
        });

        this.eventSource.addEventListener('message', (e) => {
            try {
                const data = JSON.parse(e.data);
                this.addLogEntry('message', data);
            } catch (err) {
                console.warn('解析 SSE 消息失败:', err);
            }
        });

        this.eventSource.addEventListener('error', (e) => {
            this.addLogEntry('error', { title: 'SSE 连接异常', content: '将重新连接...' });
            this.eventSource.close();
            this.scheduleReconnect();
        });

        this.eventSource.addEventListener('upload_progress', (e) => {
            try {
                const data = JSON.parse(e.data);
                this.addLogEntry('upload_progress', data);
            } catch (err) {
                console.warn('解析上传进度失败:', err);
            }
        });

        this.eventSource.addEventListener('task_progress', (e) => {
            try {
                const data = JSON.parse(e.data);
                this.addLogEntry('task_progress', data);
            } catch (err) {
                console.warn('解析任务进度失败:', err);
            }
        });

        this.eventSource.addEventListener('feature_model_download_progress', (e) => {
            try {
                const data = JSON.parse(e.data);
                this.addLogEntry('feature_model_download_progress', data);
            } catch (err) {
                console.warn('解析模型下载进度失败:', err);
            }
        });

        this.eventSource.addEventListener('connection_start', (e) => {
            try {
                const data = JSON.parse(e.data);
                this.addLogEntry('info', data);
            } catch (err) {
                console.warn('解析连接事件失败:', err);
            }
        });
    }

    scheduleReconnect() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
        }
        this.reconnectTimer = setTimeout(() => {
            this.connectSSE();
        }, this.reconnectDelay);
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
    }

    addLogEntry(eventType, data, timestamp = null) {
        const parsedData = typeof data === 'string' ? JSON.parse(data) : data;

        const messageId = parsedData.id || `${eventType}-${parsedData.title}-${parsedData.content}`;

        if (this.eventIds.has(messageId)) {
            return;
        }
        this.eventIds.add(messageId);

        const displayTime = timestamp || new Date().toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        }).replace(/\//g, '-').replace(/^\d{4}-/, '');

        const logLine = document.createElement('div');
        logLine.className = `log-line ${eventType}`;
        const message = this.formatLogEntry(eventType, data);
        logLine.innerHTML = `[${displayTime}] ${message}`;

        this.logs.push({ eventType, data, timestamp: displayTime });
        if (this.logs.length > this.MAX_LOGS) {
            const removed = this.logs.shift();
            if (removed) {
                const removedData = typeof removed.data === 'string' ? JSON.parse(removed.data) : removed.data;
                if (removedData.id) {
                    this.eventIds.delete(removedData.id);
                }
            }
        }

        this.logBox.appendChild(logLine);
        this.logBox.scrollTop = this.logBox.scrollHeight;
    }

    destroy() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        this.logs = [];
        this.eventIds = new Set();
    }
}

function showTerminal() {
    const taskId = 'terminal-task';

    const baseOptions = {
        url: '/static/components/terminal.html',
        title: '',
        width: 800,
        height: 560,
        minimizable: true,
        closable: true
    };

    const modal = window.showModal({
        ...baseOptions,
        onMinimize: window.createMinimizableHandler(
            '终端日志 · 点击恢复',
            () => {
                document.body.appendChild(modal.overlay);
                modal.overlay.style.display = 'flex';
                modal.overlay.style.opacity = '1';
                modal.modalBox.style.opacity = '1';
                modal.modalBox.style.transform = 'scale(1)';
                if (window.Terminal) {
                    window.Terminal.modalBox = modal.modalBox;
                    window.Terminal.renderLogs();
                }
            },
            {
                id: taskId,
                modalOptions: baseOptions,
                message: '终端日志 · 点击恢复'
            }
        ),
        onCloseAttempt: () => {
            return new Promise((resolve) => {
                window.showConfirm({
                    title: '关闭终端日志',
                    message: '确定要关闭终端日志吗？关闭后当前会话日志将丢失。',
                    confirmText: '关闭',
                    cancelText: '取消',
                    onConfirm: () => resolve(true),
                    onCancel: () => resolve(false)
                });
            });
        },
        onLoad: (modalBox) => {
            if (!window.Terminal) {
                window.Terminal = new Terminal(modalBox);
            } else {
                window.Terminal.modalBox = modalBox;
                window.Terminal.init(true);
            }
        },
        onUnload: () => {
            if (window.Terminal && typeof window.Terminal.destroy === 'function') {
                window.Terminal.destroy();
            }
            window.Terminal = null;
        }
    });

    modal.overlay.dataset.taskId = taskId;
}

window.showTerminal = showTerminal;