const LOCATION_TOP_FIELDS = ['type', 'parent_id', 'description'];
const _LOC_ATTRS_KNOWN_KEYS = new Set(LOCATION_TOP_FIELDS);
let _locAttrPanel = null;

function _getLocWeaveLimits() {
  const fb = {
    common: { name: 15, type: 15, aliases: 120, identity: 120, rel_type: 15, attr_key: 15, attr_value: 80 },
    location: { description: 1000, total: 2000, max_attrs: 999 },
  };
  try {
    const wfl = (typeof window !== 'undefined' && window.frontendThresholds) ? window.frontendThresholds.weave_field_limits : null;
    if (wfl && typeof wfl === 'object') {
      const merged = { common: { ...fb.common }, location: { ...fb.location } };
      if (wfl.common && typeof wfl.common === 'object') Object.keys(fb.common).forEach(k => { if (wfl.common[k] !== undefined && wfl.common[k] !== null) merged.common[k] = Number(wfl.common[k]) || fb.common[k]; });
      if (wfl.location && typeof wfl.location === 'object') Object.keys(fb.location).forEach(k => { if (wfl.location[k] !== undefined && wfl.location[k] !== null) merged.location[k] = Number(wfl.location[k]) || fb.location[k]; });
      return merged;
    }
  } catch (_) {}
  return fb;
}

function adaptLocationFromDB(row) {
  const attrs = (row && typeof row.attributes === 'object' && row.attributes) ? { ...row.attributes } : {};
  const loc = {
    id: row.id != null ? row.id : null,
    name: row.name || '',
    aliases: Array.isArray(row.aliases) ? row.aliases : []
  };
  LOCATION_TOP_FIELDS.forEach(k => {
    if (k in attrs) {
      loc[k] = attrs[k];
      delete attrs[k];
    }
  });
  if (loc.parent_id !== undefined && loc.parent_id !== null && loc.parent_id !== '') {
    const n = Number(loc.parent_id);
    loc.parent_id = isNaN(n) ? loc.parent_id : n;
  } else {
    loc.parent_id = null;
  }
  loc.attributes = attrs;
  return loc;
}

function adaptLocationToDB(location, sessionId) {
  const attrs = { ...(location.attributes || {}) };
  LOCATION_TOP_FIELDS.forEach(k => {
    if (k in location && location[k] !== undefined && location[k] !== null && location[k] !== '') {
      attrs[k] = location[k];
    }
  });
  return {
    session_id: sessionId,
    category: 'location',
    name: location.name || '',
    aliases: Array.isArray(location.aliases) ? location.aliases : [],
    attributes: attrs
  };
}

async function loadLocations(sessionId) {
  if (!sessionId) return;
  try {
    const list = await NovelAPI.listSemanticVocabularies(sessionId, 'location');
    weaveData.locations = Array.isArray(list) ? list.map(adaptLocationFromDB) : [];
  } catch (err) {
    console.error('加载地点列表失败:', err);
    showStatus('加载地点列表失败: ' + (err.message || '未知错误'), 'error');
    weaveData.locations = [];
  }
}

window.loadLocations = loadLocations;

function renderLocations() {
  safeExecute(() => {
    const container = document.getElementById('locationsList');
    if (!container) return;

    if (weaveData.locations.length === 0) {
      container.innerHTML = '<div class="empty-state"><i class="fas fa-map-marker-alt"></i><p>暂无地点，点击上方按钮添加</p></div>';
      return;
    }

    const sortedLocations = [...(weaveData.locations || [])].sort((a, b) => {
      const idA = Number(getCharId(a?.id)) || 0;
      const idB = Number(getCharId(b?.id)) || 0;
      if (idA !== idB) return idA - idB;
      const tA = a?.created_at ? new Date(String(a.created_at)).getTime() : 0;
      const tB = b?.created_at ? new Date(String(b.created_at)).getTime() : 0;
      return tA - tB;
    });

    container.innerHTML = sortedLocations.map(loc => {
      const attrsHtml = Object.keys(loc.attributes || {}).length > 0 ? `
        <div style="margin-top: 12px;">
          <span class="property-label">自定义属性</span>
          <div class="item-properties">
            ${Object.entries(loc.attributes).map(([key, value]) => `
              <div class="property-item"><span class="property-label">${escapeHtml(key)}</span><span class="property-value">${escapeHtml(value || '-')}</span></div>
            `).join('')}
          </div>
        </div>
      ` : '';

      const parentName = loc.parent_id
        ? weaveData.locations.find(p => String(p.id) === String(loc.parent_id))?.name || '-'
        : '-';

      return `
        <div class="item-card">
          <div class="item-header">
            <div>
              <span class="item-name">${escapeHtml(loc.name)}</span>
              <span class="item-type">${escapeHtml(loc.type)}</span>
            </div>
            <div class="item-actions">
              <button class="item-action-btn" onclick="openLocationModal(${loc.id})" title="编辑"><i class="fas fa-edit"></i></button>
              <button class="item-action-btn delete-btn" onclick="deleteLocation(${loc.id})" title="删除"><i class="fas fa-trash"></i></button>
            </div>
          </div>
          <div class="item-properties">
            <div class="property-item"><span class="property-label">归属</span><span class="property-value">${escapeHtml(parentName)}</span></div>
            <div class="property-item"><span class="property-label">描述意义</span><span class="property-value">${escapeHtml(loc.description || '-')}</span></div>
          </div>
          ${loc.aliases && loc.aliases.length > 0 ? `<div style="margin-top: 12px;"><span class="property-label">别名</span><div class="aliases-tag">${loc.aliases.map(a => `<span class="alias-tag">${escapeHtml(a)}</span>`).join('')}</div></div>` : ''}
          ${attrsHtml}
        </div>
      `;
    }).join('');
  }, '地点列表渲染失败');
}

