const TIMELINE_TOP_FIELDS = ['type', 'sort_index', 'description'];
const _TIME_ATTRS_KNOWN_KEYS = new Set(TIMELINE_TOP_FIELDS);
let _timeAttrPanel = null;

function _getTimeWeaveLimits() {
  const fb = {
    common: { name: 15, type: 15, aliases: 120, identity: 120, rel_type: 15, attr_key: 15, attr_value: 80 },
    temporal: { description: 500, total: 1000, max_attrs: 999 },
  };
  try {
    const wfl = (typeof window !== 'undefined' && window.frontendThresholds) ? window.frontendThresholds.weave_field_limits : null;
    if (wfl && typeof wfl === 'object') {
      const merged = { common: { ...fb.common }, temporal: { ...fb.temporal } };
      if (wfl.common && typeof wfl.common === 'object') Object.keys(fb.common).forEach(k => { if (wfl.common[k] !== undefined && wfl.common[k] !== null) merged.common[k] = Number(wfl.common[k]) || fb.common[k]; });
      if (wfl.temporal && typeof wfl.temporal === 'object') Object.keys(fb.temporal).forEach(k => { if (wfl.temporal[k] !== undefined && wfl.temporal[k] !== null) merged.temporal[k] = Number(wfl.temporal[k]) || fb.temporal[k]; });
      return merged;
    }
  } catch (_) {}
  return fb;
}

function adaptTimelineFromDB(row) {
  const attrs = (row && typeof row.attributes === 'object' && row.attributes) ? { ...row.attributes } : {};
  const tl = {
    id: row.id != null ? row.id : null,
    name: row.name || '',
    aliases: Array.isArray(row.aliases) ? row.aliases : []
  };
  TIMELINE_TOP_FIELDS.forEach(k => {
    if (k in attrs) {
      tl[k] = attrs[k];
      delete attrs[k];
    }
  });
  if (tl.sort_index !== undefined && tl.sort_index !== null && tl.sort_index !== '') {
    const n = Number(tl.sort_index);
    tl.sort_index = isNaN(n) ? (tl.sort_index || 0) : n;
  } else {
    tl.sort_index = 0;
  }
  tl.attributes = attrs;
  return tl;
}

function adaptTimelineToDB(timeline, sessionId) {
  const attrs = { ...(timeline.attributes || {}) };
  TIMELINE_TOP_FIELDS.forEach(k => {
    if (k in timeline && timeline[k] !== undefined && timeline[k] !== null && timeline[k] !== '') {
      attrs[k] = timeline[k];
    }
  });
  return {
    session_id: sessionId,
    category: 'temporal',
    name: timeline.name || '',
    aliases: Array.isArray(timeline.aliases) ? timeline.aliases : [],
    attributes: attrs
  };
}

async function loadTimelines(sessionId) {
  if (!sessionId) return;
  try {
    const list = await NovelAPI.listSemanticVocabularies(sessionId, 'temporal');
    weaveData.timelines = Array.isArray(list) ? list.map(adaptTimelineFromDB) : [];
  } catch (err) {
    console.error('加载时间列表失败:', err);
    showStatus('加载时间列表失败: ' + (err.message || '未知错误'), 'error');
    weaveData.timelines = [];
  }
}

window.loadTimelines = loadTimelines;

function openAddTimeModal() {
  const hasRelationships = weaveData.characters.some(c => c.relationships && c.relationships.length > 0);
  if (!hasRelationships && weaveData.characters.length >= 2) {
    showStatus('提示：请编辑角色添加角色关系，以便正常渲染关系图', 'info');
  }
  openTimelineModal();
}

