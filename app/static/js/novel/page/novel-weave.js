(function(){
const LABEL_CATEGORY_TO_CONTAINER = {
  subject: 'genreTags',
  style: 'styleTags',
  length: 'lengthTags'
};

const LABEL_CATEGORY_TO_WEAVE_KEY = {
  subject: 'genre',
  style: 'style',
  length: 'length'
};

const LABEL_CATEGORY_SINGLE_SELECT = {
  subject: true,
  length: true,
  style: false
};

const LABEL_CATEGORY_TO_LABEL = {
  subject: '题材',
  style: '风格',
  length: '篇幅'
};

let literaryDimensionsCache = null;
let currentLabelConfig = { label_categories: { subject: [], style: [], length: [] }, forbidden_tags: [] };

/**
 * 织网节点切作品时，先把作品级隔离的全局单例重置为干净默认值。
 * 标签配置、标签选择、角色/时间/地点都属于【作品级隔离】数据，
 * 若不先清空再加载，新作品未命中接口时会直接复用旧作品的内存态，
 * 造成「新作品显示其他作品的标签/角色」错觉。
 */
function resetWeaveWorkIsolatedState() {
  // 1) 标签配置（可选标签列表）：重置为空，等待 loadLabelConfig 从后端加载
  currentLabelConfig = { label_categories: { subject: [], style: [], length: [] }, forbidden_tags: [] };
  // 2) 标签选择（已勾选状态 / 雷点选择）：与 weaveData 联动，切作品必须清空
  if (window.weaveData) {
    weaveData.genre = '';
    weaveData.style = [];
    weaveData.length = '';
    weaveData.taboo = [];
    // 3) 角色/时间/地点：同样作品级隔离，切作品清空
    weaveData.characters = [];
    weaveData.timelines = [];
    weaveData.locations = [];
    weaveData.nextId = { character: 1, timeline: 1, location: 1 };
  }
}

function generateTagId(name) {
  const s = String(name || 'tag').trim().toLowerCase().replace(/[\s\-]+/g, '_').replace(/[^a-z0-9_]/g, '') || 'tag';
  let h = 2166136261;
  for (let i = 0; i < name.length; i++) { h ^= name.charCodeAt(i); h = Math.imul(h, 16777619); }
  return s + '_' + (h >>> 0).toString(36).slice(0, 3);
}

async function loadLiteraryDimensions() {
  if (literaryDimensionsCache) return literaryDimensionsCache;
  try {
    const res = await axios.get('/api/literary-dimensions/');
    literaryDimensionsCache = Array.isArray(res.data) ? res.data : [];
  } catch (e) {
    if (e && e.__isCancel) return literaryDimensionsCache || [];
    console.error('[文学维度] 加载失败:', e);
    showStatus('文学维度加载失败', 'error');
    literaryDimensionsCache = [];
  }
  return literaryDimensionsCache;
}

async function loadLabelConfig(sessionId) {
  try {
    const res = await axios.get(`/api/label-configs/${encodeURIComponent(sessionId)}`);
    const payload = res.data || {};
    let parsed = { label_categories: { subject: [], style: [], length: [] }, forbidden_tags: [] };
    if (payload.config_json && typeof payload.config_json === 'string') {
      try {
        parsed = JSON.parse(payload.config_json);
      } catch (e) {
        console.error('[标签配置] config_json 解析失败:', e);
      }
    } else if (payload.config_json && typeof payload.config_json === 'object') {
      parsed = payload.config_json;
    }
    if (!parsed.label_categories) parsed.label_categories = { subject: [], style: [], length: [] };
    ['subject', 'style', 'length'].forEach(k => {
      if (!Array.isArray(parsed.label_categories[k])) parsed.label_categories[k] = [];
    });
    if (!Array.isArray(parsed.forbidden_tags)) parsed.forbidden_tags = [];
    currentLabelConfig = parsed;
    return parsed;
  } catch (e) {
    if (e && e.__isCancel) return currentLabelConfig;
    console.error('[标签配置] 加载失败:', e);
    showStatus('标签配置加载失败', 'error');
    return currentLabelConfig;
  }
}

async function loadLabelSelection(sessionId) {
  try {
    const res = await axios.get(`/api/label-selections/${encodeURIComponent(sessionId)}`);
    const payload = res.data || null;
    // 新作品尚无选择记录 → 显式清空，避免 early return 时 weaveData 残留旧作品已选标签
    if (!payload) {
      weaveData.genre = '';
      weaveData.style = [];
      weaveData.length = '';
      weaveData.taboo = [];
      return;
    }
    const selected = payload.selected_labels && typeof payload.selected_labels === 'object'
      ? payload.selected_labels
      : {};
    weaveData.genre = selected.subject ? String(selected.subject) : '';
    weaveData.style = Array.isArray(selected.style) ? selected.style.map(String) : [];
    weaveData.length = selected.length ? String(selected.length) : '';
    weaveData.taboo = Array.isArray(payload.forbidden_tags) ? payload.forbidden_tags.map(String) : [];
  } catch (e) {
    if (e && e.__isCancel) return;
    if (e.response && e.response.status !== 404) {
      console.error('[标签选择] 加载失败:', e);
    } else {
      // 404 = 新作品未选过 → 同样清空，避免旧状态残留
      weaveData.genre = '';
      weaveData.style = [];
      weaveData.length = '';
      weaveData.taboo = [];
    }
  }
}

async function saveLabelSelection(sessionId) {
  const patch = {
    selected_labels: {
      subject: weaveData.genre || '',
      style: Array.isArray(weaveData.style) ? weaveData.style : [],
      length: weaveData.length || ''
    },
    forbidden_tags: Array.isArray(weaveData.taboo) ? weaveData.taboo : []
  };
  try {
    await axios.patch(`/api/label-selections/${encodeURIComponent(sessionId)}`, patch);
  } catch (e) {
    if (e && e.__isCancel) return;
    console.error('[标签选择] 保存失败:', e);
    showStatus('标签选择保存失败', 'error');
  }
}

async function saveLabelConfig(sessionId) {
  const configJsonStr = JSON.stringify(currentLabelConfig, null, 2);
  try {
    await axios.patch(`/api/label-configs/${encodeURIComponent(sessionId)}`, {
      config_json: configJsonStr
    });
  } catch (e) {
    if (e && e.__isCancel) throw e;
    console.error('[标签配置] 保存失败:', e);
    showStatus('标签配置保存失败', 'error');
    throw e;
  }
}

function renderAllTags() {
  ['subject', 'style', 'length'].forEach(category => {
    const containerId = LABEL_CATEGORY_TO_CONTAINER[category];
    const container = document.getElementById(containerId);
    if (!container) return;
    const items = currentLabelConfig.label_categories[category] || [];
    container.innerHTML = items.map(item => {
      return `<span class="tag-item" style="position:relative; padding-right:22px;" data-id="${escapeHtml(item.id)}" data-name="${escapeHtml(item.name)}" title="${escapeHtml(item.name)}">
        ${escapeHtml(item.name)}
        <span class="tag-delete-btn" data-act="delete" style="position:absolute; top:50%; right:4px; transform:translateY(-50%); width:16px; height:16px; line-height:14px; text-align:center; font-size:14px; font-weight:700; color:#9ca3af; background:#f3f4f6; border-radius:50%; cursor:pointer; user-select:none;" title="删除标签">×</span>
      </span>`;
    }).join('');
    container.querySelectorAll('.tag-item').forEach(el => {
      const id = el.getAttribute('data-id');
      const name = el.getAttribute('data-name');
      const delBtn = el.querySelector('[data-act="delete"]');
      if (delBtn) {
        delBtn.addEventListener('click', (ev) => {
          ev.stopPropagation();
          deleteCategoryTag(category, id, name);
        });
      }
      if (LABEL_CATEGORY_SINGLE_SELECT[category]) {
        el.addEventListener('click', () => toggleSingleTag(category, id));
      } else {
        el.addEventListener('click', () => toggleTag(category, id));
      }
    });
  });
  const tabooContainer = document.getElementById('tabooTags');
  if (tabooContainer) {
    tabooContainer.innerHTML = (currentLabelConfig.forbidden_tags || []).map(t => {
      return `<span class="tag-item" style="position:relative; padding-right:22px;" data-name="${escapeHtml(t)}" title="${escapeHtml(t)}">
        ${escapeHtml(t)}
        <span class="tag-delete-btn" data-act="delete" style="position:absolute; top:50%; right:4px; transform:translateY(-50%); width:16px; height:16px; line-height:14px; text-align:center; font-size:14px; font-weight:700; color:#9ca3af; background:#f3f4f6; border-radius:50%; cursor:pointer; user-select:none;" title="删除雷点">×</span>
      </span>`;
    }).join('');
    tabooContainer.querySelectorAll('.tag-item').forEach(el => {
      const name = el.getAttribute('data-name');
      const delBtn = el.querySelector('[data-act="delete"]');
      if (delBtn) {
        delBtn.addEventListener('click', (ev) => {
          ev.stopPropagation();
          deleteForbiddenTag(name);
        });
      }
      el.addEventListener('click', () => toggleTabooTag(name));
    });
  }
  updateTagDisplay('subject');
  updateTagDisplay('style');
  updateTagDisplay('length');
  updateTagDisplay('taboo');
}

function updateTagDisplay(category) {
  const weaveKey = (category === 'subject') ? 'genre' : category;
  const containerId = LABEL_CATEGORY_TO_CONTAINER[category] || (category === 'taboo' ? 'tabooTags' : null);
  if (!containerId) return;
  const container = document.getElementById(containerId);
  if (!container) return;
  const tags = container.querySelectorAll('.tag-item');
  tags.forEach(tagEl => {
    const id = tagEl.getAttribute('data-id');
    const name = tagEl.getAttribute('data-name');
    if (category === 'subject' || category === 'length') {
      tagEl.classList.toggle('selected', weaveData[weaveKey] === id);
    } else if (category === 'style') {
      const sel = Array.isArray(weaveData.style) ? weaveData.style : [];
      tagEl.classList.toggle('selected', sel.includes(id));
    } else if (category === 'taboo') {
      const tab = Array.isArray(weaveData.taboo) ? weaveData.taboo : [];
      tagEl.classList.toggle('selected', tab.includes(name));
    }
  });
}

async function deleteCategoryTag(category, tagId, tagName) {
  const sessionId = window.currentWorkId;
  if (!sessionId) {
    showStatus('请先选择作品再删除标签', 'error');
    return;
  }
  const catLabel = LABEL_CATEGORY_TO_LABEL[category] || '标签';
  const oldList = currentLabelConfig.label_categories[category] || [];
  const filtered = oldList.filter(x => String(x.id) !== String(tagId));
  if (filtered.length === oldList.length) {
    showStatus(`${catLabel}「${tagName || tagId}」不存在`, 'warning');
    return;
  }
  window.showConfirm({
    title: `删除${catLabel}`,
    message: `确定要删除${catLabel}「${tagName || tagId}」吗？此操作不可恢复。`,
    confirmText: '删除',
    cancelText: '取消',
    onConfirm: async () => {
      try {
        await axios.delete(`/api/label-configs/${encodeURIComponent(sessionId)}/tag/${encodeURIComponent(category)}/${encodeURIComponent(tagId)}`);
      } catch (e) {
        if (e && e.__isCancel) return;
        const detail = (e && e.response && e.response.data && e.response.data.detail) || null;
        console.error('[删除标签] 失败:', e);
        showStatus(detail && detail.message ? detail.message : '删除失败，请稍后再试', 'error');
        return;
      }
      currentLabelConfig.label_categories[category] = filtered;
      const weaveKey = LABEL_CATEGORY_TO_WEAVE_KEY[category] || category;
      if (category === 'style') {
        if (Array.isArray(weaveData.style)) {
          weaveData.style = weaveData.style.filter(x => String(x) !== String(tagId));
        }
      } else {
        if (String(weaveData[weaveKey] || '') === String(tagId)) {
          weaveData[weaveKey] = '';
        }
      }
      renderAllTags();
      updateWeaveNextBtn();
      try {
        await saveLabelSelection(sessionId);
      } catch (_) {}
      showStatus(`${catLabel}「${tagName || tagId}」已删除`, 'success');
    }
  });
}

async function deleteForbiddenTag(tagName) {
  const sessionId = window.currentWorkId;
  if (!sessionId) {
    showStatus('请先选择作品再删除雷点', 'error');
    return;
  }
  const oldList = currentLabelConfig.forbidden_tags || [];
  const filtered = oldList.filter(x => String(x) !== String(tagName));
  if (filtered.length === oldList.length) {
    showStatus(`雷点「${tagName}」不存在`, 'warning');
    return;
  }
  window.showConfirm({
    title: '删除雷点',
    message: `确定要删除雷点「${tagName}」吗？此操作不可恢复。`,
    confirmText: '删除',
    cancelText: '取消',
    onConfirm: async () => {
      try {
        await axios.delete(`/api/label-configs/${encodeURIComponent(sessionId)}/forbidden/${encodeURIComponent(tagName)}`);
      } catch (e) {
        const detail = (e && e.response && e.response.data && e.response.data.detail) || null;
        console.error('[删除雷点] 失败:', e);
        showStatus(detail && detail.message ? detail.message : '删除失败，请稍后再试', 'error');
        return;
      }
      currentLabelConfig.forbidden_tags = filtered;
      if (Array.isArray(weaveData.taboo)) {
        weaveData.taboo = weaveData.taboo.filter(x => String(x) !== String(tagName));
      }
      renderAllTags();
      updateWeaveNextBtn();
      try {
        await saveLabelSelection(sessionId);
      } catch (_) {}
      showStatus(`雷点「${tagName}」已删除`, 'success');
    }
  });
}

function toggleTag(category, tagId) {
  const weaveKey = LABEL_CATEGORY_TO_WEAVE_KEY[category] || category;
  if (!weaveData[weaveKey] || !Array.isArray(weaveData[weaveKey])) {
    weaveData[weaveKey] = [];
  }
  const idx = weaveData[weaveKey].indexOf(tagId);
  if (idx === -1) {
    weaveData[weaveKey].push(tagId);
  } else {
    weaveData[weaveKey].splice(idx, 1);
  }
  updateTagDisplay(category);
  updateWeaveNextBtn();
  if (window.currentWorkId) saveLabelSelection(window.currentWorkId);
}

function toggleSingleTag(category, tagId) {
  const weaveKey = LABEL_CATEGORY_TO_WEAVE_KEY[category] || category;
  weaveData[weaveKey] = tagId;
  updateTagDisplay(category);
  updateWeaveNextBtn();
  if (window.currentWorkId) saveLabelSelection(window.currentWorkId);
}

function toggleTabooTag(name) {
  if (!Array.isArray(weaveData.taboo)) weaveData.taboo = [];
  const idx = weaveData.taboo.indexOf(name);
  if (idx === -1) {
    weaveData.taboo.push(name);
  } else {
    weaveData.taboo.splice(idx, 1);
  }
  updateTagDisplay('taboo');
  updateWeaveNextBtn();
  if (window.currentWorkId) saveLabelSelection(window.currentWorkId);
}

async function addNewTabooTag() {
  const input = document.getElementById('addTabooInput');
  if (!input) return;
  const name = input.value.trim();
  if (!name) {
    showStatus('请输入雷点内容', 'error');
    return;
  }
  if (currentLabelConfig.forbidden_tags.includes(name)) {
    showStatus('该雷点已存在', 'warning');
    return;
  }
  currentLabelConfig.forbidden_tags.push(name);
  if (!Array.isArray(weaveData.taboo)) weaveData.taboo = [];
  if (!weaveData.taboo.includes(name)) weaveData.taboo.push(name);
  if (window.currentWorkId) {
    try {
      await saveLabelConfig(window.currentWorkId);
      await saveLabelSelection(window.currentWorkId);
    } catch (e) {
      currentLabelConfig.forbidden_tags.pop();
      return;
    }
  }
  renderAllTags();
  input.value = '';
  showStatus(`雷点「${name}」添加成功`, 'success');
  updateWeaveNextBtn();
}

async function openAddTagModal(category) {
  const dimensions = await loadLiteraryDimensions();
  const catLabel = LABEL_CATEGORY_TO_LABEL[category] || '标签';
  const title = `新增${catLabel}`;
  const dimRows = dimensions.map(d => `
    <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; padding:6px 4px;">
      <label style="font-size:13px; color:#374151; flex:1; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${escapeHtml(d.name)}">${escapeHtml(d.name)}</label>
      <input
        type="number"
        class="form-input"
        style="padding:4px 8px; font-size:13px; width:120px; flex-shrink:0;"
        data-offset-key="${escapeHtml(d.id)}"
        step="${d.offset_step}"
        min="${d.offset_min}"
        max="${d.offset_max}"
        value="0"
      />
    </div>
  `).join('');

  const content = `
    <div style="display:grid; grid-template-columns: 1fr; gap:10px; margin-bottom:14px;">
      <div style="display:flex; flex-direction:column; gap:4px;">
        <label style="font-size:13px; color:#374151;">标签名称 *</label>
        <input type="text" id="newTagName" class="form-input" placeholder="如：种田流" maxlength="50" />
        <input type="hidden" id="newTagId" />
      </div>
    </div>
    <div style="border-top: 1px solid #e5e7eb; padding-top:12px; margin-bottom:4px;">
      <div style="font-size:13px; color:#667eea; font-weight:600; margin-bottom:10px;">
        文学感知维度偏移（可选，默认 0，范围 [-0.5, 0.5]）
      </div>
      <div style="display: grid; grid-template-columns: repeat(2, 1fr); column-gap: 24px; row-gap: 4px;">
        ${dimRows}
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn-secondary" onclick="closeModal()">取消</button>
      <button class="btn-primary" id="confirmAddTagBtn">确认新增</button>
    </div>
  `;

  const overlay = document.getElementById('modalOverlay');
  const modalContent = document.getElementById('modalContent');
  modalContent.innerHTML = buildModalContent(title, content);
  overlay.style.display = 'flex';

  const nameInput = document.getElementById('newTagName');
  const idInput = document.getElementById('newTagId');
  let debounceTimer = null;
  let lastRequestName = '';

  const requestTagId = async (text) => {
    const name = (text || '').trim();
    if (!name) { idInput.value = ''; return; }
    lastRequestName = name;
    const fallback = () => {
      if (lastRequestName === name) {
        idInput.value = generateTagId(name);
      }
    };
    try {
      const res = await axios.post('/api/translations/tag-id', { name }, { timeout: 5000 });
      const rid = res.data && res.data.id;
      if (rid && lastRequestName === name) {
        idInput.value = String(rid);
      } else if (!rid) {
        fallback();
      }
    } catch (e) {
      const detail = (e && e.response && e.response.data && e.response.data.detail) || null;
      const code = detail && detail.code;
      const msg = detail && detail.message;
      if (code === 'TRANSLATION_CREDENTIAL_UNCONFIGURED') {
        showStatus(
          '未配置腾讯翻译密钥，当前使用本地兜底 ID 生成策略。建议在 /config 中枢注入腾讯云 SecretId / SecretKey，注册地址：https://console.cloud.tencent.com/tmt（详细指引见后续文档）',
          'warning',
          8000
        );
        console.warn('[标签ID] 全局未配置腾讯翻译密钥，使用本地 hash 兜底；腾讯云 TMT 注册页：https://console.cloud.tencent.com/tmt');
      } else {
        console.warn('[标签ID] 翻译接口失败，降级本地 hash 兜底:', msg || (e && e.message));
      }
      fallback();
    }
  };

  nameInput.addEventListener('input', (e) => {
    const val = (e.target && e.target.value) || '';
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => requestTagId(val), 300);
  });

  const confirmBtn = document.getElementById('confirmAddTagBtn');
  confirmBtn.addEventListener('click', async () => {
    await handleConfirmAddTag(category);
  });
}

async function handleConfirmAddTag(category) {
  const name = (document.getElementById('newTagName')?.value || '').trim();
  let id = (document.getElementById('newTagId')?.value || '').trim();
  if (!name) {
    showStatus('请输入标签名称', 'error');
    return;
  }
  if (!id) {
    id = generateTagId(name);
  }
  if (!/^[A-Za-z0-9_\u4e00-\u9fa5]+$/.test(id)) {
    showStatus('ID 仅允许字母、数字、下划线和中文', 'error');
    return;
  }
  const existList = currentLabelConfig.label_categories[category] || [];
  if (existList.some(x => x.id === id)) {
    showStatus('该标签 ID 已存在，请换一个名称或修改 ID', 'error');
    return;
  }
  if (existList.some(x => (x.name || '').trim() === name)) {
    showStatus('该标签名称已存在', 'warning');
    return;
  }
  const OFFSET_MIN = -0.5;
  const OFFSET_MAX = 0.5;
  const dimNameById = new Map((literaryDimensionsCache || []).map(d => [d.id, d.name]));
  const offsetInputs = document.querySelectorAll('input[data-offset-key]');
  for (const inp of offsetInputs) {
    const key = inp.getAttribute('data-offset-key');
    const raw = (inp.value || '').trim();
    if (raw === '') continue;
    const val = parseFloat(raw);
    if (isNaN(val)) {
      const dimLabel = dimNameById.get(key) || key;
      showStatus(`维度「${dimLabel}」的偏移值必须是数字`, 'error');
      return;
    }
    if (val < OFFSET_MIN || val > OFFSET_MAX) {
      const dimLabel = dimNameById.get(key) || key;
      showStatus(`维度「${dimLabel}」的偏移值必须在 [${OFFSET_MIN}, ${OFFSET_MAX}] 闭区间内，当前值：${val}`, 'error');
      return;
    }
  }
  const offsets = {};
  offsetInputs.forEach(inp => {
    const key = inp.getAttribute('data-offset-key');
    const val = parseFloat(inp.value);
    if (!isNaN(val) && Math.abs(val) > 1e-9) {
      offsets[key] = Number(val.toFixed(4));
    }
  });
  const newItem = { id, name, offsets };
  if (!Array.isArray(currentLabelConfig.label_categories[category])) {
    currentLabelConfig.label_categories[category] = [];
  }
  currentLabelConfig.label_categories[category].push(newItem);
  if (window.currentWorkId) {
    try {
      await saveLabelConfig(window.currentWorkId);
    } catch (e) {
      currentLabelConfig.label_categories[category].pop();
      return;
    }
  }
  closeModal();
  renderAllTags();
  showStatus(`${LABEL_CATEGORY_TO_LABEL[category] || '标签'}「${name}」新增成功`, 'success');
  updateWeaveNextBtn();
}

async function initWeavePage() {
  // 【作品级隔离 SOP】切作品进入织网节点时，先清空所有作品级全局单例。
  // 这是跨作品数据污染的第一道防线：否则新作品接口未命中时会复用旧作品内存态。
  resetWeaveWorkIsolatedState();
  // 织网节点优先拉取前端阈值 SSOT（后端 /api/meta/frontend-thresholds），
  // 保证角色/时间/地点模态框的 maxlength 与数量上限永远与后端 values.py / global.json 对齐，禁止分叉
  try {
    if (typeof window.frontendThresholds !== 'object' || window.frontendThresholds === null) {
      window.frontendThresholds = {};
    }
    if (typeof window.frontendThresholds.weave_field_limits !== 'object' || window.frontendThresholds.weave_field_limits === null) {
      if (typeof NovelAPI !== 'undefined' && NovelAPI && typeof NovelAPI.getFrontendThresholds === 'function') {
        const data = await NovelAPI.getFrontendThresholds();
        if (data && typeof data === 'object') {
          window.frontendThresholds = Object.assign({}, window.frontendThresholds, data);
        }
      }
    }
  } catch (_) { /* 拉取失败兜底：character/timeline/location modal 内部有 fallback 常量 */ }
  const sessionId = window.currentWorkId;
  if (sessionId) {
    await Promise.all([
      loadCharacters(sessionId),
      loadTimelines(sessionId),
      loadLocations(sessionId),
      loadLabelConfig(sessionId),
      loadLabelSelection(sessionId),
      loadLiteraryDimensions()
    ]);
  } else {
    await loadLiteraryDimensions();
  }
  renderAllTags();
  renderCharacters();
  renderRelationships();
  renderTimelines();
  renderLocations();
  updateTagDisplay('subject');
  updateTagDisplay('style');
  updateTagDisplay('length');
  updateTagDisplay('taboo');
  updateWeaveNextBtn();
  const tabooInput = document.getElementById('addTabooInput');
  if (tabooInput && !tabooInput.dataset.weaveBound) {
    tabooInput.dataset.weaveBound = '1';
    tabooInput.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        addNewTabooTag();
      }
    });
  }
}

