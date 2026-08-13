/* ========================================================================
 * 定章节点：章纲剧情设计
 *   - 分卷卷纲从分卷结果自动同步（每卷卡片内只读显示）
 *   - 多卷独立：每卷独立维护 activeTaskId / events / collapsed 状态
 *   - 调用 chapter_plot_design 能力 → 生成该卷章纲事件链 → 卡片式展示
 *   - 每卷可折叠；每章可编辑失焦自动保存；每卷右上角 saveTip + 删除按钮
 * ====================================================================== */

/**
 * 定章节点作品级隔离重置：切换作品/重入本节点前调用。
 * 清空章节缓存、折叠标记、告警去抖、自动保存定时器与 DOM 残留。
 */
function resetChapterPageIsolatedState() {
  // 1) 跨作品内存缓存：仅清空本节点（定章）的章纲结果 + 折叠规范化标记
  //   ——严禁顺手清空上游 _volumePlotResult / _globalPlotResult，
  //     定章卡片只读卷纲剧情、后续推演/成文只读回退，全部直接复用上游缓存。
  window._chapterPlotResult = { volumes: [] };
  try { delete window._chapFoldNormalized; } catch (_) { window._chapFoldNormalized = undefined; }

  // 2) 模块级去抖：自动保存定时器、最近编辑章记忆、字数告警
  for (const k of Object.keys(_chapterSaveTimers)) {
    const t = _chapterSaveTimers[k];
    if (t) clearTimeout(t);
  }
  _chapterSaveTimers = {};
  _chapterLastEditedChap = {};
  _chapterPlotAlerted = {};
  _chapterSummaryAlerted = {};

  // 3) DOM 残留：章卷卡片容器清空
  const cardsEl = document.getElementById('chapterVolumeCards');
  if (cardsEl) cardsEl.innerHTML = '';
}

if (!window._chapterPlotResult) {
  window._chapterPlotResult = { volumes: [] };
}

/* ============== 工具函数 ============== */
function _chapEnsureVolume(volIdx) {
  if (!window._chapterPlotResult) window._chapterPlotResult = { volumes: [] };
  if (!Array.isArray(window._chapterPlotResult.volumes)) window._chapterPlotResult.volumes = [];
  while (window._chapterPlotResult.volumes.length <= volIdx) {
    window._chapterPlotResult.volumes.push({
      chapters: [],
      collapsed: false,
    });
  }
  return window._chapterPlotResult.volumes[volIdx];
}

/* ============== 默认折叠规范化（懒展开：首屏仅最小必要单元展开） ============== */
/* 在 render 函数内部调用，确保 _chapEnsureVolume 已创建所有卷后再生效 */
function _chapApplyInitFold(volumes) {
  if (window._chapFoldNormalized) return;
  window._chapFoldNormalized = true;
  if (!Array.isArray(volumes) || !volumes.length) return;
  for (let vi = 0; vi < volumes.length; vi++) {
    const vs = _chapEnsureVolume(vi);
    vs.collapsed = (vi !== 0);
    const chs = Array.isArray(vs.chapters) ? vs.chapters : [];
    for (let ci = 0; ci < chs.length; ci++) {
      if (chs[ci] && typeof chs[ci] === 'object') {
        chs[ci].collapsed = !(vi === 0 && ci === 0);
      }
    }
  }
}

function _chapHasAnyChapterData() {
  const vols = (window._chapterPlotResult && Array.isArray(window._chapterPlotResult.volumes))
    ? window._chapterPlotResult.volumes
    : [];
  for (let i = 0; i < vols.length; i++) {
    const v = vols[i] || {};
    const arr = Array.isArray(v.chapters) ? v.chapters : [];
    const clean = arr.filter(e => e && (typeof e.plot === 'string' || typeof e.summary === 'string'));
    if (clean.length > 0) return true;
  }
  return false;
}

/* ============== 解析章纲历史 task 行 ============== */
function _chapTryParseChapterRow(row) {
  let obj = null;
  try { obj = (row && typeof row.content_text === 'string') ? JSON.parse(row.content_text) : null; } catch(e) {}
  // 空 content_text 也视为占位空章（用户手动添加过章但未填写任何内容）
  if (!obj) return { plot: '', summary: '' };

  // 新格式（按章独立）: {"_v":2, "plot":"...", "summary":"..."}（plot/summary 可空=占位）
  // 或 LLM 直接返回: {"chapter_plot_design": {"plot":"...", "summary":"..."}}

  // 尝试从包装格式提取
  if (obj.chapter_plot_design && typeof obj.chapter_plot_design === 'object') {
    const inner = obj.chapter_plot_design;
    return {
      plot: typeof inner.plot === 'string' ? inner.plot : '',
      summary: typeof inner.summary === 'string' ? inner.summary : ''
    };
  }

  // 直接的 plot/summary（空值也合法：占位任务）
  if (typeof obj.plot === 'string' || typeof obj.summary === 'string'
      || Object.prototype.hasOwnProperty.call(obj, 'plot') || Object.prototype.hasOwnProperty.call(obj, 'summary')) {
    return {
      plot: typeof obj.plot === 'string' ? obj.plot : '',
      summary: typeof obj.summary === 'string' ? obj.summary : ''
    };
  }

  // 后端最终态兜底格式: {"_v":2, "chapters":[{"plot":"...", "summary":"..."}]}
  // 由 _finalize_chapter_plot_task_safely 写入；前端 createChapterOutline 未覆盖时命中
  // （如 HTTP 失败但后端 SSE 成功的 needRefetch 场景，需能从任务表重新加载）。
  if (Array.isArray(obj.chapters) && obj.chapters.length > 0) {
    const first = obj.chapters[0];
    if (first && typeof first === 'object') {
      return {
        plot: typeof first.plot === 'string' ? first.plot : '',
        summary: typeof first.summary === 'string' ? first.summary : ''
      };
    }
  }

  // 未识别格式：返回空占位，避免因解析失败导致"用户添加过章但切页面消失"
  return { plot: '', summary: '' };
}

/* ============== 构建单章 content_text JSON（按章独立模式） ============== */
function _chapBuildContentTextFromChapter(chapter, volumePlotRef, volumeSummaryRef) {
  const plot = (chapter && typeof chapter.plot === 'string') ? chapter.plot.trim() : '';
  const summary = (chapter && typeof chapter.summary === 'string') ? chapter.summary.trim() : '';

  const obj = { _v: 2, plot: plot, summary: summary };
  const meta = {};
  const vp = typeof volumePlotRef === 'string' ? volumePlotRef.trim() : '';
  const vs = typeof volumeSummaryRef === 'string' ? volumeSummaryRef.trim() : '';
  if (vp) meta.volume_plot_ref = vp.slice(0, 400);
  if (vs) meta.volume_summary_ref = vs.slice(0, 400);
  if (Object.keys(meta).length > 0) obj._meta = meta;
  return JSON.stringify(obj);
}

/* ============== 自动保存（按卷隔离，防抖 500ms） ============== */
let _chapterSaveTimers = {};
let _chapterLastEditedChap = {};

function _flashChapterSaveTip(volIdx, success, customText, chapIdx) {
  const defaultText = success ? '已自动保存' : '保存失败，请稍后重试';
  const text = customText ? String(customText) : defaultText;
  const color = success ? '#7c3aed' : '#dc2626';
  const volumeCardsEl = document.getElementById('chapterVolumeCards');
  if (!volumeCardsEl) return;
  const volWrap = volumeCardsEl.querySelector(`.chapter-volume-wrap[data-vol-idx="${String(volIdx)}"]`);
  if (!volWrap) return;
  let targetChapIdx = chapIdx;
  if (targetChapIdx == null || targetChapIdx === '') {
    const last = _chapterLastEditedChap[String(volIdx)];
    if (last != null && Number.isInteger(Number(last))) targetChapIdx = Number(last);
  }
  let tipEl = null;
  if (targetChapIdx != null && Number.isInteger(Number(targetChapIdx))) {
    const ci = String(targetChapIdx);
    tipEl = volWrap.querySelector(`.chapter-card-save-tip[data-vol-idx="${String(volIdx)}"][data-chap-idx="${ci}"]`);
  }
  if (!tipEl) tipEl = volWrap.querySelector('.chapter-volume-save-tip');
  if (!tipEl) return;
  tipEl.innerText = text;
  tipEl.style.color = color;
  tipEl.style.opacity = '1';
  clearTimeout(tipEl._t);
  tipEl._t = setTimeout(() => { tipEl.style.opacity = '0'; }, 1600);
}

async function _chapterFindActiveTaskId(volIdx) {
  if (!window.currentWorkId) return null;
  const vol = _chapEnsureVolume(volIdx);
  if (vol.activeTaskId) {
    const s = String(vol.activeTaskId).trim();
    if (s) return s;
  }
  try {
    const tid = await NovelAPI.findActiveTaskId(
      window.currentWorkId,
      NovelAPI.CONST.TASK_TYPE_CHAPTER_OUTLINE,
      volIdx,
      null,
    );
    if (tid) {
      vol.activeTaskId = String(tid);
      return String(tid);
    }
    return null;
  } catch (_e) {
    console.warn('[chapter-save] _chapterFindActiveTaskId failed vol=' + volIdx + ':', _e?.message || _e);
    return null;
  }
}

async function doSaveChapterOutline(volIdx, force, chapIdx) {
  if (!window.currentWorkId) return;
  // 按编辑章单点保存：chapIdx 无效则不执行（避免整卷 N+1 请求风暴）
  if (chapIdx == null || !Number.isInteger(Number(chapIdx)) || Number(chapIdx) < 0) return;
  const ci = Number(chapIdx);
  const vol = _chapEnsureVolume(volIdx);
  const chapters = Array.isArray(vol.chapters) ? vol.chapters : [];
  const chapter = chapters[ci];
  if (!chapter) return;
  // 空章（plot/summary trim 后都为空）不存入 DB：避免空数据污染任务表，
  // 与卷纲"空卷不存 DB"策略保持一致。
  const chapHasContent = (typeof chapter.plot === 'string' && chapter.plot.trim())
    || (typeof chapter.summary === 'string' && chapter.summary.trim());
  if (!chapHasContent) return;
  const volumePlotRef = (window._volumePlotResult && Array.isArray(window._volumePlotResult.volumes) && window._volumePlotResult.volumes[volIdx])
    ? (typeof window._volumePlotResult.volumes[volIdx].plot === 'string' ? window._volumePlotResult.volumes[volIdx].plot : '')
    : '';
  const volumeSummaryRef = (window._volumePlotResult && Array.isArray(window._volumePlotResult.volumes) && window._volumePlotResult.volumes[volIdx] && typeof window._volumePlotResult.volumes[volIdx].summary === 'string')
    ? window._volumePlotResult.volumes[volIdx].summary
    : '';

  try {
    const extra = {};
    if (volumePlotRef) extra.volume_plot = volumePlotRef;
    if (volumeSummaryRef) extra.volume_summary = volumeSummaryRef;

    // 仅保存被实际编辑的这一章
    const contentText = _chapBuildContentTextFromChapter(chapter, volumePlotRef, volumeSummaryRef);
    const wc = contentText ? contentText.length : 0;
    await NovelAPI.createChapterOutline(window.currentWorkId, volIdx, ci, [chapter], extra, contentText, wc);
    chapter.chapter_index = ci;

    _flashChapterSaveTip(volIdx, true, null, chapIdx);
  } catch (err) {
    console.warn('[chapter-save] auto save failed vol=' + volIdx + ' chap=' + ci + ':', err?.message || err);
    _flashChapterSaveTip(volIdx, false, null, chapIdx);
  }
}

