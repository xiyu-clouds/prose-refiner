/* ========================================================================
 * 成文节点：章节正文生成
 *   - 数据源：从「推演」window._deductionResult.volumes[volIdx].chapters[chapIdx].events 同步只读的章节事件链
 *   - 调用 chapter_content_generation 能力 → 基于章纲和事件链生成该章正文内容
 *   - 每章一张卡片，含：章纲+事件链只读区 + 生成按钮 + 折叠效果 + 正文可编辑 + 失焦自动保存
 *   - scope 约定（与 Rust/Python SSOT 完全对齐）：task_type = 'chapter_content_generation'，parent_id = chapter_plot_design.id，sort_order = chapter_index(0-based)；volume_index 通过 parent 链反查：chapter_content.parent_id → chapter_outline.parent_id → volume_outline.sort_order
 * ====================================================================== */

/**
 * 成文节点作品级隔离重置：切换作品/重入本节点前调用。
 * 清空正文结果缓存、折叠标记、并发队列、自动保存定时器与 DOM 残留。
 */
function resetContentPageIsolatedState() {
  // 1) 跨作品内存缓存：仅清空本节点（成文）的正文结果 + 折叠规范化标记
  //   ——严禁顺手清空上游 _deductionResult / _chapterPlotResult / _volumePlotResult / _globalPlotResult，
  //     成文卡片展示章纲只读 / 事件链只读 / 生成正文时上下文传入都直接复用上游缓存。
  window._contentResult = { volumes: [] };
  try { delete window._contFoldNormalized; } catch (_) { window._contFoldNormalized = undefined; }

  // 2) 模块级去抖：并发请求队列丢弃重建、活跃计数清零、自动保存定时器清空
  _contResReqQueue.length = 0;
  _contResActiveCount = 0;
  for (const k of Object.keys(_contSaveTimers)) {
    const t = _contSaveTimers[k];
    if (t) clearTimeout(t);
  }
  _contSaveTimers = {};

  // 3) DOM 残留：章卷正文卡片容器清空
  const cardsEl = document.getElementById('contentChapterCards');
  if (cardsEl) cardsEl.innerHTML = '';
}

if (!window._contentResult) {
  window._contentResult = { volumes: [] };
}

// 生成请求锁现由公共工具 NovelAPI.runCapabilityWithSSE 统一管理（window._capabilityLocks），
// 本页不再维护独立的 _contentGenLocks，避免锁逻辑散落与状态不一致。

// ========== 图像模型能力元数据缓存（全局单次拉取，多章节复用）==========
if (!window._imageCapabilitiesCache) {
  window._imageCapabilitiesCache = null;
}

async function _ensureImageCapabilities() {
  if (window._imageCapabilitiesCache) return window._imageCapabilitiesCache;
  try {
    const data = await NovelAPI.getImageCapabilities();
    if (data && data.ok && data.models) {
      window._imageCapabilitiesCache = data;
      return data;
    }
  } catch (_e) {
    // 静默失败，渲染时走兜底
  }
  return null;
}

/**
 * 画面提示词字符上限（SSOT 读取：后端 VAL_IMAGE_PROMPT_MAX_CHARS → meta/frontend-thresholds → window.frontendThresholds）。
 * 兜底 800，仅在阈值接口未加载/失败时使用，禁止前端散写字面量。
 */
function _getImagePromptMaxChars() {
  const th = (typeof window !== 'undefined') ? window.frontendThresholds : null;
  if (th && typeof th === 'object') {
    const v = th.image_prompt_max_chars;
    if (v !== undefined && v !== null && v !== '') {
      const n = Number(v);
      if (Number.isFinite(n) && n > 0) return n;
    }
  }
  return 800;
}

function _pickImageCap(capsData, modelName) {
  if (!capsData || !capsData.models) return null;
  return capsData.models[modelName] || null;
}

// ========== 章级资源请求并发限制器（避免多章展开时请求洪峰）==========
const _contResReqQueue = [];
let _contResActiveCount = 0;
const _contResMaxConcurrent = 5;

function _contEnqueueRequest(fn) {
  return new Promise((resolve, reject) => {
    _contResReqQueue.push({ fn, resolve, reject });
    _contDrainRequestQueue();
  });
}

function _contDrainRequestQueue() {
  while (_contResActiveCount < _contResMaxConcurrent && _contResReqQueue.length > 0) {
    const { fn, resolve, reject } = _contResReqQueue.shift();
    _contResActiveCount++;
    Promise.resolve()
      .then(() => fn())
      .then(resolve, reject)
      .finally(() => {
        _contResActiveCount--;
        _contDrainRequestQueue();
      });
  }
}

