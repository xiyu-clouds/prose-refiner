(function () {
    let currentFile = null;
    let fullTreeData = null; // 保存完整树数据
    let isEditing = false;

    const ARROW_RIGHT = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16"><path fill="#000" fill-rule="evenodd" d="m10.207 8l-3.854 3.854l-.707-.707L8.793 8L5.646 4.854l.707-.708z" clip-rule="evenodd"/></svg>`;
    const ARROW_DOWN = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16"><path fill="#000" fill-rule="evenodd" d="m8 10.207l3.854-3.853l-.707-.708L8 8.793L4.854 5.646l-.708.708z" clip-rule="evenodd"/></svg>`;

    document.getElementById('toggleSidebar').addEventListener('click', () => {
      const sidebar = document.getElementById('sidebar');
      if (sidebar.classList.contains('collapsed')) {
        sidebar.classList.remove('collapsed');
      } else {
        sidebar.classList.add('collapsed');
      }
    });

    async function fetchTree() {
      try {
        const res = await fetch('/api/tree');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const treeData = await res.json();
        fullTreeData = treeData; // 保存原始数据
        renderTree(treeData, document.getElementById('treeContainer'));
      } catch (e) {
        document.getElementById('treeContainer').innerHTML =
          '<div style="padding:10px;color:red;">⚠️ 目录加载失败</div>';
      }
    }

    function renderTree(nodes, container) {
      container.innerHTML = '';
      nodes.forEach(node => {
        const nodeDiv = document.createElement('div');
        nodeDiv.className = `tree-node ${node.type}`;
        nodeDiv.dataset.path = node.key;
        nodeDiv.dataset.ext = node.ext || '';

        // === 统一 toggle 占位（对齐关键）===
        const toggleBtn = document.createElement('span');
        toggleBtn.className = 'toggle-icon';
        if (node.type === 'folder') {
          toggleBtn.innerHTML = ARROW_RIGHT;
          toggleBtn.style.cursor = 'pointer';
        } else {
          toggleBtn.innerHTML = ''; // 文件：空内容
          toggleBtn.style.visibility = 'hidden'; // 保留空间但不可见
        }

        // === 图标 ===
        const iconSpan = document.createElement('span');
        iconSpan.className = 'node-icon';
        if (node.type === 'folder') {
          iconSpan.innerHTML = '📁';
        } else {
          iconSpan.innerHTML = '📄';
        }

        // === 标签 ===
        const labelSpan = document.createElement('span');
        labelSpan.className = 'node-label';
        labelSpan.textContent = node.label;

        // === 组装 ===
        nodeDiv.appendChild(toggleBtn);
        nodeDiv.appendChild(iconSpan);
        nodeDiv.appendChild(labelSpan);

        container.appendChild(nodeDiv);

        // === 处理子容器（仅文件夹）===
        if (node.type === 'folder') {
          const subContainer = document.createElement('div');
          subContainer.className = 'tree-children';
          subContainer.style.display = 'none'; // 初始隐藏
          container.appendChild(subContainer); // 作为兄弟节点！

          // 点击 toggle
          toggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isExpanded = subContainer.style.display === 'block';

            if (!isExpanded && !subContainer.hasChildNodes()) {
              renderTree(node.children || [], subContainer);
            }

            if (isExpanded) {
              subContainer.style.display = 'none';
              toggleBtn.innerHTML = ARROW_RIGHT;
            } else {
              subContainer.style.display = 'block';
              toggleBtn.innerHTML = ARROW_DOWN;
            }
          });
        }

        // === 文件点击 ===
        if (node.type === 'file') {
          nodeDiv.addEventListener('click', () => {
            // 你的 loadFile 逻辑
            document.querySelectorAll('.tree-node').forEach(el => el.classList.remove('active'));
            nodeDiv.classList.add('active');
            loadFile(node.key, node.label, node.ext);
          });
        }
      });
    }

    async function loadFile(relPath, label, ext) {
      if (ext.toLowerCase() === 'db') {
        showStatus('不支持加载 .db 格式文件，数据库文件属于二进制文件，无法通过文本编辑器查看', 'warning');
        return; // 直接结束函数，不执行后续请求
      }

      try {
        const res = await fetch(`/api/file?path=${encodeURIComponent(relPath)}`);
        if (!res.ok) {
          const err = await res.json().catch(() => ({detail: '未知错误'}));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        const data = await res.json();
        currentFile = { path: relPath, content: data.content, ext, label };
        showFileContent(label, ext, relPath, data.content);
        // 👇 启用编辑按钮（仅文本类文件）
        const canEdit = ['txt', 'text', 'json', 'js', 'py', 'md', 'html', 'htm', 'css', 'xml', 'yml', 'yaml', 'log'].includes(ext.toLowerCase());
        document.getElementById('editBtn').disabled = !canEdit;
        document.getElementById('saveBtn').disabled = true;
        isEditing = false;
      } catch (e) {
        showStatus('加载文件失败: ' + e.message, 'error');
      }
    }

    function showFileContent(label, ext, path, content) {
      const meta = `
        <div class="file-meta">
          <p><strong>路径：</strong><span class="file-path">/data/${escapeHtml(path)}</span></p>
          <p><strong>类型：</strong><span class="file-type">${escapeHtml(ext)}</span></p>
        </div>
      `;

      // ✅ 统一布局：不设任何高度限制
      document.getElementById('fileView').innerHTML = `
        <div class="file-content-wrapper" style="position: relative; width: 100%;">
          <button class="close-btn" title="关闭文件">×</button>
          <div class="file-title">${escapeHtml(label)}</div>
          ${meta}
          <div class="file-body"></div>
        </div>
      `;
      const body = document.querySelector('#fileView .file-body');
      if (!body) return;

      const isHtml = ['html', 'htm'].includes(ext.toLowerCase());
      if (isHtml) {
        const iframe = document.createElement('iframe');
        iframe.style.width = '100%';
        iframe.style.border = 'none';
        iframe.style.display = 'block';
        iframe.style.minHeight = '500px'; // 最小高度保证可读（可选）

        iframe.sandbox.add('allow-same-origin', 'allow-scripts', 'allow-popups-to-escape-sandbox');
        body.appendChild(iframe);

        // 写入内容
        const doc = iframe.contentDocument || iframe.contentWindow.document;
        if (doc) {
          doc.open();
          doc.write(content);
          doc.close();
        } else {
          // fallback（通常不会触发）
          iframe.src = 'data:text/html;charset=utf-8,' + encodeURIComponent(content);
        }
      } else {
        // ✅ JSON/TXT：直接渲染，让 pre 自然撑高
        let formattedContent = content;
        if (ext === 'json') {
          try {
            const parsed = JSON.parse(content);
            formattedContent = JSON.stringify(parsed, null, 2);
          } catch (e) {}
        }

        const pre = document.createElement('pre');
        pre.className = 'code-block';
        pre.textContent = formattedContent;
        body.appendChild(pre);
      }

      // 绑定关闭
      const closeBtn = document.querySelector('.close-btn');
      if (closeBtn) {
        closeBtn.onclick = clearFileView;
      }
    }

    function clearFileView() {
      document.getElementById('fileView').innerHTML = `
        <div class="placeholder">👈 选择左侧文件查看内容</div>
      `;
      document.querySelectorAll('.tree-node').forEach(el => el.classList.remove('active'));
      document.getElementById('editBtn').disabled = true;
      document.getElementById('saveBtn').disabled = true;
      isEditing = false;
    }

    function escapeHtml(text) {
      if (text == null) return ''; // null, undefined → 空字符串
      return text.replace(/[&<>"']/g, m =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m])
      );
    }

    /**
     * 渲染批量分析结果到内容区（保留侧边栏）
     */
    function renderBatchResultInContentArea(data) {
      const { batch_id, total_tasks, success_count, failed_count, tasks } = data;

      // 构建 HTML
      let html = `
        <div style="padding: 20px; max-width: 900px; margin: 0 auto;">
          <h2 style="color: #4a00e0; margin-bottom: 16px; text-align: center;">📊 批量分析报告</h2>

          <div style="background: #f8f9fa; padding: 16px; border-radius: 8px; margin-bottom: 24px; border-left: 4px solid #4a00e0;">
            <p><strong>批次 ID：</strong><code>${escapeHtml(batch_id)}</code></p>
            <p><strong>总任务数：</strong>${total_tasks}</p>
            <p><strong>成功：</strong><span style="color: green; font-weight: bold;">${success_count}</span> |
               <strong>失败：</strong><span style="color: red; font-weight: bold;">${failed_count}</span></p>
          </div>

          <div style="max-height: calc(100vh - 220px); overflow-y: auto;">
            <table style="width: 100%; border-collapse: collapse; font-size: 14px; background: white; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
              <thead>
                <tr style="background: #e6eeff;">
                  <th style="text-align: left; padding: 10px 12px; border-bottom: 1px solid #ddd; width: 80px;">状态</th>
                  <th style="text-align: left; padding: 10px 12px; border-bottom: 1px solid #ddd;">输入片段（前100字符）</th>
                </tr>
              </thead>
              <tbody>
      `;

      tasks.forEach(task => {
        const statusText = task.status === 'success' ? '✅ 成功' : '❌ 失败';
        const statusColor = task.status === 'success' ? '#27ae60' : '#e74c3c';
        const snippet = escapeHtml(task.input_snippet || '无输入');

        if (task.status === 'success') {
          html += `
            <tr>
              <td style="padding: 10px 12px; border-bottom: 1px solid #eee; color: ${statusColor};">${statusText}</td>
              <td style="padding: 10px 12px; border-bottom: 1px solid #eee;">${snippet}</td>
            </tr>
          `;
        } else {
          const errorMsg = escapeHtml(task.error || '未知错误');
          html += `
            <tr>
              <td style="padding: 10px 12px; border-bottom: 1px solid #eee; color: ${statusColor};">${statusText}</td>
              <td style="padding: 10px 12px; border-bottom: 1px solid #eee;">${snippet}</td>
              <td style="padding: 10px 12px; border-bottom: 1px solid #eee; color: #c0392b; font-size: 13px;">${errorMsg}</td>
            </tr>
          `;
        }
      });

      html += `
              </tbody>
            </table>
          </div>
        </div>
      `;

      // 替换内容区
      document.getElementById('fileView').innerHTML = html;
    }

    function autoShowBatchResultIfAny() {
      const resultId = localStorage.getItem('latest_batch_result_id');
      if (!resultId) return;

      const rawData = localStorage.getItem(`batch_result_${resultId}`);
      if (!rawData) return;

      let result;
      try {
        result = JSON.parse(rawData);
      } catch (e) {
        return;
      }

      // 清除数据（只显示一次）
      localStorage.removeItem('latest_batch_result_id');
      localStorage.removeItem(`batch_result_${resultId}`);

      // 渲染到内容区（不碰 sidebar）
      renderBatchResultInContentArea(result);

      // 可选：高亮 header
      document.querySelector('.header h2').textContent = '心海 · 批量分析结果';
    }

    function toggleEdit() {
      if (!currentFile) {
        showStatus('请先选择一个文件！', 'warning');
        return;
      }

      if (isEditing) return;

      // ✅ 禁止编辑 HTML/HTM
      if (['html', 'htm', 'db'].includes(currentFile.ext.toLowerCase())) {
        showStatus('暂不支持编辑 HTML 文件，如需修改，请本地编辑后再替换对应文件', 'warning');
        return;
      }

      const wrapper = document.querySelector('.file-content-wrapper');
      const codeBlock = wrapper?.querySelector('.code-block');
      if (!codeBlock) return;

      const isLogFile =
        currentFile.path.startsWith('logs/') ||
        currentFile.path.startsWith('logs_fallback/') ||
        currentFile.ext.toLowerCase() === 'log';

      if (isLogFile) {
        showConfirm({
          title: '编辑日志文件',
          message: `您正在尝试编辑日志文件：/data/${currentFile.path}。日志由系统自动生成，手动修改可能破坏定位问题。确定要继续编辑吗？`,
          confirmText: '继续编辑',
          onConfirm: () => {
            // ✅ 计算合理高度
            const lines = currentFile.content.split('\n').length;
            const lineHeight = 20; // 行高（与 font-size + padding 匹配）
            const minRows = 10;
            const maxRows = 50;
            const visibleRows = Math.min(Math.max(lines, minRows), maxRows);
            const height = `${visibleRows * lineHeight + 30}px`; // +padding

            const textarea = document.createElement('textarea');
            textarea.value = currentFile.content;
            textarea.className = 'code-block editable';
            Object.assign(textarea.style, {
              fontFamily: 'Consolas, monospace',
              fontSize: '14px',
              lineHeight: '1.4',
              padding: '14px',
              border: '1px solid #ccc',
              borderRadius: '6px',
              background: '#fff',
              resize: 'vertical', // 允许用户手动拉高（重要！）
              outline: 'none',
              width: '100%',
              boxSizing: 'border-box',
              height: height, // ✅ 动态高度
              minHeight: '200px', // 最小兜底
              maxHeight: '70vh'   // 防止过高
            });

            codeBlock.replaceWith(textarea);
            isEditing = true;
            document.getElementById('editBtn').disabled = true;
            document.getElementById('saveBtn').disabled = false; // ← 关键：启用保存！
            // ✅ 聚焦并滚动到底部（适合日志）
            textarea.focus();
            textarea.setSelectionRange(textarea.value.length, textarea.value.length);
            textarea.scrollTop = textarea.scrollHeight;
          }
        });
        return;
      }

      // ✅ 计算合理高度
      const lines = currentFile.content.split('\n').length;
      const lineHeight = 20; // 行高（与 font-size + padding 匹配）
      const minRows = 10;
      const maxRows = 50;
      const visibleRows = Math.min(Math.max(lines, minRows), maxRows);
      const height = `${visibleRows * lineHeight + 30}px`; // +padding

      const textarea = document.createElement('textarea');
      textarea.value = currentFile.content;
      textarea.className = 'code-block editable';
      Object.assign(textarea.style, {
        fontFamily: 'Consolas, monospace',
        fontSize: '14px',
        lineHeight: '1.4',
        padding: '14px',
        border: '1px solid #ccc',
        borderRadius: '6px',
        background: '#fff',
        resize: 'vertical', // 允许用户手动拉高（重要！）
        outline: 'none',
        width: '100%',
        boxSizing: 'border-box',
        height: height, // ✅ 动态高度
        minHeight: '200px', // 最小兜底
        maxHeight: '70vh'   // 防止过高
      });

      codeBlock.replaceWith(textarea);
      isEditing = true;
      document.getElementById('editBtn').disabled = true;
      document.getElementById('saveBtn').disabled = false; // ← 关键：启用保存！
      // ✅ 聚焦并滚动到底部（适合日志）
      textarea.focus();
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);
      textarea.scrollTop = textarea.scrollHeight;
    }

    async function saveFile() {
      if (!currentFile || !isEditing) return;

      const saveBtn = document.getElementById('saveBtn');
      if (saveBtn.disabled) return; // 防重复点击

      const textarea = document.querySelector('.code-block.editable');
      if (!textarea) return;

      const originalText = saveBtn.querySelector('.text').textContent;
      saveBtn.querySelector('.text').textContent = '保存中...';
      saveBtn.disabled = true;

      const newContent = textarea.value;
      try {
        const res = await fetch(`/api/file?path=${encodeURIComponent(currentFile.path)}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: newContent })
        });

        if (!res.ok) {
          let errorMsg = '未知错误';
          try {
            const errData = await res.json();
            errorMsg = errData.detail || errData.message || '服务器内部错误';
          } catch (e) {
            errorMsg = `HTTP ${res.status}`;
          }
          throw new Error(errorMsg);
        }

        currentFile.content = newContent;
        showFileContent(currentFile.label, currentFile.ext, currentFile.path, newContent);
        isEditing = false;
        document.getElementById('editBtn').disabled = false;
        saveBtn.disabled = true; // 保持禁用
        showStatus('保存成功！', 'success');
      } catch (e) {
        showStatus('保存失败：' + e.message, 'error');
        saveBtn.disabled = false; // ❌ 只在失败时启用
      }finally {
        saveBtn.querySelector('.text').textContent = originalText;
      }
    }

    window.addEventListener('beforeunload', (e) => {
      if (isEditing) {
        e.preventDefault();
        e.returnValue = '当前有未保存的更改，确定离开？';
      }
    });

    document.addEventListener('DOMContentLoaded', () => {
      const editBtn = document.getElementById('editBtn');
      const saveBtn = document.getElementById('saveBtn');

      if (editBtn) editBtn.addEventListener('click', toggleEdit);
      if (saveBtn) saveBtn.addEventListener('click', saveFile);

      // 其他初始化...
      fetchTree();

      autoShowBatchResultIfAny();

      const toolbar = document.querySelector('.toolbar');
      const buttons = toolbar.querySelectorAll('.Btn');
      const lastBtn = buttons.length > 0 ? buttons[buttons.length - 1] : null;

      if (toolbar && lastBtn) {
        if (window.__bikeAnim) {
          window.__bikeAnim.destroy();
        }
        window.__bikeAnim = new BikeAnimation({
          container: toolbar,
          anchorElement: lastBtn,
          offsetStart: 50,
          offsetEnd: 50,
          duration: 12000,
          verticalOffset: 35
        });
      }
    });

    window.addEventListener('DOMContentLoaded', () => {
        initSSEForNotifications();
    });
})();