(function(window) {
  const TaskNotifications = {
    MAX_NOTIFICATIONS: 3,
    notifications: [],
    eventSource: null,
    reconnectDelay: 3000,
    reconnectTimer: null,

    init() {
      this.container = document.getElementById('task-notifications');
      if (!this.container) {
        console.warn('[TaskNotifications] #task-notifications 容器不存在');
        return;
      }
      this.ensureStyles();
      this.connectSSE();
    },

    ensureStyles() {
      if (document.getElementById('task-notifications-styles')) return;

      const style = document.createElement('style');
      style.id = 'task-notifications-styles';
      style.textContent = `
        #task-notifications {
          display: flex;
          flex-direction: column-reverse;
          gap: 4px;
          width: 100%;
        }
        
        .task-notification-item {
          background: rgba(30, 30, 30, 0.85);
          color: #e0e0e0;
          padding: 4px 10px;
          border-radius: 6px;
          font-size: 12px;
          line-height: 1.3;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          cursor: pointer;
          transition: background-color 0.2s ease, transform 0.2s ease;
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
          max-width: 100%;
        }
        
        .task-notification-item:hover {
          background: rgba(50, 50, 50, 0.95);
          color: #fff;
        }
      `;
      document.head.appendChild(style);
    },

    connectSSE() {
      if (this.eventSource) {
        this.eventSource.close();
      }

      this.eventSource = new EventSource('/api/sse');

      this.eventSource.addEventListener('open', () => {
        console.log('[TaskNotifications] SSE 连接已建立');
        this.reconnectDelay = 3000;
      });

      this.eventSource.addEventListener('message', (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.title && !data.content) {
            const now = new Date().toLocaleTimeString('zh-CN', {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit'
            });
            this.add(data.title, data.title, now);
          }
        } catch (err) {
          console.warn('[TaskNotifications] 解析 SSE 消息失败:', err);
        }
      });

      this.eventSource.addEventListener('error', (e) => {
        console.warn('[TaskNotifications] SSE 连接异常，将重新连接:', e);
        this.eventSource.close();
        this.scheduleReconnect();
      });

      this.eventSource.addEventListener('upload_progress', (e) => {
        try {
          const data = JSON.parse(e.data);
          const now = new Date().toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
          });
          let displayText = data.content || data.title || '上传进度';
          if (data.meta && data.meta.progress !== undefined) {
            displayText += ` [${data.meta.progress}%]`;
          }
          this.add(data.title || '上传进度', displayText, now);
        } catch (err) {
          console.warn('[TaskNotifications] 解析上传进度失败:', err);
        }
      });

      this.eventSource.addEventListener('task_progress', (e) => {
        try {
          const data = JSON.parse(e.data);
          const now = new Date().toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
          });

          let displayText = data.content || data.title || '任务进度';
          if (data.meta) {
            if (data.meta.progress !== undefined) displayText += ` [${data.meta.progress}%]`;
            if (data.meta.success !== undefined) displayText += data.meta.success ? ' ✅' : ' ❌';

            // 双通道通知：如果是重试消息，同步推送到右下角
            if (data.meta.is_retrying && typeof window.showStatus === 'function') {
              window.showStatus({
                message: displayText,
                type: 'warning',
                duration: 15000 // 重试提示保持15秒
              });
            }
          }
          this.add(data.title || '任务进度', displayText, now);
        } catch (err) {
          console.warn('[TaskNotifications] 解析任务进度失败:', err);
        }
      });
    },

    scheduleReconnect() {
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
      }
      this.reconnectTimer = setTimeout(() => {
        this.connectSSE();
      }, this.reconnectDelay);
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
    },

    add(title, status, time = null) {
      if (!this.container) {
        this.init();
        if (!this.container) return;
      }

      const now = time || new Date().toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      });

      const existing = this.notifications.find(n => n.title === title && n.status === status);
      if (existing) {
        existing.time = now;
        this.render();
        return;
      }

      this.notifications.unshift({
        id: Date.now() + Math.random(),
        title: title,
        status: status,
        time: now
      });

      if (this.notifications.length > this.MAX_NOTIFICATIONS) {
        this.notifications.pop();
      }

      this.render();
    },

    render() {
      if (!this.container) return;

      this.container.innerHTML = '';

      this.notifications.forEach(notif => {
        const div = document.createElement('div');
        div.className = 'task-notification-item';
        div.textContent = `${notif.status || notif.title}  ${notif.time}`;
        div.title = notif.title || notif.status;
        div.style.cursor = 'default';
        div.addEventListener('contextmenu', (e) => {
          e.preventDefault();
        });
        this.container.appendChild(div);
      });
    },
    
    clear() {
      this.notifications = [];
      this.render();
    },
    
    count() {
      return this.notifications.length;
    },

    destroy() {
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
      }
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
    }
  };
  
  document.addEventListener('DOMContentLoaded', () => {
    TaskNotifications.init();
  });

  window.addEventListener('beforeunload', () => {
    TaskNotifications.destroy();
  });
  
  window.TaskNotifications = TaskNotifications;
})(window);