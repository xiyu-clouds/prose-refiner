/* ========================================================================
 * 推演节点：章节事件设计
 *   - 数据源：从「定章」window._chapterPlotResult.volumes[volIdx].events[chapIdx] 同步只读的章纲剧情（event/summary）
 *   - 调用 chapter_events_design 能力 → 基于每章章纲生成该章的精炼事件链（字符串数组）
 *   - 每章一张卡片，含：章纲只读区 + 生成按钮 + 折叠效果 + 事件链可编辑 + 失焦自动保存
 *   - scope 约定（与 Rust/Python SSOT 完全对齐）：task_type = 'chapter_events_design'，parent_id = chapter_plot_design.id，sort_order = chapter_index(0-based)；volume_index 通过 parent 链反查：chapter_events.parent_id → chapter_outline.parent_id → volume_outline.sort_order
 * ====================================================================== */

/**
 * 推演节点作品级隔离重置：切换作品/重入本节点前调用。
 * 清空推演结果缓存、折叠标记、自动保存定时器、字数告警与 DOM 残留。
 */
function resetDeductionPageIsolatedState() {
  // 1) 跨作品内存缓存：仅清空本节点（推演）的事件链结果 + 折叠规范化标记
  //   ——严禁顺手清空上游 _chapterPlotResult / _volumePlotResult / _globalPlotResult，
  //     推演卡片只读章纲、后续成文只读回退全部直接复用上游缓存。
  window._deductionResult = { volumes: [] };
  try { delete window._dedFoldNormalized; } catch (_) { window._dedFoldNormalized = undefined; }

  // 2) 模块级去抖：自动保存定时器、事件字数告警
  for (const k of Object.keys(_dedSaveTimers)) {
    const t = _dedSaveTimers[k];
    if (t) clearTimeout(t);
  }
  _dedSaveTimers = {};
  _dedEventAlerted = {};

  // 3) DOM 残留：推演章卷卡片容器清空
  const cardsEl = document.getElementById('deductionChapterCards');
  if (cardsEl) cardsEl.innerHTML = '';
}

if (!window._deductionResult) {
  window._deductionResult = { volumes: [] };
}

/* ============== 工具函数 ============== */
function _dedEnsureVolume(volIdx) {
  if (!window._deductionResult) window._deductionResult = { volumes: [] };
  if (!Array.isArray(window._deductionResult.volumes)) window._deductionResult.volumes = [];
  while (window._deductionResult.volumes.length <= volIdx) {
    window._deductionResult.volumes.push({
      collapsed: false,
      chapters: [],
    });
  }
  return window._deductionResult.volumes[volIdx];
}

function _dedEnsureChapter(volIdx, chapIdx) {
  const vol = _dedEnsureVolume(volIdx);
  if (!Array.isArray(vol.chapters)) vol.chapters = [];
  while (vol.chapters.length <= chapIdx) {
    vol.chapters.push({
      activeTaskId: '',
      events: [],
      collapsed: false,
    });
  }
  return vol.chapters[chapIdx];
}

/* ============== 默认折叠规范化（懒展开：首屏仅最小必要单元展开） ============== */
/* 在 render 函数内部调用，确保 _dedEnsureVolume 已创建所有卷后再生效 */
function _dedApplyInitFold(volEvents) {
  if (window._dedFoldNormalized) return;
  window._dedFoldNormalized = true;
  if (!Array.isArray(volEvents) || !volEvents.length) return;
  for (let vi = 0; vi < volEvents.length; vi++) {
    const vs = _dedEnsureVolume(vi);
    vs.collapsed = (vi !== 0);
    const chs = Array.isArray(vs.chapters) ? vs.chapters : [];
    for (let ci = 0; ci < chs.length; ci++) {
      if (chs[ci] && typeof chs[ci] === 'object') {
        chs[ci].collapsed = !(vi === 0 && ci === 0);
      }
    }
  }
}

function _dedHasAnyEventData() {
  const vols = (window._deductionResult && Array.isArray(window._deductionResult.volumes))
    ? window._deductionResult.volumes
    : [];
  for (let i = 0; i < vols.length; i++) {
    const v = vols[i] || {};
    const chs = Array.isArray(v.chapters) ? v.chapters : [];
    for (let j = 0; j < chs.length; j++) {
      const c = chs[j] || {};
      const arr = Array.isArray(c.events) ? c.events.filter(s => typeof s === 'string' && s.trim()) : [];
      if (arr.length > 0) return true;
    }
  }
  return false;
}

/* ============== 解析 chapter_events 历史 task 行 ============== */
function _dedTryParseEventsRow(row) {
  let obj = null;
  try { obj = (row && typeof row.content_text === 'string') ? JSON.parse(row.content_text) : null; } catch(e) {}
  const arr = obj && Array.isArray(obj.events) ? obj.events : [];
  return arr.filter(s => typeof s === 'string' && s.trim());
}

/* ============== 构建 content_text JSON（与写入端对齐，单一真源） ============== */
function _dedBuildContentTextFromEvents(events, chapterPlotRef, chapterSummaryRef) {
  const arr = Array.isArray(events) ? events.filter(s => typeof s === 'string' && s.trim()) : [];
  const obj = { _v: 1, events: arr };
  const meta = {};
  const cp = typeof chapterPlotRef === 'string' ? chapterPlotRef.trim() : '';
  const cs = typeof chapterSummaryRef === 'string' ? chapterSummaryRef.trim() : '';
  if (cp) meta.chapter_plot_ref = cp.slice(0, 400);
  if (cs) meta.chapter_summary_ref = cs.slice(0, 400);
  if (Object.keys(meta).length > 0) obj._meta = meta;
  return JSON.stringify(obj);
}

