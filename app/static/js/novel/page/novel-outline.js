(function(){
let currentView = 'character';
let forceSimulation = null;
let timelineAnimFrame = null;
let timelineHoverIndex = -1;
let timelineShakeStart = 0;
let locationZoom = null;
let currentGraphGroup = null;

/**
 * 谋篇节点作品级隔离重置：切换作品/重入本节点前调用。
 * 清空所有作品级内存单例与 DOM 残留，避免异步加载完成前渲染出上一作品内容。
 */
function resetOutlinePageIsolatedState() {
  // 1) 视图/渲染句柄：回到角色视图，停止正在运行的力导向/动画
  currentView = 'character';
  if (forceSimulation) { try { forceSimulation.stop(); } catch (_) {} forceSimulation = null; }
  if (timelineAnimFrame) { cancelAnimationFrame(timelineAnimFrame); timelineAnimFrame = null; }
  timelineHoverIndex = -1;
  timelineShakeStart = 0;
  locationZoom = null;
  currentGraphGroup = null;

  // 2) 跨作品共享内存缓存：谋篇全局剧情/摘要结果
  if (window._globalPlotResult) {
    try { delete window._globalPlotResult.plot; delete window._globalPlotResult.summary; } catch (_) {
      window._globalPlotResult.plot = undefined; window._globalPlotResult.summary = undefined;
    }
  }
  window._globalPlotResult = null;

  // 3) DOM 残留：核心剧情输入框、全局剧情/摘要文本域、计数、结果面板隐藏
  const outlineText = document.getElementById('outlineText');
  if (outlineText) outlineText.value = '';
  const charCountEl = document.getElementById('outlineCharCurrent');
  if (charCountEl) charCountEl.innerText = '0';
  const plotEl = document.getElementById('globalPlotText');
  if (plotEl) plotEl.value = '';
  const summaryEl = document.getElementById('globalPlotSummary');
  if (summaryEl) summaryEl.value = '';
  const plotBox = document.getElementById('globalPlotResult');
  if (plotBox) plotBox.style.display = 'none';
  const pInfo = document.getElementById('plotCountInfo');
  const sInfo = document.getElementById('summaryCountInfo');
  if (pInfo) pInfo.textContent = '0 / 2000';
  if (sInfo) sInfo.textContent = '0 / 300';

  // 4) SVG / Canvas 容器：清空已绘制节点/关系/树，避免容器内残留上一作品图形
  const svg = document.getElementById('forceGraph');
  if (svg) { const ns = typeof d3 !== 'undefined' ? d3.select('#forceGraph') : null; if (ns && !ns.empty()) ns.selectAll('*').remove(); }
  const canvas = document.getElementById('outlineCanvas');
  if (canvas) { const ctx = canvas.getContext('2d'); ctx.clearRect(0, 0, canvas.width, canvas.height); }
  const locationContainer = document.getElementById('locationContainer');
  if (locationContainer) { const ns = typeof d3 !== 'undefined' ? d3.select('#locationContainer') : null; if (ns && !ns.empty()) ns.selectAll('*').remove(); }
}

const JELLY_KF = [
  { t: 0, s: 1 }, { t: 0.2, s: 0.95 }, { t: 0.4, s: 1.05 },
  { t: 0.6, s: 0.98 }, { t: 0.8, s: 1.02 }, { t: 1, s: 1 }
];

function getJellyScale(elapsed) {
  const dur = 600;
  if (elapsed >= dur) return 1;
  const p = elapsed / dur;
  for (let i = 0; i < JELLY_KF.length - 1; i++) {
    if (p >= JELLY_KF[i].t && p <= JELLY_KF[i + 1].t) {
      const seg = (p - JELLY_KF[i].t) / (JELLY_KF[i + 1].t - JELLY_KF[i].t);
      return JELLY_KF[i].s + (JELLY_KF[i + 1].s - JELLY_KF[i].s) * seg;
    }
  }
  return 1;
}

function getFixedRandomGradientIndex(index, total) {
  if (!sharedGradientMap.has(index)) {
    sharedGradientMap.set(index, Math.floor(Math.random() * total));
  }
  return sharedGradientMap.get(index);
}

function setupVisibilityControl() {
  document.addEventListener('visibilitychange', function() {
    if (!forceSimulation) return;

    if (document.hidden) {
      forceSimulation.stop();
    } else {
      if (forceSimulation.alpha() < 0.01) {
        forceSimulation.alpha(0.1).restart();
      } else {
        forceSimulation.restart();
      }
    }
  });
}

async function initOutlineCanvas() {
  // 【作品级隔离 SOP】切作品进入谋篇节点时，先清空所有作品级单例/DOM，再拉数据/渲染
  resetOutlinePageIsolatedState();
  // 先同步加载前端阈值（SSOT），保证后续计数刷新分母与后端完全对齐；失败则 fallback
  await _loadFrontendThresholdsOnce();
  const svg = document.getElementById('forceGraph');
  const canvas = document.getElementById('outlineCanvas');
  canvas.getContext('2d');
  const container = canvas.parentElement;

  canvas.width = container ? container.offsetWidth : 800;
  canvas.height = 600;

  const outlineText = document.getElementById('outlineText');
  const plotBox = document.getElementById('globalPlotResult');
  const plotEl = document.getElementById('globalPlotText');
  const summaryEl = document.getElementById('globalPlotSummary');
  const charCountEl = document.getElementById('outlineCharCurrent');

  let savedPlot = '';
  let savedSummary = '';

  // 1) 优先读内存里已生成的结果（生成后还没刷新的场景直接用最快）
  const mem = window._globalPlotResult || {};
  if (mem.plot && String(mem.plot).trim()) savedPlot = String(mem.plot).trim();
  if (mem.summary && String(mem.summary).trim()) savedSummary = String(mem.summary).trim();

  // 2) 如果内存里是空的 → 查后端 task 表：
  //    - core_plot：用户上一次输入的剧情核心文本
  //    - outline（status=completed，按id降序第一条）：上一次生成的全局剧情+摘要
  const needFetchResult = !savedPlot && !savedSummary;
  const shouldFetchCore = !!(window.currentWorkId && outlineText);
  const shouldFetchResult = !!(window.currentWorkId && needFetchResult);
  if (shouldFetchCore || shouldFetchResult) {
    try {
      const [coreRows, outlineRows] = await Promise.all([
        shouldFetchCore ? NovelAPI.listTasks(window.currentWorkId, NovelAPI.CONST.TASK_TYPE_CORE_PLOT, 'id', true) : Promise.resolve([]),
        shouldFetchResult ? NovelAPI.listTasks(window.currentWorkId, NovelAPI.CONST.TASK_TYPE_GLOBAL_OUTLINE, 'id', true) : Promise.resolve([]),
      ]);
      if (shouldFetchCore && Array.isArray(coreRows) && coreRows.length > 0) {
        const latest = coreRows[0] || {};
        const coreText = typeof latest.content_text === 'string' ? latest.content_text : '';
        if (outlineText && coreText.trim()) {
          outlineText.value = coreText;
          if (charCountEl) charCountEl.innerText = String(coreText.length);
        }
      }
      // 回填全局剧情结果（没有内存值时，取 outline 最新一条 completed）
      if (needFetchResult && Array.isArray(outlineRows) && outlineRows.length > 0) {
        let picked = null;
        for (const r of outlineRows) {
          if (r && String(r.status || '') === 'completed') { picked = r; break; }
        }
        // 找不到 completed 任务时不回退到 failed/pending 任务：
        // failed 任务的内容是错误信息而非剧情，pending 任务内容为空，
        // 回退到这些任务会导致已生成内容被错误信息覆盖显示。
        if (!picked) { /* 无 completed 任务，保持空值，用户可重新生成 */ }
        const content = picked && typeof picked.content_text === 'string' ? picked.content_text : '';
        if (content) {
          let p = '';
          let s = '';
          const firstCh = content.trim().charAt(0);
          if (firstCh === '{') {
            try {
              const obj = JSON.parse(content);
              if (obj && typeof obj === 'object') {
                if (typeof obj.plot === 'string') p = obj.plot;
                if (typeof obj.summary === 'string') s = obj.summary;
              }
            } catch (_) { /* ignore */ }
          }
          if (p) savedPlot = p;
          if (s) savedSummary = s;
          if (!window._globalPlotResult) window._globalPlotResult = {};
          if (!window._globalPlotResult.plot) window._globalPlotResult.plot = p;
          if (!window._globalPlotResult.summary) window._globalPlotResult.summary = s;
        }
      }
    } catch (err) {
      console.warn('[initOutlineCanvas] 查询谋篇持久化数据失败，将使用内存默认值:', err?.message || err);
    }
  }

  // === 核心剧情输入框失焦自动保存（与剧情卡片保存提示效果一致） ===
  function _flashCoreSaveTip(success) {
    const tip = document.getElementById('outlineCoreSaveTip');
    if (!tip) return;
    tip.innerText = success ? '已自动保存' : '保存失败，请稍后重试';
    tip.style.color = success ? '#7c3aed' : '#dc2626';
    tip.style.opacity = '1';
    clearTimeout(tip._t);
    tip._t = setTimeout(() => { tip.style.opacity = '0'; }, 1600);
  }
  if (outlineText && outlineText.dataset.coreSaveBound !== '1') {
    outlineText.addEventListener('blur', async () => {
      const text = outlineText.value.trim();
      if (!text) return;
      if (!window.currentWorkId) return;
      try {
        await NovelAPI.upsertCorePlot(window.currentWorkId, text);
        _flashCoreSaveTip(true);
      } catch (err) {
        console.warn('[outline-core] 自动保存失败:', err?.message || err);
        _flashCoreSaveTip(false);
      }
    });
    outlineText.dataset.coreSaveBound = '1';
  }

  const hasPlot = savedPlot.length > 0;
  const hasSummary = savedSummary.length > 0;

  let _plotExceedAlerted = false;
  let _summaryExceedAlerted = false;
  function _refreshPlotCounts() {
    const pEl = document.getElementById('globalPlotText');
    const sEl = document.getElementById('globalPlotSummary');
    const pInfo = document.getElementById('plotCountInfo');
    const sInfo = document.getElementById('summaryCountInfo');
    const pLabel = document.getElementById('plotLabel');
    const sLabel = document.getElementById('summaryLabel');
    const PLOT_MAX = _getTh('global_plot_chars', _OUTLINE_GLOBAL_PLOT_MAX_CHARS);
    const SUM_MAX = _getTh('global_summary_chars', _OUTLINE_GLOBAL_SUMMARY_MAX_CHARS);
    const PLOT_HARD = _getTh('global_plot_hard_chars', _OUTLINE_GLOBAL_PLOT_HARD_CHARS);
    const SUM_HARD = _getTh('global_summary_hard_chars', _OUTLINE_GLOBAL_SUMMARY_HARD_CHARS);
    const pLen = pEl ? (pEl.value || '').length : 0;
    const sLen = sEl ? (sEl.value || '').length : 0;
    if (pInfo) pInfo.innerText = `${pLen} / ${PLOT_HARD}`;
    if (sInfo) sInfo.innerText = `${sLen} / ${SUM_HARD}`;
    if (pLabel) pLabel.innerText = `剧情（建议 ${PLOT_MAX} 字内，最大 ${PLOT_HARD} 字）`;
    if (sLabel) sLabel.innerText = `摘要（建议 ${SUM_MAX} 字内，最大 ${SUM_HARD} 字）`;
    try {
      if (typeof showStatus === 'function') {
        const plotOver = pLen > PLOT_MAX;
        if (plotOver && !_plotExceedAlerted) {
          showStatus(`剧情已超建议值 ${pLen - PLOT_MAX} 字，建议精简`, 'warn');
          _plotExceedAlerted = true;
        } else if (!plotOver && _plotExceedAlerted) {
          _plotExceedAlerted = false;
        }
        const sumOver = sLen > SUM_MAX;
        if (sumOver && !_summaryExceedAlerted) {
          showStatus(`摘要已超建议值 ${sLen - SUM_MAX} 字，建议精简`, 'warn');
          _summaryExceedAlerted = true;
        } else if (!sumOver && _summaryExceedAlerted) {
          _summaryExceedAlerted = false;
        }
      }
    } catch (_e) {
      // 忽略通知异常，不影响计数刷新
    }
  }
  window.__refreshOutlinePlotCounts = _refreshPlotCounts;
  window.__bindOutlineEditableOnce = _bindEditableAreasOnce;

  function _flashSaveTip(success) {
    const tip = document.getElementById('globalPlotSaveTip');
    if (!tip) return;
    tip.innerText = success ? '已自动保存' : '保存失败，请稍后重试';
    tip.style.color = success ? '#7c3aed' : '#dc2626';
    tip.style.opacity = '1';
    clearTimeout(tip._t);
    tip._t = setTimeout(() => { tip.style.opacity = '0'; }, 1600);
  }

  function _bindEditableAreasOnce() {
    const pEl = document.getElementById('globalPlotText');
    const sEl = document.getElementById('globalPlotSummary');
    if (!pEl || !sEl) return;
    if (pEl.dataset.bound === '1' && sEl.dataset.bound === '1') return;
    const PLOT_HARD = _getTh('global_plot_hard_chars', _OUTLINE_GLOBAL_PLOT_HARD_CHARS);
    const SUM_HARD = _getTh('global_summary_hard_chars', _OUTLINE_GLOBAL_SUMMARY_HARD_CHARS);
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
      if (typeof showStatus === 'function') {
        showStatus(`${label}超过最大 ${hardMax} 字，已自动舍弃末尾超出内容。`, 'warn');
      }
      return true;
    }
    let saveTimer = null;
    const scheduleSave = () => {
      if (!window.currentWorkId) return;
      clearTimeout(saveTimer);
      saveTimer = setTimeout(async () => {
        const p = pEl ? (pEl.value || '') : '';
        const s = sEl ? (sEl.value || '') : '';
        if (!p && !s) return;
        if (!window._globalPlotResult) window._globalPlotResult = {};
        if (p) window._globalPlotResult.plot = p;
        if (s) window._globalPlotResult.summary = s;
        try {
          await NovelAPI.upsertOutline(window.currentWorkId, p, s);
          _flashSaveTip(true);
        } catch (err) {
          console.warn('[outline-edit] 自动保存失败:', err?.message || err);
          _flashSaveTip(false);
        }
      }, 500);
    };
    const applyHardLimits = () => {
      const changedPlot = _enforceHardMax(pEl, PLOT_HARD, '剧情');
      const changedSum = _enforceHardMax(sEl, SUM_HARD, '摘要');
      return changedPlot || changedSum;
    };
    const onInput = () => { applyHardLimits(); _refreshPlotCounts(); };
    const onPaste = () => { setTimeout(() => { onInput(); }, 0); };
    const onBlur = () => { applyHardLimits(); _refreshPlotCounts(); scheduleSave(); };
    pEl.addEventListener('input', onInput);
    pEl.addEventListener('paste', onPaste);
    pEl.addEventListener('blur', onBlur);
    sEl.addEventListener('input', onInput);
    sEl.addEventListener('paste', onPaste);
    sEl.addEventListener('blur', onBlur);
    pEl.dataset.bound = '1';
    sEl.dataset.bound = '1';
    // 绑完事件立即兜底一次：回填的历史内容若已超新硬阈值（例如之前的老数据），首次打开也正确截断，避免视觉不一致
    applyHardLimits();
    _refreshPlotCounts();
  }

  if (hasPlot || hasSummary) {
    if (plotEl) plotEl.value = savedPlot || '';
    if (summaryEl) summaryEl.value = savedSummary || '';
    if (plotBox) plotBox.style.display = 'block';
    _bindEditableAreasOnce();
    _refreshPlotCounts();
  } else {
    if (plotBox) plotBox.style.display = 'none';
  }
  // 事件绑定与计数刷新：无论当前是否有结果都先跑一次，避免用户生成后立即编辑才生效
  _bindEditableAreasOnce();
  _refreshPlotCounts();
  // 回填完成后同步两个底部按钮的可用态/tooltip
  refreshOutlineStepActions();

  if (svg) {
    svg.setAttribute('width', String(canvas.width));
    svg.setAttribute('height', String(canvas.height));
  }

  switchView(currentView);
}

function switchView(viewType) {
  currentView = viewType;

  const activeBtn = document.querySelector(`label[for="${viewType}Switch"]`);
  if (activeBtn) {
    activeBtn.classList.add('jelly-effect');
    setTimeout(() => activeBtn.classList.remove('jelly-effect'), 600);
  }

  const tips = document.querySelectorAll('.canvas-tips p');
  tips.forEach(p => p.style.display = 'none');

  const tipId = `tip${viewType.charAt(0).toUpperCase() + viewType.slice(1)}`;
  const activeTip = document.getElementById(tipId);
  if (activeTip) activeTip.style.display = 'block';

  renderView(viewType);
}

function renderView(viewType) {
  const svg = document.getElementById('forceGraph');
  const canvas = document.getElementById('outlineCanvas');
  const blurLayer = document.getElementById('timelineBlurLayer');
  const locationContainer = document.getElementById('locationContainer');

  canvas.onmousemove = null;
  canvas.onmouseleave = null;
  if (timelineAnimFrame) {
    cancelAnimationFrame(timelineAnimFrame);
    timelineAnimFrame = null;
  }
  timelineHoverIndex = -1;

  if (forceSimulation) {
    forceSimulation.stop();
    forceSimulation = null;
  }

  if (tooltip) {
    tooltip.html('').style('visibility', 'hidden').style('opacity', 0);
  }

  if (viewType === 'character') {
    resetSharedGradients();
    svg.style.display = 'block';
    canvas.style.display = 'none';
    blurLayer.style.display = 'none';
    locationContainer.style.display = 'none';
    locationContainer.style.pointerEvents = 'none';
    initForceGraph();
  } else if (viewType === 'timeline') {
    svg.style.display = 'none';
    canvas.style.display = 'block';
    blurLayer.style.display = 'block';
    locationContainer.style.display = 'none';
    locationContainer.style.pointerEvents = 'none';

    const timelines = (weaveData.timelines || []).sort((a, b) => {
      const sa = Number(a.sort_index); const sb = Number(b.sort_index);
      if (!Number.isNaN(sa) && !Number.isNaN(sb) && sa !== sb) return sa - sb;
      return (Number(a.id) || 0) - (Number(b.id) || 0);
    });
    const dynamicItemHeights = timelines.map(tl => {
      const attrsCount = tl.attributes ? Object.entries(tl.attributes).length : 0;
      return 160 + attrsCount * 20;
    });
    const totalHeight = dynamicItemHeights.reduce((sum, h) => sum + h, 0);
    const requiredHeight = Math.max(600, 80 + totalHeight + 40);

    canvas.height = requiredHeight;
    canvas.style.height = requiredHeight + 'px';

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    renderTimelineList(ctx, canvas.width, canvas.height);
  } else if (viewType === 'location') {
    svg.style.display = 'none';
    canvas.style.display = 'none';
    blurLayer.style.display = 'none';
    locationContainer.style.display = 'block';
    locationContainer.style.pointerEvents = 'auto';

    const w = locationContainer.offsetWidth || 800;
    const h = locationContainer.offsetHeight || 600;
    resetSharedGradients();
    renderLocationTree('#locationContainer', w, h);
  }
}

function transformCharacterData(characters) {
    const nodes = characters.map((char, index) => ({
        id: String(char.id),
        name: char.name,
        gender: char.gender || 'male',
        identity: char.identity || '',
        secret: char.secret || '',
        type: char.type || '',
        aliases: char.aliases || [],
        attributes: char.attributes || {},
        x: null,
        y: null,
        index: index
    }));

    const relationships = extractRelationships(characters);
    const links = relationships.length > 0
        ? generateRealLinks(relationships, nodes)
        : generateSimulatedLinks(nodes);

    return { nodes, links };
}

function extractRelationships(characters) {
    const allRelationships = [];
    characters.forEach(char => {
        const rels = char.relationships || [];
        rels.forEach(rel => {
            allRelationships.push({
                source: char.id,
                target: rel.targetId,
                type: rel.type
            });
        });
    });
    return allRelationships;
}

function generateRealLinks(relationships, nodes) {
    const nodeIds = new Set(nodes.map(n => n.id));
    return relationships.filter(rel =>
        nodeIds.has(String(rel.source)) && nodeIds.has(String(rel.target))
    ).map(rel => ({
        source: String(rel.source),
        target: String(rel.target),
        type: rel.type
    }));
}

function generateSimulatedLinks(nodes) {
    const links = [];
    for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
            links.push({
                source: nodes[i].id,
                target: nodes[j].id,
                type: '关联',
                value: 2
            });
        }
    }
    return links;
}