/**
 * 整卷章纲保存（统一入口，与卷纲 doSaveVolumeOutline 对齐）。
 * 用于：generateChapterPlotDesign 生成后保存、deleteChapterCard 删除后重存。
 *
 * 核心策略：显示章号(i+1) = 数组下标(i) = DB chapter_index(i)，三者严格对齐。
 * - 若某章的 chapter_index（DB 原始位置）!== 当前数组下标 i（说明发生过中间删除导致前移），
 *   先级联删除旧位置的 DB 记录（含下属事件链/正文），再 upsert 到新位置 i；
 * - 空章（plot/summary trim 后都为空）不存入 DB，但若 oldCi !== i 也会执行清理旧记录。
 */
async function doSaveAllChapterOutlines(volIdx) {
  if (!window.currentWorkId) return;
  const vol = _chapEnsureVolume(volIdx);
  const chapters = Array.isArray(vol.chapters) ? vol.chapters : [];
  const sessionId = window.currentWorkId;

  const volumePlotRef = (window._volumePlotResult && Array.isArray(window._volumePlotResult.volumes) && window._volumePlotResult.volumes[volIdx])
    ? (typeof window._volumePlotResult.volumes[volIdx].plot === 'string' ? window._volumePlotResult.volumes[volIdx].plot : '')
    : '';
  const volumeSummaryRef = (window._volumePlotResult && Array.isArray(window._volumePlotResult.volumes) && window._volumePlotResult.volumes[volIdx] && typeof window._volumePlotResult.volumes[volIdx].summary === 'string')
    ? window._volumePlotResult.volumes[volIdx].summary
    : '';

  const extra = {};
  if (volumePlotRef) extra.volume_plot = volumePlotRef;
  if (volumeSummaryRef) extra.volume_summary = volumeSummaryRef;

  for (let i = 0; i < chapters.length; i++) {
    const chapter = chapters[i];
    if (!chapter || typeof chapter !== 'object') continue;

    const hasContent = (typeof chapter.plot === 'string' && chapter.plot.trim())
      || (typeof chapter.summary === 'string' && chapter.summary.trim());

    const oldCi = (typeof chapter.chapter_index === 'number' && Number.isFinite(chapter.chapter_index))
      ? chapter.chapter_index
      : null;
    const needReindex = (oldCi !== null) && (oldCi !== i);

    // 位置发生过迁移：先级联删除旧位置的 DB 记录（含下属事件链/正文）
    if (needReindex && sessionId) {
      try {
        const oldTaskId = await NovelAPI.findActiveTaskId(
          sessionId,
          NovelAPI.CONST.TASK_TYPE_CHAPTER_OUTLINE,
          volIdx,
          oldCi,
        );
        if (oldTaskId) {
          try { await NovelAPI.cascadeDelete(oldTaskId); } catch (_de) { /* ignore */ }
        }
      } catch (_fe) { /* ignore */ }
    }

    if (!hasContent) continue;

    const contentText = _chapBuildContentTextFromChapter(chapter, volumePlotRef, volumeSummaryRef);
    if (!contentText) continue;
    const wc = contentText.length;
    await NovelAPI.createChapterOutline(sessionId, volIdx, i, [chapter], extra, contentText, wc);
    chapter.chapter_index = i;
  }
}

function scheduleChapterAutoSave(volIdx, immediate, chapIdx) {
  if (!window.currentWorkId) return;
  const key = String(volIdx);
  if (chapIdx != null && Number.isInteger(Number(chapIdx))) {
    _chapterLastEditedChap[key] = Number(chapIdx);
  }
  clearTimeout(_chapterSaveTimers[key]);
  if (immediate) {
    doSaveChapterOutline(volIdx, true, chapIdx);
    return;
  }
  _chapterSaveTimers[key] = setTimeout(() => {
    doSaveChapterOutline(volIdx, false, chapIdx);
  }, 500);
}

/* ============== 阈值 fallback + 告警记录（与分卷/谋篇完全对齐，SSOT 优先从 window.frontendThresholds 读） ============== */
const _CHAPTER_PLOT_MAX_CHARS = 1500;
const _CHAPTER_PLOT_HARD_CHARS = 2000;
const _CHAPTER_SUMMARY_MAX_CHARS = 200;
const _CHAPTER_SUMMARY_HARD_CHARS = 300;
let _chapterPlotAlerted = {};    // key = `${volIdx}_${chapIdx}`，是否已经弹过本章剧情「超建议值」通知（避免每敲一个字都弹）
let _chapterSummaryAlerted = {}; // key = `${volIdx}_${chapIdx}`，是否已经弹过本章摘要「超建议值」通知（避免每敲一个字都弹）

