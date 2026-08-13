let uploadedFiles = [];

const WORK_ICON_LIST = ['fa-file-alt', 'fa-file-text', 'fa-book', 'fa-book-open', 'fa-scroll', 'fa-feather-alt', 'fa-edit', 'fa-pen-square'];

function initWorkPage() {
  initUploadHandlers();
  loadWorks();
}

async function loadWorks() {
  const sidebarContent = document.getElementById('sidebarContent');
  if (!sidebarContent) return;

  try {
    const works = await NovelAPI.getWorks();
    const list = works || [];
    renderWorkList(list);
    showStatus(`查询作品成功，共 ${list.length} 个作品`, 'success');
  } catch (err) {
    if (err && err.__isCancel) return;
    console.error('加载作品列表失败:', err);
    showStatus('加载作品列表失败: ' + (err.message || '未知错误'), 'error');
    sidebarContent.innerHTML = '<div class="empty-hint"><i class="fas fa-exclamation-triangle"></i><span>加载失败，请刷新重试</span></div>';
  }
}

function renderWorkList(works) {
  const sidebarContent = document.getElementById('sidebarContent');
  if (!sidebarContent) return;

  if (!works || works.length === 0) {
    sidebarContent.innerHTML = '<div class="empty-hint"><i class="fas fa-book-open"></i><span>暂无作品</span></div>';
    return;
  }

  sidebarContent.innerHTML = '<div class="work-list"></div>';
  const workList = sidebarContent.querySelector('.work-list');

  works.forEach((work, index) => {
    const workItem = buildWorkItemElement(work, index);
    workList.appendChild(workItem);
  });
}

function buildWorkItemElement(work, index) {
  const sessionId = work.session_id;
  const title = work.title || '未命名作品';
  const iconClass = WORK_ICON_LIST[index % WORK_ICON_LIST.length];
  const displayTitle = title.length > 4 ? title.slice(0, 4) + '…' : title;

  const workItem = document.createElement('div');
  workItem.className = 'work-item';
  workItem.id = sessionId;
  workItem.setAttribute('data-title', escapeHtml(title));

  workItem.innerHTML = `
    <div class="work-header" onclick="toggleWorkExpand('${escapeAttr(sessionId)}')">
      <div class="work-info">
        <div class="work-item-icon"><i class="fas ${iconClass}"></i></div>
        <div class="work-item-name">${escapeHtml(displayTitle)}</div>
      </div>
      <div class="work-actions">
        <button class="work-action-btn edit-btn" onclick="event.stopPropagation(); editWorkTitle('${escapeAttr(sessionId)}')" title="编辑作品名称">
          <i class="fas fa-edit"></i>
        </button>
        <button class="work-action-btn delete-btn" onclick="event.stopPropagation(); deleteWork('${escapeAttr(sessionId)}')" title="删除作品">
          <i class="fas fa-trash"></i>
        </button>
        <i class="fas fa-chevron-right expand-icon" title="展开/折叠"></i>
      </div>
    </div>
    <div class="work-steps" id="${escapeAttr(sessionId)}_steps">
      <div class="step-item step-active" data-step="0" onclick="handleStepClick('${escapeAttr(sessionId)}', 0)">
        <span class="step-num">1</span>
        <span class="step-name">立基</span>
        <span class="step-status"><i class="fas fa-play"></i></span>
      </div>
      <div class="step-item step-locked" data-step="1" onclick="handleStepClick('${escapeAttr(sessionId)}', 1)">
        <span class="step-num">2</span>
        <span class="step-name">织网</span>
        <span class="step-status"><i class="fas fa-lock"></i></span>
      </div>
      <div class="step-item step-locked" data-step="2" onclick="handleStepClick('${escapeAttr(sessionId)}', 2)">
        <span class="step-num">3</span>
        <span class="step-name">谋篇</span>
        <span class="step-status"><i class="fas fa-lock"></i></span>
      </div>
      <div class="step-item step-locked" data-step="3" onclick="handleStepClick('${escapeAttr(sessionId)}', 3)">
        <span class="step-num">4</span>
        <span class="step-name">分卷</span>
        <span class="step-status"><i class="fas fa-lock"></i></span>
      </div>
      <div class="step-item step-locked" data-step="4" onclick="handleStepClick('${escapeAttr(sessionId)}', 4)">
        <span class="step-num">5</span>
        <span class="step-name">定章</span>
        <span class="step-status"><i class="fas fa-lock"></i></span>
      </div>
      <div class="step-item step-locked" data-step="5" onclick="handleStepClick('${escapeAttr(sessionId)}', 5)">
        <span class="step-num">6</span>
        <span class="step-name">推演</span>
        <span class="step-status"><i class="fas fa-lock"></i></span>
      </div>
      <div class="step-item step-locked" data-step="6" onclick="handleStepClick('${escapeAttr(sessionId)}', 6)">
        <span class="step-num">7</span>
        <span class="step-name">成文</span>
        <span class="step-status"><i class="fas fa-lock"></i></span>
      </div>
    </div>
  `;

  return workItem;
}