function _contEscapeHtml(text) {
  const s = (text == null) ? '' : String(text);
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function _contEnsureVolume(volIdx) {
  if (!window._contentResult) window._contentResult = { volumes: [] };
  if (!Array.isArray(window._contentResult.volumes)) window._contentResult.volumes = [];
  while (window._contentResult.volumes.length <= volIdx) {
    window._contentResult.volumes.push({
      collapsed: false,
      chapters: [],
    });
  }
  return window._contentResult.volumes[volIdx];
}

function _contEnsureChapter(volIdx, chapIdx) {
  const vol = _contEnsureVolume(volIdx);
  if (!Array.isArray(vol.chapters)) vol.chapters = [];
  while (vol.chapters.length <= chapIdx) {
    vol.chapters.push({
      activeTaskId: '',
      content: '',
      collapsed: false,
    });
  }
  return vol.chapters[chapIdx];
}

/* ============== 默认折叠规范化（懒展开：首屏仅最小必要单元展开） ============== */
/* 在 render 函数内部调用，确保 _contEnsureVolume 已创建所有卷后再生效 */
function _contApplyInitFold(volEvents) {
  if (window._contFoldNormalized) return;
  window._contFoldNormalized = true;
  if (!Array.isArray(volEvents) || !volEvents.length) return;
  for (let vi = 0; vi < volEvents.length; vi++) {
    const vs = _contEnsureVolume(vi);
    vs.collapsed = (vi !== 0);
    const chs = Array.isArray(vs.chapters) ? vs.chapters : [];
    for (let ci = 0; ci < chs.length; ci++) {
      if (chs[ci] && typeof chs[ci] === 'object') {
        chs[ci].collapsed = !(vi === 0 && ci === 0);
      }
    }
  }
}

function _contHasAnyContentData() {
  const vols = (window._contentResult && Array.isArray(window._contentResult.volumes))
    ? window._contentResult.volumes
    : [];
  for (let i = 0; i < vols.length; i++) {
    const v = vols[i] || {};
    const chs = Array.isArray(v.chapters) ? v.chapters : [];
    for (let j = 0; j < chs.length; j++) {
      const c = chs[j] || {};
      const ct = typeof c.content === 'string' ? c.content.trim() : '';
      if (ct.length > 0) return true;
    }
  }
  return false;
}

function _contTryParseContentRow(row) {
  let obj = null;
  try { obj = (row && typeof row.content_text === 'string') ? JSON.parse(row.content_text) : null; } catch(e) {}
  if (obj && typeof obj.content_text === 'string') return obj.content_text;
  if (row && typeof row.content_text === 'string') {
    try {
      const inner = JSON.parse(row.content_text);
      if (inner && typeof inner.chapter_content_generation === 'object' && typeof inner.chapter_content_generation.content_text === 'string') {
        return inner.chapter_content_generation.content_text;
      }
    } catch(_e) {}
    return row.content_text;
  }
  return '';
}

function _contBuildContentText(content) {
  const ct = typeof content === 'string' ? content.trim() : '';
  return JSON.stringify({ _v: 1, content_text: ct });
}

let _contSaveTimers = {};

function _flashContentSaveTip(volIdx, chapIdx, success, customText) {
  const defaultText = success ? '已自动保存' : '保存失败，请稍后重试';
  const text = customText ? String(customText) : defaultText;
  const color = success ? '#5b21b6' : '#dc2626';
  const cardsEl = document.getElementById('contentChapterCards');
  if (!cardsEl) return;
  const volWrap = cardsEl.querySelector(`.content-volume-wrap[data-vol-idx="${String(volIdx)}"]`);
  if (!volWrap) return;
  let tipEl = volWrap.querySelector(`.content-card-save-tip[data-vol-idx="${String(volIdx)}"][data-chap-idx="${String(chapIdx)}"]`);
  if (!tipEl) tipEl = volWrap.querySelector('.content-volume-save-tip');
  if (!tipEl) return;
  tipEl.innerText = text;
  tipEl.style.color = color;
  tipEl.style.opacity = '1';
  clearTimeout(tipEl._t);
  tipEl._t = setTimeout(() => { tipEl.style.opacity = '0'; }, 1600);
}

async function _contFindActiveTaskId(volIdx, chapIdx) {
  if (!window.currentWorkId) return null;
  const ch = _contEnsureChapter(volIdx, chapIdx);
  if (ch.activeTaskId) {
    const s = String(ch.activeTaskId).trim();
    if (s) {
      return s;
    }
  }
  try {
    const tid = await NovelAPI.findActiveTaskId(
      window.currentWorkId,
      NovelAPI.CONST.TASK_TYPE_CHAPTER_CONTENT,
      volIdx,
      chapIdx,
    );
    if (tid) {
      ch.activeTaskId = String(tid);
      return String(tid);
    }
    return null;
  } catch (_e) {
    console.warn('[content-save] _contFindActiveTaskId failed vol=' + volIdx + ' chap=' + chapIdx + ':', _e?.message || _e);
    return null;
  }
}

async function doSaveChapterContent(volIdx, chapIdx, force) {
  if (!window.currentWorkId) return;
  const ch = _contEnsureChapter(volIdx, chapIdx);
  const content = typeof ch.content === 'string' ? ch.content : '';
  const clean = content.trim();
  if (clean.length === 0 && !force) return;
  const contentText = _contBuildContentText(clean);
  const wc = contentText.length;
  try {
    let taskId = await _contFindActiveTaskId(volIdx, chapIdx);
    if (taskId) {
      const patch = {
        status: 'completed',
        title: `章节正文（第 ${Number(volIdx) + 1} 卷第 ${Number(chapIdx) + 1} 章）`,
        content_text: contentText,
        word_count: Number(wc) || 0,
      };
      await NovelAPI.updateTask(String(taskId), patch);
    } else {
      let parentId = null;
      try {
        parentId = await NovelAPI.resolveChapterParentId(window.currentWorkId, volIdx, chapIdx);
      } catch (_e) {
        console.warn('[content-save] find parent failed vol=' + volIdx + ' chap=' + chapIdx + ':', _e?.message || _e);
      }
      const payload = {
        session_id: window.currentWorkId,
        task_type: NovelAPI.CONST.TASK_TYPE_CHAPTER_CONTENT,
        sequence: 0,
        parent_id: parentId,
        sort_order: Number(chapIdx),
        volume_index: Number(volIdx),
        chapter_index: Number(chapIdx),
        status: 'completed',
        title: `章节正文（第 ${Number(volIdx) + 1} 卷第 ${Number(chapIdx) + 1} 章）`,
        content_text: contentText,
        word_count: Number(wc) || 0,
      };
      await NovelAPI.semanticUpsertTask(payload);
      const newId = await _contFindActiveTaskId(volIdx, chapIdx);
      if (newId && !ch.activeTaskId) ch.activeTaskId = String(newId);
    }
    _flashContentSaveTip(volIdx, chapIdx, true, null);
  } catch (err) {
    console.warn('[content-save] auto save failed vol=' + volIdx + ' chap=' + chapIdx + ':', err?.message || err);
    _flashContentSaveTip(volIdx, chapIdx, false, null);
  }
}

function scheduleContentAutoSave(volIdx, chapIdx, immediate) {
  if (!window.currentWorkId) return;
  const key = `${String(volIdx)}_${String(chapIdx)}`;
  clearTimeout(_contSaveTimers[key]);
  if (immediate) {
    doSaveChapterContent(volIdx, chapIdx, false);
    return;
  }
  _contSaveTimers[key] = setTimeout(() => {
    doSaveChapterContent(volIdx, chapIdx, false);
  }, 500);
}

function _refreshContentCharCount(volIdx, chapIdx) {
  const vi = Number(volIdx);
  const ci = Number(chapIdx);
  if (!Number.isInteger(vi) || vi < 0 || !Number.isInteger(ci) || ci < 0) return;
  const cardsEl = document.getElementById('contentChapterCards');
  if (!cardsEl) return;
  const volWrap = cardsEl.querySelector(`.content-volume-wrap[data-vol-idx="${String(vi)}"]`);
  if (!volWrap) return;
  const cardsContainer = volWrap.querySelector(':scope > .content-volume-body > div:last-child');
  if (!cardsContainer || !cardsContainer.children[ci]) return;
  const chapBody = cardsContainer.children[ci].querySelector(':scope > .content-card-body');
  if (!chapBody) return;
  const ta = chapBody.querySelector('textarea');
  const countEl = chapBody.querySelector(`[data-content-count="${String(vi)}_${String(ci)}"]`);
  if (!ta || !countEl) return;
  const cur = (ta.value || '').length;
  countEl.textContent = `${cur} / ∞`;
}

function toggleContentVolume(volIdx) {
  const vol = _contEnsureVolume(volIdx);
  vol.collapsed = !vol.collapsed;
  const cardsEl = document.getElementById('contentChapterCards');
  if (!cardsEl) return;
  const volWrap = cardsEl.querySelector(`.content-volume-wrap[data-vol-idx="${String(volIdx)}"]`);
  if (!volWrap) return;
  const body = volWrap.querySelector('.content-volume-body');
  const icon = volWrap.querySelector('.content-toggle-icon');
  if (!body) return;
  const collapsed = !!vol.collapsed;
  if (collapsed) {
    body.style.overflow = 'hidden';
    body.style.maxHeight = body.scrollHeight + 'px';
    body.style.opacity = '1';
    body.style.transform = 'translateY(0)';
    requestAnimationFrame(() => {
      body.style.transition = 'max-height 0.35s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease 0.02s, transform 0.3s ease 0.02s';
      body.style.maxHeight = '0px';
      body.style.opacity = '0';
      body.style.transform = 'translateY(-4px)';
    });
    setTimeout(() => {
      body.style.display = 'none';
      body.style.transition = '';
      body.style.overflow = '';
      body.style.transform = '';
    }, 380);
    if (icon) {
      icon.style.transition = 'transform 0.3s ease';
      icon.classList.remove('fa-chevron-up');
      icon.classList.add('fa-chevron-down');
    }
  } else {
    // 卷层懒渲染：首次展开卷时创建章卡（之前折叠卷未创建）
    const chapContainer = body.querySelector('.content-chapters-container');
    if (chapContainer && chapContainer.getAttribute('data-chapters-populated') !== '1') {
      const count = Number(chapContainer.getAttribute('data-chapter-count')) || 0;
      for (let ci = 0; ci < count; ci++) {
        _renderContentCard(volIdx, ci, chapContainer);
      }
      chapContainer.setAttribute('data-chapters-populated', '1');
    }
    body.style.display = 'block';
    body.style.overflow = 'hidden';
    body.style.opacity = '0';
    body.style.transform = 'translateY(-4px)';
    const fullHeight = body.scrollHeight;
    body.style.maxHeight = '0px';
    requestAnimationFrame(() => {
      body.style.transition = 'max-height 0.4s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.35s ease 0.05s, transform 0.35s ease 0.05s';
      body.style.maxHeight = fullHeight + 40 + 'px';
      body.style.opacity = '1';
      body.style.transform = 'translateY(0)';
    });
    setTimeout(() => {
      body.style.transition = '';
      body.style.overflow = '';
      body.style.maxHeight = '';
      body.style.transform = '';
    }, 480);
    if (icon) {
      icon.style.transition = 'transform 0.3s ease';
      icon.classList.remove('fa-chevron-down');
      icon.classList.add('fa-chevron-up');
    }
  }
}

function toggleContentCard(volIdx, chapIdx) {
  const ch = _contEnsureChapter(volIdx, chapIdx);
  ch.collapsed = !ch.collapsed;
  const cardsEl = document.getElementById('contentChapterCards');
  if (!cardsEl) return;
  const volWrap = cardsEl.querySelector(`.content-volume-wrap[data-vol-idx="${String(volIdx)}"]`);
  if (!volWrap) return;
  const cardsContainer = volWrap.querySelector(':scope > .content-volume-body > div:last-child');
  if (!cardsContainer || !cardsContainer.children[chapIdx]) return;
  const chapWrap = cardsContainer.children[chapIdx];
  const header = chapWrap.querySelector(':scope > .content-card-header');
  const body = chapWrap.querySelector(':scope > .content-card-body');
  const icon = chapWrap.querySelector('.content-card-toggle-icon');
  if (!body || !header) return;
  const collapsed = !!ch.collapsed;
  if (collapsed) {
    body.style.overflow = 'hidden';
    body.style.maxHeight = body.scrollHeight + 'px';
    body.style.opacity = '1';
    body.style.transform = 'translateY(0)';
    requestAnimationFrame(() => {
      body.style.transition = 'max-height 0.35s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease 0.02s, transform 0.3s ease 0.02s';
      body.style.maxHeight = '0px';
      body.style.opacity = '0';
      body.style.transform = 'translateY(-4px)';
    });
    setTimeout(() => {
      body.style.display = 'none';
      body.style.transition = '';
      body.style.overflow = '';
      body.style.transform = '';
    }, 380);
    if (icon) {
      icon.style.transition = 'transform 0.3s ease';
      icon.classList.remove('fa-chevron-up');
      icon.classList.add('fa-chevron-down');
    }
  } else {
    // 懒渲染：首次展开章卡时填充 body（章纲/事件链/textarea/音频/图片）
    if (body.getAttribute('data-body-populated') !== '1') {
      _contPopulateContentCardBody(chapWrap, body, volIdx, chapIdx);
    }
    body.style.display = 'block';
    body.style.overflow = 'hidden';
    body.style.opacity = '0';
    body.style.transform = 'translateY(-4px)';
    const fullHeight = body.scrollHeight;
    body.style.maxHeight = '0px';
    requestAnimationFrame(() => {
      body.style.transition = 'max-height 0.4s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.35s ease 0.05s, transform 0.35s ease 0.05s';
      body.style.maxHeight = fullHeight + 40 + 'px';
      body.style.opacity = '1';
      body.style.transform = 'translateY(0)';
    });
    setTimeout(() => {
      body.style.transition = '';
      body.style.overflow = '';
      body.style.maxHeight = '';
      body.style.transform = '';
    }, 480);
    if (icon) {
      icon.style.transition = 'transform 0.3s ease';
      icon.classList.remove('fa-chevron-down');
      icon.classList.add('fa-chevron-up');
    }
  }
}

/**
 * 增量更新单章正文内容（不清空重建整个容器，避免闪烁与 GC 抖动）。
 * 仅更新该章 body 中的 textarea 值与字符计数；若 body 未填充则跳过（展开时自动拉取最新数据）。
 */
function _contRefreshChapterContent(volIdx, chapIdx) {
  const vi = Number(volIdx);
  const ci = Number(chapIdx);
  if (!Number.isInteger(vi) || vi < 0 || !Number.isInteger(ci) || ci < 0) return;
  const cardsEl = document.getElementById('contentChapterCards');
  if (!cardsEl) return;
  const chapWrap = cardsEl.querySelector(`.content-card-wrap[data-vol-idx="${String(vi)}"][data-chap-idx="${String(ci)}"]`);
  if (!chapWrap) return;
  const body = chapWrap.querySelector(':scope > .content-card-body');
  if (!body || body.getAttribute('data-body-populated') !== '1') return;
  const ta = body.querySelector('textarea');
  if (!ta) return;
  const ch = _contEnsureChapter(vi, ci);
  ta.value = typeof ch.content === 'string' ? ch.content : '';
  _refreshContentCharCount(vi, ci);
}

function deleteChapterContent(volIdx, chapIdx) {
  const ch = _contEnsureChapter(volIdx, chapIdx);
  ch.content = '';
  ch.activeTaskId = '';
  _contRefreshChapterContent(volIdx, chapIdx);
  refreshContentStepActions();
  // immediate=true：强制写入空内容到 DB，清空数据库记录，防止刷新后旧数据复活。
  // 与事件链 deleteDeductionEvent 的 immediate=true 行为对齐。
  scheduleContentAutoSave(volIdx, chapIdx, true);
}

async function generateChapterContent(volIdx, chapIdx) {
  // 锁与 SSE 竞态由 NovelAPI.runCapabilityWithSSE 统一处理，本函数只做参数装配与结果渲染。
  const CAP_ID = NovelAPI.CONST.TASK_TYPE_CHAPTER_CONTENT;
  const lockKey = `content_${String(volIdx)}_${String(chapIdx)}`;

  if (!window.currentWorkId) {
    if (typeof showStatus === 'function') showStatus('请先在左侧选择一个作品', 'error');
    return;
  }

  const chapMeta = (window._chapterPlotResult && Array.isArray(window._chapterPlotResult.volumes)
    && window._chapterPlotResult.volumes[volIdx] && Array.isArray(window._chapterPlotResult.volumes[volIdx].chapters))
    ? window._chapterPlotResult.volumes[volIdx].chapters[chapIdx]
    : null;
  const chapterPlot = typeof chapMeta.plot === 'string' ? chapMeta.plot.trim() : '';
  const chapterSummary = typeof chapMeta.summary === 'string' ? chapMeta.summary.trim() : '';

  const dedCh = (window._deductionResult && Array.isArray(window._deductionResult.volumes)
    && window._deductionResult.volumes[volIdx] && Array.isArray(window._deductionResult.volumes[volIdx].chapters))
    ? window._deductionResult.volumes[volIdx].chapters[chapIdx]
    : null;
  const chapterEvents = Array.isArray(dedCh && dedCh.events) ? dedCh.events.filter(s => typeof s === 'string' && s.trim()) : [];

  if (!chapterPlot) {
    if (typeof showStatus === 'function') showStatus(`第 ${Number(volIdx) + 1} 卷第 ${Number(chapIdx) + 1} 章没有章纲剧情，请先在「定章」页面填写`, 'error');
    return;
  }

  if (chapterEvents.length === 0) {
    if (typeof showStatus === 'function') showStatus(`第 ${Number(volIdx) + 1} 卷第 ${Number(chapIdx) + 1} 章没有事件链，请先在「推演」页面生成`, 'error');
    return;
  }

  let volumePlotText = '';
  try {
    const volResult = window._volumePlotResult;
    const vEv = (volResult && Array.isArray(volResult.volumes) && volResult.volumes[volIdx])
      ? (typeof volResult.volumes[volIdx].plot === 'string' ? volResult.volumes[volIdx].plot : '')
      : '';
    if (vEv) volumePlotText = vEv;
  } catch (_e) {}

  const ch = _contEnsureChapter(volIdx, chapIdx);
  const existingContent = typeof ch.content === 'string' ? ch.content.trim() : '';
  const hasExisting = existingContent.length > 0;

  const doReal = async (finalVariables) => {
    const genBtn = document.getElementById(`generateContentBtn_${String(volIdx)}_${String(chapIdx)}`);
    if (genBtn) {
      genBtn.dataset.oriHtml = genBtn.innerHTML;
      genBtn.disabled = true;
      genBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>生成中…</span>';
    }

    try {
      const variables = (finalVariables && typeof finalVariables === 'object')
        ? Object.assign({}, finalVariables)
        : {};
      if (typeof variables.volume_plot_text !== 'string' || !variables.volume_plot_text) {
        variables.volume_plot_text = volumePlotText;
      }
      if (typeof variables.chapter_plot_text !== 'string' || !variables.chapter_plot_text) {
        variables.chapter_plot_text = chapterPlot;
      }
      if (typeof variables.chapter_plot !== 'string' || !variables.chapter_plot) {
        variables.chapter_plot = chapterPlot;
      }
      if (typeof variables.chapter_summary !== 'string' || !variables.chapter_summary) {
        variables.chapter_summary = chapterSummary;
      }
      if (typeof variables.chapter_events !== 'string' || !variables.chapter_events) {
        variables.chapter_events = chapterEvents.join('\n');
      }
      if (typeof variables.volume_index === 'undefined' || variables.volume_index === null) {
        variables.volume_index = Number(volIdx);
      }
      if (typeof variables.chapter_index === 'undefined' || variables.chapter_index === null) {
        variables.chapter_index = Number(chapIdx);
      }

      // 调用公共工具：锁 + SSE 监听 + HTTP 竞态裁决
      const res = await NovelAPI.runCapabilityWithSSE({
        capabilityId: CAP_ID,
        variables: variables,
        lockKey: lockKey,
        volumeIndex: Number(volIdx),
        chapterIndex: Number(chapIdx),
      });

      if (res.conflict) {
        // 并发冲突（前端锁或后端 409），不视为失败
        if (typeof showStatus === 'function') {
          showStatus(res.error?.message || '该章节正在生成中，请稍候...', 'warning');
        }
        return;
      }

      if (!res.ok) {
        const errMsg = res.error?.message || String(res.error || '未知错误');
        console.warn('[content-generate] failed vol=' + volIdx + ' chap=' + chapIdx + ':', errMsg);
        if (typeof showStatus === 'function') showStatus('章节正文生成失败：' + errMsg, 'error');
        return;
      }

      // needRefetch：HTTP 失败但 SSE 显示任务成功，需从 task 表重新拉取结果
      if (res.needRefetch) {
        if (typeof showStatus === 'function') {
          showStatus('任务已完成，正在加载正文结果...', 'info');
        }
        try {
          await _contLoadAllHistoryTasks();
          renderContentChapters();
          refreshContentStepActions();
          const cur = _contEnsureChapter(volIdx, chapIdx);
          const contentText = typeof cur.content === 'string' ? cur.content.trim() : '';
          if (contentText) {
            if (typeof showStatus === 'function') {
              showStatus(`第 ${Number(volIdx) + 1} 卷第 ${Number(chapIdx) + 1} 章正文生成完成（${contentText.length} 字）`, 'success');
            }
          } else {
            if (typeof showStatus === 'function') showStatus('任务已完成但结果为空，请刷新页面查看', 'warning');
          }
        } catch (e) {
          console.warn('[content-generate] refetch failed:', e?.message || e);
          if (typeof showStatus === 'function') showStatus('任务已完成，刷新页面查看结果', 'info');
        }
        return;
      }

      // HTTP 成功：从响应中提取正文
      const payload = res.result;
      const inner = (payload && payload.result && payload.result.chapter_content_generation)
        ? payload.result.chapter_content_generation
        : ((payload && payload.chapter_content_generation) ? payload.chapter_content_generation : null);
      const contentText = inner && typeof inner.content_text === 'string' ? inner.content_text.trim() : '';

      if (!contentText) {
        if (typeof showStatus === 'function') showStatus('章节正文返回为空，请重试或检查后端日志', 'error');
        return;
      }

      const cur = _contEnsureChapter(volIdx, chapIdx);
      cur.content = contentText;
      _contRefreshChapterContent(volIdx, chapIdx);
      refreshContentStepActions();
      scheduleContentAutoSave(volIdx, chapIdx, true);
      if (typeof showStatus === 'function') {
        showStatus(`第 ${Number(volIdx) + 1} 卷第 ${Number(chapIdx) + 1} 章正文生成完成（${contentText.length} 字）`, 'success');
      }
    } catch (err) {
      console.warn('[content-generate] unexpected error vol=' + volIdx + ' chap=' + chapIdx + ':', err?.message || err);
      if (typeof showStatus === 'function') {
        showStatus('章节正文生成出现意外错误：' + (err?.message || String(err)), 'error');
      }
    } finally {
      // 锁与 SSE 订阅由 runCapabilityWithSSE 内部 finally 统一释放；
      // 这里只恢复按钮状态。
      if (genBtn && genBtn.dataset.oriHtml) {
        genBtn.innerHTML = genBtn.dataset.oriHtml;
        genBtn.disabled = false;
        refreshContentStepActions();
      }
    }
  };

  if (window.startGenerateFlowWithPreview) {
    window.startGenerateFlowWithPreview({
      hasExisting: hasExisting,
      confirmConfig: hasExisting ? {
        title: '确认重新生成',
        message: `第 ${Number(volIdx) + 1} 卷第 ${Number(chapIdx) + 1} 章已有正文内容，重新生成会覆盖本章内容，是否继续？`,
        confirmText: '下一步',
        cancelText: '取消',
      } : null,
      previewConfig: {
        sessionId: window.currentWorkId,
        capabilityId: CAP_ID,
        rawVariables: {
          volume_plot_text: volumePlotText,
          chapter_plot_text: chapterPlot,
          chapter_events: chapterEvents.join('\n'),
          volume_index: Number(volIdx),
          chapter_index: Number(chapIdx),
        },
      },
      previewRequired: true,
      doReal: doReal,
    });
  } else {
    await doReal();
  }
}

/** 获取章卡所需基础数据（章纲/事件链/正文内容，复用） */
function _contGetChapterMeta(volIdx, chapIdx) {
  const chapMeta = (window._chapterPlotResult && Array.isArray(window._chapterPlotResult.volumes)
    && window._chapterPlotResult.volumes[volIdx] && Array.isArray(window._chapterPlotResult.volumes[volIdx].chapters))
    ? window._chapterPlotResult.volumes[volIdx].chapters[chapIdx]
    : null;
  const dedCh = (window._deductionResult && Array.isArray(window._deductionResult.volumes)
    && window._deductionResult.volumes[volIdx] && Array.isArray(window._deductionResult.volumes[volIdx].chapters))
    ? window._deductionResult.volumes[volIdx].chapters[chapIdx]
    : null;
  const chapterPlotRaw = (chapMeta && typeof chapMeta.plot === 'string') ? chapMeta.plot : '';
  const chapterSummaryRaw = (chapMeta && typeof chapMeta.summary === 'string') ? chapMeta.summary : '';
  const chapterEvents = Array.isArray(dedCh && dedCh.events)
    ? dedCh.events.filter(s => typeof s === 'string' && s.trim()) : [];
  const ch = _contEnsureChapter(volIdx, chapIdx);
  return {
    chapterPlotRaw, chapterSummaryRaw, chapterEvents,
    ch, content: typeof ch.content === 'string' ? ch.content : '',
    collapsed: !!ch.collapsed,
  };
}

/**
 * 懒渲染章卡：仅创建 chapWrap + header + body 占位，body 不填充内容。
 * 数百章时只创建极简 header（~15 DOM 节点），极大降低首屏 DOM 节点和内存。
 * body 在首次展开时调用 _contPopulateContentCardBody 一次性填充。
 */
function _renderContentCard(volIdx, chapIdx, cardsContainer) {
  const meta = _contGetChapterMeta(volIdx, chapIdx);
  const { chapterPlotRaw, chapterSummaryRaw, chapterEvents, content, collapsed } = meta;

  const chapWrap = document.createElement('div');
  chapWrap.className = 'content-card-wrap';
  chapWrap.setAttribute('data-vol-idx', String(volIdx));
  chapWrap.setAttribute('data-chap-idx', String(chapIdx));
  chapWrap.style.cssText = [
    'border: 1px solid #f0e8f8',
    'border-radius: 10px',
    'background: rgba(255, 255, 255, 0.85)',
    'overflow: hidden',
    'transition: box-shadow 0.25s ease, border-color 0.25s ease',
    'margin-bottom: 14px',
  ].join(';');
  chapWrap.addEventListener('mouseenter', () => {
    chapWrap.style.boxShadow = '0 6px 18px rgba(162, 28, 175, 0.08)';
    chapWrap.style.borderColor = 'rgba(168, 85, 247, 0.25)';
  });
  chapWrap.addEventListener('mouseleave', () => {
    chapWrap.style.boxShadow = '';
    chapWrap.style.borderColor = '#f0e8f8';
  });

  const header = document.createElement('div');
  header.className = 'content-card-header';
  header.style.cssText = [
    'display: flex',
    'align-items: center',
    'justify-content: space-between',
    'gap: 16px',
    'padding: ' + (collapsed ? '13px 18px' : '15px 18px'),
    'background: ' + (collapsed
      ? 'linear-gradient(90deg, rgba(139, 92, 246, 0.08), rgba(168, 85, 247, 0.02))'
      : 'linear-gradient(90deg, rgba(139, 92, 246, 0.1), rgba(168, 85, 247, 0.03))'),
    'cursor: pointer',
    'font-weight: 600',
    'color: #444',
    'user-select: none',
    'transition: background 0.3s ease, padding 0.25s ease',
  ].join(';');
  header.addEventListener('mouseenter', () => {
    header.style.background = collapsed
      ? 'linear-gradient(90deg, rgba(139, 92, 246, 0.13), rgba(168, 85, 247, 0.05))'
      : 'linear-gradient(90deg, rgba(139, 92, 246, 0.15), rgba(139, 92, 246, 0.08))';
  });
  header.addEventListener('mouseleave', () => {
    header.style.background = collapsed
      ? 'linear-gradient(90deg, rgba(139, 92, 246, 0.08), rgba(168, 85, 247, 0.02))'
      : 'linear-gradient(90deg, rgba(139, 92, 246, 0.1), rgba(168, 85, 247, 0.03))';
  });
  header.onclick = () => toggleContentCard(volIdx, chapIdx);

  const headerLeft = document.createElement('div');
  headerLeft.style.cssText = [
    'display: inline-flex', 'align-items: center', 'gap: 12px',
    'min-width: 0', 'flex: 1',
  ].join(';');

  const toggleIconWrap = document.createElement('div');
  toggleIconWrap.style.cssText = [
    'display: inline-flex', 'align-items: center', 'justify-content: center',
    'width: 22px', 'height: 22px', 'border-radius: 50%',
    'background: rgba(139, 92, 246, 0.1)', 'flex-shrink: 0',
    'transition: background 0.25s ease, transform 0.25s ease',
  ].join(';');
  const toggleIcon = document.createElement('i');
  toggleIcon.className = 'content-card-toggle-icon fas ' + (collapsed ? 'fa-chevron-down' : 'fa-chevron-up');
  toggleIcon.style.cssText = 'font-size: 11px; color: #5b21b6;';
  toggleIconWrap.appendChild(toggleIcon);
  headerLeft.appendChild(toggleIconWrap);

  const badge = document.createElement('div');
  badge.style.cssText = [
    'display: inline-flex', 'align-items: center', 'justify-content: center',
    'min-width: 58px', 'height: 26px', 'padding: 0 12px',
    'border-radius: 999px',
    'background: linear-gradient(135deg, #7c3aed, #a855f7)',
    'color: #fff', 'font-size: 16px', 'font-weight: 700',
    'flex-shrink: 0', 'cursor: default',
    'box-shadow: 0 2px 8px rgba(139, 92, 246, 0.22)',
  ].join(';');
  badge.textContent = `第 ${Number(chapIdx) + 1} 章`;
  headerLeft.appendChild(badge);

  const fallbackText = (() => {
    const s = chapterSummaryRaw ? chapterSummaryRaw : chapterPlotRaw;
    if (s) return s.length > 60 ? s.slice(0, 60) + '…' : s;
    const ctLen = (content || '').length;
    return ctLen > 0 ? `正文 ${ctLen} 字` : `章纲 ${(chapterPlotRaw || '').length} 字 / 事件链 ${chapterEvents.length} 条`;
  })();
  if (fallbackText) {
    const sumEl = document.createElement('div');
    sumEl.style.cssText = [
      'font-size: 17px', 'font-weight: 500', 'color: #555',
      'min-width: 0', 'flex: 1',
      'white-space: nowrap', 'overflow: hidden', 'text-overflow: ellipsis',
      'padding-left: 4px', 'padding-right: 12px',
      'max-width: 500px',
    ].join(';');
    sumEl.title = (chapterSummaryRaw || chapterPlotRaw || fallbackText);
    sumEl.textContent = fallbackText;
    headerLeft.appendChild(sumEl);
  }
  header.appendChild(headerLeft);

  const headerRight = document.createElement('div');
  headerRight.style.cssText = [
    'display: inline-flex', 'align-items: center', 'gap: 10px', 'flex-shrink: 0',
  ].join(';');
  headerRight.onclick = (ev) => { if (ev) ev.stopPropagation && ev.stopPropagation(); };

  const saveTip = document.createElement('span');
  saveTip.className = 'content-card-save-tip';
  saveTip.setAttribute('data-vol-idx', String(volIdx));
  saveTip.setAttribute('data-chap-idx', String(chapIdx));
  saveTip.innerText = '已自动保存';
  saveTip.style.cssText = [
    'font-size: 12px', 'color: #5b21b6', 'opacity: 0',
    'transition: opacity 0.3s', 'white-space: nowrap',
    'pointer-events: none', 'margin-right: 4px',
  ].join(';');
  headerRight.appendChild(saveTip);

  const genBtn = document.createElement('button');
  genBtn.type = 'button';
  genBtn.id = `generateContentBtn_${String(volIdx)}_${String(chapIdx)}`;
  genBtn.onclick = (ev) => {
    if (ev) ev.stopPropagation && ev.stopPropagation();
    generateChapterContent(volIdx, chapIdx);
  };
  genBtn.innerHTML = '<i class="fas fa-magic"></i> <span>生成正文</span>';
  genBtn.style.cssText = [
    'display: inline-flex', 'align-items: center', 'gap: 6px',
    'padding: 7px 14px', 'border-radius: 6px',
    'border: 1px solid rgba(168, 85, 247, 0.3)',
    'cursor: pointer', 'color: #6d28d9', 'font-size: 16px', 'font-weight: 600',
    'background: rgba(168, 85, 247, 0.15)',
    'transition: background 0.15s, border-color 0.15s',
    'font-family: inherit', 'line-height: 1.2',
  ].join(';');
  genBtn.addEventListener('mouseenter', () => {
    genBtn.style.background = 'rgba(168, 85, 247, 0.25)';
    genBtn.style.borderColor = 'rgba(168, 85, 247, 0.4)';
  });
  genBtn.addEventListener('mouseleave', () => {
    genBtn.style.background = 'rgba(168, 85, 247, 0.15)';
    genBtn.style.borderColor = 'rgba(168, 85, 247, 0.3)';
  });
  headerRight.appendChild(genBtn);

  const delBtn = document.createElement('button');
  delBtn.type = 'button';
  delBtn.setAttribute('aria-label', '删除本章正文');
  delBtn.innerHTML = '<i class="fas fa-trash-alt"></i>';
  delBtn.title = `删除第 ${chapIdx + 1} 章正文`;
  const hasContent = content.trim().length > 0;
  delBtn.style.cssText = [
    'width: 30px', 'height: 30px', 'border: none',
    'background: none', 'border-radius: 6px',
    'display: inline-flex', 'align-items: center', 'justify-content: center',
    'font-size: 17px', 'padding: 8px',
    'transition: background 0.2s ease, color 0.2s ease, transform 0.12s ease, cursor 0.15s',
    'cursor: ' + (hasContent ? 'pointer' : 'default'),
    'color: ' + (hasContent ? '#999' : '#ddd'),
    'opacity: ' + (hasContent ? '1' : '0.4'),
  ].join(';');
  if (hasContent) {
    delBtn.addEventListener('mouseenter', () => {
      delBtn.style.background = 'rgba(231, 76, 60, 0.12)';
      delBtn.style.color = '#e74c3c';
      delBtn.style.transform = 'scale(1.08)';
    });
    delBtn.addEventListener('mouseleave', () => {
      delBtn.style.background = 'none';
      delBtn.style.color = '#999';
      delBtn.style.transform = 'scale(1)';
    });
    delBtn.addEventListener('mousedown', () => { delBtn.style.transform = 'scale(0.96)'; });
    delBtn.addEventListener('mouseup', () => { delBtn.style.transform = 'scale(1.08)'; });
    delBtn.addEventListener('click', (ev) => {
      ev && ev.preventDefault && ev.preventDefault();
      window.showConfirm({
        title: '确认删除',
        message: `确定删除第 ${Number(volIdx) + 1} 卷第 ${Number(chapIdx) + 1} 章的正文内容吗？此操作不可恢复。`,
        confirmText: '删除',
        cancelText: '取消',
        onConfirm: () => deleteChapterContent(volIdx, chapIdx),
      });
    });
  }
  headerRight.appendChild(delBtn);

  header.appendChild(headerRight);
  chapWrap.appendChild(header);

  // 懒渲染：body 容器已创建，但不填充子节点；首次展开时调用 _contPopulateContentCardBody
  const body = document.createElement('div');
  body.className = 'content-card-body';
  body.setAttribute('data-body-populated', '0');
  body.style.cssText = [
    'padding: 18px 18px 16px',
    'border-top: 1px solid #ede9fe',
    'background: rgba(255, 255, 255, 0.85)',
    'display: ' + (collapsed ? 'none' : 'block'),
    'box-sizing: border-box',
  ].join(';');

  chapWrap.appendChild(body);
  cardsContainer.appendChild(chapWrap);

  // 非折叠态：异步微任务里填充 body，避免卡主线程（createElement 仍会触发 CSS 计算）
  if (!collapsed) {
    requestAnimationFrame(() => _contPopulateContentCardBody(chapWrap, body, volIdx, chapIdx));
  }
}

/**
 * 填充章卡 body 内容：章纲剧情 + 事件链 + 正文 textarea + 音频卡 + 图片卡 + 视频卡。
 * 带幂等守卫：`data-body-populated === '1'` 时直接 return，避免重复构建。
 * 被 _renderContentCard（非折叠章）和 toggleContentCard（首次展开章）调用。
 */
function _contPopulateContentCardBody(chapWrap, body, volIdx, chapIdx) {
  if (body.getAttribute('data-body-populated') === '1') return;
  const meta = _contGetChapterMeta(volIdx, chapIdx);
  const { chapterPlotRaw, chapterSummaryRaw, chapterEvents, content } = meta;
  body.setAttribute('data-body-populated', '1');

  const plotBox = document.createElement('div');
  plotBox.style.cssText = [
    'padding: 14px 16px',
    'border: 1px solid #ede9fe',
    'border-radius: 10px',
    'background: linear-gradient(180deg, rgba(250, 245, 255, 0.9) 0%, rgba(255, 255, 255, 0.95) 100%)',
    'margin-bottom: 14px',
  ].join(';');
  const plotHead = document.createElement('div');
  plotHead.style.cssText = [
    'display: flex', 'align-items: center', 'justify-content: space-between',
    'margin-bottom: 10px',
  ].join(';');
  const plotHeadLeft = document.createElement('div');
  plotHeadLeft.style.cssText = 'font-size: 16px; font-weight: 700; color: #4c1d95; display: inline-flex; align-items: center; gap: 6px;';
  plotHeadLeft.innerHTML = '<i class="fas fa-book-open" style="font-size: 11px;"></i><span>章纲剧情（只读，修改请切到「定章」页）</span>';
  const plotCharCount = document.createElement('div');
  plotCharCount.className = 'char-counter';
  const plotLen = (chapterPlotRaw || '').length;
  plotCharCount.style.cssText = 'pointer-events: auto';
  plotCharCount.textContent = `剧情 ${plotLen} 字 / 摘要 ${(chapterSummaryRaw || '').length} 字`;
  plotHead.appendChild(plotHeadLeft);
  plotHead.appendChild(plotCharCount);
  plotBox.appendChild(plotHead);

  if (chapterPlotRaw) {
    const p = document.createElement('div');
    p.style.cssText = [
      'font-size: 17px', 'line-height: 1.7', 'color: #3f3f46',
      'white-space: pre-wrap', 'word-break: break-word',
      'padding: 0 0 8px', 'margin: 0',
    ].join(';');
    p.textContent = chapterPlotRaw;
    plotBox.appendChild(p);
  }
  if (chapterSummaryRaw) {
    const s = document.createElement('div');
    s.style.cssText = [
      'padding: 8px 10px', 'border-radius: 8px',
      'background: rgba(139, 92, 246, 0.08)',
      'font-size: 17px', 'line-height: 1.6', 'color: #4c1d95',
      'white-space: pre-wrap', 'word-break: break-word',
      'border-left: 3px solid #a78bfa',
    ].join(';');
    s.textContent = '【摘要】' + chapterSummaryRaw;
    plotBox.appendChild(s);
  }
  if (!chapterPlotRaw && !chapterSummaryRaw) {
    const p = document.createElement('div');
    p.style.cssText = 'font-size: 17px; color: #999; padding: 8px 0;';
    p.textContent = '本章尚无章纲剧情，请先在「定章」页面生成或手动填写。';
    plotBox.appendChild(p);
  }
  body.appendChild(plotBox);

  if (chapterEvents.length > 0) {
    const eventsBox = document.createElement('div');
    eventsBox.style.cssText = [
      'padding: 14px 16px',
      'border: 1px solid #ede9fe',
      'border-radius: 10px',
      'background: linear-gradient(180deg, rgba(248, 250, 252, 0.9) 0%, rgba(255, 255, 255, 0.95) 100%)',
      'margin-bottom: 14px',
    ].join(';');
    const eventsHead = document.createElement('div');
    eventsHead.style.cssText = 'font-size: 16px; font-weight: 700; color: #4c1d95; display: inline-flex; align-items: center; gap: 6px; margin-bottom: 10px;';
    eventsHead.innerHTML = `<i class="fas fa-list-ol" style="font-size: 11px;"></i><span>章节事件链（${chapterEvents.length} 条，只读，修改请切到「推演」页）</span>`;
    eventsBox.appendChild(eventsHead);

    const evList = document.createElement('div');
    evList.style.cssText = 'display: flex; flex-direction: column; gap: 8px;';
    for (let i = 0; i < chapterEvents.length; i++) {
      const evItem = document.createElement('div');
      evItem.style.cssText = [
        'padding: 8px 10px',
        'border-radius: 8px',
        'background: rgba(139, 92, 246, 0.05)',
        'font-size: 17px',
        'line-height: 1.6',
        'color: #374151',
        'white-space: pre-wrap',
        'word-break: break-word',
        'border-left: 3px solid #a78bfa',
      ].join(';');
      evItem.textContent = `${i + 1}. ${chapterEvents[i]}`;
      evList.appendChild(evItem);
    }
    eventsBox.appendChild(evList);
    body.appendChild(eventsBox);
  }

  const contentHead = document.createElement('div');
  contentHead.style.cssText = [
    'display: flex', 'align-items: center', 'justify-content: space-between',
    'margin: 0 0 10px',
  ].join(';');
  const contentHeadLeft = document.createElement('div');
  contentHeadLeft.style.cssText = 'font-size: 16px; font-weight: 700; color: #4c1d95; display: inline-flex; align-items: center; gap: 6px;';
  contentHeadLeft.innerHTML = '<i class="fas fa-file-alt" style="font-size: 11px;"></i><span>章节正文</span>';
  const contentCount = document.createElement('div');
  contentCount.className = 'char-counter';
  contentCount.setAttribute('data-content-count', String(volIdx) + '_' + String(chapIdx));
  contentCount.textContent = `${(content || '').length} / ∞`;
  contentCount.style.cssText = 'pointer-events: auto';
  contentHead.appendChild(contentHeadLeft);
  contentHead.appendChild(contentCount);
  body.appendChild(contentHead);

  const ta = document.createElement('textarea');
  ta.rows = 10;
  ta.placeholder = '生成的正文内容将显示在这里，可直接修改，修改后失焦会自动保存...';
  ta.value = content;
  ta.style.cssText = [
    'width: 100%', 'height: 550px', 'min-height: 550px',
    'padding: 14px 16px', 'border-radius: 10px',
    'border: 1px solid #ede9fe',
    'background: rgba(255, 255, 255, 0.85)', 'font-size: 16px',
    'line-height: 1.8', 'color: #333',
    'box-sizing: border-box', 'white-space: pre-wrap',
    'word-break: break-word', 'resize: vertical',
    'outline: none',
    'transition: border-color 0.15s, box-shadow 0.15s',
    'font-family: inherit',
  ].join(';');

  ta.addEventListener('focus', () => {
    ta.style.borderColor = '#c4b5fd';
    ta.style.boxShadow = '0 0 0 3px rgba(139, 92, 246, 0.12)';
  });
  ta.addEventListener('blur', () => {
    ta.style.borderColor = '#ede9fe';
    ta.style.boxShadow = 'none';
    _refreshContentCharCount(volIdx, chapIdx);
    scheduleContentAutoSave(volIdx, chapIdx, true);
  });
  ta.addEventListener('input', () => {
    _refreshContentCharCount(volIdx, chapIdx);
    const cur = _contEnsureChapter(volIdx, chapIdx);
    cur.content = typeof ta.value === 'string' ? ta.value : '';
    scheduleContentAutoSave(volIdx, chapIdx, false);
  });
  body.appendChild(ta);

  // ========== 音频生成统一卡片（控制区 + 播放区合并，背景与图片卡片统一为浅灰0.6透明）==========
  const audioCard = document.createElement('div');
  audioCard.className = 'audio-gen-card';
  audioCard.setAttribute('data-vol-idx', String(volIdx));
  audioCard.setAttribute('data-chap-idx', String(chapIdx));
  audioCard.style.cssText = [
    'margin-top: 12px',
    'border: 1px solid rgba(107,114,128,0.2)',
    'border-radius: 12px',
    'background: rgba(229,231,235,0.6)',
    'overflow: hidden',
    'width: 100%',
    'box-sizing: border-box',
    'box-shadow: 0 2px 8px rgba(107,114,128,0.08)',
  ].join(';');

  // --- 卡片控制区（模型选择 + 音色选择 + 生成按钮）---
  const audioControl = document.createElement('div');
  audioControl.style.cssText = [
    'padding: 12px 14px',
    'display: flex',
    'flex-wrap: wrap',
    'align-items: center',
    'gap: 10px',
    'border-bottom: 1px solid rgba(107,114,128,0.15)',
  ].join(';');

  const audioHeader = document.createElement('div');
  audioHeader.style.cssText = 'display:flex;align-items:center;gap:6px;font-size:14px;font-weight:600;color:#6d28d9;';
  audioHeader.textContent = '音频生成';
  audioControl.appendChild(audioHeader);

  // 音频模型选择器（从 /api/audios/capabilities 获取，切换后重新加载音色列表）
  const audioModelSelect = document.createElement('select');
  audioModelSelect.className = 'tts-model-select';
  audioModelSelect.style.cssText = [
    'padding: 5px 10px', 'border-radius: 6px',
    'border: 1px solid rgba(168,85,247,0.3)',
    'background: #fff',
    'color: #374151', 'font-size: 13px',
    'cursor: pointer', 'font-family: inherit',
    'outline: none', 'transition: border-color 0.15s',
    'min-width: 160px', 'height: 33px', 'line-height: 1.4', 'box-sizing: border-box',
  ].join(';');
  audioModelSelect.innerHTML = '<option value="">加载中...</option>';
  audioControl.appendChild(audioModelSelect);

  // 音色选择 select（高度与图片区控件统一为 33px）
  const speakerSelect = document.createElement('select');
  speakerSelect.className = 'tts-speaker-select';
  speakerSelect.id = `speakerSelect_${String(volIdx)}_${String(chapIdx)}`;
  speakerSelect.style.cssText = [
    'padding: 5px 10px', 'border-radius: 6px',
    'border: 1px solid rgba(168,85,247,0.3)',
    'background: #fff',
    'color: #374151', 'font-size: 13px',
    'cursor: pointer', 'font-family: inherit',
    'outline: none', 'transition: border-color 0.15s',
    'min-width: 180px', 'height: 33px', 'line-height: 1.4', 'box-sizing: border-box',
  ].join(';');
  audioControl.appendChild(speakerSelect);

  // 按指定模型加载音色列表（切换模型时复用）
  async function _loadSpeakersByModel(modelName) {
    speakerSelect.innerHTML = '<option value="">加载中...</option>';
    try {
      const data = await NovelAPI.getSpeakers(modelName || undefined);
      const speakers = (data && Array.isArray(data.speakers)) ? data.speakers : [];
      if (speakers.length > 0) {
        speakerSelect.innerHTML = speakers.map(s =>
          `<option value="${_contEscapeHtml(s.id)}">🎙️ ${_contEscapeHtml(s.name)}</option>`
        ).join('');
      } else {
        speakerSelect.innerHTML = '<option value="">无可用音色</option>';
      }
    } catch (_e) {
      speakerSelect.innerHTML = '<option value="">音色加载失败</option>';
    }
  }

  // 初始化：拉取音频能力元数据，填充模型选择器，加载默认模型音色
  (async () => {
    try {
      const capsData = await NovelAPI.getAudioCapabilities();
      const models = (capsData && Array.isArray(capsData.models)) ? capsData.models : [];
      const defaultModel = (capsData && capsData.default_model) || (models[0] || '');
      if (models.length > 0) {
        audioModelSelect.innerHTML = models.map(m =>
          `<option value="${_contEscapeHtml(m)}">${_contEscapeHtml(m)}</option>`
        ).join('');
        if (defaultModel && models.includes(defaultModel)) {
          audioModelSelect.value = defaultModel;
        }
      } else {
        audioModelSelect.innerHTML = '<option value="">无可用模型</option>';
      }
      await _loadSpeakersByModel(audioModelSelect.value || defaultModel);
    } catch (_e) {
      audioModelSelect.innerHTML = '<option value="">模型加载失败</option>';
      await _loadSpeakersByModel('');
    }
  })();

  // 模型切换 → 重新加载对应音色列表
  audioModelSelect.addEventListener('change', () => {
    _loadSpeakersByModel(audioModelSelect.value);
  });

  // 生成音频按钮（紫色风格，与图片生成按钮基础样式完全统一：透明背景+紫色边框+紫色文字）
  const ttsBtn = document.createElement('button');
  ttsBtn.type = 'button';
  ttsBtn.id = `generateAudioBtn_${String(volIdx)}_${String(chapIdx)}`;
  ttsBtn.innerHTML = '<i class="fas fa-volume-up"></i> <span>生成音频</span>';
  ttsBtn.style.cssText = [
    'display: inline-flex', 'align-items: center', 'gap: 6px',
    'padding: 7px 14px', 'border-radius: 6px',
    'border: 1px solid rgba(168, 85, 247, 0.3)',
    'cursor: pointer', 'color: #6d28d9', 'font-size: 16px', 'font-weight: 600',
    'background: rgba(168, 85, 247, 0.15)',
    'transition: background 0.15s, border-color 0.15s, opacity 0.15s',
    'font-family: inherit', 'line-height: 1.2',
    'margin-left: auto',
  ].join(';');
  ttsBtn.addEventListener('mouseenter', () => {
    if (ttsBtn.disabled) return;
    ttsBtn.style.background = 'rgba(168, 85, 247, 0.25)';
    ttsBtn.style.borderColor = 'rgba(168, 85, 247, 0.4)';
  });
  ttsBtn.addEventListener('mouseleave', () => {
    ttsBtn.style.background = 'rgba(168, 85, 247, 0.15)';
    ttsBtn.style.borderColor = 'rgba(168, 85, 247, 0.3)';
  });
  ttsBtn.onclick = async (ev) => {
    if (ev && ev.stopPropagation) ev.stopPropagation();
    const curText = ta.value.trim();
    if (!curText) {
      if (typeof window.showStatus === 'function') {
        window.showStatus('正文为空，无法生成音频', 'warn');
      }
      return;
    }
    const sessionId = window.currentWorkId || (window._currentSessionId ? String(window._currentSessionId) : '');
    if (!sessionId) {
      if (typeof window.showStatus === 'function') {
        window.showStatus('未找到当前会话', 'error');
      }
      return;
    }
    const selectedSpeaker = speakerSelect.value || '';
    const selectedAudioModel = audioModelSelect.value || '';
    ttsBtn.disabled = true;
    const originalHTML = ttsBtn.innerHTML;
    ttsBtn.style.opacity = '0.6';
    ttsBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>生成中...</span>';

    let sseUnsubscribe = null;
    let sseResolved = false;

    const restoreBtn = () => {
      ttsBtn.disabled = false;
      ttsBtn.style.opacity = '';
      ttsBtn.innerHTML = originalHTML;
    };

    // SSE 监听：匹配本 volume/chapter 的最终态（success=true/false），提前结束等待
    if (typeof window.listenSSE === 'function') {
      sseUnsubscribe = window.listenSSE('task_progress', (detail) => {
        const data = detail && detail.data;
        const meta = data && data.meta;
        if (!meta) return;
        if (Number(meta.volume_index) !== Number(volIdx)) return;
        if (Number(meta.chapter_index) !== Number(chapIdx)) return;
        if (meta.progress !== 100) return;
        if (meta.success !== true && meta.success !== false) return;
        if (sseResolved) return;
        sseResolved = true;
        if (sseUnsubscribe) sseUnsubscribe();
        if (meta.success === true && meta.audio_url) {
          if (typeof window.showStatus === 'function') {
            window.showStatus('音频生成完成', 'success');
          }
          _renderAudioPlayer(chapWrap, meta.audio_url, volIdx, chapIdx);
          restoreBtn();
        } else {
          const errMsg = (typeof meta.error === 'string' && meta.error) ? meta.error : '音频生成失败';
          if (typeof window.showStatus === 'function') window.showStatus(errMsg, 'error', 8);
          restoreBtn();
        }
      });
    }
    // 兜底：20 分钟后自动注销 SSE 监听并恢复按钮
    const fallbackTimer = setTimeout(() => {
      if (!sseResolved) {
        if (sseUnsubscribe) sseUnsubscribe();
        restoreBtn();
        if (typeof window.showStatus === 'function') window.showStatus('音频生成超时，按钮已恢复', 'warning');
      }
    }, 1200000);

    try {
      const result = await NovelAPI.generateAudio(sessionId, volIdx, chapIdx, curText, selectedSpeaker, selectedAudioModel);
      if (sseUnsubscribe) sseUnsubscribe();
      clearTimeout(fallbackTimer);
      // HTTP 返回 OK：如 SSE 未渲染则兜底渲染
      if (result && result.ok) {
        if (!sseResolved) {
          sseResolved = true;
          if (typeof window.showStatus === 'function') {
            const speakerName = result.speaker_name || selectedSpeaker;
            window.showStatus(`音频生成完成（${speakerName}）`, 'success');
          }
          _renderAudioPlayer(chapWrap, result.audio_url, volIdx, chapIdx);
        }
        restoreBtn();
      } else if (!sseResolved) {
        sseResolved = true;
        const msg = (result && (result.detail || result.message)) || '音频生成失败';
        if (typeof window.showStatus === 'function') window.showStatus(msg, 'error', 8);
        restoreBtn();
      }
    } catch (err) {
      if (sseUnsubscribe) sseUnsubscribe();
      clearTimeout(fallbackTimer);
      if (!sseResolved) {
        sseResolved = true;
        const msg = (err && err.message) ? err.message : String(err);
        if (typeof window.showStatus === 'function') window.showStatus('生成音频异常: ' + msg, 'error', 8);
      }
      restoreBtn();
    }
  };
  audioControl.appendChild(ttsBtn);
  audioCard.appendChild(audioControl);

  // --- 卡片播放区（生成成功后渲染，替代原来的 audioPlayerContainer）---
  const audioPlayerContainer = document.createElement('div');
  audioPlayerContainer.className = 'audio-player-container';
  audioPlayerContainer.setAttribute('data-vol-idx', String(volIdx));
  audioPlayerContainer.setAttribute('data-chap-idx', String(chapIdx));
  audioPlayerContainer.style.cssText = [
    'padding: 12px 14px',
    'display: none',
  ].join(';');
  audioCard.appendChild(audioPlayerContainer);

  body.appendChild(audioCard);

  // ========== 图片生成卡片（控制区 + 展示区合并为统一卡片，背景与音频卡片统一为浅灰0.6透明）==========
  const imageCard = document.createElement('div');
  imageCard.className = 'image-gen-card';
  imageCard.setAttribute('data-vol-idx', String(volIdx));
  imageCard.setAttribute('data-chap-idx', String(chapIdx));
  imageCard.style.cssText = [
    'margin-top: 12px',
    'border: 1px solid rgba(107,114,128,0.2)',
    'border-radius: 12px',
    'background: rgba(229,231,235,0.6)',
    'overflow: hidden',
    'width: 100%',
    'box-sizing: border-box',
    'box-shadow: 0 2px 8px rgba(107,114,128,0.08)',
  ].join(';');

  // --- 控制区 ---
  const imgControl = document.createElement('div');
  imgControl.style.cssText = [
    'padding: 12px 14px',
    'display: flex',
    'flex-wrap: wrap',
    'align-items: center',
    'gap: 10px',
    'border-bottom: 1px solid #f3e8ff',
  ].join(';');

  const imgHeader = document.createElement('div');
  imgHeader.style.cssText = 'display:flex;align-items:center;gap:6px;font-size:14px;font-weight:600;color:#6d28d9;';
  imgHeader.textContent = '图片生成';
  imgControl.appendChild(imgHeader);

  // select 统一样式（和音频音色列表高度一致：约 34px）
  const _SELECT_BASE = [
    'padding:5px 10px', 'border:1px solid #d8b4fe', 'border-radius:6px',
    'background:#fff', 'font-size:13px', 'height:33px', 'line-height:1.4',
    'box-sizing:border-box', 'font-family:inherit', 'color:#374151',
  ].join(';');

  // 模型选择器（按能力元数据动态填充）
  const modelSelect = document.createElement('select');
  modelSelect.style.cssText = _SELECT_BASE + ';min-width:130px;';
  imgControl.appendChild(modelSelect);

  // 尺寸选择（按模型动态渲染）
  const sizeSelect = document.createElement('select');
  sizeSelect.style.cssText = _SELECT_BASE + ';min-width:120px;';
  imgControl.appendChild(sizeSelect);

  // 负面提示词（按模型能力条件显示）
  const negInput = document.createElement('input');
  negInput.type = 'text';
  negInput.placeholder = '负面提示词（可选）';
  negInput.style.cssText = 'padding:5px 10px;border:1px solid #d8b4fe;border-radius:6px;font-size:13px;min-width:140px;flex:1;max-width:220px;height:33px;line-height:1.4;box-sizing:border-box;';
  imgControl.appendChild(negInput);

  // 生成数量（按模型 max_count 动态渲染，组图时上限切换为 sequential_max_count）
  const batchLabel = document.createElement('span');
  batchLabel.textContent = '数量';
  batchLabel.style.cssText = 'font-size:13px;color:#6d28d9;';
  imgControl.appendChild(batchLabel);
  const batchSelect = document.createElement('select');
  batchSelect.style.cssText = _SELECT_BASE + ';';
  imgControl.appendChild(batchSelect);

  // ========== wan2.7 特有控件（默认隐藏，由 _applyModelCap 按模型能力切换显示）==========
  // 1. thinking_mode 开关（增强推理 / 仅 wan2.7 且非组图）
  const tmWrap = document.createElement('label');
  tmWrap.style.cssText = 'display:none;align-items:center;gap:4px;font-size:13px;color:#6d28d9;cursor:pointer;user-select:none;white-space:nowrap;';
  const thinkingModeCheckbox = document.createElement('input');
  thinkingModeCheckbox.type = 'checkbox';
  thinkingModeCheckbox.style.cssText = 'width:14px;height:14px;accent-color:#6d28d9;';
  thinkingModeCheckbox.checked = true;
  tmWrap.appendChild(thinkingModeCheckbox);
  tmWrap.insertAdjacentText('beforeend', '思考增强');
  imgControl.appendChild(tmWrap);

  // 2. enable_sequential 组图模式开关（仅 wan2.7）
  const seqWrap = document.createElement('label');
  seqWrap.style.cssText = 'display:none;align-items:center;gap:4px;font-size:13px;color:#6d28d9;cursor:pointer;user-select:none;white-space:nowrap;';
  const sequentialCheckbox = document.createElement('input');
  sequentialCheckbox.type = 'checkbox';
  sequentialCheckbox.style.cssText = 'width:14px;height:14px;accent-color:#6d28d9;';
  sequentialCheckbox.checked = false;
  seqWrap.appendChild(sequentialCheckbox);
  seqWrap.insertAdjacentText('beforeend', '组图连贯');
  imgControl.appendChild(seqWrap);

  // 3. color_palette 可视化颜色选择面板（仅 wan2.7 且非组图；独立成块不挤在控制行）
  //    官方格式：[{"hex":"#RRGGBB","ratio":"xx.xx%"}, ...]，3-10 种颜色（推荐 8 种），ratio 总和须 100%
  const cpPanel = document.createElement('div');
  cpPanel.style.cssText = [
    'display:none',
    'padding:10px 14px',
    'border-top:1px solid rgba(107,114,128,0.12)',
    'background:rgba(249,250,251,0.5)',
  ].join(';');
  // 面板标题行
  const cpHeader = document.createElement('div');
  cpHeader.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap;';
  const cpTitle = document.createElement('span');
  cpTitle.textContent = '自定义配色';
  cpTitle.style.cssText = 'font-size:14px;font-weight:600;color:#6d28d9;white-space:nowrap;';
  cpHeader.appendChild(cpTitle);
  const cpHint = document.createElement('span');
  cpHint.textContent = '选 3-10 种颜色（推荐 8 种），占比总和须为 100%';
  cpHint.style.cssText = 'font-size:14px;color:#6b7280;white-space:nowrap;';
  cpHeader.appendChild(cpHint);
  // 占比总和实时显示
  const cpSum = document.createElement('span');
  cpSum.style.cssText = 'font-size:13px;font-weight:600;margin-left:auto;white-space:nowrap;';
  cpHeader.appendChild(cpSum);
  // 添加颜色按钮（不压缩大小，与控制区控件协调）
  const cpAddBtn = document.createElement('button');
  cpAddBtn.type = 'button';
  cpAddBtn.textContent = '+ 添加颜色';
  cpAddBtn.style.cssText = [
    'padding:6px 12px', 'border-radius:6px', 'font-size:13px',
    'border:1px solid rgba(168,85,247,0.3)', 'background:rgba(168,85,247,0.1)',
    'color:#6d28d9', 'cursor:pointer', 'font-family:inherit', 'white-space:nowrap',
    'height:33px', 'box-sizing:border-box', 'line-height:1.2',
  ].join(';');
  cpHeader.appendChild(cpAddBtn);
  cpPanel.appendChild(cpHeader);
  // 颜色行容器：一行三列 grid 布局
  const cpRows = document.createElement('div');
  cpRows.style.cssText = 'display:grid;grid-template-columns:repeat(3,1fr);gap:8px;';
  cpPanel.appendChild(cpRows);

  // 占比总和实时校验与显示（需求5：强制2位小数精度；需求6：总和去掉 ✓ 符号）
  function _normalizeRatio(inp) {
    const raw = inp.value;
    if (raw === '' || raw === null || raw === undefined) return;
    // 允许：可选负号+数字+可选小数+可选2位小数
    const num = parseFloat(raw);
    if (isNaN(num)) return;
    const clamped = Math.max(0, Math.min(100, num));
    // 保留最多 2 位小数，避免 3 位小数导致的浮点漂移问题
    const fixed = Number(clamped.toFixed(2));
    const dispStr = fixed.toString();
    if (dispStr !== raw) {
      inp.value = dispStr;
    }
  }
  function _updateCpSum() {
    let total = 0;
    const inputs = cpRows.querySelectorAll('input[data-cp-ratio]');
    inputs.forEach(inp => {
      _normalizeRatio(inp);
      const v = parseFloat(inp.value);
      if (!isNaN(v)) total += v;
    });
    // 用 2 位小数精确展示，避免浮点漂移
    total = Number(total.toFixed(2));
    const ok = Math.abs(total - 100) < 0.005;
    // 需求6：总和显示去掉 ✓ 符号
    cpSum.textContent = ok ? `占比总和: ${total.toFixed(2)}%` : `占比总和: ${total.toFixed(2)}% (需为100%)`;
    cpSum.style.color = ok ? '#16a34a' : '#dc2626';
  }
  // 添加一行颜色（hex 默认值 + 占比输入 + 删除按钮）
  const CP_DEFAULT_COLORS = ['#C2D1E6', '#CDD8E9', '#B5C8DB', '#C0B5B4', '#DAE0EC', '#636574', '#CACAD2', '#CBD4E4'];
  function _addColorRow(hex) {
    if (cpRows.children.length >= 10) {
      if (typeof window.showStatus === 'function') window.showStatus('最多 10 种颜色', 'warn');
      return;
    }
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:4px;min-width:0;';
    // 颜色选择器（HTML5 color picker）
    const colorInput = document.createElement('input');
    colorInput.type = 'color';
    colorInput.value = hex || '#000000';
    colorInput.style.cssText = [
      'width:34px', 'height:33px', 'padding:0', 'border:1px solid #d8b4fe',
      'border-radius:6px', 'cursor:pointer', 'background:none', 'box-sizing:border-box', 'flex-shrink:0',
    ].join(';');
    row.appendChild(colorInput);
    // hex 文本显示（只读，跟随 color picker）
    const hexLabel = document.createElement('span');
    hexLabel.textContent = colorInput.value.toUpperCase();
    hexLabel.style.cssText = 'font-size:11px;color:#374151;font-family:monospace;flex-shrink:0;';
    colorInput.addEventListener('input', () => { hexLabel.textContent = colorInput.value.toUpperCase(); });
    row.appendChild(hexLabel);
    // 占比输入（数字，单位 %，flex 占满剩余空间）
    const ratioInput = document.createElement('input');
    ratioInput.type = 'number';
    ratioInput.step = '0.01';
    ratioInput.min = '0';
    ratioInput.max = '100';
    ratioInput.placeholder = '占比';
    ratioInput.setAttribute('data-cp-ratio', '1');
    ratioInput.style.cssText = [
      'width:0', 'flex:1', 'min-width:50px', 'padding:5px 6px', 'border:1px solid #d8b4fe', 'border-radius:6px',
      'font-size:12px', 'height:33px', 'line-height:1.4', 'box-sizing:border-box',
    ].join(';');
    // 输入过程就做 2 位小数强制归一（失焦再兜底一次）
    ratioInput.addEventListener('input', () => {
      _normalizeRatio(ratioInput);
      _updateCpSum();
    });
    ratioInput.addEventListener('blur', () => {
      _normalizeRatio(ratioInput);
      _updateCpSum();
    });
    row.appendChild(ratioInput);
    const pctLabel = document.createElement('span');
    pctLabel.textContent = '%';
    pctLabel.style.cssText = 'font-size:12px;color:#6b7280;flex-shrink:0;';
    row.appendChild(pctLabel);
    // 删除按钮（至少保留 3 行）
    const delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.textContent = '✕';
    delBtn.title = '删除此颜色';
    delBtn.style.cssText = [
      'width:28px', 'height:28px', 'border-radius:6px', 'font-size:12px',
      'border:1px solid rgba(220,38,38,0.3)', 'background:rgba(220,38,38,0.08)',
      'color:#dc2626', 'cursor:pointer', 'padding:0', 'line-height:1', 'flex-shrink:0',
    ].join(';');
    delBtn.onclick = () => {
      if (cpRows.children.length <= 3) {
        if (typeof window.showStatus === 'function') window.showStatus('至少保留 3 种颜色', 'warn');
        return;
      }
      row.remove();
      _updateCpSum();
    };
    row.appendChild(delBtn);
    cpRows.appendChild(row);
    _updateCpSum();
  }
  cpAddBtn.onclick = () => _addColorRow(CP_DEFAULT_COLORS[cpRows.children.length % CP_DEFAULT_COLORS.length]);
  // 收集配色数据为官方格式 [{hex, ratio:"xx.xx%"}]，校验失败返回 null
  function _collectColorPalette() {
    const rows = cpRows.children;
    if (rows.length < 3 || rows.length > 10) return null;
    let total = 0;
    const items = [];
    for (const row of rows) {
      const colorInput = row.querySelector('input[type="color"]');
      const ratioInput = row.querySelector('input[data-cp-ratio]');
      if (!colorInput || !ratioInput) continue;
      const hex = colorInput.value.toUpperCase();
      const ratioVal = parseFloat(ratioInput.value);
      if (isNaN(ratioVal) || ratioVal < 0 || ratioVal > 100) return null;
      total += ratioVal;
      items.push({ hex, ratio_num: ratioVal });
    }
    if (items.length < 3 || Math.abs(total - 100) > 0.01) return null;
    return items.map(it => ({ hex: it.hex, ratio: `${it.ratio_num.toFixed(2)}%` }));
  }
  // 默认填充 8 种推荐颜色（占比留空由用户填，触发总和校验）
  function _resetColorPalette() {
    cpRows.innerHTML = '';
    for (let i = 0; i < 8; i++) {
      _addColorRow(CP_DEFAULT_COLORS[i]);
    }
  }
  _resetColorPalette();

  // 生成按钮（紫色风格，与生成正文/音频按钮完全统一）
  const imgBtn = document.createElement('button');
  imgBtn.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i> <span>生成图片</span>';
  imgBtn.style.cssText = [
    'display: inline-flex', 'align-items: center', 'gap: 6px',
    'padding: 7px 14px', 'border-radius: 6px',
    'border: 1px solid rgba(168, 85, 247, 0.3)',
    'cursor: pointer', 'color: #6d28d9', 'font-size: 16px', 'font-weight: 600',
    'background: rgba(168, 85, 247, 0.15)',
    'transition: background 0.15s, border-color 0.15s, opacity 0.15s',
    'font-family: inherit', 'line-height: 1.2',
    'margin-left: auto',
  ].join(';');
  imgBtn.addEventListener('mouseenter', () => {
    if (imgBtn.disabled) return;
    imgBtn.style.background = 'rgba(168, 85, 247, 0.25)';
    imgBtn.style.borderColor = 'rgba(168, 85, 247, 0.4)';
  });
  imgBtn.addEventListener('mouseleave', () => {
    imgBtn.style.background = 'rgba(168, 85, 247, 0.15)';
    imgBtn.style.borderColor = 'rgba(168, 85, 247, 0.3)';
  });
  imgControl.appendChild(imgBtn);

  imageCard.appendChild(imgControl);

  // --- 自定义配色面板（控制区下方，画面提示词上方）---
  imageCard.appendChild(cpPanel);

  // --- 提示词输入区（配色面板下方、图片展示上方）---
  const promptArea = document.createElement('div');
  promptArea.style.cssText = 'padding:10px 14px;border-top:1px solid rgba(107,114,128,0.12);';
  // 标题行：左「画面提示词」标签 + 右字符统计（与章节正文 contentHead flex space-between 布局完全统一）
  const promptHead = document.createElement('div');
  promptHead.style.cssText = 'display:flex;align-items:center;justify-content:space-between;margin:0 0 6px;';
  const promptLabel = document.createElement('div');
  promptLabel.textContent = '画面提示词';
  promptLabel.style.cssText = 'font-size:14px;font-weight:600;color:#6d28d9;';
  promptHead.appendChild(promptLabel);
  // 右侧：自动保存提示 + 字符统计（与章节正文 headerRight 布局一致）
  const promptHeadRight = document.createElement('div');
  promptHeadRight.style.cssText = 'display:inline-flex;align-items:center;gap:10px;';
  // 自动保存提示（与正文 content-card-save-tip 样式/行为完全同源）
  const promptSaveTip = document.createElement('span');
  promptSaveTip.innerText = '已自动保存';
  promptSaveTip.style.cssText = [
    'font-size: 12px', 'color: #5b21b6', 'opacity: 0',
    'transition: opacity 0.3s', 'white-space: nowrap',
    'pointer-events: none',
  ].join(';');
  promptHeadRight.appendChild(promptSaveTip);
  // 字符统计：复用全局 .char-counter + .char-counter--inline 样式（与章节正文字符统计同源 SSOT）
  const promptCount = document.createElement('div');
  promptCount.className = 'char-counter char-counter--inline';
  promptCount.style.cssText = 'pointer-events:auto;';
  promptHeadRight.appendChild(promptCount);
  promptHead.appendChild(promptHeadRight);
  promptArea.appendChild(promptHead);

  // textarea 包裹层：position:relative 让优化按钮能 absolute 定位在 textarea 内右下角
  const promptTextareaWrap = document.createElement('div');
  promptTextareaWrap.style.cssText = 'position:relative;';
  const promptTextarea = document.createElement('textarea');
  promptTextarea.placeholder = '输入画面描述，可直接生成或点右下角按钮优化';
  promptTextarea.maxLength = _getImagePromptMaxChars();
  promptTextarea.rows = 7;
  promptTextarea.style.cssText = [
    'width:100%', 'padding:8px 10px 36px 10px',
    'border:1px solid #d8b4fe', 'border-radius:6px',
    'font-size:13px', 'line-height:1.5', 'box-sizing:border-box',
    'font-family:inherit', 'resize:vertical', 'outline:none',
  ].join(';');
  // 失焦自动保存：与章节正文 ta.blur 逻辑对齐，持久化最新 prompt 到后端，并闪烁保存提示
  promptTextarea.addEventListener('blur', async () => {
    const sessionId = window.currentWorkId || (window._currentSessionId ? String(window._currentSessionId) : '');
    if (!sessionId) return;
    const val = promptTextarea.value.trim();
    if (!val) return;
    try {
      await NovelAPI.upsertImagePrompt(sessionId, volIdx, chapIdx, val);
      // 保存成功：闪烁紫色"已自动保存"（与正文 _flashContentSaveTip 行为一致）
      promptSaveTip.innerText = '已自动保存';
      promptSaveTip.style.color = '#5b21b6';
      promptSaveTip.style.opacity = '1';
      clearTimeout(promptSaveTip._t);
      promptSaveTip._t = setTimeout(() => { promptSaveTip.style.opacity = '0'; }, 1600);
    } catch (_e) {
      // 保存失败：闪烁红色提示（静默，不阻塞用户输入）
      promptSaveTip.innerText = '保存失败，请稍后重试';
      promptSaveTip.style.color = '#dc2626';
      promptSaveTip.style.opacity = '1';
      clearTimeout(promptSaveTip._t);
      promptSaveTip._t = setTimeout(() => { promptSaveTip.style.opacity = '0'; }, 1600);
    }
  });
  promptTextareaWrap.appendChild(promptTextarea);

  // 优化提示词按钮：absolute 定位在 textarea 内右下角（仅点击才调 LLM 能力，不默认触发）
  const refineBtn = document.createElement('button');
  refineBtn.type = 'button';
  refineBtn.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i> <span>优化</span>';
  refineBtn.title = '调用模型优化提示词';
  refineBtn.style.cssText = [
    'position:absolute', 'right:6px', 'bottom:8px',
    'display:inline-flex', 'align-items:center', 'gap:4px',
    'padding:5px 10px', 'border-radius:5px', 'font-size:12px',
    'border:1px solid rgba(168,85,247,0.4)', 'background:rgba(255,255,255,0.95)',
    'color:#6d28d9', 'cursor:pointer', 'font-family:inherit', 'white-space:nowrap',
    'height:26px', 'box-sizing:border-box', 'line-height:1', 'z-index:2',
  ].join(';');
  refineBtn.onclick = async () => {
    const sessionId = window.currentWorkId || (window._currentSessionId ? String(window._currentSessionId) : '');
    if (!sessionId) {
      if (typeof window.showStatus === 'function') window.showStatus('请先选择一个作品', 'error');
      return;
    }
    const rawPrompt = promptTextarea.value.trim();
    if (!rawPrompt) {
      if (typeof window.showStatus === 'function') window.showStatus('请先输入画面提示词', 'warn');
      return;
    }
    refineBtn.disabled = true;
    const origHtml = refineBtn.innerHTML;
    refineBtn.style.opacity = '0.6';
    refineBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>优化中</span>';
    try {
      const result = await NovelAPI.refineImagePrompt(sessionId, rawPrompt);
      if (result && typeof result.prompt_text === 'string' && result.prompt_text.trim()) {
        const refined = result.prompt_text.trim();
        const limit = _getImagePromptMaxChars();
        if (refined.length > limit) {
          promptTextarea.value = refined.slice(0, limit);
          if (typeof window.showStatus === 'function') {
            window.showStatus(`提示词已优化，超出 ${limit} 字符上限已截断`, 'warning');
          }
        } else {
          promptTextarea.value = refined;
          if (typeof window.showStatus === 'function') {
            window.showStatus('提示词已优化', 'success');
          }
        }
        _updatePromptCount();
      } else {
        if (typeof window.showStatus === 'function') window.showStatus('提示词优化失败，请重试', 'error');
      }
    } catch (err) {
      const msg = (err && (err.message || (err.response && err.response.data && err.response.data.detail))) || String(err);
      if (typeof window.showStatus === 'function') window.showStatus('提示词优化异常：' + msg, 'error');
    } finally {
      refineBtn.disabled = false;
      refineBtn.style.opacity = '';
      refineBtn.innerHTML = origHtml;
    }
  };
  promptTextareaWrap.appendChild(refineBtn);
  promptArea.appendChild(promptTextareaWrap);

  // 字符统计：实时刷新 + 超限截断推送（上限走 SSOT 动态读取，不硬编码）
  function _updatePromptCount() {
    const limit = _getImagePromptMaxChars();
    const n = promptTextarea.value.length;
    promptCount.textContent = `${n} / ${limit}`;
    // 超限用全局 .char-counter--over 红色样式（与章节正文超限样式同源）
    if (n >= limit) {
      promptCount.classList.add('char-counter--over');
    } else {
      promptCount.classList.remove('char-counter--over');
    }
  }
  promptTextarea.addEventListener('input', () => {
    const limit = _getImagePromptMaxChars();
    let v = promptTextarea.value;
    if (v.length > limit) {
      promptTextarea.value = v.slice(0, limit);
      if (typeof window.showStatus === 'function') {
        window.showStatus(`提示词字符上限 ${limit}，超出部分已自动截断`, 'warning');
      }
    }
    _updatePromptCount();
  });
  _updatePromptCount();
  // 需求1：promptArea 必须挂载到 imageCard 才能渲染（之前漏挂导致 textarea 消失）
  imageCard.appendChild(promptArea);

  // --- 展示区（生成后渲染图片网格）：根据图片数量动态列数，统一卡片高度避免喧宾夺主 ---
  const imgGalleryContainer = document.createElement('div');
  imgGalleryContainer.className = 'img-gallery-container';
  imgGalleryContainer.setAttribute('data-vol-idx', String(volIdx));
  imgGalleryContainer.setAttribute('data-chap-idx', String(chapIdx));
  imgGalleryContainer.style.cssText = [
    'padding: 12px 14px',
    'display: none',
    'grid-template-columns: repeat(3, 1fr)',
    'gap: 12px',
    'max-width: 100%',
  ].join(';');
  imageCard.appendChild(imgGalleryContainer);

  body.appendChild(imageCard);

  // ========== 视频生成统一卡片（紧随图片卡片之后）==========
  const videoCard = document.createElement('div');
  videoCard.className = 'video-gen-card';
  videoCard.setAttribute('data-vol-idx', String(volIdx));
  videoCard.setAttribute('data-chap-idx', String(chapIdx));
  videoCard.style.cssText = [
    'margin-top: 12px',
    'border: 1px solid rgba(107,114,128,0.2)',
    'border-radius: 12px',
    'background: rgba(229,231,235,0.6)',
    'overflow: hidden',
    'width: 100%',
    'box-sizing: border-box',
    'box-shadow: 0 2px 8px rgba(107,114,128,0.08)',
  ].join(';');

  // --- 控制区 ---
  const videoControl = document.createElement('div');
  videoControl.style.cssText = [
    'padding: 12px 14px',
    'display: flex',
    'flex-wrap: wrap',
    'align-items: center',
    'gap: 10px',
    'border-bottom: 1px solid rgba(107,114,128,0.15)',
  ].join(';');

  const videoHeader = document.createElement('div');
  videoHeader.style.cssText = 'display:flex;align-items:center;gap:6px;font-size:14px;font-weight:600;color:#6d28d9;min-width:100%;margin-bottom:4px;';
  videoHeader.innerHTML = '<span>视频生成</span>';
  const genVideoBtn = document.createElement('button');
  genVideoBtn.type = 'button';
  genVideoBtn.innerHTML = '<i class="fas fa-film"></i> <span>生成视频</span>';
  genVideoBtn.style.cssText = [
    'display: inline-flex', 'align-items: center', 'gap: 6px',
    'padding: 7px 14px', 'border-radius: 6px',
    'border: 1px solid rgba(168, 85, 247, 0.3)',
    'cursor: pointer', 'color: #6d28d9', 'font-size: 16px', 'font-weight: 600',
    'background: rgba(168, 85, 247, 0.15)',
    'transition: background 0.15s, border-color 0.15s, opacity 0.15s',
    'font-family: inherit', 'line-height: 1.2',
    'margin-left: auto',
  ].join(';');
  videoHeader.appendChild(genVideoBtn);
  videoControl.appendChild(videoHeader);

  // 公共样式：select / input / label
  const _selectCss = [
    'padding: 5px 10px', 'border-radius: 6px',
    'border: 1px solid rgba(168,85,247,0.3)',
    'background: #fff', 'color: #374151', 'font-size: 13px',
    'cursor: pointer', 'font-family: inherit',
    'outline: none', 'transition: border-color 0.15s',
    'min-width: 120px', 'height: 33px', 'line-height: 1.4', 'box-sizing: border-box',
  ].join(';');
  const _numCss = [
    'padding: 5px 10px', 'border-radius: 6px',
    'border: 1px solid rgba(168,85,247,0.3)',
    'background: #fff', 'color: #374151', 'font-size: 13px',
    'font-family: inherit', 'outline: none',
    'transition: border-color 0.15s',
    'width: 80px', 'height: 33px', 'line-height: 1.4', 'box-sizing: border-box',
  ].join(';');
  const _labelCss = 'font-size:13px;color:#4b5563;display:inline-flex;align-items:center;gap:4px;';
  const _chkCss = 'width:15px;height:15px;accent-color:#6d28d9;';

  function _mkLabel(text, targetId) {
    const l = document.createElement('label');
    l.textContent = text;
    l.style.cssText = _labelCss;
    if (targetId) l.htmlFor = targetId;
    return l;
  }

  // 分组选择器：折叠式，参照图片卡片 color_palette 面板
  function _mkGroup(title, opts) {
    const wrap = document.createElement('details');
    wrap.open = opts && opts.defaultOpen !== false;
    wrap.style.cssText = [
      'width: 100%',
      'border: 1px solid rgba(168,85,247,0.2)',
      'border-radius: 8px',
      'background: rgba(255,255,255,0.65)',
      'margin-bottom: 8px',
      'box-sizing: border-box',
    ].join(';');
    const sum = document.createElement('summary');
    sum.style.cssText = [
      'padding: 6px 10px',
      'cursor: pointer',
      'font-size: 13px',
      'font-weight: 600',
      'color: #6d28d9',
      'list-style: none',
      'user-select: none',
    ].join(';');
    sum.innerHTML = `<i class="fas fa-chevron-down" style="font-size:11px;margin-right:6px;transition:transform .15s;"></i>${title}`;
    // 简单箭头旋转
    wrap.addEventListener('toggle', () => {
      const ic = sum.querySelector('i');
      if (ic) ic.style.transform = wrap.open ? 'rotate(0deg)' : 'rotate(-90deg)';
    });
    const body = document.createElement('div');
    body.style.cssText = [
      'padding: 10px 12px',
      'display: flex', 'flex-wrap: wrap',
      'gap: 10px 14px', 'align-items: center',
      'border-top: 1px solid rgba(168,85,247,0.15)',
    ].join(';');
    wrap.appendChild(sum);
    wrap.appendChild(body);
    return { wrap, body };
  }

  // 基础设置组（默认展开）
  const g1 = _mkGroup('基础设置', { defaultOpen: true });
  // 画面组件
  const videoSizeSelect = document.createElement('select');
  videoSizeSelect.style.cssText = _selectCss;
  [
    ['auto', '自动 (按首图)'],
    ['9:16', '9:16 竖屏'],
    ['16:9', '16:9 横屏'],
    ['1:1', '1:1 方形'],
    ['4:3', '4:3 标准'],
    ['3:4', '3:4 标准竖'],
  ].forEach(([v, l]) => {
    const o = document.createElement('option'); o.value = v; o.textContent = l;
    if (v === 'auto') o.selected = true;
    videoSizeSelect.appendChild(o);
  });
  const qualitySelect = document.createElement('select');
  qualitySelect.style.cssText = _selectCss;
  [
    ['low', '低质量'],
    ['medium', '中等'],
    ['high', '高质量 (默认)'],
    ['ultra', '超清'],
  ].forEach(([v, l]) => {
    const o = document.createElement('option'); o.value = v; o.textContent = l;
    if (v === 'high') o.selected = true;
    qualitySelect.appendChild(o);
  });
  // 图片序列组件
  const intervalInput = document.createElement('input');
  intervalInput.type = 'number';
  intervalInput.value = 8;
  intervalInput.min = 1;
  intervalInput.max = 60;
  intervalInput.step = 1;
  intervalInput.style.cssText = _numCss;
  // 图片选择：从后端 API 加载当前章节的全部图片（生成 + 上传），展示为缩略图网格
  const imgSelectorWrap = document.createElement('div');
  imgSelectorWrap.style.cssText = 'width:100%;display:flex;flex-direction:column;gap:6px;margin-top:8px;';
  const imgSelectorHint = document.createElement('div');
  imgSelectorHint.style.cssText = 'font-size:12px;color:#6b7280;line-height:1.5;';
  imgSelectorHint.textContent = '勾选下方图片作为视频画面素材（至少1张）。支持生成的图片和已上传的背景图片。';
  const imgSelectorList = document.createElement('div');
  imgSelectorList.style.cssText = [
    'display:grid', 'grid-template-columns: repeat(8, 1fr)',
    'gap: 8px', 'width:100%', 'max-height:240px', 'overflow-y:auto',
  ].join(';');
  imgSelectorWrap.appendChild(imgSelectorHint);
  imgSelectorWrap.appendChild(imgSelectorList);

  g1.body.appendChild(_mkLabel('视频尺寸'));
  g1.body.appendChild(videoSizeSelect);
  g1.body.appendChild(_mkLabel('画面质量'));
  g1.body.appendChild(qualitySelect);
  g1.body.appendChild(_mkLabel('单图秒数'));
  g1.body.appendChild(intervalInput);
  g1.body.appendChild(imgSelectorWrap);
  videoControl.appendChild(g1.wrap);

  // 转场设置组（默认展开）
  const g2 = _mkGroup('转场设置', { defaultOpen: true });
  const transEnable = document.createElement('input');
  transEnable.type = 'checkbox';
  transEnable.checked = true;
  transEnable.style.cssText = _chkCss;
  const transTypeSelect = document.createElement('select');
  transTypeSelect.style.cssText = _selectCss;
  [
    ['fade', '淡入淡出（呼吸感）'],
    ['dissolve', '溶解过渡（半隐半显）'],
    ['smoothleft', '平滑滑动（柔顺推移）'],
    ['circleopen', '圆形展开（涟漪感）'],
  ].forEach(([v, l]) => {
    const o = document.createElement('option'); o.value = v; o.textContent = l;
    if (v === 'fade') o.selected = true;
    transTypeSelect.appendChild(o);
  });
  const transDurInput = document.createElement('input');
  transDurInput.type = 'number';
  transDurInput.value = 2;
  transDurInput.step = 0.1;
  transDurInput.min = 0.5;
  transDurInput.max = 8;
  transDurInput.style.cssText = _numCss;
  g2.body.appendChild(transEnable);
  const teLbl = _mkLabel('启用转场');
  teLbl.style.cssText = _labelCss + 'font-weight:500;color:#6d28d9;';
  teLbl.insertBefore(transEnable, teLbl.firstChild);
  teLbl.htmlFor = '';
  g2.body.appendChild(teLbl);
  g2.body.appendChild(_mkLabel('转场类型'));
  g2.body.appendChild(transTypeSelect);
  g2.body.appendChild(_mkLabel('转场时长(秒)'));
  g2.body.appendChild(transDurInput);
  videoControl.appendChild(g2.wrap);

  // 铅笔画设置组（默认展开）
  const g3 = _mkGroup('铅笔画特效', { defaultOpen: true });
  const sketchEnable = document.createElement('input');
  sketchEnable.type = 'checkbox';
  sketchEnable.checked = false;
  sketchEnable.style.cssText = _chkCss;
  const skChkLbl = _mkLabel('启用铅笔画');
  skChkLbl.style.cssText = _labelCss + 'font-weight:500;color:#6d28d9;';
  skChkLbl.insertBefore(sketchEnable, skChkLbl.firstChild);
  skChkLbl.htmlFor = '';

  const sketchDirSelect = document.createElement('select');
  sketchDirSelect.style.cssText = _selectCss;
  [
    ['sketch_to_real', '素描 → 原图'],
    ['real_to_sketch', '原图 → 素描'],
  ].forEach(([v, l]) => {
    const o = document.createElement('option'); o.value = v; o.textContent = l;
    if (v === 'sketch_to_real') o.selected = true;
    sketchDirSelect.appendChild(o);
  });

  function _mkRange(min, max, step, value, w) {
    const r = document.createElement('input');
    r.type = 'range';
    r.min = String(min); r.max = String(max); r.step = String(step); r.value = String(value);
    r.style.cssText = `accent-color:#6d28d9;vertical-align:middle;width:${w || 140}px;`;
    return r;
  }
  const sketchDurInput = document.createElement('input');
  sketchDurInput.type = 'number';
  sketchDurInput.value = 5; sketchDurInput.min = 0; sketchDurInput.step = 0.5;
  sketchDurInput.style.cssText = _numCss;
  const sketchBlurRange = _mkRange(3, 41, 2, 15, 120);
  const sketchBlurVal = document.createElement('span');
  sketchBlurVal.style.cssText = 'font-size:12px;color:#4b5563;min-width:22px;';
  sketchBlurVal.textContent = '15';
  sketchBlurRange.addEventListener('input', () => sketchBlurVal.textContent = sketchBlurRange.value);
  const sketchIntensityRange = _mkRange(0, 2, 0.05, 0.80, 120);
  const sketchIntensityVal = document.createElement('span');
  sketchIntensityVal.style.cssText = 'font-size:12px;color:#4b5563;min-width:22px;';
  sketchIntensityVal.textContent = '0.80';
  sketchIntensityRange.addEventListener('input', () => sketchIntensityVal.textContent = sketchIntensityRange.value);
  const sketchSharpenRange = _mkRange(0, 2, 0.1, 0.65, 120);
  const sketchSharpenVal = document.createElement('span');
  sketchSharpenVal.style.cssText = 'font-size:12px;color:#4b5563;min-width:22px;';
  sketchSharpenVal.textContent = '0.65';
  sketchSharpenRange.addEventListener('input', () => sketchSharpenVal.textContent = sketchSharpenRange.value);

  g3.body.appendChild(skChkLbl);
  g3.body.appendChild(_mkLabel('渐变方向'));
  g3.body.appendChild(sketchDirSelect);
  g3.body.appendChild(_mkLabel('渐变时长(秒)'));
  g3.body.appendChild(sketchDurInput);

  const blurRow = document.createElement('div');
  blurRow.style.cssText = 'display:inline-flex;align-items:center;gap:6px;';
  blurRow.appendChild(_mkLabel('模糊核'));
  blurRow.appendChild(sketchBlurRange);
  blurRow.appendChild(sketchBlurVal);
  g3.body.appendChild(blurRow);

  const intensityRow = document.createElement('div');
  intensityRow.style.cssText = 'display:inline-flex;align-items:center;gap:6px;';
  intensityRow.appendChild(_mkLabel('素描强度'));
  intensityRow.appendChild(sketchIntensityRange);
  intensityRow.appendChild(sketchIntensityVal);
  g3.body.appendChild(intensityRow);

  const sharpenRow = document.createElement('div');
  sharpenRow.style.cssText = 'display:inline-flex;align-items:center;gap:6px;';
  sharpenRow.appendChild(_mkLabel('线条锐化'));
  sharpenRow.appendChild(sketchSharpenRange);
  sharpenRow.appendChild(sketchSharpenVal);
  g3.body.appendChild(sharpenRow);

  videoControl.appendChild(g3.wrap);

  // 刷新图片选择器：从后端 API 加载当前章节的全部图片
  let _refreshInProgress = false;
  async function _refreshVideoImageOptions() {
    if (_refreshInProgress) return;
    _refreshInProgress = true;
    try {
      imgSelectorList.innerHTML = '';

      let allImages = [];
      try {
        const sessionId = window.currentWorkId || (window._currentSessionId ? String(window._currentSessionId) : '');
        if (sessionId) {
          const resp = await NovelAPI.getImagesByChapter(sessionId, volIdx, chapIdx);
          if (resp && resp.ok && Array.isArray(resp.images)) {
            allImages = resp.images;
          }
        }
      } catch (_e) { /* 静默失败，走 DOM 兜底 */ }

      // 兜底：从当前章节已渲染的 DOM 图片中提取
      if (allImages.length === 0) {
        const imgGallery = chapWrap.querySelector('.img-gallery-container');
        const imgs = (imgGallery && imgGallery.querySelectorAll('img')) || [];
        imgs.forEach((imgEl, idx) => {
          allImages.push({
            id: `dom_${idx}`,
            url: imgEl.src,
            file_name: imgEl.src.split('/').pop() || `img_${idx}`,
            image_type: 'generated',
          });
        });
      }

      if (allImages.length === 0) {
        const ph = document.createElement('div');
        ph.style.cssText = 'grid-column:1/-1;font-size:12px;color:#9ca3af;padding:4px 6px;';
        ph.textContent = '暂无可选图片，请先在上方生成或上传图片。';
        imgSelectorList.appendChild(ph);
        return;
      }

      // 前端去重：按 id 去重（防止后端重复返回）
      const seenIds = new Set();
      allImages = allImages.filter(img => {
        const key = img.id || img.url;
        if (seenIds.has(key)) return false;
        seenIds.add(key);
        return true;
      });

      allImages.forEach((imgData, idx) => {
        const item = document.createElement('label');
        item.style.cssText = [
          'display:block', 'position:relative', 'aspect-ratio:1/1',
          'border-radius:6px', 'overflow:hidden', 'cursor:pointer',
          'border:2px solid transparent', 'transition:border-color .15s',
        ].join(';');
        const thumb = document.createElement('img');
        thumb.src = imgData.url || imgData.file_name || '';
        thumb.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;';
        thumb.loading = 'lazy';
        thumb.onerror = () => { thumb.style.opacity = '0.3'; };
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.dataset.imgIdx = String(idx);
        cb.dataset.imgId = imgData.id || '';
        cb.dataset.imgUrl = imgData.url || '';
        cb.style.cssText = [
          'position:absolute', 'left:4px', 'bottom:4px',
          'width:16px', 'height:16px', 'accent-color:#6d28d9',
        ].join(';');
        cb.addEventListener('change', () => {
          item.style.borderColor = cb.checked ? '#6d28d9' : 'transparent';
        });
        // 标记图片类型（上传/生成）
        if (imgData.image_type === 'uploaded') {
          const badge = document.createElement('span');
          badge.textContent = '上传';
          badge.style.cssText = [
            'position:absolute', 'top:2px', 'right:2px', 'font-size:10px',
            'background:rgba(41,128,185,0.85)', 'color:#fff', 'padding:1px 4px',
            'border-radius:3px', 'line-height:1.2',
          ].join(';');
          item.appendChild(badge);
        }
        item.appendChild(thumb);
        item.appendChild(cb);
        imgSelectorList.appendChild(item);
      });
    } finally {
      _refreshInProgress = false;
    }
  }
  // 注册到全局 map，供图片恢复后重新刷新选择器
  if (typeof window._refreshVideoImageOptionsMap !== 'object' || !window._refreshVideoImageOptionsMap) {
    window._refreshVideoImageOptionsMap = {};
  }
  window._refreshVideoImageOptionsMap[`${volIdx}_${chapIdx}`] = _refreshVideoImageOptions;
  // 100ms 延迟初始化，确保图片卡片结构先挂载；再监听一次 SSE 中的 task_progress
  setTimeout(_refreshVideoImageOptions, 150);

  function _hasExistingVideo() {
    const v = chapWrap.querySelector('.video-player-container video');
    return !!(v && v.src);
  }

  function _collectVideoConfig() {
    // 勾选的图片 → 收集 image id（优先用 cb.dataset.imgId，fallback DOM 匹配）
    const checkedBoxes = imgSelectorList.querySelectorAll('input[type=checkbox]:checked');
    const allBoxes = imgSelectorList.querySelectorAll('input[type=checkbox]');
    // 若用户未勾选但图片存在，默认全选
    const effectiveBoxes = checkedBoxes.length > 0 ? checkedBoxes : allBoxes;

    const imageIds = [];
    effectiveBoxes.forEach(cb => {
      const id = cb.dataset.imgId || '';
      if (id && !id.startsWith('dom_') && !imageIds.includes(id)) {
        imageIds.push(id);
      }
    });

    // 若 dom 兜底图片（无真实 id），传空数组让后端按章节查找
    const hasRealIds = imageIds.length > 0;
    const finalImageIds = hasRealIds ? imageIds : [];

    return {
      image_ids: finalImageIds,
      video_size: videoSizeSelect.value,
      quality: qualitySelect.value,
      fps: 25,
      image_interval: parseFloat(intervalInput.value) || 8,
      effects: {
        transition: {
          enabled: transEnable.checked,
          type: transTypeSelect.value,
          duration: parseFloat(transDurInput.value) || 0.8,
        },
        pencil_sketch: {
          enabled: sketchEnable.checked,
          apply_to: [],
          direction: sketchDirSelect.value,
          transition_duration: parseFloat(sketchDurInput.value) || 5,
          blur_size: parseInt(sketchBlurRange.value, 10) || 15,
          intensity: parseFloat(sketchIntensityRange.value) || 0.80,
          sharpen: parseFloat(sketchSharpenRange.value) || 0.65,
        },
      },
    };
  }

  async function _doGenerateVideo() {
    const sessionId = window.currentWorkId || (window._currentSessionId ? String(window._currentSessionId) : '');
    if (!sessionId) {
      if (typeof window.showStatus === 'function') window.showStatus('未找到当前会话', 'error');
      return;
    }
    const audioExist = chapWrap.querySelector('.audio-player-container audio');
    if (!audioExist || !audioExist.src) {
      if (typeof window.showStatus === 'function') {
        window.showStatus('请先生成对应章节的 TTS 音频后再合成视频', 'warn');
      }
      return;
    }
    const cfg = _collectVideoConfig();
    if (!cfg.image_ids || cfg.image_ids.length === 0) {
      if (typeof window.showStatus === 'function') {
        window.showStatus('请先勾选至少一张图片，或先生成/上传图片', 'warn');
      }
      return;
    }
    genVideoBtn.disabled = true;
    const originalHTML = genVideoBtn.innerHTML;
    genVideoBtn.style.opacity = '0.6';
    genVideoBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>生成中...</span>';
    // 先隐藏旧视频播放器，避免生成期间还能播放旧视频
    const oldContainer = chapWrap.querySelector('.video-player-container');
    if (oldContainer) oldContainer.style.display = 'none';

    // === SSE 监听：HTTP 超时后仍能自动刷新播放器 ===
    // 后端合成完成会广播 task_progress（meta.success=true, meta.video_url）。
    // 用正则匹配 _v{volIdx}_c{chapIdx}_ 确认是当前章节的视频，避免误渲染其他章节。
    let sseRendered = false;
    const targetPattern = new RegExp('_v' + volIdx + '_c' + chapIdx + '_');
    const restoreBtn = () => {
      genVideoBtn.disabled = false;
      genVideoBtn.style.opacity = '';
      genVideoBtn.innerHTML = originalHTML;
    };
    const sseUnsubscribe = (typeof window.listenSSE === 'function')
      ? window.listenSSE('task_progress', (detail) => {
          const data = detail && detail.data;
          const meta = data && data.meta;
          if (!meta || meta.success !== true || !meta.video_url) return;
          if (!targetPattern.test(String(meta.video_url))) return;
          if (sseRendered) return;
          sseRendered = true;
          _renderVideoPlayer(chapWrap, meta.video_url);
          if (typeof window.showStatus === 'function') window.showStatus('视频生成完成', 'success');
          restoreBtn();
          if (sseUnsubscribe) sseUnsubscribe();
        })
      : null;
    // 兜底：30 分钟后自动注销 SSE 并恢复按钮，防止永久等待
    const fallbackTimer = setTimeout(() => {
      if (!sseRendered) {
        if (sseUnsubscribe) sseUnsubscribe();
        restoreBtn();
      }
    }, 1800000);

    try {
      const result = await NovelAPI.generateVideo(sessionId, volIdx, chapIdx, cfg);
      // HTTP 成功返回：正常渲染 + 注销 SSE（避免重复渲染）
      if (sseUnsubscribe) sseUnsubscribe();
      clearTimeout(fallbackTimer);
      if (!sseRendered && result && result.ok) {
        if (typeof window.showStatus === 'function') window.showStatus('视频生成完成', 'success');
        _renderVideoPlayer(chapWrap, result.video_url);
        restoreBtn();
      } else if (!sseRendered) {
        const msg = (result && (result.detail || result.message)) || '视频生成失败';
        if (typeof window.showStatus === 'function') window.showStatus(msg, 'error');
        restoreBtn();
      }
    } catch (err) {
      const isTimeout = err && (err.code === 'ECONNABORTED' || (err.message && err.message.includes('timeout')));
      if (isTimeout) {
        // 超时：后端可能仍在合成，保留 SSE 监听等待完成通知
        if (typeof window.showStatus === 'function') {
          window.showStatus('合成仍在后台进行，完成后将自动显示视频', 'info');
        }
        // 不注销 SSE、不清除 fallbackTimer、不恢复按钮（交给 SSE 回调或兜底）
      } else {
        // 非超时错误：注销 SSE，恢复按钮
        if (sseUnsubscribe) sseUnsubscribe();
        clearTimeout(fallbackTimer);
        const msg = (err && err.message) ? err.message : String(err);
        if (typeof window.showStatus === 'function') window.showStatus('生成视频异常: ' + msg, 'error');
        restoreBtn();
      }
    }
  }

  genVideoBtn.addEventListener('click', () => {
    if (genVideoBtn.disabled) return;
    if (_hasExistingVideo()) {
      if (typeof window.showConfirm === 'function') {
        window.showConfirm({
          title: '确认覆盖视频',
          message: '当前章节已存在生成的视频，再次生成将覆盖原有视频，是否确认继续？',
          confirmText: '确认生成',
          cancelText: '取消',
          onConfirm: () => _doGenerateVideo(),
        });
      } else {
        _doGenerateVideo();
      }
    } else {
      _doGenerateVideo();
    }
  });
  genVideoBtn.addEventListener('mouseenter', () => {
    if (genVideoBtn.disabled) return;
    genVideoBtn.style.background = 'rgba(168, 85, 247, 0.25)';
    genVideoBtn.style.borderColor = 'rgba(168, 85, 247, 0.4)';
  });
  genVideoBtn.addEventListener('mouseleave', () => {
    genVideoBtn.style.background = 'rgba(168, 85, 247, 0.15)';
    genVideoBtn.style.borderColor = 'rgba(168, 85, 247, 0.3)';
  });

  videoCard.appendChild(videoControl);

  // 播放器容器
  const videoPlayerContainer = document.createElement('div');
  videoPlayerContainer.className = 'video-player-container';
  videoPlayerContainer.setAttribute('data-vol-idx', String(volIdx));
  videoPlayerContainer.setAttribute('data-chap-idx', String(chapIdx));
  videoPlayerContainer.style.cssText = [
    'padding: 12px 14px',
    'display: none',
  ].join(';');
  videoCard.appendChild(videoPlayerContainer);

  body.appendChild(videoCard);

  // ========== 按模型能力动态渲染控制项 ==========
  function _applyModelCap(cap, _keepSequential) {
    // 1. 尺寸选项
    sizeSelect.innerHTML = '';
    const sizes = (cap && Array.isArray(cap.sizes)) ? cap.sizes : [{ value: '720*1280', label: '720×1280 (9:16 竖)' }];
    const defaultSize = (cap && cap.default_size) || '720*1280';
    sizes.forEach(s => {
      const o = document.createElement('option');
      o.value = s.value; o.textContent = s.label;
      if (s.value === defaultSize) o.selected = true;
      sizeSelect.appendChild(o);
    });
    // 2. 负面提示词可见性（wan2.7 不支持）
    const supportsNeg = cap ? !!cap.supports_negative_prompt : true;
    negInput.style.display = supportsNeg ? '' : 'none';
    if (!supportsNeg) negInput.value = '';
    // 3. wan2.7 特有控件可见性
    const supportsTM = cap ? !!cap.supports_thinking_mode : false;
    const supportsSeq = cap ? !!cap.supports_sequential : false;
    const supportsCP = cap ? !!cap.supports_color_palette : false;
    tmWrap.style.display = supportsTM ? 'inline-flex' : 'none';
    seqWrap.style.display = supportsSeq ? 'inline-flex' : 'none';
    // color_palette 面板可见性：仅 wan2.7 且非组图模式时显示
    const cpVisible = supportsCP && !sequentialCheckbox.checked;
    cpPanel.style.display = cpVisible ? 'block' : 'none';
    // 默认值填充（仅首次切换到该模型时应用，keepSequential=true 时保留用户手动勾选）
    if (supportsSeq && !_keepSequential) {
      const defaults = (cap && cap.defaults) || {};
      sequentialCheckbox.checked = !!defaults.enable_sequential;
    }
    if (supportsTM) {
      const defaults = (cap && cap.defaults) || {};
      thinkingModeCheckbox.checked = defaults.thinking_mode !== false;
    }
    // 4. 批量数选项：上限随 enable_sequential 是否开启切换
    const isSequential = supportsSeq && sequentialCheckbox.checked;
    const maxCount = isSequential
      ? ((cap && cap.sequential_max_count) || 12)
      : ((cap && cap.max_count) || 4);
    const defaultCount = (cap && cap.default_count) || 2;
    const prevVal = Number(batchSelect.value);
    batchSelect.innerHTML = '';
    for (let n = 1; n <= maxCount; n++) {
      const o = document.createElement('option');
      o.value = String(n); o.textContent = `${n}张`;
      if (n === defaultCount) o.selected = true;
      batchSelect.appendChild(o);
    }
    // 还原之前的选择（不超过新上限）
    if (prevVal && prevVal >= 1 && prevVal <= maxCount) {
      batchSelect.value = String(prevVal);
    }
    // 5. 互斥：enable_sequential 勾选 → 禁用 thinking_mode 并隐藏 color_palette 面板
    if (supportsSeq && supportsTM) {
      if (sequentialCheckbox.checked) {
        thinkingModeCheckbox.disabled = true;
        thinkingModeCheckbox.checked = false;
      } else {
        thinkingModeCheckbox.disabled = false;
      }
    } else {
      thinkingModeCheckbox.disabled = false;
    }
    // color_palette 面板在组图模式下直接隐藏（互斥），非组图时按模型能力显示
    cpPanel.style.display = (supportsCP && !sequentialCheckbox.checked) ? 'block' : 'none';
  }

  // enable_sequential 状态变化 → 重新应用能力（重绘 batch 数量上限 + 互斥禁用）
  sequentialCheckbox.addEventListener('change', () => {
    const capsData = window._imageCapabilitiesCache;
    const cap = capsData ? (capsData.models[modelSelect.value] || null) : null;
    _applyModelCap(cap, true);
  });

  // thinking_mode / color_palette 控件自身无需互斥反向联动（已通过 _applyModelCap 统一管控）

  // 初始化：拉取能力元数据，填充模型选择器与风格下拉框并应用默认模型能力
  (async () => {
    const capsData = await _ensureImageCapabilities();
    if (capsData && capsData.models) {
      const modelNames = Object.keys(capsData.models);
      modelNames.forEach(m => {
        const o = document.createElement('option');
        o.value = m; o.textContent = m;
        modelSelect.appendChild(o);
      });
      const defaultModel = capsData.default_model && capsData.models[capsData.default_model]
        ? capsData.default_model
        : (modelNames[0] || '');
      if (defaultModel) modelSelect.value = defaultModel;
      _applyModelCap(capsData.models[defaultModel] || null);
    } else {
      // 兜底：能力接口失败时隐藏模型选择器，用固定配置
      modelSelect.style.display = 'none';
      _applyModelCap(null);
    }
  })();

  // 模型切换 → 重新渲染控制项
  modelSelect.addEventListener('change', () => {
    const capsData = window._imageCapabilitiesCache;
    const cap = capsData ? (capsData.models[modelSelect.value] || null) : null;
    _applyModelCap(cap);
  });

  // ========== 图片生成事件绑定 ==========
  // 生成前先判断：若当前章节已有生成图片 → 弹确认框提示是否覆盖
  function _hasExistingImages() {
    const gal = chapWrap.querySelector('.img-gallery-container');
    if (!gal) return false;
    return gal.querySelectorAll('img').length > 0;
  }
  async function _doGenerateImages() {
    if (imgBtn.disabled) return;
    const sessionId = window.currentWorkId || (window._currentSessionId ? String(window._currentSessionId) : '');
    if (!sessionId) { if (typeof window.showStatus === 'function') window.showStatus('请先选择一个作品', 'error'); return; }
    // 需求1/3：用户输入或优化后的提示词（前端已按 SSOT 上限强制截断），trim 后必须非空；
    // 同时记录最终要发出去的 user_prompt，供持久化 + 注入颜色风格后整体校验。
    const userInputRaw = promptTextarea.value;
    const userInput = typeof userInputRaw === 'string' ? userInputRaw.trim() : '';
    // 兜底截断：以防绕过 input 事件粘贴超长内容（上限走 SSOT 动态读取）。
    const MAX = _getImagePromptMaxChars();
    let finalPrompt = userInput;
    if (finalPrompt.length > MAX) {
      finalPrompt = finalPrompt.slice(0, MAX);
      promptTextarea.value = finalPrompt;
      _updatePromptCount();
      if (typeof window.showStatus === 'function') {
        window.showStatus(`提示词字符上限 ${MAX}，超出部分已自动截断`, 'warning');
      }
    }
    if (!finalPrompt) {
      if (typeof window.showStatus === 'function') window.showStatus('请输入画面提示词', 'error');
      return;
    }

    const originalHTML = imgBtn.innerHTML;
    imgBtn.disabled = true;
    imgBtn.style.opacity = '0.6';
    imgBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 生成中...';

    // 保存用户当前选择的模式状态：生成完成后在 finally 中恢复，确保 wan2.7-image 下
    // 自定义配色面板可见性与用户手选模式严格一致（防止生成过程中模式被意外切换）。
    const selectedModel = modelSelect.style.display === 'none' ? '' : modelSelect.value;
    const capsData = window._imageCapabilitiesCache;
    const curCap = capsData ? capsData.models[selectedModel] : null;
    const _prevSequential = sequentialCheckbox.checked;
    const _prevThinkingMode = thinkingModeCheckbox.checked;

    try {
      // 需求4：生成之前先把 image_prompt_refine task 持久化（单例覆写），便于下次进入章节回填
      try {
        await NovelAPI.upsertImagePrompt(sessionId, volIdx, chapIdx, finalPrompt);
      } catch (_ignore) {
        // 持久化失败不阻塞生成，只静默（用户无感）。
      }

      // wan2.7 特有参数：仅当该模型支持时才传递（selectedModel/capsData/curCap 已在 try 外部声明）
      const options = {
        user_prompt: finalPrompt,
        image_size: sizeSelect.value,
        negative_prompt: negInput.value.trim(),
        batch_size: Number(batchSelect.value),
        model: selectedModel,
      };
      let cpData = null;
      if (curCap) {
        if (curCap.supports_thinking_mode && !sequentialCheckbox.checked) {
          options.thinking_mode = !!thinkingModeCheckbox.checked;
        }
        if (curCap.supports_sequential) {
          options.enable_sequential = !!sequentialCheckbox.checked;
        }
        if (curCap.supports_color_palette && !sequentialCheckbox.checked) {
          // 收集可视化颜色面板数据，校验通过才透传（3-10色，占比总和100%）
          cpData = _collectColorPalette();
          if (cpData) {
            options.color_palette = JSON.stringify(cpData);
          }
        }
      }
      // 需求1：点击生成按钮时检查「最终要注入到模型侧的提示词内容」是否非空。
      // 这里 finalPrompt 是用户输入/优化结果；cpData 作为颜色风格注入，是额外拼接；
      // 组合后至少 finalPrompt 非空，才能允许调用模型（如果两个都为空直接拦截）。
      if (!finalPrompt && (!cpData || cpData.length === 0)) {
        if (typeof window.showStatus === 'function') window.showStatus('注入的提示词内容为空，请输入画面描述或设置自定义配色', 'error');
        return;
      }
      const data = await NovelAPI.generateImages(sessionId, volIdx, chapIdx, options);
      if (data && data.ok && Array.isArray(data.image_urls) && data.image_urls.length > 0) {
        _renderImgGallery(chapWrap, data.image_urls);
        // 生成图片成功后同步刷新本章节视频生成卡片下方基础设置的图片选择器
        // （与恢复路径 L2641-2647 的刷新逻辑保持一致，避免用户必须刷新/切页才看到新图）
        setTimeout(() => {
          try {
            const fn = (typeof window._refreshVideoImageOptionsMap === 'object' && window._refreshVideoImageOptionsMap)
              ? window._refreshVideoImageOptionsMap[`${volIdx}_${chapIdx}`] : null;
            if (typeof fn === 'function') fn();
          } catch (_err) { /* 选择器刷新失败不影响图片生成结果 */ }
        }, 120);
        if (typeof window.showStatus === 'function') window.showStatus(`图片生成完成（${data.image_urls.length} 张）`, 'success');
      } else {
        if (typeof window.showStatus === 'function') window.showStatus('图片生成失败，请重试', 'error');
      }
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || String(err);
      if (typeof window.showStatus === 'function') window.showStatus(`图片生成失败：${msg}`, 'error');
    } finally {
      imgBtn.disabled = false;
      imgBtn.style.opacity = '';
      imgBtn.innerHTML = originalHTML;
      // 恢复用户选择的模式状态（防御性：避免生成过程中模式被意外切换导致 cpPanel 状态错乱）
      if (curCap) {
        sequentialCheckbox.checked = _prevSequential;
        thinkingModeCheckbox.checked = _prevThinkingMode;
        _applyModelCap(curCap, true);
      }
    }
  }
  imgBtn.addEventListener('click', async () => {
    if (imgBtn.disabled) return;
    if (_hasExistingImages()) {
      // 已有图片：弹确认框提示覆盖风险
      if (typeof window.showConfirm === 'function') {
        window.showConfirm({
          title: '确认覆盖图片',
          message: '当前章节已存在生成的图片，再次生成将覆盖原有图片，是否确认继续？',
          confirmText: '确认生成',
          cancelText: '取消',
          onConfirm: () => _doGenerateImages(),
        });
      } else {
        _doGenerateImages();
      }
    } else {
      _doGenerateImages();
    }
  });

  // 需求4：进入章节时异步回填 image_prompt_refine task 中上次保存的提示词（经并发限制器节流）
  (async () => {
    try {
      const sessionId = window.currentWorkId || (window._currentSessionId ? String(window._currentSessionId) : '');
      if (!sessionId) return;
      const saved = await _contEnqueueRequest(() => NovelAPI.fetchImagePrompt(sessionId, volIdx, chapIdx));
      if (saved && typeof saved.content_text === 'string' && saved.content_text.trim()) {
        const MAX = _getImagePromptMaxChars();
        let v = saved.content_text;
        if (v.length > MAX) v = v.slice(0, MAX);
        promptTextarea.value = v;
        _updatePromptCount();
      }
    } catch (_ignore) {
      // 回填失败不阻塞 UI
    }
  })();

  // 异步恢复已生成的音频（持久化显示，经并发限制器节流）
  (async () => {
    try {
      const sessionId = window.currentWorkId || (window._currentSessionId ? String(window._currentSessionId) : '');
      if (!sessionId) return;
      const data = await _contEnqueueRequest(() => NovelAPI.getTtsAudioByChapter(sessionId, volIdx, chapIdx));
      if (data && data.ok && data.audio_url) {
        _renderAudioPlayer(chapWrap, data.audio_url, volIdx, chapIdx);
      }
    } catch (_e) {
      // 静默失败
    }
  })();

  // 异步恢复已生成的图片（持久化显示，经并发限制器节流）
  (async () => {
    try {
      const sessionId = window.currentWorkId || (window._currentSessionId ? String(window._currentSessionId) : '');
      if (!sessionId) return;
      const data = await _contEnqueueRequest(() => NovelAPI.getImagesByChapter(sessionId, volIdx, chapIdx, 'generated'));
      if (data && data.ok && Array.isArray(data.images) && data.images.length > 0) {
        // 后端已按 image_type=generated + 章节隔离过滤，前端无需再 filter
        const urls = data.images.map(img => img.url);
        _renderImgGallery(chapWrap, urls);
        // 图片恢复完后再刷新视频卡片的图片选择器和铅笔画 apply_to
        setTimeout(() => {
          try {
            const fn = (typeof window._refreshVideoImageOptionsMap === 'object' && window._refreshVideoImageOptionsMap)
              ? window._refreshVideoImageOptionsMap[`${volIdx}_${chapIdx}`] : null;
            if (typeof fn === 'function') fn();
          } catch (_err) {}
        }, 100);
      }
    } catch (_e) {
      // 静默失败
    }
  })();

  // 异步恢复已生成的视频（持久化显示，经并发限制器节流）
  (async () => {
    try {
      const sessionId = window.currentWorkId || (window._currentSessionId ? String(window._currentSessionId) : '');
      if (!sessionId) return;
      const data = await _contEnqueueRequest(() => NovelAPI.getVideoByChapter(sessionId, volIdx, chapIdx));
      if (data && data.ok && data.video_url) {
        _renderVideoPlayer(chapWrap, data.video_url);
      }
    } catch (_e) {
      // 静默失败
    }
  })();
}

function _renderAudioPlayer(cardElement, audioUrl, volIdx, chapIdx) {
  // 查找对应的播放器容器（已内嵌在音频卡片内）
  const container = cardElement.querySelector('.audio-player-container');
  if (!container) return;
  container.innerHTML = '';
  // 标题（简洁，不重复展示「音频生成」图标和标题）
  const hint = document.createElement('div');
  hint.style.cssText = 'font-size: 13px; color: #6d28d9; margin-bottom: 8px; font-weight: 500;';
  hint.textContent = '音频已生成，点击播放按钮开始收听';
  container.appendChild(hint);
  // 音频播放器
  const audio = document.createElement('audio');
  audio.src = audioUrl;
  audio.controls = true;
  audio.style.cssText = 'width: 100%;';
  container.appendChild(audio);
  // 显示容器（保留原 padding，不再重复增加边框和背景：外层卡片已负责）
  container.style.display = 'block';
}

function _renderImgGallery(cardElement, imageUrls) {
  const container = cardElement.querySelector('.img-gallery-container');
  if (!container) return;
  container.innerHTML = '';
  container.style.display = 'grid';

  // 默认一行三列：1张占首列（左对齐），2张占前两列，3张占满；不居中、不限制单卡宽度，避免过度设计
  container.style.gridTemplateColumns = 'repeat(3, 1fr)';
  container.style.justifyItems = 'stretch';

  // 统一卡片高度（与图像原始宽高比解耦）：竖图横图均裁剪展示，点击查看原图
  const CARD_HEIGHT = 200;

  imageUrls.forEach(url => {
    const imgWrapper = document.createElement('div');
    imgWrapper.style.cssText = [
      'border-radius: 8px',
      'overflow: hidden',
      'box-shadow: 0 2px 8px rgba(124,58,237,0.15)',
      'background: #f3f4f6',
      'position: relative',
      'cursor: pointer',
      `height: ${CARD_HEIGHT}px`,
      'width: 100%',
    ].join(';');

    const img = document.createElement('img');
    img.src = url;
    img.alt = '生成图片';
    img.loading = 'lazy';
    // 关键：width/height 双 100% + object-fit:cover，无论原图竖横均在固定高度容器内裁剪展示
    img.style.cssText = 'width:100%;height:100%;display:block;object-fit:cover;transition:transform .3s;';
    img.addEventListener('click', () => {
      window.open(url, '_blank');
    });
    img.addEventListener('error', () => {
      img.style.opacity = '0.3';
      imgWrapper.title = '图片加载失败';
    });
    // 鼠标悬停轻微放大，提示可点击查看原图
    imgWrapper.addEventListener('mouseenter', () => { img.style.transform = 'scale(1.04)'; });
    imgWrapper.addEventListener('mouseleave', () => { img.style.transform = 'scale(1)'; });

    imgWrapper.appendChild(img);
    container.appendChild(imgWrapper);
  });
}

function _renderVideoPlayer(cardElement, videoUrl) {
  // 查找对应的播放器容器（已内嵌在视频卡片内）
  const container = cardElement.querySelector('.video-player-container');
  if (!container) return;
  container.innerHTML = '';
  // 提示标题
  const hint = document.createElement('div');
  hint.style.cssText = 'font-size: 13px; color: #6d28d9; margin-bottom: 8px; font-weight: 500;';
  hint.textContent = '视频已生成，点击播放按钮开始观看';
  container.appendChild(hint);
  // 视频播放器
  const video = document.createElement('video');
  video.src = videoUrl;
  video.controls = true;
  video.preload = 'metadata';
  video.style.cssText = [
    'width: 100%',
    'height: auto',
    'max-height: 540px',
    'border-radius: 8px',
    'background: #000',
    'box-shadow: 0 2px 12px rgba(107,114,128,0.18)',
    'display: block',
  ].join(';');
  container.appendChild(video);
  // 显示容器
  container.style.display = 'block';
}

function renderContentChapters() {
  (function _contRaiseZ() {
    try {
      const ids = ['contentArea', 'contentResult', 'contentChapterCards'];
      for (let i = 0; i < ids.length; i++) {
        const el = document.getElementById(ids[i]);
        if (!el) continue;
        const cur = el.getAttribute('style') || '';
        const cleaned = String(cur).replace(/position\s*:\s*[^;]*;?/gi, '').replace(/z-index\s*:\s*[^;]*;?/gi, '');
        el.setAttribute('style', (cleaned + '; position: relative; z-index: ' + (998 + i) + ';').replace(/;;/g, ';'));
      }
    } catch (_e) {}
  })();

  const cardsEl = document.getElementById('contentChapterCards');
  const resultBox = document.getElementById('contentResult');
  if (!cardsEl) return;
  cardsEl.innerHTML = '';

  const volEvents = (window._volumePlotResult && Array.isArray(window._volumePlotResult.volumes))
    ? window._volumePlotResult.volumes
    : [];
  const chapterVols = (window._chapterPlotResult && Array.isArray(window._chapterPlotResult.volumes))
    ? window._chapterPlotResult.volumes
    : [];

  if (!Array.isArray(volEvents) || volEvents.length === 0) {
    if (resultBox) resultBox.style.display = 'block';
    const empty = document.createElement('div');
    empty.style.cssText = [
      'padding: 28px 20px',
      'border: 1px dashed rgba(139, 92, 246, 0.35)',
      'border-radius: 12px', 'text-align: center',
      'font-size: 17px', 'color: #5b21b6',
      'background: rgba(139, 92, 246, 0.04)',
    ].join(';');
    empty.innerHTML = '暂无分卷卷纲。请先在「分卷」页面生成卷纲，再在「定章」页面生成章纲，「推演」页面生成事件链后，进入本成文页面。';
    cardsEl.appendChild(empty);
    return;
  }
  if (resultBox) resultBox.style.display = 'block';

  // 首次渲染：预填充所有卷 + 规范化默认折叠状态（懒展开：仅第 0 卷 + 第 0 章展开）
  _contApplyInitFold(volEvents);

  let anyChapter = false;
  for (let volIdx = 0; volIdx < volEvents.length; volIdx++) {
    const volMeta = volEvents[volIdx] || {};
    const volSummaryRaw = typeof volMeta.summary === 'string' ? volMeta.summary.trim() : '';
    const chapArrSrc = (chapterVols[volIdx] && Array.isArray(chapterVols[volIdx].chapters))
      ? chapterVols[volIdx].chapters
      : [];
    if (!Array.isArray(chapArrSrc) || chapArrSrc.length === 0) continue;
    anyChapter = true;
    const volState = _contEnsureVolume(volIdx);
    const collapsed = !!volState.collapsed;

    const volWrap = document.createElement('div');
    volWrap.className = 'content-volume-wrap';
    volWrap.setAttribute('data-vol-idx', String(volIdx));
    volWrap.style.cssText = [
      'border: 1px solid #f0e8f8',
      'border-radius: 10px',
      'background: rgba(255, 255, 255, 0.85)',
      'overflow: hidden',
      'transition: box-shadow 0.25s ease, border-color 0.25s ease',
      'margin-bottom: 18px',
    ].join(';');
    volWrap.addEventListener('mouseenter', () => {
      volWrap.style.boxShadow = '0 6px 18px rgba(162, 28, 175, 0.07)';
      volWrap.style.borderColor = 'rgba(168, 85, 247, 0.22)';
    });
    volWrap.addEventListener('mouseleave', () => {
      volWrap.style.boxShadow = '';
      volWrap.style.borderColor = '#f0e8f8';
    });

    const vHeader = document.createElement('div');
    vHeader.style.cssText = [
      'display: flex', 'align-items: center', 'justify-content: space-between',
      'gap: 16px',
      'padding: ' + (collapsed ? '13px 20px' : '16px 20px'),
      'background: ' + (collapsed
        ? 'linear-gradient(90deg, rgba(139, 92, 246, 0.08), rgba(168, 85, 247, 0.02))'
        : 'linear-gradient(90deg, rgba(139, 92, 246, 0.1), rgba(168, 85, 247, 0.03))'),
      'cursor: pointer',
      'font-weight: 600', 'color: #444', 'user-select: none',
      'transition: background 0.3s ease, padding 0.25s ease',
    ].join(';');
    vHeader.onclick = () => toggleContentVolume(volIdx);
    const vLeft = document.createElement('div');
    vLeft.style.cssText = [
      'display: inline-flex', 'align-items: center', 'gap: 12px',
      'min-width: 0', 'flex: 1',
    ].join(';');
    const vIconWrap = document.createElement('div');
    vIconWrap.style.cssText = [
      'display: inline-flex', 'align-items: center', 'justify-content: center',
      'width: 22px', 'height: 22px', 'border-radius: 50%',
      'background: rgba(139, 92, 246, 0.1)',
      'flex-shrink: 0',
      'transition: background 0.25s ease, transform 0.25s ease',
    ].join(';');
    const vIcon = document.createElement('i');
    vIcon.className = 'content-toggle-icon fas ' + (collapsed ? 'fa-chevron-down' : 'fa-chevron-up');
    vIcon.style.cssText = 'font-size: 11px; color: #5b21b6;';
    vIconWrap.appendChild(vIcon);
    vLeft.appendChild(vIconWrap);

    const vBadge = document.createElement('div');
    vBadge.style.cssText = [
      'display: inline-flex', 'align-items: center', 'justify-content: center',
      'min-width: 52px', 'height: 28px', 'padding: 0 14px',
      'border-radius: 999px',
      'background: linear-gradient(135deg, #db2777, #8b5cf6)',
      'color: #fff', 'font-size: 16px', 'font-weight: 700',
      'flex-shrink: 0',
      'box-shadow: 0 2px 8px rgba(219, 39, 119, 0.22)',
    ].join(';');
    vBadge.textContent = `第 ${volIdx + 1} 卷`;
    vLeft.appendChild(vBadge);

    if (volSummaryRaw) {
      const vs = document.createElement('div');
      vs.style.cssText = [
        'font-size: 17px', 'font-weight: 500', 'color: #555',
        'min-width: 0', 'flex: 1',
        'white-space: nowrap', 'overflow: hidden', 'text-overflow: ellipsis',
        'padding-left: 4px', 'padding-right: 12px', 'max-width: 420px',
      ].join(';');
      vs.title = volSummaryRaw;
      vs.textContent = volSummaryRaw;
      vLeft.appendChild(vs);
    }
    vHeader.appendChild(vLeft);

    const vRight = document.createElement('div');
    vRight.style.cssText = 'display: inline-flex; align-items: center; gap: 10px; flex-shrink: 0;';
    vRight.onclick = (ev) => { if (ev) ev.stopPropagation && ev.stopPropagation(); };
    const vTip = document.createElement('span');
    vTip.className = 'content-volume-save-tip';
    vTip.setAttribute('data-vol-idx', String(volIdx));
    vTip.innerText = '已自动保存';
    vTip.style.cssText = [
      'font-size: 12px', 'color: #5b21b6', 'opacity: 0',
      'transition: opacity 0.3s', 'white-space: nowrap',
      'pointer-events: none',
    ].join(';');
    vRight.appendChild(vTip);
    vHeader.appendChild(vRight);
    volWrap.appendChild(vHeader);

    const vBody = document.createElement('div');
    vBody.className = 'content-volume-body';
    vBody.style.cssText = [
      'padding: 0 18px 18px',
      'border-top: 1px solid #ede9fe',
      'background: rgba(255, 255, 255, 0.85)',
      'display: ' + (collapsed ? 'none' : 'block'),
      'box-sizing: border-box',
    ].join(';');
    const metaLine = document.createElement('div');
    metaLine.style.cssText = [
      'padding: 14px 0 12px',
      'font-size: 17px', 'color: #5b21b6',
      'display: inline-flex', 'align-items: center', 'gap: 8px',
      'opacity: 0.85',
    ].join(';');
    metaLine.innerHTML = `<i class="fas fa-info-circle"></i><span>本卷共 ${chapArrSrc.length} 章，以下卡片每张对应一章：章纲+事件链只读 + 正文可编辑。`;
    vBody.appendChild(metaLine);

    const chapContainer = document.createElement('div');
    chapContainer.className = 'content-chapters-container';
    chapContainer.setAttribute('data-chapters-populated', collapsed ? '0' : '1');
    chapContainer.setAttribute('data-chapter-count', String(chapArrSrc.length));
    chapContainer.style.cssText = [
      'display: flex', 'flex-direction: column',
      'gap: 0',
    ].join(';');
    // 卷层懒渲染：折叠卷不创建章卡 DOM，展开卷才创建，避免数百章 DOM 爆炸
    if (!collapsed) {
      for (let ci = 0; ci < chapArrSrc.length; ci++) {
        _renderContentCard(volIdx, ci, chapContainer);
      }
    }
    vBody.appendChild(chapContainer);
    volWrap.appendChild(vBody);
    cardsEl.appendChild(volWrap);
  }

  if (!anyChapter) {
    const empty = document.createElement('div');
    empty.style.cssText = [
      'padding: 28px 20px',
      'border: 1px dashed rgba(139, 92, 246, 0.35)',
      'border-radius: 12px', 'text-align: center',
      'font-size: 17px', 'color: #5b21b6',
      'background: rgba(139, 92, 246, 0.04)',
    ].join(';');
    empty.innerHTML = '尚无章纲剧情。请先在「定章」页面生成或手动填写章纲，再在「推演」页面生成事件链后，进入成文页面。';
    cardsEl.appendChild(empty);
  }
}

async function _contLoadAllHistoryTasks() {
  if (!window.currentWorkId) return;
  try {
    const rows = await NovelAPI.listTasks(
      window.currentWorkId,
      NovelAPI.CONST.TASK_TYPE_CHAPTER_CONTENT,
      'id',
      true,
    );
    if (!Array.isArray(rows) || rows.length === 0) return;
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i];
      if (!r) continue;
      const vi = (r.volume_index !== null && r.volume_index !== undefined) ? Number(r.volume_index) : -1;
      const ci = (r.chapter_index !== null && r.chapter_index !== undefined) ? Number(r.chapter_index) : -1;
      if (!Number.isInteger(vi) || !Number.isInteger(ci) || vi < 0 || ci < 0) continue;
      const content = _contTryParseContentRow(r);
      const ch = _contEnsureChapter(vi, ci);
      if (content && !ch.content) {
        ch.content = content;
      }
      if (r && (r.id || r.id === 0) && !ch.activeTaskId) {
        ch.activeTaskId = String(r.id);
      }
    }
  } catch (_e) {
    console.warn('[content-init] _contLoadAllHistoryTasks failed:', _e?.message || _e);
  }
}