function openLocationModal(id = null) {
  editingType = 'location';
  editingId = id;

  const location = id != null ? weaveData.locations.find(l => String(l.id) === String(id)) : null;
  if (id != null && !location) return;

  const isEdit = !!location;
  const title = isEdit ? '编辑地点' : '添加地点';
  const L = _getLocWeaveLimits();
  const NAME_MAX = L.common.name;
  const TYPE_MAX = L.common.type;
  const ALIASES_MAX = L.common.aliases;
  const DESC_MAX = L.location.description;
  const ATTR_KEY_MAX = L.common.attr_key;
  const ATTR_VAL_MAX = L.common.attr_value;
  const MAX_ATTRS = L.location.max_attrs;

  const parentOptions = [...(weaveData.locations || [])]
    .filter(l => String(l.id) !== String(id))
    .sort((a, b) => (Number(getCharId(a?.id)) || 0) - (Number(getCharId(b?.id)) || 0))
    .map(p => `<option value="${p.id}" ${String(location?.parent_id) === String(p.id) ? 'selected' : ''}>${escapeHtml(p.name)}</option>`)
    .join('');

  document.getElementById('modalOverlay').style.display = 'flex';
  document.getElementById('modalContent').innerHTML = `
    <div class="modal-content-wrapper">
      <div class="modal-header">
        <h3 class="modal-title">${title}</h3>
        <button class="modal-close" onclick="closeModal()">×</button>
      </div>
      <div class="modal-item-form">
        <div class="form-row-flex">
          <div style="flex:1;">
            <label class="form-label"><span>*</span> 名称（最多 ${NAME_MAX} 字）</label>
            <input type="text" id="locName" class="form-input"
                   value="${escapeHtml(location?.name || '')}"
                   placeholder="${isEdit ? '' : '请输入地点名称'}" maxlength="${NAME_MAX}" />
          </div>
          <div style="flex:1;">
            <label class="form-label"><span>*</span> 类型（最多 ${TYPE_MAX} 字）</label>
            <input type="text" id="locType" class="form-input"
                   value="${escapeHtml(location?.type || '')}"
                   placeholder="${isEdit ? '' : '请输入地点类型'}" maxlength="${TYPE_MAX}" />
          </div>
          <div style="flex:1;min-width:140px;">
            <label class="form-label">归属</label>
            <select id="locParentId" class="form-select">
              <option value="">无</option>
              ${parentOptions}
            </select>
          </div>
        </div>

        <div class="form-row-full"><div>
          <label class="form-label">别名（逗号分隔，总长最多 ${ALIASES_MAX} 字）</label>
          <textarea id="locAliases" class="form-textarea weave-aliases" style="resize:vertical;"
                    maxlength="${ALIASES_MAX}" placeholder="多个别名用逗号分隔">${escapeHtml(location?.aliases ? location.aliases.join(',') : '')}</textarea>
        </div></div>

        <div class="form-row-full"><div>
          <label class="form-label"><span>*</span> 描述意义（最多 ${DESC_MAX} 字）</label>
          <textarea id="locDesc" class="form-textarea weave-location-desc" style="resize:vertical;" rows="12"
                    maxlength="${DESC_MAX}" placeholder="请输入描述意义">${escapeHtml(location?.description || '')}</textarea>
        </div></div>

        <div class="form-row-full"><div>
          <label class="form-label">自定义属性（最多 ${MAX_ATTRS} 条）</label>
          <div id="locAttributes"></div>
        </div></div>

        <div class="modal-footer">
          <button class="btn-secondary" onclick="closeModal()">取消</button>
          <button class="btn-primary" onclick="saveLocation()">保存</button>
        </div>
      </div>
    </div>`;

  const attrContainer = document.getElementById('locAttributes');
  if (typeof window.CharCounter === 'object' && typeof window.CharCounter.bind === 'function') {
    window.CharCounter.bind('locDesc', { max: DESC_MAX });
    window.CharCounter.bind('locAliases', { max: ALIASES_MAX });
  }
  if (attrContainer && typeof initCustomAttributes === 'function') {
    _locAttrPanel = initCustomAttributes(attrContainer, location?.attributes || {}, {
      attrKeyMax: ATTR_KEY_MAX,
      attrValueMax: ATTR_VAL_MAX,
      maxAttributes: MAX_ATTRS,
      knownKeys: _LOC_ATTRS_KNOWN_KEYS,
      labelName: '属性名',
      labelValue: '属性值',
      hintName: `键名（最多 ${ATTR_KEY_MAX} 字）`,
      hintValue: `属性值（最多 ${ATTR_VAL_MAX} 字）`,
    });
  }
}