function initForceGraph() {
  resetSharedGradients();
  const container = document.querySelector('.canvas-container');
  const width = container.offsetWidth || 800;
  const charsCount = (weaveData.characters || []).length;
  const minByNodes = Math.max(600, charsCount * 140 + 200);
  const height = Math.max(minByNodes, width);

  let svg = d3.select('#forceGraph');
  if (svg.empty()) {
    svg = d3.select('.canvas-container')
      .append('svg')
      .attr('id', 'forceGraph')
      .attr('width', width)
      .attr('height', height)
      .style('overflow', 'visible');
  } else {
    svg.attr('width', width).attr('height', height).style('overflow', 'visible');
    svg.selectAll('*').remove();
  }

  svg.on('.zoom', null);
  const zoom = d3.zoom()
    .scaleExtent([0.3, 3])
    .on('zoom', (event) => {
      if (currentGraphGroup) {
        currentGraphGroup.attr('transform', event.transform);
      }
    });
  svg.call(zoom);

  const defs = svg.append('defs');
  const linkGrad = defs.append('linearGradient')
    .attr('id', 'linkGradient')
    .attr('x1', '0%').attr('y1', '0%').attr('x2', '100%').attr('y2', '0%');
  linkGrad.append('stop').attr('offset', '0%').attr('stop-color', '#ffffff');
  linkGrad.append('stop').attr('offset', '100%').attr('stop-color', '#3b82f6');

  svg.append('rect')
    .attr('width', width)
    .attr('height', height)
    .attr('fill', 'transparent');

  currentGraphGroup = svg.append('g').attr('class', 'graph-group');

  if (!document.querySelector('.force-tooltip')) {
    tooltip = d3.select('body')
      .append('div')
      .attr('class', 'force-tooltip');
  } else {
    tooltip = d3.select('.force-tooltip');
  }

  if (window.typeColorMap) {
    for (const key in window.typeColorMap) {
      delete window.typeColorMap[key];
    }
  }

  renderForceGraph(currentGraphGroup, width, height);

  const cw = container.offsetWidth || width;
  const ch = container.offsetHeight || 600;
  const targetCx = cw / 2;
  const targetCy = ch * 0.42;
  const svgCx = width / 2;
  const svgCy = height / 2;
  svg.call(zoom.transform, d3.zoomIdentity.translate(targetCx - svgCx, targetCy - svgCy));
}