function refreshContentStepActions() {
  const has = _contHasAnyContentData();
  const nextBtn = document.getElementById('nextStepBtnContent');
  if (nextBtn) {
    if (has) nextBtn.classList.add('show');
    else nextBtn.classList.remove('show');
  }
  // 同步侧边栏成文节点图标：有正文内容时切换为完成态，避免永远是播放图标造成流程视觉断裂
  _contSyncContentStepIcon(has);
}

// 同步侧边栏成文节点（第 7 步，索引 6）的图标与状态：
// 有任意章节正文内容 → step-completed + fa-check（绿色完成态）
// 无正文内容         → step-active + fa-play（紫色播放态，默认）
// 节点未解锁（step-locked）时不操作，避免误改锁定态。
function _contSyncContentStepIcon(hasContent) {
  const workId = window.currentWorkId;
  if (!workId) return;
  const workItem = document.getElementById(workId);
  if (!workItem) return;
  const steps = workItem.querySelectorAll('.step-item');
  const contentStep = steps[6];
  if (!contentStep) return;
  if (contentStep.classList.contains('step-locked')) return;
  const statusEl = contentStep.querySelector('.step-status');
  if (!statusEl) return;
  if (hasContent) {
    contentStep.classList.remove('step-active');
    contentStep.classList.add('step-completed');
    statusEl.innerHTML = '<i class="fas fa-check"></i>';
  } else {
    contentStep.classList.remove('step-completed');
    contentStep.classList.add('step-active');
    statusEl.innerHTML = '<i class="fas fa-play"></i>';
  }
}