function _getThCh(key, fallbackValue) {
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

/* ============== 定章单卡片计数刷新（与分卷 _refreshVolumeCardCounts 逻辑一致，按卷+章定位） ============== */
function _refreshChapterCardCount(volIdx, chapIdx) {
  const vi = Number(volIdx);
  const ci = Number(chapIdx);
  if (!Number.isInteger(vi) || vi < 0 || !Number.isInteger(ci) || ci < 0) return;
  const volumeCardsEl = document.getElementById('chapterVolumeCards');
  if (!volumeCardsEl) return;
  const volWrap = volumeCardsEl.querySelector(`.chapter-volume-wrap[data-vol-idx="${String(vi)}"]`);
  if (!volWrap) return;
  const cardsContainer = volWrap.querySelector('.chapter-volume-body > div:last-child');
  const chapCard = cardsContainer ? cardsContainer.children[ci] : null;
  if (!chapCard) return;
  const allTa = chapCard.querySelectorAll('textarea');
  const evTa = allTa[0] || null;
  const suTa = allTa[1] || null;
  const plotCountEl = chapCard.querySelector(`[data-chapter-count-plot="${String(vi)}_${String(ci)}"]`);
  const sumCountEl = chapCard.querySelector(`[data-chapter-count-summary="${String(vi)}_${String(ci)}"]`);
  const PLOT_MAX = _getThCh('chapter_plot_chars', _CHAPTER_PLOT_MAX_CHARS);
  const SUM_MAX = _getThCh('chapter_summary_chars', _CHAPTER_SUMMARY_MAX_CHARS);
  const PLOT_HARD = _getThCh('chapter_plot_hard_chars', _CHAPTER_PLOT_HARD_CHARS);
  const SUM_HARD = _getThCh('chapter_summary_hard_chars', _CHAPTER_SUMMARY_HARD_CHARS);
  const k = `${String(vi)}_${String(ci)}`;
  const setCounter = (el, cur, max, hard, label, alertMap) => {
    if (!el) return;
    el.textContent = `${cur} / ${hard}`;
    el.classList.remove('char-counter--warn', 'char-counter--danger');
    if (cur > hard) {
      el.classList.add('char-counter--danger');
    } else if (cur > max) {
      el.classList.add('char-counter--warn');
      if (!alertMap[k]) {
        alertMap[k] = true;
        try {
          if (typeof showStatus === 'function') {
            showStatus(`${label}当前 ${cur} 字，超过建议值 ${max} 字，精简下内容会更凝练；超过 ${hard} 字将自动截断。`, 'warn');
          }
        } catch (_e) {}
      }
    }
  };
  const pLen = evTa ? (evTa.value || '').length : 0;
  const sLen = suTa ? (suTa.value || '').length : 0;
  setCounter(plotCountEl, pLen, PLOT_MAX, PLOT_HARD, `第 ${vi + 1} 卷第 ${ci + 1} 章剧情`, _chapterPlotAlerted);
  setCounter(sumCountEl, sLen, SUM_MAX, SUM_HARD, `第 ${vi + 1} 卷第 ${ci + 1} 章摘要`, _chapterSummaryAlerted);
}

/* ============== 定章单卡片硬截断工具（与分卷 _enforceVolumeHardMax 逻辑一致） ============== */
function _enforceChapterHardMax(el, hardMax, label) {
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

/* ============== 折叠切换（自然呼吸感动画：max-height + opacity + translateY） ============== */
function toggleChapterVolume(volIdx) {
  const vol = _chapEnsureVolume(volIdx);
  vol.collapsed = !vol.collapsed;
  const volumeCardsEl = document.getElementById('chapterVolumeCards');
  if (!volumeCardsEl) return;
  const volWrap = volumeCardsEl.querySelector(`.chapter-volume-wrap[data-vol-idx="${String(volIdx)}"]`);
  if (!volWrap) return;
  const body = volWrap.querySelector('.chapter-volume-body');
  const icon = volWrap.querySelector('.chapter-toggle-icon');
  if (!body) return;
  if (vol.collapsed) {
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
    body.style.display = 'block';
    // 卷层懒渲染：首次展开卷时补建章卡（折叠卷未创建 DOM）
    const cardsContainer = volWrap.querySelector('.chapter-cards-container');
    if (cardsContainer && cardsContainer.getAttribute('data-chapters-populated') !== '1') {
      const count = Number(cardsContainer.getAttribute('data-chapter-count')) || 0;
      const volState = _chapEnsureVolume(volIdx);
      const chapArr = Array.isArray(volState.chapters) ? volState.chapters : [];
      // 先清掉可能残留的空状态提示，再按内存模型补建章卡
      cardsContainer.innerHTML = '';
      for (let ci = 0; ci < count; ci++) {
        _renderChapterCard(cardsContainer, volIdx, chapArr[ci] || {}, ci);
      }
      cardsContainer.setAttribute('data-chapters-populated', '1');
    }
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

/* ============== 添加 / 删除 单章 ============== */
function addChapterCard(volIdx) {
  const vol = _chapEnsureVolume(volIdx);
  if (!Array.isArray(vol.chapters)) vol.chapters = [];
  vol.chapters.push({ plot: '', summary: '' });
  // 增量更新：只追加新章卡 DOM，不全量重渲
  const newChapIdx = vol.chapters.length - 1;
  _chapSyncVolumeCards(volIdx, newChapIdx);
  refreshChapterStepActions();
  scheduleChapterAutoSave(volIdx, false, newChapIdx);
}

function deleteChapterCard(volIdx, chapIdx) {
  const vol = _chapEnsureVolume(volIdx);
  if (!Array.isArray(vol.chapters)) return;
  const n = Number(chapIdx);
  if (!Number.isInteger(n) || n < 0 || n >= vol.chapters.length) return;

  const sessionId = window.currentWorkId;
  if (!sessionId || typeof NovelAPI === 'undefined' || !NovelAPI.findTaskBySortOrder) {
    showStatus('删除功能暂不可用，请刷新页面后重试', 'error');
    return;
  }

  // 必须按 global → volume → chapter 的正确 parent_id 链逐级查找，
  // 避免重复记录时 findTaskBySortOrder 找到错误（非本子树）的任务 → 级联删错数据。
  NovelAPI.fetchLatestCompletedTask(sessionId, NovelAPI.CONST.TASK_TYPE_GLOBAL_OUTLINE).then(globalTask => {
    const globalParentId = globalTask ? globalTask.id : null;
    return NovelAPI.findTaskBySortOrder(sessionId, NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE, volIdx, globalParentId);
  }).then(volumeTask => {
    if (!volumeTask || !volumeTask.id) {
      // 兜底：不传 parentId 再查一次（兼容老数据 parent_id 为空的情况）
      return NovelAPI.findTaskBySortOrder(sessionId, NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE, volIdx);
    }
    return volumeTask;
  }).then(volumeTask => {
    if (!volumeTask || !volumeTask.id) {
      showStatus('未找到该卷的任务记录，无法删除', 'error');
      return null;
    }
    return NovelAPI.findTaskBySortOrder(sessionId, NovelAPI.CONST.TASK_TYPE_CHAPTER_OUTLINE, n, volumeTask.id);
  }).then(chapterTask => {
    if (!chapterTask || !chapterTask.id) {
      showStatus('未找到该章的任务记录，无法删除', 'error');
      return null;
    }
    return NovelAPI.cascadeDelete(chapterTask.id);
  }).then(async function(res) {
    if (res === null) return;
    if (res && res.ok) {
      showStatus(`第 ${volIdx + 1} 卷第 ${n + 1} 章及其下属数据已删除，正在同步剩余章号...`, 'success');
      // 1. 从内存中移除该章（数组下标前移，剩余章的下标变成新的正确位置）
      const left = vol.chapters.slice(0, n);
      const right = vol.chapters.slice(n + 1);
      vol.chapters = left.concat(right);
      _chapSyncVolumeCards(volIdx, n);
      refreshChapterStepActions();
      // 2. 立即整卷重存：
      //    - 剩余章的旧 chapter_index（可能大于当前下标 i）会被 doSaveAllChapterOutlines
      //      里 needReindex 分支级联删除 DB 旧位置的脏记录，并 upsert 到新位置 i；
      //    - 显示章号 i+1、数组下标 i、持久 chapter_index=i 三者严格对齐。
      try { await doSaveAllChapterOutlines(volIdx); } catch (_se) { /* ignore */ }
    } else if (res) {
      showStatus('删除失败，请重试', 'error');
    }
  }).catch(err => {
    console.error('删除章节失败：', err);
    showStatus('删除失败，请检查网络连接', 'error');
  });
}

/* ============== 单章折叠 / 展开 切换（自然呼吸感动画：max-height + opacity + translateY） ============== */
function toggleChapterCard(volIdx, chapIdx) {
  const vol = _chapEnsureVolume(volIdx);
  if (!Array.isArray(vol.chapters) || chapIdx >= vol.chapters.length) return;
  const cur = vol.chapters[chapIdx] || {};
  cur.collapsed = !cur.collapsed;
  vol.chapters[chapIdx] = cur;
  const volumeCardsEl = document.getElementById('chapterVolumeCards');
  if (!volumeCardsEl) return;
  const volWrap = volumeCardsEl.querySelector(`.chapter-volume-wrap[data-vol-idx="${String(volIdx)}"]`);
  if (!volWrap) return;
  const cardsContainer = volWrap.querySelector('.chapter-volume-body > div:last-child');
  if (!cardsContainer || !cardsContainer.children[chapIdx]) return;
  const chapWrap = cardsContainer.children[chapIdx];
  const header = chapWrap.querySelector(':scope > .chapter-card-header');
  const body = chapWrap.querySelector(':scope > .chapter-card-body');
  const icon = chapWrap.querySelector('.chapter-card-toggle-icon');
  if (!body || !header) return;
  const collapsed = !!cur.collapsed;
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
    header.style.padding = '13px 20px 13px 68px';
    header.style.background = 'linear-gradient(90deg, rgba(139, 92, 246, 0.08), rgba(139, 92, 246, 0.02))';
  } else {
    body.style.display = 'block';
    // 章卡懒渲染：首次展开时填充 body（同步填充后再计算 scrollHeight，保证动画高度正确）
    if (body.getAttribute('data-body-populated') !== '1') {
      _chapPopulateCardBody(chapWrap, body, volIdx, chapIdx);
    }
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
    header.style.padding = '16px 20px 16px 68px';
    header.style.background = 'linear-gradient(90deg, rgba(139, 92, 246, 0.1), rgba(139, 92, 246, 0.03))';
  }
}

/* ============== 渲染章卡片（复用分卷 event/summary 同款样式 + 折叠呼吸感动画） ============== */
function _renderChapterCard(cardsContainer, volIdx, item, chapIdx) {
  const plot = typeof item.plot === 'string' ? item.plot : '';
  const summary = typeof item.summary === 'string' ? item.summary : '';
  const collapsed = !!item.collapsed;

  const chapWrap = document.createElement('div');
  chapWrap.style.cssText = [
    'border: 1px solid #e0d2fc',
    'border-radius: 14px',
    'background: rgba(255, 255, 255, 0.85)',
    'overflow: hidden',
    'position: relative',
    'transition: box-shadow 0.25s ease, border-color 0.25s ease',
    'box-sizing: border-box',
  ].join(';');
  chapWrap.addEventListener('mouseenter', () => {
    chapWrap.style.boxShadow = '0 8px 24px rgba(168, 85, 247, 0.16)';
    chapWrap.style.borderColor = 'rgba(139, 92, 246, 0.25)';
  });
  chapWrap.addEventListener('mouseleave', () => {
    chapWrap.style.boxShadow = '';
    chapWrap.style.borderColor = '#e0d2fc';
  });

  // ---- 序号徽章（左上角 absolute，在 z-index 最高层） ----
  const idxBadge = document.createElement('div');
  idxBadge.style.cssText = [
    'position: absolute',
    'top: 13px',
    'left: 18px',
    'display: inline-flex',
    'align-items: center',
    'justify-content: center',
    'width: 36px',
    'height: 36px',
    'border-radius: 999px',
    'background: linear-gradient(135deg, #7c3aed, #a855f7)',
    'color: #fff',
    'font-size: 17px',
    'font-weight: 700',
    'box-shadow: 0 4px 12px rgba(168, 85, 247, 0.25)',
    'user-select: none',
    'z-index: 25',
  ].join(';');
  idxBadge.textContent = String(chapIdx + 1);
  chapWrap.appendChild(idxBadge);

  // ---- header：整行可点击切换折叠，整行 padding 左侧 68px 避开徽章 ----
  const header = document.createElement('div');
  header.className = 'chapter-card-header';
  header.style.cssText = [
    'display: flex',
    'align-items: center',
    'justify-content: space-between',
    'gap: 16px',
    'padding: ' + (collapsed ? '13px 20px 13px 68px' : '16px 20px 16px 68px'),
    'background: ' + (collapsed
      ? 'linear-gradient(90deg, rgba(139, 92, 246, 0.08), rgba(139, 92, 246, 0.02))'
      : 'linear-gradient(90deg, rgba(139, 92, 246, 0.1), rgba(139, 92, 246, 0.03))'),
    'cursor: pointer',
    'font-weight: 600',
    'color: #444',
    'user-select: none',
    'transition: background 0.3s ease, padding 0.25s ease',
  ].join(';');
  header.addEventListener('mouseenter', () => {
    const now = !!(_chapEnsureVolume(volIdx).chapters[chapIdx] || {}).collapsed;
    header.style.background = now
      ? 'linear-gradient(90deg, rgba(139, 92, 246, 0.13), rgba(139, 92, 246, 0.05))'
      : 'linear-gradient(90deg, rgba(139, 92, 246, 0.15), rgba(139, 92, 246, 0.06))';
  });
  header.addEventListener('mouseleave', () => {
    const now = !!(_chapEnsureVolume(volIdx).chapters[chapIdx] || {}).collapsed;
    header.style.background = now
      ? 'linear-gradient(90deg, rgba(139, 92, 246, 0.08), rgba(139, 92, 246, 0.02))'
      : 'linear-gradient(90deg, rgba(139, 92, 246, 0.1), rgba(139, 92, 246, 0.03))';
  });
  header.onclick = () => toggleChapterCard(volIdx, chapIdx);

  const headerLeft = document.createElement('div');
  headerLeft.style.cssText = [
    'display: inline-flex',
    'align-items: center',
    'gap: 12px',
    'min-width: 0',
    'flex: 1',
  ].join(';');

  const toggleIconWrap = document.createElement('div');
  toggleIconWrap.style.cssText = [
    'display: inline-flex',
    'align-items: center',
    'justify-content: center',
    'width: 22px',
    'height: 22px',
    'border-radius: 50%',
    'background: rgba(139, 92, 246, 0.1)',
    'flex-shrink: 0',
    'transition: background 0.25s ease, transform 0.25s ease',
  ].join(';');
  const toggleIcon = document.createElement('i');
  toggleIcon.className = 'chapter-card-toggle-icon fas ' + (collapsed ? 'fa-chevron-down' : 'fa-chevron-up');
  toggleIcon.style.cssText = 'font-size: 11px; color: #6d28d9;';
  toggleIconWrap.appendChild(toggleIcon);
  headerLeft.appendChild(toggleIconWrap);

  const sumRaw = summary && summary.trim() ? summary.trim() : '';
  const plotRaw = plot && plot.trim() ? plot.trim() : '';
  const fallbackText = (() => {
    if (sumRaw) return sumRaw;
    if (plotRaw) return plotRaw.length > 80 ? plotRaw.slice(0, 80) + '…' : plotRaw;
    const n1 = (plot || '').length;
    const n2 = (summary || '').length;
    return `剧情 ${n1} 字 / 摘要 ${n2} 字`;
  })();
  if (fallbackText) {
    const sumEl = document.createElement('div');
    sumEl.className = 'chapter-card-sum-preview';
    sumEl.style.cssText = [
      'font-size: 16px',
      'font-weight: 500',
      'color: #555',
      'min-width: 0',
      'flex: 1',
      'padding-left: 4px',
      'padding-right: 12px',
    ].join(';');
    sumEl.title = sumRaw || plotRaw || fallbackText;
    sumEl.textContent = fallbackText;
    headerLeft.appendChild(sumEl);
  }

  header.appendChild(headerLeft);

  const headerRight = document.createElement('div');
  headerRight.style.cssText = [
    'display: inline-flex',
    'align-items: center',
    'gap: 10px',
    'flex-shrink: 0',
  ].join(';');
  headerRight.onclick = (ev) => {
    if (ev) ev.stopPropagation && ev.stopPropagation();
  };

  const cardTip = document.createElement('span');
  cardTip.className = 'chapter-card-save-tip';
  cardTip.setAttribute('data-vol-idx', String(volIdx));
  cardTip.setAttribute('data-chap-idx', String(chapIdx));
  cardTip.innerText = '已自动保存';
  cardTip.style.cssText = [
    'font-size: 12px',
    'color: #7c3aed',
    'opacity: 0',
    'transition: opacity 0.3s',
    'white-space: nowrap',
    'pointer-events: none',
    'margin-right: 4px',
  ].join(';');
  headerRight.appendChild(cardTip);

  const delBtn = document.createElement('button');
  delBtn.type = 'button';
  delBtn.setAttribute('aria-label', '删除本章');
  delBtn.innerHTML = '<i class="fas fa-trash-alt"></i>';
  delBtn.title = `删除第 ${chapIdx + 1} 章`;
  delBtn.style.cssText = [
    'width: 30px',
    'height: 30px',
    'border: none',
    'cursor: pointer',
    'background: none',
    'color: #999',
    'border-radius: 6px',
    'display: inline-flex',
    'align-items: center',
    'justify-content: center',
    'font-size: 17px',
    'padding: 8px',
    'transition: background 0.2s ease, color 0.2s ease, transform 0.12s ease',
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
    window.showConfirm({
      title: '确认删除章节',
      message: `即将删除第 ${volIdx + 1} 卷第 ${chapIdx + 1} 章。<br><br>此操作将 <b>级联删除</b> 该章节关联的：<b>章节章纲、章节事件链、章节正文</b>，以及与这些任务关联的多媒体记录与文件。<br><br><b>此操作不可恢复！</b>`,
      confirmText: '确认级联删除',
      confirmBtnStyle: 'danger',
      cancelText: '取消',
      onConfirm: () => {
        deleteChapterCard(volIdx, chapIdx);
      },
    });
  });
  headerRight.appendChild(delBtn);

  header.appendChild(headerRight);
  chapWrap.appendChild(header);

  // ---- body：懒渲染占位，子节点在 _chapPopulateCardBody 中首次展开时填充 ----
  const body = document.createElement('div');
  body.className = 'chapter-card-body';
  body.setAttribute('data-body-populated', '0');
  body.style.cssText = [
    'padding: 22px 22px 20px',
    'border-top: 1px solid #eee',
    'background: rgba(255, 255, 255, 0.85)',
    'display: ' + (collapsed ? 'none' : 'block'),
    'box-sizing: border-box',
  ].join(';');

  chapWrap.appendChild(body);
  cardsContainer.appendChild(chapWrap);

  // 非折叠态：异步微任务里填充 body，避免卡主线程
  if (!collapsed) {
    requestAnimationFrame(() => _chapPopulateCardBody(chapWrap, body, volIdx, chapIdx));
  }
}

/**
 * 填充章卡 body 内容：剧情 textarea + 摘要 textarea + 所有事件监听器。
 * 带幂等守卫：`data-body-populated === '1'` 时直接 return，避免重复构建。
 * 被 _renderChapterCard（非折叠章）和 toggleChapterCard（首次展开章）调用。
 */
function _chapPopulateCardBody(chapWrap, body, volIdx, chapIdx) {
  if (body.getAttribute('data-body-populated') === '1') return;
  const vol = _chapEnsureVolume(volIdx);
  if (!Array.isArray(vol.chapters)) vol.chapters = [];
  while (vol.chapters.length <= chapIdx) vol.chapters.push({ plot: '', summary: '' });
  const item = vol.chapters[chapIdx] || {};
  const plot = typeof item.plot === 'string' ? item.plot : '';
  const summary = typeof item.summary === 'string' ? item.summary : '';
  body.setAttribute('data-body-populated', '1');

  // --- 剧情 textarea ---
  const evWrap = document.createElement('div');
  evWrap.style.cssText = [
    'margin-bottom: 14px',
    'position: relative',
    'width: 100%',
    'display: block',
    'box-sizing: border-box',
    'pointer-events: none',
  ].join(';');
  const evLabel = document.createElement('div');
  evLabel.style.cssText = [
    'font-size: 17px',
    'font-weight: 600',
    'color: #4c1d95',
    'margin-bottom: 6px',
    'display: flex',
    'align-items: center',
    'justify-content: space-between',
    'pointer-events: auto',
  ].join(';');
  const PLOT_MAX_LABEL = _getThCh('chapter_plot_chars', _CHAPTER_PLOT_MAX_CHARS);
  evLabel.innerHTML = `<span>剧情（建议 ${PLOT_MAX_LABEL} 字内，最大 ${_getThCh('chapter_plot_hard_chars', _CHAPTER_PLOT_HARD_CHARS)} 字）</span>`;
  const evTa = document.createElement('textarea');
  evTa.rows = 8;
  evTa.placeholder = '填写本章主剧情、核心冲突、关键转折…修改后失焦自动保存';
  evTa.value = plot;
  evTa.style.cssText = [
    'width: 100%',
    'min-height: 200px',
    'padding: 12px 14px',
    'border-radius: 10px',
    'border: 1px solid #e0d2fc',
    'background: rgba(255, 255, 255, 0.85)',
    'font-size: 18px',
    'line-height: 1.75',
    'color: #333',
    'box-sizing: border-box',
    'white-space: pre-wrap',
    'word-break: break-word',
    'resize: vertical',
    'outline: none',
    'transition: border-color 0.15s, box-shadow 0.15s',
    'font-family: inherit',
    'pointer-events: auto',
  ].join(';');
  const evCount = document.createElement('div');
  evCount.className = 'char-counter';
  evCount.setAttribute('data-chapter-count-plot', String(volIdx) + '_' + String(chapIdx));
  evCount.style.cssText = [
    'pointer-events: auto',
    'margin: 0',
    'padding: 0',
    'position: static',
    'transform: none',
  ].join(';');
  const PLOT_HARD_I = _getThCh('chapter_plot_hard_chars', _CHAPTER_PLOT_HARD_CHARS);
  const SUM_HARD_I = _getThCh('chapter_summary_hard_chars', _CHAPTER_SUMMARY_HARD_CHARS);
  evCount.textContent = `${(plot || '').length} / ${_getThCh('chapter_plot_hard_chars', _CHAPTER_PLOT_HARD_CHARS)}`;
  evLabel.appendChild(evCount);
  const applyHardLimitsI = () => {
    const changedPlot = _enforceChapterHardMax(evTa, PLOT_HARD_I, `第 ${volIdx + 1} 卷第 ${chapIdx + 1} 章剧情`);
    const changedSum = _enforceChapterHardMax(suTa, SUM_HARD_I, `第 ${volIdx + 1} 卷第 ${chapIdx + 1} 章摘要`);
    if (changedPlot || changedSum) {
      const v = _chapEnsureVolume(volIdx);
      if (!Array.isArray(v.chapters)) v.chapters = [];
      while (v.chapters.length <= chapIdx) v.chapters.push({ plot: '', summary: '' });
      const cur = v.chapters[chapIdx] || {};
      cur.plot = typeof evTa.value === 'string' ? evTa.value : '';
      cur.summary = typeof suTa.value === 'string' ? suTa.value : '';
      v.chapters[chapIdx] = cur;
    }
    _refreshChapterCardCount(volIdx, chapIdx);
    return changedPlot || changedSum;
  };
  evTa.addEventListener('focus', () => {
    evTa.style.borderColor = '#8b5cf6';
    evTa.style.boxShadow = '0 0 0 3px rgba(139, 92, 246, 0.12)';
  });
  evTa.addEventListener('blur', () => {
    evTa.style.borderColor = '#e0d2fc';
    evTa.style.boxShadow = 'none';
    applyHardLimitsI();
    scheduleChapterAutoSave(volIdx, true, chapIdx);
  });
  evTa.addEventListener('input', () => {
    applyHardLimitsI();
    const v = _chapEnsureVolume(volIdx);
    if (!Array.isArray(v.chapters)) v.chapters = [];
    while (v.chapters.length <= chapIdx) v.chapters.push({ plot: '', summary: '' });
    const cur = v.chapters[chapIdx] || {};
    cur.plot = typeof evTa.value === 'string' ? evTa.value : '';
    v.chapters[chapIdx] = cur;
    scheduleChapterAutoSave(volIdx, false, chapIdx);
  });
  evTa.addEventListener('paste', () => { setTimeout(() => { applyHardLimitsI(); }, 0); });
  evWrap.appendChild(evLabel);
  evWrap.appendChild(evTa);
  body.appendChild(evWrap);

  // --- 摘要 textarea（外层包装，同剧情样式） ---
  const suWrap = document.createElement('div');
  suWrap.style.cssText = [
    'position: relative',
    'width: 100%',
    'display: block',
    'box-sizing: border-box',
    'pointer-events: none',
  ].join(';');
  const suLabel = document.createElement('div');
  suLabel.style.cssText = [
    'font-size: 17px',
    'font-weight: 600',
    'color: #4c1d95',
    'margin: 0 0 6px',
    'padding: 0',
    'display: flex',
    'align-items: center',
    'justify-content: space-between',
    'pointer-events: auto',
  ].join(';');
  const SUM_MAX_LABEL = _getThCh('chapter_summary_chars', _CHAPTER_SUMMARY_MAX_CHARS);
  suLabel.innerHTML = `<span>摘要（建议 ${SUM_MAX_LABEL} 字内，最大 ${_getThCh('chapter_summary_hard_chars', _CHAPTER_SUMMARY_HARD_CHARS)} 字）</span>`;
  const suTa = document.createElement('textarea');
  suTa.rows = 3;
  suTa.placeholder = '一句话概括本章核心事件（主导者为主语，不提炼主题）';
  suTa.value = summary;
  const suTaBox = document.createElement('div');
  suTaBox.style.cssText = [
    'padding: 8px 10px',
    'border-radius: 10px',
    'background: rgba(139, 92, 246, 0.06)',
    'position: relative',
    'pointer-events: auto',
    'box-sizing: border-box',
  ].join(';');
  suTa.style.cssText = [
    'width: 100%',
    'min-height: 88px',
    'padding: 10px 12px',
    'border-radius: 8px',
    'border: 1px solid rgba(139, 92, 246, 0.15)',
    'background: rgba(255, 255, 255, 0.85)',
    'font-size: 18px',
    'line-height: 1.6',
    'color: #333',
    'box-sizing: border-box',
    'white-space: pre-wrap',
    'word-break: break-word',
    'resize: vertical',
    'outline: none',
    'transition: border-color 0.15s, box-shadow 0.15s',
    'font-family: inherit',
    'pointer-events: auto',
  ].join(';');
  const suCount = document.createElement('div');
  suCount.className = 'char-counter';
  suCount.setAttribute('data-chapter-count-summary', String(volIdx) + '_' + String(chapIdx));
  suCount.style.cssText = [
    'pointer-events: auto',
    'margin: 0',
    'padding: 0',
    'position: static',
    'transform: none',
  ].join(';');
  suCount.textContent = `${(summary || '').length} / ${_getThCh('chapter_summary_hard_chars', _CHAPTER_SUMMARY_HARD_CHARS)}`;
  suLabel.appendChild(suCount);
  suTaBox.appendChild(suTa);
  suTa.addEventListener('focus', () => {
    suTa.style.borderColor = '#8b5cf6';
    suTa.style.boxShadow = '0 0 0 3px rgba(139, 92, 246, 0.12)';
  });
  suTa.addEventListener('blur', () => {
    suTa.style.borderColor = 'rgba(139, 92, 246, 0.15)';
    suTa.style.boxShadow = 'none';
    applyHardLimitsI();
    scheduleChapterAutoSave(volIdx, true, chapIdx);
  });
  suTa.addEventListener('input', () => {
    applyHardLimitsI();
    const v = _chapEnsureVolume(volIdx);
    if (!Array.isArray(v.chapters)) v.chapters = [];
    while (v.chapters.length <= chapIdx) v.chapters.push({ plot: '', summary: '' });
    const cur = v.chapters[chapIdx] || {};
    cur.summary = typeof suTa.value === 'string' ? suTa.value : '';
    v.chapters[chapIdx] = cur;
    scheduleChapterAutoSave(volIdx, false, chapIdx);
  });
  suTa.addEventListener('paste', () => { setTimeout(() => { applyHardLimitsI(); }, 0); });
  suWrap.appendChild(suLabel);
  suWrap.appendChild(suTaBox);
  body.appendChild(suWrap);

  try { applyHardLimitsI(); } catch (_e) {}
}

/**
 * 增量同步单卷章卡 DOM 与内存模型（避免全量 renderChapterVolumes 重渲）。
 * - [0, rebuildFromCi) 范围：就地更新 header 预览 + body textarea（保留 body 已填充状态与事件绑定）
 * - [rebuildFromCi, 旧 DOM 末尾) 范围：移除旧章卡
 * - [rebuildFromCi, 内存模型末尾) 范围：追加新章卡（_renderChapterCard 内部 rAF 填充 body）
 * 未展开的卷（data-chapters-populated !== '1'）只更新计数标记，等展开时按最新内存模型补建。
 */
function _chapSyncVolumeCards(vi, rebuildFromCi) {
  const volumeCardsEl = document.getElementById('chapterVolumeCards');
  if (!volumeCardsEl) return;
  const volWrap = volumeCardsEl.querySelector(`.chapter-volume-wrap[data-vol-idx="${String(vi)}"]`);
  if (!volWrap) return;
  const cardsContainer = volWrap.querySelector('.chapter-cards-container');
  if (!cardsContainer) return;
  const volState = _chapEnsureVolume(vi);
  const chapters = Array.isArray(volState.chapters) ? volState.chapters : [];

  // 更新章数标记与标题
  cardsContainer.setAttribute('data-chapter-count', String(chapters.length));
  const chapLabel = volWrap.querySelector('.chapter-list-label');
  if (chapLabel) {
    chapLabel.innerHTML = '<span>📑</span> <span>章纲剧情（共 ' + String(chapters.length) + ' 章）</span>';
  }

  // 未展开的卷：只更新计数，等展开时按最新内存模型补建
  if (cardsContainer.getAttribute('data-chapters-populated') !== '1') return;

  // 空列表：显示空状态提示
  if (chapters.length === 0) {
    cardsContainer.innerHTML = '';
    const empty = document.createElement('div');
    empty.style.cssText = [
      'padding: 24px 18px',
      'border: 1px dashed #d8c9f5',
      'border-radius: 8px',
      'text-align: center',
      'font-size: 16px',
      'color: #6d28d9',
      'background: #faf6ff',
    ].join(';');
    empty.innerHTML = '暂无章纲内容。可点击右上角「生成章纲剧情」或「添加章节」。';
    cardsContainer.appendChild(empty);
    return;
  }

  // 清理可能残留的空状态提示（之前 chapters.length===0 时插入的 empty div）
  let domCount = cardsContainer.children.length;
  if (domCount > 0) {
    const first = cardsContainer.children[0];
    if (first && !first.querySelector(':scope > .chapter-card-header')) {
      cardsContainer.innerHTML = '';
      domCount = 0;
    }
  }

  const start = (typeof rebuildFromCi === 'number' && rebuildFromCi >= 0)
    ? Math.min(rebuildFromCi, chapters.length, domCount)
    : Math.min(chapters.length, domCount);

  // 1. 就地更新 [0, start) 范围的章卡（保留 body 已填充状态与事件绑定）
  for (let ci = 0; ci < start; ci++) {
    const domCard = cardsContainer.children[ci];
    if (!domCard) continue;
    const item = chapters[ci] || {};
    const plot = typeof item.plot === 'string' ? item.plot : '';
    const summary = typeof item.summary === 'string' ? item.summary : '';
    const sumRaw = summary && summary.trim() ? summary.trim() : '';
    const plotRaw = plot && plot.trim() ? plot.trim() : '';
    const fallbackText = (() => {
      if (sumRaw) return sumRaw;
      if (plotRaw) return plotRaw.length > 80 ? plotRaw.slice(0, 80) + '…' : plotRaw;
      const n1 = (plot || '').length;
      const n2 = (summary || '').length;
      return `剧情 ${n1} 字 / 摘要 ${n2} 字`;
    })();
    const sumEl = domCard.querySelector('.chapter-card-sum-preview');
    if (sumEl) {
      sumEl.title = sumRaw || plotRaw || fallbackText;
      sumEl.textContent = fallbackText;
    }
    // body 已填充则更新 textarea，否则保留未填充态（展开时按最新内存模型填充）
    const chapBody = domCard.querySelector(':scope > .chapter-card-body');
    if (chapBody && chapBody.getAttribute('data-body-populated') === '1') {
      const allTa = chapBody.querySelectorAll('textarea');
      const evTa = allTa[0] || null;
      const suTa = allTa[1] || null;
      if (evTa) evTa.value = plot;
      if (suTa) suTa.value = summary;
      _refreshChapterCardCount(vi, ci);
    }
  }

  // 2. 移除 [start, domCount) 范围的旧章卡
  for (let ci = domCount - 1; ci >= start; ci--) {
    if (cardsContainer.children[ci]) cardsContainer.children[ci].remove();
  }

  // 3. 追加 [start, chapters.length) 范围的新章卡
  for (let ci = start; ci < chapters.length; ci++) {
    _renderChapterCard(cardsContainer, vi, chapters[ci] || {}, ci);
  }
}

/* ============== 渲染按卷分组的定章主页 ============== */
function renderChapterVolumes() {
  // ===== 关键修复：给定章结果容器显式拉高 z-index，压在谋篇节点的 d3 svg/canvas 合成层之上（最高 z-index 3）
  // 与分卷页修复逻辑 1:1 对齐，保证不聚焦 textarea 也能稳定命中删除按钮
  (function _chapRaiseZ() {
    try {
      const ids = ['chapterArea', 'chapterVolumeResult', 'chapterVolumeCards'];
      for (let i = 0; i < ids.length; i++) {
        const el = document.getElementById(ids[i]);
        if (!el) continue;
        const cur = el.getAttribute('style') || '';
        // 先清除已有 z-index/position 冲突设置，避免重复追加
        const cleaned = String(cur).replace(/position\s*:\s*[^;]*;?/gi, '').replace(/z-index\s*:\s*[^;]*;?/gi, '');
        el.setAttribute('style', (cleaned + '; position: relative; z-index: ' + (998 + i) + ';').replace(/;;/g, ';'));
      }
    } catch (_e) {}
  })();

  const volumeCardsEl = document.getElementById('chapterVolumeCards');
  const resultBox = document.getElementById('chapterVolumeResult');
  if (!volumeCardsEl) return;
  volumeCardsEl.innerHTML = '';

  const volumes = (window._volumePlotResult && Array.isArray(window._volumePlotResult.volumes))
    ? window._volumePlotResult.volumes
    : [];

  if (!Array.isArray(volumes) || volumes.length === 0) {
    if (resultBox) resultBox.style.display = 'block';
    const empty = document.createElement('div');
    empty.style.cssText = [
      'padding: 28px 20px',
      'border: 1px dashed rgba(139, 92, 246, 0.35)',
      'border-radius: 12px',
      'text-align: center',
      'font-size: 17px',
      'color: #6d28d9',
      'background: rgba(139, 92, 246, 0.04)',
    ].join(';');
    empty.innerHTML = '暂无分卷卷纲。请先在「分卷」页面生成并保存卷纲剧情后，再进入本定章页面生成章纲。';
    volumeCardsEl.appendChild(empty);
    return;
  }
  if (resultBox) resultBox.style.display = 'block';

  const metaLine = document.createElement('div');
  metaLine.style.cssText = [
    'padding: 14px 0 12px',
    'font-size: 16px', 'color: #5b21b6',
    'display: inline-flex', 'align-items: center', 'gap: 8px',
    'opacity: 0.85',
  ].join(';');
  metaLine.innerHTML = `<i class="fas fa-info-circle"></i><span>本作品共 ${volumes.length} 卷，以下卡片每张对应一卷：卷纲只读 + 章纲可编辑。`;
  volumeCardsEl.appendChild(metaLine);

  // 首次渲染：预填充所有卷 + 规范化默认折叠状态（懒展开：仅第 0 卷 + 第 0 章展开）
  _chapApplyInitFold(volumes);

  for (let volIdx = 0; volIdx < volumes.length; volIdx++) {
    const volMeta = volumes[volIdx] || {};
    const volPlot = typeof volMeta.plot === 'string' ? volMeta.plot : '';
    const volSummaryRaw = typeof volMeta.summary === 'string' ? volMeta.summary.trim() : '';
    const volState = _chapEnsureVolume(volIdx);
    const chapters = Array.isArray(volState.chapters) ? volState.chapters.slice() : [];
    const collapsed = !!volState.collapsed;

    const volWrap = document.createElement('div');
    volWrap.className = 'chapter-volume-wrap';
    volWrap.setAttribute('data-vol-idx', String(volIdx));
    volWrap.style.cssText = [
      'border: 1px solid #e8e6ed',
      'border-radius: 10px',
      'background: rgba(255, 255, 255, 0.85)',
      'overflow: hidden',
      'transition: box-shadow 0.25s ease, border-color 0.25s ease',
      'margin-bottom: 14px',
    ].join(';');
    volWrap.addEventListener('mouseenter', () => {
      volWrap.style.boxShadow = '0 6px 18px rgba(74, 0, 224, 0.08)';
      volWrap.style.borderColor = 'rgba(139, 92, 246, 0.25)';
    });
    volWrap.addEventListener('mouseleave', () => {
      volWrap.style.boxShadow = '';
      volWrap.style.borderColor = '#e8e6ed';
    });

    const header = document.createElement('div');
    header.style.cssText = [
      'display: flex',
      'align-items: center',
      'justify-content: space-between',
      'gap: 16px',
      'padding: ' + (collapsed ? '13px 20px' : '16px 20px'),
      'background: ' + (collapsed
        ? 'linear-gradient(90deg, rgba(139, 92, 246, 0.08), rgba(139, 92, 246, 0.02))'
        : 'linear-gradient(90deg, rgba(139, 92, 246, 0.1), rgba(139, 92, 246, 0.03))'),
      'cursor: pointer',
      'font-weight: 600',
      'color: #444',
      'user-select: none',
      'transition: background 0.3s ease, padding 0.25s ease',
    ].join(';');
    header.addEventListener('mouseenter', () => {
      header.style.background = collapsed
        ? 'linear-gradient(90deg, rgba(139, 92, 246, 0.13), rgba(139, 92, 246, 0.05))'
        : 'linear-gradient(90deg, rgba(139, 92, 246, 0.15), rgba(139, 92, 246, 0.06))';
    });
    header.addEventListener('mouseleave', () => {
      header.style.background = collapsed
        ? 'linear-gradient(90deg, rgba(139, 92, 246, 0.08), rgba(139, 92, 246, 0.02))'
        : 'linear-gradient(90deg, rgba(139, 92, 246, 0.1), rgba(139, 92, 246, 0.03))';
    });
    header.onclick = () => toggleChapterVolume(volIdx);

    const headerLeft = document.createElement('div');
    headerLeft.style.cssText = [
      'display: inline-flex',
      'align-items: center',
      'gap: 12px',
      'min-width: 0',
      'flex: 1',
    ].join(';');

    const toggleIconWrap = document.createElement('div');
    toggleIconWrap.style.cssText = [
      'display: inline-flex',
      'align-items: center',
      'justify-content: center',
      'width: 22px',
      'height: 22px',
      'border-radius: 50%',
      'background: rgba(139, 92, 246, 0.1)',
      'flex-shrink: 0',
      'transition: background 0.25s ease, transform 0.25s ease',
    ].join(';');
    const toggleIcon = document.createElement('i');
    toggleIcon.className = 'chapter-toggle-icon fas ' + (collapsed ? 'fa-chevron-down' : 'fa-chevron-up');
    toggleIcon.style.cssText = 'font-size: 11px; color: #6d28d9;';
    toggleIconWrap.appendChild(toggleIcon);
    headerLeft.appendChild(toggleIconWrap);

    const badge = document.createElement('div');
    badge.style.cssText = [
      'display: inline-flex',
      'align-items: center',
      'justify-content: center',
      'min-width: 52px',
      'height: 28px',
      'padding: 0 14px',
      'border-radius: 999px',
      'background: linear-gradient(135deg, #6d28d9, #a855f7)',
      'color: #fff',
      'font-size: 16px',
      'font-weight: 700',
      'flex-shrink: 0',
      'cursor: default',
      'box-shadow: 0 2px 8px rgba(168, 85, 247, 0.25)',
      'letter-spacing: 0.2px',
    ].join(';');
    badge.textContent = `第 ${volIdx + 1} 卷`;
    headerLeft.appendChild(badge);

    if (volSummaryRaw) {
      const volSumEl = document.createElement('div');
      volSumEl.style.cssText = [
        'font-size: 16px',
        'font-weight: 500',
        'color: #555',
        'min-width: 0',
        'flex: 1',
        'white-space: nowrap',
        'overflow: hidden',
        'text-overflow: ellipsis',
        'padding-left: 4px',
        'padding-right: 12px',
        'max-width: 420px',
      ].join(';');
      volSumEl.title = volSummaryRaw;
      volSumEl.textContent = volSummaryRaw;
      headerLeft.appendChild(volSumEl);
    }

    header.appendChild(headerLeft);

    const headerRight = document.createElement('div');
    headerRight.style.cssText = [
      'display: inline-flex',
      'align-items: center',
      'gap: 10px',
      'flex-shrink: 0',
    ].join(';');
    headerRight.onclick = (ev) => {
      if (ev) ev.stopPropagation && ev.stopPropagation();
    };

    const saveTip = document.createElement('span');
    saveTip.className = 'chapter-volume-save-tip';
    saveTip.setAttribute('data-vol-idx', String(volIdx));
    saveTip.innerText = '已自动保存';
    saveTip.style.cssText = [
      'font-size: 12px',
      'color: #7c3aed',
      'opacity: 0',
      'transition: opacity 0.3s',
      'white-space: nowrap',
      'pointer-events: none',
    ].join(';');
    headerRight.appendChild(saveTip);

    const genBtn = document.createElement('button');
    genBtn.type = 'button';
    genBtn.id = `generateChapterBtn_${volIdx}`;
    genBtn.onclick = (ev) => {
      if (ev) ev.stopPropagation && ev.stopPropagation();
      generateChapterPlotDesign(volIdx);
    };
    genBtn.innerHTML = '<i class="fas fa-magic"></i> <span>生成章纲剧情</span>';
    genBtn.style.cssText = [
      'display: inline-flex',
      'align-items: center',
      'gap: 6px',
      'padding: 7px 14px',
      'border-radius: 6px',
      'border: 1px solid rgba(168, 85, 247, 0.3)',
      'cursor: pointer',
      'color: #6d28d9',
      'font-size: 16px',
      'font-weight: 600',
      'background: rgba(168, 85, 247, 0.15)',
      'transition: background 0.15s, border-color 0.15s',
      'font-family: inherit',
      'line-height: 1.2',
    ].join(';');
    genBtn.addEventListener('mouseenter', () => {
      if (!genBtn.disabled) {
        genBtn.style.background = 'rgba(168, 85, 247, 0.25)';
        genBtn.style.borderColor = 'rgba(168, 85, 247, 0.4)';
      }
    });
    genBtn.addEventListener('mouseleave', () => {
      if (!genBtn.disabled) {
        genBtn.style.background = 'rgba(168, 85, 247, 0.15)';
        genBtn.style.borderColor = 'rgba(168, 85, 247, 0.3)';
      }
    });
    headerRight.appendChild(genBtn);

    header.appendChild(headerRight);
    volWrap.appendChild(header);

    const body = document.createElement('div');
    body.className = 'chapter-volume-body';
    body.style.cssText = [
      'padding: 20px',
      'border-top: 1px solid #e8e6ed',
      'background: rgba(255, 255, 255, 0.85)',
      'display: ' + (collapsed ? 'none' : 'block'),
    ].join(';');

    const volPlotBox = document.createElement('div');
    volPlotBox.style.cssText = [
      'margin-bottom: 22px',
      'border-radius: 14px',
      'padding: 18px 20px',
      'background: linear-gradient(135deg, rgba(139, 92, 246, 0.08), rgba(168, 85, 247, 0.05))',
      'border: 1px solid rgba(139, 92, 246, 0.15)',
      'position: relative',
    ].join(';');

    const volPlotHead = document.createElement('div');
    volPlotHead.style.cssText = [
      'display: flex',
      'align-items: center',
      'justify-content: space-between',
      'gap: 16px',
      'margin-bottom: 12px',
      'flex-wrap: wrap',
    ].join(';');
    const volPlotHeadLeft = document.createElement('div');
    volPlotHeadLeft.style.cssText = [
      'font-size: 17px',
      'font-weight: 700',
      'color: #4c1d95',
      'display: inline-flex',
      'align-items: center',
      'gap: 8px',
    ].join(';');
    volPlotHeadLeft.innerHTML = '<i class="fas fa-book-open" style="font-size: 16px;"></i> <span>卷纲剧情（只读，修改请切到「分卷」页）</span>';
    const volPlotHeadRight = document.createElement('div');
    volPlotHeadRight.style.cssText = [
      'display: inline-flex',
      'align-items: center',
      'gap: 14px',
      'opacity: 0.9',
    ].join(';');
    volPlotHeadRight.classList.add('char-counter');
    const volPlotEvCount = document.createElement('div');
    volPlotEvCount.style.cssText = 'display: inline-flex; align-items: center; gap: 4px;';
    volPlotEvCount.innerHTML = `<i class="fas fa-pen-fancy" style="font-size: 11px; opacity: 0.85;"></i> <span>剧情 ${(volPlot || '').length} 字</span>`;
    const volPlotSuCount = document.createElement('div');
    volPlotSuCount.style.cssText = 'display: inline-flex; align-items: center; gap: 4px;';
    volPlotSuCount.innerHTML = `<i class="fas fa-stream" style="font-size: 11px; opacity: 0.85;"></i> <span>摘要 ${(volSummaryRaw || '').length} 字</span>`;
    volPlotHeadRight.appendChild(volPlotEvCount);
    volPlotHeadRight.appendChild(volPlotSuCount);
    volPlotHead.appendChild(volPlotHeadLeft);
    volPlotHead.appendChild(volPlotHeadRight);
    volPlotBox.appendChild(volPlotHead);

    const volPlotBody = document.createElement('div');
    volPlotBody.style.cssText = [
      'padding: 14px 16px',
      'background: rgba(255, 255, 255, 0.75)',
      'border-radius: 10px',
      'border: 1px solid rgba(139, 92, 246, 0.1)',
    ].join(';');

    const volPlotEvText = document.createElement('div');
    volPlotEvText.style.cssText = [
      'font-size: 17px',
      'line-height: 1.75',
      'color: #1f2937',
      'white-space: pre-wrap',
      'word-break: break-word',
      'margin-bottom: volSummaryRaw ? 12px : 0',
    ].join(';').replace('volSummaryRaw ? 12px : 0', volSummaryRaw ? '12px' : '0');
    volPlotEvText.textContent = volPlot || '（当前卷暂无卷纲内容）';
    volPlotBody.appendChild(volPlotEvText);

    if (volSummaryRaw) {
      const volPlotSuWrap = document.createElement('div');
      volPlotSuWrap.style.cssText = [
        'padding: 8px 10px',
        'border-radius: 8px',
        'background: rgba(139, 92, 246, 0.08)',
        'border-left: 3px solid #a78bfa',
      ].join(';');
      const volPlotSuText = document.createElement('div');
      volPlotSuText.style.cssText = [
        'font-size: 16px',
        'line-height: 1.6',
        'color: #4c1d95',
        'white-space: pre-wrap',
        'word-break: break-word',
      ].join(';');
      volPlotSuText.textContent = '【摘要】' + volSummaryRaw;
      volPlotSuWrap.appendChild(volPlotSuText);
      volPlotBody.appendChild(volPlotSuWrap);
    }
    volPlotBox.appendChild(volPlotBody);
    body.appendChild(volPlotBox);

    const chapListTitle = document.createElement('div');
    chapListTitle.style.cssText = [
      'display: flex',
      'align-items: center',
      'justify-content: space-between',
      'margin-bottom: 14px',
      'gap: 12px',
    ].join(';');
    const chapLabel = document.createElement('div');
    chapLabel.className = 'chapter-list-label';
    chapLabel.style.cssText = [
      'font-size: 17px',
      'font-weight: 600',
      'color: #444',
      'display: inline-flex',
      'align-items: center',
      'gap: 8px',
    ].join(';');
    chapLabel.innerHTML = '<span>📑</span> <span>章纲剧情（共 ' + String(chapters.length) + ' 章）</span>';
    chapListTitle.appendChild(chapLabel);

    const addChapBtn = document.createElement('button');
    addChapBtn.type = 'button';
    addChapBtn.onclick = (ev) => {
      if (ev) ev.stopPropagation && ev.stopPropagation();
      addChapterCard(volIdx);
    };
    addChapBtn.innerHTML = '<i class="fas fa-plus"></i> <span>添加章节</span>';
    addChapBtn.style.cssText = [
      'display: inline-flex',
      'align-items: center',
      'gap: 6px',
      'padding: 7px 14px',
      'border-radius: 6px',
      'border: 1px solid rgba(168, 85, 247, 0.3)',
      'background: rgba(168, 85, 247, 0.15)',
      'color: #6d28d9',
      'cursor: pointer',
      'font-size: 16px',
      'font-weight: 600',
      'transition: background 0.15s, border-color 0.15s',
      'font-family: inherit',
      'line-height: 1.2',
    ].join(';');
    addChapBtn.addEventListener('mouseenter', () => {
      addChapBtn.style.background = 'rgba(168, 85, 247, 0.25)';
      addChapBtn.style.borderColor = 'rgba(168, 85, 247, 0.4)';
    });
    addChapBtn.addEventListener('mouseleave', () => {
      addChapBtn.style.background = 'rgba(168, 85, 247, 0.15)';
      addChapBtn.style.borderColor = 'rgba(168, 85, 247, 0.3)';
    });
    chapListTitle.appendChild(addChapBtn);

    body.appendChild(chapListTitle);

    const cardsContainer = document.createElement('div');
    cardsContainer.className = 'chapter-cards-container';
    cardsContainer.setAttribute('data-chapters-populated', collapsed ? '0' : '1');
    cardsContainer.setAttribute('data-chapter-count', String(chapters.length));
    cardsContainer.style.cssText = [
      'display: flex',
      'flex-direction: column',
      'gap: 16px',
    ].join(';');
    if (chapters.length === 0) {
      const empty = document.createElement('div');
      empty.style.cssText = [
        'padding: 24px 18px',
        'border: 1px dashed #d8c9f5',
        'border-radius: 8px',
        'text-align: center',
        'font-size: 16px',
        'color: #6d28d9',
        'background: #faf6ff',
      ].join(';');
      empty.innerHTML = '暂无章纲内容。可点击右上角「生成章纲剧情」或「添加章节」。';
      cardsContainer.appendChild(empty);
    } else if (!collapsed) {
      // 卷层懒渲染：展开卷才创建章卡 DOM，折叠卷留空容器等展开时补建
      for (let c = 0; c < chapters.length; c++) {
        _renderChapterCard(cardsContainer, volIdx, chapters[c] || {}, c);
      }
    }
    body.appendChild(cardsContainer);

    volWrap.appendChild(body);
    volumeCardsEl.appendChild(volWrap);
  }
}

/* ============== 下一步：推演按钮状态控制 ============== */
function refreshChapterStepActions() {
  const nextBtn = document.getElementById('nextStepBtnChapter');
  if (!nextBtn) return;
  if (!window.currentWorkId) {
    nextBtn.disabled = true;
    nextBtn.title = '请先在左侧选择一个作品';
    return;
  }
  const has = _chapHasAnyChapterData();
  if (has) {
    nextBtn.disabled = false;
    nextBtn.title = '进入推演环节：基于章纲逐章拆分章节级事件（场景/动作/对白）';
  } else {
    nextBtn.disabled = true;
    nextBtn.title = '请先在至少一卷中点击「生成本卷章纲剧情」或手动添加章节，生成章纲数据后再进入推演';
  }
}

/* ============== 从任务表加载章纲历史（init 与 needRefetch 复用） ============== */
async function _chapLoadHistoryTasks() {
  if (!window.currentWorkId) return;
  try {
    const rows = await NovelAPI.listTasks(
      window.currentWorkId,
      NovelAPI.CONST.TASK_TYPE_CHAPTER_OUTLINE,
      'id',
      true,
    );
    if (!Array.isArray(rows) || rows.length === 0) return;
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i] || {};
      const volIdx = (r.volume_index !== null && r.volume_index !== undefined) ? Number(r.volume_index) : -1;
      const chapIdx = (r.chapter_index !== null && r.chapter_index !== undefined) ? Number(r.chapter_index) : -1;
      if (volIdx < 0) continue;

      const chapter = _chapTryParseChapterRow(r);
      if (!chapter) continue;
      const vol = _chapEnsureVolume(volIdx);
      if (!Array.isArray(vol.chapters)) vol.chapters = [];

      // 如果有确定的章号，按章号插入；否则追加
      if (chapIdx >= 0) {
        // 确保数组足够大，空位填充空对象占位，保持数组索引与 chapter_index 严格对齐
        while (vol.chapters.length <= chapIdx) {
          vol.chapters.push({ plot: '', summary: '' });
        }
        // 仅在该位置为空（无内容）时才覆写；已有内容时保留
        const existing = vol.chapters[chapIdx] || {};
        const hasExisting = (typeof existing.plot === 'string' && existing.plot.trim())
          || (typeof existing.summary === 'string' && existing.summary.trim());
        if (!hasExisting) {
          vol.chapters[chapIdx] = chapter;
        }
        // 记录 DB 原始 chapter_index：删除中间章后触发 doSaveAllChapterOutlines 时，
        // needReindex 检测会用到这个值来级联清理旧位置的 DB 记录。
        vol.chapters[chapIdx].chapter_index = chapIdx;
        // 无论是否覆写，都将 activeTaskId 记录到该章对象上（按章隔离，与推演/成文对齐）
        const id = (r.id || r.id === 0) ? String(r.id) : '';
        if (id && !vol.chapters[chapIdx].activeTaskId) {
          vol.chapters[chapIdx].activeTaskId = id;
        }
      } else {
        // 无章号时直接追加（兼容历史脏数据）
        vol.chapters.push(chapter);
      }
    }
  } catch (_e) {
    console.warn('[_chapLoadHistoryTasks] fetch chapter tasks failed:', _e?.message || _e);
  }
}