function escapeAttr(str) {
  if (!str) return '';
  return String(str).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function initUploadHandlers() {
  const uploadSection = document.getElementById('uploadSection');
  const fileInput = document.getElementById('fileInput');
  const uploadedFilesContainer = document.getElementById('uploadedFiles');

  if (!uploadSection || !fileInput || !uploadedFilesContainer) {
    console.warn('Upload elements not found, retrying...');
    setTimeout(initUploadHandlers, 100);
    return;
  }

  uploadSection.addEventListener('dragover', handleDragOver);
  uploadSection.addEventListener('dragleave', handleDragLeave);
  uploadSection.addEventListener('drop', handleDrop);
  fileInput.addEventListener('change', handleFileChange);

  const workTitleInput = document.getElementById('workTitleInput');
  if (workTitleInput) {
    workTitleInput.addEventListener('input', handleTitleInput);
  }
}

function handleTitleInput(e, countElementId) {
  const elementId = countElementId || 'charCount';
  const charCount = document.getElementById(elementId);
  if (charCount) charCount.textContent = e.target.value.length + ' / 12';
}

function handleDragOver(e) {
  e.preventDefault();
  uploadSection.classList.add('dragover');
}

function handleDragLeave() {
  uploadSection.classList.remove('dragover');
}

function handleDrop(e) {
  e.preventDefault();
  uploadSection.classList.remove('dragover');
  handleFiles(e.dataTransfer.files);
}

function handleFileChange(e) {
  handleFiles(e.target.files);
}

function handleFiles(files) {
  if (!window.currentWorkId) {
    showStatus('请先在左侧选择一个作品，再上传创作设定文件', 'error');
    return;
  }

  const remainingSlots = 3 - uploadedFiles.length;
  const filesToProcess = Array.from(files).slice(0, remainingSlots);

  if (filesToProcess.length === 0) {
    if (uploadedFiles.length >= 3) {
      showStatus('最多只能上传3个文件', 'error');
    }
    return;
  }

  filesToProcess.forEach(file => {
    const nameLower = (file.name || '').toLowerCase();
    const isTextFile = /\.(txt|text|md|markdown)$/.test(nameLower) ||
      (file.type && (file.type.indexOf('text/plain') === 0 || file.type.indexOf('text/markdown') === 0));
    if (!isTextFile) {
      showStatus(`文件 "${file.name}" 格式不支持，仅允许 .txt/.text/.md/.markdown 等文本文件`, 'error');
      return;
    }

    const isDuplicate = uploadedFiles.some(f => f.name === file.name && f.size === file.size);
    if (isDuplicate) {
      showStatus(`文件 "${file.name}" 已上传，请勿重复操作`, 'warning');
      return;
    }

    const reader = new FileReader();
    reader.onload = function(e) {
      const content = e.target.result;
      if (content.length > 5000) {
        showStatus(`文件 "${file.name}" 超过5000字符限制`, 'error');
        return;
      }
      addFile(file, content);
    };
    reader.onerror = function() {
      showStatus(`文件 "${file.name}" 读取失败`, 'error');
    };
    reader.readAsText(file, 'UTF-8');
  });

  const fileInput = document.getElementById('fileInput');
  if (fileInput) fileInput.value = '';
}

function addFile(file, content) {
  const fileData = {
    id: Date.now(),
    name: file.name,
    size: file.size,
    content: content
  };

  uploadedFiles.push(fileData);

  const uploadedFilesContainer = document.getElementById('uploadedFiles');
  if (!uploadedFilesContainer) return;

  const fileCard = document.createElement('div');
  fileCard.className = 'file-card';
  fileCard.dataset.fileId = fileData.id;

  fileCard.innerHTML = `
    <i class="fas fa-file-alt file-icon"></i>
    <div class="file-info">
      <div class="file-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</div>
      <div class="file-size">${formatSize(file.size)}</div>
    </div>
    <button class="file-remove" onclick="removeFile(${fileData.id})">×</button>
  `;

  uploadedFilesContainer.appendChild(fileCard);
  showStatus(`文件 "${file.name}" 上传成功`, 'success');
  refreshWorkStepActions();
}

function removeFile(fileId) {
  const index = uploadedFiles.findIndex(f => f.id === fileId);
  if (index !== -1) {
    uploadedFiles.splice(index, 1);
    const fileCard = document.querySelector(`[data-file-id="${fileId}"]`);
    if (fileCard) {
      fileCard.remove();
    }
    showStatus('文件已移除', 'success');
    refreshWorkStepActions();
  }
}

function refreshWorkStepActions() {
  const extractBtn = document.getElementById('extractMemoriesBtn');
  const weaveBtn = document.getElementById('nextStepBtn');
  if (!extractBtn && !weaveBtn) return;

  const hasWork = !!window.currentWorkId;
  const hasFiles = uploadedFiles && uploadedFiles.length > 0;

  if (extractBtn) {
    if (!hasWork) {
      extractBtn.disabled = true;
      extractBtn.title = '请先在左侧选择一个作品';
    } else if (!hasFiles) {
      extractBtn.disabled = true;
      extractBtn.title = '请先上传创作设定文件';
    } else {
      extractBtn.disabled = false;
      extractBtn.title = '并发生成当前已上传的所有创作设定（每个文件单独处理）';
    }
  }
  if (weaveBtn) {
    if (!hasWork) {
      weaveBtn.disabled = true;
      weaveBtn.title = '请先在左侧选择一个作品';
    } else {
      weaveBtn.disabled = false;
      weaveBtn.title = '进入织网环节（可以不提取记忆直接进入）';
    }
  }
}

function ensureMemoriesContainer() {
  const mainArea = document.getElementById('mainArea');
  if (!mainArea) return null;
  let container = document.getElementById('sessionMemoriesContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'sessionMemoriesContainer';
    container.className = 'memories-section';
    container.innerHTML = `
      <div class="memories-header">
        <div class="memories-title">
          <i class="fas fa-brain"></i>
          <span>已提取创作设定</span>
          <span class="memories-count" id="memoriesCount">0</span>
        </div>
        <button class="memories-add-btn" id="addMemoryBtn" onclick="openAddMemoryModal()">
          <i class="fas fa-plus"></i>
          <span>添加设定</span>
        </button>
      </div>
      <div class="memories-list" id="memoriesList"></div>
    `;
    const anchor = document.querySelector('.step-actions') || document.getElementById('nextStepBtn');
    if (anchor) {
      mainArea.insertBefore(container, anchor);
    } else {
      mainArea.appendChild(container);
    }
  }
  return container;
}

async function loadAndRenderSessionMemories(sessionId) {
  if (!sessionId) return;
  try {
    const list = await NovelAPI.getSessionMemories(sessionId);
    renderSessionMemories(list || []);
  } catch (err) {
    console.error('加载创作设定失败:', err);
  }
}

function renderSessionMemories(memories) {
  const container = ensureMemoriesContainer();
  if (!container) return;
  const countEl = document.getElementById('memoriesCount');
  const listEl = document.getElementById('memoriesList');
  const arr = Array.isArray(memories) ? memories : [];
  if (countEl) countEl.textContent = String(arr.length);
  if (!listEl) return;

  if (arr.length === 0) {
    listEl.innerHTML = '<div class="empty-hint"><i class="fas fa-lightbulb"></i><span>暂无设定，上传创作设定文件后自动生成</span></div>';
    return;
  }

  const sortedByInsertion = [...arr].sort((a, b) => {
    const idA = a && a.id != null ? Number(a.id) || 0 : 0;
    const idB = b && b.id != null ? Number(b.id) || 0 : 0;
    return idB - idA;
  });

  const validRows = [];
  sortedByInsertion.forEach((m) => {
    const content = typeof m.content === 'string' ? m.content : (m && typeof m === 'string' ? m : '');
    if (!content) return;
    const memoryId = m && m.id != null ? String(m.id) : '';
    validRows.push({ memoryId, content });
  });

  if (validRows.length === 0) {
    listEl.innerHTML = '<div class="empty-hint"><i class="fas fa-lightbulb"></i><span>暂无设定，上传创作设定文件后自动生成</span></div>';
    return;
  }

  let bodyHtml = '';
  const MEM_MAX = _getTh('session_memory_chars', 200);
  const MEM_HARD = _getTh('session_memory_hard_chars', 200);
  validRows.forEach((row, idx) => {
    const index = idx + 1;
    const idAttr = escapeAttr(row.memoryId);
    const truncatedContent = row.content.length > MEM_HARD ? row.content.slice(0, MEM_HARD) : row.content;
    const contentLen = truncatedContent.length;
    bodyHtml += `
      <tr class="memory-row" data-memory-id="${idAttr}">
        <td class="memory-id-cell">${index}</td>
        <td class="memory-content-cell-wrap">
          <div class="memory-content-cell"></div>
          <div class="char-counter memory-char-counter" data-memory-count="${idAttr}">${contentLen} / ${MEM_MAX}</div>
        </td>
        <td class="memory-actions-cell">
          <div class="work-actions memory-row-actions">
            <button class="work-action-btn edit-btn" onclick="editSessionMemory('${idAttr}')" title="编辑会话">
              <i class="fas fa-edit"></i>
            </button>
            <button class="work-action-btn delete-btn" onclick="deleteSessionMemory('${idAttr}')" title="删除会话">
              <i class="fas fa-trash"></i>
            </button>
          </div>
        </td>
      </tr>
    `;
  });

  listEl.innerHTML = `
    <table class="memory-table">
      <thead>
        <tr class="memory-header-row">
          <th class="memory-id-cell">序号</th>
          <th class="memory-content-cell">内容</th>
          <th class="memory-actions-cell">操作</th>
        </tr>
      </thead>
      <tbody>${bodyHtml}</tbody>
    </table>
  `;

  const contentCells = listEl.querySelectorAll('tbody .memory-content-cell');
  validRows.forEach((row, idx) => {
    const truncatedContent = row.content.length > MEM_HARD ? row.content.slice(0, MEM_HARD) : row.content;
    if (contentCells[idx]) contentCells[idx].textContent = truncatedContent;
  });
}

function editSessionMemory(memoryId) {
  if (!memoryId) return;
  const row = document.querySelector(`.memory-row[data-memory-id="${escapeAttr(memoryId)}"]`);
  if (!row) return;
  if (row.classList.contains('editing')) return;

  const contentCell = row.querySelector('.memory-content-cell');
  const actionsCell = row.querySelector('.memory-actions-cell');
  const countEl = row.querySelector('.memory-char-counter');
  if (!contentCell || !actionsCell) return;

  const currentContent = contentCell.textContent || '';
  row.classList.add('editing');
  row.dataset.originalContent = currentContent;

  const editorId = 'memoryEditor-' + memoryId;
  const MEM_MAX = _getTh('session_memory_chars', 200);
  const MEM_HARD = _getTh('session_memory_hard_chars', 200);
  contentCell.innerHTML = `<textarea id="${editorId}" class="memory-inline-editor">${escapeHtml(currentContent)}</textarea>`;

  actionsCell.innerHTML = `
    <div class="memory-inline-actions">
      <button class="memory-inline-save" onclick="saveSessionMemoryInline('${escapeAttr(memoryId)}')" title="保存">
        <i class="fas fa-save"></i> 保存
      </button>
      <button class="memory-inline-cancel" onclick="cancelEditSessionMemory('${escapeAttr(memoryId)}')" title="取消">
        <i class="fas fa-times"></i> 取消
      </button>
    </div>
  `;

  setTimeout(() => {
    const el = document.getElementById(editorId);
    if (el) {
      el.focus();
      const len = el.value.length;
      el.setSelectionRange(len, len);

      const MEM_MAX = _getTh('global_summary_chars', 50);
      const MEM_HARD = _getTh('session_memory_hard_chars', 200);
      const alertMap = {};

      _setCharCounter(countEl, len, MEM_MAX, MEM_HARD, '创作设定', alertMap);

      el.addEventListener('input', () => {
        const curLen = el.value.length;
        if (curLen > MEM_HARD) {
          _enforceHardMax(el, MEM_HARD, '创作设定');
        }
        _setCharCounter(countEl, el.value.length, MEM_MAX, MEM_HARD, '创作设定', alertMap);
      });
    }
  }, 20);
}

function saveSessionMemoryInline(memoryId) {
  if (!memoryId) return;
  const row = document.querySelector(`.memory-row[data-memory-id="${escapeAttr(memoryId)}"]`);
  const editor = row && row.querySelector('textarea.memory-inline-editor');
  if (!row || !editor) return;

  const trimmed = editor.value.trim();
  if (!trimmed) {
    showStatus('记忆内容不能为空', 'error');
    editor.focus();
    return;
  }

  const MEM_HARD = _getTh('session_memory_hard_chars', 200);
  if (trimmed.length > MEM_HARD) {
    showStatus(`创作设定内容不能超过 ${MEM_HARD} 字`, 'error');
    return;
  }

  const orig = row.dataset.originalContent || '';
  if (trimmed === orig.trim()) {
    cancelEditSessionMemory(memoryId);
    return;
  }

  const saveBtn = row.querySelector('.memory-inline-save');
  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.style.opacity = '0.6';
  }

  axios
    .patch(`/api/session-memories/${encodeURIComponent(memoryId)}`, { content: trimmed })
    .then(() => {
      showStatus('会话更新成功', 'success');
      if (window.currentWorkId) return loadAndRenderSessionMemories(window.currentWorkId);
    })
    .catch((err) => {
      if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.style.opacity = '';
      }
      console.error('[更新会话记忆失败:', err);
      showStatus('更新失败，请稍后重试', 'error');
    });
}