function handleContentNextStep() {
  if (!window.currentWorkId) {
    if (typeof showStatus === 'function') showStatus('请先在左侧选择一个作品', 'error');
    return;
  }
  const has = _contHasAnyContentData();
  if (!has) {
    if (typeof showStatus === 'function') showStatus('请先点击任意章的「生成正文」或手动输入正文内容，至少为一章生成正文后再进入后续环节', 'error');
    const firstGen = document.querySelector('[id^="generateContentBtn_"]');
    if (firstGen && typeof firstGen.scrollIntoView === 'function') {
      firstGen.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    return;
  }
  if (typeof showStatus === 'function') showStatus('成文环节完成！作品已包含完整的章节正文内容，正在打包完整创作数据下载...', 'success');

  const btn = document.getElementById('nextStepBtnContent');
  const oriHTML = btn ? btn.innerHTML : null;
  const restoreBtn = () => {
    if (!btn || !oriHTML) return;
    btn.disabled = false;
    btn.innerHTML = oriHTML;
  };
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>打包下载中…</span>';
  }
  (async () => {
    try {
      const { blob, suggestedName } = await NovelAPI.exportWork(window.currentWorkId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = suggestedName;
      a.rel = 'noopener';
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        try { URL.revokeObjectURL(url); } catch (_e) {}
        try { if (a.parentNode) a.parentNode.removeChild(a); } catch (_e) {}
      }, 2000);
      if (typeof showStatus === 'function') {
        showStatus(`下载已启动：${suggestedName}，请在浏览器默认下载目录中查看。`, 'success');
      }
    } catch (err) {
      const msg = err?.message || String(err || '导出失败');
      console.warn('[content-export] 作品导出失败:', msg);
      if (typeof showStatus === 'function') {
        showStatus('完整创作包下载失败：' + msg, 'error');
      }
    } finally {
      restoreBtn();
    }
  })();
}

