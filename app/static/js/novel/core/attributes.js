/**
 * 织网模态框：自定义属性面板（键值对列表）
 * 单一真源（SSOT）：所有字符/数量上限必须通过 opts 从后端 weave_field_limits 传入，禁止硬编码分叉
 * 【兼容约束：DOM 结构 & 类名 & 全局函数必须与 novel.css 原有选择器 100% 对齐，禁止改 CSS
 *
 * 调用方式一（新 API，推荐）：
 *   const attrs = initCustomAttributes(containerEl, existingAttrsDict, {
 *     attrKeyMax: 15,           // 属性键 maxlength（必填，读 weave_field_limits.common.attr_key）
 *     attrValueMax: 80,         // 属性值 maxlength（必填，读 weave_field_limits.common.attr_value）
 *     maxAttributes: 8,         // 自定义属性最大条数（可选，undefined/null=不限制；建议读 weave_field_limits.*.max_attrs）
 *     knownKeys: null,              // 已知内置字段的 Set，避免用户覆盖 type/gender/identity 等
 *     labelName: '属性名',
 *     labelValue: '属性值',
 *     hintName: '例如：性格、修为、武器（建议 1-2 字简洁标签）',
 *     hintValue: '属性对应描述，简洁完整表达',
 *   });
 *   attrs.get();    // 导出 {dict} 形式存 attributes
 *   attrs.set(newDict); // 用 dict 覆盖填充
 *
 * 调用方式二（旧 API 兼容，全局函数保留）：
 *   const html = renderAttributeRow(key, value);  // 单行 HTML 字符串
 *   addAttributeRow(containerId);           // 点击按钮追加一行
 *   const dict = getAttributes(containerId);  // 收集为 dict
 */
