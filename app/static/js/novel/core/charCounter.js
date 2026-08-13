(function() {
  const OVERFLOW_CLASS = 'char-counter--over';
  const PARENT_RELATIVE_MARK = '__charCounterParentRelSet';
  const INPUT_PB_MARK = '__charCounterInputPad';
  const INPUT_PB_VALUE = '32px';

  function resolveEl(ref) {
    if (ref == null) return null;
    if (ref instanceof Element) return ref;
    if (typeof ref === 'string') return document.getElementById(ref);
    return null;
  }

  function createCounterEl(position) {
    const el = document.createElement('div');
    el.className = 'char-counter';
    el.setAttribute('aria-live', 'polite');
    if (position === 'inline') {
      el.className += ' char-counter--inline';
    } else if (position === 'inside') {
      el.className += ' char-counter--inside';
    } else if (position === 'row-right') {
      el.className += ' char-counter--row-right';
    } else {
      el.className += ' char-counter--right';
    }
    return el;
  }

  function format(cur, max) {
    return `${cur} / ${max}`;
  }

  function update(input, counterEl, max, overflowState) {
    const cur = (input.value || '').length;
    counterEl.textContent = format(cur, max);
    const overflow = cur > max;
    if (overflow) {
      counterEl.classList.add(OVERFLOW_CLASS);
    } else {
      counterEl.classList.remove(OVERFLOW_CLASS);
    }
    if (overflow && typeof overflowState === 'object' && !overflowState.warned) {
      if (typeof window.showStatus === 'function') {
        window.showStatus(`建议控制在 ${max} 字以内，超出部分可能影响展示与后续处理`, 'warn');
      }
      overflowState.warned = true;
    } else if (!overflow && typeof overflowState === 'object') {
      overflowState.warned = false;
    }
  }

  function bindCharCounter(inputRef, options = {}) {
    const input = resolveEl(inputRef);
    if (!input) return { destroy: () => {}, refresh: () => {} };

    const {
      max,
      position = 'right',
    } = options || {};

    if (typeof max !== 'number' || !(max > 0)) {
      console.warn('[CharCounter] bind 失败：必须传入有效的 max');
      return { destroy: () => {}, refresh: () => {} };
    }

    const counterEl = createCounterEl(position);
    const parent = input.parentNode;
    const isInside = position === 'inside';
    const isRowRight = position === 'row-right';

    // 定位锚点：inside / row-right 用特殊锚点
    let anchor = parent;
    if (isRowRight) {
      const row = (typeof input.closest === 'function') ? input.closest('.attribute-row') : null;
      if (row) anchor = row;
    }

    // 为锚点 / 父级设置相对定位 + 输入框预留底部留白（只对 inside 生效）
    let anchorNeedClean = false;
    let inputNeedClean = false;
    if (isInside && parent) {
      const pos = window.getComputedStyle(parent).position;
      if (pos !== 'relative' && pos !== 'absolute' && pos !== 'fixed' && pos !== 'sticky') {
        const prevRel = parent.style.position;
        parent.style.position = 'relative';
        parent.dataset[PARENT_RELATIVE_MARK] = prevRel || '';
        anchorNeedClean = true;
      }
      const pb = window.getComputedStyle(input).paddingBottom || '0px';
      input.dataset[INPUT_PB_MARK] = pb;
      input.style.paddingBottom = INPUT_PB_VALUE;
      inputNeedClean = true;
    }
    if (isRowRight && anchor && anchor !== parent) {
      const pos = window.getComputedStyle(anchor).position;
      if (pos !== 'relative' && pos !== 'absolute' && pos !== 'fixed' && pos !== 'sticky') {
        const prevRel = anchor.style.position;
        anchor.style.position = 'relative';
        anchor.dataset[PARENT_RELATIVE_MARK] = prevRel || '';
        anchorNeedClean = true;
      }
    }

    let inserted = false;
    if (position === 'inline') {
      const label = (input.closest && input.closest('.form-row-full, .form-row-flex, .form-group, form'))
        ?.querySelector?.('.form-label');
      if (label && label.parentNode) {
        label.parentNode.insertBefore(counterEl, label.nextSibling);
        inserted = true;
      }
    }
    if (!inserted && isRowRight && anchor) {
      // 插入到行末尾，避免被 wrap/input 的样式遮挡
      anchor.appendChild(counterEl);
      inserted = true;
    }
    if (!inserted && parent) {
      parent.insertBefore(counterEl, input.nextSibling);
      inserted = true;
    }

    const overflowState = { warned: false };
    const handler = () => update(input, counterEl, max, overflowState);
    input.addEventListener('input', handler);
    handler();

    return {
      refresh: handler,
      destroy: () => {
        input.removeEventListener('input', handler);
        if (counterEl.parentNode) counterEl.parentNode.removeChild(counterEl);
        if (inputNeedClean && input.dataset && Object.prototype.hasOwnProperty.call(input.dataset, INPUT_PB_MARK)) {
          input.style.paddingBottom = input.dataset[INPUT_PB_MARK] || '';
          delete input.dataset[INPUT_PB_MARK];
        }
        if (anchorNeedClean && anchor && anchor.dataset && Object.prototype.hasOwnProperty.call(anchor.dataset, PARENT_RELATIVE_MARK)) {
          anchor.style.position = anchor.dataset[PARENT_RELATIVE_MARK] || '';
          delete anchor.dataset[PARENT_RELATIVE_MARK];
        }
      },
    };
  }

  window.CharCounter = Object.freeze({
    bind: bindCharCounter,
  });
})();
