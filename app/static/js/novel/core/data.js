let editingType = null;
let editingId = null;
let tooltip = null;

const characterPropertyMap = {
  gender: {
    'male': '男',
    'female': '女'
  }
};

const SHARED_GRADIENTS = [
  ['rgba(255, 230, 130, 0.42)', 'rgba(255, 248, 200, 0.28)'],
  ['rgba(160, 220, 255, 0.42)', 'rgba(210, 245, 255, 0.28)'],
  ['rgba(180, 235, 200, 0.42)', 'rgba(220, 250, 230, 0.28)'],
  ['rgba(255, 200, 200, 0.42)', 'rgba(255, 235, 235, 0.28)'],
  ['rgba(200, 210, 255, 0.42)', 'rgba(235, 240, 255, 0.28)'],
  ['rgba(212, 180, 140, 0.45)', 'rgba(245, 225, 190, 0.32)'],
  ['rgba(180, 200, 190, 0.42)', 'rgba(225, 240, 230, 0.28)'],
  ['rgba(231, 76, 60, 0.42)',   'rgba(255, 200, 200, 0.28)'],
  ['rgba(192, 57, 43, 0.42)',   'rgba(240, 190, 180, 0.28)'],
  ['rgba(243, 156, 18, 0.42)',  'rgba(255, 230, 180, 0.28)'],
  ['rgba(52, 152, 219, 0.42)',  'rgba(200, 225, 255, 0.28)'],
  ['rgba(155, 89, 182, 0.42)',  'rgba(230, 200, 255, 0.28)'],
  ['rgba(233, 30, 99, 0.42)',   'rgba(255, 200, 220, 0.28)'],
  ['rgba(139, 195, 74, 0.42)',  'rgba(220, 255, 200, 0.28)'],
  ['rgba(0, 188, 212, 0.42)',   'rgba(200, 255, 255, 0.28)'],
  ['rgba(255, 152, 0, 0.42)',   'rgba(255, 230, 180, 0.28)'],
  ['rgba(121, 85, 72, 0.42)',   'rgba(230, 210, 190, 0.28)'],
  ['rgba(76, 175, 80, 0.42)',   'rgba(210, 245, 210, 0.28)'],
  ['rgba(33, 150, 243, 0.42)',  'rgba(200, 220, 255, 0.28)'],
  ['rgba(142, 45, 226, 0.42)',  'rgba(230, 200, 255, 0.28)'],
  ['rgba(96, 125, 139, 0.42)',  'rgba(220, 225, 230, 0.28)'],
  ['rgba(0, 150, 136, 0.42)',   'rgba(200, 240, 230, 0.28)'],
  ['rgba(192, 192, 192, 0.42)', 'rgba(240, 240, 240, 0.28)'],
  ['rgba(255, 215, 0, 0.42)',   'rgba(255, 245, 180, 0.28)'],
  ['rgba(255, 204, 204, 0.42)', 'rgba(255, 230, 230, 0.28)'],
  ['rgba(204, 204, 255, 0.42)', 'rgba(230, 230, 255, 0.28)'],
  ['rgba(212, 180, 140, 0.42)', 'rgba(240, 225, 200, 0.28)'],
  ['rgba(255, 182, 117, 0.42)', 'rgba(255, 225, 190, 0.28)'],
  ['rgba(180, 180, 255, 0.42)', 'rgba(220, 220, 255, 0.28)'],
  ['rgba(200, 220, 180, 0.42)', 'rgba(230, 245, 220, 0.28)'],
  ['rgba(220, 180, 255, 0.42)', 'rgba(240, 220, 255, 0.28)'],
  ['rgba(255, 230, 200, 0.42)', 'rgba(255, 245, 230, 0.28)'],
  ['rgba(200, 255, 255, 0.42)', 'rgba(230, 255, 255, 0.28)'],
  ['rgba(230, 200, 255, 0.42)', 'rgba(245, 230, 255, 0.28)'],
  ['rgba(255, 200, 220, 0.42)', 'rgba(255, 230, 240, 0.28)'],
  ['rgba(220, 255, 200, 0.42)', 'rgba(240, 255, 230, 0.28)'],
  ['rgba(255, 255, 200, 0.42)', 'rgba(255, 255, 230, 0.28)'],
];