function cancelEditSessionMemory(memoryId) {
  if (!memoryId) return;
  const row = document.querySelector(`.memory-row[data-memory-id="${escapeAttr(memoryId)}"]`);
  if (!row) return;

  const orig = row.dataset.originalContent || '';
  const contentCell = row.querySelector('.memory-content-cell');
  const actionsCell = row.querySelector('.memory-actions-cell');
  const countEl = row.querySelector('.memory-char-counter');
  if (!contentCell || !actionsCell) return;

  row.classList.remove('editing');
  delete row.dataset.originalContent;
  contentCell.textContent = orig;

  const MEM_MAX = _getTh('session_memory_chars', 200);
  const MEM_HARD = _getTh('session_memory_hard_chars', 200);
  const truncatedOrig = orig.length > MEM_HARD ? orig.slice(0, MEM_HARD) : orig;
  if (countEl) {
    countEl.textContent = `${truncatedOrig.length} / ${MEM_MAX}`;
  }

  actionsCell.innerHTML = `
    <div class="work-actions memory-row-actions">
      <button class="work-action-btn edit-btn" onclick="editSessionMemory('${escapeAttr(memoryId)}')" title="编辑会话">
        <i class="fas fa-edit"></i>
      </button>
      <button class="work-action-btn delete-btn" onclick="deleteSessionMemory('${escapeAttr(memoryId)}')" title="删除会话">
        <i class="fas fa-trash"></i>
      </button>
    </div>
  `;
}

