(function(){
/* ========================================================================
 * 分卷节点：卷纲剧情设计
 *   - 全局剧情从谋篇结果自动同步（只读）
 *   - 调用 volume_plot_design 能力 → 生成单卷卷纲 → 卡片式展示多卷
 * ====================================================================== */

/**
 * 分卷节点作品级隔离重置：切换作品/重入本节点前调用。
 * 清空所有作品级缓存、告警去抖、自动保存定时器与 DOM 残留。
 */
function resetVolumePageIsolatedState() {
  // 1) 跨作品内存缓存：仅清空本节点（分卷）的卷纲结果，不得顺手清空上游谋篇 _globalPlotResult
  //   ——因为分卷、定章、推演、成文等多个节点只读回退都直接复用 _globalPlotResult，
  //     上游缓存由其对应节点的 initXxxPage 进入时负责重置，本节点 reset 只管本节点状态。
  window._volumePlotResult = { volumes: [] };

  // 2) 模块级去抖：超字数通知 + 自动保存定时器
  _volumePlotAlerted = {};
  _volumeSummaryAlerted = {};
  if (_volumeSaveTimer) { clearTimeout(_volumeSaveTimer); _volumeSaveTimer = null; }

  // 3) DOM 残留：卷纲卡片容器清空 + 卷纲结果容器隐藏
  //   ——注意：只读全局剧情显示区（volumeGlobalPlotText / volumeGlobalPlotContent）
  //     其内容在 initVolumePage 中会重新从 _globalPlotResult 或 ensureGlobalPlotLoaded 拉取并渲染，
  //     reset 阶段不要清空，避免出现"进入页面先闪空白等接口"的肉眼可见的空窗。
  const cardsEl = document.getElementById('volumePlotCards');
  if (cardsEl) cardsEl.innerHTML = '';
  const box = document.getElementById('volumePlotResult');
  if (box) box.style.display = 'none';
}

if (!window._volumePlotResult) {
  window._volumePlotResult = { volumes: [] };
}

function _volTryParseOutlineRow(row) {
  let obj = null;
  try { obj = (row && typeof row.content_text === 'string') ? JSON.parse(row.content_text) : null; } catch(e) {}
  return {
    plot: obj && typeof obj.plot === 'string' ? obj.plot.trim() : '',
    summary: obj && typeof obj.summary === 'string' ? obj.summary.trim() : ''
  };
}

function _volTryParseVolumeRow(row) {
  let obj = null;
  try { obj = (row && typeof row.content_text === 'string') ? JSON.parse(row.content_text) : null; } catch(e) {}
  let arr = [];
  // 空 content_text 也视为占位空卷（用户手动添加过卷但未填写任何内容）
  if (!obj) {
    return [{ plot: '', summary: '' }];
  }

  // 处理多种可能的格式：
  // 1. 旧单例格式: {"_v":2, "volumes": [{"plot":"...", "summary":"..."}]}
  // 2. 旧事件列表格式: {"_v":2, "events": [{"event":"...", "summary":"..."}]}
  // 3. 新按卷独立格式: {"_v":2, "plot":"...", "summary":"..."}（plot/summary 可空=占位）
  // 4. 其他可能的包装格式: {"volume_plot_design": {"plot":"..."}} 或 {"result": {"volume_plot_design": {"plot":"..."}}}

  if (Array.isArray(obj.volumes)) {
    arr = obj.volumes;
  } else if (Array.isArray(obj.events)) {
    arr = obj.events.map(function(e) {
      return {
        plot: e && typeof e.plot === 'string' ? e.plot : (e && typeof e.event === 'string' ? e.event : ''),
        summary: e && typeof e.summary === 'string' ? e.summary : ''
      };
    });
  } else if (typeof obj.plot === 'string' || typeof obj.summary === 'string' || Object.prototype.hasOwnProperty.call(obj, 'plot') || Object.prototype.hasOwnProperty.call(obj, 'summary')) {
    // 直接的 plot/summary（空值也合法：占位任务）
    arr = [{ plot: typeof obj.plot === 'string' ? obj.plot : '', summary: typeof obj.summary === 'string' ? obj.summary : '' }];
  } else if (obj.volume_plot_design && typeof obj.volume_plot_design === 'object') {
    // 被包装的格式（空值也合法）
    const inner = obj.volume_plot_design;
    arr = [{
      plot: typeof inner.plot === 'string' ? inner.plot : '',
      summary: typeof inner.summary === 'string' ? inner.summary : ''
    }];
  } else if (obj.result && obj.result.volume_plot_design && typeof obj.result.volume_plot_design === 'object') {
    // 双层包装
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

/* ============== 阈值 fallback + 告警记录（与谋篇完全对齐，SSOT 优先从 window.frontendThresholds 读） ============== */
const _VOLUME_PLOT_MAX_CHARS = 1500;
const _VOLUME_PLOT_HARD_CHARS = 2000;
const _VOLUME_SUMMARY_MAX_CHARS = 200;
const _VOLUME_SUMMARY_HARD_CHARS = 300;
let _volumePlotAlerted = {};    // key = String(index)，是否已经弹过本卷剧情「超建议值」通知（避免每敲一个字都弹）
let _volumeSummaryAlerted = {}; // key = String(index)，是否已经弹过本卷摘要「超建议值」通知（避免每敲一个字都弹）

function _getThVol(key, fallbackValue) {
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

/* ============== 分卷卡片计数刷新（与谋篇 _refreshPlotCounts 逻辑一致，逐张卡片刷新） ============== */
function _refreshVolumeCardCounts(i) {
  const idx = Number(i);
  if (!Number.isInteger(idx) || idx < 0) return;
  const cardsEl = document.getElementById('volumePlotCards');
  if (!cardsEl) return;
  const card = cardsEl.querySelector(`.volume-wrap[data-vol-idx="${idx}"]`);
  if (!card) return;
  const evTa = card.querySelector('textarea');
  const allTa = card.querySelectorAll('textarea');
  const suTa = allTa && allTa.length >= 2 ? allTa[1] : null;
  const plotCountEl = card.querySelector(`[data-volume-count-plot="${idx}"]`);
  const sumCountEl = card.querySelector(`[data-volume-count-summary="${idx}"]`);
  const PLOT_MAX = _getThVol('volume_plot_chars', _VOLUME_PLOT_MAX_CHARS);
  const SUM_MAX = _getThVol('volume_summary_chars', _VOLUME_SUMMARY_MAX_CHARS);
  const PLOT_HARD = _getThVol('volume_plot_hard_chars', _VOLUME_PLOT_HARD_CHARS);
  const SUM_HARD = _getThVol('volume_summary_hard_chars', _VOLUME_SUMMARY_HARD_CHARS);
  const setCounter = function(el, cur, max, hard, label, alertMap) {
    if (!el) return;
    el.textContent = `${cur} / ${hard}`;
    el.classList.remove('char-counter--warn', 'char-counter--danger');
    if (cur > hard) {
      el.classList.add('char-counter--danger');
    } else if (cur > max) {
      el.classList.add('char-counter--warn');
      const k = String(idx);
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
  setCounter(plotCountEl, pLen, PLOT_MAX, PLOT_HARD, `第 ${idx + 1} 卷剧情`, _volumePlotAlerted);
  setCounter(sumCountEl, sLen, SUM_MAX, SUM_HARD, `第 ${idx + 1} 卷摘要`, _volumeSummaryAlerted);
}

/* ============== 分卷卡片硬截断工具（与谋篇 _enforceHardMax 逻辑一致） ============== */
function _enforceVolumeHardMax(el, hardMax, label) {
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

/* ============== 自动保存（防抖 500ms，对齐谋篇） ============== */
let _volumeSaveTimer = null;

function _flashVolumeSaveTip(success, customText, targetIndex) {
  const defaultText = success ? '已自动保存' : '保存失败，请稍后重试';
  const text = customText ? String(customText) : defaultText;
  const color = success ? '#7c3aed' : '#dc2626';
  const applyTip = function(tipEl) {
    if (!tipEl) return;
    tipEl.innerText = text;
    tipEl.style.color = color;
    tipEl.style.opacity = '1';
    clearTimeout(tipEl._t);
    tipEl._t = setTimeout(function() { tipEl.style.opacity = '0'; }, 1600);
  };
  if (typeof targetIndex === 'number' && Number.isInteger(targetIndex) && targetIndex >= 0) {
    const cardsEl = document.getElementById('volumePlotCards');
    if (cardsEl) {
      const per = cardsEl.querySelector('.volume-card-save-tip[data-volume-index="' + String(targetIndex) + '"]');
      if (per) { applyTip(per); return; }
    }
  }
  applyTip(document.getElementById('volumePlotSaveTip'));
}

async function _volumeFindActiveTaskId() {
  if (!window.currentWorkId) return null;
  const mem = window._volumePlotResult || {};
  if (mem.activeTaskId) {
    const s = String(mem.activeTaskId).trim();
    if (s) return s;
  }
  try {
    const rows = await NovelAPI.listTasks(
      window.currentWorkId,
      NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE,
      'id',
      true,
    );
    if (!Array.isArray(rows) || rows.length === 0) return null;
    const completed = rows.filter(function(r) { return r && (r.status === 'completed' || r.status === 'success'); });
    // 不回退到 failed/pending 任务：failed 任务可能携带旧内容但状态不正确，
    // pending 任务内容为空，回退会导致后续保存逻辑定位到错误任务。
    const keeper = completed[0] || null;
    if (keeper && (keeper.id || keeper.id === 0)) {
      if (!window._volumePlotResult) window._volumePlotResult = {};
      window._volumePlotResult.activeTaskId = String(keeper.id);
      return String(keeper.id);
    }
    return null;
  } catch (_e) {
    console.warn('[volume-save] _volumeFindActiveTaskId failed:', _e?.message || _e);
    return null;
  }
}

async function doSaveVolumeOutline(force, targetIndex) {
  if (!window.currentWorkId) return;
  const mem = window._volumePlotResult || {};
  const volumes = Array.isArray(mem.volumes) ? mem.volumes.slice() : [];
  // 仅当从未添加过任何卷（volumes 全空）且非强制保存时才跳过；
  // 否则即便全空（如删除最后一卷后），也需将空列表持久化，防止刷新后旧数据复活
  if (volumes.length === 0 && !force) return;
  const globalPlotRef = (window._globalPlotResult && typeof window._globalPlotResult.plot === 'string')
    ? window._globalPlotResult.plot
    : '';
  const globalSummaryRef = (window._globalPlotResult && typeof window._globalPlotResult.summary === 'string')
    ? window._globalPlotResult.summary
    : '';
  try {
    const extra = {};
    if (globalPlotRef) extra.global_plot = globalPlotRef;
    if (globalSummaryRef) extra.global_summary = globalSummaryRef;

    // 统一坐标系：显示卷号(i+1) = 数组下标(i) = 持久 volume_index(i)，三者严格对齐。
    // 遍历每一卷：
    //   - 空卷（plot/summary trim 后都为空）不存入 DB，但若该卷对象上挂载的"旧 volume_index"
    //     与当前 i 不一致（说明发生过位置移动 / 中间删除），仍需清理旧位置的 DB 脏记录；
    //   - 非空卷：若旧 volume_index !== 当前 i（说明之前被删过中间卷导致前移 / init 时压缩过空洞），
    //     先 cascadeDelete 旧 volume_index 对应的 DB 记录，再以新 volume_index=i 执行 upsert，
    //     避免残留重复任务。
    const sessionId = window.currentWorkId;
    const globalTask = sessionId ? (await NovelAPI.fetchLatestCompletedTask(sessionId, NovelAPI.CONST.TASK_TYPE_GLOBAL_OUTLINE)) : null;
    const globalParentId = globalTask ? globalTask.id : null;

    for (let i = 0; i < volumes.length; i++) {
      const vol = volumes[i];
      if (!vol || typeof vol !== 'object') continue;

      const hasContent = (typeof vol.plot === 'string' && vol.plot.trim())
        || (typeof vol.summary === 'string' && vol.summary.trim());

      // oldVi 候选优先级：
      //   1) vol.__oldDbVolumeIndex —— init 时从 DB 加载记录的原始 volume_index（不可枚举属性，
      //      因为加载后我们把内存的 vol.volume_index 压缩成了数组下标 i）
      //   2) vol.volume_index —— 已经是持久化对齐过的正常标识（或新 push 的候选值）
      const dbOld = (vol && typeof vol.__oldDbVolumeIndex === 'number' && Number.isFinite(vol.__oldDbVolumeIndex))
        ? vol.__oldDbVolumeIndex
        : null;
      const curIdx = (typeof vol.volume_index === 'number' && Number.isFinite(vol.volume_index))
        ? vol.volume_index
        : null;
      const oldVi = (dbOld !== null) ? dbOld : curIdx;
      // 如果存在 __oldDbVolumeIndex，说明该卷是"刚从 DB 加载且可能压缩过下标的"，
      // 无论 vol.volume_index 当前是否正好等于 i，都以 __oldDbVolumeIndex 作为旧位置清理。
      const needReindex = (oldVi !== null) && (oldVi !== i);

      // 位置发生过迁移：无论该卷当前是否有内容，先清理旧 volume_index 对应的 DB 记录
      // （有内容时旧记录是脏重复；空内容时它以前可能存过，需要同步删除）
      if (needReindex && sessionId) {
        try {
          const oldRow = await NovelAPI.findTaskBySortOrder(sessionId, NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE, oldVi, globalParentId)
            || await NovelAPI.findTaskBySortOrder(sessionId, NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE, oldVi);
          if (oldRow && oldRow.id) {
            try { await NovelAPI.cascadeDelete(oldRow.id); } catch (_de) { /* ignore */ }
          }
        } catch (_fe) { /* ignore */ }
      }

      if (!hasContent) continue;
      await NovelAPI.createVolumeOutline(window.currentWorkId, i, [vol], extra);
      vol.volume_index = i;
    }

    // 清除旧的 activeTaskId，因为现在不再使用单任务模式
    if (window._volumePlotResult.activeTaskId) {
      delete window._volumePlotResult.activeTaskId;
    }

    _flashVolumeSaveTip(true, undefined, targetIndex);
  } catch (err) {
    console.warn('[volume-save] auto save failed:', err?.message || err);
    _flashVolumeSaveTip(false, undefined, targetIndex);
  }
}

function scheduleVolumeAutoSave(immediate, targetIndex) {
  if (!window.currentWorkId) return;
  clearTimeout(_volumeSaveTimer);
  const hasIndex = typeof targetIndex === 'number' && Number.isInteger(targetIndex) && targetIndex >= 0;
  if (immediate) {
    void doSaveVolumeOutline(true, hasIndex ? targetIndex : undefined);
    return;
  }
  _volumeSaveTimer = setTimeout(function() {
    void doSaveVolumeOutline(false, hasIndex ? targetIndex : undefined);
  }, 500);
}

/* ============== 添加 / 删除 单卷 ============== */
function addVolumeCard() {
  if (!window._volumePlotResult) window._volumePlotResult = { volumes: [] };
  if (!Array.isArray(window._volumePlotResult.volumes)) window._volumePlotResult.volumes = [];
  // 统一坐标系：新增卷插在末尾 → 数组下标 len-1 = 持久 volume_index = 显示卷号(len-1)+1-1
  // 这里只给 volume_index 赋一个"候选值"；真正落库时 doSave 会以数组下标 i 为准，
  // 并自动清理/迁移旧位置的 DB 记录，保证三者永远对齐。
  const newVi = window._volumePlotResult.volumes.length;
  window._volumePlotResult.volumes.push({ plot: '', summary: '', volume_index: newVi });
  const box = document.getElementById('volumePlotResult');
  if (box) box.style.display = 'block';
  renderVolumeCards(window._volumePlotResult.volumes);
  refreshVolumeStepActions();
  scheduleVolumeAutoSave(false);
}

function deleteVolumeCard(idx) {
  if (!window._volumePlotResult || !Array.isArray(window._volumePlotResult.volumes)) return;
  const n = Number(idx);
  if (!Number.isInteger(n) || n < 0 || n >= window._volumePlotResult.volumes.length) return;

  const sessionId = window.currentWorkId;
  if (!sessionId || typeof NovelAPI === 'undefined' || !NovelAPI.findTaskBySortOrder) {
    showStatus('删除功能暂不可用，请刷新页面后重试', 'error');
    return;
  }

  // 删除时优先使用该卷自带的持久化 volume_index（= DB 中任务的 sort_order），
  // 只有当卷是手动新增、尚未保存时才 fallback 到数组下标，
  // 这样避免"用户删过中间卷导致数组下标与持久化 sort_order 错位 → 查不到任务"。
  const curVol = window._volumePlotResult.volumes[n] || {};
  const curSortOrder = (typeof curVol.volume_index === 'number' && Number.isFinite(curVol.volume_index))
    ? curVol.volume_index
    : n;

  // 必须先拿到 global outline 的 id 作为 parentId，再查 volume outline，
  // 避免重复记录时 findTaskBySortOrder 找到错误（非本子树）的卷任务 → 级联删错数据。
  NovelAPI.fetchLatestCompletedTask(sessionId, NovelAPI.CONST.TASK_TYPE_GLOBAL_OUTLINE).then(globalTask => {
    const globalParentId = globalTask ? globalTask.id : null;
    return NovelAPI.findTaskBySortOrder(sessionId, NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE, curSortOrder, globalParentId);
  }).then(task => {
    if (!task || !task.id) {
      // 兜底：如果按自带 volume_index + parentId 找不到任务，尝试不传 parentId 再查一次（兼容老数据 parent_id 为空的情况）
      return NovelAPI.findTaskBySortOrder(sessionId, NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE, curSortOrder);
    }
    return task;
  }).then(task => {
    if (!task || !task.id) {
      // 再兜底：尝试数组下标
      if (curSortOrder !== n) {
        return NovelAPI.findTaskBySortOrder(sessionId, NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE, n);
      }
      showStatus('未找到该卷的任务记录，无法删除', 'error');
      return null;
    }
    return NovelAPI.cascadeDelete(task.id);
  }).then(async function(res) {
    if (res === null) return;
    if (res && res.ok) {
      showStatus(`第 ${n + 1} 卷及其下属数据已删除，正在同步剩余卷号...`, 'success');
      // 1. 从内存中移除该卷（数组下标前移，剩余卷的下标变成新的正确位置）
      window._volumePlotResult.volumes.splice(n, 1);
      renderVolumeCards(window._volumePlotResult.volumes);
      refreshVolumeStepActions();
      // 2. 立即全量保存：
      //    - 剩余卷的旧 volume_index（可能大于当前下标 i）会被 doSave 里 needReindex 分支
      //      级联删除 DB 旧位置的脏记录，并 upsert 到新位置 i；
      //    - 显示卷号 i+1、数组下标 i、持久 volume_index=i 三者严格对齐。
      try { await doSaveVolumeOutline(true); } catch (_se) { /* ignore */ }
    } else {
      showStatus('删除失败，请重试', 'error');
    }
  }).catch(err => {
    console.error('删除卷失败：', err);
    showStatus('删除失败，请检查网络连接', 'error');
  });
}

/* ============== 单卷折叠 / 展开 切换（自然呼吸感动画：max-height + opacity + translateY） ============== */
function toggleVolumeCard(idx) {
  if (!window._volumePlotResult || !Array.isArray(window._volumePlotResult.volumes)) return;
  const n = Number(idx);
  if (!Number.isInteger(n) || n < 0 || n >= window._volumePlotResult.volumes.length) return;
  const cur = window._volumePlotResult.volumes[n] || {};
  cur.collapsed = !cur.collapsed;
  window._volumePlotResult.volumes[n] = cur;
  const cardsEl = document.getElementById('volumePlotCards');
  if (!cardsEl) return;
  const volWrap = cardsEl.querySelector(`.volume-wrap[data-vol-idx="${n}"]`);
  if (!volWrap) return;
  const header = volWrap.querySelector(':scope > .volume-header');
  const body = volWrap.querySelector(':scope > .volume-body');
  const icon = volWrap.querySelector('.volume-toggle-icon');
  if (!body || !header) return;
  const collapsed = !!cur.collapsed;
  if (collapsed) {
    body.style.overflow = 'hidden';
    body.style.maxHeight = body.scrollHeight + 'px';
    body.style.opacity = '1';
    body.style.transform = 'translateY(0)';
    requestAnimationFrame(function() {
      body.style.transition = 'max-height 0.35s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease 0.02s, transform 0.3s ease 0.02s';
      body.style.maxHeight = '0px';
      body.style.opacity = '0';
      body.style.transform = 'translateY(-4px)';
    });
    setTimeout(function() {
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
    header.style.padding = '13px 20px';
    header.style.background = 'linear-gradient(90deg, rgba(139, 92, 246, 0.08), rgba(139, 92, 246, 0.02))';
  } else {
    body.style.display = 'block';
    body.style.overflow = 'hidden';
    body.style.opacity = '0';
    body.style.transform = 'translateY(-4px)';
    const fullHeight = body.scrollHeight;
    body.style.maxHeight = '0px';
    requestAnimationFrame(function() {
      body.style.transition = 'max-height 0.4s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.35s ease 0.05s, transform 0.35s ease 0.05s';
      body.style.maxHeight = fullHeight + 40 + 'px';
      body.style.opacity = '1';
      body.style.transform = 'translateY(0)';
    });
    setTimeout(function() {
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
    header.style.padding = '16px 20px';
    header.style.background = 'linear-gradient(90deg, rgba(139, 92, 246, 0.1), rgba(139, 92, 246, 0.03))';
  }
}

/* ============== 渲染单卷卡片（谋篇同款可编辑 textarea） ============== */
function renderVolumeCards(volumes) {
  (function _volRaiseZ() {
    try {
      const ids = ['volumeArea', 'volumePlotResult', 'volumePlotCards'];
      for (let i = 0; i < ids.length; i++) {
        const el = document.getElementById(ids[i]);
        if (!el) continue;
        const cur = el.getAttribute('style') || '';
        const cleaned = String(cur).replace(/position\s*:\s*[^;]*;?/gi, '').replace(/z-index\s*:\s*[^;]*;?/gi, '');
        el.setAttribute('style', (cleaned + '; position: relative; z-index: ' + (998 + i) + ';').replace(/;;/g, ';'));
      }
    } catch (_e) {}
  })();

  const cardsEl = document.getElementById('volumePlotCards');
  const box = document.getElementById('volumePlotResult');
  if (!cardsEl) return;
  cardsEl.innerHTML = '';
  const arr = Array.isArray(volumes) ? volumes.filter(function(v) {
    return v && (typeof v.plot === 'string' || typeof v.summary === 'string');
  }) : [];
  if (!window._volumePlotResult) window._volumePlotResult = { volumes: [] };
  if (!Array.isArray(window._volumePlotResult.volumes)) window._volumePlotResult.volumes = [];
  if (window._volumePlotResult.volumes !== volumes) {
    if (arr.length > 0) window._volumePlotResult.volumes = arr.slice();
  }
  if (arr.length === 0) {
    if (box) {
      box.style.display = 'block';
    }
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
    empty.innerHTML = '暂无卷纲内容。点击「生成卷纲剧情」生成新卷，或点击右上角「添加卷」手动新增一卷。';
    cardsEl.appendChild(empty);
    return;
  }
  if (box) box.style.display = 'block';

  const metaLine = document.createElement('div');
  metaLine.style.cssText = [
    'padding: 14px 0 12px',
    'font-size: 16px', 'color: #5b21b6',
    'display: inline-flex', 'align-items: center', 'gap: 8px',
    'opacity: 0.85',
  ].join(';');
  metaLine.innerHTML = `<i class="fas fa-info-circle"></i><span>本作品共 ${arr.length} 卷，以下卡片每张对应一卷：卷纲可编辑。`;
  cardsEl.appendChild(metaLine);

  for (let i = 0; i < arr.length; i++) {
    const item = arr[i] || {};
    const plot = typeof item.plot === 'string' ? item.plot : '';
    const summary = typeof item.summary === 'string' ? item.summary : '';
    if (!window._volumePlotResult.volumes[i]) window._volumePlotResult.volumes[i] = {};
    const collapsed = !!window._volumePlotResult.volumes[i].collapsed;

    const volWrap = document.createElement('div');
    volWrap.className = 'volume-wrap';
    volWrap.setAttribute('data-vol-idx', String(i));
    volWrap.style.cssText = [
      'border: 1px solid #e0d2fc',
      'border-radius: 12px',
      'background: rgba(255, 255, 255, 0.85)',
      'overflow: hidden',
      'position: relative',
      'transition: box-shadow 0.25s ease, border-color 0.25s ease',
      'margin-bottom: 16px',
      'box-sizing: border-box',
    ].join(';');
    volWrap.addEventListener('mouseenter', function() {
      volWrap.style.boxShadow = '0 6px 18px rgba(139, 92, 246, 0.08)';
      volWrap.style.borderColor = 'rgba(139, 92, 246, 0.25)';
    });
    volWrap.addEventListener('mouseleave', function() {
      volWrap.style.boxShadow = '';
      volWrap.style.borderColor = '#e0d2fc';
    });

    // ---- header：整行可点击切换折叠，左切换箭头+徽章+摘要，右操作按钮（stopPropagation） ----
    const header = document.createElement('div');
    header.className = 'volume-header';
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
    header.addEventListener('mouseenter', function() {
      const now = !!window._volumePlotResult.volumes[i]?.collapsed;
      header.style.background = now
        ? 'linear-gradient(90deg, rgba(139, 92, 246, 0.13), rgba(139, 92, 246, 0.05))'
        : 'linear-gradient(90deg, rgba(139, 92, 246, 0.15), rgba(139, 92, 246, 0.06))';
    });
    header.addEventListener('mouseleave', function() {
      const now = !!window._volumePlotResult.volumes[i]?.collapsed;
      header.style.background = now
        ? 'linear-gradient(90deg, rgba(139, 92, 246, 0.08), rgba(139, 92, 246, 0.02))'
        : 'linear-gradient(90deg, rgba(139, 92, 246, 0.1), rgba(139, 92, 246, 0.03))';
    });
    header.onclick = function() { toggleVolumeCard(i); };

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
    toggleIcon.className = 'volume-toggle-icon fas ' + (collapsed ? 'fa-chevron-down' : 'fa-chevron-up');
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
    badge.textContent = `第 ${i + 1} 卷`;
    headerLeft.appendChild(badge);

    const sumRaw = summary && summary.trim() ? summary.trim() : '';
    const plotRaw = plot && plot.trim() ? plot.trim() : '';
    const fallbackText = (function() {
      if (sumRaw) return sumRaw;
      if (plotRaw) return plotRaw.length > 80 ? plotRaw.slice(0, 80) + '…' : plotRaw;
      const n1 = (plot || '').length;
      const n2 = (summary || '').length;
      return `剧情 ${n1} 字 / 摘要 ${n2} 字`;
    })();
    if (fallbackText) {
      const sumEl = document.createElement('div');
      sumEl.style.cssText = [
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
        'max-width: 600px',
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
    headerRight.onclick = function(ev) {
      if (ev) ev.stopPropagation && ev.stopPropagation();
    };

    // ---- 右上角：单卡片保存提示（删除按钮左侧） ----
    const cardTip = document.createElement('span');
    cardTip.className = 'volume-card-save-tip';
    cardTip.setAttribute('data-volume-index', String(i));
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

    // ---- 右上角：删除本卷按钮 ----
    const delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.setAttribute('aria-label', '删除本卷');
    delBtn.innerHTML = '<i class="fas fa-trash-alt"></i>';
    delBtn.title = '删除第 ' + (i + 1) + ' 卷';
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
    delBtn.addEventListener('mouseenter', function() {
      delBtn.style.background = 'rgba(231, 76, 60, 0.12)';
      delBtn.style.color = '#e74c3c';
      delBtn.style.transform = 'scale(1.08)';
    });
    delBtn.addEventListener('mouseleave', function() {
      delBtn.style.background = 'none';
      delBtn.style.color = '#999';
      delBtn.style.transform = 'scale(1)';
    });
    delBtn.addEventListener('mousedown', function() { delBtn.style.transform = 'scale(0.96)'; });
    delBtn.addEventListener('mouseup', function() { delBtn.style.transform = 'scale(1.08)'; });
    delBtn.addEventListener('click', function(ev) {
      ev && ev.preventDefault && ev.preventDefault();
      window.showConfirm({
        title: '确认删除分卷',
        message: `即将删除第 ${i + 1} 卷。<br><br>此操作将 <b>级联删除</b> 该卷下的：<b>所有章节章纲、章节事件链、章节正文</b>，以及与这些任务关联的多媒体记录与文件。<br><br><b>此操作不可恢复！</b>`,
        confirmText: '确认级联删除',
        confirmBtnStyle: 'danger',
        cancelText: '取消',
        onConfirm: function() {
          deleteVolumeCard(i);
        },
      });
    });
    headerRight.appendChild(delBtn);

    header.appendChild(headerRight);
    volWrap.appendChild(header);

    // ---- body：剧情+摘要两个 textarea，折叠时隐藏 ----
    const body = document.createElement('div');
    body.className = 'volume-body';
    body.style.cssText = [
      'padding: 22px 22px 20px',
      'border-top: 1px solid #eee',
      'background: rgba(255, 255, 255, 0.85)',
      'display: ' + (collapsed ? 'none' : 'block'),
      'box-sizing: border-box',
    ].join(';');

    // --- 卷纲剧情 textarea ---
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
    const PLOT_MAX_LABEL = _getThVol('volume_plot_chars', _VOLUME_PLOT_MAX_CHARS);
    evLabel.innerHTML = `<span>剧情（建议 ${PLOT_MAX_LABEL} 字内，最大 ${_getThVol('volume_plot_hard_chars', _VOLUME_PLOT_HARD_CHARS)} 字）</span>`;
    const evTa = document.createElement('textarea');
    evTa.rows = 8;
    evTa.placeholder = '填写本卷主剧情、核心冲突、关键转折…修改后失焦自动保存';
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
    evCount.setAttribute('data-volume-count-plot', String(i));
    evCount.style.cssText = [
      'pointer-events: auto',
      'margin: 0',
      'padding: 0',
      'position: static',
      'transform: none',
    ].join(';');
    evCount.textContent = `${(plot || '').length} / ${_getThVol('volume_plot_hard_chars', _VOLUME_PLOT_HARD_CHARS)}`;
    evLabel.appendChild(evCount);
    const PLOT_HARD_I = _getThVol('volume_plot_hard_chars', _VOLUME_PLOT_HARD_CHARS);
    const SUM_HARD_I = _getThVol('volume_summary_hard_chars', _VOLUME_SUMMARY_HARD_CHARS);
    const applyHardLimitsI = function() {
      const changedPlot = _enforceVolumeHardMax(evTa, PLOT_HARD_I, `第 ${i + 1} 卷剧情`);
      const changedSum = _enforceVolumeHardMax(suTa, SUM_HARD_I, `第 ${i + 1} 卷摘要`);
      if (changedPlot || changedSum) {
        if (!window._volumePlotResult) window._volumePlotResult = { volumes: [] };
        if (!Array.isArray(window._volumePlotResult.volumes)) window._volumePlotResult.volumes = [];
        while (window._volumePlotResult.volumes.length <= i) window._volumePlotResult.volumes.push({ plot: '', summary: '' });
        const cur = window._volumePlotResult.volumes[i] || {};
        cur.plot = typeof evTa.value === 'string' ? evTa.value : '';
        cur.summary = typeof suTa.value === 'string' ? suTa.value : '';
        window._volumePlotResult.volumes[i] = cur;
      }
      _refreshVolumeCardCounts(i);
      return changedPlot || changedSum;
    };
    evTa.addEventListener('focus', function() {
      evTa.style.borderColor = '#8b5cf6';
      evTa.style.boxShadow = '0 0 0 3px rgba(139, 92, 246, 0.12)';
    });
    evTa.addEventListener('blur', function() {
      evTa.style.borderColor = '#e0d2fc';
      evTa.style.boxShadow = 'none';
      applyHardLimitsI();
      scheduleVolumeAutoSave(true, i);
    });
    evTa.addEventListener('input', function() {
      applyHardLimitsI();
      if (!window._volumePlotResult) window._volumePlotResult = { volumes: [] };
      if (!Array.isArray(window._volumePlotResult.volumes)) window._volumePlotResult.volumes = [];
      while (window._volumePlotResult.volumes.length <= i) window._volumePlotResult.volumes.push({ plot: '', summary: '' });
      const cur = window._volumePlotResult.volumes[i] || {};
      cur.plot = typeof evTa.value === 'string' ? evTa.value : '';
      window._volumePlotResult.volumes[i] = cur;
      scheduleVolumeAutoSave(false, i);
    });
    evTa.addEventListener('paste', function() { setTimeout(function() { applyHardLimitsI(); }, 0); });
    evWrap.appendChild(evLabel);
    evWrap.appendChild(evTa);
    body.appendChild(evWrap);

    // --- 摘要 textarea ---
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
      'margin-bottom: 6px',
      'display: flex',
      'align-items: center',
      'justify-content: space-between',
      'pointer-events: auto',
    ].join(';');
    const SUM_MAX_LABEL = _getThVol('volume_summary_chars', _VOLUME_SUMMARY_MAX_CHARS);
    suLabel.innerHTML = `<span>摘要（建议 ${SUM_MAX_LABEL} 字内，最大 ${_getThVol('volume_summary_hard_chars', _VOLUME_SUMMARY_HARD_CHARS)} 字）</span>`;
    const suTa = document.createElement('textarea');
    suTa.rows = 3;
    suTa.placeholder = '一句话概括本卷核心走向（用于总览/下阶段入口提示）';
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
    suCount.setAttribute('data-volume-count-summary', String(i));
    suCount.style.cssText = [
      'pointer-events: auto',
      'margin: 0',
      'padding: 0',
      'position: static',
      'transform: none',
    ].join(';');
    suCount.textContent = `${(summary || '').length} / ${_getThVol('volume_summary_hard_chars', _VOLUME_SUMMARY_HARD_CHARS)}`;
    suLabel.appendChild(suCount);
    suTaBox.appendChild(suTa);
    suTa.addEventListener('focus', function() {
      suTa.style.borderColor = '#8b5cf6';
      suTa.style.boxShadow = '0 0 0 3px rgba(139, 92, 246, 0.12)';
    });
    suTa.addEventListener('blur', function() {
      suTa.style.borderColor = 'rgba(139, 92, 246, 0.15)';
      suTa.style.boxShadow = 'none';
      applyHardLimitsI();
      scheduleVolumeAutoSave(true, i);
    });
    suTa.addEventListener('input', function() {
      applyHardLimitsI();
      if (!window._volumePlotResult) window._volumePlotResult = { volumes: [] };
      if (!Array.isArray(window._volumePlotResult.volumes)) window._volumePlotResult.volumes = [];
      while (window._volumePlotResult.volumes.length <= i) window._volumePlotResult.volumes.push({ plot: '', summary: '' });
      const cur = window._volumePlotResult.volumes[i] || {};
      cur.summary = typeof suTa.value === 'string' ? suTa.value : '';
      window._volumePlotResult.volumes[i] = cur;
      scheduleVolumeAutoSave(false, i);
    });
    suTa.addEventListener('paste', function() { setTimeout(function() { applyHardLimitsI(); }, 0); });
    suWrap.appendChild(suLabel);
    suWrap.appendChild(suTaBox);
    body.appendChild(suWrap);

    volWrap.appendChild(body);
    cardsEl.appendChild(volWrap);
    try { applyHardLimitsI(); } catch (_e) {}
  }
}

function refreshVolumeStepActions() {
  const genBtn = document.getElementById('generateVolumeBtn');
  const nextBtn = document.getElementById('nextStepBtnVolume');
  const plotEl = document.getElementById('volumeGlobalPlotText');

  const plot = plotEl && typeof plotEl.value === 'string' ? plotEl.value.trim() : '';
  const memPlot = (window._globalPlotResult && typeof window._globalPlotResult.plot === 'string')
    ? window._globalPlotResult.plot.trim()
    : '';
  const hasPlot = (plot.length > 0) || (memPlot.length > 0);

  if (genBtn) {
    if (!window.currentWorkId) {
      genBtn.disabled = true;
      genBtn.title = '请先在左侧选择一个作品';
    } else if (!hasPlot) {
      genBtn.disabled = true;
      genBtn.title = '请先在「谋篇」页面生成并保存全局剧情后，再进入本分卷页面生成卷纲';
    } else {
      genBtn.disabled = false;
      genBtn.title = '基于已同步的全局剧情，生成新一卷卷纲';
    }
  }

  const volumes = (window._volumePlotResult && Array.isArray(window._volumePlotResult.volumes))
    ? window._volumePlotResult.volumes.filter(function(v) { return v && (typeof v.plot === 'string' || typeof v.summary === 'string'); })
    : [];
  if (nextBtn) {
    if (!window.currentWorkId) {
      nextBtn.disabled = true;
      nextBtn.title = '请先在左侧选择一个作品';
    } else if (volumes.length === 0) {
      nextBtn.disabled = true;
      nextBtn.title = '请先点击「生成卷纲剧情」并等待生成完成后，再进入定章';
    } else {
      nextBtn.disabled = false;
      nextBtn.title = '进入定章环节：基于每一卷卷纲逐卷拆分章节级事件流';
    }
  }
}

async function initVolumePage() {
  // 【作品级隔离 SOP】切作品进入分卷节点时，先清空所有作品级单例/DOM，再拉数据/渲染
  resetVolumePageIsolatedState();
  const plotEl = document.getElementById('volumeGlobalPlotText');
  const cardsEl = document.getElementById('volumePlotCards');
  const box = document.getElementById('volumePlotResult');

  if (!window.currentWorkId) {
    if (plotEl) plotEl.value = '';
    if (cardsEl) cardsEl.innerHTML = '';
    if (box) box.style.display = 'none';
    refreshVolumeStepActions();
    return;
  }

  let plot = '';
  let summary = '';
  if (window._globalPlotResult) {
    plot = (typeof window._globalPlotResult.plot === 'string') ? window._globalPlotResult.plot.trim() : '';
    summary = (typeof window._globalPlotResult.summary === 'string') ? window._globalPlotResult.summary.trim() : '';
  }
  if (!plot) {
    try {
      const row = await NovelAPI.fetchLatestCompletedTask(
        window.currentWorkId,
        NovelAPI.CONST.TASK_TYPE_GLOBAL_OUTLINE,
      );
      const parsed = _volTryParseOutlineRow(row);
      plot = parsed.plot;
      summary = parsed.summary;
      if (!window._globalPlotResult) window._globalPlotResult = {};
      if (plot) window._globalPlotResult.plot = plot;
      if (summary) window._globalPlotResult.summary = summary;
    } catch (_e) {
      console.warn('[initVolumePage] fetch global outline failed:', _e?.message || _e);
    }
  }
  if (plotEl) {
    plotEl.value = plot || '';
    if (summary && plotEl.dataset && !plotEl.dataset.summary) {
      plotEl.dataset.summary = summary;
    }
  }
  (function _volRefreshGlobalDisplay() {
    try {
      const plotContent = document.getElementById('volumeGlobalPlotContent');
      const summaryContent = document.getElementById('volumeGlobalSummaryContent');
      const countEl = document.getElementById('volumeGlobalPlotCount');
      const p = (typeof plot === 'string') ? plot.trim() : '';
      const s = (typeof summary === 'string') ? summary.trim() : '';
      if (plotContent) plotContent.textContent = p
        || '当前尚未生成全局剧情，请先在「谋篇」页面生成并保存全局剧情后，再进入本分卷页面。';
      if (summaryContent) {
        if (s) {
          summaryContent.style.display = 'block';
          summaryContent.textContent = '\u3010摘要\u3011' + s;
        } else {
          summaryContent.style.display = 'none';
        }
      }
      if (countEl) countEl.textContent = `剧情 ${p.length} 字 / 摘要 ${s.length} 字`;
    } catch (_e) {}
  })();

  let volumes = (window._volumePlotResult && Array.isArray(window._volumePlotResult.volumes))
    ? window._volumePlotResult.volumes
    : [];
  // 默认折叠策略（懒展开：首屏最小必要单元，后续用户手动展开，DOM 与渲染开销最低）
  //   仅第 0 卷展开，其余卷默认折叠；分卷页无"章"粒度
  if (Array.isArray(volumes) && volumes.length > 0) {
    for (let i = 0; i < volumes.length; i++) {
      if (!volumes[i] || typeof volumes[i] !== 'object') continue;
      volumes[i].collapsed = (i !== 0);
    }
  }
  if (!Array.isArray(volumes) || volumes.length === 0) {
    try {
      // 获取所有 volume_outline 任务，按 sort_order 排序（卷索引）
      const rows = await NovelAPI.listTasks(
        window.currentWorkId,
        NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE,
        'id',
        true,  // id 降序=最新优先
      );
      if (Array.isArray(rows) && rows.length > 0) {
        // 按 volume_index 去重：同一 sort_order 可能因 parent_id 变化（谋篇重新生成）导致 upsert 键不同而残留旧任务，
        // 只保留同 volume_index 中 id 最大的（最新写入）那条；空卷（plot/summary 都为空）也必须保留，因为用户手动添加过。
        const dedupMap = {};
        for (let i = 0; i < rows.length; i++) {
          const parsed = _volTryParseVolumeRow(rows[i]);
          if (Array.isArray(parsed)) {
            const p = parsed[0] || { plot: '', summary: '' };
            const volIdx = rows[i].volume_index ?? rows[i].sort_order ?? i;
            const numericIdx = typeof volIdx === 'number' ? volIdx : Number(volIdx) || 0;
            const rowId = Number(rows[i].id) || 0;
            const existing = dedupMap[numericIdx];
            if (!existing || rowId > existing.rowId) {
              dedupMap[numericIdx] = {
                rowId: rowId,
                parsed: p,
              };
            }
          }
        }
        const sortedKeys = Object.keys(dedupMap).sort((a, b) => Number(a) - Number(b));
        // 统一坐标系：加载后把 volume_index "压缩"为连续的 0..N-1（=数组下标 i）。
        // 这一步只在内存改，不写 DB——写 DB 由后续保存/生成/删除动作触发 doSaveVolumeOutline，
        // 内部会把 oldVi（这里是 DB 里的原始 k）!= i 的记录级联删除后再 upsert 到新位置，
        // 保证"显示卷号 = 数组下标 = volume_index"三者严格对齐。
        const allVolumes = [];
        for (let i = 0; i < sortedKeys.length; i++) {
          const k = sortedKeys[i];
          const entry = dedupMap[k];
          allVolumes.push({
            ...entry.parsed,
            // 记录 oldVi：下次 doSave 时会检测到 oldVi !== i 并自动清理 DB 旧位置记录
            volume_index: i,
          });
          if (entry.parsed && typeof entry.parsed === 'object') {
            // 在对象上暂存原始 DB volume_index（不可枚举，仅用于 doSave 迁移判断）
            Object.defineProperty(entry.parsed, '__oldDbVolumeIndex', {
              value: Number(k), writable: true, enumerable: false, configurable: true,
            });
          }
        }
        if (allVolumes.length > 0) {
          volumes = allVolumes;

          // 默认折叠策略：仅第 0 卷展开，其余卷折叠（懒展开首屏最小必要单元）
          for (let i = 0; i < volumes.length; i++) {
            if (!volumes[i] || typeof volumes[i] !== 'object') continue;
            volumes[i].collapsed = (i !== 0);
          }

          if (!window._volumePlotResult) window._volumePlotResult = {};
          window._volumePlotResult.volumes = volumes;
          // 不再设置 activeTaskId，因为现在有多个任务
        }
      }
    } catch (_e) {
      console.warn('[initVolumePage] fetch volume tasks failed:', _e?.message || _e);
    }
  }
  renderVolumeCards(volumes);
  refreshVolumeStepActions();
}

async function generateVolumePlotDesign() {
  // 锁与 SSE 竞态由 NovelAPI.runCapabilityWithSSE 统一处理。
  // volume_plot_design 是卷类能力（按 volume_index 唯一），但本页面是"追加新一卷"语义，
  // 新卷的 volume_index 在生成前未确定（依赖已有卷数），故 lockKey 用固定键防止并发追加。
  const CAP_ID = NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE;
  const lockKey = `volume_append_${CAP_ID}`;

  if (!window.currentWorkId) {
    showStatus('请先在左侧选择一个作品', 'error');
    return;
  }
  const plotEl = document.getElementById('volumeGlobalPlotText');
  let plot = (plotEl && typeof plotEl.value === 'string') ? plotEl.value.trim() : '';
  if (!plot && window._globalPlotResult && typeof window._globalPlotResult.plot === 'string') {
    plot = window._globalPlotResult.plot.trim();
  }
  if (!plot) {
    showStatus('请先在「谋篇」页面生成并保存全局剧情后，再进入本分卷页面生成卷纲', 'error');
    if (plotEl) plotEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    return;
  }

  const savedVolumes = Array.isArray(window._volumePlotResult && window._volumePlotResult.volumes)
    ? window._volumePlotResult.volumes.filter(function(v) { return v && (typeof v.plot === 'string' || typeof v.summary === 'string'); })
    : [];
  const volCards = document.getElementById('volumePlotCards');
  const domWraps = volCards ? volCards.querySelectorAll('.volume-wrap') : [];
  const hasDomWraps = !!(domWraps && domWraps.length > 0);
  const hasExisting = savedVolumes.length > 0 || hasDomWraps;

  const doReal = async function(finalVariables) {
    const genBtn = document.getElementById('generateVolumeBtn');
    if (genBtn) {
      genBtn.disabled = true;
      genBtn.dataset.oriHtml = genBtn.innerHTML;
      genBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 生成中...';
    }
  try {
    showStatus('正在基于全局剧情生成新一卷卷纲，请稍候...', 'info');
    const variables = (finalVariables && typeof finalVariables === 'object')
      ? Object.assign({}, finalVariables)
      : {};
    if (typeof variables.global_plot_text !== 'string' || !variables.global_plot_text) {
      variables.global_plot_text = plot;
    }
    const res = await NovelAPI.runCapabilityWithSSE({
      capabilityId: CAP_ID,
      variables: variables,
      lockKey: lockKey,
    });

    if (res.conflict) {
      showStatus(res.error?.message || '卷纲剧情正在生成中，请稍候...', 'warning');
      return;
    }
    if (!res.ok) {
      const msg = res.error?.message || '生成失败，请稍后重试';
      console.warn('[generateVolumePlotDesign] failed:', msg);
      showStatus(`生成卷纲剧情失败：${msg}`, 'error');
      return;
    }

    // needRefetch：HTTP 失败但 SSE 显示成功，从 task 表重新拉取最新一卷
    if (res.needRefetch) {
      showStatus('任务已完成，正在加载卷纲结果...', 'info');
      try {
        const rows = await NovelAPI.listTasks(
          window.currentWorkId,
          NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE,
          'id',
          true,
        );
        let picked = null;
        if (Array.isArray(rows)) {
          for (const r of rows) {
            if (r && String(r.status || '') === 'completed') { picked = r; break; }
          }
        }
        const content = picked && typeof picked.content_text === 'string' ? picked.content_text : '';
        let newPlot = '';
        let newSummary = '';
        if (content) {
          try {
            const obj = JSON.parse(content);
            if (obj && typeof obj === 'object') {
              if (typeof obj.plot === 'string') newPlot = obj.plot;
              if (typeof obj.summary === 'string') newSummary = obj.summary;
            }
          } catch (_) { /* ignore */ }
        }
        if (!newPlot && !newSummary) {
          showStatus('任务已完成但结果为空，请刷新页面查看', 'warning');
          return;
        }
        // 复用下面的截断与追加逻辑
        const PLOT_HARD = _getThVol('volume_plot_hard_chars', _VOLUME_PLOT_HARD_CHARS);
        const SUM_HARD = _getThVol('volume_summary_hard_chars', _VOLUME_SUMMARY_HARD_CHARS);
        const plotFinal = newPlot.length > PLOT_HARD ? newPlot.slice(0, PLOT_HARD) : newPlot;
        const summaryFinal = newSummary.length > SUM_HARD ? newSummary.slice(0, SUM_HARD) : newSummary;
        if (!window._volumePlotResult) window._volumePlotResult = {};
        if (!Array.isArray(window._volumePlotResult.volumes)) window._volumePlotResult.volumes = [];
        window._volumePlotResult.volumes.push({ plot: plotFinal, summary: summaryFinal });
        const newIndex = window._volumePlotResult.volumes.length - 1;
        if (picked && picked.id) {
          window._volumePlotResult.activeTaskId = String(picked.id);
        }
        renderVolumeCards(window._volumePlotResult.volumes);
        refreshVolumeStepActions();
        showStatus(`卷纲剧情生成成功（已从任务表加载第 ${newIndex + 1} 卷）`, 'success');
        return;
      } catch (e) {
        console.warn('[generateVolumePlotDesign] refetch failed:', e?.message || e);
        showStatus('任务已完成，刷新页面查看结果', 'info');
        return;
      }
    }

    const resData = res.result;
    const isOk = !!(
      resData &&
      (
        (typeof resData.ok === 'boolean' && resData.ok === true) ||
        (resData.result && typeof resData.result === 'object') ||
        (resData?.result?.volume_plot_design && typeof resData?.result?.volume_plot_design === 'object') ||
        (resData?.volume_plot_design && typeof resData?.volume_plot_design === 'object')
      )
    );
    if (!isOk) {
      const msg = resData && resData.detail ? String(resData.detail) : '生成失败，请稍后重试';
      showStatus(`生成卷纲剧情失败：${msg}`, 'error');
      return;
    }
    const payload = (resData && resData.result) ? resData.result : (resData || {});
    let newPlot = '';
    let newSummary = '';
    if (payload && typeof payload === 'object') {
      const vp = payload.volume_plot_design;
      if (vp && typeof vp === 'object') {
        newPlot = typeof vp.plot === 'string' ? vp.plot : '';
        newSummary = typeof vp.summary === 'string' ? vp.summary : '';
      }
    }
    if (!newPlot && !newSummary) {
      showStatus('模型返回卷纲结果为空，请调整全局剧情内容后重试', 'error');
      return;
    }
    // ===== 硬截断 + 追加到列表 =====
    const PLOT_HARD = _getThVol('volume_plot_hard_chars', _VOLUME_PLOT_HARD_CHARS);
    const SUM_HARD = _getThVol('volume_summary_hard_chars', _VOLUME_SUMMARY_HARD_CHARS);
    const PLOT_SUG = _getThVol('volume_plot_chars', _VOLUME_PLOT_MAX_CHARS);
    const SUM_SUG = _getThVol('volume_summary_chars', _VOLUME_SUMMARY_MAX_CHARS);
    const plotFinal = newPlot.length > PLOT_HARD ? newPlot.slice(0, PLOT_HARD) : newPlot;
    const summaryFinal = newSummary.length > SUM_HARD ? newSummary.slice(0, SUM_HARD) : newSummary;

    if (!window._volumePlotResult) window._volumePlotResult = {};
    if (!Array.isArray(window._volumePlotResult.volumes)) window._volumePlotResult.volumes = [];
    window._volumePlotResult.volumes.push({ plot: plotFinal, summary: summaryFinal });
    const newIndex = window._volumePlotResult.volumes.length - 1;

    if (resData && (resData.task_id || resData.task_id === 0)) {
      const s = String(resData.task_id).trim();
      if (s) window._volumePlotResult.activeTaskId = s;
    } else if (!window._volumePlotResult.activeTaskId) {
      _volumeFindActiveTaskId().catch(function(err) {
        console.warn('[generateVolumePlotDesign] 找 activeTaskId 失败（不影响展示）:', err?.message || err);
      });
    }
    renderVolumeCards(window._volumePlotResult.volumes);

    const exceedParts = [];
    if (plotFinal.length > PLOT_SUG) exceedParts.push(`本卷剧情超过建议值 ${PLOT_SUG} 字`);
    if (summaryFinal.length > SUM_SUG) exceedParts.push(`本卷摘要超过建议值 ${SUM_SUG} 字`);
    if (plotFinal.length !== newPlot.length) exceedParts.push(`剧情超过硬上限 ${PLOT_HARD} 字已截断`);
    if (summaryFinal.length !== newSummary.length) exceedParts.push(`摘要超过硬上限 ${SUM_HARD} 字已截断`);
    if (exceedParts.length > 0) {
      try { showStatus(exceedParts.join('；') + '，可点击卡片手动调整后重新保存。', 'warn'); } catch (_e) {}
    }
    refreshVolumeStepActions();

    let persistTip = '';
    try {
      // 统一走 doSaveVolumeOutline(immediate=true)：与手动保存使用完全同一段代码，
      // 保证"显示卷号 = 数组下标 = volume_index"三者严格对齐；
      // 内部会自动清理 oldVi !== i 的 DB 脏记录（级联删旧位置 + upsert 新位置）。
      await doSaveVolumeOutline(true);
      _flashVolumeSaveTip(true, '已保存', newIndex);
    } catch (_e) {
      console.warn('[generateVolumePlotDesign] 保存卷纲任务失败（不影响展示）:', _e?.message || _e);
      persistTip = '（结果未成功写入任务表，请手动保存）';
    }
    const token = (typeof res?.token_cost === 'number') ? res.token_cost : 0;
    const taskId = res.task_id ? `（任务ID：${res.task_id}）` : '';
    const totalVols = window._volumePlotResult.volumes.length;
    showStatus(`卷纲剧情生成成功${taskId}${persistTip}，当前共 ${totalVols} 卷，消耗 ${token} tokens`, 'success');
  } catch (err) {
    console.error('[生成卷纲剧情失败:', err);
    showStatus('生成卷纲剧情失败，请稍后重试', 'error');
  } finally {
    if (genBtn) {
      if (genBtn.dataset.oriHtml) genBtn.innerHTML = genBtn.dataset.oriHtml;
      refreshVolumeStepActions();
    }
  }
  };

  window.startGenerateFlowWithPreview({
    hasExisting: hasExisting,
    confirmConfig: null,
    previewConfig: {
      sessionId: window.currentWorkId,
      capabilityId: CAP_ID,
      rawVariables: { global_plot_text: plot },
    },
    previewRequired: true,
    doReal: doReal,
  });
}

function handleVolumeNextStep() {
  if (!window.currentWorkId) {
    showStatus('请先在左侧选择一个作品', 'error');
    return;
  }
  const volumes = (window._volumePlotResult && Array.isArray(window._volumePlotResult.volumes))
    ? window._volumePlotResult.volumes.filter(function(v) { return v && (typeof v.plot === 'string' || typeof v.summary === 'string'); })
    : [];
  if (volumes.length === 0) {
    showStatus('请先点击上方「生成卷纲剧情」按钮并等待生成完成，再进入定章', 'error');
    const genBtn = document.getElementById('generateVolumeBtn');
    if (genBtn) genBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
    return;
  }
  showStatus(`已完成分卷环节（共 ${volumes.length} 卷），准备进入定章`, 'success');
  if (window.completeStep) {
    completeStep(window.currentWorkId, 3);
  } else if (window.handleStepClick) {
    void handleStepClick(window.currentWorkId, 4);
  }
}

window.resetVolumePageIsolatedState = resetVolumePageIsolatedState;
window.initVolumePage = initVolumePage;
window.refreshVolumeStepActions = refreshVolumeStepActions;
window.renderVolumeCards = renderVolumeCards;
window.generateVolumePlotDesign = generateVolumePlotDesign;
window.handleVolumeNextStep = handleVolumeNextStep;
window.addVolumeCard = addVolumeCard;
window.deleteVolumeCard = deleteVolumeCard;
window.toggleVolumeCard = toggleVolumeCard;
// 暴露卷纲行解析函数，供定章/推演/成文等下游节点 fallback 拉取卷纲任务时复用，避免跨 IIFE 调用不到
window._volTryParseVolumeRow = _volTryParseVolumeRow;
})();