function renderTimelines() {
  safeExecute(() => {
    const container = document.getElementById('timelinesList');
    if (!container) return;

    if (weaveData.timelines.length === 0) {
      container.innerHTML = '<div class="empty-state"><i class="fas fa-clock"></i><p>暂无时间节点，点击上方按钮添加</p></div>';
      return;
    }

    const sortedTimelines = [...(weaveData.timelines || [])].sort((a, b) => {
      const idA = Number(getCharId(a?.id)) || 0;
      const idB = Number(getCharId(b?.id)) || 0;
      if (idA !== idB) return idA - idB;
      const tA = a?.created_at ? new Date(String(a.created_at)).getTime() : 0;
      const tB = b?.created_at ? new Date(String(b.created_at)).getTime() : 0;
      return tA - tB;
    });

    container.innerHTML = sortedTimelines.map(timeline => {
      const attrsHtml = Object.keys(timeline.attributes || {}).length > 0 ? `
        <div style="margin-top: 12px;">
          <span class="property-label">自定义属性</span>
          <div class="item-properties">
            ${Object.entries(timeline.attributes).map(([key, value]) => `
              <div class="property-item"><span class="property-label">${escapeHtml(key)}</span><span class="property-value">${escapeHtml(value || '-')}</span></div>
            `).join('')}
          </div>
        </div>
      ` : '';

      return `
        <div class="item-card">
          <div class="item-header">
            <div>
              <span class="item-name">${escapeHtml(timeline.name)}</span>
              <span class="item-type">${escapeHtml(timeline.type)}</span>
            </div>
            <div class="item-actions">
              <button class="item-action-btn" onclick="openTimelineModal(${timeline.id})" title="编辑"><i class="fas fa-edit"></i></button>
              <button class="item-action-btn delete-btn" onclick="deleteTimeline(${timeline.id})" title="删除"><i class="fas fa-trash"></i></button>
            </div>
          </div>
          <div class="item-properties">
            <div class="property-item"><span class="property-label">排序</span><span class="property-value">${timeline.sort_index || '-'}</span></div>
            <div class="property-item"><span class="property-label">描述</span><span class="property-value">${escapeHtml(timeline.description || '-')}</span></div>
          </div>
          ${timeline.aliases && timeline.aliases.length > 0 ? `<div style="margin-top: 12px;"><span class="property-label">别名</span><div class="aliases-tag">${timeline.aliases.map(a => `<span class="alias-tag">${escapeHtml(a)}</span>`).join('')}</div></div>` : ''}
          ${attrsHtml}
        </div>
      `;
    }).join('');
  }, '时间列表渲染失败');
}

