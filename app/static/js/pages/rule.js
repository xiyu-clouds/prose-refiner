(function () {
    let punctuationData = {};
    let spellData = {};

    async function loadRules() {
        try {
            showStatus('正在加载配置...', 'info');

            const [punctResult, spellResult] = await Promise.all([
                AppCache.swrFetch('/api/punctuation-configs/config/get', { ttl: AppCache.TTL_CONFIG }),
                AppCache.swrFetch('/api/text-correction-configs/config/get', { ttl: AppCache.TTL_CONFIG })
            ]);

            punctuationData = punctResult;
            spellData = spellResult;

            normalizeRuleData();

            renderPunctuationRules();
            renderSpellRules();

            showStatus('配置加载成功', 'success');

            document.querySelectorAll('.plugin-card').forEach((card, index) => {
                if (index === 0) {
                    const body = card.querySelector('.plugin-body');
                    const icon = card.querySelector('.icon');
                    if (body && icon) {
                        body.classList.add('open');
                        icon.textContent = '▲';
                    }
                }
            });
        } catch (error) {
            const detail = error.response?.data?.detail || error.message;
            const parsedDetail = window.parseBackendError(detail, window.ruleFieldLabels) || detail;
            showStatus('加载配置失败: ' + parsedDetail, 'error');
        }
    }

    function normalizeRuleData() {
        punctuationData.half_to_full = punctuationData.half_to_full || {};
        punctuationData.invalid_punctuation_patterns = Array.isArray(punctuationData.invalid_punctuation_patterns)
            ? punctuationData.invalid_punctuation_patterns : [];
        punctuationData.missing_space_patterns = Array.isArray(punctuationData.missing_space_patterns)
            ? punctuationData.missing_space_patterns : [];
        punctuationData.wrong_punctuation_patterns = Array.isArray(punctuationData.wrong_punctuation_patterns)
            ? punctuationData.wrong_punctuation_patterns : [];

        spellData.common_errors = spellData.common_errors || {};
        spellData.de_fix_pairs = spellData.de_fix_pairs || {};
    }

    function validateRuleData() {
        const errors = [];

        if (!punctuationData.invalid_punctuation_patterns ||
            !Array.isArray(punctuationData.invalid_punctuation_patterns) ||
            punctuationData.invalid_punctuation_patterns.length === 0) {
            errors.push('「无效标点模式」不能为空');
        }

        if (!punctuationData.missing_space_patterns ||
            !Array.isArray(punctuationData.missing_space_patterns) ||
            punctuationData.missing_space_patterns.length === 0) {
            errors.push('「缺少空格模式」不能为空');
        }

        if (!punctuationData.wrong_punctuation_patterns ||
            !Array.isArray(punctuationData.wrong_punctuation_patterns) ||
            punctuationData.wrong_punctuation_patterns.length === 0) {
            errors.push('「错误标点模式」不能为空');
        }

        return errors;
    }

    function toggleCard(cardId) {
        const card = document.getElementById(cardId);
        const header = card.parentElement.querySelector('.plugin-header');
        card.classList.toggle('open');
        header.classList.toggle('open');
    }

    function renderPunctuationRules() {
        renderHalfFullTable();
        renderPatternList('invalidPunctuationContainer', punctuationData.invalid_punctuation_patterns || []);
        renderMissingSpacePatterns();
        renderWrongPunctuationPatterns();
    }

    function renderHalfFullTable() {
        const container = document.getElementById('halfFullContainer');
        container.className = 'rules-grid';
        container.innerHTML = '';

        for (const [half, full] of Object.entries(punctuationData.half_to_full || {})) {
            const item = document.createElement('div');
            item.className = 'rule-item half-full';
            item.innerHTML = `
                <input type="text" value="${escapeHtml(half)}" placeholder="半角" title="半角字符" maxlength="1">
                <span class="arrow-cell">→</span>
                <input type="text" value="${escapeHtml(full)}" placeholder="全角" title="全角字符" maxlength="1">
                <div class="delete-cell"><button class="delete-btn" onclick="removeHalfFullRow(this)" title="删除"><i class="fas fa-trash"></i></button></div>
            `;
            container.appendChild(item);
        }
    }

    function addHalfFullRow() {
        const container = document.getElementById('halfFullContainer');
        container.className = 'rules-grid';
        const item = document.createElement('div');
        item.className = 'rule-item half-full';
        item.innerHTML = `
            <input type="text" placeholder="半角" title="半角字符" maxlength="1">
            <span class="arrow-cell">→</span>
            <input type="text" placeholder="全角" title="全角字符" maxlength="1">
            <div class="delete-cell"><button class="delete-btn" onclick="removeHalfFullRow(this)" title="删除"><i class="fas fa-trash"></i></button></div>
        `;
        container.appendChild(item);
    }

    function removeHalfFullRow(btn) {
        btn.parentElement.parentElement.remove();
    }

    function renderPatternList(containerId, patterns) {
        const container = document.getElementById(containerId);
        container.className = 'rules-grid three-col';
        container.innerHTML = '';

        patterns.forEach(pattern => {
            const item = document.createElement('div');
            item.className = 'rule-item pattern-desc';
            item.innerHTML = `
                <input type="text" placeholder="标点" title="用于匹配无效标点的正则模式">
                <input type="text" placeholder="描述" title="该模式检测的问题描述">
                <div class="delete-cell"><button class="delete-btn" onclick="removePatternItem(this)" title="删除"><i class="fas fa-trash"></i></button></div>
            `;
            const inputs = item.querySelectorAll('input');
            inputs[0].value = pattern[0] || '';
            inputs[1].value = pattern[1] || '';
            container.appendChild(item);
        });
    }

    function addPatternItem(containerId) {
        const container = document.getElementById(containerId);
        container.className = 'rules-grid three-col';
        const item = document.createElement('div');
        item.className = 'rule-item pattern-desc';
        item.innerHTML = `
            <input type="text" placeholder="标点" title="用于匹配无效标点的正则模式">
            <input type="text" placeholder="描述" title="该模式检测的问题描述">
            <div class="delete-cell"><button class="delete-btn" onclick="removePatternItem(this)" title="删除"><i class="fas fa-trash"></i></button></div>
        `;
        container.appendChild(item);
    }

    function removePatternItem(btn) {
        btn.parentElement.parentElement.remove();
    }

    function renderMissingSpacePatterns() {
        const container = document.getElementById('missingSpaceContainer');
        container.className = 'rules-grid two-col';
        container.innerHTML = '';

        (punctuationData.missing_space_patterns || []).forEach(pattern => {
            const item = document.createElement('div');
            item.className = 'rule-item four-parts';
            item.innerHTML = `
                <input type="text" placeholder="正则" title="检测缺少空格的模式">
                <input type="text" placeholder="替换" title="匹配后替换为此内容">
                <input type="text" placeholder="描述" title="该规则的说明">
                <div class="delete-cell"><button class="delete-btn" onclick="removePatternItem(this)" title="删除"><i class="fas fa-trash"></i></button></div>
            `;
            const inputs = item.querySelectorAll('input');
            inputs[0].value = pattern[0] || '';
            inputs[1].value = pattern[1] || '';
            inputs[2].value = pattern[2] || '';
            container.appendChild(item);
        });
    }

    function addMissingSpaceItem() {
        const container = document.getElementById('missingSpaceContainer');
        container.className = 'rules-grid two-col';
        const item = document.createElement('div');
        item.className = 'rule-item four-parts';
        item.innerHTML = `
            <input type="text" placeholder="正则" title="检测缺少空格的模式">
            <input type="text" placeholder="替换" title="匹配后替换为此内容">
            <input type="text" placeholder="描述" title="该规则的说明">
            <div class="delete-cell"><button class="delete-btn" onclick="removePatternItem(this)" title="删除"><i class="fas fa-trash"></i></button></div>
        `;
        container.appendChild(item);
    }

    function renderWrongPunctuationPatterns() {
        const container = document.getElementById('wrongPunctuationContainer');
        container.className = 'rules-grid two-col';
        container.innerHTML = '';

        (punctuationData.wrong_punctuation_patterns || []).forEach(pattern => {
            const item = document.createElement('div');
            item.className = 'rule-item four-parts';
            item.innerHTML = `
                <input type="text" placeholder="正则" title="检测错误标点的模式">
                <input type="text" placeholder="替换" title="匹配后替换为此内容">
                <input type="text" placeholder="描述" title="该规则的说明">
                <div class="delete-cell"><button class="delete-btn" onclick="removePatternItem(this)" title="删除"><i class="fas fa-trash"></i></button></div>
            `;
            const inputs = item.querySelectorAll('input');
            inputs[0].value = pattern[0] || '';
            inputs[1].value = pattern[1] || '';
            inputs[2].value = pattern[2] || '';
            container.appendChild(item);
        });
    }

    function addWrongPunctuationItem() {
        const container = document.getElementById('wrongPunctuationContainer');
        container.className = 'rules-grid two-col';
        const item = document.createElement('div');
        item.className = 'rule-item four-parts';
        item.innerHTML = `
            <input type="text" placeholder="正则" title="检测错误标点的模式">
            <input type="text" placeholder="替换" title="匹配后替换为此内容">
            <input type="text" placeholder="描述" title="该规则的说明">
            <div class="delete-cell"><button class="delete-btn" onclick="removePatternItem(this)" title="删除"><i class="fas fa-trash"></i></button></div>
        `;
        container.appendChild(item);
    }



    function renderSpellRules() {
        renderDictEntries('commonErrorsContainer', spellData.common_errors || {});
        renderDeFixPairs();
    }

    function renderDictEntries(containerId, dict) {
        const container = document.getElementById(containerId);
        container.className = 'rules-grid three-col dict-grid';
        container.innerHTML = '';

        for (const [key, values] of Object.entries(dict)) {
            const entry = document.createElement('div');
            entry.className = 'dict-entry';
            entry.innerHTML = `
                <div class="dict-header">
                    <div class="dict-key">
                        <input type="text" class="dict-key-input" title="错误字符/词">
                    </div>
                    <div class="add-button-wrapper">
                        <button class="add-dict-btn" onclick="addDictValue('${containerId}-values-${key}')">添加</button>
                    </div>
                    <div class="delete-entry-wrapper">
                        <button class="delete-btn" onclick="removeDictEntry(this)" title="删除条目"><i class="fas fa-trash"></i></button>
                    </div>
                </div>
                <div class="dict-values" id="${containerId}-values-${key}"></div>
            `;
            entry.querySelector('.dict-key-input').value = key || '';
            container.appendChild(entry);

            const valuesContainer = document.getElementById(`${containerId}-values-${key}`);
            values.forEach(value => {
                const valueItem = document.createElement('div');
                valueItem.className = 'dict-value';
                valueItem.innerHTML = `
                    <input type="text" title="正确替换值">
                    <button class="delete-btn" onclick="removeDictValue(this)" title="删除"><i class="fas fa-trash"></i></button>
                `;
                valueItem.querySelector('input').value = value || '';
                valuesContainer.appendChild(valueItem);
            });
        }
    }

    function addDictEntry(containerId) {
        const container = document.getElementById(containerId);
        container.className = 'rules-grid three-col dict-grid';
        const entry = document.createElement('div');
        entry.className = 'dict-entry';
        const uniqueId = `${containerId}-values-${Date.now()}`;
        entry.innerHTML = `
            <div class="dict-header">
                <div class="dict-key">
                    <input type="text" placeholder="错误字符/词" class="dict-key-input" title="错误字符/词">
                </div>
                <div class="add-button-wrapper">
                    <button class="add-dict-btn" onclick="addDictValue('${uniqueId}')">添加</button>
                </div>
                <div class="delete-entry-wrapper">
                    <button class="delete-btn" onclick="removeDictEntry(this)" title="删除条目"><i class="fas fa-trash"></i></button>
                </div>
            </div>
            <div class="dict-values" id="${uniqueId}"></div>
        `;
        container.appendChild(entry);
    }

    function addDictValue(containerId) {
        const container = document.getElementById(containerId);
        const valueItem = document.createElement('div');
        valueItem.className = 'dict-value';
        valueItem.innerHTML = `
            <input type="text" placeholder="正确替换值" title="替换为正确的字符/词">
            <button class="delete-btn" onclick="removeDictValue(this)" title="删除"><i class="fas fa-trash"></i></button>
        `;
        container.appendChild(valueItem);
    }

    function removeDictValue(btn) {
        btn.parentElement.remove();
    }

    function removeDictEntry(btn) {
        btn.closest('.dict-entry').remove();
    }

    function renderDeFixPairs() {
        const container = document.getElementById('deFixContainer');
        container.className = 'rules-grid three-col';
        container.innerHTML = '';

        for (const [wrong, correct] of Object.entries(spellData.de_fix_pairs || {})) {
            const item = document.createElement('div');
            item.className = 'rule-item de-fix-item';
            item.innerHTML = `
                <input type="text" placeholder="错误用法" title="错误的的/地/得用法">
                <input type="text" placeholder="正确用法" title="正确的的/地/得用法">
                <div class="delete-cell"><button class="delete-btn" onclick="removeDeFixItem(this)" title="删除"><i class="fas fa-trash"></i></button></div>
            `;
            const inputs = item.querySelectorAll('input');
            inputs[0].value = wrong || '';
            inputs[1].value = correct || '';
            container.appendChild(item);
        }
    }

    function addDeFixItem() {
        const container = document.getElementById('deFixContainer');
        container.className = 'rules-grid three-col';
        const item = document.createElement('div');
        item.className = 'rule-item de-fix-item';
        item.innerHTML = `
            <input type="text" placeholder="错误用法" title="错误的的/地/得用法">
            <input type="text" placeholder="正确用法" title="正确的的/地/得用法">
            <div class="delete-cell"><button class="delete-btn" onclick="removeDeFixItem(this)" title="删除"><i class="fas fa-trash"></i></button></div>
        `;
        container.appendChild(item);
    }

    function removeDeFixItem(btn) {
        btn.closest('.de-fix-item').remove();
    }

    async function saveAllRules() {
        try {
            const punctuationData = collectPunctuationData();
            const spellData = collectSpellData();

            const errors = validateCollectedData(punctuationData, spellData);
            if (errors.length > 0) {
                showStatus('校验失败:\n' + errors.join('\n'), 'error');
                return;
            }

            const results = await Promise.all([
                fetch('/api/punctuation-configs/config/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(punctuationData)
                }),
                fetch('/api/text-correction-configs/config/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(spellData)
                })
            ]);

            for (const result of results) {
                if (!result.ok) {
                    const errorData = await result.json().catch(() => null);
                    const detail = errorData?.detail || '保存失败';
                    const parsedDetail = window.parseBackendError(detail, window.ruleFieldLabels) || detail;
                    throw new Error(parsedDetail);
                }
            }

            AppCache.invalidate(
                AppCache.cacheKeyOf('/api/punctuation-configs/config/get'),
                AppCache.cacheKeyOf('/api/text-correction-configs/config/get')
            );

            showStatus('所有配置已保存并重载', 'success');
        } catch (error) {
            const parsedDetail = window.parseBackendError(error.message, window.ruleFieldLabels) || error.message;
            showStatus('保存失败: ' + parsedDetail, 'error');
        }
    }

    function validateCollectedData(punctuationData, spellData) {
        const errors = [];

        if (!punctuationData.invalid_punctuation_patterns ||
            !Array.isArray(punctuationData.invalid_punctuation_patterns) ||
            punctuationData.invalid_punctuation_patterns.length === 0) {
            errors.push('「无效标点模式」不能为空');
        }

        if (!punctuationData.missing_space_patterns ||
            !Array.isArray(punctuationData.missing_space_patterns) ||
            punctuationData.missing_space_patterns.length === 0) {
            errors.push('「缺少空格模式」不能为空');
        }

        if (!punctuationData.wrong_punctuation_patterns ||
            !Array.isArray(punctuationData.wrong_punctuation_patterns) ||
            punctuationData.wrong_punctuation_patterns.length === 0) {
            errors.push('「错误标点模式」不能为空');
        }

        return errors;
    }

    function collectPunctuationData() {
        const halfToFull = {};
        document.querySelectorAll('#halfFullContainer .rule-item.half-full').forEach(item => {
            const inputs = item.querySelectorAll('input');
            const half = inputs[0].value.trim();
            const full = inputs[1].value.trim();
            if (half && full) {
                halfToFull[half] = full;
            }
        });

        const invalidPatterns = [];
        document.querySelectorAll('#invalidPunctuationContainer .rule-item.pattern-desc').forEach(item => {
            const inputs = item.querySelectorAll('input');
            if (inputs[0].value.trim()) {
                invalidPatterns.push([inputs[0].value.trim(), inputs[1].value.trim()]);
            }
        });

        const missingSpacePatterns = [];
        document.querySelectorAll('#missingSpaceContainer .rule-item.four-parts').forEach(item => {
            const inputs = item.querySelectorAll('input');
            if (inputs[0].value.trim()) {
                missingSpacePatterns.push([inputs[0].value.trim(), inputs[1].value.trim(), inputs[2].value.trim()]);
            }
        });

        const wrongPunctuationPatterns = [];
        document.querySelectorAll('#wrongPunctuationContainer .rule-item.four-parts').forEach(item => {
            const inputs = item.querySelectorAll('input');
            if (inputs[0].value.trim()) {
                wrongPunctuationPatterns.push([inputs[0].value.trim(), inputs[1].value.trim(), inputs[2].value.trim()]);
            }
        });

        return {
            half_to_full: halfToFull,
            invalid_punctuation_patterns: invalidPatterns,
            missing_space_patterns: missingSpacePatterns,
            wrong_punctuation_patterns: wrongPunctuationPatterns
        };
    }

    function collectSpellData() {
        const commonErrors = collectDictData('commonErrorsContainer');

        const deFixPairs = {};
        document.querySelectorAll('#deFixContainer .de-fix-item').forEach(item => {
            const inputs = item.querySelectorAll('input');
            if (inputs[0].value.trim()) {
                deFixPairs[inputs[0].value.trim()] = inputs[1].value.trim();
            }
        });

        return {
            common_errors: commonErrors,
            de_fix_pairs: deFixPairs
        };
    }

    function collectDictData(containerId) {
        const dict = {};
        document.querySelectorAll(`#${containerId} .dict-entry`).forEach(entry => {
            const key = entry.querySelector('.dict-key-input').value.trim();
            if (!key) return;

            const values = [];
            entry.querySelectorAll('.dict-value input').forEach(input => {
                const value = input.value.trim();
                if (value) values.push(value);
            });

            if (values.length > 0) {
                dict[key] = values;
            }
        });
        return dict;
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    window.escapeHtml = escapeHtml;
    window.collectDictData = collectDictData;
    window.collectSpellData = collectSpellData;
    window.collectPunctuationData = collectPunctuationData;
    window.saveAllRules = saveAllRules;
    window.removeDeFixItem = removeDeFixItem;
    window.addDeFixItem = addDeFixItem;
    window.renderDeFixPairs = renderDeFixPairs;
    window.removeDictEntry = removeDictEntry;
    window.removeDictValue = removeDictValue;
    window.addDictValue = addDictValue;
    window.addDictEntry = addDictEntry;
    window.renderDictEntries = renderDictEntries;
    window.renderSpellRules = renderSpellRules;
    window.addWrongPunctuationItem = addWrongPunctuationItem;
    window.renderWrongPunctuationPatterns = renderWrongPunctuationPatterns;
    window.addMissingSpaceItem = addMissingSpaceItem;
    window.renderMissingSpacePatterns = renderMissingSpacePatterns;
    window.removePatternItem = removePatternItem;
    window.addPatternItem = addPatternItem;
    window.renderPatternList = renderPatternList;
    window.removeHalfFullRow = removeHalfFullRow;
    window.addHalfFullRow = addHalfFullRow;
    window.renderHalfFullTable = renderHalfFullTable;
    window.renderPunctuationRules = renderPunctuationRules;
    window.toggleCard = toggleCard;
    window.loadRules = loadRules;

    document.getElementById('loadBtn').addEventListener('click', loadRules);
    document.getElementById('saveBtn').addEventListener('click', saveAllRules);

    window.addEventListener('DOMContentLoaded', loadRules);

    window.addEventListener('DOMContentLoaded', () => {
        const toolbar = document.querySelector('.page-actions');
        const targetBtn = document.getElementById('loadBtn');

        if (toolbar && targetBtn) {
            if (window.__bikeAnim) window.__bikeAnim.destroy();

            const toolbarRect = toolbar.getBoundingClientRect();
            const btnRect = targetBtn.getBoundingClientRect();
            const anchorRightInContainer = btnRect.right - toolbarRect.left;
            const anchorLeftInContainer = btnRect.left - toolbarRect.left;

            window.__bikeAnim = new BikeAnimation({
                container: toolbar,
                anchorElement: targetBtn,
                offsetStart: 20 - anchorRightInContainer,
                offsetEnd: toolbar.clientWidth - anchorLeftInContainer + 20,
                duration: 12000,
                verticalOffset: 35
            });
        }

        });
})();