/* ============== 自动保存（按卷+章隔离，防抖 500ms） ============== */
let _dedSaveTimers = {}; // key = `${volIdx}_${chapIdx}`

function _flashDeductionSaveTip(volIdx, chapIdx, success, customText) {
  const defaultText = success ? '已自动保存' : '保存失败，请稍后重试';
  const text = customText ? String(customText) : defaultText;
  const color = success ? '#5b21b6' : '#dc2626';
  const cardsEl = document.getElementById('deductionChapterCards');
  if (!cardsEl) return;
  const volWrap = cardsEl.querySelector(`.deduction-volume-wrap[data-vol-idx="${String(volIdx)}"]`);
  if (!volWrap) return;
  let tipEl = volWrap.querySelector(`.deduction-card-save-tip[data-vol-idx="${String(volIdx)}"][data-chap-idx="${String(chapIdx)}"]`);
  if (!tipEl) tipEl = volWrap.querySelector('.deduction-volume-save-tip');
  if (!tipEl) return;
  tipEl.innerText = text;
  tipEl.style.color = color;
  tipEl.style.opacity = '1';
  clearTimeout(tipEl._t);
  tipEl._t = setTimeout(() => { tipEl.style.opacity = '0'; }, 1600);
}

async function _dedFindActiveTaskId(volIdx, chapIdx) {
  if (!window.currentWorkId) return null;
  const ch = _dedEnsureChapter(volIdx, chapIdx);
  if (ch.activeTaskId) {
    const s = String(ch.activeTaskId).trim();
    if (s) return s;
  }
  try {
    const tid = await NovelAPI.findActiveTaskId(
      window.currentWorkId,
      NovelAPI.CONST.TASK_TYPE_CHAPTER_EVENTS,
      volIdx,
      chapIdx,
    );
    if (tid) {
      ch.activeTaskId = String(tid);
      return String(tid);
    }
    return null;
  } catch (_e) {
    console.warn('[deduction-save] _dedFindActiveTaskId failed vol=' + volIdx + ' chap=' + chapIdx + ':', _e?.message || _e);
    return null;
  }
}

async function doSaveDeductionEvents(volIdx, chapIdx, force) {
  if (!window.currentWorkId) return;
  const ch = _dedEnsureChapter(volIdx, chapIdx);
  const events = Array.isArray(ch.events) ? ch.events.slice() : [];
  const clean = events.filter(s => typeof s === 'string' && s.trim());
  // 仅当从未添加过任何事件（events 全空）且非强制保存时才跳过；
  // 否则即便 clean 为空（如删除最后一条事件后），也需将空列表持久化，防止刷新后旧数据复活
  if (events.length === 0 && !force) return;
  const chPlotSrc = (window._chapterPlotResult && Array.isArray(window._chapterPlotResult.volumes)
    && window._chapterPlotResult.volumes[volIdx] && Array.isArray(window._chapterPlotResult.volumes[volIdx].chapters)
    && window._chapterPlotResult.volumes[volIdx].chapters[chapIdx])
    ? window._chapterPlotResult.volumes[volIdx].chapters[chapIdx]
    : null;
  const chapterPlotRef = (chPlotSrc && typeof chPlotSrc.plot === 'string') ? chPlotSrc.plot : '';
  const chapterSummaryRef = (chPlotSrc && typeof chPlotSrc.summary === 'string') ? chPlotSrc.summary : '';
  const contentText = _dedBuildContentTextFromEvents(clean, chapterPlotRef, chapterSummaryRef);
  const wc = contentText.length;
  try {
    let taskId = await _dedFindActiveTaskId(volIdx, chapIdx);
    if (taskId) {
      const patch = {
        status: 'completed',
        title: `章节事件设计（第 ${Number(volIdx) + 1} 卷第 ${Number(chapIdx) + 1} 章，${clean.length} 条事件）`,
        content_text: contentText,
        word_count: Number(wc) || 0,
      };
      await NovelAPI.updateTask(String(taskId), patch);
    } else {
      let parentId = null;
      try {
        parentId = await NovelAPI.resolveChapterParentId(window.currentWorkId, volIdx, chapIdx);
      } catch (_e) {
        console.warn('[deduction-save] find parent failed vol=' + volIdx + ' chap=' + chapIdx + ':', _e?.message || _e);
      }
      const payload = {
        session_id: window.currentWorkId,
        task_type: NovelAPI.CONST.TASK_TYPE_CHAPTER_EVENTS,
        sequence: 0,
        parent_id: parentId,
        sort_order: Number(chapIdx),
        volume_index: Number(volIdx),
        chapter_index: Number(chapIdx),
        status: 'completed',
        title: `章节事件设计（第 ${Number(volIdx) + 1} 卷第 ${Number(chapIdx) + 1} 章，${clean.length} 条事件）`,
        content_text: contentText,
        word_count: Number(wc) || 0,
      };
      await NovelAPI.semanticUpsertTask(payload);
      const newId = await _dedFindActiveTaskId(volIdx, chapIdx);
      if (newId && !ch.activeTaskId) ch.activeTaskId = String(newId);
    }
    _flashDeductionSaveTip(volIdx, chapIdx, true, null);
  } catch (err) {
    console.warn('[deduction-save] auto save failed vol=' + volIdx + ' chap=' + chapIdx + ':', err?.message || err);
    _flashDeductionSaveTip(volIdx, chapIdx, false, null);
  }
}

function scheduleDeductionAutoSave(volIdx, chapIdx, immediate) {
  if (!window.currentWorkId) return;
  const key = `${String(volIdx)}_${String(chapIdx)}`;
  clearTimeout(_dedSaveTimers[key]);
  if (immediate) {
    doSaveDeductionEvents(volIdx, chapIdx, true);
    return;
  }
  _dedSaveTimers[key] = setTimeout(() => {
    doSaveDeductionEvents(volIdx, chapIdx, false);
  }, 500);
}