/**
 * 内联卷纲行解析（不依赖 novel-volume.js 的 _volTryParseVolumeRow）
 * 解析 task row 的 content_text，提取 plot/summary
 */
function _chapParseVolumeRow(row) {
  let obj = null;
  try { obj = (row && typeof row.content_text === 'string') ? JSON.parse(row.content_text) : null; } catch (_) {}
  // 空 content_text 也视为占位空卷：用户手动添加过卷但未填写任何内容
  if (!obj) return [{ plot: '', summary: '' }];
  let arr = [];
  if (Array.isArray(obj.volumes)) {
    arr = obj.volumes;
  } else if (Array.isArray(obj.events)) {
    arr = obj.events.map(function(e) {
      return {
        plot: e && typeof e.plot === 'string' ? e.plot : (e && typeof e.event === 'string' ? e.event : ''),
        summary: e && typeof e.summary === 'string' ? e.summary : ''
      };
    });
  } else if (typeof obj.plot === 'string' || typeof obj.summary === 'string'
      || Object.prototype.hasOwnProperty.call(obj, 'plot') || Object.prototype.hasOwnProperty.call(obj, 'summary')) {
    arr = [{
      plot: typeof obj.plot === 'string' ? obj.plot : '',
      summary: typeof obj.summary === 'string' ? obj.summary : ''
    }];
  } else if (obj.volume_plot_design && typeof obj.volume_plot_design === 'object') {
    const inner = obj.volume_plot_design;
    arr = [{
      plot: typeof inner.plot === 'string' ? inner.plot : '',
      summary: typeof inner.summary === 'string' ? inner.summary : ''
    }];
  } else if (obj.result && obj.result.volume_plot_design && typeof obj.result.volume_plot_design === 'object') {
    const inner = obj.result.volume_plot_design;
    arr = [{
      plot: typeof inner.plot === 'string' ? inner.plot : '',
      summary: typeof inner.summary === 'string' ? inner.summary : ''
    }];
  }
  // 不过滤空卷：用户手动添加的空卷必须保留，否则切页面后消失
  return arr.map(function(v) {
    if (!v) return { plot: '', summary: '' };
    return {
      plot: typeof v.plot === 'string' ? v.plot : '',
      summary: typeof v.summary === 'string' ? v.summary : ''
    };
  });
}