function renderForceGraph(g, width, height) {
  const characters = (weaveData.characters || []).sort((a, b) => (Number(a.id) || 0) - (Number(b.id) || 0));
  g.attr("transform", null);

  if (characters.length === 0) {
    g.selectAll("*").remove();
    g.append("text")
      .attr("x", width/2)
      .attr("y", height/2 - 10)
      .attr("text-anchor", "middle")
      .attr("fill", "#999")
      .attr("font-size", "14px")
      .text("暂无角色数据");
    g.append("text")
      .attr("x", width/2)
      .attr("y", height/2 + 15)
      .attr("text-anchor", "middle")
      .attr("fill", "#bbb")
      .attr("font-size", "12px")
      .text("请先在织网环节添加角色");
    return;
  }

  const { nodes, links } = transformCharacterData(characters);
  const hasRealLinks = links.length > 0 && links.some(l => l.type !== undefined);

  links.forEach(d => {
      d.restLength = 100 + Math.random() * 60;
  });

  const cx = width / 2 || 300;
  const cy = height / 2 || 250;
  nodes.forEach(d => {
      if (d.x === undefined) d.x = cx + (Math.random() - 0.5) * 50;
      if (d.y === undefined) d.y = cy + (Math.random() - 0.5) * 50;
  });

  g.selectAll(".link").remove();
  g.selectAll(".link-text").remove();
  g.selectAll(".node").remove();

  const linkGroup = g.append("g").attr("class", "links");
  const link = linkGroup.selectAll(".link")
      .data(links)
      .enter().append("line")
      .attr("class", "link")
      .attr("stroke", "url(#linkGradient)")
      .attr("stroke-opacity", 1)
      .attr("stroke-width", 3)
      .attr("stroke-linecap", "round")
      .attr("stroke-dasharray", d => (!hasRealLinks || !d.type) ? "4,3" : "none");

  let linkText = null;
  if (hasRealLinks) {
    const linkTextGroup = g.append("g").attr("class", "link-texts");
    linkText = linkTextGroup.selectAll(".link-text")
        .data(links)
        .enter().append("g")
        .attr("class", "link-text")
        .on("mouseover", function(event, d) {
          const rect = d3.select(this).select("rect");
          rect.classed("link-label-shaking", false);
          void this.getBoundingClientRect();
          rect.classed("link-label-shaking", true);
        })
        .on("mouseout", function() {
            const rect = d3.select(this).select("rect");
            rect.classed("link-label-shaking", false);
            rect.style("opacity", 0.7);
        });

    linkText.append("rect")
        .attr("rx", 16)
        .attr("ry", 16)
        .attr("fill", d => d.type ? getRelationshipColor(d.type) : 'rgba(142, 45, 226, 0.7)')
        .attr("opacity", 0.7);

    linkText.append("text")
        .attr("font-size", "11px")
        .attr("fill", "#fff")
        .attr("font-weight", "600")
        .attr("text-anchor", "middle")
        .attr("dominant-baseline", "central")
        .text(d => d.type || '')
        .each(function(d) {
          const bbox = this.getBBox();
          d3.select(this.parentNode).select("rect")
            .attr("x", bbox.x - 12)
            .attr("y", bbox.y - 8)
            .attr("width", bbox.width + 24)
            .attr("height", bbox.height + 16);
        });
  }

  const nodeGroup = g.append("g").attr("class", "nodes");
  const node = nodeGroup.selectAll(".node")
      .data(nodes, d => d.id)
      .enter().append("g")
      .attr("class", "node")
      .attr("cursor", "pointer")
      .call(d3.drag()
          .on("start", dragstarted)
          .on("drag", dragged)
          .on("end", dragended)
      );

  node.append("circle")
      .attr("r", 32)
      .attr("fill", "rgba(26, 26, 46, 0.8)")
      .style("pointer-events", "none");

  node.append("circle")
      .attr("r", 34)
      .attr("fill", "transparent")
      .attr("class", "node-hotzone");

  node.append("circle")
      .attr("r", 30)
      .attr("fill", "transparent")
      .attr("stroke", d => d.gender === 'female' ? '#e74c3c' : '#3498db')
      .attr("stroke-width", 3)
      .style("filter", "none")
      .style("box-shadow", "none")
      .attr("cursor", "pointer")
      .attr("class", "node-circle");

  node.append("text")
      .attr("y", -4)
      .attr("font-size", "11px")
      .attr("fill", "#fff")
      .attr("text-anchor", "middle")
      .attr("pointer-events", "none")
      .attr("font-weight", "bold")
      .text(d => d.gender === 'female' ? '♀' : '♂');

  node.append("text")
      .attr("y", 10)
      .attr("font-size", "12px")
      .attr("font-weight", "600")
      .attr("fill", "#fff")
      .attr("text-anchor", "middle")
      .attr("pointer-events", "none")
      .text(d => d.name.length > 4 ? d.name.slice(0, 4) + '…' : d.name);

  let isHovering = false;

  node.on("mouseenter", function(event, d) {
    if (isHovering) return;
    isHovering = true;

    const identityDisplay = d.identity || '无';
    const secretDisplay = d.secret || '无';

    const typeStr = (d.type || '').toString();
    const typeDisplay = typeStr || '未知';

    const aliasesDisplay = d.aliases && d.aliases.length > 0
        ? `<span class="tooltip-alias">（${d.aliases.map(a => escapeHtml(a)).join('、')}）</span>`
        : '';

    const attrsEntries = d.attributes ? Object.entries(d.attributes) : [];
    const attrsDisplay = attrsEntries.length > 0
        ? attrsEntries.map(([k, v]) => `<div class="tooltip-item"><span class="tooltip-label">${escapeHtml(k)}</span><span class="tooltip-value">${escapeHtml(v)}</span></div>`).join('')
        : '';

    const gradIdx = getSharedGradientIndex(d.id, SHARED_GRADIENTS.length);
    const pair = SHARED_GRADIENTS[gradIdx];

    tooltip.html(`
      <div class="tooltip-header">
        <span class="tooltip-name">${d.name}</span>${aliasesDisplay}
      </div>
      <hr class="tooltip-divider">
      <div class="tooltip-item">
        <span class="tooltip-label">类型</span>
        <span class="tooltip-value">${typeDisplay}</span>
      </div>
      <div class="tooltip-item">
        <span class="tooltip-label">身份</span>
        <span class="tooltip-value">${identityDisplay}</span>
      </div>
      <div class="tooltip-item">
        <span class="tooltip-label">隐秘</span>
        <span class="tooltip-value">${secretDisplay}</span>
      </div>
      ${attrsDisplay}
    `)
    .style("visibility", "visible")
    .style("opacity", 1)
    .style("background", `linear-gradient(135deg, ${pair[0]} 0%, ${pair[1]} 100%)`);

    const circle = d3.select(this).select(".node-circle");
    circle.attr("filter", "none");
    circle.classed("node-circle-shaking", false);
    void this.getBoundingClientRect();
    circle.classed("node-circle-shaking", true);

    link.style("opacity", l =>
        l.source.id === d.id || l.target.id === d.id ? 0.85 : 0.15
    );
  })
  .on("mousemove", function(event) {
      tooltip.style("top", (event.pageY + 15) + "px")
              .style("left", (event.pageX + 15) + "px");
  })
  .on("mouseleave", function(event, d) {
    isHovering = false;

    tooltip.style("visibility", "hidden").style("opacity", 0)
           .style("background", "rgba(26, 26, 46, 0.85)");

    const circle = d3.select(this).select(".node-circle");
    circle.attr("filter", "none");
    circle.classed("node-circle-shaking", false);

    link.style("opacity", 0.6);
  });

  if (forceSimulation) forceSimulation.stop();

  forceSimulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id(d => d.id).distance(d => d.restLength).strength(0.6))
      .force("charge", d3.forceManyBody().strength(-300))
      .force("center", d3.forceCenter(cx, cy))
      .force("collision", d3.forceCollide().radius(40).strength(0.5))
      .alphaMin(0.001)
      .alphaDecay(0.02)
      .velocityDecay(0.4)
      .on("tick", ticked);

  let dragPrevX = 0, dragPrevY = 0, dragPrevTime = 0;

  function ticked() {
      link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
          .attr("x2", d => d.target.x).attr("y2", d => d.target.y);

      if (linkText) {
          linkText.attr("transform", d => `translate(${(d.source.x + d.target.x) / 2}, ${(d.source.y + d.target.y) / 2})`)
              .style("display", d => {
                  const dist = Math.sqrt(Math.pow(d.target.x - d.source.x, 2) + Math.pow(d.target.y - d.source.y, 2));
                  return dist < 100 ? 'none' : 'block';
              });
      }
      node.attr("transform", d => `translate(${d.x},${d.y})`);
  }

  function dragstarted(event, d) {
      if (!event.active) forceSimulation.alphaTarget(0.1).restart();
      d.fx = d.x; d.fy = d.y;
      dragPrevX = event.x; dragPrevY = event.y; dragPrevTime = Date.now();
      d.vx = 0; d.vy = 0;
      d3.select(this).style("cursor", "grabbing");
  }

  function dragged(event, d) {
      d.fx = event.x; d.fy = event.y;
      dragPrevX = event.x; dragPrevY = event.y; dragPrevTime = Date.now();
  }

  function dragended(event, d) {
      if (!event.active) forceSimulation.alphaTarget(0);

      links.forEach(l => {
          if (l.source.id === d.id || l.target.id === d.id) {
              const dx = l.source.x - l.target.x;
              const dy = l.source.y - l.target.y;
              l.restLength = Math.sqrt(dx * dx + dy * dy);
          }
      });
      forceSimulation.force("link").distance(l => l.restLength);

      const now = Date.now();
      const dt = Math.max(now - dragPrevTime, 1);
      const vx = (event.x - dragPrevX) / dt * 16;
      const vy = (event.y - dragPrevY) / dt * 16;
      const speed = Math.sqrt(vx * vx + vy * vy);

      d.fx = null; d.fy = null;

      const maxV = 25;
      d.vx = Math.max(-maxV, Math.min(maxV, vx));
      d.vy = Math.max(-maxV, Math.min(maxV, vy));

      const dynamicAlpha = Math.min(0.8, 0.3 + speed * 0.05);
      forceSimulation.alpha(dynamicAlpha).restart();

      d3.select(this).style("cursor", "pointer");
  }
}

