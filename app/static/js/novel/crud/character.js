const CHARACTER_TOP_FIELDS = ['type', 'gender', 'identity', 'secret', 'relationships'];
const _CHAR_ATTRS_KNOWN_KEYS = new Set(CHARACTER_TOP_FIELDS);
let _charAttrPanel = null;

function _getCharWeaveLimits() {
  const fb = {
    common: { name: 15, type: 15, aliases: 120, identity: 120, rel_type: 15, attr_key: 15, attr_value: 80 },
    character: { secret: 1000, total: 2000, max_attrs: 999, max_relations: 99 },
  };
  try {
    const wfl = (typeof window !== 'undefined' && window.frontendThresholds) ? window.frontendThresholds.weave_field_limits : null;
    if (wfl && typeof wfl === 'object') {
      const merged = { common: { ...fb.common }, character: { ...fb.character } };
      if (wfl.common && typeof wfl.common === 'object') Object.keys(fb.common).forEach(k => { if (wfl.common[k] !== undefined && wfl.common[k] !== null) merged.common[k] = Number(wfl.common[k]) || fb.common[k]; });
      if (wfl.character && typeof wfl.character === 'object') Object.keys(fb.character).forEach(k => { if (wfl.character[k] !== undefined && wfl.character[k] !== null) merged.character[k] = Number(wfl.character[k]) || fb.character[k]; });
      return merged;
    }
  } catch (_) {}
  return fb;
}

function adaptCharacterFromDB(row) {
  const attrs = (row && typeof row.attributes === 'object' && row.attributes) ? { ...row.attributes } : {};
  const char = {
    id: row.id != null ? row.id : null,
    name: row.name || '',
    aliases: Array.isArray(row.aliases) ? row.aliases : []
  };
  CHARACTER_TOP_FIELDS.forEach(k => {
    if (k in attrs) {
      char[k] = attrs[k];
      delete attrs[k];
    }
  });
  if (!Array.isArray(char.relationships)) char.relationships = [];
  if (!char.gender) char.gender = 'male';
  char.attributes = attrs;
  return char;
}

function adaptCharacterToDB(character, sessionId) {
  const attrs = { ...(character.attributes || {}) };
  CHARACTER_TOP_FIELDS.forEach(k => {
    if (k in character && character[k] !== undefined && character[k] !== null) {
      attrs[k] = character[k];
    }
  });
  return {
    session_id: sessionId,
    category: 'entity',
    name: character.name || '',
    aliases: Array.isArray(character.aliases) ? character.aliases : [],
    attributes: attrs
  };
}

async function loadCharacters(sessionId) {
  if (!sessionId) return;
  try {
    const list = await NovelAPI.listSemanticVocabularies(sessionId, 'entity');
    weaveData.characters = Array.isArray(list) ? list.map(adaptCharacterFromDB) : [];
  } catch (err) {
    console.error('加载角色列表失败:', err);
    showStatus('加载角色列表失败: ' + (err.message || '未知错误'), 'error');
    weaveData.characters = [];
  }
}

window.loadCharacters = loadCharacters;