/**
 * 内联卷纲行解析（不依赖 novel-volume.js）
 */
function _contParseVolumeRow(row) {
  let obj = null;
  try { obj = (row && typeof row.content_text === 'string') ? JSON.parse(row.content_text) : null; } catch (_) {}
  if (!obj) return [];
  let arr = [];
  if (Array.isArray(obj.volumes)) {
    arr = obj.volumes;
  } else if (Array.isArray(obj.events)) {
    arr = obj.events.map(function(e) {
      return { plot: e && typeof e.plot === 'string' ? e.plot : (e && typeof e.event === 'string' ? e.event : ''), summary: e && typeof e.summary === 'string' ? e.summary : '' };
    });
  } else if (typeof obj.plot === 'string' || typeof obj.summary === 'string') {
    arr = [{ plot: obj.plot || '', summary: obj.summary || '' }];
  } else if (obj.volume_plot_design) {
    const inner = obj.volume_plot_design;
    if (typeof inner.plot === 'string' || typeof inner.summary === 'string') arr = [{ plot: inner.plot || '', summary: inner.summary || '' }];
  } else if (obj.result && obj.result.volume_plot_design) {
    const inner = obj.result.volume_plot_design;
    if (typeof inner.plot === 'string' || typeof inner.summary === 'string') arr = [{ plot: inner.plot || '', summary: inner.summary || '' }];
  }
  return arr.filter(function(v) { return v && (typeof v.plot === 'string' || typeof v.summary === 'string') && (v.plot || v.summary); });
}