function openTimelineModal(id = null) {
  editingType = 'timeline';
  editingId = id;

  const timeline = id != null ? weaveData.timelines.find(t => String(t.id) === String(id)) : null;
  if (id != null && !timeline) return;

  const isEdit = !!timeline;
  const title = isEdit ? '编辑时间' : '添加时间';
  const L = _getTimeWeaveLimits();
  const NAME_MAX = L.common.name;
  const TYPE_MAX = L.common.type;
  const ALIASES_MAX = L.common.aliases;
  const DESC_MAX = L.temporal.description;
  const ATTR_KEY_MAX = L.common.attr_key;
  const ATTR_VAL_MAX = L.common.attr_value;
  const MAX_ATTRS = L.temporal.max_attrs;

  document.getElementById('modalOverlay').style.display = 'flex';
  const contentHtml = `
    <div class="modal-content-wrapper">
      <div class="modal-header">
        <h3 class="modal-title">${title}</h3>
        <button class="modal-close" onclick="closeModal()">×</button>
      </div>
      <div class="modal-item-form">
        <div class="form-row-flex">
          <div style="flex:1;">
            <label class="form-label"><span>*</span> 名称（最多 ${NAME_MAX} 字）</label>
            <input type="text" id="timeName" class="form-input"
                   value="${escapeHtml(timeline?.name || '')}"
                   placeholder="${isEdit ? '' : '请输入时间名称'}" maxlength="${NAME_MAX}" />
          </div>
          <div style="flex:1;">
            <label class="form-label"><span>*</span> 类型（最多 ${TYPE_MAX} 字）</label>
            <input type="text" id="timeType" class="form-input"
                   value="${escapeHtml(timeline?.type || '')}"
                   placeholder="${isEdit ? '' : '请输入时间类型'}" maxlength="${TYPE_MAX}" />
          </div>
          <div style="flex:0.8;min-width:120px;">
            <label class="form-label"><span>*</span> 序号</label>
            <input type="number" id="timeSortIndex" class="form-input"
                   value="${timeline?.sort_index ?? ''}"
                   placeholder="${isEdit ? '' : '请输入序号'}" min="0" />
          </div>
        </div>

        <div class="form-row-full"><div>
          <label class="form-label">别名（逗号分隔，总长最多 ${ALIASES_MAX} 字）</label>
          <textarea id="timeAliases" class="form-textarea weave-aliases" style="resize:vertical;"
                    maxlength="${ALIASES_MAX}" placeholder="多个别名用逗号分隔">${escapeHtml(timeline?.aliases ? timeline.aliases.join(',') : '')}</textarea>
        </div></div>

        <div class="form-row-full"><div>
          <label class="form-label"><span>*</span> 描述意义（最多 ${DESC_MAX} 字）</label>
          <textarea id="timeDesc" class="form-textarea weave-timeline-desc" style="resize:vertical;" rows="6"
                    maxlength="${DESC_MAX}" placeholder="请输入描述意义">${escapeHtml(timeline?.description || '')}</textarea>
        </div></div>

        <div class="form-row-full"><div>
          <label class="form-label">自定义属性（最多 ${MAX_ATTRS} 条）</label>
          <div id="timeAttributes"></div>
        </div></div>

        <div class="modal-footer">
          <button class="btn-secondary" onclick="closeModal()">取消</button>
          <button class="btn-primary" onclick="saveTimeline()">保存</button>
        </div>
      </div>
    </div>`;

  const modalContent = document.getElementById('modalContent');
  modalContent.innerHTML = '';
  const fragment = document.createRange().createContextualFragment(contentHtml);
  modalContent.appendChild(fragment);

  const attrContainer = document.getElementById('timeAttributes');
  if (typeof window.CharCounter === 'object' && typeof window.CharCounter.bind === 'function') {
    window.CharCounter.bind('timeDesc', { max: DESC_MAX });
    window.CharCounter.bind('timeAliases', { max: ALIASES_MAX });
  }
  if (attrContainer && typeof initCustomAttributes === 'function') {
    _timeAttrPanel = initCustomAttributes(attrContainer, timeline?.attributes || {}, {
      attrKeyMax: ATTR_KEY_MAX,
      attrValueMax: ATTR_VAL_MAX,
      maxAttributes: MAX_ATTRS,
      knownKeys: _TIME_ATTRS_KNOWN_KEYS,
      labelName: '属性名',
      labelValue: '属性值',
      hintName: `键名（最多 ${ATTR_KEY_MAX} 字）`,
      hintValue: `属性值（最多 ${ATTR_VAL_MAX} 字）`,
    });
  }

  // 新建模态框：异步请求后端计算"下一个可用序号"，填入后用户可直接保存不用手填
  // 编辑：直接用原值回显，不动
  if (!isEdit) {
    const sid = window.currentWorkId;
    if (sid) {
      NovelAPI.getNextTimelineSortIndex(sid, 'temporal').then(nextVal => {
        const input = document.getElementById('timeSortIndex');
        if (input && input.value === '') {
          input.value = String(nextVal);
        }
      }).catch(() => { /* NovelAPI 内部已兜底本地计算，此处静默 */ });
    }
  }
}