/**
 * 全局作品缓存清空：切作品时调用，确保内存中只驻留一个作品的数据。
 * 清空全部 5 个节点（谋篇/分卷/定章/推演/成文）的 window 级结果缓存 + 织网数据 + 图像能力缓存。
 * 各节点的 initXxxPage 进入时还会调各自的 resetXxxPageIsolatedState 清本页 DOM/去抖/定时器，
 * 此处只负责"跨作品"层面的 window 全局单例清零。
 */
function _resetAllWorkCaches() {
  // 谋篇：全局剧情/摘要
  window._globalPlotResult = null;
  // 分卷：卷纲结果
  window._volumePlotResult = { volumes: [] };
  // 定章：章纲结果
  window._chapterPlotResult = { volumes: [] };
  // 推演：事件链结果
  window._deductionResult = { volumes: [] };
  // 成文：正文结果
  window._contentResult = { volumes: [] };
  // 折叠规范化标记（各节点）
  try { delete window._chapFoldNormalized; } catch (_) { window._chapFoldNormalized = undefined; }
  try { delete window._dedFoldNormalized; } catch (_) { window._dedFoldNormalized = undefined; }
  try { delete window._contFoldNormalized; } catch (_) { window._contFoldNormalized = undefined; }
  // 图像能力元数据缓存（作品无关但安全起见一并清）
  window._imageCapabilitiesCache = null;
  // 能力锁（防止上一作品的锁残留阻塞新作品）
  if (window._capabilityLocks) {
    try { for (const k of Object.keys(window._capabilityLocks)) delete window._capabilityLocks[k]; } catch (_) {}
  }
  // 织网：标签选择 + weaveData（由 resetWeaveWorkIsolatedState 在 initWeavePage 中再清一次，此处提前清防止闪现）
  if (typeof resetWeaveWorkIsolatedState === 'function') {
    resetWeaveWorkIsolatedState();
  }
}