const DEPTH_BORDER_COLORS = [
  '#5d0e0e', '#7209b7', '#023e8a', '#065646', '#4a4e69',
  '#8b0000', '#5a189a', '#1e3a5f', '#1b4332', '#3c096c',
  '#0d4f4f', '#4e342e', '#22223b', '#0f3460', '#6a1b9a',
  '#3e2723', '#16213e', '#5d4037', '#1a1a2e', '#1e8449',
  '#5b2c6f', '#2874a6', '#212f3c', '#1f618d', '#6c3483',
  '#283747', '#922b21', '#7d6608', '#784212', '#b71c1c'
];

const sharedGradientMap = new Map();
function getSharedGradientIndex(id, total) {
  if (sharedGradientMap.has(id)) {
    return sharedGradientMap.get(id);
  }
  const index = Math.floor(Math.random() * total);
  sharedGradientMap.set(id, index);
  return index;
}
function resetSharedGradients() {
  sharedGradientMap.clear();
}

let weaveData = {
  characters: [],
  timelines: [],
  locations: [],
  genre: '',
  style: [],
  length: '',
  taboo: [],
  nextId: {
    character: 1,
    timeline: 1,
    location: 1
  }
};

function getNextId(type) {
  const id = weaveData.nextId[type] || 1;
  weaveData.nextId[type] = id + 1;
  return id;
}

function parseCommaList(str) {
  if (!str) return [];
  return String(str)
    .split(/[,，、]/g)
    .map(s => s.trim())
    .filter(s => s.length > 0);
}

function formatCommaList(arr) {
  if (!Array.isArray(arr)) return '';
  return arr.filter(s => s != null && String(s).trim().length > 0).join(',');
}

function safeExecute(fn, errorMessage) {
  try {
    return fn();
  } catch (error) {
    console.error('[安全执行]', errorMessage, error);
    showStatus(errorMessage || '操作失败，请重试', 'error');
    return null;
  }
}

function saveDataItem(type, item, listName, renderFn) {
  safeExecute(() => {
    const id = editingId || item.id;
    if (editingId) {
      const index = weaveData[listName].findIndex(item => item.id === editingId);
      if (index !== -1) {
        weaveData[listName][index] = { ...item, id: editingId };
      }
    } else {
      weaveData[listName].push({ ...item, id: id });
    }
    renderFn();
    closeModal();
    showStatus(`${type}「${item.name}」保存成功`, 'success');
    updateWeaveNextBtn();
  }, `${type}保存失败`);
}

function setFormFields(fields) {
  for (const [key, value] of Object.entries(fields)) {
    const element = document.getElementById(key);
    if (element) {
      element.value = value || '';
    }
  }
}

function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function getCharId(id) {
  return String(id);
}

function getLinkedCharacterIds(charId) {
  const targetId = getCharId(charId);
  const characters = weaveData.characters || [];
  const char = characters.find(c => getCharId(c.id) === targetId);

  const existingTargetIds = new Set((char?.relationships || [])
    .filter(r => r.targetId)
    .map(r => getCharId(r.targetId)));

  characters.forEach(c => {
    const cId = getCharId(c.id);
    if (cId !== targetId && c.relationships?.some(r => getCharId(r.targetId) === targetId)) {
      existingTargetIds.add(cId);
    }
  });

  return existingTargetIds;
}