function renderCharacters() {
  safeExecute(() => {
    const container = document.getElementById('charactersList');
    if (!container) return;

    if (weaveData.characters.length === 0) {
      container.innerHTML = '<div class="empty-state"><i class="fas fa-users"></i><p>暂无角色，点击上方按钮添加</p></div>';
      return;
    }

    const sortedCharacters = [...(weaveData.characters || [])].sort((a, b) => {
      const idA = Number(getCharId(a?.id)) || 0;
      const idB = Number(getCharId(b?.id)) || 0;
      if (idA !== idB) return idA - idB;
      const tA = a?.created_at ? new Date(String(a.created_at)).getTime() : 0;
      const tB = b?.created_at ? new Date(String(b.created_at)).getTime() : 0;
      return tA - tB;
    });

    const fragment = document.createDocumentFragment();
    sortedCharacters.forEach(char => {
      const card = document.createElement('div');
      card.className = 'item-card';

      const attrsHtml = Object.keys(char.attributes || {}).length > 0 ? `
        <div style="margin-top: 12px;">
          <span class="property-label">自定义属性</span>
          <div class="item-properties">
            ${Object.entries(char.attributes).map(([key, value]) => `
              <div class="property-item"><span class="property-label">${escapeHtml(key)}</span><span class="property-value">${escapeHtml(value || '-')}</span></div>
            `).join('')}
          </div>
        </div>
      ` : '';

      card.innerHTML = `
        <div class="item-header">
          <div>
            <span class="item-name">${escapeHtml(char.name)}</span>
            <span class="item-type">${escapeHtml(char.type)}</span>
          </div>
          <div class="item-actions">
            <button class="item-action-btn" onclick="openCharacterModal(${char.id})" title="编辑"><i class="fas fa-edit"></i></button>
            <button class="item-action-btn delete-btn" onclick="deleteCharacter(${char.id})" title="删除"><i class="fas fa-trash"></i></button>
          </div>
        </div>
        <div class="item-properties">
          <div class="property-item"><span class="property-label">性别</span><span class="property-value">${characterPropertyMap.gender[char.gender] || '-'}</span></div>
          <div class="property-item"><span class="property-label">身份</span><span class="property-value">${escapeHtml(char.identity || '-')}</span></div>
          <div class="property-item"><span class="property-label">隐秘</span><span class="property-value">${escapeHtml(char.secret || '-')}</span></div>
        </div>
        ${char.aliases && char.aliases.length > 0 ? `<div style="margin-top: 12px;"><span class="property-label">别名</span><div class="aliases-tag">${char.aliases.map(a => `<span class="alias-tag">${escapeHtml(a)}</span>`).join('')}</div></div>` : ''}
        ${attrsHtml}
      `;
      fragment.appendChild(card);
    });

    container.innerHTML = '';
    container.appendChild(fragment);
  }, '角色列表渲染失败');
}

function renderRelationships() {
  safeExecute(() => {
    const container = document.getElementById('relationshipsList');
    if (!container) return;

    const characters = weaveData.characters || [];
    const allRels = [];

    characters.forEach(char => {
      (char.relationships || []).forEach((rel, index) => {
        const targetChar = findCharacterById(rel.targetId);
        allRels.push({
          sourceId: getCharId(char.id),
          sourceName: char.name,
          targetId: getCharId(rel.targetId),
          targetName: targetChar?.name || '未知角色',
          relIndex: index,
          type: rel.type
        });
      });
    });

    if (allRels.length === 0) {
      container.innerHTML = '<div class="empty-state"><i class="fas fa-project-diagram"></i><p>暂无角色关系，请在角色编辑中添加</p></div>';
      return;
    }

    allRels.sort((a, b) => {
      const sA = Number(a.sourceId) || 0;
      const sB = Number(b.sourceId) || 0;
      if (sA !== sB) return sA - sB;
      return (Number(a.relIndex) || 0) - (Number(b.relIndex) || 0);
    });

    container.innerHTML = allRels.map((rel, i) => `
      <div class="item-card">
        <div class="item-header">
          <div>
            <span class="item-name">${escapeHtml(rel.sourceName)} → ${escapeHtml(rel.targetName)}</span>
            <span class="item-type" style="color: ${getRelationshipColor(rel.type)};">[${escapeHtml(rel.type)}]</span>
          </div>
          <div class="item-actions">
            <button class="item-action-btn" onclick="openCharacterModal(${rel.sourceId})" title="编辑角色"><i class="fas fa-edit"></i></button>
          </div>
        </div>
      </div>
    `).join('');
  }, '角色关系渲染失败');
}

function shouldShowRelationshipSection(char) {
  const rels = char.relationships || [];
  if (rels.length > 0) {
    return true;
  }
  return canAddMoreRelationships(char.id);
}