async function handleStepClick(workId, stepIndex) {
  const workItem = document.getElementById(workId);
  const steps = workItem.querySelectorAll('.step-item');

  if (steps[stepIndex].classList.contains('step-locked')) {
    showStatus('请先完成前序环节', 'error');
    return;
  }

  for (let i = 0; i < steps.length; i++) {
    steps[i].classList.remove('step-current');
  }
  steps[stepIndex].classList.add('step-current');

  // 【作品级隔离 SOP】检测作品是否切换：切作品时必须清空全部节点的全局缓存，
  // 确保每次只有一个作品的数据驻留内存，杜绝跨作品数据污染。
  // 同作品切节点不清缓存（保留上游只读回退数据）。
  const isWorkSwitch = (window.currentWorkId !== workId);
  window.currentWorkId = workId;
  if (isWorkSwitch) {
    _resetAllWorkCaches();
  }

  const stepNames = ['立基 - 创作设定', '织网 - 基础设定', '谋篇 - 全局剧情设计', '分卷 - 卷纲剧情设计', '定章 - 章纲剧情设计', '推演 - 章节事件设计', '成文 - 章节正文生成'];
  showStatus(`已进入：${stepNames[stepIndex]}`, 'success');

  const mainArea = document.getElementById('mainArea');
  const weaveArea = document.getElementById('weaveArea');
  const outlineArea = document.getElementById('outlineArea');
  const volumeArea = document.getElementById('volumeArea');
  const chapterArea = document.getElementById('chapterArea');
  const deductionArea = document.getElementById('deductionArea');
  const contentArea = document.getElementById('contentArea');
  const sidebarContent = document.getElementById('sidebarContent');
  const hasWorks = sidebarContent && sidebarContent.querySelectorAll('.work-item').length > 0;

  if (stepIndex === 1) {
    if (mainArea) mainArea.style.display = 'none';
    if (outlineArea) outlineArea.style.display = 'none';
    if (volumeArea) volumeArea.style.display = 'none';
    if (chapterArea) chapterArea.style.display = 'none';
    if (deductionArea) deductionArea.style.display = 'none';
    if (contentArea) contentArea.style.display = 'none';
    if (weaveArea) weaveArea.style.display = 'block';
    try {
      window.scrollTo({top: 0, left: 0, behavior: 'instant'});
    } catch (_) {
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    }
    await initWeavePage();
  } else if (stepIndex === 2) {
    if (mainArea) mainArea.style.display = 'none';
    if (weaveArea) weaveArea.style.display = 'none';
    if (volumeArea) volumeArea.style.display = 'none';
    if (chapterArea) chapterArea.style.display = 'none';
    if (deductionArea) deductionArea.style.display = 'none';
    if (contentArea) contentArea.style.display = 'none';
    if (outlineArea) outlineArea.style.display = 'block';
    try {
      window.scrollTo({top: 0, left: 0, behavior: 'instant'});
    } catch (_) {
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    }
    await initOutlineCanvas();
  } else if (hasWorks && stepIndex === 0) {
    if (mainArea) mainArea.style.display = 'block';
    if (weaveArea) weaveArea.style.display = 'none';
    if (outlineArea) outlineArea.style.display = 'none';
    if (volumeArea) volumeArea.style.display = 'none';
    if (chapterArea) chapterArea.style.display = 'none';
    if (deductionArea) deductionArea.style.display = 'none';
    if (contentArea) contentArea.style.display = 'none';
    try {
      window.scrollTo({top: 0, left: 0, behavior: 'instant'});
    } catch (_) {
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    }
    if (window.refreshWorkStepActions) {
      window.refreshWorkStepActions();
    }
    if (window.loadAndRenderSessionMemories) {
      window.loadAndRenderSessionMemories(workId);
    }
  } else if (stepIndex === 3) {
    if (mainArea) mainArea.style.display = 'none';
    if (weaveArea) weaveArea.style.display = 'none';
    if (outlineArea) outlineArea.style.display = 'none';
    if (chapterArea) chapterArea.style.display = 'none';
    if (deductionArea) deductionArea.style.display = 'none';
    if (contentArea) contentArea.style.display = 'none';
    if (volumeArea) volumeArea.style.display = 'block';
    try {
      window.scrollTo({top: 0, left: 0, behavior: 'instant'});
    } catch (_) {
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    }
    if (window.initVolumePage) {
      window.initVolumePage();
    }
  } else if (stepIndex === 4) {
    if (mainArea) mainArea.style.display = 'none';
    if (weaveArea) weaveArea.style.display = 'none';
    if (outlineArea) outlineArea.style.display = 'none';
    if (volumeArea) volumeArea.style.display = 'none';
    if (deductionArea) deductionArea.style.display = 'none';
    if (contentArea) contentArea.style.display = 'none';
    if (chapterArea) chapterArea.style.display = 'flex';
    try {
      window.scrollTo({top: 0, left: 0, behavior: 'instant'});
    } catch (_) {
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    }
    if (window.initChapterPage) {
      window.initChapterPage();
    }
  } else if (stepIndex === 5) {
    if (mainArea) mainArea.style.display = 'none';
    if (weaveArea) weaveArea.style.display = 'none';
    if (outlineArea) outlineArea.style.display = 'none';
    if (volumeArea) volumeArea.style.display = 'none';
    if (chapterArea) chapterArea.style.display = 'none';
    if (contentArea) contentArea.style.display = 'none';
    if (deductionArea) deductionArea.style.display = 'flex';
    try {
      window.scrollTo({top: 0, left: 0, behavior: 'instant'});
    } catch (_) {
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    }
    if (window.initDeductionPage) {
      window.initDeductionPage();
    }
  } else if (stepIndex === 6) {
    if (mainArea) mainArea.style.display = 'none';
    if (weaveArea) weaveArea.style.display = 'none';
    if (outlineArea) outlineArea.style.display = 'none';
    if (volumeArea) volumeArea.style.display = 'none';
    if (chapterArea) chapterArea.style.display = 'none';
    if (deductionArea) deductionArea.style.display = 'none';
    if (contentArea) contentArea.style.display = 'flex';
    try {
      window.scrollTo({top: 0, left: 0, behavior: 'instant'});
    } catch (_) {
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    }
    if (window.initContentPage) {
      window.initContentPage();
    }
  } else {
    if (mainArea) mainArea.style.display = 'none';
    if (weaveArea) weaveArea.style.display = 'none';
    if (outlineArea) outlineArea.style.display = 'none';
    if (volumeArea) volumeArea.style.display = 'none';
    if (chapterArea) chapterArea.style.display = 'none';
    if (deductionArea) deductionArea.style.display = 'none';
    if (contentArea) contentArea.style.display = 'none';
  }
}