function getTimelineGradient(ctx, index, x, y, w, h) {
  const pair = SHARED_GRADIENTS[index % SHARED_GRADIENTS.length];
  const grad = ctx.createLinearGradient(x, y, x + w, y + h);
  grad.addColorStop(0, pair[0]);
  grad.addColorStop(1, pair[1]);
  return grad;
}

function drawEmptyState(ctx, width, height, title, subtitle) {
  ctx.clearRect(0, 0, width, height);

  ctx.font = '56px FontAwesome';
  ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('\uf07b', width / 2, height / 2 - 40);

  ctx.font = '16px sans-serif';
  ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
  ctx.fillText(title, width / 2, height / 2 + 20);

  ctx.font = '13px sans-serif';
  ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
  ctx.fillText(subtitle, width / 2, height / 2 + 45);
}

function renderTimelineList(ctx, width, height) {
  const timelines = (weaveData.timelines || []).sort((a, b) => {
    const sa = Number(a.sort_index); const sb = Number(b.sort_index);
    if (!Number.isNaN(sa) && !Number.isNaN(sb) && sa !== sb) return sa - sb;
    return (Number(a.id) || 0) - (Number(b.id) || 0);
  });
  if (!timelines.length) {
    drawEmptyState(ctx, width, height, '暂无时间节点', '请先在织网环节添加时间节点');
    return;
  }

  if (timelineAnimFrame) cancelAnimationFrame(timelineAnimFrame);
  bindTimelineHover(width, height, timelines, 80, 80);

  function frame() {
    drawTimeline(ctx, width, height, timelines);
    if (timelineHoverIndex !== -1) {
      timelineAnimFrame = requestAnimationFrame(frame);
    } else {
      timelineAnimFrame = null;
    }
  }
  frame();
}