(function (global) {
  function escapeAttrText(str) {
    const s = (str == null) ? '' : String(str);
    return s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ========== 旧 API 兼容：renderAttributeRow 输出 DOM 类名与 novel.css 100% 对齐 ==========
  function _renderRowHtml(keyVal, valVal, opts) {
    const options = opts || {};
    const k = (keyVal == null) ? '' : String(keyVal);
    const v = (valVal == null) ? '' : String(valVal);
    const keyMaxNum = (typeof options.attrKeyMax === 'number' && options.attrKeyMax > 0) ? options.attrKeyMax : null;
    const valMaxNum = (typeof options.attrValueMax === 'number' && options.attrValueMax > 0) ? options.attrValueMax : null;
    const keyMax = keyMaxNum ? ` maxlength="${keyMaxNum}"` : '';
    const valMax = valMaxNum ? ` maxlength="${valMaxNum}"` : '';
    const keyPlaceholder = options.hintName || '属性名';
    const valPlaceholder = options.hintValue || '属性值';
    const initCount = v.length;
    const counterInitText = (typeof valMaxNum === 'number')
      ? (String(initCount) + ' / ' + String(valMaxNum))
      : (String(initCount));
    const counterMaxAttr = (typeof valMaxNum === 'number') ? ` data-counter-max="${valMaxNum}"` : '';
    const keyStyle = '' +
      'display:block !important;' +
      'flex:0 0 180px !important;' +
      'min-width:180px !important;' +
      'max-width:180px !important;' +
      'width:180px !important;' +
      'height:80px !important;' +
      'min-height:80px !important;' +
      'max-height:80px !important;' +
      'resize:none !important;' +
      'box-sizing:border-box !important;' +
      'line-height:1.5 !important;' +
      'margin:0 !important;';
    const valWrapStyle = '' +
      'position:static !important;' +
      'display:block !important;' +
      'flex:1 1 auto !important;' +
      'min-width:0 !important;' +
      'width:1% !important;' +
      'max-width:100% !important;' +
      'box-sizing:border-box !important;';
    const valStyle = '' +
      'display:block !important;' +
      'width:100% !important;' +
      'min-width:0 !important;' +
      'max-width:100% !important;' +
      'height:80px !important;' +
      'min-height:80px !important;' +
      'max-height:80px !important;' +
      'resize:none !important;' +
      'box-sizing:border-box !important;' +
      'line-height:1.5 !important;' +
      'padding:10px 14px !important;' +
      'margin:0 !important;';
    const counterStyle = '' +
      'display:block !important;' +
      'margin-top:4px !important;' +
      'text-align:right !important;' +
      'pointer-events:none !important;' +
      'font-size:12px !important;' +
      'color:#6d28d9 !important;' +
      'font-weight:400 !important;' +
      'white-space:nowrap !important;' +
      'user-select:none !important;';
    const rowStyle = '' +
      'display:flex !important;' +
      'width:100% !important;' +
      'max-width:100% !important;' +
      'box-sizing:border-box !important;' +
      'gap:14px !important;' +
      'align-items:flex-start !important;' +
      'margin-bottom:16px !important;';
    const btnStyle = '' +
      'flex:0 0 36px !important;' +
      'min-width:36px !important;' +
      'max-width:36px !important;' +
      'width:36px !important;' +
      'height:36px !important;' +
      'margin-top:22px !important;' +
      'box-sizing:border-box !important;';
    return '' +
      '<div class="attribute-row" style="' + rowStyle + '">' +
        '<textarea class="form-input js-attr-key" placeholder="' + keyPlaceholder + '"' + keyMax +
          ' style="' + keyStyle + '">' +
          escapeAttrText(k) +
        '</textarea>' +
        '<div class="attribute-value-wrap" style="' + valWrapStyle + '">' +
          '<textarea class="form-input js-attr-val" placeholder="' + valPlaceholder + '"' + valMax +
            ' style="' + valStyle + '">' +
            escapeAttrText(v) +
          '</textarea>' +
          '<div class="js-attr-counter char-counter char-counter--right"' + counterMaxAttr +
            ' style="' + counterStyle + '">' +
            counterInitText +
          '</div>' +
        '</div>' +
        '<button type="button" class="attribute-remove-btn js-attr-remove" title="删除该属性"' +
          ' style="' + btnStyle + '">' +
          '<i class="fas fa-trash"></i>' +
        '</button>' +
      '</div>';
  }

  function renderAttributeRow(key, val) {
    return _renderRowHtml(key, val, {});
  }
  global.renderAttributeRow = renderAttributeRow;

  // ========== 内部：销毁一行的计数监听句柄 ==========
  function _destroyRowCounters(row) {
    if (!row || !Array.isArray(row._attrCounterHandlers)) return;
    for (let i = 0; i < row._attrCounterHandlers.length; i++) {
      const h = row._attrCounterHandlers[i];
      if (h && h.target && typeof h.handler === 'function') {
        try { h.target.removeEventListener('input', h.handler); } catch (_) { /* ignore */ }
      }
      if (h && typeof h.destroy === 'function') { try { h.destroy(); } catch (_) { /* ignore */ } }
    }
    row._attrCounterHandlers = null;
  }

  function _updateCounterDom(counterEl, cur, max) {
    if (!counterEl) return;
    if (typeof max === 'number' && max > 0) {
      counterEl.textContent = String(cur) + ' / ' + String(max);
      if (cur > max) {
        try { counterEl.style.setProperty('color', '#b91c1c', 'important'); } catch (_) { counterEl.style.color = '#b91c1c'; }
        counterEl.classList.add('char-counter--over');
      } else {
        try { counterEl.style.setProperty('color', '#6d28d9', 'important'); } catch (_) { counterEl.style.color = '#6d28d9'; }
        counterEl.classList.remove('char-counter--over');
      }
    } else {
      counterEl.textContent = String(cur);
      counterEl.classList.remove('char-counter--over');
    }
  }

  // ========== 内部：为一行绑定值的计数（计数 DOM 已由 HTML 模板直接内置）==========
  function _bindRowCounters(row, opts) {
    if (!row) return;
    const options = opts || {};
    const valEl = row.querySelector('.js-attr-val');
    const counterEl = row.querySelector('.js-attr-counter');
    _destroyRowCounters(row);
    const handlers = [];
    if (valEl && counterEl) {
      let max = null;
      if (typeof options.attrValueMax === 'number' && options.attrValueMax > 0) {
        max = options.attrValueMax;
      } else {
        const fromData = counterEl.getAttribute('data-counter-max');
        if (fromData && !isNaN(Number(fromData)) && Number(fromData) > 0) {
          max = Number(fromData);
        }
      }
      const warnedState = { warned: false };
      const handler = function () {
        const cur = (valEl.value || '').length;
        _updateCounterDom(counterEl, cur, max);
        if (typeof max === 'number' && cur > max && !warnedState.warned) {
          if (typeof window.showStatus === 'function') {
            window.showStatus('建议控制在 ' + String(max) + ' 字以内，超出部分可能影响展示与后续处理', 'warn');
          }
          warnedState.warned = true;
        } else if (typeof max === 'number' && cur <= max) {
          warnedState.warned = false;
        }
      };
      valEl.addEventListener('input', handler);
      handler();
      handlers.push({ target: valEl, handler: handler });
    }
    // 兼容旧调用：仍然允许通用 CharCounter 绑定（保留兜底）
    const fallback = [];
    if (typeof global.CharCounter === 'object' && typeof global.CharCounter.bind === 'function') {
      /* 新机制已内置计数 DOM，不再使用通用绑定 */
    }
    if (fallback.length) handlers.push(...fallback);
    row._attrCounterHandlers = handlers;
  }

  // ========== 旧 API 兼容：addAttributeRow(containerId) 全局函数 ==========
  function addAttributeRow(containerOrId, keyVal, valVal) {
    let container;
    if (typeof containerOrId === 'string') {
      container = document.getElementById(containerOrId);
    } else if (containerOrId && containerOrId.nodeType === 1) {
      container = containerOrId;
    } else {
      return null;
    }
    if (!container) return null;
    // 若调用时只传了 containerId 一个参数，keyVal/valVal 未传
    const isOldCall = (typeof containerOrId === 'string' && arguments.length <= 1);
    const optsFromContainer = container._attrOpts || {};
    if (isOldCall) { keyVal = ''; valVal = ''; }
    const rows = container.querySelectorAll(':scope > .attribute-row');
    const count = rows ? rows.length : 0;
    const maxAttrs = optsFromContainer.maxAttributes;
    if (typeof maxAttrs === 'number' && maxAttrs >= 0 && count >= maxAttrs) {
      _refreshAddBtn(container);
      return null;
    }
    const tmp = document.createElement('div');
    tmp.innerHTML = _renderRowHtml(keyVal, valVal, optsFromContainer);
    const row = tmp.firstElementChild;
    container.appendChild(row);
    _bindRowEvents(row, container);
    _refreshAddBtn(container);
    return row;
  }
  global.addAttributeRow = addAttributeRow;

  // ========== 旧 API 兼容：getAttributes(containerId) 全局函数 ==========
  function getAttributes(containerOrId) {
    let container;
    if (typeof containerOrId === 'string') {
      container = document.getElementById(containerOrId);
    } else if (containerOrId && containerOrId.nodeType === 1) {
      container = containerOrId;
    } else {
      return {};
    }
    const out = {};
    if (!container) return out;
    const optsFromContainer = container._attrOpts || {};
    const known = (optsFromContainer.knownKeys && typeof optsFromContainer.knownKeys.has === 'function')
      ? optsFromContainer.knownKeys
      : null;
    const rows = container.querySelectorAll(':scope > .attribute-row');
    if (!rows) return out;
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      const kInput = row.querySelector('.js-attr-key');
      const vInput = row.querySelector('.js-attr-val');
      if (!kInput || !vInput) continue;
      let k = (kInput.value || '').toString().trim();
      let v = (vInput.value === undefined || vInput.value === null) ? '' : String(vInput.value);
      if (!k) continue;
      if (known && known.has(k)) k = '自定义_' + k;
      let base = k;
      let idx = 2;
      while (Object.prototype.hasOwnProperty.call(out, k)) {
        k = base + String(idx);
        idx += 1;
      }
      out[k] = v;
    }
    return out;
  }
  global.getAttributes = getAttributes;

  // ========== 内部：绑定行事件 ==========
  function _bindRowEvents(row, container) {
    if (!row || row.dataset.attrBound === 'true') return;
    row.dataset.attrBound = 'true';
    const opts = container ? (container._attrOpts || {}) : {};
    const delBtn = row.querySelector('.js-attr-remove');
    if (delBtn) {
      delBtn.addEventListener('click', function () {
        _destroyRowCounters(row);
        if (row.parentNode) row.parentNode.removeChild(row);
        _refreshAddBtn(container);
      });
    }
    _bindRowCounters(row, opts);
  }

  // ========== 内部：刷新添加按钮状态（disabled/文案）==========
  function _refreshAddBtn(container) {
    if (!container) return;
    const addBtn = container.querySelector(':scope > .attribute-add-btn');
    if (!addBtn) return;
    const rows = container.querySelectorAll(':scope > .attribute-row');
    const count = rows ? rows.length : 0;
    const opts = container._attrOpts || {};
    const maxAttrs = opts.maxAttributes;
    const isMax = typeof maxAttrs === 'number' && maxAttrs >= 0 && count >= maxAttrs;
    if (isMax) {
      addBtn.disabled = true;
      addBtn.classList.add('attr-add-btn-disabled');
      const original = addBtn.getAttribute('data-original-text');
      if (!original) {
        addBtn.setAttribute('data-original-text', addBtn.textContent || '');
      }
      addBtn.innerHTML = '<i class="fas fa-ban"></i> 已达上限（最多 ' + String(maxAttrs) + ' 条）';
      addBtn.title = '超出条数的自定义属性后端将自动丢弃末尾项，建议精简合并';
    } else {
      addBtn.disabled = false;
      addBtn.classList.remove('attr-add-btn-disabled');
      addBtn.removeAttribute('title');
      const original = addBtn.getAttribute('data-original-text');
      if (original) {
        addBtn.innerHTML = original;
        addBtn.removeAttribute('data-original-text');
      }
    }
  }

  // ========== 内部：构建添加按钮（旧 DOM 类名）==========
  function _buildAddButton(container) {
    const existing = container.querySelector(':scope > .attribute-add-btn');
    if (existing) return existing;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'attribute-add-btn';
    btn.innerHTML = '<i class="fas fa-plus"></i> 添加属性';
    const containerId = container.id || '';
    btn.addEventListener('click', function () {
      if (containerId) addAttributeRow(containerId);
      else addAttributeRow(container);
    });
    container.appendChild(btn);
    return btn;
  }

  // ========== 内部：从 dict 填充 ==========
  function _fillFromDict(container, dict, opts) {
    if (!container) return;
    const rows = container.querySelectorAll(':scope > .attribute-row');
    for (let i = 0; rows && i < rows.length; i++) {
      _destroyRowCounters(rows[i]);
      if (rows[i].parentNode) rows[i].parentNode.removeChild(rows[i]);
    }
    if (!dict || typeof dict !== 'object') {
      _refreshAddBtn(container);
      return;
    }
    const keys = Object.keys(dict);
    const known = (opts.knownKeys && typeof opts.knownKeys.has === 'function') ? opts.knownKeys : null;
    for (let i = 0; i < keys.length; i++) {
      const k = keys[i];
      if (known && known.has(k)) continue;
      const v = dict[k];
      if (typeof v === 'object' && v !== null) continue;
      addAttributeRow(container, String(k), (v === null || v === undefined) ? '' : String(v));
    }
    _refreshAddBtn(container);
  }

  // ========== 新 API：initCustomAttributes（推荐方式二选一即可）==========
  function initCustomAttributes(container, initialAttrs, opts) {
    if (!container) return { get: function () { return {}; }, set: function () {} };
    const options = opts || {};
    container._attrOpts = options;
    // 清掉旧内容（避免重复绑定/重复添加按钮）
    const oldRows = container.querySelectorAll(':scope > .attribute-row');
    for (let i = 0; oldRows && i < oldRows.length; i++) _destroyRowCounters(oldRows[i]);
    container.innerHTML = '';
    _buildAddButton(container);
    if (initialAttrs) _fillFromDict(container, initialAttrs, options);
    else _refreshAddBtn(container);
    return {
      get: function () { return getAttributes(container); },
      set: function (dict) { _fillFromDict(container, dict || {}, options); },
      _refreshLimit: function () { _refreshAddBtn(container); },
    };
  }

  global.initCustomAttributes = initCustomAttributes;
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this));