async function doSaveLocation(options = {}) {
  const { keepModal = false, autoTriggered = false } = options;
  const name = document.getElementById('locName').value.trim();
  const type = document.getElementById('locType').value.trim();
  const description = document.getElementById('locDesc').value.trim();
  const parentIdValue = document.getElementById('locParentId').value;
  const sessionId = window.currentWorkId;

  if (!sessionId) { showStatus('请先在左侧选择作品', 'error'); return false; }
  if (!name) { showStatus('请输入名称', 'error'); return false; }
  if (!type) { showStatus('请输入类型', 'error'); return false; }
  if (!description) { showStatus('请输入描述意义', 'error'); return false; }

  const totalChars = _calcLocationTotal();
  const L = _getLocWeaveLimits();
  const MAX_CHARS = L.location.total;
  if (totalChars > MAX_CHARS) {
    showStatus(`当前合计 ${totalChars} 字符，超过地点上限 ${MAX_CHARS}，请精简字段（优先缩短自定义属性值、别名、描述意义）`, 'error');
    return false;
  }

  const location = {
    id: editingId,
    name: name,
    type: type,
    parent_id: parentIdValue ? parseInt(parentIdValue, 10) : null,
    description: description,
    aliases: parseCommaList(document.getElementById('locAliases').value),
    attributes: (_locAttrPanel && typeof _locAttrPanel.get === 'function') ? _locAttrPanel.get() : {}
  };

  try {
    if (editingId) {
      const patch = adaptLocationToDB(location, sessionId);
      delete patch.session_id;
      delete patch.category;
      await NovelAPI.updateSemanticVocabulary(String(editingId), patch);
      const index = weaveData.locations.findIndex(l => String(l.id) === String(editingId));
      if (index !== -1) weaveData.locations[index] = { ...location, id: editingId };
    } else {
      const payload = adaptLocationToDB(location, sessionId);
      await NovelAPI.createSemanticVocabulary(payload);
      await loadLocations(sessionId);
    }
    renderLocations();
    if (!keepModal) closeModal();
    if (!autoTriggered) showStatus(`地点「${name}」保存成功`, 'success');
    updateWeaveNextBtn();
    return true;
  } catch (err) {
    console.error('保存地点失败:', err);
    const backendDetail = err.response && err.response.data && err.response.data.detail;
    const msg = backendDetail
      ? backendDetail
      : `保存地点：${err.message || '未知错误'}`;
    showStatus(msg, 'error');
    return false;
  }
}

async function saveLocation() {
  return doSaveLocation();
}

async function deleteLocation(id) {
  const loc = weaveData.locations.find(l => String(l.id) === String(id));
  if (!loc) return;
  const sessionId = window.currentWorkId;
  if (!sessionId) { showStatus('请先在左侧选择作品', 'error'); return; }

  const hasChildren = weaveData.locations.some(l => String(l.parent_id) === String(id));
  if (hasChildren) {
    showStatus('该地点下存在子地点，无法删除', 'error');
    return;
  }

  window.showConfirm({
    title: '确认删除',
    message: `确定要删除地点「${loc.name}」吗？`,
    confirmText: '删除',
    cancelText: '取消',
    onConfirm: async () => {
      try {
        await NovelAPI.deleteSemanticVocabulary(String(id));
        weaveData.locations = weaveData.locations.filter(l => String(l.id) !== String(id));
        renderLocations();
        showStatus(`地点「${loc.name}」已删除`, 'success');
        updateWeaveNextBtn();
      } catch (err) {
        console.error('删除地点失败:', err);
        const backendDetail = err.response && err.response.data && err.response.data.detail;
        const msg = backendDetail
          ? backendDetail
          : `删除地点：${err.message || '未知错误'}`;
        showStatus(msg, 'error');
      }
    }
  });
}

function _calcLocationTotal() {
  let total = 0;
  total += (document.getElementById('locName')?.value || '').length;
  total += (document.getElementById('locType')?.value || '').length;
  total += (document.getElementById('locParentId')?.value || '').length;
  total += (document.getElementById('locAliases')?.value || '').length;
  total += (document.getElementById('locDesc')?.value || '').length;
  const attrs = document.getElementById('locAttributes');
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

window.renderLocations = renderLocations;
window.openLocationModal = openLocationModal;
window.doSaveLocation = doSaveLocation;
window.saveLocation = saveLocation;
window.deleteLocation = deleteLocation;