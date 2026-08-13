/* ============== 注入预览弹窗公共单例（SSOT：所有页面复用，零散写 if 分支） ============== */
(function () {
  'use strict';

  const CATEGORY_META = [
    { key: 'characters',        label: '角色',       selectedKey: 'selected_character_ids',      defaultsKey: 'selected_character_ids' },
    { key: 'temporals',         label: '时间',       selectedKey: 'selected_temporal_ids',       defaultsKey: 'selected_temporal_ids' },
    { key: 'locations',         label: '地点',       selectedKey: 'selected_location_ids',       defaultsKey: 'selected_location_ids' },
    { key: 'session_memories',  label: '创作设定',   selectedKey: 'selected_session_memory_ids', defaultsKey: 'selected_session_memory_ids' },
  ];

  function _escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, function (c) {
      switch (c) {
        case '&': return '&amp;';
        case '<': return '&lt;';
        case '>': return '&gt;';
        case '"': return '&quot;';
        case "'": return '&#39;';
      }
      return c;
    });
  }

  function _getCheckedIdsFromContainer(container) {
    if (!container) return [];
    const boxes = container.querySelectorAll('input[type="checkbox"][data-entry-id]');
    const ids = [];
    for (let i = 0; i < boxes.length; i++) {
      const b = boxes[i];
      if (b.checked) {
        const n = Number(b.getAttribute('data-entry-id'));
        if (Number.isInteger(n) && n > 0) ids.push(n);
      }
    }
    return ids;
  }

  /** 渲染单个条目（selected 或 unselected 内通用）。 */
  function _renderItemRow(item, checked) {
    const id = Number(item.id);
    const name = _escapeHtml(item.name || '');
    const match = Number(item.match_pct || 0);
    const comp = Number(item.completeness_pct || 0);
    const reason = _escapeHtml(item.reason || '');
    const matchBarW = Math.max(0, Math.min(100, match));
    const compBarW = Math.max(0, Math.min(100, comp));

    // 类型标签（如：男主、朝代、门派）
    const typeLabel = (item.type_label && typeof item.type_label === 'string' && item.type_label.trim())
      ? _escapeHtml(item.type_label.trim())
      : '';
    const typeLabelHtml = typeLabel
      ? `<span style="display:inline-block;flex-shrink:0;margin-left:8px;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:500;background:linear-gradient(135deg,#ede9fe,#ddd6fe);color:#5b21b6;">${typeLabel}</span>`
      : '';

    // 昵称标签（aliases 有值才渲染，带 icon）
    const aliases = Array.isArray(item.aliases) ? item.aliases.filter(a => a && typeof a === 'string' && a.trim()) : [];
    const aliasesHtml = aliases.length > 0
      ? (`<div style="margin-top:4px;font-size:11px;color:#6b7280;line-height:1.5;">` +
           `<i class="fas fa-user-tag" style="color:#7c3aed;margin-right:4px;"></i>` +
           `<span style="font-weight:500;color:#4b5563;">昵称：</span>` +
           `<span>${aliases.map(function(a){return _escapeHtml(a.trim());}).join('、')}</span>` +
         `</div>`)
      : '';

    // 核心属性摘要（如：男 / 22岁 / 学生）
    const attrsSummary = (item.attrs_summary && typeof item.attrs_summary === 'string' && item.attrs_summary.trim())
      ? _escapeHtml(item.attrs_summary.trim())
      : '';
    const attrsSummaryHtml = attrsSummary
      ? `<div style="margin-top:4px;font-size:11px;color:#6b7280;line-height:1.5;"><i class="fas fa-info-circle" style="color:#6b7280;margin-right:4px;"></i>${attrsSummary}</div>`
      : '';

    const metaHtml = (aliasesHtml || attrsSummaryHtml)
      ? `<div style="margin-top:6px;">${aliasesHtml}${attrsSummaryHtml}</div>`
      : '';

    const reasonHtml = reason
      ? `<div style="margin-top:6px;font-size:12px;color:#dc2626;">${reason}</div>`
      : '';
    return (
      `<label style="display:flex;align-items:flex-start;gap:10px;padding:10px 12px;border-radius:8px;cursor:pointer;transition:background 0.15s;"
              class="inject-item-row" onmouseover="this.style.background='#f9fafb'" onmouseout="this.style.background=''">
         <input type="checkbox" data-entry-id="${id}" ${checked ? 'checked' : ''}
                style="margin-top:4px;accent-color:#7c3aed;flex-shrink:0;width:16px;height:16px;cursor:pointer;">
         <div style="flex:1;min-width:0;">
           <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
             <div style="font-size:13px;font-weight:500;color:#111827;word-break:break-all;flex:1;min-width:0;">${name}</div>
             ${typeLabelHtml}
           </div>
           ${metaHtml}
           <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:8px;">
             <div>
               <div style="font-size:11px;color:#6b7280;margin-bottom:2px;">匹配度 ${match}%</div>
               <div style="height:4px;border-radius:2px;background:#e5e7eb;overflow:hidden;">
                 <div style="height:100%;width:${matchBarW}%;background:linear-gradient(90deg,#8e2de2,#4a00e0);"></div>
               </div>
             </div>
             <div>
               <div style="font-size:11px;color:#6b7280;margin-bottom:2px;">完整度 ${comp}%</div>
               <div style="height:4px;border-radius:2px;background:#e5e7eb;overflow:hidden;">
                 <div style="height:100%;width:${compBarW}%;background:linear-gradient(90deg,#10b981,#059669);"></div>
               </div>
             </div>
           </div>
           ${reasonHtml}
         </div>
       </label>`
    );
  }

  /** 渲染摘要块。 */
  function _renderSummaryHtml(summary) {
    const s = summary || {};
    const budget = (s.per_category_budget || {});
    const row = (catKey, label) => {
      const b = budget[catKey] || {};
      return (
        `<div style="font-size:12px;color:#4b5563;">
           <span style="font-weight:500;color:#374151;">${label}：</span>
           默认 ${b.max_count || '-'} 条 × 单条 最大 ${b.max_chars_per_entry || '-'} 字符
         </div>`
      );
    };
    return (
      `<div style="padding:12px 16px;background:linear-gradient(135deg,#f5f3ff,#eef2ff);border-radius:10px;margin-bottom:14px;">
         <div style="display:flex;flex-wrap:wrap;gap:16px 24px;align-items:center;">
           <div style="font-size:13px;color:#111827;">
             <span style="font-weight:600;color:#4a00e0;">预估总注入：</span>
             <span style="font-size:15px;font-weight:600;">${s.total_chars || 0}</span> 字
             <span style="color:#6b7280;margin:0 6px;">≈</span>
             <span style="font-weight:600;">${s.total_tokens || 0}</span> tokens
           </div>
           <div style="font-size:13px;color:#111827;">
             <span style="font-weight:600;color:#4a00e0;">上下文占用：</span>
             <span style="font-weight:600;">${s.context_usage_pct || 0}%</span>
             <span style="font-size:11px;color:#6b7280;margin-left:4px;">（按 1M 上限估）</span>
           </div>
         </div>
         <div style="margin-top:10px;display:grid;grid-template-columns:1fr 1fr;gap:6px 20px;">
           ${row('entity', '角色')}
           ${row('temporal', '时间')}
           ${row('location', '地点')}
           ${row('session_mem', '创作设定')}
         </div>
       </div>`
    );
  }

  /** 渲染单个分类（selected + unselected 折叠区，未选择懒渲染）。 */
  function _renderCategoryHtml(label, selected, unselected) {
    const selArr = Array.isArray(selected) ? selected : [];
    const unselArr = Array.isArray(unselected) ? unselected : [];
    const selectedRows = selArr.map(function (it) { return _renderItemRow(it, true); }).join('');
    const selectedEmpty = selArr.length === 0
      ? `<div style="padding:12px;font-size:12px;color:#9ca3af;text-align:center;">（暂无自动推荐条目，可展开下方未选择区手动勾选）</div>`
      : '';
    return (
      `<div style="margin-bottom:14px;">
         <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
           <div style="font-size:14px;font-weight:600;color:#111827;">
             ${label}
             <span style="margin-left:8px;font-size:12px;font-weight:500;color:#7c3aed;">
               已选 <span class="inject-cat-count">0</span>
             </span>
           </div>
           <div style="font-size:12px;color:#6b7280;">
             推荐 ${selArr.length} / 未选 ${unselArr.length}
           </div>
         </div>

         <div class="inject-selected-list" data-unsel-count="${unselArr.length}"
              style="border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;background:#fff;">
           <div style="padding:8px 12px;background:#fafafa;border-bottom:1px solid #f0f0f0;font-size:12px;font-weight:500;color:#374151;">
             <i class="fas fa-star" style="color:#f59e0b;margin-right:6px;"></i>自动推荐
           </div>
           <div class="inject-selected-inner" style="max-height:260px;overflow-y:auto;padding:4px;">
             ${selectedRows}
             ${selectedEmpty}
           </div>
         </div>

         ${unselArr.length > 0 ? (
           `<div style="margin-top:6px;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;background:#fff;">
              <button type="button" class="inject-unsel-toggle"
                      style="width:100%;padding:8px 12px;background:#fafafa;border:none;border-bottom:1px solid #f0f0f0;
                             font-size:12px;font-weight:500;color:#374151;text-align:left;cursor:pointer;
                             display:flex;align-items:center;justify-content:space-between;">
                <span><i class="fas fa-inbox" style="color:#6b7280;margin-right:6px;"></i>未选择（${unselArr.length}）</span>
                <i class="fas fa-chevron-down inject-unsel-caret" style="color:#9ca3af;transition:transform 0.2s;"></i>
              </button>
              <div class="inject-unsel-inner" data-rendered="0"
                   style="display:none;max-height:260px;overflow-y:auto;padding:4px;"></div>
              <script type="text/html" class="inject-unsel-template">${unselArr.map(function (it) { return _renderItemRow(it, false); }).join('')}</script>
            </div>`
         ) : (
           `<div style="margin-top:6px;padding:10px;border-radius:10px;background:#f9fafb;
                      font-size:12px;color:#6b7280;text-align:center;">（当前分类下无更多候选条目）</div>`
         )}
       </div>`
    );
  }

  /**
   * 公共入口 1：注入预览弹窗（必弹，所有路径统一）。
   * 返回 Promise<{ selected_character_ids, selected_temporal_ids, selected_location_ids, selected_session_memory_ids }>
   * 用户点关闭则 reject(Error('user_closed'))。
   */
  function showInjectionPreview(sessionId, capabilityId, rawVariables) {
    return new Promise(function (resolve, reject) {
      if (!window.NovelAPI || typeof window.NovelAPI.previewInjection !== 'function') {
        const msg = 'NovelAPI.previewInjection 未就绪，请刷新页面后重试';
        if (typeof showStatus === 'function') showStatus(msg, 'error');
        reject(new Error(msg));
        return;
      }

      // 先调后端拿 preview 结构
      window.NovelAPI.previewInjection(sessionId, capabilityId, rawVariables || {})
        .then(function (data) {
          // 结构合法性校验（3.2 第 6 条：结构非法 warn + showStatus）
          const missing = [];
          if (!data || typeof data !== 'object') missing.push('root');
          else {
            if (!data.slots || typeof data.slots !== 'object') missing.push('slots');
            if (!data.defaults || typeof data.defaults !== 'object') missing.push('defaults');
          }
          if (missing.length > 0) {
            const msg = `结构缺少字段: ${missing.join(',')}；请检查后端 preview-injection 端点返回`;
            console.warn(
              `[预览注入结构非法] workId=${sessionId} capabilityId=${capabilityId} ` +
              `missFields=${missing.join(',')}；请检查后端 preview-injection 端点返回`
            );
            if (typeof showStatus === 'function') {
              showStatus(`预览注入结构非法：${msg}`, 'error');
            }
            reject(new Error(msg));
            return;
          }

          const slots = data.slots;
          const defaults = data.defaults;
          const summary = data.summary || {};

          // 校验 slots 四类键存在（缺了用空结构兜底 + warn）
          for (let i = 0; i < CATEGORY_META.length; i++) {
            const cm = CATEGORY_META[i];
            if (!slots[cm.key]) slots[cm.key] = { selected: [], unselected: [] };
            if (!Array.isArray(slots[cm.key].selected)) slots[cm.key].selected = [];
            if (!Array.isArray(slots[cm.key].unselected)) slots[cm.key].unselected = [];
          }

          // 构建完整 overlay（完全复用 showConfirm 的 xh-confirm-overlay / xh-confirm-modal / xh-confirm-close / xh-confirm-cancel / xh-confirm-ok）
          const overlay = document.createElement('div');
          overlay.className = 'xh-confirm-overlay';
          const modalId = 'inject-preview-' + Date.now();
          overlay.style.cssText =
            'position:fixed !important;top:0 !important;left:0 !important;width:100% !important;height:100% !important;' +
            'background:rgba(0,0,0,0.6) !important;display:flex !important;align-items:center !important;' +
            'justify-content:center !important;z-index:99999 !important;';

          // 内容区 body 由 JS 生成：摘要 -> 四个分类 -> 底部四个操作按钮
          const contentHtml =
            _renderSummaryHtml(summary) +
            '<div style="max-height:56vh;overflow-y:auto;padding:0 4px;">' +
              CATEGORY_META.map(function (cm) {
                return _renderCategoryHtml(cm.label, slots[cm.key].selected, slots[cm.key].unselected);
              }).join('') +
            '</div>';

          overlay.innerHTML =
            `<div class="xh-confirm-modal" style="background:#ffffff;border-radius:12px;box-shadow:0 10px 40px rgba(0,0,0,0.25);max-width:860px;width:92%;max-height:88vh;overflow:hidden;display:flex;flex-direction:column;">
               <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 20px;border-bottom:1px solid #e5e7eb;flex-shrink:0;">
                 <h3 style="margin:0;font-size:16px;font-weight:600;color:#374151;">
                   <i class="fas fa-filter" style="color:#8e2de2;margin-right:8px;"></i>注入数据预览与决策
                 </h3>
                 <button class="xh-confirm-close inject-btn-close"
                         style="background:none;border:none;color:#9ca3af;cursor:pointer;font-size:20px;padding:4px;border-radius:4px;">&times;</button>
               </div>
               <div style="padding:16px 20px;flex:1;overflow:hidden;display:flex;flex-direction:column;min-height:120px;">
                 ${contentHtml}
               </div>
               <div style="padding:12px 20px;border-top:1px solid #e5e7eb;display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px 10px;flex-shrink:0;">
                 <div style="display:flex;gap:8px;flex-wrap:wrap;">
                   <button type="button" class="inject-btn-reset-defaults"
                           style="padding:8px 14px;background:#f3f4f6;border:1px solid #d1d5db;border-radius:6px;color:#4b5563;font-size:13px;font-weight:500;cursor:pointer;transition:background 0.2s;">
                     <i class="fas fa-undo" style="margin-right:5px;"></i>恢复自动推荐
                   </button>
                   <button type="button" class="inject-btn-filter-30"
                           style="padding:8px 14px;background:#fff7ed;border:1px solid #fed7aa;border-radius:6px;color:#c2410c;font-size:13px;font-weight:500;cursor:pointer;transition:background 0.2s;">
                     <i class="fas fa-filter" style="margin-right:5px;"></i>只保留匹配度&gt;30%
                   </button>
                 </div>
                 <div style="display:flex;gap:8px;flex-wrap:wrap;">
                   <button type="button" class="xh-confirm-cancel inject-btn-close"
                           style="padding:8px 16px;background:#f3f4f6;border:1px solid #d1d5db;border-radius:6px;color:#4b5563;font-size:13px;font-weight:500;cursor:pointer;transition:background 0.2s;">
                     <i class="fas fa-times" style="margin-right:5px;"></i>关闭
                   </button>
                   <button type="button" class="xh-confirm-ok inject-btn-confirm"
                           style="padding:8px 18px;background:linear-gradient(135deg,#4a00e0,#8e2de2);border:none;border-radius:6px;color:white;font-size:13px;font-weight:500;cursor:pointer;transition:box-shadow 0.2s;">
                     <i class="fas fa-check" style="margin-right:5px;"></i>确认并生成
                   </button>
                 </div>
               </div>
             </div>`;

          document.body.appendChild(overlay);

          // hover 样式（复用 showConfirm 的 hover 规则）
          const stEl = document.createElement('style');
          stEl.textContent =
            `.xh-confirm-cancel:hover{background:#e5e7eb !important;}
             .xh-confirm-ok:hover{box-shadow:0 4px 12px rgba(142,45,226,0.4) !important;}
             .inject-btn-reset-defaults:hover{background:#e5e7eb !important;}
             .inject-btn-filter-30:hover{background:#ffedd5 !important;}
             .inject-item-row:hover{background:#f9fafb;}`;
          document.head.appendChild(stEl);

          // 工具：刷新「已选」数字 + 收集勾选
          function refreshCatCounts() {
            const lists = overlay.querySelectorAll('.inject-selected-list');
            for (let i = 0; i < lists.length; i++) {
              const list = lists[i];
              const ids1 = _getCheckedIdsFromContainer(list);
              // 未选择区（如果被展开并渲染了）也要算入（因为用户可能勾选了）
              const parent = list.parentElement;
              const unselInner = parent ? parent.querySelector('.inject-unsel-inner') : null;
              let ids2 = [];
              if (unselInner && unselInner.getAttribute('data-rendered') === '1') {
                ids2 = _getCheckedIdsFromContainer(unselInner);
              }
              // 合并去重
              const seen = {};
              let total = 0;
              ids1.forEach(function(n) { if (!seen[n]) { seen[n] = 1; total++; } });
              ids2.forEach(function(n) { if (!seen[n]) { seen[n] = 1; total++; } });
              const countSpan = list.parentElement.querySelector('.inject-cat-count');
              if (countSpan) countSpan.textContent = String(total);
            }
          }

          function collectPickedIds() {
            const out = {};
            const lists = overlay.querySelectorAll('.inject-selected-list');
            for (let i = 0; i < lists.length; i++) {
              const cm = CATEGORY_META[i];
              if (!cm) continue;
              const list = lists[i];
              const ids1 = _getCheckedIdsFromContainer(list);
              // 未选择区（如果被展开并渲染了）也要算入（因为用户可能勾选了）
              const parent = list.parentElement;
              const unselInner = parent ? parent.querySelector('.inject-unsel-inner') : null;
              let ids2 = [];
              if (unselInner && unselInner.getAttribute('data-rendered') === '1') {
                ids2 = _getCheckedIdsFromContainer(unselInner);
              }
              // 按「selected顺序 + unselected出现顺序」合并去重
              const seen = {};
              const merged = [];
              const pushOne = function (n) {
                if (!seen[n]) { seen[n] = 1; merged.push(n); }
              };
              ids1.forEach(pushOne);
              ids2.forEach(pushOne);
              out[cm.selectedKey] = merged;
            }
            return out;
          }

          // 绑定：未选择区折叠懒渲染
          const unselToggles = overlay.querySelectorAll('.inject-unsel-toggle');
          for (let i = 0; i < unselToggles.length; i++) {
            (function (btn) {
              btn.addEventListener('click', function () {
                const wrap = btn.parentElement;
                if (!wrap) return;
                const inner = wrap.querySelector('.inject-unsel-inner');
                const tpl = wrap.querySelector('.inject-unsel-template');
                const caret = wrap.querySelector('.inject-unsel-caret');
                if (!inner) return;
                if (inner.getAttribute('data-rendered') !== '1') {
                  if (tpl) inner.innerHTML = tpl.textContent || '';
                  inner.setAttribute('data-rendered', '1');
                }
                const show = inner.style.display === 'none' || inner.style.display === '';
                inner.style.display = show ? 'block' : 'none';
                if (caret) caret.style.transform = show ? 'rotate(180deg)' : 'rotate(0deg)';
              });
            })(unselToggles[i]);
          }

          // 绑定：勾选变化时刷新计数
          overlay.addEventListener('change', function (e) {
            const t = e.target;
            if (t && t.tagName === 'INPUT' && t.type === 'checkbox' && t.hasAttribute('data-entry-id')) {
              refreshCatCounts();
            }
          });
          refreshCatCounts();

          // 工具：关闭弹窗并清理
          let closed = false;
          function closeAndCleanup() {
            if (closed) return;
            closed = true;
            try {
              if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
            } catch (e) { /* ignore */ }
            try {
              if (stEl.parentNode) stEl.parentNode.removeChild(stEl);
            } catch (e) { /* ignore */ }
          }

          // 关闭按钮（两种：close 图标 + ×关闭 按钮）
          const closeBtns = overlay.querySelectorAll('.inject-btn-close');
          for (let i = 0; i < closeBtns.length; i++) {
            closeBtns[i].addEventListener('click', function () {
              closeAndCleanup();
              reject(new Error('user_closed'));
            });
          }
          overlay.addEventListener('click', function (e) {
            if (e.target === overlay) {
              closeAndCleanup();
              reject(new Error('user_closed'));
            }
          });

          // 恢复自动推荐：按 defaults.*_ids 勾选，其余不勾选
          overlay.querySelector('.inject-btn-reset-defaults').addEventListener('click', function () {
            const allBoxes = overlay.querySelectorAll('input[type="checkbox"][data-entry-id]');
            const defaultSets = {};
            for (let i = 0; i < CATEGORY_META.length; i++) {
              const cm = CATEGORY_META[i];
              const arr = Array.isArray(defaults[cm.defaultsKey]) ? defaults[cm.defaultsKey] : [];
              const s = {};
              for (let j = 0; j < arr.length; j++) s[arr[j]] = 1;
              defaultSets[cm.selectedKey] = s;
            }
            for (let i = 0; i < CATEGORY_META.length; i++) {
              const cm = CATEGORY_META[i];
              const list = overlay.querySelectorAll('.inject-selected-list')[i];
              const catWrap = list ? list.parentElement : null;
              const unselInner = catWrap ? catWrap.querySelector('.inject-unsel-inner') : null;
              const scannedBoxes = [];
              const selBoxes = list ? list.querySelectorAll('input[type="checkbox"][data-entry-id]') : [];
              for (let k = 0; k < selBoxes.length; k++) scannedBoxes.push(selBoxes[k]);
              if (unselInner && unselInner.getAttribute('data-rendered') === '1') {
                const usb = unselInner.querySelectorAll('input[type="checkbox"][data-entry-id]');
                for (let k = 0; k < usb.length; k++) scannedBoxes.push(usb[k]);
              }
              const wantSet = defaultSets[cm.selectedKey] || {};
              for (let k = 0; k < scannedBoxes.length; k++) {
                const id = Number(scannedBoxes[k].getAttribute('data-entry-id'));
                scannedBoxes[k].checked = !!wantSet[id];
              }
            }
            refreshCatCounts();
            if (typeof showStatus === 'function') showStatus('已恢复为系统自动推荐勾选状态', 'info');
          });

          // 只保留匹配度>30%：所有已经勾选的条目，如果 match_pct < 30 就取消勾选
          overlay.querySelector('.inject-btn-filter-30').addEventListener('click', function () {
            const allBoxes = overlay.querySelectorAll('input[type="checkbox"][data-entry-id]');
            let changed = 0;
            for (let i = 0; i < allBoxes.length; i++) {
              const b = allBoxes[i];
              if (!b.checked) continue;
              // 反查：找 row 里的 match 进度条对应的 pct（先看兄弟 DOM 里的 match 数字）
              const row = b.closest('.inject-item-row');
              if (!row) continue;
              const txt = row.textContent || '';
              const m = txt.match(/匹配度\s*(\d+)\s*%/);
              if (!m) continue;
              const pct = Number(m[1]) || 0;
              if (pct < 30) { b.checked = false; changed++; }
            }
            refreshCatCounts();
            if (typeof showStatus === 'function') {
              showStatus(changed > 0
                ? `已清理匹配度<30%的勾选条目（共取消 ${changed} 项）`
                : '当前勾选条目匹配度均≥30%，无需调整',
                changed > 0 ? 'warn' : 'info'
              );
            }
          });

          // 确认并生成
          overlay.querySelector('.inject-btn-confirm').addEventListener('click', function () {
            const picked = collectPickedIds();
            const pickedSafe = {
              selected_character_ids: Array.isArray(picked.selected_character_ids) ? picked.selected_character_ids : [],
              selected_temporal_ids: Array.isArray(picked.selected_temporal_ids) ? picked.selected_temporal_ids : [],
              selected_location_ids: Array.isArray(picked.selected_location_ids) ? picked.selected_location_ids : [],
              selected_session_memory_ids: Array.isArray(picked.selected_session_memory_ids) ? picked.selected_session_memory_ids : [],
            };
            // 3.2 第 4 条日志：预览注入确认生成
            console.info(
              `[预览注入确认生成] workId=${sessionId} capabilityId=${capabilityId} ` +
              `picked_ids=${JSON.stringify(pickedSafe)}`
            );
            closeAndCleanup();
            resolve(pickedSafe);
          });
        })
        .catch(function (err) {
          // previewInjection 自身已打 warn + showStatus，这里只把 reject 继续上抛
          reject(err);
        });
    });
  }

  /**
   * 公共入口 2：统一调度 hasExisting 二分支 + 确认框 + 预览弹窗 + variables 合并 + doReal 触发。
   * options: {
   *   hasExisting: boolean,
   *   confirmConfig: {title, message, confirmText, cancelText} | null,
   *   previewConfig: {sessionId, capabilityId, rawVariables},
   *   previewRequired: boolean (默认 true),
   *   doReal: async (finalVariables) => void
   * }
   */
  function startGenerateFlowWithPreview(options) {
    const opts = options && typeof options === 'object' ? options : {};
    const hasExisting = !!opts.hasExisting;
    const confirmCfg = (opts.confirmConfig && typeof opts.confirmConfig === 'object') ? opts.confirmConfig : null;
    const previewCfg = (opts.previewConfig && typeof opts.previewConfig === 'object') ? opts.previewConfig : null;
    const previewRequired = opts.previewRequired !== false;
    const doReal = (typeof opts.doReal === 'function') ? opts.doReal : null;

    if (!previewCfg) {
      if (typeof showStatus === 'function') showStatus('previewConfig 缺失，无法执行生成流程', 'error');
      return;
    }
    if (typeof doReal !== 'function') {
      if (typeof showStatus === 'function') showStatus('doReal 回调缺失，无法执行生成流程', 'error');
      return;
    }

    const sessionId = previewCfg.sessionId;
    const capabilityId = previewCfg.capabilityId;
    const rawVars = (previewCfg.rawVariables && typeof previewCfg.rawVariables === 'object')
      ? previewCfg.rawVariables
      : {};

    // Step 1: hasExisting 二分支（确认框调度写在公共单例里，页面零散写 if）
    function afterConfirm() {
      // Step 2: 预览是否需要
      if (!previewRequired) {
        doReal(rawVars).catch(function (e) {
          console.error('[startGenerateFlowWithPreview] doReal 异常:', e && e.message ? e.message : e);
        });
        return;
      }
      // Step 3: 弹预览 -> 合并 variables -> doReal
      showInjectionPreview(sessionId, capabilityId, rawVars)
        .then(function (picked) {
          const finalVars = {};
          // 先合并 rawVariables（保持剧情核心等原有字段）
          Object.keys(rawVars).forEach(function (k) { finalVars[k] = rawVars[k]; });
          // 再合并四个 selected_*_ids（覆盖用户决策）
          finalVars.selected_character_ids = Array.isArray(picked.selected_character_ids) ? picked.selected_character_ids : [];
          finalVars.selected_temporal_ids = Array.isArray(picked.selected_temporal_ids) ? picked.selected_temporal_ids : [];
          finalVars.selected_location_ids = Array.isArray(picked.selected_location_ids) ? picked.selected_location_ids : [];
          finalVars.selected_session_memory_ids = Array.isArray(picked.selected_session_memory_ids) ? picked.selected_session_memory_ids : [];
          // 3.2 第 5 条日志：variables 合并完成
          const nChar = finalVars.selected_character_ids.length;
          const nTime = finalVars.selected_temporal_ids.length;
          const nLoc = finalVars.selected_location_ids.length;
          const nMem = finalVars.selected_session_memory_ids.length;
          console.info(
            `[注入variables合并完成] workId=${sessionId} capabilityId=${capabilityId} ` +
            `finalVariablesKeys=${Object.keys(finalVars).join(',')} ` +
            `selected_counts=角色:${nChar},时间:${nTime},地点:${nLoc},记忆:${nMem}`
          );
          return doReal(finalVars);
        })
        .catch(function (err) {
          // user_closed 是用户主动取消，不打 error 不 showStatus
          if (err && err.message === 'user_closed') return;
          const msg = (err && err.message) ? err.message : String(err);
          console.warn('[startGenerateFlowWithPreview] 预览或生成失败:', msg);
        });
    }

    if (hasExisting && confirmCfg) {
      if (typeof window.showConfirm !== 'function') {
        // 极端降级：showConfirm 未加载就跳过确认框
        afterConfirm();
        return;
      }
      window.showConfirm({
        title: confirmCfg.title || '确认操作',
        message: confirmCfg.message || '确定要继续吗？',
        confirmText: confirmCfg.confirmText || '确定',
        cancelText: confirmCfg.cancelText || '取消',
        onConfirm: afterConfirm,
        onCancel: null,
      });
    } else {
      afterConfirm();
    }
  }

  // 挂载到 window（SSOT 公共单例，所有页面复用）
  window.showInjectionPreview = showInjectionPreview;
  window.startGenerateFlowWithPreview = startGenerateFlowWithPreview;
})();