function renderCharRelationshipsInline(char) {
  const rels = char.relationships || [];
  const characters = weaveData.characters || [];
  const existingTargetIds = getLinkedCharacterIds(char.id);
  const safeCharId = getCharId(char.id);
  const limits = _getCharWeaveLimits();
  const REL_MAX = limits.common.rel_type;
  const MAX_RELS = limits.character.max_relations;
  const relCount = rels.length;
  const isRelMax = typeof MAX_RELS === 'number' && MAX_RELS >= 0 && relCount >= MAX_RELS;

  const rows = rels.map((rel, index) => {
    const safeTargetId = getCharId(rel.targetId || '');
    const availableTargets = characters.filter(c => {
      const cId = getCharId(c.id);
      return cId !== safeCharId && (cId === safeTargetId || !existingTargetIds.has(cId));
    });

    const targetOptions = availableTargets
      .map(c => `<option value="${escapeHtml(getCharId(c.id))}" ${getCharId(c.id) === safeTargetId ? 'selected' : ''}>${escapeHtml(c.name)}</option>`)
      .join('');

    return `
      <div class="attribute-row" data-rel-index="${index}">
        <select class="form-select js-rel-field"
                data-char-id="${safeCharId}"
                data-rel-index="${index}"
                data-field="targetId">
          <option value="">选择目标角色</option>
          ${targetOptions}
        </select>
        <input type="text" class="form-input js-rel-field"
                value="${escapeHtml(rel.type)}"
                placeholder="关系类型（最多 ${REL_MAX} 字）" maxlength="${REL_MAX}"
                data-char-id="${safeCharId}"
                data-rel-index="${index}"
                data-field="type" />
        <button type="button" class="attribute-remove-btn js-rel-remove"
                title="删除此关系"
                data-char-id="${safeCharId}"
                data-rel-index="${index}">
          <i class="fas fa-trash"></i>
        </button>
      </div>`;
  }).join('');

  const addBtn = canAddMoreRelationships(char.id)
    ? `<button type="button" class="attribute-add-btn js-rel-add"
            data-char-id="${safeCharId}">
      <i class="fas fa-plus"></i> 添加关系（最多 ${MAX_RELS} 条，已填 ${relCount}/${MAX_RELS}）
    </button>`
    : `<button type="button" class="attribute-add-btn" disabled title="已达关系条数上限或无可用目标角色">
      <i class="fas fa-ban"></i> 关系已达上限（最多 ${MAX_RELS} 条，已填 ${relCount}/${MAX_RELS}）
    </button>`;

  return `${rows}${addBtn}`;
}

function handleRelFieldChange(e) {
  const el = e.target.closest('.js-rel-field');
  if (!el) return;

  const { charId, relIndex, field } = el.dataset;
  if (charId == null || relIndex == null || !field) return;

  updateRelationshipField(charId, parseInt(relIndex, 10), field, el.value);
}

function handleRelActionClick(e) {
  const removeBtn = e.target.closest('.js-rel-remove');
  if (removeBtn) {
    const { charId, relIndex } = removeBtn.dataset;
    if (charId != null && relIndex != null) {
      removeRelationshipRow(parseInt(charId), parseInt(relIndex));
    }
    return;
  }

  const addBtn = e.target.closest('.js-rel-add');
  if (addBtn) {
    const { charId } = addBtn.dataset;
    if (charId != null) {
      addRelationshipRow(parseInt(charId));
    }
  }
}

function initRelationshipEventDelegation() {
  const container = document.getElementById('modalContent');
  if (!container || container.dataset.relDelegated === 'true') return;

  container.addEventListener('change', handleRelFieldChange);
  container.addEventListener('click', handleRelActionClick);
  container.dataset.relDelegated = 'true';
}

function removeRelationshipEventDelegation() {
  const container = document.getElementById('modalContent');
  if (!container || container.dataset.relDelegated !== 'true') return;

  container.removeEventListener('change', handleRelFieldChange);
  container.removeEventListener('click', handleRelActionClick);
  container.dataset.relDelegated = 'false';
}

function addRelationshipRow(charId) {
  const char = findCharacterById(charId);
  if (!char) return;

  if (!canAddMoreRelationships(charId)) {
    showStatus('该角色已与所有其他角色建立关系', 'info');
    return;
  }

  if (!Array.isArray(char.relationships)) {
    char.relationships = [];
  }

  const hasEmptyRel = char.relationships.some(rel => !rel.targetId && !rel.type);
  if (hasEmptyRel) {
    showStatus('请先填写当前的空关系', 'info');
    return;
  }

  char.relationships.push({ targetId: '', type: '' });

  const modalList = document.getElementById('charRelationshipsList');
  if (modalList) {
    modalList.innerHTML = renderCharRelationshipsInline(char);
    const lastSelect = modalList.querySelector('.attribute-row:last-of-type select');
    if (lastSelect) lastSelect.focus();
  }

  renderRelationships();
}