/* ============== 初始化入口 ============== */
async function initChapterPage() {
  // 【作品级隔离 SOP】切作品进入定章节点时，先清空所有作品级单例/DOM，再拉数据/渲染
  resetChapterPageIsolatedState();
  if (!window._chapterPlotResult) window._chapterPlotResult = { volumes: [] };
  if (!window.currentWorkId) {
    const volumeCardsEl = document.getElementById('chapterVolumeCards');
    if (volumeCardsEl) volumeCardsEl.innerHTML = '';
    renderChapterVolumes();
    refreshChapterStepActions();
    return;
  }

  let volEvents = (window._volumePlotResult && Array.isArray(window._volumePlotResult.volumes))
    ? window._volumePlotResult.volumes
    : null;
  if (!Array.isArray(volEvents) || volEvents.length === 0) {
    try {
      const rows = await NovelAPI.listTasks(
        window.currentWorkId,
        NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE,
        'id',
        true,  // id 降序：最新优先，去重时能更简单地保留最新
      );
      if (Array.isArray(rows) && rows.length > 0) {
        // 按 volume_index 去重：同 sort_order 只保留 id 最大（最新）那条；
        // 空卷（plot/summary 都为空）也必须保留，因为用户手动添加过并保存了占位任务。
        const dedupMap = {};
        for (let i = 0; i < rows.length; i++) {
          const parsed = _chapParseVolumeRow(rows[i]);
          if (Array.isArray(parsed)) {
            const p = parsed[0] || { plot: '', summary: '' };
            const volIdx = rows[i].volume_index ?? rows[i].sort_order ?? i;
            const numericIdx = typeof volIdx === 'number' ? volIdx : Number(volIdx) || 0;
            const rowId = Number(rows[i].id) || 0;
            const existing = dedupMap[numericIdx];
            if (!existing || rowId > existing.rowId) {
              dedupMap[numericIdx] = { rowId, parsed: p };
            }
          }
        }
        const allVols = [];
        const sortedKeys = Object.keys(dedupMap).sort((a, b) => Number(a) - Number(b));
        for (const k of sortedKeys) {
          allVols.push(dedupMap[k].parsed);
        }
        if (allVols.length > 0) {
          volEvents = allVols;
          if (!window._volumePlotResult) window._volumePlotResult = {};
          window._volumePlotResult.volumes = allVols;
        }
      }
    } catch (_e) {
      console.warn('[initChapterPage] fetch volume tasks failed:', _e?.message || _e);
    }
  }

  await _chapLoadHistoryTasks();

  renderChapterVolumes();
  refreshChapterStepActions();
}