async function saveTimeline() {
  const name = document.getElementById('timeName').value.trim();
  const type = document.getElementById('timeType').value.trim();
  const sortIndexInput = document.getElementById('timeSortIndex').value;
  const desc = document.getElementById('timeDesc').value.trim();
  const sessionId = window.currentWorkId;

  if (!sessionId) { showStatus('请先在左侧选择作品', 'error'); return; }
  if (!name) {
    showStatus('请输入时间名称', 'error');
    return;
  }
  if (!type) {
    showStatus('请输入时间类型', 'error');
    return;
  }
  const sortIndexRaw = String(sortIndexInput ?? '').trim();
  const sortIndexNum = Number(sortIndexRaw);
  if (sortIndexRaw === '' || Number.isNaN(sortIndexNum) || !Number.isFinite(sortIndexNum) || sortIndexNum < 0 || !Number.isInteger(sortIndexNum)) {
    showStatus('请输入有效的序号（大于等于0的整数）', 'error');
    return;
  }
  const sortIndex = Math.trunc(sortIndexNum);
  if (!desc) {
    showStatus('请输入描述意义', 'error');
    return;
  }

  const totalChars = _calcTimelineTotal();
  const L = _getTimeWeaveLimits();
  const MAX_CHARS = L.temporal.total;
  if (totalChars > MAX_CHARS) {
    showStatus(`当前合计 ${totalChars} 字符，超过时间上限 ${MAX_CHARS}，请精简字段（优先缩短自定义属性值、别名、描述意义）`, 'error');
    return;
  }

  const timeline = {
    id: editingId,
    name: name,
    type: type,
    sort_index: sortIndex,
    description: desc,
    aliases: parseCommaList(document.getElementById('timeAliases').value),
    attributes: (_timeAttrPanel && typeof _timeAttrPanel.get === 'function') ? _timeAttrPanel.get() : {}
  };

  try {
    if (editingId) {
      const patch = adaptTimelineToDB(timeline, sessionId);
      delete patch.session_id;
      delete patch.category;
      await NovelAPI.updateSemanticVocabulary(String(editingId), patch);
      const index = weaveData.timelines.findIndex(t => String(t.id) === String(editingId));
      if (index !== -1) weaveData.timelines[index] = { ...timeline, id: editingId };
    } else {
      const payload = adaptTimelineToDB(timeline, sessionId);
      await NovelAPI.createSemanticVocabulary(payload);
      await loadTimelines(sessionId);
    }
    renderTimelines();
    closeModal();
    showStatus(`时间「${name}」保存成功`, 'success');
    updateWeaveNextBtn();
  } catch (err) {
    console.error('保存时间失败:', err);
    const backendDetail = err.response && err.response.data && err.response.data.detail;
    const msg = backendDetail
      ? backendDetail
      : `保存时间：${err.message || '未知错误'}`;
    showStatus(msg, 'error');
  }
}

async function deleteTimeline(id) {
  const timeline = weaveData.timelines.find(t => String(t.id) === String(id));
  if (!timeline) return;
  const sessionId = window.currentWorkId;
  if (!sessionId) { showStatus('请先在左侧选择作品', 'error'); return; }

  window.showConfirm({
    title: '确认删除',
    message: `确定要删除时间「${timeline.name}」吗？`,
    confirmText: '删除',
    cancelText: '取消',
    onConfirm: async () => {
      try {
        await NovelAPI.deleteSemanticVocabulary(String(id));
        weaveData.timelines = weaveData.timelines.filter(t => String(t.id) !== String(id));
        renderTimelines();
        showStatus(`时间「${timeline.name}」已删除`, 'success');
        updateWeaveNextBtn();
      } catch (err) {
        console.error('删除时间失败:', err);
        const backendDetail = err.response && err.response.data && err.response.data.detail;
        const msg = backendDetail
          ? backendDetail
          : `删除时间：${err.message || '未知错误'}`;
        showStatus(msg, 'error');
      }
    }
  });
}

function _calcTimelineTotal() {
  let total = 0;
  total += (document.getElementById('timeName')?.value || '').length;
  total += (document.getElementById('timeType')?.value || '').length;
  total += (document.getElementById('timeSortIndex')?.value || '').length;
  total += (document.getElementById('timeAliases')?.value || '').length;
  total += (document.getElementById('timeDesc')?.value || '').length;
  const attrs = document.getElementById('timeAttributes');
  if (attrs) {
    attrs.querySelectorAll(':scope > .attribute-row').forEach(row => {
      const kInput = row.querySelector('.js-attr-key');
      const vInput = row.querySelector('.js-attr-val');
      if (kInput) total += ((kInput.value || '').trim()).length;
      if (vInput) total += ((vInput.value || '').trim()).length;
    });
  }
  return total;
}

window.openAddTimeModal = openAddTimeModal;
window.renderTimelines = renderTimelines;
window.openTimelineModal = openTimelineModal;
window.saveTimeline = saveTimeline;
window.deleteTimeline = deleteTimeline;