function updateRelationshipField(charId, relIndex, field, value) {
  const char = findCharacterById(charId);
  if (!char || !char.relationships || !char.relationships[relIndex]) return;

  if (field !== 'targetId') {
    char.relationships[relIndex][field] = value;
    return;
  }

  const safeValue = getCharId(value);

  if (!safeValue) {
    char.relationships[relIndex].targetId = '';
    renderRelationships();
    refreshInlineRelationshipList(char);
    return;
  }

  const targetChar = findCharacterById(safeValue);
  if (!targetChar) {
    console.warn(`[关系校验] 目标角色ID "${safeValue}" 不存在，已忽略本次修改`);
    refreshInlineRelationshipList(char);
    return;
  }

  const linkedIds = getLinkedCharacterIds(charId);
  const currentRowOriginalTarget = getCharId(char.relationships[relIndex].targetId || '');
  const isSameAsBefore = currentRowOriginalTarget === safeValue;
  const isDuplicate = !isSameAsBefore && linkedIds.has(safeValue);

  if (isDuplicate) {
    console.warn(`[关系校验] 角色「${targetChar.name}」已存在关联，已忽略本次修改`);
    showStatus(`「${targetChar.name}」已存在关联，无法重复绑定`, 'info');
    refreshInlineRelationshipList(char);
    return;
  }

  char.relationships[relIndex].targetId = safeValue;
  renderRelationships();
  refreshInlineRelationshipList(char);
}

function removeRelationshipRow(charId, relIndex) {
  const char = findCharacterById(charId);
  if (!char || !char.relationships || relIndex < 0 || relIndex >= char.relationships.length) return;

  char.relationships.splice(relIndex, 1);
  refreshRelationshipViews(char);
}

function refreshRelationshipViews(char) {
  const modalList = document.getElementById('charRelationshipsList');
  if (modalList && editingType === 'character' && editingId === char.id) {
    modalList.innerHTML = renderCharRelationshipsInline(char);
  }
  renderRelationships();
}

function refreshInlineRelationshipList(char) {
  const modalList = document.getElementById('charRelationshipsList');
  if (!modalList) return;

  const activeElement = document.activeElement;
  const focusedRow = activeElement?.closest('.attribute-row');
  const focusedRowIndex = focusedRow ? Array.from(modalList.children).indexOf(focusedRow) : -1;
  const focusedFieldType = activeElement?.tagName === 'SELECT' ? 'select' : 'input';

  modalList.innerHTML = renderCharRelationshipsInline(char);

  if (focusedRowIndex >= 0) {
    const rows = modalList.children;
    if (rows[focusedRowIndex]) {
      const target = rows[focusedRowIndex].querySelector(focusedFieldType);
      if (target) target.focus();
    }
  }
}