function drawTimeline(ctx, width, height, timelines) {
  const lineX = 80, startY = 80;

  ctx.clearRect(0, 0, width, height);

  const dynamicItemHeights = timelines.map(tl => {
    const attrsCount = tl.attributes ? Object.entries(tl.attributes).length : 0;
    return 160 + attrsCount * 20;
  });

  const totalHeight = dynamicItemHeights.reduce((sum, h) => sum + h, 0);
  const endY = startY + totalHeight + 40;
  const lg = ctx.createLinearGradient(lineX, startY, lineX, endY);
  lg.addColorStop(0, '#c4b5fd');
  lg.addColorStop(0.5, '#8e2de2');
  lg.addColorStop(1, '#c4b5fd');
  ctx.strokeStyle = lg;
  ctx.lineWidth = 3;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(lineX, startY - 10);
  ctx.lineTo(lineX, endY);
  ctx.stroke();

  let currentY = startY;
  timelines.forEach((tl, i) => {
    const itemH = dynamicItemHeights[i];
    const y = currentY;
    currentY += itemH;

    const isFirst = i === 0, isLast = i === timelines.length - 1;
    const accent = isFirst ? '#e74c3c' : isLast ? '#27ae60' : '#8e2de2';
    const hovered = i === timelineHoverIndex;

    const attrsEntries = tl.attributes ? Object.entries(tl.attributes) : [];
    const attrsCount = attrsEntries.length;
    const dynamicHeight = 140 + attrsCount * 20;

    const nodeScale = hovered ? getJellyScale(Date.now() - timelineShakeStart) : 1;
    ctx.save();
    ctx.translate(lineX, y);
    ctx.scale(nodeScale, nodeScale);
    ctx.beginPath();
    ctx.arc(0, 0, 24, 0, Math.PI * 2);
    ctx.fillStyle = isFirst ? 'rgba(231,76,60,0.15)' : isLast ? 'rgba(39,174,96,0.15)' : 'rgba(142,45,226,0.12)';
    ctx.fill();
    ctx.beginPath();
    ctx.arc(0, 0, 18, 0, Math.PI * 2);
    ctx.fillStyle = accent;
    ctx.fill();
    ctx.font = 'bold 16px "PingFang SC", sans-serif';
    ctx.fillStyle = '#fff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(String(i + 1), 0, 0);
    ctx.restore();

    ctx.strokeStyle = isFirst ? 'rgba(231,76,60,0.3)' : isLast ? 'rgba(39,174,96,0.3)' : 'rgba(142,45,226,0.2)';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(lineX + 24, y);
    ctx.lineTo(lineX + 80, y);
    ctx.stroke();
    ctx.setLineDash([]);

    const cX = lineX + 80, cY = y - (dynamicHeight / 2);
    const cW = width - cX - 80, cH = dynamicHeight;
    const cardScale = hovered ? getJellyScale(Date.now() - timelineShakeStart) : 1;

    ctx.save();
    ctx.translate(cX + cW / 2, cY + cH / 2);
    ctx.scale(cardScale, cardScale);
    ctx.translate(-(cX + cW / 2), -(cY + cH / 2));

    ctx.beginPath();
    ctx.roundRect(cX, cY, cW, cH, 16);
    if (hovered) {
      ctx.fillStyle = getTimelineGradient(ctx, getFixedRandomGradientIndex(i, SHARED_GRADIENTS.length), cX, cY, cW, cH);
    } else {
      ctx.fillStyle = 'rgba(30, 30, 40, 0.6)';
    }
    ctx.fill();

    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';

    const textColor = hovered ? '#fff' : '#f5f0e8';
    const descColor = hovered ? 'rgba(255, 255, 255, 0.8)' : 'rgba(245, 240, 232, 0.75)';

    ctx.font = '700 18px "PingFang SC", sans-serif';
    ctx.fillStyle = textColor;
    const name = tl.name || '未知';
    ctx.fillText(name, cX + 24, cY + 32);

    if (tl.aliases && tl.aliases.length > 0) {
      const aliasesText = `（${tl.aliases.join('、')}）`;
      const nameWidth = ctx.measureText(name).width;
      ctx.font = '500 14px "PingFang SC", sans-serif';
      ctx.fillStyle = descColor;
      ctx.fillText(aliasesText, cX + 24 + nameWidth + 8, cY + 32);
    }

    ctx.strokeStyle = hovered ? 'rgba(26, 26, 46, 0.2)' : 'rgba(245, 240, 232, 0.2)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cX + 24, cY + 52);
    ctx.lineTo(cX + cW - 24, cY + 52);
    ctx.stroke();

    ctx.font = '600 14px "PingFang SC", sans-serif';
    ctx.fillStyle = textColor;
    ctx.fillText('类型：', cX + 24, cY + 72);
    ctx.font = '500 14px "PingFang SC", sans-serif';
    ctx.fillStyle = descColor;
    ctx.fillText(tl.type || '未分类', cX + 24 + ctx.measureText('类型：').width, cY + 72);

    ctx.font = '600 14px "PingFang SC", sans-serif';
    ctx.fillStyle = textColor;
    ctx.fillText('描述：', cX + 24, cY + 96);
    ctx.font = '500 14px "PingFang SC", sans-serif';
    ctx.fillStyle = descColor;
    let desc = tl.description || '';
    const maxW = cW - 48 - ctx.measureText('描述：').width;
    if (desc && ctx.measureText(desc).width > maxW) {
      while (ctx.measureText(desc + '…').width > maxW && desc.length > 0) desc = desc.slice(0, -1);
      desc += '…';
    }
    ctx.fillText(desc, cX + 24 + ctx.measureText('描述：').width, cY + 96);

    attrsEntries.forEach(([k, v], idx) => {
      const attrY = cY + 120 + idx * 20;
      ctx.font = '600 14px "PingFang SC", sans-serif';
      ctx.fillStyle = textColor;
      ctx.fillText(`${k}：`, cX + 24, attrY);
      ctx.font = '500 14px "PingFang SC", sans-serif';
      ctx.fillStyle = descColor;
      const attrMaxW = cW - 48 - ctx.measureText(`${k}：`).width;
      let attrVal = v || '';
      if (attrVal && ctx.measureText(attrVal).width > attrMaxW) {
        while (ctx.measureText(attrVal + '…').width > attrMaxW && attrVal.length > 0) attrVal = attrVal.slice(0, -1);
        attrVal += '…';
      }
      ctx.fillText(attrVal, cX + 24 + ctx.measureText(`${k}：`).width, attrY);
    });

    ctx.restore();
  });
}

function bindTimelineHover(width, height, timelines, lineX, startY) {
  const canvas = document.getElementById('outlineCanvas');
  canvas.onmousemove = null;
  canvas.onmouseleave = null;
  timelineHoverIndex = -1;

  const dynamicItemHeights = timelines.map(tl => {
    const attrsCount = tl.attributes ? Object.entries(tl.attributes).length : 0;
    return 160 + attrsCount * 20;
  });

  canvas.onmousemove = (e) => {
    if (currentView !== 'timeline') return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    let idx = -1;
    let currentY = startY;
    timelines.forEach((tl, i) => {
      const itemH = dynamicItemHeights[i];
      const y = currentY;
      currentY += itemH;

      const attrsCount = tl.attributes ? Object.entries(tl.attributes).length : 0;
      const dynamicHeight = 140 + attrsCount * 20;
      const cX = lineX + 80, cY = y - (dynamicHeight / 2);
      const cW = width - cX - 80;
      if (Math.hypot(mx - lineX, my - y) <= 24 ||
          (mx >= cX && mx <= cX + cW && my >= cY && my <= cY + dynamicHeight)) {
        idx = i;
      }
    });
    if (idx !== timelineHoverIndex) {
      timelineHoverIndex = idx;
      timelineShakeStart = Date.now();
      if (idx !== -1 && !timelineAnimFrame) {
        const ctx = canvas.getContext('2d');
        (function loop() {
          drawTimeline(ctx, width, height, timelines);
          if (timelineHoverIndex !== -1) timelineAnimFrame = requestAnimationFrame(loop);
          else timelineAnimFrame = null;
        })();
      }
      if (idx === -1 && timelineAnimFrame) {
        cancelAnimationFrame(timelineAnimFrame);
        timelineAnimFrame = null;
        drawTimeline(canvas.getContext('2d'), width, height, timelines);
      }
    }
  };

  canvas.onmouseleave = () => {
    timelineHoverIndex = -1;
    if (timelineAnimFrame) { cancelAnimationFrame(timelineAnimFrame); timelineAnimFrame = null; }
    drawTimeline(canvas.getContext('2d'), width, height, timelines);
  };
}