/**
 * 内联章纲行解析（不依赖 novel-chapter.js）
 */
function _contParseChapterRow(row) {
  let obj = null;
  try { obj = (row && typeof row.content_text === 'string') ? JSON.parse(row.content_text) : null; } catch (_) {}
  if (!obj) return null;
  let plot = '', summary = '';
  if (typeof obj.plot === 'string') plot = obj.plot;
  else if (obj.chapter_plot_design && typeof obj.chapter_plot_design.plot === 'string') plot = obj.chapter_plot_design.plot;
  else if (obj.result && obj.result.chapter_plot_design && typeof obj.result.chapter_plot_design.plot === 'string') plot = obj.result.chapter_plot_design.plot;
  if (typeof obj.summary === 'string') summary = obj.summary;
  else if (obj.chapter_plot_design && typeof obj.chapter_plot_design.summary === 'string') summary = obj.chapter_plot_design.summary;
  else if (obj.result && obj.result.chapter_plot_design && typeof obj.result.chapter_plot_design.summary === 'string') summary = obj.result.chapter_plot_design.summary;
  if (!plot && !summary) return null;
  return { plot: plot || '', summary: summary || '' };
}

function initContentPage() {
  // 【作品级隔离 SOP】切作品进入成文节点时，先清空所有作品级单例/DOM，再拉数据/渲染
  resetContentPageIsolatedState();
  (async () => {
    // fallback：成文页依赖上游卷纲/章纲/事件链缓存，切作品后可能为空，需自行拉取
    await _contEnsureUpstreamLoaded();
    try {
      await _contLoadAllHistoryTasks();
    } catch (_e) {}
    renderContentChapters();
    refreshContentStepActions();
  })();
}

