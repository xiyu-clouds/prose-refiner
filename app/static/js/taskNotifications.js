/**
 * 任务通知组件
 * 用于在左下角显示任务执行状态通知
 * 
 * 使用方式：
 * 1. 在 HTML 中添加容器：<div id="task-notifications"></div>
 * 2. 引入脚本：<script src="/static/js/taskNotifications.js"></script>
 * 3. 调用：window.TaskNotifications.add(title, status)
 * 
 * API:
 * - add(title, status) - 添加通知
 * - clear() - 清空所有通知
 * - count() - 获取通知数量
 */
(function(window) {
  const TaskNotifications = {
    MAX_NOTIFICATIONS: 3,
    notifications: [],
    
    init() {
      this.container = document.getElementById('task-notifications');
      if (!this.container) {
        console.warn('[TaskNotifications] #task-notifications 容器不存在');
        return;
      }
      this.ensureStyles();
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

    add(title, status) {
      if (!this.container) {
        this.init();
        if (!this.container) return;
      }

      const now = new Date().toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      });

      const existing = this.notifications.find(n => n.title === title);
      if (existing) {
        existing.time = now;
        existing.status = status;
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
        div.textContent = `${notif.title}  ${notif.time}`;
        div.title = notif.status || notif.title;
        div.style.cursor = 'pointer';
        div.onclick = function() {
          window.location.assign('/novel');
        };
        this.container.appendChild(div);
      });
    },
    
    clear() {
      this.notifications = [];
      this.render();
    },
    
    count() {
      return this.notifications.length;
    }
  };
  
  document.addEventListener('DOMContentLoaded', () => {
    TaskNotifications.init();
  });
  
  window.TaskNotifications = TaskNotifications;
})(window);