function deleteSessionMemory(memoryId) {
  if (!memoryId) return;

  showConfirm({
    title: '确认删除',
    message: '确定要删除此条创作设定吗？此操作不可撤销。',
    confirmText: '删除',
    cancelText: '取消',
    onConfirm: async () => {
      try {
        await axios.delete(`/api/session-memories/${encodeURIComponent(memoryId)}`);
        showStatus('记忆删除成功', 'success');
        if (window.currentWorkId) await loadAndRenderSessionMemories(window.currentWorkId);
      } catch (err) {
        console.error('[删除会话记忆失败:', err);
        showStatus('删除失败，请稍后重试', 'error');
      }
    },
  });
}

async function extractMemoriesNow() {
  if (!window.currentWorkId) {
    showStatus('请先在左侧选择一个作品，再执行生成', 'error');
    return;
  }

  if (uploadedFiles.length === 0) {
    showStatus('请先上传文件，再点提取', 'error');
    return;
  }

  // 判断是否已有记忆：有则弹确认框，避免误点直接覆盖
  const countEl = document.getElementById('memoriesCount');
  const curCount = Number(countEl ? (countEl.textContent || '0') : '0') || 0;

  const hasExisting = curCount > 0;

  const doReal = async (_finalVars) => {
    const btn = document.getElementById('extractMemoriesBtn');
    if (btn) {
      btn.disabled = true;
      btn.dataset.oriHtml = btn.innerHTML;
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 生成中...';
    }

    const fileCount = uploadedFiles.length;
    showStatus(`正在并发调用提取能力，共 ${fileCount} 个文件，请稍候...`, 'info');

    const batch = uploadedFiles.map((f) => {
      const name = typeof f.name === 'string' ? f.name : '未命名文件';
      const text = typeof f.content === 'string' ? f.content : String(f.content || '');
      const sourceText = `===== 文件: ${name} =====\n${text}`;
      return { source_text: sourceText };
    });

    try {
      const result = await NovelAPI.invokeCapabilityBatch(
        window.currentWorkId,
        'extract_session_memory',
        batch
      );

      const agg = (result && result.aggregation) || {};
      const totalCount = Number(agg.memories_count_total || 0);
      const created = Number(agg.memories_created_total || 0);
      const token = Number(agg.token_total || 0);
      const success = Number((result && result.success) || 0);
      const failed = Number((result && result.failed) || 0);

      await loadAndRenderSessionMemories(window.currentWorkId);

      if (failed > 0) {
        const sampleErr =
          Array.isArray(result.errors) && result.errors[0]
            ? ` 示例错误：${result.errors[0].detail || result.errors[0].status}`
            : '';
        showStatus(
          `生成完成：成功${success}/${fileCount}，失败${failed}。共识别${totalCount}条，新增${created}条（token ${token}）。${sampleErr}`,
          'warning'
        );
      } else {
        showStatus(
          `生成成功：并发 ${fileCount}/${success} 个文件，共识别${totalCount}条，新增${created}条（token ${token}）。可继续上传文件后再次点击「生成」做增量补充。`,
          'success'
        );
      }
    } catch (err) {
      console.error('调用批量生成能力失败:', err);
      showStatus('批量生成失败，请稍后重试', 'error');
    } finally {
      if (btn) {
        if (btn.dataset.oriHtml) btn.innerHTML = btn.dataset.oriHtml;
        btn.disabled = false;
      }
    }
  };

  window.startGenerateFlowWithPreview({
    hasExisting: hasExisting,
    confirmConfig: hasExisting ? {
      title: '确认重新生成',
      message: `当前作品已有 ${curCount} 条创作设定，重新生成会对已有内容做增量/去重写入，是否继续执行？`,
      confirmText: '确认生成',
      cancelText: '取消',
    } : null,
    previewConfig: {
      sessionId: window.currentWorkId,
      capabilityId: 'extract_session_memory',
      rawVariables: {},
    },
    previewRequired: false,
    doReal: doReal,
  });
}