function renderLocationTree(containerSelector, width, height) {
  const locations = (weaveData.locations || []).sort((a, b) => (Number(a.id) || 0) - (Number(b.id) || 0));
  const container = d3.select(containerSelector);
  container.selectAll('*').remove();

  if (!document.querySelector('.force-tooltip')) {
    tooltip = d3.select('body')
      .append('div')
      .attr('class', 'force-tooltip');
  } else {
    tooltip = d3.select('.force-tooltip');
  }

  if (locations.length === 0) {
    const svg = container.append('svg').attr('width', width).attr('height', height);
    svg.append('text')
      .attr('x', width / 2).attr('y', height / 2 - 20)
      .attr('text-anchor', 'middle').attr('fill', '#e0e0e0').attr('font-size', '56px')
      .attr('font-family', 'FontAwesome').text('\uf07b');
    svg.append('text')
      .attr('x', width / 2).attr('y', height / 2 + 30)
      .attr('text-anchor', 'middle').attr('fill', '#999').attr('font-size', '16px')
      .text('暂无地点数据');
    svg.append('text')
      .attr('x', width / 2).attr('y', height / 2 + 55)
      .attr('text-anchor', 'middle').attr('fill', '#bbb').attr('font-size', '13px')
      .text('请先在织网环节添加地点');
    return;
  }

  const virtualRootId = '__virtual_location_root__';
  const renderLocations = [
    { id: virtualRootId, name: '根节点', type: 'root', parent_id: null },
    ...locations.map(loc => ({
      ...loc,
      parent_id: loc.parent_id ? loc.parent_id : virtualRootId
    }))
  ];

  const root = d3.stratify()
    .id(d => d.id)
    .parentId(d => d.parent_id)(renderLocations);

  const treeLayout = d3.tree().nodeSize([180, 120]);
  treeLayout(root);

  const svg = container.append('svg')
    .attr('width', width)
    .attr('height', height)
    .style('background', 'rgba(26, 26, 46, 0.6)');

  const defs = svg.append('defs');

  svg.append('rect')
    .attr('width', width)
    .attr('height', height)
    .attr('fill', 'transparent');

  const g = svg.append('g');

  svg.on('.zoom', null);
  locationZoom = d3.zoom()
    .scaleExtent([0.3, 3])
    .on('zoom', (event) => g.attr('transform', event.transform));
  svg.call(locationZoom);
  svg.call(locationZoom.transform, d3.zoomIdentity.translate(width / 2, 60).scale(1));

  const linkGroup = g.append('g').attr('class', 'links');
  const nodeGroup = g.append('g').attr('class', 'nodes');

  const linkPath = d3.linkVertical().x(d => d.x).y(d => d.y + 25);

  linkGroup.selectAll('.link')
    .data(root.links())
    .enter()
    .append('path')
    .attr('class', 'link location-link')
    .attr('fill', 'none')
    .style('stroke', '#a8c8ff')
    .style('stroke-width', '3px')
    .style('stroke-opacity', '1')
    .attr('d', linkPath);

  const nodeGroups = nodeGroup.selectAll('.node')
    .data(root.descendants())
    .enter()
    .append('g')
    .attr('class', 'node')
    .attr('transform', d => `translate(${d.x},${d.y})`);

  nodeGroups.call(d3.drag()
    .on('start', function(event, d) {
      d._dragging = true;
      d._shakeStart = Date.now();
      event.sourceEvent.stopPropagation();
    })
    .on('drag', function(event, d) {
      d.x = d.x + event.dx;
      d.y = d.y + event.dy;
      d3.select(this).attr('transform', `translate(${d.x},${d.y})`);
      linkGroup.selectAll('.link')
        .attr('d', d3.linkVertical().x(dd => dd.x).y(dd => dd.y + 25));
    })
    .on('end', function(event, d) {
      d._dragging = false;
      d._shakeStart = 0;
      d3.select(this).attr('transform', `translate(${d.x},${d.y})`);
    })
  );

  nodeGroups.append('rect')
    .attr('class', 'card-bg')
    .attr('x', -65).attr('y', -18)
    .attr('width', 130).attr('height', 36)
    .attr('rx', 6).attr('ry', 6)
    .attr('fill', 'rgba(26, 26, 46, 0.8)')
    .attr('stroke', d => {
      const depth = d.depth || 0;
      const idx = depth % DEPTH_BORDER_COLORS.length;
      return DEPTH_BORDER_COLORS[idx];
    })
    .attr('stroke-width', 2)
    .style('pointer-events', 'none');

  nodeGroups.append('rect')
    .attr('class', 'hit-area')
    .attr('x', -65).attr('y', -18)
    .attr('width', 130).attr('height', 36)
    .attr('rx', 6).attr('ry', 6)
    .attr('fill', 'transparent')
    .attr('stroke', 'none');

  nodeGroups.append('text')
    .attr('class', 'node-icon')
    .attr('x', -50).attr('y', 3)
    .attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
    .attr('fill', '#fff').attr('font-size', '18px')
    .attr('font-family', 'FontAwesome')
    .text('\uf3c5')
    .style('pointer-events', 'none');

  nodeGroups.append('text')
    .attr('class', 'node-name')
    .attr('x', -30).attr('y', 3)
    .attr('text-anchor', 'start').attr('dominant-baseline', 'central')
    .attr('fill', '#fff').attr('font-size', '13px').attr('font-weight', '600')
    .attr('width', 80)
    .attr('text-overflow', 'ellipsis')
    .attr('overflow', 'hidden')
    .text(d => {
      const name = d.data.name || '未知';
      return name.length > 8 ? name.substring(0, 8) + '...' : name;
    })
    .style('pointer-events', 'none');

  nodeGroups.on("mouseenter", function(event, d) {
    if (d._dragging) return;
    const el = d3.select(this);

    const gradIdx = getSharedGradientIndex(d.data.id, SHARED_GRADIENTS.length);
    const pair = SHARED_GRADIENTS[gradIdx];

    const gradId = `locGrad-${d.data.id}`;
    let gradDef = defs.select(`#${gradId}`);
    if (gradDef.empty()) {
      gradDef = defs.append('linearGradient').attr('id', gradId)
        .attr('x1', '0%').attr('y1', '0%').attr('x2', '100%').attr('y2', '100%');
      gradDef.append('stop').attr('offset', '0%').attr('stop-color', pair[0]);
      gradDef.append('stop').attr('offset', '100%').attr('stop-color', pair[1]);
    }

    el.select('.card-bg')
      .transition().duration(200)
      .attr('fill', `url(#${gradId})`);

    el.select('.node-name')
      .transition().duration(200)
      .attr('fill', '#fff');

    el.select('.node-icon')
      .transition().duration(200)
      .attr('fill', '#fff');

    const cardBg = el.select('.card-bg');
    cardBg.classed('node-location-shaking', false);
    void this.getBoundingClientRect();
    cardBg.classed('node-location-shaking', true);

    const aliasesDisplay = d.data.aliases && d.data.aliases.length > 0
        ? `<span class="tooltip-alias">（${d.data.aliases.map(a => escapeHtml(a)).join('、')}）</span>`
        : '';

    const attrsEntries = d.data.attributes ? Object.entries(d.data.attributes) : [];
    const attrsDisplay = attrsEntries.length > 0
        ? attrsEntries.map(([k, v]) => `<div class="tooltip-item"><span class="tooltip-label">${escapeHtml(k)}</span><span class="tooltip-value">${escapeHtml(v)}</span></div>`).join('')
        : '';

    tooltip.html(`
      <div class="tooltip-header">
        <span class="tooltip-name">${d.data.name || '未知'}</span>${aliasesDisplay}
      </div>
      <hr class="tooltip-divider">
      <div class="tooltip-item">
        <span class="tooltip-label">类型</span>
        <span class="tooltip-value">${d.data.type || '地点'}</span>
      </div>
      <div class="tooltip-item">
        <span class="tooltip-label">描述</span>
        <span class="tooltip-value">${d.data.description || '-'}</span>
      </div>
      ${attrsDisplay}
    `)
    .style("visibility", "visible")
    .style("opacity", 1)
    .style("background", `linear-gradient(135deg, ${pair[0]} 0%, ${pair[1]} 100%)`);
  })
  .on("mousemove", function(event) {
    tooltip.style("top", (event.pageY + 15) + "px")
             .style("left", (event.pageX + 15) + "px");
  })
  .on("mouseleave", function(event, d) {
    const el = d3.select(this);
    el.select('.card-bg')
      .transition().duration(200)
      .attr('fill', 'rgba(26, 26, 46, 0.8)');
    const cardBg = el.select('.card-bg');
    cardBg.classed('node-location-shaking', false);
    el.select('.node-name')
      .transition().duration(200)
      .attr('fill', '#fff');
    el.select('.node-icon')
      .transition().duration(200)
      .attr('fill', '#fff');

    tooltip.style("visibility", "hidden").style("opacity", 0)
           .style("background", "rgba(26, 26, 46, 0.85)");
  });
}

// ============== 用户设定注入：织网角色/时间/地点/标签 + 剧情核心；与后端 values.py VAL_INJECT_* 完全对齐（SSOT） ==============
// 注意：下方常量仅作为「接口尚未返回/接口失败」时的 fallback 值，实际运行时优先读 window.frontendThresholds（后端 /api/meta/frontend-thresholds 注入），禁止两套值分叉
// 注入配置已从 global.json 移至 values.py，此处 fallback 值需与 values.py 保持一致
const _OUTLINE_CORE_PLOT_MAX_CHARS = 2000;
const _OUTLINE_GLOBAL_PLOT_MAX_CHARS = 1500;
const _OUTLINE_GLOBAL_SUMMARY_MAX_CHARS = 200;
const _OUTLINE_GLOBAL_PLOT_HARD_CHARS = 2000;
const _OUTLINE_GLOBAL_SUMMARY_HARD_CHARS = 300;

// 织网模态框字段级 SSOT：与后端 common/values.py VAL_WEAVE_* 完全对齐，禁止分叉
const _OUTLINE_WEAVE_FIELD_LIMITS_FALLBACK = {
  common: { name: 15, type: 15, aliases: 120, identity: 120, rel_type: 15, attr_key: 15, attr_value: 80 },
  character: { secret: 400, total: 600, max_attrs: 8, max_relations: 99 },
  temporal: { description: 300, total: 250, max_attrs: 5 },
  location: { description: 500, total: 450, max_attrs: 6 },
};