/**
 * 确保上游卷纲、章纲、事件链缓存已加载。
 * 切作品后 _resetAllWorkCaches 会清空全部缓存，若用户直接进入成文页（未经分卷/定章/推演），
 * 需从此处 fallback 拉取，否则 renderContentChapters 读到空数组 → 页面空白。
 */
async function _contEnsureUpstreamLoaded() {
  if (!window.currentWorkId) return;

  // 1) 卷纲 fallback
  const volCache = window._volumePlotResult;
  if (!volCache || !Array.isArray(volCache.volumes) || volCache.volumes.length === 0) {
    try {
      const rows = await NovelAPI.listTasks(
        window.currentWorkId,
        NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE,
        'sequence',
        false,
      );
      if (Array.isArray(rows) && rows.length > 0) {
        const dedupMap = {};
        for (let i = 0; i < rows.length; i++) {
          const parsed = _contParseVolumeRow(rows[i]);
          if (Array.isArray(parsed) && parsed.length > 0) {
            const volIdx = rows[i].volume_index ?? rows[i].sort_order ?? i;
            const numericIdx = typeof volIdx === 'number' ? volIdx : Number(volIdx) || 0;
            const rowId = Number(rows[i].id) || 0;
            const existing = dedupMap[numericIdx];
            if (!existing || rowId > existing.rowId) {
              dedupMap[numericIdx] = { rowId, parsed: parsed[0] };
            }
          }
        }
        const allVols = [];
        const sortedKeys = Object.keys(dedupMap).sort((a, b) => Number(a) - Number(b));
        for (const k of sortedKeys) {
          allVols.push(dedupMap[k].parsed);
        }
        if (allVols.length > 0) {
          if (!window._volumePlotResult) window._volumePlotResult = {};
          window._volumePlotResult.volumes = allVols;
        }
      }
    } catch (_e) {
      console.warn('[content-init] fallback fetch volume tasks failed:', _e?.message || _e);
    }
  }

  // 2) 章纲 fallback —— 写入 _chapterPlotResult 缓存（成文页 render 从此缓存读章纲只读区）
  const chapCache = window._chapterPlotResult;
  if (!chapCache || !Array.isArray(chapCache.volumes) || chapCache.volumes.length === 0) {
    try {
      // 排序：id 降序，保证同一章的最新任务先被处理，内容优先填入空位置
      const rows = await NovelAPI.listTasks(
        window.currentWorkId,
        NovelAPI.CONST.TASK_TYPE_CHAPTER_OUTLINE,
        'id',
        true,
      );
      if (Array.isArray(rows) && rows.length > 0) {
        if (!window._chapterPlotResult) window._chapterPlotResult = { volumes: [] };
        if (!Array.isArray(window._chapterPlotResult.volumes)) window._chapterPlotResult.volumes = [];
        for (let i = 0; i < rows.length; i++) {
          const r = rows[i];
          if (!r) continue;
          const vi = (r.volume_index !== null && r.volume_index !== undefined) ? Number(r.volume_index) : -1;
          const ci = (r.chapter_index !== null && r.chapter_index !== undefined) ? Number(r.chapter_index) : -1;
          if (!Number.isInteger(vi) || !Number.isInteger(ci) || vi < 0 || ci < 0) continue;
          const parsed = _contParseChapterRow(r);
          if (parsed && (parsed.plot || parsed.summary)) {
            // 直接操作 _chapterPlotResult（禁止调用 _contEnsureVolume 这种操作另一缓存的函数）
            while (window._chapterPlotResult.volumes.length <= vi) {
              window._chapterPlotResult.volumes.push({ chapters: [], collapsed: false });
            }
            const chapVol = window._chapterPlotResult.volumes[vi];
            if (!Array.isArray(chapVol.chapters)) chapVol.chapters = [];
            // 空位填充空对象，保证数组索引与 chapter_index 严格对齐
            while (chapVol.chapters.length <= ci) {
              chapVol.chapters.push({ plot: '', summary: '', collapsed: false });
            }
            const ch = chapVol.chapters[ci] || {};
            const hasExisting = (typeof ch.plot === 'string' && ch.plot.trim())
              || (typeof ch.summary === 'string' && ch.summary.trim());
            // 仅在该位置无内容时才覆写，避免覆盖已有更优数据
            if (!hasExisting) {
              if (parsed.plot) ch.plot = parsed.plot;
              if (parsed.summary) ch.summary = parsed.summary;
              chapVol.chapters[ci] = ch;
            }
            // 记录 activeTaskId 到该章对象（与定章/推演页对齐）
            const id = (r.id || r.id === 0) ? String(r.id) : '';
            if (id && !chapVol.chapters[ci].activeTaskId) {
              chapVol.chapters[ci].activeTaskId = id;
            }
          }
        }
      }
    } catch (_e) {
      console.warn('[content-init] fallback fetch chapter tasks failed:', _e?.message || _e);
    }
  }

  // 3) 事件链 fallback（推演结果）
  const dedCache = window._deductionResult;
  if (!dedCache || !Array.isArray(dedCache.volumes) || dedCache.volumes.length === 0) {
    try {
      // 排序：id 降序，保证同一章最新任务先处理
      const rows = await NovelAPI.listTasks(
        window.currentWorkId,
        NovelAPI.CONST.TASK_TYPE_CHAPTER_EVENTS,
        'id',
        true,
      );
      if (Array.isArray(rows) && rows.length > 0) {
        for (let i = 0; i < rows.length; i++) {
          const r = rows[i];
          if (!r) continue;
          const vi = (r.volume_index !== null && r.volume_index !== undefined) ? Number(r.volume_index) : -1;
          const ci = (r.chapter_index !== null && r.chapter_index !== undefined) ? Number(r.chapter_index) : -1;
          if (!Number.isInteger(vi) || !Number.isInteger(ci) || vi < 0 || ci < 0) continue;
          // 解析事件链内容
          let events = [];
          try {
            const obj = JSON.parse(r.content_text);
            if (Array.isArray(obj.events)) {
              events = obj.events.filter(e => typeof e === 'string' && e.trim()).map(e => e.trim());
            } else if (obj && obj.chapter_events_design && Array.isArray(obj.chapter_events_design.events)) {
              events = obj.chapter_events_design.events.filter(e => typeof e === 'string' && e.trim()).map(e => e.trim());
            }
          } catch (_) {}
          if (!window._deductionResult) window._deductionResult = { volumes: [] };
          if (!Array.isArray(window._deductionResult.volumes)) window._deductionResult.volumes = [];
          // 空位填充，保证索引与卷章号严格对齐
          while (window._deductionResult.volumes.length <= vi) {
            window._deductionResult.volumes.push({ chapters: [], collapsed: false });
          }
          const dedVol = window._deductionResult.volumes[vi];
          if (!Array.isArray(dedVol.chapters)) dedVol.chapters = [];
          while (dedVol.chapters.length <= ci) {
            dedVol.chapters.push({ events: [], collapsed: false });
          }
          const dedCh = dedVol.chapters[ci];
          const existingEvents = Array.isArray(dedCh.events)
            ? dedCh.events.filter(s => typeof s === 'string' && s.trim())
            : [];
          // 仅当当前位置无事件数据且新解析有数据时才写入
          if (existingEvents.length === 0 && events.length > 0) {
            dedCh.events = events.slice();
          }
          // 记录 activeTaskId 到该章对象
          const id = (r.id || r.id === 0) ? String(r.id) : '';
          if (id && !dedCh.activeTaskId) {
            dedCh.activeTaskId = id;
          }
        }
      }
    } catch (_e) {
      console.warn('[content-init] fallback fetch deduction tasks failed:', _e?.message || _e);
    }
  }
}

window.resetContentPageIsolatedState = resetContentPageIsolatedState;
window.initContentPage = initContentPage;
window.renderContentChapters = renderContentChapters;
window.refreshContentStepActions = refreshContentStepActions;
window.handleContentNextStep = handleContentNextStep;