function updateWeaveNextBtn() {
  const nextBtn = document.getElementById('nextStepBtnWeave');
  if (!nextBtn) return;

  const hasContent = weaveData.characters.length >= 1 &&
                     weaveData.timelines.length >= 1 &&
                     weaveData.locations.length > 0 &&
                     weaveData.genre &&
                     weaveData.style && weaveData.style.length > 0 &&
                     weaveData.length &&
                     weaveData.taboo && weaveData.taboo.length > 0;

  if (hasContent) {
    nextBtn.classList.add('show');
  } else {
    nextBtn.classList.remove('show');
  }
}

function openAddTimeModal() {
  const hasRelationships = weaveData.characters.some(c => c.relationships && c.relationships.length > 0);
  if (!hasRelationships && weaveData.characters.length >= 2) {
    showStatus('提示：请编辑角色添加角色关系，以便正常渲染关系图', 'info');
  }
  openTimelineModal();
}

function openAddLocationModal() {
  openLocationModal();
}

function handleWeaveNextStep() {
  if (!weaveData.genre || String(weaveData.genre).trim() === '') {
    showStatus('请选择题材标签', 'error');
    return;
  }
  if (!weaveData.style || weaveData.style.length === 0) {
    showStatus('请选择风格标签', 'error');
    return;
  }
  if (!weaveData.length || String(weaveData.length).trim() === '') {
    showStatus('请选择篇幅标签', 'error');
    return;
  }
  if (!weaveData.taboo || weaveData.taboo.length === 0) {
    showStatus('请选择禁止雷点标签', 'error');
    return;
  }

  const hasRelationships = weaveData.characters.some(c => c.relationships && c.relationships.length > 0);
  if (!hasRelationships) {
    window.showConfirm({
      title: '提示',
      message: '您还未添加角色关系，角色关系图将无法正常渲染。建议先编辑角色添加关系，是否继续前往谋篇？',
      confirmText: '继续',
      cancelText: '返回编辑',
      onConfirm: () => {
        proceedToOutline();
      }
    });
    return;
  }

  proceedToOutline();
}