let _frontThresholdsPending = null;
function _loadFrontendThresholdsOnce() {
  if (_frontThresholdsPending) return _frontThresholdsPending;
  _frontThresholdsPending = (async () => {
    try {
      if (typeof window.frontendThresholds !== 'object' || window.frontendThresholds === null) {
        window.frontendThresholds = {};
      }
      if (typeof NovelAPI !== 'undefined' && NovelAPI && typeof NovelAPI.getFrontendThresholds === 'function') {
        const data = await NovelAPI.getFrontendThresholds();
        if (data && typeof data === 'object') {
          window.frontendThresholds = Object.assign({}, window.frontendThresholds, data);
        }
      }
      // 织网字段级上限兜底：若后端没返回（旧缓存/接口失败），用静态 fallback 合并，保证模态框 maxlength 永远有值
      if (typeof window.frontendThresholds.weave_field_limits !== 'object' || window.frontendThresholds.weave_field_limits === null) {
        window.frontendThresholds.weave_field_limits = JSON.parse(JSON.stringify(_OUTLINE_WEAVE_FIELD_LIMITS_FALLBACK));
      } else {
        const wfl = window.frontendThresholds.weave_field_limits;
        const fb = _OUTLINE_WEAVE_FIELD_LIMITS_FALLBACK;
        ['common', 'character', 'temporal', 'location'].forEach((k) => {
          if (typeof wfl[k] !== 'object' || wfl[k] === null) wfl[k] = JSON.parse(JSON.stringify(fb[k]));
          else Object.keys(fb[k]).forEach((fk) => { if (wfl[k][fk] === undefined || wfl[k][fk] === null || wfl[k][fk] === '') wfl[k][fk] = fb[k][fk]; });
        });
      }
    } catch (e) {
      console.warn('[init] 拉取前端阈值接口失败，使用 fallback 常量（不影响功能，值已与后端 SSOT 对齐）:', e?.message || e);
      // 兜底：接口完全失败也要把 weave_field_limits 填上
      if (typeof window.frontendThresholds !== 'object' || window.frontendThresholds === null) window.frontendThresholds = {};
      if (!window.frontendThresholds.weave_field_limits) {
        window.frontendThresholds.weave_field_limits = JSON.parse(JSON.stringify(_OUTLINE_WEAVE_FIELD_LIMITS_FALLBACK));
      }
    } finally {
      // 无论成功失败，刷新一次计数器上限的显示（如果 DOM 存在）
      try {
        const maxSpan = document.getElementById('outlineCharMax');
        if (maxSpan) maxSpan.textContent = String(_getTh('core_plot_max_chars', _OUTLINE_CORE_PLOT_MAX_CHARS));
      } catch (_) {}
      // 兜底：全局剧情/摘要计数，保证阈值加载后分母立即刷新（即使 initOutline 还没走到）
      try {
        if (typeof window.__refreshOutlinePlotCounts === 'function') window.__refreshOutlinePlotCounts();
      } catch (_) {}
    }
    // return 移出 finally：避免吞掉 catch 体可能抛出的异常（finally 内 return 会静默覆盖异常）
    return window.frontendThresholds || {};
  })();
  return _frontThresholdsPending;
}

function _getTh(key, fallbackValue) {
  const def = (fallbackValue === undefined || fallbackValue === null) ? 0 : fallbackValue;
  if (typeof window === 'undefined' || typeof window.frontendThresholds !== 'object' || window.frontendThresholds === null) {
    return def;
  }
  const v = window.frontendThresholds[key];
  if (v === undefined || v === null || v === '') return def;
  if (typeof def === 'number') {
    const n = Number(v);
    return Number.isFinite(n) ? n : def;
  }
  return v;
}
window.__getThreshold = _getTh;
if (typeof window._getTh !== 'function') window._getTh = _getTh;