/* ============== 生成本卷章纲剧情（调用 chapter_plot_design 能力） ============== */
async function generateChapterPlotDesign(volIdx) {
  if (!window.currentWorkId) {
    showStatus('请先在左侧选择一个作品', 'error');
    return;
  }
  const vi = Number(volIdx);
  if (!Number.isInteger(vi) || vi < 0) {
    showStatus('卷序号无效', 'error');
    return;
  }
  const volumes = (window._volumePlotResult && Array.isArray(window._volumePlotResult.volumes))
    ? window._volumePlotResult.volumes
    : [];
  if (!Array.isArray(volumes) || vi >= volumes.length) {
    showStatus('请先在「分卷」页面生成并保存卷纲剧情后，再生成章纲', 'error');
    return;
  }
  const volMeta = volumes[vi] || {};
  const volumePlotText = (typeof volMeta.plot === 'string' && volMeta.plot.trim())
    ? volMeta.plot.trim()
    : '';
  if (!volumePlotText) {
    showStatus(`第 ${vi + 1} 卷卷纲内容为空，请先在分卷页面完善卷纲后再生成章纲`, 'error');
    return;
  }

  // 锁与 SSE 竞态由 NovelAPI.runCapabilityWithSSE 统一处理。
  // chapter_plot_design 属卷维度能力（按 volume_index 唯一），lockKey 按卷隔离防止并发生成同卷。
  const CAP_ID = NovelAPI.CONST.TASK_TYPE_CHAPTER_OUTLINE;
  const lockKey = `chapter_${String(vi)}`;

  // 判断该卷是否已有章纲结果：有则弹确认框，避免误点直接覆盖
  const volState = _chapEnsureVolume(vi);
  const savedChapters = Array.isArray(volState.chapters)
    ? volState.chapters.filter(e => e && (typeof e.plot === 'string' || typeof e.summary === 'string'))
    : [];
  const volumeCardsEl = document.getElementById('chapterVolumeCards');
  const volWrap = volumeCardsEl ? volumeCardsEl.querySelector(`.chapter-volume-wrap[data-vol-idx="${String(vi)}"]`) : null;
  const cardsContainer = volWrap ? volWrap.querySelector('.chapter-volume-body > div:last-child') : null;
  let hasDomReal = false;
  if (cardsContainer && cardsContainer.children && cardsContainer.children.length > 0) {
    const first = cardsContainer.children[0];
    const isEmpty = !(first && first.querySelector(':scope > .chapter-card-header'));
    hasDomReal = !isEmpty;
  }
  const hasExisting = savedChapters.length > 0 || hasDomReal;

  const doReal = async (finalVariables) => {
    const genBtn = document.getElementById(`generateChapterBtn_${vi}`);
    if (genBtn) {
      genBtn.disabled = true;
      genBtn.dataset.oriHtml = genBtn.innerHTML;
      genBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 生成中...';
    }
  try {
    showStatus(`正在基于第 ${vi + 1} 卷卷纲生成章纲剧情，请稍候...`, 'info');
    const variables = (finalVariables && typeof finalVariables === 'object')
      ? Object.assign({}, finalVariables)
      : {};
    if (typeof variables.volume_plot_text !== 'string' || !variables.volume_plot_text) {
      variables.volume_plot_text = volumePlotText;
    }
    if (typeof variables.volume_index === 'undefined' || variables.volume_index === null) {
      variables.volume_index = vi;
    }
    // 如果已有章纲，传递上一章剧情作为参考（用于续生成）
    if (savedChapters.length > 0) {
      const lastChapter = savedChapters[savedChapters.length - 1];
      if (lastChapter && typeof lastChapter.plot === 'string' && lastChapter.plot.trim()) {
        variables.previous_chapter = lastChapter.plot.trim();
      } else if (lastChapter && typeof lastChapter.summary === 'string' && lastChapter.summary.trim()) {
        variables.previous_chapter = lastChapter.summary.trim();
      }
    }
    const res = await NovelAPI.runCapabilityWithSSE({
      capabilityId: CAP_ID,
      variables: variables,
      lockKey: lockKey,
      volumeIndex: Number(vi),
    });

    // 冲突：同卷章纲正在生成中（后端幂等检查命中 / 前端锁命中）
    if (res.conflict) {
      showStatus(res.error?.message || '该卷章纲正在生成中，请稍候...', 'warning');
      return;
    }
    // 失败：HTTP 与 SSE 均未拿到成功最终态
    if (!res.ok) {
      const msg = res.error?.message || '生成失败，请稍后重试';
      console.warn('[generateChapterPlotDesign] failed:', msg);
      showStatus(`生成章纲剧情失败：${msg}`, 'error');
      return;
    }

    // needRefetch：HTTP 失败但 SSE 显示成功，从任务表重新加载该卷章纲
    if (res.needRefetch) {
      showStatus('任务已完成，正在加载章纲结果...', 'info');
      try {
        await _chapLoadHistoryTasks();
        renderChapterVolumes();
        refreshChapterStepActions();
        const curVol = _chapEnsureVolume(vi);
        const chaptersCount = Array.isArray(curVol.chapters) ? curVol.chapters.length : 0;
        if (chaptersCount > 0) {
          showStatus(`第 ${vi + 1} 卷章纲剧情生成完成（已从任务表加载 ${chaptersCount} 章）`, 'success');
        } else {
          showStatus('任务已完成但结果为空，请刷新页面查看', 'warning');
        }
      } catch (e) {
        console.warn('[generateChapterPlotDesign] refetch failed:', e?.message || e);
        showStatus('任务已完成，刷新页面查看结果', 'info');
      }
      return;
    }

    const resData = res.result;
    const isOk = !!(
      resData &&
      (
        (typeof resData.ok === 'boolean' && resData.ok === true) ||
        (resData.result && typeof resData.result === 'object') ||
        (Array.isArray(resData.chapter_plot_design)) ||
        (resData.chapter_plot_design && typeof resData.chapter_plot_design === 'object')
      )
    );
    if (!isOk) {
      const msg = resData && resData.detail ? String(resData.detail) : '生成失败，请稍后重试';
      showStatus(`生成章纲剧情失败：${msg}`, 'error');
      return;
    }
    const payload = (resData && resData.result) ? resData.result : (resData || {});
    let chapters = [];
    if (payload && typeof payload === 'object') {
      const cp = payload.chapter_plot_design;
      if (Array.isArray(cp)) {
        chapters = cp;
      } else if (cp && typeof cp === 'object') {
        // 优先检查是否有 chapters 数组
        if (Array.isArray(cp.chapters)) {
          chapters = cp.chapters;
        } else if (typeof cp.plot === 'string' || typeof cp.summary === 'string') {
          // 单章结构 {plot, summary} → 包装为 chapters 数组（与卷纲逻辑一致）
          chapters = [{
            plot: typeof cp.plot === 'string' ? cp.plot : '',
            summary: typeof cp.summary === 'string' ? cp.summary : '',
          }];
        }
      }
      if ((!Array.isArray(chapters) || chapters.length === 0) && Array.isArray(payload.chapters)) {
        chapters = payload.chapters;
      }
    }
    if (!Array.isArray(chapters) || chapters.length === 0) {
      if (resData && Array.isArray(resData.chapters)) chapters = resData.chapters;
    }
    chapters = Array.isArray(chapters) ? chapters.filter(e => e && (typeof e.plot === 'string' || typeof e.summary === 'string')) : [];
    if (chapters.length === 0) {
      showStatus(`模型返回第 ${vi + 1} 卷章纲结果为空，请调整卷纲内容后重试`, 'error');
      return;
    }
    const vol = _chapEnsureVolume(vi);
    // 如果已有章纲，追加新生成的章节（续生成模式），否则直接替换
    if (savedChapters.length > 0) {
      vol.chapters = savedChapters.concat(chapters);
    } else {
      vol.chapters = chapters;
    }
    if (resData && (resData.task_id || resData.task_id === 0)) {
      const s = String(resData.task_id).trim();
      if (s) vol.activeTaskId = s;
    } else if (!vol.activeTaskId) {
      _chapterFindActiveTaskId(vi).catch(err => console.warn('[generateChapterPlotDesign] 找 activeTaskId 失败（不影响展示）:', err?.message || err));
    }
    // 增量更新：不全量重渲，只同步该卷章卡 DOM（保留 body 已填充状态）
    const _rebuildFromCi = savedChapters.length > 0 ? savedChapters.length : vol.chapters.length;
    _chapSyncVolumeCards(vi, _rebuildFromCi);
    refreshChapterStepActions();

    let persistTip = '';
    try {
      // 统一走 doSaveAllChapterOutlines：与删除后重存使用完全同一段代码，
      // 保证"显示章号 = 数组下标 = chapter_index"三者严格对齐；
      // 内部会自动清理 oldCi !== i 的 DB 脏记录（级联删旧位置 + upsert 新位置）。
      await doSaveAllChapterOutlines(vi);
      _flashChapterSaveTip(vi, true, '已保存');
    } catch (_e) {
      console.warn(`[generateChapterPlotDesign vol=${vi}] 保存章纲任务失败（不影响展示）:`, _e?.message || _e);
      persistTip = '（结果未成功写入任务表，请手动保存）';
    }
    const token = (typeof resData.token_cost === 'number') ? resData.token_cost : 0;
    const taskId = resData.task_id ? `（任务ID：${resData.task_id}）` : '';
    const totalChapters = vol.chapters.length;
    const addedCount = savedChapters.length > 0 ? chapters.length : totalChapters;
    const msg = savedChapters.length > 0
      ? `第 ${vi + 1} 卷章纲剧情追加成功${taskId}${persistTip}，新增 ${addedCount} 章，当前共 ${totalChapters} 章，消耗 ${token} tokens`
      : `第 ${vi + 1} 卷章纲剧情生成成功${taskId}${persistTip}，共 ${totalChapters} 章，消耗 ${token} tokens`;
    showStatus(msg, 'success');
  } catch (err) {
    console.error('[生成章纲剧情失败:', err);
    showStatus('生成章纲剧情失败，请稍后重试', 'error');
  } finally {
    if (genBtn) {
      if (genBtn.dataset.oriHtml) genBtn.innerHTML = genBtn.dataset.oriHtml;
      genBtn.disabled = false;
      refreshChapterStepActions();
    }
  }
  };

  window.startGenerateFlowWithPreview({
    hasExisting: hasExisting,
    confirmConfig: hasExisting ? {
      title: '确认继续生成',
      message: `第 ${vi + 1} 卷已有 ${savedChapters.length} 章章纲剧情结果，继续生成将在现有章节后追加新章节，是否继续？`,
      confirmText: '下一步',
      cancelText: '取消',
    } : null,
    previewConfig: {
      sessionId: window.currentWorkId,
      capabilityId: CAP_ID,
      rawVariables: { volume_plot_text: volumePlotText, volume_index: vi },
    },
    previewRequired: true,
    doReal: doReal,
  });
}