function proceedToOutline() {
  showStatus('正在构建人物关系图谱，请稍候...', 'info');

  setTimeout(() => {
    showStatus('人物关系图谱构建成功，准备进入谋篇环节', 'success');

    if (window.currentWorkId) {
      completeStep(window.currentWorkId, 1);
    }
  }, 1500);
}

window.initWeavePage = initWeavePage;
window.handleStepClick = handleStepClick;
window._resetAllWorkCaches = _resetAllWorkCaches;
window.updateWeaveNextBtn = updateWeaveNextBtn;
window.toggleTag = toggleTag;
window.toggleSingleTag = toggleSingleTag;
window.toggleTabooTag = toggleTabooTag;
window.updateTagDisplay = updateTagDisplay;
window.addNewTabooTag = addNewTabooTag;
window.openAddTagModal = openAddTagModal;
window.handleConfirmAddTag = handleConfirmAddTag;
window.deleteCategoryTag = deleteCategoryTag;
window.deleteForbiddenTag = deleteForbiddenTag;
window.openAddTimeModal = openAddTimeModal;
window.openAddLocationModal = openAddLocationModal;
window.handleWeaveNextStep = handleWeaveNextStep;
window.proceedToOutline = proceedToOutline;
window.currentLabelConfig = currentLabelConfig;
})();