function canAddMoreRelationships(charId) {
  const existingTargetIds = getLinkedCharacterIds(charId);
  const characters = weaveData.characters || [];
  const hasFreeTarget = characters.some(c => getCharId(c.id) !== getCharId(charId) && !existingTargetIds.has(getCharId(c.id)));
  if (!hasFreeTarget) return false;
  // 条数上限：读后端 SSOT weave_field_limits.character.max_relations，兜底 99 条
  let maxRels = 99;
  try {
    const wfl = (typeof window !== 'undefined' && window.frontendThresholds) ? window.frontendThresholds.weave_field_limits : null;
    if (wfl && wfl.character && typeof wfl.character.max_relations === 'number' && wfl.character.max_relations >= 0) {
      maxRels = wfl.character.max_relations;
    }
  } catch (_) {}
  const curChar = characters.find(c => getCharId(c.id) === getCharId(charId));
  const relCount = (curChar && Array.isArray(curChar.relationships)) ? curChar.relationships.length : 0;
  return relCount < maxRels;
}

function findCharacterById(charId) {
  const targetId = getCharId(charId);
  return weaveData.characters?.find(c => getCharId(c.id) === targetId);
}

const relationshipColors = [
  'rgba(231, 76, 60, 0.7)',    'rgba(192, 57, 43, 0.7)',   'rgba(243, 156, 18, 0.7)',  'rgba(52, 152, 219, 0.7)',
  'rgba(155, 89, 182, 0.7)',  'rgba(233, 30, 99, 0.7)',   'rgba(139, 195, 74, 0.7)',  'rgba(0, 188, 212, 0.7)',
  'rgba(255, 152, 0, 0.7)',   'rgba(121, 85, 72, 0.7)',   'rgba(76, 175, 80, 0.7)',   'rgba(33, 150, 243, 0.7)',
  'rgba(142, 45, 226, 0.7)',  'rgba(96, 125, 139, 0.7)',  'rgba(0, 150, 136, 0.7)',   'rgba(192, 192, 192, 0.7)',
  'rgba(255, 215, 0, 0.7)',   'rgba(255, 204, 204, 0.7)', 'rgba(204, 204, 255, 0.7)', 'rgba(212, 180, 140, 0.7)',
  'rgba(255, 182, 117, 0.7)', 'rgba(180, 180, 255, 0.7)', 'rgba(200, 220, 180, 0.7)', 'rgba(220, 180, 255, 0.7)',
  'rgba(255, 230, 200, 0.7)', 'rgba(200, 255, 255, 0.7)', 'rgba(230, 200, 255, 0.7)', 'rgba(255, 200, 220, 0.7)',
  'rgba(220, 255, 200, 0.7)', 'rgba(255, 255, 200, 0.7)'
];

const typeColorMap = {};

function getRelationshipColor(type) {
  if (!type) return 'rgba(136, 136, 136, 0.5)';

  if (!typeColorMap[type]) {
    const randomIndex = Math.floor(Math.random() * relationshipColors.length);
    typeColorMap[type] = relationshipColors[randomIndex];
  }

  return typeColorMap[type];
}

window.editingType = editingType;
window.editingId = editingId;
window.tooltip = tooltip;
window.characterPropertyMap = characterPropertyMap;
window.weaveData = weaveData;
window.getNextId = getNextId;
window.saveDataItem = saveDataItem;
window.setFormFields = setFormFields;
window.escapeHtml = escapeHtml;
window.getCharId = getCharId;
window.getLinkedCharacterIds = getLinkedCharacterIds;
window.canAddMoreRelationships = canAddMoreRelationships;
window.findCharacterById = findCharacterById;
window.SHARED_GRADIENTS = SHARED_GRADIENTS;
window.DEPTH_BORDER_COLORS = DEPTH_BORDER_COLORS;
window.getSharedGradientIndex = getSharedGradientIndex;
window.resetSharedGradients = resetSharedGradients;
window.getRelationshipColor = getRelationshipColor;
window.parseCommaList = parseCommaList;
window.formatCommaList = formatCommaList;
window.safeExecute = safeExecute;