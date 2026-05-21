(function () {
    let punctuationData = {};
    let analysisData = {};
    let spellData = {};

    async function loadRules() {
        try {
            showStatus('正在加载配置...', 'info');

            const [punctRes, analysisRes, spellRes] = await Promise.all([
                fetch('/api/punctuation-rules'),
                fetch('/api/analysis-rules'),
                fetch('/api/spell-rules')
            ]);

            punctuationData = await punctRes.json();
            analysisData = await analysisRes.json();
            spellData = await spellRes.json();

            normalizeRuleData();

            renderPunctuationRules();
            renderAnalysisRules();
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

        analysisData.patterns = analysisData.patterns || {};
        analysisData.thresholds = analysisData.thresholds || {};
        analysisData.readability = Array.isArray(analysisData.readability)
            ? analysisData.readability : [];
        analysisData.readability_fallback = analysisData.readability_fallback || {};
        analysisData.paragraph_splitter = analysisData.paragraph_splitter || {};
        analysisData.style_checks = analysisData.style_checks || {};
        analysisData.style_checks.passive_voice_patterns = Array.isArray(analysisData.style_checks.passive_voice_patterns)
            ? analysisData.style_checks.passive_voice_patterns : [];
        analysisData.style_checks.wordiness_patterns = Array.isArray(analysisData.style_checks.wordiness_patterns)
            ? analysisData.style_checks.wordiness_patterns : [];
        analysisData.style_checks.buzzword_patterns = Array.isArray(analysisData.style_checks.buzzword_patterns)
            ? analysisData.style_checks.buzzword_patterns : [];

        spellData.wrong_characters = spellData.wrong_characters || {};
        spellData.similar_characters = spellData.similar_characters || {};
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

        if (!analysisData.readability ||
            !Array.isArray(analysisData.readability) ||
            analysisData.readability.length === 0) {
            errors.push('「可读性配置」不能为空');
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

    function renderAnalysisRules() {
        const patterns = analysisData.patterns || {};
        document.getElementById('pattern-sentence').value = patterns.sentence || '';
        document.getElementById('pattern-word').value = patterns.word || '';
        document.getElementById('pattern-chinese').value = patterns.chinese || '';
        document.getElementById('pattern-email').value = patterns.email || '';
        document.getElementById('pattern-phone').value = patterns.phone || '';
        document.getElementById('pattern-url').value = patterns.url || '';

        renderThresholds();
        renderReadability();
        renderReadabilityFallback();
        renderParagraphSplitter();
        renderStylePatterns();
    }

    function renderThresholds() {
        const container = document.getElementById('thresholdsContainer');
        container.innerHTML = '';

        const thresholds = analysisData.thresholds || {};
        const thresholdFields = [
            { key: 'max_sentence_length', label: '最大句子长度', desc: '单个句子允许的最大字符数' },
            { key: 'min_sentence_length', label: '最小句子长度', desc: '单个句子允许的最小字符数' },
            { key: 'repeated_word_min_length', label: '重复词最小长度', desc: '检测重复词的最小长度' },
            { key: 'repeated_word_min_count', label: '重复词最小次数', desc: '判定为重复的最小出现次数' },
            { key: 'repeated_phrase_min_length', label: '重复短语最小长度', desc: '检测重复短语的最小长度' },
            { key: 'repeated_phrase_max_length', label: '重复短语最大长度', desc: '检测重复短语的最大长度' },
            { key: 'repeated_phrase_limit', label: '重复短语限制', desc: '允许重复短语的最大数量' },
            { key: 'max_paragraph_length', label: '最大段落长度', desc: '单个段落允许的最大字符数' },
            { key: 'min_paragraph_length', label: '最小段落长度', desc: '单个段落允许的最小字符数' },
            { key: 'repeated_phrase_ngram_min', label: 'N-Gram最小', desc: 'N-Gram分析的最小N值' },
            { key: 'repeated_phrase_ngram_max', label: 'N-Gram最大', desc: 'N-Gram分析的最大N值' }
        ];

        thresholdFields.forEach(field => {
            const item = document.createElement('div');
            item.className = 'form-group';
            item.innerHTML = `
                <label title="${field.desc}">${field.label}</label>
                <input type="number" class="form-control" id="threshold-${field.key}" value="${thresholds[field.key] || ''}" title="${field.desc}">
            `;
            container.appendChild(item);
        });
    }

    function renderReadability() {
        const container = document.getElementById('readabilityContainer');
        container.className = 'rules-grid two-col';
        container.innerHTML = '';

        (analysisData.readability || []).forEach(item => {
            const div = document.createElement('div');
            div.className = 'rule-item readability';
            div.innerHTML = `
                <input type="number" value="${item.min}" placeholder="最小" title="Flesch阅读难度指数最小值">
                <input type="number" value="${item.max}" placeholder="最大" title="Flesch阅读难度指数最大值">
                <input type="number" value="${item.score}" placeholder="分数" title="对应此范围的可读性分数">
                <input type="text" value="${escapeHtml(item.level)}" placeholder="级别" title="难度级别描述">
                <input type="text" value="${escapeHtml(item.suggestion)}" placeholder="建议" title="针对此难度级别的优化建议">
                <div class="delete-cell"><button class="delete-btn" onclick="removeReadabilityItem(this)" title="删除"><i class="fas fa-trash"></i></button></div>
            `;
            container.appendChild(div);
        });
    }

    function addReadabilityItem() {
        const container = document.getElementById('readabilityContainer');
        container.className = 'rules-grid two-col';
        const div = document.createElement('div');
        div.className = 'rule-item readability';
        div.innerHTML = `
            <input type="number" placeholder="最小" title="Flesch阅读难度指数最小值">
            <input type="number" placeholder="最大" title="Flesch阅读难度指数最大值">
            <input type="number" placeholder="分数" title="对应此范围的可读性分数">
            <input type="text" placeholder="级别" title="难度级别描述">
            <input type="text" placeholder="建议" title="针对此难度级别的优化建议">
            <div class="delete-cell"><button class="delete-btn" onclick="removeReadabilityItem(this)" title="删除"><i class="fas fa-trash"></i></button></div>
        `;
        container.appendChild(div);
    }

    function removeReadabilityItem(btn) {
        btn.parentElement.parentElement.remove();
    }

    function renderReadabilityFallback() {
        const fallback = analysisData.readability_fallback || {};
        document.getElementById('fallback-score').value = fallback.score || '';
        document.getElementById('fallback-level').value = fallback.level || '';
        document.getElementById('fallback-suggestion').value = fallback.suggestion || '';
    }

    function renderParagraphSplitter() {
        const splitter = analysisData.paragraph_splitter || {};
        document.getElementById('para-min-chars').value = splitter.min_chars || '';
        document.getElementById('para-target-chars').value = splitter.target_chars || '';
        document.getElementById('para-tolerance').value = splitter.char_tolerance || '';
    }

    function renderStylePatterns() {
        renderStylePatternList('passiveVoiceContainer', analysisData.style_checks?.passive_voice_patterns || []);
        renderStylePatternList('wordinessContainer', analysisData.style_checks?.wordiness_patterns || []);
        renderBuzzwords();
    }

    function renderStylePatternList(containerId, patterns) {
        const container = document.getElementById(containerId);
        container.className = 'rules-grid three-col';
        container.innerHTML = '';

        patterns.forEach(pattern => {
            const item = document.createElement('div');
            item.className = 'rule-item style-pattern';
            item.innerHTML = `
                <input type="text" placeholder="正则" title="匹配风格问题的正则模式">
                <input type="text" placeholder="类型" title="问题类型标签">
                <div class="delete-cell"><button class="delete-btn" onclick="removePatternItem(this)" title="删除"><i class="fas fa-trash"></i></button></div>
            `;
            const inputs = item.querySelectorAll('input');
            inputs[0].value = pattern[0] || '';
            inputs[1].value = pattern[1] || '';
            container.appendChild(item);
        });
    }

    function addStylePattern(containerId) {
        const container = document.getElementById(containerId);
        container.className = 'rules-grid three-col';
        const item = document.createElement('div');
        item.className = 'rule-item style-pattern';
        item.innerHTML = `
            <input type="text" placeholder="正则" title="匹配风格问题的正则模式">
            <input type="text" placeholder="类型" title="问题类型标签">
            <div class="delete-cell"><button class="delete-btn" onclick="removePatternItem(this)" title="删除"><i class="fas fa-trash"></i></button></div>
        `;
        container.appendChild(item);
    }

    function renderBuzzwords() {
        const container = document.getElementById('buzzwordContainer');
        container.className = 'rules-grid three-col';
        container.innerHTML = '';

        (analysisData.style_checks?.buzzword_patterns || []).forEach(pattern => {
            const item = document.createElement('div');
            item.className = 'rule-item style-pattern';
            item.innerHTML = `
                <input type="text" placeholder="术语" title="需要标记的流行术语">
                <input type="text" placeholder="标签" title="显示的标签文本">
                <div class="delete-cell"><button class="delete-btn" onclick="removePatternItem(this)" title="删除"><i class="fas fa-trash"></i></button></div>
            `;
            const inputs = item.querySelectorAll('input');
            inputs[0].value = pattern[0] || '';
            inputs[1].value = pattern[1] || '';
            container.appendChild(item);
        });
    }

    function addBuzzwordItem() {
        const container = document.getElementById('buzzwordContainer');
        container.className = 'rules-grid three-col';
        const item = document.createElement('div');
        item.className = 'rule-item style-pattern';
        item.innerHTML = `
            <input type="text" placeholder="术语" title="需要标记的流行术语">
            <input type="text" placeholder="标签" title="显示的标签文本">
            <div class="delete-cell"><button class="delete-btn" onclick="removePatternItem(this)" title="删除"><i class="fas fa-trash"></i></button></div>
        `;
        container.appendChild(item);
    }

    function renderSpellRules() {
        renderDictEntries('wrongCharactersContainer', spellData.wrong_characters || {});
        renderDictEntries('similarCharactersContainer', spellData.similar_characters || {});
        renderDictEntries('commonErrorsContainer', spellData.common_errors || {});
        renderDeFixPairs();
    }

    function renderDictEntries(containerId, dict) {
        const container = document.getElementById(containerId);
        container.innerHTML = '';

        for (const [key, values] of Object.entries(dict)) {
            const entry = document.createElement('div');
            entry.className = 'dict-entry';
            entry.innerHTML = `
                <div class="dict-header">
                    <div class="dict-key">
                        <input type="text" class="dict-key-input" title="正确项">
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
                    <input type="text" title="错误字符/词">
                    <button class="delete-btn" onclick="removeDictValue(this)" title="删除"><i class="fas fa-trash"></i></button>
                `;
                valueItem.querySelector('input').value = value || '';
                valuesContainer.appendChild(valueItem);
            });
        }
    }

    function addDictEntry(containerId) {
        const container = document.getElementById(containerId);
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
            item.className = 'rule-item pattern-desc';
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
        item.className = 'rule-item pattern-desc';
        item.innerHTML = `
            <input type="text" placeholder="错误用法" title="错误的的/地/得用法">
            <input type="text" placeholder="正确用法" title="正确的的/地/得用法">
            <div class="delete-cell"><button class="delete-btn" onclick="removeDeFixItem(this)" title="删除"><i class="fas fa-trash"></i></button></div>
        `;
        container.appendChild(item);
    }

    function removeDeFixItem(btn) {
        btn.parentElement.remove();
    }

    async function saveAllRules() {
        try {
            const punctuationData = collectPunctuationData();
            const analysisData = collectAnalysisData();
            const spellData = collectSpellData();

            const errors = validateCollectedData(punctuationData, analysisData, spellData);
            if (errors.length > 0) {
                showStatus('校验失败:\n' + errors.join('\n'), 'error');
                return;
            }

            const results = await Promise.all([
                fetch('/api/punctuation-rules', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(punctuationData)
                }),
                fetch('/api/analysis-rules', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(analysisData)
                }),
                fetch('/api/spell-rules', {
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

            showStatus('所有配置已保存并重载', 'success');
        } catch (error) {
            const parsedDetail = window.parseBackendError(error.message, window.ruleFieldLabels) || error.message;
            showStatus('保存失败: ' + parsedDetail, 'error');
        }
    }

    function validateCollectedData(punctuationData, analysisData, spellData) {
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

        if (!analysisData.readability ||
            !Array.isArray(analysisData.readability) ||
            analysisData.readability.length === 0) {
            errors.push('「可读性配置」不能为空');
        }

        const requiredPatterns = ['sentence', 'word', 'chinese'];
        for (const key of requiredPatterns) {
            if (!analysisData.patterns?.[key] || !analysisData.patterns[key].trim()) {
                errors.push(`「${window.ruleFieldLabels[key] || key}」不能为空`);
            }
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

    function collectAnalysisData() {
        const thresholdFields = [
            'max_sentence_length', 'min_sentence_length', 'repeated_word_min_length',
            'repeated_word_min_count', 'repeated_phrase_min_length', 'repeated_phrase_max_length',
            'repeated_phrase_limit', 'max_paragraph_length', 'min_paragraph_length',
            'repeated_phrase_ngram_min', 'repeated_phrase_ngram_max'
        ];

        const thresholds = {};
        thresholdFields.forEach(field => {
            const value = document.getElementById(`threshold-${field}`).value;
            if (value) thresholds[field] = parseInt(value);
        });

        const readability = [];
        document.querySelectorAll('#readabilityContainer .rule-item.readability').forEach(item => {
            const inputs = item.querySelectorAll('input');
            if (inputs[0].value) {
                readability.push({
                    min: parseInt(inputs[0].value),
                    max: parseInt(inputs[1].value),
                    score: parseInt(inputs[2].value),
                    level: inputs[3].value,
                    suggestion: inputs[4].value
                });
            }
        });

        const passiveVoicePatterns = [];
        document.querySelectorAll('#passiveVoiceContainer .rule-item.style-pattern').forEach(item => {
            const inputs = item.querySelectorAll('input');
            if (inputs[0].value.trim()) {
                passiveVoicePatterns.push([inputs[0].value.trim(), inputs[1].value.trim()]);
            }
        });

        const wordinessPatterns = [];
        document.querySelectorAll('#wordinessContainer .rule-item.style-pattern').forEach(item => {
            const inputs = item.querySelectorAll('input');
            if (inputs[0].value.trim()) {
                wordinessPatterns.push([inputs[0].value.trim(), inputs[1].value.trim()]);
            }
        });

        const buzzwordPatterns = [];
        document.querySelectorAll('#buzzwordContainer .rule-item.style-pattern').forEach(item => {
            const inputs = item.querySelectorAll('input');
            if (inputs[0].value.trim()) {
                buzzwordPatterns.push([inputs[0].value.trim(), inputs[1].value.trim()]);
            }
        });

        return {
            patterns: {
                sentence: document.getElementById('pattern-sentence').value,
                word: document.getElementById('pattern-word').value,
                chinese: document.getElementById('pattern-chinese').value,
                email: document.getElementById('pattern-email').value,
                phone: document.getElementById('pattern-phone').value,
                url: document.getElementById('pattern-url').value
            },
            thresholds,
            readability,
            readability_fallback: {
                score: parseInt(document.getElementById('fallback-score').value),
                level: document.getElementById('fallback-level').value,
                suggestion: document.getElementById('fallback-suggestion').value
            },
            paragraph_splitter: {
                min_chars: parseInt(document.getElementById('para-min-chars').value),
                target_chars: parseInt(document.getElementById('para-target-chars').value),
                char_tolerance: parseInt(document.getElementById('para-tolerance').value)
            },
            style_checks: {
                passive_voice_patterns: passiveVoicePatterns,
                wordiness_patterns: wordinessPatterns,
                buzzword_patterns: buzzwordPatterns
            }
        };
    }

    function collectSpellData() {
        const wrongCharacters = collectDictData('wrongCharactersContainer');
        const similarCharacters = collectDictData('similarCharactersContainer');
        const commonErrors = collectDictData('commonErrorsContainer');

        const deFixPairs = {};
        document.querySelectorAll('#deFixContainer .de-fix-item').forEach(item => {
            const inputs = item.querySelectorAll('input');
            if (inputs[0].value.trim()) {
                deFixPairs[inputs[0].value.trim()] = inputs[1].value.trim();
            }
        });

        return {
            wrong_characters: wrongCharacters,
            similar_characters: similarCharacters,
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
    window.collectAnalysisData = collectAnalysisData;
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
    window.addBuzzwordItem = addBuzzwordItem;
    window.renderBuzzwords = renderBuzzwords;
    window.addStylePattern = addStylePattern;
    window.renderStylePatternList = renderStylePatternList;
    window.renderStylePatterns = renderStylePatterns;
    window.renderParagraphSplitter = renderParagraphSplitter;
    window.renderReadabilityFallback = renderReadabilityFallback;
    window.removeReadabilityItem = removeReadabilityItem;
    window.addReadabilityItem = addReadabilityItem;
    window.renderReadability = renderReadability;
    window.renderThresholds = renderThresholds;
    window.renderAnalysisRules = renderAnalysisRules;
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

        if (toolbar) {
            if (window.__bikeAnim) window.__bikeAnim.destroy();
            window.__bikeAnim = new BikeAnimation({
                container: toolbar,
                anchorElement: targetBtn,
                offsetStart: -930,
                offsetEnd: 330,
                duration: 12000,
                verticalOffset: 35
            });
        }

        initSSEForNotifications();
    });
})();