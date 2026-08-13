(function () {
    let currentFile = null;
    let fullTreeData = null;
    let isEditing = false;
    let currentAudioPlayer = null;
    let currentPlayingId = null;
    let currentTab = 'files';
    const audioDurations = {};

    const SUPPORTED_TEXT_EXT = ['txt', 'text', 'json', 'js', 'py', 'md', 'html', 'htm', 'css', 'xml', 'yml', 'yaml', 'log', 'lrc'];
    const SUPPORTED_IMAGE_EXT = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'];

    const ARROW_RIGHT = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16"><path fill="#000" fill-rule="evenodd" d="m10.207 8l-3.854 3.854l-.707-.707L8.793 8L5.646 4.854l.707-.708z" clip-rule="evenodd"/></svg>`;
    const ARROW_DOWN = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16"><path fill="#000" fill-rule="evenodd" d="m8 10.207l3.854-3.853l-.707-.708L8 8.793L4.854 5.646l-.708.708z" clip-rule="evenodd"/></svg>`;
    const IMAGE_ICON = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"><path fill="#666" d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/></svg>`;

    function $(id) { return document.getElementById(id); }

    function getRightmostVisibleBtn(toolbar) {
      const btns = Array.from(toolbar.querySelectorAll('.Btn'));
      const visibleBtns = btns.filter(btn =>
        btn.style.display !== 'none' && btn.offsetParent !== null
      );
      if (visibleBtns.length === 0) return null;
      return visibleBtns.reduce((max, btn) =>
        btn.getBoundingClientRect().right > max.getBoundingClientRect().right ? btn : max
      );
    }

    function escapeHtml(text) {
      if (text == null) return '';
      return text.replace(/[&<>"']/g, m =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m])
      );
    }

    function updateToolbarButtons(tabName) {
      const editBtn = $('editBtn');
      const saveBtn = $('saveBtn');
      const uploadImageBtn = $('uploadImageBtn');
      const uploadAudioBtn = $('uploadAudioBtn');
      const uploadLyricBtn = $('uploadLyricBtn');

      if (tabName === 'files') {
        editBtn.style.display = 'flex';
        saveBtn.style.display = 'flex';
        uploadImageBtn.style.display = 'none';
        uploadAudioBtn.style.display = 'none';
        uploadLyricBtn.style.display = 'none';
      } else if (tabName === 'images') {
        editBtn.style.display = 'none';
        saveBtn.style.display = 'none';
        uploadImageBtn.style.display = 'flex';
        uploadAudioBtn.style.display = 'none';
        uploadLyricBtn.style.display = 'none';
      } else if (tabName === 'audios') {
        editBtn.style.display = 'none';
        saveBtn.style.display = 'none';
        uploadImageBtn.style.display = 'none';
        uploadAudioBtn.style.display = 'flex';
        uploadLyricBtn.style.display = 'flex';
      }
    }

    async function fetchTree() {
      try {
        const res = await fetch('/api/tree');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const treeData = await res.json();
        fullTreeData = treeData;
        renderTree(treeData, $('treePanel'));
      } catch (e) {
        showStatus('目录加载失败: ' + e.message, 'error');
        $('treePanel').innerHTML = '<div class="empty-state"><div class="icon">📁</div><div class="text">目录加载失败</div></div>';
      }
    }

    function renderTree(nodes, container) {
      container.innerHTML = '';
      nodes.forEach(node => {
        const nodeDiv = document.createElement('div');
        nodeDiv.className = `tree-node ${node.type}`;
        nodeDiv.dataset.path = node.key;
        nodeDiv.dataset.ext = node.ext || '';

        const toggleBtn = document.createElement('span');
        toggleBtn.className = 'toggle-icon';
        if (node.type === 'folder') {
          toggleBtn.innerHTML = ARROW_RIGHT;
          toggleBtn.style.cursor = 'pointer';
        } else {
          toggleBtn.innerHTML = '';
          toggleBtn.style.visibility = 'hidden';
        }

        const iconSpan = document.createElement('span');
        iconSpan.className = 'node-icon';
        if (node.type === 'folder') {
          iconSpan.innerHTML = '📁';
        } else {
          iconSpan.innerHTML = '📄';
        }

        const labelSpan = document.createElement('span');
        labelSpan.className = 'node-label';
        labelSpan.textContent = node.label;

        nodeDiv.appendChild(toggleBtn);
        nodeDiv.appendChild(iconSpan);
        nodeDiv.appendChild(labelSpan);

        container.appendChild(nodeDiv);

        if (node.type === 'folder') {
          const subContainer = document.createElement('div');
          subContainer.className = 'tree-children';
          subContainer.style.display = 'none';
          container.appendChild(subContainer);

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

        if (node.type === 'file') {
          nodeDiv.addEventListener('click', () => {
            document.querySelectorAll('.tree-node').forEach(el => el.classList.remove('active'));
            nodeDiv.classList.add('active');
            loadFile(node.key, node.label, node.ext);
          });
        }
      });
    }

    async function loadFile(relPath, label, ext) {
      const cleanExt = (ext || '').toLowerCase().replace(/^\./, '');

      if (SUPPORTED_IMAGE_EXT.includes(cleanExt)) {
        showImagePreview(relPath, label);
        return;
      }

      if (!SUPPORTED_TEXT_EXT.includes(cleanExt)) {
        showStatus(`暂不支持查看 .${cleanExt} 格式文件，该类型文件不支持文本操作`, 'warning');
        return;
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
        $('editBtn').disabled = false;
        $('saveBtn').disabled = true;
        isEditing = false;
      } catch (e) {
        showStatus('加载文件失败: ' + e.message, 'error');
      }
    }

    function showImagePreview(relPath, label) {
      const imgUrl = `/api/file?path=${encodeURIComponent(relPath)}`;
      $('editBtn').disabled = true;
      $('saveBtn').disabled = true;

      $('fileView').innerHTML = `
        <div class="image-preview-container">
          <div class="image-preview-header">
            <h3>${escapeHtml(label)}</h3>
            <p class="image-path">/data/${escapeHtml(relPath)}</p>
          </div>
          <div class="image-preview-content">
            <img src="${imgUrl}" alt="${escapeHtml(label)}" class="preview-image">
          </div>
        </div>
      `;

      const contentArea = document.querySelector('.content-area');
      if (contentArea) contentArea.scrollTop = 0;

      window.scrollTo({ top: 450, behavior: 'smooth' });
    }

    function showFileContent(label, ext, path, content) {
      const meta = `
        <div class="file-meta">
          <p><strong>路径：</strong><span class="file-path">/data/${escapeHtml(path)}</span></p>
          <p><strong>类型：</strong><span class="file-type">${escapeHtml(ext)}</span></p>
        </div>
      `;

      $('fileView').innerHTML = `
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
        iframe.style.minHeight = '500px';
        iframe.sandbox.add('allow-same-origin', 'allow-scripts', 'allow-popups-to-escape-sandbox');
        body.appendChild(iframe);

        const doc = iframe.contentDocument || iframe.contentWindow.document;
        if (doc) {
          doc.open();
          doc.write(content);
          doc.close();
        } else {
          iframe.src = 'data:text/html;charset=utf-8,' + encodeURIComponent(content);
        }
      } else {
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

      const closeBtn = document.querySelector('.close-btn');
      if (closeBtn) {
        closeBtn.onclick = clearFileView;
      }

      const contentArea = document.querySelector('.content-area');
      if (contentArea) contentArea.scrollTop = 0;

      window.scrollTo({ top: 450, behavior: 'smooth' });
    }

    function clearFileView() {
      $('fileView').innerHTML = `<div class="placeholder">👈 选择左侧文件查看内容</div>`;
      document.querySelectorAll('.tree-node').forEach(el => el.classList.remove('active'));
      $('editBtn').disabled = true;
      $('saveBtn').disabled = true;
      isEditing = false;
    }

    function toggleEdit() {
      if (!currentFile) {
        showStatus('请先选择一个文件！', 'warning');
        return;
      }

      if (isEditing) return;

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
          message: `您正在尝试编辑日志文件：/data/${currentFile.path}。日志由系统自动生成，手动修改可能破坏问题定位。确定要继续编辑吗？`,
          confirmText: '继续编辑',
          onConfirm: () => {
            createEditableTextarea(codeBlock);
          }
        });
        return;
      }

      createEditableTextarea(codeBlock);
    }

    function createEditableTextarea(codeBlock) {
      const lines = currentFile.content.split('\n').length;
      const lineHeight = 20;
      const minRows = 10;
      const maxRows = 50;
      const visibleRows = Math.min(Math.max(lines, minRows), maxRows);
      const height = `${visibleRows * lineHeight + 30}px`;

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
        resize: 'vertical',
        outline: 'none',
        width: '100%',
        boxSizing: 'border-box',
        height: height,
        minHeight: '200px',
        maxHeight: '70vh'
      });

      codeBlock.replaceWith(textarea);
      isEditing = true;
      $('editBtn').disabled = true;
      $('saveBtn').disabled = false;
      textarea.focus();
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);
      textarea.scrollTop = textarea.scrollHeight;
    }

    async function saveFile() {
      if (!currentFile || !isEditing) return;

      const saveBtn = $('saveBtn');
      if (saveBtn.disabled) return;

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
          let errorMsg;
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
        $('editBtn').disabled = false;
        saveBtn.disabled = true;
        showStatus('保存成功！', 'success');
      } catch (e) {
        showStatus('保存失败：' + e.message, 'error');
        saveBtn.disabled = false;
      } finally {
        saveBtn.querySelector('.text').textContent = originalText;
      }
    }

    window.addEventListener('beforeunload', (e) => {
      if (isEditing) {
        e.preventDefault();
        e.returnValue = '当前有未保存的更改，确定离开？';
      }
    });

    function switchTab(tabName) {
      currentTab = tabName;

      document.querySelectorAll('.tab-item').forEach(el => el.classList.remove('active'));
      document.querySelector(`.tab-item[data-tab="${tabName}"]`).classList.add('active');

      document.querySelectorAll('.tab-panel').forEach(el => el.classList.remove('active'));
      document.querySelector(`.tab-panel[data-tab="${tabName}"]`).classList.add('active');

      document.querySelectorAll('.view-panel').forEach(el => el.classList.remove('active'));
      const viewId = tabName === 'images' ? 'imageView' : tabName === 'audios' ? 'audioView' : 'fileView';
      $(viewId).classList.add('active');

      updateToolbarButtons(tabName);

      requestAnimationFrame(() => {
        if (window.__bikeAnim) {
          const toolbar = document.querySelector('.toolbar');
          const rightmostBtn = getRightmostVisibleBtn(toolbar);
          if (rightmostBtn) {
            window.__bikeAnim.anchor = rightmostBtn;
          }
          window.__bikeAnim._init();
        }
      });

      if (tabName === 'images') {
        loadImages();
      } else if (tabName === 'audios') {
        loadAudios();
      }
    }

    async function loadImages() {
      try {
        const res = await fetch('/api/images');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const images = await res.json();
        renderImageSidebar(images);
        renderImages(images);
      } catch (e) {
        showStatus('加载图片失败: ' + e.message, 'error');
        $('imagePanel').innerHTML = '<div class="empty-state"><div class="icon">📷</div><div class="text">加载失败</div></div>';
        $('imageGrid').innerHTML = '<div class="empty-state"><div class="icon">📷</div><div class="text">加载失败</div></div>';
      }
    }

    function renderImageSidebar(images) {
      const panel = $('imagePanel');
      if (!images || images.length === 0) {
        panel.innerHTML = '<div class="empty-state"><div class="text">暂无图片</div></div>';
        return;
      }

      panel.innerHTML = images.sort((a, b) =>
        a.file_name.localeCompare(b.file_name, undefined, {numeric: true, sensitivity: 'base'})
      ).map((img) => `
        <div class="tree-node" data-id="${img.id}" onclick="scrollToImage('${img.id}')">
          <span class="node-icon">${IMAGE_ICON}</span>
          <span class="node-label">${escapeHtml(img.file_name)}</span>
        </div>
      `).join('');
    }

    function renderImages(images) {
      const grid = $('imageGrid');
      if (!images || images.length === 0) {
        grid.innerHTML = `
          <div class="empty-state">
            <div class="text">暂无图片，点击上方上传</div>
          </div>
        `;
        return;
      }

      grid.innerHTML = images.map(img => `
        <div class="image-card" data-id="${img.id}" onclick="previewImage('${img.id}', '${escapeHtml(img.file_name)}')">
          <img src="/media/image/${img.file_name}" alt="${escapeHtml(img.file_name)}" />
          <div class="image-overlay">
            <div class="image-info">${escapeHtml(img.file_name)}</div>
            <div class="image-actions">
              <button class="image-action-btn" onclick="event.stopPropagation(); previewImage('${img.id}', '${escapeHtml(img.file_name)}')">👁</button>
              <button class="image-action-btn" onclick="event.stopPropagation(); deleteImage('${img.id}')">🗑</button>
            </div>
          </div>
        </div>
      `).join('');
    }

    window.scrollToImage = function(id) {
      const imageCard = document.querySelector(`.image-card[data-id="${id}"]`);
      if (imageCard) {
        imageCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
        imageCard.classList.add('highlight');
        setTimeout(() => imageCard.classList.remove('highlight'), 1500);
      }
    };

    window.previewImage = function(id, fileName) {
      const modal = $('imagePreviewModal');
      const img = $('previewImage');
      img.src = `/media/image/${fileName}`;
      img.alt = fileName;
      modal.classList.add('show');
    };

    window.deleteImage = async function(id) {
      showConfirm({
        title: '删除图片',
        message: '确定要删除这张图片吗？此操作不可恢复。',
        confirmText: '删除',
        onConfirm: async () => {
          try {
            const res = await fetch(`/api/images/${id}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('删除失败');
            showStatus('删除成功！', 'success');
            loadImages();
          } catch (e) {
            showStatus('删除失败: ' + e.message, 'error');
          }
        }
      });
    };

    async function loadAudios() {
      try {
        const res = await fetch('/api/audios');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const audios = await res.json();
        renderAudioSidebar(audios);
        renderAudios(audios);
      } catch (e) {
        showStatus('加载音频失败: ' + e.message, 'error');
        $('audioPanel').innerHTML = '<div class="empty-state"><div class="icon">🎵</div><div class="text">加载失败</div></div>';
        $('audioList').innerHTML = '<div class="empty-state"><div class="icon">🎵</div><div class="text">加载失败</div></div>';
      }
    }

    function renderAudioSidebar(audios) {
      const panel = $('audioPanel');
      if (!audios || audios.length === 0) {
        panel.innerHTML = '<div class="empty-state"><div class="text">暂无音频</div></div>';
        return;
      }

      panel.innerHTML = audios.sort((a, b) => (a.title || a.file_name).localeCompare(b.title || b.file_name)).map((audio) => {
        const icon = audio.audio_type === 'tts' ? '🎙️' : '🎵';
        return `
        <div class="tree-node" data-id="${audio.id}" onclick="scrollToAudio('${audio.id}')">
          <span class="node-icon">${icon}</span>
          <span class="node-label">${escapeHtml(audio.title || audio.file_name)}</span>
        </div>
      `;
      }).join('');
    }

    function formatDuration(seconds) {
      if (!seconds || isNaN(seconds)) return '--:--';
      const mins = Math.floor(seconds / 60);
      const secs = Math.floor(seconds % 60);
      return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }

    function renderAudios(audios) {
      const list = $('audioList');
      if (!audios || audios.length === 0) {
        list.innerHTML = `
          <div class="empty-state">
            <div class="text">暂无音频，点击上方上传</div>
          </div>
        `;
        return;
      }

      list.innerHTML = audios.map(audio => {
        const isTts = audio.audio_type === 'tts';
        const isMusic = audio.audio_type === 'music';
        const typeBadge = isTts
          ? '<span style="background: rgba(34, 197, 94, 0.15); color: #16a34a; font-size: 11px; padding: 2px 6px; border-radius: 4px; margin-left: 6px;">TTS</span>'
          : '<span style="background: rgba(245, 158, 11, 0.15); color: #d97706; font-size: 11px; padding: 2px 6px; border-radius: 4px; margin-left: 6px;">音乐</span>';

        // 音乐显示艺人信息，TTS 不显示说话人信息
        const artistInfo = isMusic
          ? `<div class="audio-artist">${escapeHtml(audio.artist || '')}</div>`
          : '';

        // 编辑按钮仅对音乐类型渲染
        const editBtn = isMusic
          ? `<button class="audio-action-btn" onclick="editAudio('${audio.id}')">编辑</button>`
          : '';

        return `
        <div class="audio-item" data-id="${audio.id}" data-url="/media/audio/${escapeHtml(audio.file_name)}">
          <div class="audio-left">
            <button class="audio-play-btn" data-tooltip="播放" onclick="toggleAudio('${audio.id}', '/media/audio/${escapeHtml(audio.file_name)}')">▶</button>
            <div class="audio-info">
              <div class="audio-title">${escapeHtml(audio.title || audio.file_name)}${typeBadge}</div>
              ${artistInfo}
            </div>
          </div>
          <div class="audio-right">
            <div class="audio-duration" id="duration-${audio.id}">${formatDuration(audio.duration)}</div>
            <div class="audio-actions">
              ${editBtn}
              <button class="audio-action-btn" onclick="deleteAudio('${audio.id}')">删除</button>
            </div>
          </div>
          <div class="audio-progress-wrap">
            <div class="audio-progress-bar" id="progress-${audio.id}">
              <div class="audio-progress-fill" id="progress-fill-${audio.id}" style="width:0;"></div>
            </div>
            <span class="audio-progress-time" id="progress-time-${audio.id}">00:00 / ${formatDuration(audio.duration)}</span>
          </div>
        </div>
      `;
      }).join('');

      audios.forEach(audio => {
        if (!audio.duration || audio.duration <= 0) {
          const audioEl = new Audio(`/media/audio/${audio.file_name}`);
          audioEl.addEventListener('loadedmetadata', () => {
            const durationEl = document.getElementById(`duration-${audio.id}`);
            if (durationEl) {
              durationEl.textContent = formatDuration(audioEl.duration);
            }
            audioDurations[audio.id] = audioEl.duration;
            audioEl.remove();
          });
          audioEl.load();
        } else {
          audioDurations[audio.id] = audio.duration;
        }
      });
    }

    window.scrollToAudio = function(id) {
      const audioItem = document.querySelector(`.audio-item[data-id="${id}"]`);
      if (audioItem) {
        audioItem.scrollIntoView({ behavior: 'smooth', block: 'center' });
        audioItem.classList.add('highlight');
        setTimeout(() => audioItem.classList.remove('highlight'), 1500);
      }
    };

    window.toggleAudio = function(id, url) {
      const playBtn = document.querySelector(`.audio-item[data-id="${id}"] .audio-play-btn`);
      const progressFill = document.getElementById(`progress-fill-${id}`);
      const progressTime = document.getElementById(`progress-time-${id}`);
      const durationEl = document.getElementById(`duration-${id}`);

      if (currentPlayingId === id && currentAudioPlayer && !currentAudioPlayer.paused) {
        currentAudioPlayer.pause();
        currentAudioPlayer = null;
        currentPlayingId = null;
        playBtn.classList.remove('playing');
        playBtn.textContent = '▶';
        playBtn.setAttribute('data-tooltip', '播放');
        return;
      }

      document.querySelectorAll('.audio-play-btn.playing').forEach(btn => {
        btn.classList.remove('playing');
        btn.textContent = '▶';
        btn.setAttribute('data-tooltip', '播放');
      });

      document.querySelectorAll('.audio-progress-fill').forEach(fill => {
        fill.style.width = '0%';
      });
      document.querySelectorAll('.audio-progress-time').forEach(time => {
        const durEl = time.parentElement.previousElementSibling?.querySelector('.audio-duration');
        time.textContent = `00:00 / ${durEl?.textContent || '--:--'}`;
      });

      if (currentAudioPlayer) {
        currentAudioPlayer.pause();
      }

      currentAudioPlayer = new Audio(url);
      currentPlayingId = id;

      currentAudioPlayer.ontimeupdate = function() {
        if (currentPlayingId === id && progressFill && progressTime) {
          const duration = currentAudioPlayer.duration || audioDurations[id] || 0;
          if (duration && duration > 0) {
            const percent = (currentAudioPlayer.currentTime / duration) * 100;
            progressFill.style.width = `${Math.min(percent, 100)}%`;
            progressTime.textContent = `${formatDuration(currentAudioPlayer.currentTime)} / ${formatDuration(duration)}`;
          }
        }
      };

      currentAudioPlayer.onended = () => {
        currentAudioPlayer = null;
        currentPlayingId = null;
        playBtn.classList.remove('playing');
        playBtn.textContent = '▶';
        playBtn.setAttribute('data-tooltip', '播放');
        if (progressFill) progressFill.style.width = '0%';
        if (progressTime && durationEl) progressTime.textContent = `00:00 / ${durationEl.textContent}`;
      };

      currentAudioPlayer.play().then(() => {
        playBtn.classList.add('playing');
        playBtn.textContent = '⏸';
        playBtn.setAttribute('data-tooltip', '暂停');
      }).catch(e => {
        showStatus('播放失败: ' + e.message, 'error');
        currentAudioPlayer = null;
        currentPlayingId = null;
      });
    };

    let currentEditAudioId = null;

    window.editAudio = async function(id) {
      try {
        const res = await fetch(`/api/audios/${id}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const audio = await res.json();

        currentEditAudioId = id;
        $('editTitle').value = audio.title || '';
        $('editArtist').value = audio.artist || '';
        $('audioEditModal').classList.add('show');
      } catch (e) {
        showStatus('加载音频信息失败: ' + e.message, 'error');
      }
    };

    window.deleteAudio = async function(id) {
      showConfirm({
        title: '删除音频',
        message: '确定要删除这首音频吗？此操作不可恢复。',
        confirmText: '删除',
        onConfirm: async () => {
          try {
            const res = await fetch(`/api/audios/${id}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('删除失败');
            showStatus('删除成功！', 'success');
            if (currentPlayingId === id && currentAudioPlayer) {
              currentAudioPlayer.pause();
              currentAudioPlayer = null;
              currentPlayingId = null;
            }
            loadAudios();
          } catch (e) {
            showStatus('删除失败: ' + e.message, 'error');
          }
        }
      });
    };

    let _imageUploadCount = 0;
    let _imageUploadTotal = 0;
    let _imageUploadSuccess = 0;
    let _imageUploadFailed = 0;
    let _imageUploadTimer = null;

    function handleImageUpload(files) {
      if (!files || files.length === 0) return;

      const uploadBtn = $('uploadImageBtn');
      uploadBtn.disabled = true;

      _imageUploadTotal = files.length;
      _imageUploadCount = 0;
      _imageUploadSuccess = 0;
      _imageUploadFailed = 0;

      showStatus({ message: `正在上传 ${_imageUploadTotal} 张图片...`, type: 'info', duration: 5000 });

      Array.from(files).forEach(file => {
        const formData = new FormData();
        formData.append('file', file);

        fetch('/api/images/upload', {
          method: 'POST',
          body: formData
        }).then(res => {
          if (!res.ok) throw new Error('上传失败');
          return res.json();
        }).then(data => {
          _imageUploadSuccess++;
        }).catch(e => {
          _imageUploadFailed++;
        }).finally(() => {
          _imageUploadCount++;
          if (_imageUploadCount >= _imageUploadTotal) {
            uploadBtn.disabled = false;
            if (_imageUploadSuccess > 0 && _imageUploadFailed === 0) {
              showStatus(`全部 ${_imageUploadSuccess} 张图片上传成功！`, 'success', 5000);
            } else if (_imageUploadSuccess > 0 && _imageUploadFailed > 0) {
              showStatus(`上传完成：成功 ${_imageUploadSuccess} 张，失败 ${_imageUploadFailed} 张`, 'warning', 5000);
            } else {
              showStatus(`全部 ${_imageUploadFailed} 张图片上传失败`, 'error', 5000);
            }
            if (_imageUploadTimer) clearTimeout(_imageUploadTimer);
            _imageUploadTimer = setTimeout(() => {
              loadImages();
            }, 300);
          }
        });
      });
    }

    function handleAudioUpload(files) {
      if (!files || files.length === 0) return;

      const uploadBtn = $('uploadAudioBtn');
      uploadBtn.disabled = true;

      const formData = new FormData();
      Array.from(files).forEach(file => {
        formData.append('files', file);
      });

      fetch('/api/audios/upload', {
        method: 'POST',
        body: formData
      }).then(res => {
        if (!res.ok) throw new Error('上传失败');
        return res.json();
      }).then(data => {
        if (data.results && data.results.length > 0) {
          const count = data.results.length;
          showStatus(`成功上传 ${count} 个音频文件！`, 'success');
          loadAudios();
        }
      }).catch(e => {
        showStatus('上传失败: ' + e.message, 'error');
      }).finally(() => {
        uploadBtn.disabled = false;
      });
    }

    function handleLyricUpload(files) {
      if (!files || files.length === 0) return;

      const uploadBtn = $('uploadLyricBtn');
      if (uploadBtn) uploadBtn.disabled = true;

      const formData = new FormData();
      Array.from(files).forEach(file => {
        formData.append('files', file);
      });

      fetch('/api/lyrics/upload', {
        method: 'POST',
        body: formData
      }).then(res => {
        if (!res.ok) throw new Error('上传失败');
        return res.json();
      }).then(data => {
        if (data.results && data.results.length > 0) {
          const successCount = data.results.filter(r => r.ok).length;
          const skipCount = data.results.filter(r => !r.ok && r.message.includes('已存在')).length;
          let msg = '';
          if (successCount > 0 && skipCount > 0) {
            msg = `成功上传 ${successCount} 个歌词，跳过 ${skipCount} 个重复文件`;
          } else if (successCount > 0) {
            msg = `成功上传 ${successCount} 个歌词文件！`;
          } else {
            msg = `跳过 ${skipCount} 个重复文件`;
          }
          showStatus(msg, 'success');
        }
        loadAudios();
      }).catch(e => {
        showStatus('上传失败: ' + e.message, 'error');
      }).finally(() => {
        if (uploadBtn) uploadBtn.disabled = false;
      });
    }

    function closeAudioEdit() {
      $('audioEditModal').classList.remove('show');
      currentEditAudioId = null;
    }

    document.addEventListener('DOMContentLoaded', () => {
      $('editBtn').addEventListener('click', toggleEdit);
      $('saveBtn').addEventListener('click', saveFile);

      $('uploadImageBtn').addEventListener('click', () => $('imageFileInput').click());
      $('uploadAudioBtn').addEventListener('click', () => $('audioFileInput').click());
      $('uploadLyricBtn').addEventListener('click', () => $('lyricFileInput').click());

      $('toggleSidebar').addEventListener('click', () => {
        const sidebar = $('sidebar');
        if (sidebar.classList.contains('collapsed')) {
          sidebar.classList.remove('collapsed');
        } else {
          sidebar.classList.add('collapsed');
        }
      });

      updateToolbarButtons('files');

      fetchTree();

      document.querySelectorAll('.tab-item').forEach(tab => {
        tab.addEventListener('click', () => {
          switchTab(tab.dataset.tab);
        });
      });

      const imageUploadZone = $('imageUploadZone');
      const imageFileInput = $('imageFileInput');

      imageUploadZone.addEventListener('click', () => imageFileInput.click());
      imageUploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        imageUploadZone.classList.add('dragover');
      });
      imageUploadZone.addEventListener('dragleave', () => {
        imageUploadZone.classList.remove('dragover');
      });
      imageUploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        imageUploadZone.classList.remove('dragover');
        handleImageUpload(e.dataTransfer.files);
      });
      imageFileInput.addEventListener('change', (e) => {
        handleImageUpload(e.target.files);
        e.target.value = '';
      });

      const audioUploadZone = $('audioUploadZone');
      const audioFileInput = $('audioFileInput');

      audioUploadZone.addEventListener('click', () => audioFileInput.click());
      audioUploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        audioUploadZone.classList.add('dragover');
      });
      audioUploadZone.addEventListener('dragleave', () => {
        audioUploadZone.classList.remove('dragover');
      });
      audioUploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        audioUploadZone.classList.remove('dragover');
        handleAudioUpload(e.dataTransfer.files);
      });
      audioFileInput.addEventListener('change', (e) => {
        handleAudioUpload(e.target.files);
        e.target.value = '';
      });

      const lyricUploadZone = $('lyricUploadZone');
      const lyricFileInput = $('lyricFileInput');

      lyricUploadZone.addEventListener('click', () => lyricFileInput.click());
      lyricUploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        lyricUploadZone.classList.add('dragover');
      });
      lyricUploadZone.addEventListener('dragleave', () => {
        lyricUploadZone.classList.remove('dragover');
      });
      lyricUploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        lyricUploadZone.classList.remove('dragover');
        handleLyricUpload(e.dataTransfer.files);
      });
      lyricFileInput.addEventListener('change', (e) => {
        handleLyricUpload(e.target.files);
        e.target.value = '';
      });

      $('previewClose').addEventListener('click', () => {
        $('imagePreviewModal').classList.remove('show');
      });

      $('previewOverlay').addEventListener('click', () => {
        $('imagePreviewModal').classList.remove('show');
      });

      $('editClose').addEventListener('click', closeAudioEdit);

      $('editOverlay').addEventListener('click', closeAudioEdit);

      $('saveAudioBtn').addEventListener('click', async () => {
        if (!currentEditAudioId) return;

        const title = $('editTitle').value;
        const artist = $('editArtist').value;

        try {
          const res = await fetch(`/api/audios/${currentEditAudioId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, artist })
          });

          if (!res.ok) throw new Error('保存失败');
          showStatus('保存成功！', 'success');
          closeAudioEdit();
          await loadAudios();
        } catch (e) {
          showStatus('保存失败: ' + e.message, 'error');
        }
      });

      $('cancelAudioBtn').addEventListener('click', closeAudioEdit);

      updateToolbarButtons('files');

      const toolbar = document.querySelector('.toolbar');
      const rightmostBtn = getRightmostVisibleBtn(toolbar);
      if (toolbar && rightmostBtn) {
        if (window.__bikeAnim) window.__bikeAnim.destroy();
        window.__bikeAnim = new BikeAnimation({
          container: toolbar,
          anchorElement: rightmostBtn,
          offsetStart: 50,
          offsetEnd: 50,
          duration: 12000,
          verticalOffset: 28
        });
      }
    });
})();