function openCharacterModal(id = null) {
  editingType = 'character';
  editingId = id;

  const char = id != null ? weaveData.characters.find(c => String(c.id) === String(id)) : null;
  if (id != null && !char) return;

  if (char && !char.relationships) {
    char.relationships = [];
  }

  if (char && char.relationships.length === 0 && canAddMoreRelationships(char.id)) {
    char.relationships.push({ targetId: '', type: '' });
  }

  const isEdit = !!char;
  const title = isEdit ? '编辑角色' : '添加角色';
  const L = _getCharWeaveLimits();
  const NAME_MAX = L.common.name;
  const TYPE_MAX = L.common.type;
  const IDENTITY_MAX = L.common.identity;
  const ALIASES_MAX = L.common.aliases;
  const SECRET_MAX = L.character.secret;
  const REL_MAX = L.common.rel_type;
  const ATTR_KEY_MAX = L.common.attr_key;
  const ATTR_VAL_MAX = L.common.attr_value;
  const MAX_ATTRS = L.character.max_attrs;
  const MAX_RELS = L.character.max_relations;

  const relationshipSection = (isEdit && shouldShowRelationshipSection(char))
      ? `<div class="form-row-full"><div>
           <label class="form-label">角色关系</label>
           <div id="charRelationshipsList">${renderCharRelationshipsInline(char)}</div>
         </div></div>`
      : '';

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
            <input type="text" id="charName" class="form-input"
                   value="${escapeHtml(char?.name || '')}"
                   placeholder="${isEdit ? '' : '请输入名称'}" maxlength="${NAME_MAX}" />
          </div>
          <div style="flex:1;">
            <label class="form-label"><span>*</span> 类型（最多 ${TYPE_MAX} 字）</label>
            <input type="text" id="charType" class="form-input"
                   value="${escapeHtml(char?.type || '')}"
                   placeholder="${isEdit ? '' : '请输入类型'}" maxlength="${TYPE_MAX}" />
          </div>
          <div style="flex:0.7;min-width:120px;">
            <label class="form-label"><span>*</span> 性别</label>
            <select id="charGender" class="form-select">
              <option value="male" ${char?.gender === 'female' ? '' : 'selected'}>男</option>
              <option value="female" ${char?.gender === 'female' ? 'selected' : ''}>女</option>
            </select>
          </div>
        </div>

        <div class="form-row-full"><div>
          <label class="form-label"><span>*</span> 身份（最多 ${IDENTITY_MAX} 字）</label>
          <textarea id="charIdentity" class="form-textarea weave-identity"
                    style="resize:vertical;"
                    maxlength="${IDENTITY_MAX}" placeholder="${isEdit ? '' : '请输入身份'}">${escapeHtml(char?.identity || '')}</textarea>
        </div></div>

        <div class="form-row-full"><div>
          <label class="form-label">别名（逗号分隔，总长最多 ${ALIASES_MAX} 字）</label>
          <textarea id="charAliases" class="form-textarea weave-aliases" style="resize:vertical;"
                    maxlength="${ALIASES_MAX}" placeholder="多个别名用逗号分隔">${escapeHtml(char?.aliases ? char.aliases.join(',') : '')}</textarea>
        </div></div>

        <div class="form-row-full"><div>
          <label class="form-label"><span>*</span> 隐秘（最多 ${SECRET_MAX} 字）</label>
          <textarea id="charSecret" class="form-textarea weave-secret" style="resize:vertical;" rows="12"
                    maxlength="${SECRET_MAX}" placeholder="${isEdit ? '' : '请输入隐秘'}">${escapeHtml(char?.secret || '')}</textarea>
        </div></div>

        ${relationshipSection}

        <div class="form-row-full"><div>
          <label class="form-label">自定义属性（最多 ${MAX_ATTRS} 条）</label>
          <div id="charAttributes"></div>
        </div></div>

        <div class="modal-footer">
          <button class="btn-secondary" onclick="closeModal()">取消</button>
          <button class="btn-primary" onclick="saveCharacter()">保存</button>
        </div>
      </div>
    </div>`;

  const attrContainer = document.getElementById('charAttributes');
  if (typeof window.CharCounter === 'object' && typeof window.CharCounter.bind === 'function') {
    window.CharCounter.bind('charIdentity', { max: IDENTITY_MAX });
    window.CharCounter.bind('charSecret', { max: SECRET_MAX });
    window.CharCounter.bind('charAliases', { max: ALIASES_MAX });
  }
  if (attrContainer && typeof initCustomAttributes === 'function') {
    _charAttrPanel = initCustomAttributes(attrContainer, char?.attributes || {}, {
      attrKeyMax: ATTR_KEY_MAX,
      attrValueMax: ATTR_VAL_MAX,
      maxAttributes: MAX_ATTRS,
      knownKeys: _CHAR_ATTRS_KNOWN_KEYS,
      labelName: '属性名',
      labelValue: '属性值',
      hintName: `键名（最多 ${ATTR_KEY_MAX} 字）`,
      hintValue: `属性值（最多 ${ATTR_VAL_MAX} 字）`,
    });
  }

  initRelationshipEventDelegation();
}

async function doSaveCharacter(options = {}) {
  const { keepModal = false, autoTriggered = false } = options;
  const name = document.getElementById('charName').value.trim();
  const type = document.getElementById('charType').value.trim();
  const gender = document.getElementById('charGender').value;
  const identity = document.getElementById('charIdentity').value.trim();
  const secret = document.getElementById('charSecret').value.trim();
  const sessionId = window.currentWorkId;

  if (!sessionId) { showStatus('请先在左侧选择作品', 'error'); return false; }
  if (!name) { showStatus('请输入名称', 'error'); return false; }
  if (!type) { showStatus('请输入类型', 'error'); return false; }
  if (!identity) { showStatus('请输入身份', 'error'); return false; }
  if (!secret) { showStatus('请输入隐秘', 'error'); return false; }

  const totalChars = _calcCharacterTotal();
  const L = _getCharWeaveLimits();
  const MAX_CHARS = L.character.total;
  if (totalChars > MAX_CHARS) {
    showStatus(`当前合计 ${totalChars} 字符，超过角色上限 ${MAX_CHARS}，请精简字段（优先缩短自定义属性值、关系类型、别名、隐秘）`, 'error');
    return false;
  }

  let relationships = [];
  if (editingId) {
    const existingChar = weaveData.characters.find(c => String(c.id) === String(editingId));
    if (existingChar) relationships = existingChar.relationships || [];
  }

  const charId = editingId;
  const seenInCurrent = new Set();

  for (const rel of relationships) {
    if (!rel.targetId || !rel.type) continue;
    const safeTargetId = String(rel.targetId);

    if (seenInCurrent.has(safeTargetId)) {
      const targetChar = weaveData.characters.find(c => String(c.id) === safeTargetId);
      showStatus(`角色「${targetChar?.name || '未知角色'}」在本次编辑中存在重复关系`, 'error');
      return false;
    }

    const alreadyLinked = getLinkedCharacterIds(charId ?? 'temp-create');
    const wasAlreadyLinked = editingId &&
      weaveData.characters.find(c => String(c.id) === String(charId))?.relationships
        ?.some(r => String(r.targetId) === safeTargetId);

    if (!wasAlreadyLinked && alreadyLinked.has(safeTargetId)) {
      const targetChar = weaveData.characters.find(c => String(c.id) === safeTargetId);
      showStatus(`角色「${targetChar?.name || '未知角色'}」已与当前角色存在关系，无法重复添加`, 'error');
      return false;
    }

    seenInCurrent.add(safeTargetId);
  }

  const character = {
    id: charId,
    name, type, gender, identity, secret,
    aliases: parseCommaList(document.getElementById('charAliases').value),
    relationships,
    attributes: (_charAttrPanel && typeof _charAttrPanel.get === 'function') ? _charAttrPanel.get() : {}
  };

  try {
    if (editingId) {
      const patch = adaptCharacterToDB(character, sessionId);
      delete patch.session_id;
      delete patch.category;
      await NovelAPI.updateSemanticVocabulary(String(editingId), patch);
      const index = weaveData.characters.findIndex(c => String(c.id) === String(editingId));
      if (index !== -1) weaveData.characters[index] = { ...character, id: editingId };
    } else {
      const payload = adaptCharacterToDB(character, sessionId);
      await NovelAPI.createSemanticVocabulary(payload);
      await loadCharacters(sessionId);
    }
    renderCharacters();
    renderRelationships();
    if (!keepModal) closeModal();
    if (!autoTriggered) showStatus(`角色「${name}」保存成功`, 'success');
    updateWeaveNextBtn();
    return true;
  } catch (err) {
    console.error('保存角色失败:', err);
    const backendDetail = err.response && err.response.data && err.response.data.detail;
    const msg = backendDetail
      ? backendDetail
      : `保存角色：${err.message || '未知错误'}`;
    showStatus(msg, 'error');
    return false;
  }
}

async function saveCharacter() {
  return doSaveCharacter();
}

async function saveCharacterByMemory(char) {
  if (!char || !char.id) return false;
  const sessionId = window.currentWorkId;
  if (!sessionId) { showStatus('请先在左侧选择作品', 'error'); return false; }
  try {
    const patch = adaptCharacterToDB(char, sessionId);
    delete patch.session_id;
    delete patch.category;
    await NovelAPI.updateSemanticVocabulary(String(char.id), patch);
    const index = weaveData.characters.findIndex(c => String(c.id) === String(char.id));
    if (index !== -1) weaveData.characters[index] = { ...char };
    renderCharacters();
    renderRelationships();
    updateWeaveNextBtn();
    return true;
  } catch (err) {
    console.error('同步保存角色失败:', err);
    const backendDetail = err.response && err.response.data && err.response.data.detail;
    const msg = backendDetail
      ? backendDetail
      : `保存角色：${err.message || '未知错误'}`;
    showStatus(msg, 'error');
    return false;
  }
}

async function deleteCharacter(id) {
  const char = weaveData.characters.find(c => String(c.id) === String(id));
  if (!char) return;
  const sessionId = window.currentWorkId;
  if (!sessionId) { showStatus('请先在左侧选择作品', 'error'); return; }

  const ownRelCount = (char.relationships || []).length;

  let otherRelCount = 0;
  weaveData.characters.forEach(c => {
    if (String(c.id) !== String(id)) {
      otherRelCount += (c.relationships || []).filter(r => String(r.targetId) === String(id)).length;
    }
  });

  const totalRelCount = ownRelCount + otherRelCount;

  window.showConfirm({
    title: '确认删除',
    message: totalRelCount > 0
      ? `删除角色「${char.name}」将同时删除 ${totalRelCount} 条相关关系，确定继续吗？`
      : `确定要删除角色「${char.name}」吗？`,
    confirmText: '删除',
    cancelText: '取消',
    onConfirm: async () => {
      try {
        await NovelAPI.deleteSemanticVocabulary(String(id));
        weaveData.characters = weaveData.characters.filter(c => String(c.id) !== String(id));
        weaveData.characters.forEach(c => {
          if (c.relationships) {
            c.relationships = c.relationships.filter(r => String(r.targetId) !== String(id));
          }
        });
        renderCharacters();
        renderRelationships();
        showStatus(`角色「${char.name}」已删除${totalRelCount > 0 ? `，同时删除 ${totalRelCount} 条关系` : ''}`, 'success');
        updateWeaveNextBtn();
      } catch (err) {
        console.error('删除角色失败:', err);
        const backendDetail = err.response && err.response.data && err.response.data.detail;
        const msg = backendDetail
          ? backendDetail
          : `删除角色：${err.message || '未知错误'}`;
        showStatus(msg, 'error');
      }
    }
  });
}

function _calcCharacterTotal() {
  let total = 0;
  total += (document.getElementById('charName')?.value || '').length;
  total += (document.getElementById('charType')?.value || '').length;
  total += (document.getElementById('charGender')?.value || '').length;
  total += (document.getElementById('charIdentity')?.value || '').length;
  total += (document.getElementById('charAliases')?.value || '').length;
  total += (document.getElementById('charSecret')?.value || '').length;
  const attrs = document.getElementById('charAttributes');
  if (attrs) {
    attrs.querySelectorAll(':scope > .attribute-row').forEach(row => {
      const kInput = row.querySelector('.js-attr-key');
      const vInput = row.querySelector('.js-attr-val');
      if (kInput) total += ((kInput.value || '').trim()).length;
      if (vInput) total += ((vInput.value || '').trim()).length;
    });
  }
  const rels = document.getElementById('charRelationshipsList');
  if (rels) {
    rels.querySelectorAll('input, select').forEach(el => {
      if (el.tagName === 'SELECT') {
        total += ((el.value || '').trim()).length;
      } else if (el.tagName === 'INPUT' && el.id !== 'charRelationshipTargetSearch') {
        total += ((el.value || '').trim()).length;
      }
    });
  }
  return total;
}

window.renderCharacters = renderCharacters;
window.renderRelationships = renderRelationships;
window.shouldShowRelationshipSection = shouldShowRelationshipSection;
window.renderCharRelationshipsInline = renderCharRelationshipsInline;
window.handleRelFieldChange = handleRelFieldChange;
window.handleRelActionClick = handleRelActionClick;
window.initRelationshipEventDelegation = initRelationshipEventDelegation;
window.removeRelationshipEventDelegation = removeRelationshipEventDelegation;
window.openCharacterModal = openCharacterModal;
window.doSaveCharacter = doSaveCharacter;
window.saveCharacter = saveCharacter;
window.saveCharacterByMemory = saveCharacterByMemory;
window.deleteCharacter = deleteCharacter;