/* ============== 阈值 fallback + 告警记录（与定章/分卷完全对齐，SSOT 优先从 window.frontendThresholds 读） ============== */
const _DED_EVENT_MAX_CHARS = 200;
const _DED_EVENT_HARD_CHARS = 300;
let _dedEventAlerted = {};    // key = `${volIdx}_${chapIdx}_${evtIdx}`，是否已经弹过「超建议值」通知（避免每敲一个字都弹）

function _getThDed(key, fallbackValue) {
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

/* ============== 单事件计数刷新（与 _refreshChapterCardCount 逻辑一致） ============== */
function _refreshDeductionEventCount(volIdx, chapIdx, evtIdx) {
  const vi = Number(volIdx);
  const ci = Number(chapIdx);
  const ei = Number(evtIdx);
  if (!Number.isInteger(vi) || vi < 0 || !Number.isInteger(ci) || ci < 0 || !Number.isInteger(ei) || ei < 0) return;
  const cardsEl = document.getElementById('deductionChapterCards');
  if (!cardsEl) return;
  const volWrap = cardsEl.querySelector(`.deduction-volume-wrap[data-vol-idx="${String(vi)}"]`);
  if (!volWrap) return;
  const cardsContainer = volWrap.querySelector(':scope > .deduction-volume-body > div:last-child');
  if (!cardsContainer || !cardsContainer.children[ci]) return;
  const chapBody = cardsContainer.children[ci].querySelector(':scope > .deduction-card-body');
  if (!chapBody) return;
  const evList = chapBody.querySelector(':scope > .deduction-events-list');
  if (!evList || !evList.children[ei]) return;
  const evWrap = evList.children[ei];
  const ta = evWrap.querySelector('textarea');
  const countEl = evWrap.querySelector(`[data-deduction-count-event="${String(vi)}_${String(ci)}_${String(ei)}"]`);
  if (!ta || !countEl) return;
  const MAX = _getThDed('deduction_event_chars', _DED_EVENT_MAX_CHARS);
  const HARD = _getThDed('deduction_event_hard_chars', _DED_EVENT_HARD_CHARS);
  const k = `${String(vi)}_${String(ci)}_${String(ei)}`;
  const cur = (ta.value || '').length;
  countEl.textContent = `${cur} / ${MAX}`;
  countEl.classList.remove('char-counter--warn', 'char-counter--danger');
  if (cur > HARD) {
    countEl.classList.add('char-counter--danger');
  } else if (cur > MAX) {
    countEl.classList.add('char-counter--warn');
    if (!_dedEventAlerted[k]) {
      _dedEventAlerted[k] = true;
      try {
        if (typeof showStatus === 'function') {
          showStatus(`第 ${vi + 1} 卷第 ${ci + 1} 章事件 ${ei + 1} 当前 ${cur} 字，超过建议值 ${MAX} 字，精简下内容会更凝练；超过 ${HARD} 字将自动截断。`, 'warn');
        }
      } catch (_e) {}
    }
  }
}

/* ============== 单事件硬截断工具 ============== */
function _enforceDeductionHardMax(el, hardMax, label) {
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

/* ============== 卷折叠切换 ============== */
function toggleDeductionVolume(volIdx) {
  const vol = _dedEnsureVolume(volIdx);
  vol.collapsed = !vol.collapsed;
  const cardsEl = document.getElementById('deductionChapterCards');
  if (!cardsEl) return;
  const volWrap = cardsEl.querySelector(`.deduction-volume-wrap[data-vol-idx="${String(volIdx)}"]`);
  if (!volWrap) return;
  const body = volWrap.querySelector('.deduction-volume-body');
  const icon = volWrap.querySelector('.deduction-toggle-icon');
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
    const chapContainer = body.querySelector('.deduction-chapters-container');
    if (chapContainer && chapContainer.getAttribute('data-chapters-populated') !== '1') {
      const count = Number(chapContainer.getAttribute('data-chapter-count')) || 0;
      for (let ci = 0; ci < count; ci++) {
        _renderDeductionCard(volIdx, ci, chapContainer);
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

/* ============== 单章折叠切换 ============== */
function toggleDeductionCard(volIdx, chapIdx) {
  const ch = _dedEnsureChapter(volIdx, chapIdx);
  ch.collapsed = !ch.collapsed;
  const cardsEl = document.getElementById('deductionChapterCards');
  if (!cardsEl) return;
  const volWrap = cardsEl.querySelector(`.deduction-volume-wrap[data-vol-idx="${String(volIdx)}"]`);
  if (!volWrap) return;
  const cardsContainer = volWrap.querySelector(':scope > .deduction-volume-body > div:last-child');
  if (!cardsContainer || !cardsContainer.children[chapIdx]) return;
  const chapWrap = cardsContainer.children[chapIdx];
  const header = chapWrap.querySelector(':scope > .deduction-card-header');
  const body = chapWrap.querySelector(':scope > .deduction-card-body');
  const icon = chapWrap.querySelector('.deduction-card-toggle-icon');
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
    // 懒渲染：首次展开章卡时填充 body（章纲只读区 + 事件链列表）
    if (body.getAttribute('data-body-populated') !== '1') {
      _dedPopulateCardBody(chapWrap, body, volIdx, chapIdx);
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

/* ============== 添加 / 删除 单条事件 ============== */
function addDeductionEvent(volIdx, chapIdx) {
  const ch = _dedEnsureChapter(volIdx, chapIdx);
  if (!Array.isArray(ch.events)) ch.events = [];
  ch.events.push('');
  _dedRefreshChapterEvents(volIdx, chapIdx);
  refreshDeductionStepActions();
  scheduleDeductionAutoSave(volIdx, chapIdx, false);
}

function deleteDeductionEvent(volIdx, chapIdx, evtIdx) {
  const ch = _dedEnsureChapter(volIdx, chapIdx);
  if (!Array.isArray(ch.events)) return;
  const n = Number(evtIdx);
  if (!Number.isInteger(n) || n < 0 || n >= ch.events.length) return;
  const left = ch.events.slice(0, n);
  const right = ch.events.slice(n + 1);
  ch.events = left.concat(right);
  _dedRefreshChapterEvents(volIdx, chapIdx);
  refreshDeductionStepActions();
  // 强制保存：删除操作必须立即持久化，防止刷新后旧数据复活
  scheduleDeductionAutoSave(volIdx, chapIdx, true);
}

/* ============== 生成按钮：调 chapter_events_design 能力 ============== */
async function generateDeductionEvents(volIdx, chapIdx) {
  // 锁与 SSE 竞态由 NovelAPI.runCapabilityWithSSE 统一处理。
  const CAP_ID = NovelAPI.CONST.TASK_TYPE_CHAPTER_EVENTS;
  const lockKey = `events_${String(volIdx)}_${String(chapIdx)}`;

  if (!window.currentWorkId) {
    if (typeof showStatus === 'function') showStatus('请先在左侧选择一个作品', 'error');
    return;
  }
  const volState = _chapEnsureVolume ? _chapEnsureVolume(volIdx) : null;
  const volChapChapters = (volState && Array.isArray(volState.chapters)) ? volState.chapters : [];
  const chapMeta = volChapChapters[chapIdx] || {};
  const chapterPlot = typeof chapMeta.plot === 'string' ? chapMeta.plot.trim() : '';
  const chapterSummary = typeof chapMeta.summary === 'string' ? chapMeta.summary.trim() : '';
  if (!chapterPlot) {
    if (typeof showStatus === 'function') showStatus(`第 ${Number(volIdx) + 1} 卷第 ${Number(chapIdx) + 1} 章没有章纲剧情，请先在「定章」页面填写`, 'error');
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

  const ch = _dedEnsureChapter(volIdx, chapIdx);
  const existingEvents = Array.isArray(ch.events) ? ch.events.filter(s => typeof s === 'string' && s.trim()) : [];
  const hasExisting = existingEvents.length > 0;

  const doReal = async (finalVariables) => {
    const genBtn = document.getElementById(`generateDeductionBtn_${String(volIdx)}_${String(chapIdx)}`);
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
      if (typeof variables.volume_index === 'undefined' || variables.volume_index === null) {
        variables.volume_index = Number(volIdx);
      }
      if (typeof variables.chapter_index === 'undefined' || variables.chapter_index === null) {
        variables.chapter_index = Number(chapIdx);
      }
      const res = await NovelAPI.runCapabilityWithSSE({
        capabilityId: CAP_ID,
        variables: variables,
        lockKey: lockKey,
        volumeIndex: Number(volIdx),
        chapterIndex: Number(chapIdx),
      });

      if (res.conflict) {
        if (typeof showStatus === 'function') {
          showStatus(res.error?.message || '该章节事件链正在生成中，请稍候...', 'warning');
        }
        return;
      }
      if (!res.ok) {
        const errMsg = res.error?.message || String(res.error || '未知错误');
        console.warn('[deduction-generate] failed vol=' + volIdx + ' chap=' + chapIdx + ':', errMsg);
        if (typeof showStatus === 'function') showStatus('章节事件链生成失败：' + errMsg, 'error');
        return;
      }

      // needRefetch：HTTP 失败但 SSE 显示成功，从 task 表重新拉取
      if (res.needRefetch) {
        if (typeof showStatus === 'function') showStatus('任务已完成，正在加载事件链结果...', 'info');
        try {
          await _dedLoadAllHistoryTasks();
          renderDeductionChapters();
          refreshDeductionStepActions();
          const cur = _dedEnsureChapter(volIdx, chapIdx);
          const events = Array.isArray(cur.events) ? cur.events.filter(s => typeof s === 'string' && s.trim()) : [];
          if (events.length > 0) {
            if (typeof showStatus === 'function') {
              showStatus(`第 ${Number(volIdx) + 1} 卷第 ${Number(chapIdx) + 1} 章事件链生成完成（${events.length} 条）`, 'success');
            }
          } else {
            if (typeof showStatus === 'function') showStatus('任务已完成但结果为空，请刷新页面查看', 'warning');
          }
        } catch (e) {
          console.warn('[deduction-generate] refetch failed:', e?.message || e);
          if (typeof showStatus === 'function') showStatus('任务已完成，刷新页面查看结果', 'info');
        }
        return;
      }

      // HTTP 成功：从响应中提取事件链
      const payload = res.result;
      const r = payload && payload.result && payload.result.chapter_events_design ? payload.result.chapter_events_design : null;
      const arr = Array.isArray(r && r.events) ? r.events : [];
      const clean = arr.filter(s => typeof s === 'string' && s.trim()).map(s => s.trim());
      if (clean.length === 0) {
        if (typeof showStatus === 'function') showStatus('章节事件链返回为空，请重试或检查后端日志', 'error');
        return;
      }
      const cur = _dedEnsureChapter(volIdx, chapIdx);
      cur.events = clean.slice();
      _dedRefreshChapterEvents(volIdx, chapIdx);
      refreshDeductionStepActions();
      scheduleDeductionAutoSave(volIdx, chapIdx, true);
      if (typeof showStatus === 'function') showStatus(`第 ${Number(volIdx) + 1} 卷第 ${Number(chapIdx) + 1} 章事件链生成完成（${clean.length} 条）`, 'success');
    } catch (err) {
      console.warn('[deduction-generate] unexpected error vol=' + volIdx + ' chap=' + chapIdx + ':', err?.message || err);
      if (typeof showStatus === 'function') showStatus('章节事件链生成出现意外错误：' + (err?.message || String(err)), 'error');
    } finally {
      if (genBtn && genBtn.dataset.oriHtml) {
        genBtn.innerHTML = genBtn.dataset.oriHtml;
        genBtn.disabled = false;
        refreshDeductionStepActions();
      }
    }
  };

  if (window.startGenerateFlowWithPreview) {
    window.startGenerateFlowWithPreview({
      hasExisting: hasExisting,
      confirmConfig: hasExisting ? {
        title: '确认重新生成',
        message: `第 ${Number(volIdx) + 1} 卷第 ${Number(chapIdx) + 1} 章已有 ${existingEvents.length} 条事件链结果，重新生成会覆盖本章内容，是否继续？`,
        confirmText: '下一步',
        cancelText: '取消',
      } : null,
      previewConfig: {
        sessionId: window.currentWorkId,
        capabilityId: CAP_ID,
        rawVariables: {
          volume_plot_text: volumePlotText,
          chapter_plot_text: chapterPlot,
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

/* ============== 单张章卡片渲染 ============== */
function _renderDeductionCard(volIdx, chapIdx, cardsContainer) {
  const chapMeta = (window._chapterPlotResult && Array.isArray(window._chapterPlotResult.volumes)
    && window._chapterPlotResult.volumes[volIdx] && Array.isArray(window._chapterPlotResult.volumes[volIdx].chapters))
    ? window._chapterPlotResult.volumes[volIdx].chapters[chapIdx]
    : null;
  const chapterPlotRaw = (chapMeta && typeof chapMeta.plot === 'string') ? chapMeta.plot : '';
  const chapterSummaryRaw = (chapMeta && typeof chapMeta.summary === 'string') ? chapMeta.summary : '';
  const ch = _dedEnsureChapter(volIdx, chapIdx);
  const events = Array.isArray(ch.events) ? ch.events.slice() : [];
  const collapsed = !!ch.collapsed;

  const chapWrap = document.createElement('div');
  chapWrap.className = 'deduction-card-wrap';
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

  // ---- header ----
  const header = document.createElement('div');
  header.className = 'deduction-card-header';
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
  header.onclick = () => toggleDeductionCard(volIdx, chapIdx);

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
  toggleIcon.className = 'deduction-card-toggle-icon fas ' + (collapsed ? 'fa-chevron-down' : 'fa-chevron-up');
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
    return `章纲 ${(chapterPlotRaw || '').length} 字 / 事件链 ${events.filter(s => s && s.trim()).length} 条`;
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
  saveTip.className = 'deduction-card-save-tip';
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
  genBtn.id = `generateDeductionBtn_${String(volIdx)}_${String(chapIdx)}`;
  genBtn.onclick = (ev) => {
    if (ev) ev.stopPropagation && ev.stopPropagation();
    generateDeductionEvents(volIdx, chapIdx);
  };
  genBtn.innerHTML = '<i class="fas fa-magic"></i> <span>生成事件链</span>';
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
  header.appendChild(headerRight);
  chapWrap.appendChild(header);

  // 懒渲染：body 容器已创建，但不填充子节点；首次展开时调用 _dedPopulateCardBody
  const body = document.createElement('div');
  body.className = 'deduction-card-body';
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

  // 非折叠态：异步微任务里填充 body，避免卡主线程
  if (!collapsed) {
    requestAnimationFrame(() => _dedPopulateCardBody(chapWrap, body, volIdx, chapIdx));
  }
}

/**
 * 填充章卡 body 内容：章纲只读区 + 事件链列表。
 * 带幂等守卫：`data-body-populated === '1'` 时直接 return，避免重复构建。
 * 被 _renderDeductionCard（非折叠章）和 toggleDeductionCard（首次展开章）调用。
 */
function _dedPopulateCardBody(chapWrap, body, volIdx, chapIdx) {
  if (body.getAttribute('data-body-populated') === '1') return;
  const chapMeta = (window._chapterPlotResult && Array.isArray(window._chapterPlotResult.volumes)
    && window._chapterPlotResult.volumes[volIdx] && Array.isArray(window._chapterPlotResult.volumes[volIdx].chapters))
    ? window._chapterPlotResult.volumes[volIdx].chapters[chapIdx]
    : null;
  const chapterPlotRaw = (chapMeta && typeof chapMeta.plot === 'string') ? chapMeta.plot : '';
  const chapterSummaryRaw = (chapMeta && typeof chapMeta.summary === 'string') ? chapMeta.summary : '';
  const ch = _dedEnsureChapter(volIdx, chapIdx);
  const events = Array.isArray(ch.events) ? ch.events.slice() : [];
  body.setAttribute('data-body-populated', '1');

  // 章纲只读区
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

  // 事件链列表
  const listHead = document.createElement('div');
  listHead.style.cssText = [
    'display: flex', 'align-items: center', 'justify-content: space-between',
    'margin: 0 0 10px',
  ].join(';');
  const listHeadLeft = document.createElement('div');
  listHeadLeft.style.cssText = 'font-size: 16px; font-weight: 700; color: #4c1d95; display: inline-flex; align-items: center; gap: 6px;';
  const cleanCount = events.filter(s => typeof s === 'string' && s.trim()).length;
  listHeadLeft.innerHTML = `<i class="fas fa-list-ol" style="font-size: 11px;"></i><span>事件链（${cleanCount} 条，每条建议 200 字内）</span>`;
  const addBtn = document.createElement('button');
  addBtn.type = 'button';
  addBtn.innerHTML = '<i class="fas fa-plus"></i> <span>添加事件</span>';
  addBtn.style.cssText = [
    'display: inline-flex', 'align-items: center', 'gap: 6px',
    'padding: 7px 14px', 'border-radius: 6px',
    'border: 1px solid rgba(168, 85, 247, 0.3)',
    'background: rgba(168, 85, 247, 0.15)', 'color: #6d28d9', 'font-size: 16px',
    'font-weight: 600', 'cursor: pointer',
    'transition: background 0.15s, border-color 0.15s',
    'font-family: inherit', 'line-height: 1.2',
  ].join(';');
  addBtn.addEventListener('mouseenter', () => {
    addBtn.style.background = 'rgba(168, 85, 247, 0.25)';
    addBtn.style.borderColor = 'rgba(168, 85, 247, 0.4)';
  });
  addBtn.addEventListener('mouseleave', () => {
    addBtn.style.background = 'rgba(168, 85, 247, 0.15)';
    addBtn.style.borderColor = 'rgba(168, 85, 247, 0.3)';
  });
  addBtn.onclick = () => addDeductionEvent(volIdx, chapIdx);
  listHead.appendChild(listHeadLeft);
  listHead.appendChild(addBtn);
  body.appendChild(listHead);

  const evList = document.createElement('div');
  evList.className = 'deduction-events-list';
  evList.style.cssText = [
    'display: flex', 'flex-direction: column', 'gap: 10px',
  ].join(';');

  if (events.length === 0) {
    const empty = document.createElement('div');
    empty.style.cssText = [
      'padding: 14px 12px',
      'border: 1px dashed rgba(139, 92, 246, 0.35)',
      'border-radius: 8px', 'text-align: center',
      'font-size: 17px', 'color: #5b21b6',
      'background: rgba(139, 92, 246, 0.04)',
    ].join(';');
    empty.textContent = '暂无事件链，点击右上角「生成事件链」或「新增事件」按钮开始设计。';
    evList.appendChild(empty);
  }

  for (let ei = 0; ei < events.length; ei++) {
    const raw = typeof events[ei] === 'string' ? events[ei] : '';
    const evWrap = document.createElement('div');
    evWrap.style.cssText = [
      'border: 1px solid #ede9fe', 'border-radius: 8px',
      'background: rgba(255, 255, 255, 0.85)', 'padding: 10px 12px',
      'display: flex', 'align-items: flex-start', 'gap: 10px',
    ].join(';');

    const idxChip = document.createElement('div');
    idxChip.style.cssText = [
      'flex-shrink: 0', 'min-width: 26px', 'height: 26px',
      'border-radius: 50%',
      'background: linear-gradient(135deg, #a78bfa, #c4b5fd)',
      'color: #fff', 'font-size: 16px', 'font-weight: 700',
      'display: inline-flex', 'align-items: center', 'justify-content: center',
      'margin-top: 8px',
    ].join(';');
    idxChip.textContent = String(ei + 1);
    evWrap.appendChild(idxChip);

    const inner = document.createElement('div');
    inner.style.cssText = 'flex: 1; min-width: 0; position: relative;';
    const ta = document.createElement('textarea');
    ta.rows = 3;
    ta.placeholder = '事件描述：何时何地 → 谁 → 想做什么？ → 为什么？→ 如何做？→ 阻力 → 结局如何？（建议 200 字内）';
    ta.value = raw;
    ta.style.cssText = [
      'width: 100%', 'min-height: 88px', 'height: auto',
      'padding: 10px 12px', 'border-radius: 8px',
      'border: 1px solid #ede9fe',
      'background: rgba(255, 255, 255, 0.85)', 'font-size: 17px',
      'line-height: 1.7', 'color: #333',
      'box-sizing: border-box', 'white-space: pre-wrap',
      'word-break: break-word', 'resize: vertical',
      'outline: none',
      'transition: border-color 0.15s, box-shadow 0.15s',
      'font-family: inherit',
    ].join(';');
    const adjustHeight = () => {
      ta.style.height = 'auto';
      ta.style.height = Math.max(ta.scrollHeight, 88) + 'px';
    };
    adjustHeight();
    const evCount = document.createElement('div');
    evCount.className = 'char-counter char-counter--inside';
    evCount.setAttribute('data-deduction-count-event', String(volIdx) + '_' + String(chapIdx) + '_' + String(ei));
    const MAX = _getThDed('deduction_event_chars', _DED_EVENT_MAX_CHARS);
    evCount.textContent = `${(raw || '').length} / ${MAX}`;
    const HARD = _getThDed('deduction_event_hard_chars', _DED_EVENT_HARD_CHARS);
    const applyLimit = () => {
      const changed = _enforceDeductionHardMax(ta, HARD, `第 ${Number(volIdx) + 1} 卷第 ${Number(chapIdx) + 1} 章事件 ${ei + 1}`);
      if (changed) {
        const cur = _dedEnsureChapter(volIdx, chapIdx);
        if (!Array.isArray(cur.events)) cur.events = [];
        while (cur.events.length <= ei) cur.events.push('');
        cur.events[ei] = typeof ta.value === 'string' ? ta.value : '';
      }
      _refreshDeductionEventCount(volIdx, chapIdx, ei);
      return changed;
    };
    ta.addEventListener('focus', () => {
      ta.style.borderColor = '#c4b5fd';
      ta.style.boxShadow = '0 0 0 3px rgba(139, 92, 246, 0.12)';
    });
    ta.addEventListener('blur', () => {
      ta.style.borderColor = '#ede9fe';
      ta.style.boxShadow = 'none';
      applyLimit();
      scheduleDeductionAutoSave(volIdx, chapIdx, true);
    });
    ta.addEventListener('input', () => {
      applyLimit();
      adjustHeight();
      const cur = _dedEnsureChapter(volIdx, chapIdx);
      if (!Array.isArray(cur.events)) cur.events = [];
      while (cur.events.length <= ei) cur.events.push('');
      cur.events[ei] = typeof ta.value === 'string' ? ta.value : '';
      scheduleDeductionAutoSave(volIdx, chapIdx, false);
    });
    ta.addEventListener('paste', () => { setTimeout(() => { applyLimit(); adjustHeight(); }, 0); });
    inner.appendChild(ta);
    inner.appendChild(evCount);
    evWrap.appendChild(inner);

    const delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.setAttribute('aria-label', '删除本条事件');
    delBtn.innerHTML = '<i class="fas fa-trash-alt"></i>';
    delBtn.title = `删除第 ${ei + 1} 条事件`;
    delBtn.style.cssText = [
      'width: 28px', 'height: 28px', 'border: none', 'cursor: pointer',
      'background: none', 'color: #999', 'border-radius: 6px',
      'display: inline-flex', 'align-items: center', 'justify-content: center',
      'font-size: 12px', 'padding: 6px', 'flex-shrink: 0',
      'transition: background 0.2s ease, color 0.2s ease, transform 0.12s ease',
      'margin-top: 6px',
    ].join(';');
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
      if (window.showConfirm) {
        window.showConfirm({
          title: '确认删除',
          message: `确定删除第 ${Number(volIdx) + 1} 卷第 ${Number(chapIdx) + 1} 章的第 ${ei + 1} 条事件吗？此操作不可恢复。`,
          confirmText: '删除',
          cancelText: '取消',
          onConfirm: () => deleteDeductionEvent(volIdx, chapIdx, ei),
        });
      } else {
        deleteDeductionEvent(volIdx, chapIdx, ei);
      }
    });
    evWrap.appendChild(delBtn);
    evList.appendChild(evWrap);

    try { applyLimit(); } catch (_e) {}
  }

  body.appendChild(evList);
}

/**
 * 增量更新单章事件链列表：若 body 已填充则重建 body 内容，否则跳过（内存模型已更新，展开时自动填充）。
 * 被 generateDeductionEvents / addDeductionEvent / deleteDeductionEvent 调用，替代全量 renderDeductionChapters。
 */
function _dedRefreshChapterEvents(volIdx, chapIdx) {
  const cardsEl = document.getElementById('deductionChapterCards');
  if (!cardsEl) return;
  const volWrap = cardsEl.querySelector(`.deduction-volume-wrap[data-vol-idx="${String(volIdx)}"]`);
  if (!volWrap) return;
  const chapContainer = volWrap.querySelector(':scope > .deduction-volume-body > .deduction-chapters-container');
  if (!chapContainer) return;
  const chapWrap = chapContainer.children[chapIdx];
  if (!chapWrap) return;
  const body = chapWrap.querySelector(':scope > .deduction-card-body');
  if (!body) return;
  if (body.getAttribute('data-body-populated') !== '1') return;
  // body 已填充：重置标志并重建 body 内容（章纲只读区 + 事件链列表）
  body.setAttribute('data-body-populated', '0');
  body.innerHTML = '';
  _dedPopulateCardBody(chapWrap, body, volIdx, chapIdx);
}

/* ============== 主渲染：按卷分组展示所有章 ============== */
function renderDeductionChapters() {
  (function _dedRaiseZ() {
    try {
      const ids = ['deductionArea', 'deductionResult', 'deductionChapterCards'];
      for (let i = 0; i < ids.length; i++) {
        const el = document.getElementById(ids[i]);
        if (!el) continue;
        const cur = el.getAttribute('style') || '';
        const cleaned = String(cur).replace(/position\s*:\s*[^;]*;?/gi, '').replace(/z-index\s*:\s*[^;]*;?/gi, '');
        el.setAttribute('style', (cleaned + '; position: relative; z-index: ' + (998 + i) + ';').replace(/;;/g, ';'));
      }
    } catch (_e) {}
  })();

  const cardsEl = document.getElementById('deductionChapterCards');
  const resultBox = document.getElementById('deductionResult');
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
    empty.innerHTML = '暂无分卷卷纲。请先在「分卷」页面生成并保存卷纲剧情，再在「定章」页面生成章纲后，进入本推演页面。';
    cardsEl.appendChild(empty);
    return;
  }
  if (resultBox) resultBox.style.display = 'block';

  // 首次渲染：预填充所有卷 + 规范化默认折叠状态（懒展开：仅第 0 卷 + 第 0 章展开）
  _dedApplyInitFold(volEvents);

  let anyChapter = false;
  for (let volIdx = 0; volIdx < volEvents.length; volIdx++) {
    const volMeta = volEvents[volIdx] || {};
    const volSummaryRaw = typeof volMeta.summary === 'string' ? volMeta.summary.trim() : '';
    const chapArrSrc = (chapterVols[volIdx] && Array.isArray(chapterVols[volIdx].chapters))
      ? chapterVols[volIdx].chapters
      : [];
    if (!Array.isArray(chapArrSrc) || chapArrSrc.length === 0) continue;
    anyChapter = true;
    const volState = _dedEnsureVolume(volIdx);
    const collapsed = !!volState.collapsed;

    const volWrap = document.createElement('div');
    volWrap.className = 'deduction-volume-wrap';
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
    vHeader.onclick = () => toggleDeductionVolume(volIdx);
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
    vIcon.className = 'deduction-toggle-icon fas ' + (collapsed ? 'fa-chevron-down' : 'fa-chevron-up');
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
    vTip.className = 'deduction-volume-save-tip';
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

    // volume body
    const vBody = document.createElement('div');
    vBody.className = 'deduction-volume-body';
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
    metaLine.innerHTML = `<i class="fas fa-info-circle"></i><span>本卷共 ${chapArrSrc.length} 章，以下卡片每张对应一章：章纲只读 + 事件链可编辑。`;
    vBody.appendChild(metaLine);

    const chapContainer = document.createElement('div');
    chapContainer.className = 'deduction-chapters-container';
    chapContainer.setAttribute('data-chapters-populated', collapsed ? '0' : '1');
    chapContainer.setAttribute('data-chapter-count', String(chapArrSrc.length));
    chapContainer.style.cssText = [
      'display: flex', 'flex-direction: column',
      'gap: 0',
    ].join(';');
    // 卷层懒渲染：折叠卷不创建章卡 DOM，展开卷才创建，避免数百章 DOM 爆炸
    if (!collapsed) {
      for (let ci = 0; ci < chapArrSrc.length; ci++) {
        _renderDeductionCard(volIdx, ci, chapContainer);
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
    empty.innerHTML = '尚无章纲剧情。请先在「定章」页面生成或手动填写章纲，再进入推演页面生成事件链。';
    cardsEl.appendChild(empty);
  }
}

/* ============== 加载所有 chapter_events 历史 task 并归位 ============== */
async function _dedLoadAllHistoryTasks() {
  if (!window.currentWorkId) return;
  try {
    const rows = await NovelAPI.listTasks(
      window.currentWorkId,
      NovelAPI.CONST.TASK_TYPE_CHAPTER_EVENTS,
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
      const events = _dedTryParseEventsRow(r);
      const ch = _dedEnsureChapter(vi, ci);
      if (events.length > 0 && !(Array.isArray(ch.events) && ch.events.filter(s => s && s.trim()).length > 0)) {
        ch.events = events.slice();
      }
      if (r && (r.id || r.id === 0) && !ch.activeTaskId) {
        ch.activeTaskId = String(r.id);
      }
    }
  } catch (_e) {
    console.warn('[deduction-init] _dedLoadAllHistoryTasks failed:', _e?.message || _e);
  }
}

/* ============== 下一步按钮显隐控制 ============== */
function refreshDeductionStepActions() {
  const nextBtn = document.getElementById('nextStepBtnDeduction');
  if (!nextBtn) return;
  const has = _dedHasAnyEventData();
  if (has) nextBtn.classList.add('show');
  else nextBtn.classList.remove('show');
}

/* ============== 下一步：成文 ============== */
function handleDeductionNextStep() {
  if (!window.currentWorkId) {
    if (typeof showStatus === 'function') showStatus('请先在左侧选择一个作品', 'error');
    return;
  }
  const has = _dedHasAnyEventData();
  if (!has) {
    if (typeof showStatus === 'function') showStatus('请先点击任意章的「生成事件链」或手动添加事件，至少为一章生成事件链后再进入成文', 'error');
    const firstGen = document.querySelector('[id^="generateDeductionBtn_"]');
    if (firstGen && typeof firstGen.scrollIntoView === 'function') {
      firstGen.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    return;
  }
  if (typeof showStatus === 'function') showStatus('已完成推演环节，准备进入成文', 'success');
  if (window.completeStep) {
    completeStep(window.currentWorkId, 5);
  } else if (window.handleStepClick) {
    handleStepClick(window.currentWorkId, 6);
  }
}

/* ============== init ============== */
async function initDeductionPage() {
  // 【作品级隔离 SOP】切作品进入推演节点时，先清空所有作品级单例/DOM，再拉数据/渲染
  resetDeductionPageIsolatedState();
  refreshDeductionStepActions();
  if (!window.currentWorkId) {
    renderDeductionChapters();
    return;
  }

  // fallback：推演页依赖上游卷纲 _volumePlotResult 和章纲 _chapterPlotResult，
  // 若缓存为空（切作品后直接进入推演页，未经分卷/定章页），需自行从 API 拉取。
  await _dedEnsureUpstreamLoaded();

  await _dedLoadAllHistoryTasks();
  renderDeductionChapters();
  refreshDeductionStepActions();
}

/**
 * 内联卷纲行解析（不依赖 novel-volume.js）
 */
function _dedParseVolumeRow(row) {
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
function _dedParseChapterRow(row) {
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

/**
 * 确保上游卷纲和章纲缓存已加载。
 * 切作品后 _resetAllWorkCaches 会清空全部缓存，若用户直接进入推演页（未经分卷/定章），
 * 需从此处 fallback 拉取，否则 renderDeductionChapters 读到空数组 → 页面空白。
 */
async function _dedEnsureUpstreamLoaded() {
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
          const parsed = _dedParseVolumeRow(rows[i]);
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
      console.warn('[deduction-init] fallback fetch volume tasks failed:', _e?.message || _e);
    }
  }

  // 2) 章纲 fallback —— 写入 _chapterPlotResult 缓存（推演页 render 从此缓存读章纲只读区）
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
          const parsed = _dedParseChapterRow(r);
          if (parsed && (parsed.plot || parsed.summary)) {
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
            // 记录 activeTaskId 到该章对象（与定章页对齐）
            const id = (r.id || r.id === 0) ? String(r.id) : '';
            if (id && !chapVol.chapters[ci].activeTaskId) {
              chapVol.chapters[ci].activeTaskId = id;
            }
          }
        }
      }
    } catch (_e) {
      console.warn('[deduction-init] fallback fetch chapter tasks failed:', _e?.message || _e);
    }
  }
}

window.resetDeductionPageIsolatedState = resetDeductionPageIsolatedState;
window.initDeductionPage = initDeductionPage;
window.renderDeductionChapters = renderDeductionChapters;
window.refreshDeductionStepActions = refreshDeductionStepActions;
window.toggleDeductionVolume = toggleDeductionVolume;
window.toggleDeductionCard = toggleDeductionCard;
window.addDeductionEvent = addDeductionEvent;
window.deleteDeductionEvent = deleteDeductionEvent;
window.generateDeductionEvents = generateDeductionEvents;
window.handleDeductionNextStep = handleDeductionNextStep;