function handleEnterWeave() {
  if (!window.currentWorkId) {
    showStatus('请先在左侧选择作品，再进入织网', 'error');
    return;
  }
  if (window.currentWorkId) {
    completeStep(window.currentWorkId, 0);
  }
  showStatus('进入织网环节：在画布上管理实体/时间/地点/事件，完善基础设定', 'info');
}

// 历史兼容：旧 onclick/缓存页可能还在引用 handleNextStep
async function handleNextStep() {
  return extractMemoriesNow();
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

function startCreating() {
  const modalOverlay = document.getElementById('modalOverlay');
  if (modalOverlay) modalOverlay.style.display = 'flex';
}

function _getTh(key, fallbackValue) {
  if (typeof window._getTh === 'function') {
    try { return window._getTh(key, fallbackValue); } catch (_e) {}
  }
  const def = (fallbackValue === undefined || fallbackValue === null) ? 0 : fallbackValue;
  if (typeof window === 'undefined' || typeof window.frontendThresholds !== 'object' || window.frontendThresholds === null) return def;
  const v = window.frontendThresholds[key];
  if (v === undefined || v === null || v === '') return def;
  if (typeof def === 'number') {
    const n = Number(v);
    return Number.isFinite(n) ? n : def;
  }
  return v;
}

function _enforceHardMax(el, hardMax, label) {
  if (!el || !hardMax) return false;
  const val = el.value || '';
  if (val.length <= hardMax) return false;
  const oldStart = typeof el.selectionStart === 'number' ? el.selectionStart : hardMax;
  const oldEnd = typeof el.selectionEnd === 'number' ? el.selectionEnd : hardMax;
  el.value = val.slice(0, hardMax);
  try {
    const ns = Math.min(oldStart, hardMax);
    const ne = Math.min(oldEnd, hardMax);
    el.setSelectionRange(ns, ne);
  } catch (_e) {}
  try {
    if (typeof showStatus === 'function') {
      showStatus(`${label}超过最大 ${hardMax} 字，已自动舍弃末尾超出内容。`, 'warn');
    }
  } catch (_e) {}
  return true;
}

function _setCharCounter(el, cur, max, hard, label, alertMap) {
  if (!el) return;
  el.textContent = `${cur} / ${max}`;
  if (cur > max) {
    const k = String(label);
    if (!alertMap[k]) {
      alertMap[k] = true;
      try {
        if (typeof showStatus === 'function') {
          showStatus(`${label}当前 ${cur} 字，超过建议值 ${max} 字，精简下内容会更凝练；超过 ${hard} 字将自动截断。`, 'warn');
        }
      } catch (_e) {}
    }
  }
}

function openAddMemoryModal() {
  const MEM_MAX = _getTh('session_memory_chars', 200);
  const MEM_HARD = _getTh('session_memory_hard_chars', 200);

  const modalOverlay = document.createElement('div');
  modalOverlay.className = 'modal-overlay';
  modalOverlay.id = 'addMemoryModalOverlay';
  modalOverlay.style.display = 'flex';
  modalOverlay.innerHTML = `
    <div class="modal">
      <div class="modal-content-wrapper">
        <div class="modal-header">
          <h3 class="modal-title">添加创作设定</h3>
          <button class="modal-close" onclick="closeAddMemoryModal()">×</button>
        </div>
        <div class="form-group">
          <textarea
            id="addMemoryContent"
            class="form-input"
            placeholder="请输入创作设定内容..."
            rows="5"
          ></textarea>
          <div class="char-counter char-counter--right" id="addMemoryCharCount">0 / ${MEM_MAX}</div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" onclick="closeAddMemoryModal()">取消</button>
          <button class="btn-primary" onclick="createSessionMemory()">确认添加</button>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(modalOverlay);

  const textarea = document.getElementById('addMemoryContent');
  const countEl = document.getElementById('addMemoryCharCount');
  const alertMap = {};
  if (textarea && countEl) {
    textarea.addEventListener('input', () => {
      const len = textarea.value.length;
      if (len > MEM_HARD) {
        _enforceHardMax(textarea, MEM_HARD, '创作设定');
      }
      _setCharCounter(countEl, textarea.value.length, MEM_MAX, MEM_HARD, '创作设定', alertMap);
    });
  }
}

function closeAddMemoryModal() {
  const modal = document.getElementById('addMemoryModalOverlay');
  if (modal) {
    modal.remove();
  }
}

async function createSessionMemory() {
  if (!window.currentWorkId) {
    showStatus('请先在左侧选择一个作品', 'error');
    closeAddMemoryModal();
    return;
  }
  const contentEl = document.getElementById('addMemoryContent');
  const content = contentEl ? contentEl.value.trim() : '';
  if (!content) {
    showStatus('请输入创作设定内容', 'error');
    return;
  }
  try {
    await axios.post('/api/session-memories/', {
      session_id: window.currentWorkId,
      content: content,
    }, { timeout: 10000 });
    showStatus('创作设定添加成功', 'success');
    closeAddMemoryModal();
    await loadAndRenderSessionMemories(window.currentWorkId);
  } catch (err) {
    console.error('[添加会话记忆失败:', err);
    showStatus('添加创作设定失败，请稍后重试', 'error');
  }
}

async function createWork() {
  const titleInput = document.getElementById('workTitleInput');
  const title = titleInput ? titleInput.value.trim() : '';

  if (!title) {
    showStatus('请输入作品名称', 'error');
    return;
  }

  if (title.length > 12) {
    showStatus('作品名称不能超过12个字', 'error');
    return;
  }

  try {
    const created = await NovelAPI.createWork({ title: title });
    closeModal();
    if (titleInput) titleInput.value = '';
    const charCount = document.getElementById('charCount');
    if (charCount) charCount.textContent = '0 / 12';
    await loadWorks();
    // 【作品级隔离 SOP】创建新作品时，若当前已有其他作品数据驻留内存，必须先清空全部缓存
    if (window.currentWorkId && window.currentWorkId !== created.session_id && typeof window._resetAllWorkCaches === 'function') {
      window._resetAllWorkCaches();
    }
    window.currentWorkId = created && created.session_id ? created.session_id : null;
    showStatus('作品创建成功，当前可进入「立基」环节', 'success');
  } catch (err) {
    console.error('创建作品失败:', err);
    const msg = err.response?.data?.detail || err.message || '未知错误';
    showStatus('作品创建失败: ' + msg, 'error');
  }
}

function toggleWorkExpand(workId) {
  const sidebar = document.getElementById('sidebar');

  if (sidebar.classList.contains('collapsed')) {
    toggleSidebar();
    return;
  }

  const workItem = document.getElementById(workId);
  const steps = document.getElementById(workId + '_steps');
  const icon = workItem.querySelector('.expand-icon');

  if (steps.style.display === 'none' || steps.style.display === '') {
    steps.style.display = 'block';
    icon.style.transform = 'rotate(90deg)';
  } else {
    steps.style.display = 'none';
    icon.style.transform = 'rotate(0deg)';
  }
}

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  sidebar.classList.toggle('collapsed');
}

function editWorkTitle(sessionId) {
  const workItem = document.getElementById(sessionId);
  if (!workItem) return;

  const currentTitle = workItem.getAttribute('data-title') || '';
  const inputId = 'editTitleInput-' + Date.now();
  const countId = inputId + '_charCount';
  const saveBtnId = inputId + '_save';

  const overlay = document.getElementById('modalOverlay');
  const modalContent = document.getElementById('modalContent');
  if (!overlay || !modalContent) return;

  // 保存原始内容（仅首次）
  if (!window.__originalModalContent) {
    window.__originalModalContent = modalContent.innerHTML;
  }

  // 使用与创建作品相同的模态窗结构
  modalContent.innerHTML = `
    <div class="modal-content-wrapper">
      <div class="modal-header">
        <h3 class="modal-title">编辑作品名称</h3>
        <button class="modal-close" onclick="closeModal()">×</button>
      </div>
      <div class="form-group">
        <label class="form-label">作品名称</label>
        <input type="text" id="${inputId}" class="form-input edit-title-input" value="${escapeHtml(currentTitle)}" maxlength="12" placeholder="请输入作品名称" />
        <span class="char-counter char-counter--right" id="${countId}">${currentTitle.length} / 12</span>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary" onclick="closeModal()">取消</button>
        <button class="btn-primary" id="${saveBtnId}">保存</button>
      </div>
    </div>
  `;

  overlay.style.display = 'flex';

  // 绑定事件
  setTimeout(() => {
    const input = document.getElementById(inputId);
    if (input) {
      input.focus();
      input.select();
      input.addEventListener('input', () => {
        const countEl = document.getElementById(countId);
        if (countEl) countEl.textContent = input.value.length + ' / 12';
      });
    }

    const saveBtn = document.getElementById(saveBtnId);
    if (saveBtn) {
      saveBtn.addEventListener('click', async () => {
        const trimmedTitle = input.value.trim();
        if (!trimmedTitle) {
          showStatus('作品名称不能为空', 'error');
          return;
        }
        if (trimmedTitle.length > 12) {
          showStatus('作品名称不能超过12个字', 'error');
          return;
        }
        try {
          await NovelAPI.updateWork(sessionId, { title: trimmedTitle });
          closeModal();
          await loadWorks();
          showStatus('作品名称修改成功', 'success');
        } catch (err) {
          console.error('修改作品名称失败:', err);
          const msg = err.response?.data?.detail || err.message || '未知错误';
          showStatus('修改失败: ' + msg, 'error');
        }
      });
    }
  }, 50);
}

async function deleteWork(sessionId) {
  const workItem = document.getElementById(sessionId);
  if (!workItem) return;

  const workName = workItem.getAttribute('data-title') || workItem.querySelector('.work-item-name')?.textContent || '未知作品';

  showConfirm({
    title: '⚠️ 确认删除作品',
    message: `即将永久删除作品「<b>${escapeHtml(workName)}</b>」。<br><br>此操作将 <b>级联删除</b> 该作品的：<b>全局剧情、分卷卷纲、章节章纲、章节事件链、章节正文、策略配置、会话记忆、标签配置</b> 等全部数据库记录与关联多媒体文件。<br><br><b style="color:#dc2626;font-size:15px;">此操作不可恢复，且作品下的多媒体文件将被一并物理删除！</b>`,
    confirmText: '我已了解风险，永久删除',
    confirmBtnStyle: 'danger',
    cancelText: '取消',
    onConfirm: async () => {
      try {
        await NovelAPI.deleteWork(sessionId);
        if (window.currentWorkId === sessionId) {
          // 【作品级隔离 SOP】删除当前作品时清空全部缓存，防止残留数据污染后续作品
          if (typeof window._resetAllWorkCaches === 'function') {
            window._resetAllWorkCaches();
          }
          window.currentWorkId = null;
          const mainArea = document.getElementById('mainArea');
          if (mainArea) mainArea.style.display = 'none';
        }
        await loadWorks();
        showStatus('作品已永久删除', 'success');
      } catch (err) {
        console.error('删除作品失败:', err);
        const msg = err.response?.data?.detail || err.message || '未知错误';
        showStatus('删除失败: ' + msg, 'error');
      }
    }
  });
}

function completeStep(workId, stepIndex) {
  const workItem = document.getElementById(workId);
  if (!workItem) return;

  const steps = workItem.querySelectorAll('.step-item');

  if (steps[stepIndex].classList.contains('step-locked')) {
    showStatus('无法完成未解锁的环节', 'error');
    return;
  }

  steps[stepIndex].classList.remove('step-active', 'step-current');
  steps[stepIndex].classList.add('step-completed');
  steps[stepIndex].querySelector('.step-status').innerHTML = '<i class="fas fa-check"></i>';

  if (stepIndex < steps.length - 1) {
    steps[stepIndex + 1].classList.remove('step-locked');
    steps[stepIndex + 1].classList.add('step-active');
    steps[stepIndex + 1].querySelector('.step-status').innerHTML = '<i class="fas fa-play"></i>';
  }

  const stepNames = ['立基', '织网', '谋篇', '分卷', '定章', '推演', '成文'];
  showStatus(`「${stepNames[stepIndex]}」已完成`, 'success');

  handleStepClick(workId, stepIndex + 1);
}

window.uploadedFiles = uploadedFiles;
window.initWorkPage = initWorkPage;
window.initUploadHandlers = initUploadHandlers;
window.handleTitleInput = handleTitleInput;
window.handleDragOver = handleDragOver;
window.handleDragLeave = handleDragLeave;
window.handleDrop = handleDrop;
window.handleFileChange = handleFileChange;
window.handleFiles = handleFiles;
window.addFile = addFile;
window.removeFile = removeFile;
window.refreshWorkStepActions = refreshWorkStepActions;
window.extractMemoriesNow = extractMemoriesNow;
window.handleEnterWeave = handleEnterWeave;
window.handleNextStep = handleNextStep;
window.formatSize = formatSize;
window.startCreating = startCreating;
window.createWork = createWork;
window.toggleWorkExpand = toggleWorkExpand;
window.toggleSidebar = toggleSidebar;
window.editWorkTitle = editWorkTitle;
window.deleteWork = deleteWork;
window.completeStep = completeStep;
window.ensureMemoriesContainer = ensureMemoriesContainer;
window.loadAndRenderSessionMemories = loadAndRenderSessionMemories;
window.renderSessionMemories = renderSessionMemories;
window.editSessionMemory = editSessionMemory;
window.saveSessionMemoryInline = saveSessionMemoryInline;
window.cancelEditSessionMemory = cancelEditSessionMemory;
window.deleteSessionMemory = deleteSessionMemory;