async function generateGlobalPlotDesign() {
  // 锁与 SSE 竞态由 NovelAPI.runCapabilityWithSSE 统一处理。
  // global_plot_design 是全局类能力（无卷章索引），lockKey 用 capability_id 唯一标识。
  const CAP_ID = NovelAPI.CONST.TASK_TYPE_GLOBAL_OUTLINE;
  const lockKey = `global_${CAP_ID}`;

  if (!window.currentWorkId) {
    showStatus('请先在左侧选择一个作品', 'error');
    return;
  }
  const outlineText = document.getElementById('outlineText');
  const userInput = outlineText ? outlineText.value.trim() : '';
  if (!userInput) {
    showStatus('请先填写故事核心走向描述', 'error');
    return;
  }
  const MAX_CHARS = _getTh('core_plot_max_chars', _OUTLINE_CORE_PLOT_MAX_CHARS);
  if (userInput.length > MAX_CHARS) {
    showStatus(`故事核心走向不能超过${MAX_CHARS}字`, 'error');
    return;
  }

  // 判断是否已有生成结果：有则弹确认框，避免误点直接覆盖
  const saved = window._globalPlotResult || {};
  const hasPlotMem = typeof saved.plot === 'string' && saved.plot.trim().length > 0;
  const hasSummaryMem = typeof saved.summary === 'string' && saved.summary.trim().length > 0;
  const plotEl = document.getElementById('globalPlotText');
  const sumEl = document.getElementById('globalPlotSummary');
  const hasPlotDom = !!(plotEl && typeof plotEl.value === 'string' && plotEl.value.trim().length > 0);
  const hasSumDom = !!(sumEl && typeof sumEl.value === 'string' && sumEl.value.trim().length > 0);
  const hasExisting = hasPlotMem || hasSummaryMem || hasPlotDom || hasSumDom;

  const doReal = async (finalVariables) => {
    const loader = document.getElementById('outlineEyeLoader');
    const genBtn = document.getElementById('generatePlotBtn');
    if (loader) loader.classList.add('running');
    if (genBtn) {
      genBtn.disabled = true;
      genBtn.dataset.oriHtml = genBtn.innerHTML;
      genBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 生成中...';
    }
  try {
    // 先生成前把用户输入的剧情核心持久化，刷新后再进谋篇还能看到
    try { await NovelAPI.upsertCorePlot(window.currentWorkId, userInput); } catch (_e) {
      console.warn('[generateGlobalPlotDesign] 保存剧情核心输入失败（不影响生成）:', _e?.message || _e);
    }
    showStatus('正在生成全局剧情，请稍候...', 'info');
    const variables = (finalVariables && typeof finalVariables === 'object')
      ? Object.assign({}, finalVariables)
      : { core_plot_text: userInput };
    if (typeof variables.core_plot_text !== 'string' || !variables.core_plot_text) {
      variables.core_plot_text = userInput;
    }
    const res = await NovelAPI.runCapabilityWithSSE({
      capabilityId: CAP_ID,
      variables: variables,
      lockKey: lockKey,
    });

    if (res.conflict) {
      showStatus(res.error?.message || '全局剧情正在生成中，请稍候...', 'warning');
      return;
    }
    if (!res.ok) {
      const msg = res.error?.message || '生成失败，请稍后重试';
      console.warn('[generateGlobalPlotDesign] failed:', msg);
      showStatus(`生成全局剧情失败：${msg}`, 'error');
      return;
    }

    // needRefetch：HTTP 失败但 SSE 显示成功，从 task 表重新拉取
    if (res.needRefetch) {
      showStatus('任务已完成，正在加载全局剧情结果...', 'info');
      try {
        const rows = await NovelAPI.listTasks(
          window.currentWorkId,
          NovelAPI.CONST.TASK_TYPE_GLOBAL_OUTLINE,
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
        let plotRaw = '';
        let summaryRaw = '';
        if (content) {
          try {
            const obj = JSON.parse(content);
            if (obj && typeof obj === 'object') {
              if (typeof obj.plot === 'string') plotRaw = obj.plot.trim();
              if (typeof obj.summary === 'string') summaryRaw = obj.summary.trim();
            }
          } catch (_) { /* ignore */ }
        }
        if (!plotRaw && !summaryRaw) {
          showStatus('任务已完成但结果为空，请刷新页面查看', 'warning');
          return;
        }
        // 复用下面的渲染与持久化逻辑
        const PLOT_HARD = _getTh('global_plot_hard_chars', _OUTLINE_GLOBAL_PLOT_HARD_CHARS);
        const SUM_HARD = _getTh('global_summary_hard_chars', _OUTLINE_GLOBAL_SUMMARY_HARD_CHARS);
        const plot = plotRaw.length > PLOT_HARD ? plotRaw.slice(0, PLOT_HARD) : plotRaw;
        const summary = summaryRaw.length > SUM_HARD ? summaryRaw.slice(0, SUM_HARD) : summaryRaw;
        window._globalPlotResult = { plot, summary };
        const plotEl2 = document.getElementById('globalPlotText');
        const summaryEl2 = document.getElementById('globalPlotSummary');
        if (plotEl2) plotEl2.value = plot || '';
        if (summaryEl2) summaryEl2.value = summary || '';
        if (typeof window.__bindOutlineEditableOnce === 'function') window.__bindOutlineEditableOnce();
        if (typeof window.__refreshOutlinePlotCounts === 'function') window.__refreshOutlinePlotCounts();
        const plotBox2 = document.getElementById('globalPlotResult');
        if (plotBox2) {
          plotBox2.style.display = 'block';
          plotBox2.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        refreshOutlineStepActions();
        const taskId = picked && picked.id ? `（任务ID：${picked.id}）` : '';
        showStatus(`全局剧情生成成功${taskId}（已从任务表加载）`, 'success');
        return;
      } catch (e) {
        console.warn('[generateGlobalPlotDesign] refetch failed:', e?.message || e);
        showStatus('任务已完成，刷新页面查看结果', 'info');
        return;
      }
    }

    const resData = res.result;
    if (!resData || !resData.ok) {
      const msg = resData && resData.detail ? String(resData.detail) : '生成失败，请稍后重试';
      showStatus(`生成全局剧情失败：${msg}`, 'error');
      return;
    }
    const payload = (resData && resData.result) ? resData.result : {};
    const plotRaw = (payload && typeof payload.plot === 'string') ? payload.plot.trim() : '';
    const summaryRaw = (payload && typeof payload.summary === 'string') ? payload.summary.trim() : '';
    if (!plotRaw && !summaryRaw) {
      showStatus('模型返回结果为空，请调整核心走向描述后重试', 'error');
      return;
    }
    // 按 HARD 阈值做 UI 层同步截断：保证用户看到的和实际持久化的一致，避免"写了保存后少了"的幻觉
    const PLOT_HARD = _getTh('global_plot_hard_chars', _OUTLINE_GLOBAL_PLOT_HARD_CHARS);
    const SUM_HARD = _getTh('global_summary_hard_chars', _OUTLINE_GLOBAL_SUMMARY_HARD_CHARS);
    const plot = plotRaw.length > PLOT_HARD ? plotRaw.slice(0, PLOT_HARD) : plotRaw;
    const summary = summaryRaw.length > SUM_HARD ? summaryRaw.slice(0, SUM_HARD) : summaryRaw;
    if ((plot.length !== plotRaw.length || summary.length !== summaryRaw.length) && typeof showStatus === 'function') {
      const parts = [];
      if (plot.length !== plotRaw.length) parts.push(`全局剧情超过硬上限 ${PLOT_HARD} 字，已自动舍弃末尾注水内容`);
      if (summary.length !== summaryRaw.length) parts.push(`剧情摘要超过硬上限 ${SUM_HARD} 字，已自动舍弃末尾注水内容`);
      if (parts.length) showStatus(parts.join('；') + '，可手动调整后重新保存。', 'warn');
    }
    window._globalPlotResult = { plot, summary };
    const plotBox = document.getElementById('globalPlotResult');
    const plotEl = document.getElementById('globalPlotText');
    const summaryEl = document.getElementById('globalPlotSummary');
    if (plotEl) plotEl.value = plot || '';
    if (summaryEl) summaryEl.value = summary || '';
    // 自动保存绑定 + 计数刷新（复用 init 逻辑，阈值分母直接走 SSOT）
    if (typeof window.__bindOutlineEditableOnce === 'function') window.__bindOutlineEditableOnce();
    if (typeof window.__refreshOutlinePlotCounts === 'function') window.__refreshOutlinePlotCounts();
    if (plotBox) {
      plotBox.style.display = 'block';
      plotBox.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    const nextBtn = document.getElementById('nextStepBtnOutline');
    refreshOutlineStepActions();
    // 生成结果立即持久化为 outline 任务（同时保证唯一性）
    let persistTip = '';
    try {
      await NovelAPI.upsertOutline(window.currentWorkId, plot, summary);
      const tip = document.getElementById('globalPlotSaveTip');
      if (tip) {
        tip.innerText = '已保存';
        tip.style.color = '#7c3aed';
        tip.style.opacity = '1';
        clearTimeout(tip._t);
        tip._t = setTimeout(() => { tip.style.opacity = '0'; }, 1600);
      }
    } catch (_e) {
      console.warn('[generateGlobalPlotDesign] 保存 outline 任务失败（不影响展示）:', _e?.message || _e);
      persistTip = '（结果未成功写入任务表，请手动保存）';
    }
    const token = (typeof resData.token_cost === 'number') ? resData.token_cost : 0;
    const taskId = resData.task_id ? `（任务ID：${resData.task_id}）` : '';
    showStatus(`全局剧情生成成功${taskId}${persistTip}，共消耗 ${token} tokens，可点击下一步进入分卷`, 'success');
  } catch (err) {
    console.error('[生成全局剧情失败:', err);
    showStatus('生成全局剧情失败，请稍后重试', 'error');
  } finally {
    if (loader) loader.classList.remove('running');
    if (genBtn) {
      if (genBtn.dataset.oriHtml) genBtn.innerHTML = genBtn.dataset.oriHtml;
      refreshOutlineStepActions();
    }
  }
  };

  window.startGenerateFlowWithPreview({
    hasExisting: hasExisting,
    confirmConfig: hasExisting ? {
      title: '确认重新生成',
      message: '当前作品已有生成好的全局剧情/摘要结果，重新生成会覆盖当前内容，是否继续？',
      confirmText: '下一步',
      cancelText: '取消',
    } : null,
    previewConfig: {
      sessionId: window.currentWorkId,
      capabilityId: CAP_ID,
      rawVariables: { core_plot_text: userInput },
    },
    previewRequired: true,
    doReal: doReal,
  });
}

function handleOutlineNextStep() {
  if (!window.currentWorkId) {
    showStatus('请先在左侧选择一个作品', 'error');
    return;
  }
  const saved = window._globalPlotResult || {};
  const hasPlot = (saved.plot && String(saved.plot).trim().length > 0);
  const hasSummary = (saved.summary && String(saved.summary).trim().length > 0);
  if (!hasPlot && !hasSummary) {
    showStatus('请先点击上方「生成全局剧情」按钮并等待生成完成，再进入分卷', 'error');
    const genBtn = document.getElementById('generatePlotBtn');
    if (genBtn) genBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
    return;
  }
  showStatus('已完成谋篇环节，准备进入分卷', 'success');
  if (window.completeStep) {
    completeStep(window.currentWorkId, 2);
  } else {
    handleStepClick(window.currentWorkId, 3);
  }
}

function handleOutlineTextInput(e) {
  const charCountEl = document.getElementById('outlineCharCurrent');
  if (charCountEl) charCountEl.textContent = String(e.target.value.length);
  refreshOutlineStepActions();
}

function refreshOutlineStepActions() {
  const genBtn = document.getElementById('generatePlotBtn');
  const nextBtn = document.getElementById('nextStepBtnOutline');
  const outlineText = document.getElementById('outlineText');

  if (genBtn) {
    if (!window.currentWorkId) {
      genBtn.disabled = true;
      genBtn.title = '请先在左侧选择一个作品';
    } else {
      const hasCore = !!(outlineText && String(outlineText.value || '').trim());
      if (!hasCore) {
        genBtn.disabled = true;
        genBtn.title = '请先填写故事核心走向（何时何地→谁→想做什么→为什么→如何做→阻力→结局）';
      } else {
        genBtn.disabled = false;
        genBtn.title = '基于当前核心剧情生成全局剧情+摘要（唯一最新记录会自动替换旧值）';
      }
    }
  }
  if (nextBtn) {
    if (!window.currentWorkId) {
      nextBtn.disabled = true;
      nextBtn.title = '请先在左侧选择一个作品';
    } else {
      const saved = window._globalPlotResult || {};
      const hasPlot = !!(saved.plot && String(saved.plot).trim());
      const hasSummary = !!(saved.summary && String(saved.summary).trim());
      if (!hasPlot && !hasSummary) {
        nextBtn.disabled = true;
        nextBtn.title = '请先点击左侧「生成全局剧情」并等待完成后再进入分卷';
      } else {
        nextBtn.disabled = false;
        nextBtn.title = '进入分卷环节：基于全局剧情拆分多卷结构与叙事节奏';
      }
    }
  }
}

window.resetOutlinePageIsolatedState = resetOutlinePageIsolatedState;
window.getJellyScale = getJellyScale;
window.getFixedRandomGradientIndex = getFixedRandomGradientIndex;
window.setupVisibilityControl = setupVisibilityControl;
window.initOutlineCanvas = initOutlineCanvas;
window.switchView = switchView;
window.renderView = renderView;
window.transformCharacterData = transformCharacterData;
window.extractRelationships = extractRelationships;
window.generateRealLinks = generateRealLinks;
window.generateSimulatedLinks = generateSimulatedLinks;
window.initForceGraph = initForceGraph;
window.renderForceGraph = renderForceGraph;
window.getTimelineGradient = getTimelineGradient;
window.drawEmptyState = drawEmptyState;
window.renderTimelineList = renderTimelineList;
window.drawTimeline = drawTimeline;
window.bindTimelineHover = bindTimelineHover;
window.renderLocationTree = renderLocationTree;
window.generateGlobalPlotDesign = generateGlobalPlotDesign;
window.handleOutlineNextStep = handleOutlineNextStep;
window.handleOutlineTextInput = handleOutlineTextInput;
window.refreshOutlineStepActions = refreshOutlineStepActions;
})();