/* ============== 下一步：推演 ============== */
function handleChapterNextStep() {
  if (!window.currentWorkId) {
    showStatus('请先在左侧选择一个作品', 'error');
    return;
  }
  const has = _chapHasAnyChapterData();
  if (!has) {
    showStatus('请先点击任意一卷的「生成本卷章纲剧情」或手动添加章节，生成章纲数据后再进入推演', 'error');
    const firstGen = document.querySelector('[id^="generateChapterBtn_"]');
    if (firstGen && typeof firstGen.scrollIntoView === 'function') {
      firstGen.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    return;
  }
  const counts = [];
  const vols = (window._chapterPlotResult && Array.isArray(window._chapterPlotResult.volumes))
    ? window._chapterPlotResult.volumes
    : [];
  for (let i = 0; i < vols.length; i++) {
    const v = vols[i] || {};
    const arr = Array.isArray(v.chapters) ? v.chapters.filter(e => e && (typeof e.plot === 'string' || typeof e.summary === 'string')) : [];
    if (arr.length > 0) counts.push(`第 ${i + 1} 卷 ${arr.length} 章`);
  }
  showStatus(`已完成定章环节（${counts.join(' / ')}），准备进入推演`, 'success');
  if (window.completeStep) {
    completeStep(window.currentWorkId, 4);
  } else if (window.handleStepClick) {
    handleStepClick(window.currentWorkId, 5);
  }
}

window.resetChapterPageIsolatedState = resetChapterPageIsolatedState;
window.initChapterPage = initChapterPage;
// 暴露章纲行解析函数，供推演/成文等下游节点 fallback 拉取章纲任务时复用
window._chapTryParseChapterRow = _chapTryParseChapterRow;
window.refreshChapterStepActions = refreshChapterStepActions;
window.renderChapterVolumes = renderChapterVolumes;
window.toggleChapterVolume = toggleChapterVolume;
window.toggleChapterCard = toggleChapterCard;
window.addChapterCard = addChapterCard;
window.deleteChapterCard = deleteChapterCard;
window.generateChapterPlotDesign = generateChapterPlotDesign;
window.handleChapterNextStep = handleChapterNextStep;
