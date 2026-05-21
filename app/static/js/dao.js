(function () {
    let globalDaoData = null;

    const daoTypeMap = {
        title: { type: 'string', label: '标题' },
        version: { type: 'string', label: '版本' },
        statement: { type: 'string', label: '道之宣言' },
        elaboration: { type: 'string', label: '道之阐释' },
        ontological_axioms: { type: 'array', label: '本体论公理' },
        supreme_directive: { type: 'array', label: '最高指令' }
    };

    function validateDaoData(data) {
        const errors = [];

        if (!data || typeof data !== 'object') {
            errors.push('配置必须是有效的 JSON 对象');
            return errors;
        }

        if (!data.supreme_directive || !Array.isArray(data.supreme_directive)) {
            errors.push('「最高指令」必须是数组');
        } else if (data.supreme_directive.length === 0) {
            errors.push('「最高指令」不能为空');
        }

        if (!data.dao || typeof data.dao !== 'object') {
            errors.push('「道之元典」配置不能为空');
            return errors;
        }

        const dao = data.dao;

        if (!dao.title || typeof dao.title !== 'string' || !dao.title.trim()) {
            errors.push('「标题」不能为空');
        }

        if (!dao.statement || typeof dao.statement !== 'string' || !dao.statement.trim()) {
            errors.push('「道之宣言」不能为空');
        }

        if (!dao.elaboration || !Array.isArray(dao.elaboration)) {
            errors.push('「道之阐释」必须是数组');
        } else if (dao.elaboration.length === 0 || !dao.elaboration.some(item => item && String(item).trim())) {
            errors.push('「道之阐释」不能为空');
        }

        if (!dao.ontological_axioms || !Array.isArray(dao.ontological_axioms)) {
            errors.push('「本体论公理」必须是数组');
        }

        return errors;
    }

    function normalizeDaoData(data) {
        if (!data || typeof data !== 'object') return data;

        const normalized = { ...data };

        normalized.dao = data.dao && typeof data.dao === 'object' ? { ...data.dao } : {};

        if (!Array.isArray(normalized.supreme_directive)) {
            normalized.supreme_directive = [];
        }
        if (!Array.isArray(normalized.dao.ontological_axioms)) {
            normalized.dao.ontological_axioms = [];
        }

        normalized.supreme_directive = normalized.supreme_directive
            .map(item => String(item).trim())
            .filter(item => item);

        normalized.dao.ontological_axioms = normalized.dao.ontological_axioms
            .map(item => String(item).trim())
            .filter(item => item);

        if (!Array.isArray(normalized.dao.elaboration)) {
            normalized.dao.elaboration = [];
        }
        normalized.dao.elaboration = normalized.dao.elaboration
            .map(item => String(item).trim())
            .filter(item => item);

        return normalized;
    }

    function renderDao(data) {
        const container = document.getElementById('pluginsContainer');
        if (!container) return;
        container.innerHTML = '';

        if (!data || !data.dao) {
            container.innerHTML = '<div class="alert alert-warning" style="display:block">未找到道之元典配置</div>';
            return;
        }

        const dao = data.dao;
        const supremeDirective = data.supreme_directive || [];
        const ontologicalAxioms = dao.ontological_axioms || [];

        let cardsHTML = '';

        cardsHTML += `
            <div class="plugin-card">
                <div class="plugin-header" onclick="toggleCard(this)">
                    <span>道之元典 <small style="color:#888;">(${dao.title || '未命名'})</small></span>
                    <i class="fas fa-chevron-down"></i>
                </div>
                <div class="plugin-body">
                    <div class="alert alert-warning" id="alert-dao"></div>
                    <div class="form-grid">
                        <div class="form-group"><label>标题</label><input type="text" class="form-control" id="dao-title" value="${esc(dao.title || '')}" oninput="updateDaoField('title', this.value)" required></div>
                        <div class="form-group"><label>版本</label><input type="text" class="form-control" id="dao-version" value="${esc(dao.version || '1.0.0')}" oninput="updateDaoField('version', this.value)"></div>
                    </div>
                    <div class="form-group full-width"><label>道之宣言</label><textarea class="form-control" id="dao-statement" rows="4" oninput="updateDaoField('statement', this.value)" required>${esc(dao.statement || '')}</textarea></div>
                    <div class="form-group full-width"><label>道之阐释</label><textarea class="form-control" id="dao-elaboration" rows="8" oninput="updateDaoField('elaboration', this.value)" required>${esc(Array.isArray(dao.elaboration) ? dao.elaboration.join('\n') : (dao.elaboration || ''))}</textarea></div>
                </div>
            </div>
        `;

        cardsHTML += `
            <div class="plugin-card">
                <div class="plugin-header" onclick="toggleCard(this)">
                    <span>本体论公理 <small style="color:#888;">(${ontologicalAxioms.length} 条)</small></span>
                    <i class="fas fa-chevron-down"></i>
                </div>
                <div class="plugin-body">
                    <div id="axioms-list">
                        ${ontologicalAxioms.map((axiom, index) => `
                            <div class="list-item">
                                <input type="text" value="${esc(axiom)}" oninput="updateAxiom(${index}, this.value)">
                                <button onclick="removeAxiom(${index})"><i class="fas fa-trash"></i></button>
                            </div>
                        `).join('')}
                    </div>
                    <button class="add-item-btn" onclick="addAxiom()"><i class="fas fa-plus"></i> 添加公理</button>
                </div>
            </div>
        `;

        cardsHTML += `
            <div class="plugin-card">
                <div class="plugin-header" onclick="toggleCard(this)">
                    <span>最高指令 <small style="color:#888;">(${supremeDirective.length} 条)</small></span>
                    <i class="fas fa-chevron-down"></i>
                </div>
                <div class="plugin-body">
                    <div id="directive-list">
                        ${supremeDirective.map((directive, index) => `
                            <div class="list-item">
                                <input type="text" value="${esc(directive)}" oninput="updateDirective(${index}, this.value)">
                                <button onclick="removeDirective(${index})"><i class="fas fa-trash"></i></button>
                            </div>
                        `).join('')}
                    </div>
                    <button class="add-item-btn" onclick="addDirective()"><i class="fas fa-plus"></i> 添加指令</button>
                </div>
            </div>
        `;

        container.innerHTML = cardsHTML;

        document.querySelectorAll('.plugin-card').forEach((card, index) => {
            if (index === 0) {
                const header = card.querySelector('.plugin-header');
                const body = card.querySelector('.plugin-body');
                const icon = card.querySelector('i');
                body.classList.add('open');
                icon.className = 'fas fa-chevron-up';
            }
        });
    }

    function updateDaoField(field, value) {
        if (!globalDaoData || typeof globalDaoData !== 'object') {
            return;
        }
        if (!globalDaoData.dao || typeof globalDaoData.dao !== 'object') {
            return;
        }

        if (field === 'elaboration') {
            if (typeof value === 'string') {
                globalDaoData.dao[field] = value.split('\n').map(item => item.trim()).filter(item => item);
            } else if (Array.isArray(value)) {
                globalDaoData.dao[field] = value.map(item => String(item).trim()).filter(item => item);
            } else {
                globalDaoData.dao[field] = [];
            }
        } else {
            const typeConfig = daoTypeMap[field];
            if (typeConfig?.type === 'string') {
                globalDaoData.dao[field] = String(value || '').trim();
            } else {
                globalDaoData.dao[field] = value;
            }
        }
    }

    function updateAxiom(index, value) {
        if (!globalDaoData || typeof globalDaoData !== 'object') {
            globalDaoData = { dao: {}, supreme_directive: [] };
        }
        if (!globalDaoData.dao || typeof globalDaoData.dao !== 'object') {
            globalDaoData.dao = {};
        }
        if (!Array.isArray(globalDaoData.dao.ontological_axioms)) {
            globalDaoData.dao.ontological_axioms = [];
        }
        globalDaoData.dao.ontological_axioms[index] = String(value || '').trim();
    }

    function removeAxiom(index) {
        if (!globalDaoData?.dao?.ontological_axioms) return;
        globalDaoData.dao.ontological_axioms.splice(index, 1);
        refreshAxiomsDisplay();
    }

    function addAxiom() {
        if (!globalDaoData) {
            globalDaoData = { dao: {}, supreme_directive: [] };
        }
        if (!globalDaoData.dao) {
            globalDaoData.dao = {};
        }
        if (!globalDaoData.dao.ontological_axioms) {
            globalDaoData.dao.ontological_axioms = [];
        }
        globalDaoData.dao.ontological_axioms.push('');
        refreshAxiomsDisplay();

        const container = document.getElementById('axioms-list');
        const inputs = container?.querySelectorAll('input');
        if (inputs?.length > 0) {
            inputs[inputs.length - 1].focus();
        }
    }

    function refreshAxiomsDisplay() {
        const container = document.getElementById('axioms-list');
        if (!container || !globalDaoData?.dao?.ontological_axioms) return;

        container.innerHTML = globalDaoData.dao.ontological_axioms.map((axiom, index) => `
            <div class="list-item">
                <input type="text" value="${esc(axiom)}" oninput="updateAxiom(${index}, this.value)">
                <button onclick="removeAxiom(${index})"><i class="fas fa-trash"></i></button>
            </div>
        `).join('');
    }

    function updateDirective(index, value) {
        if (!globalDaoData || typeof globalDaoData !== 'object') {
            globalDaoData = { dao: {}, supreme_directive: [] };
        }
        if (!Array.isArray(globalDaoData.supreme_directive)) {
            globalDaoData.supreme_directive = [];
        }
        globalDaoData.supreme_directive[index] = String(value || '').trim();
    }

    function removeDirective(index) {
        if (!globalDaoData?.supreme_directive) return;
        globalDaoData.supreme_directive.splice(index, 1);
        refreshDirectiveDisplay();
    }

    function addDirective() {
        if (!globalDaoData) {
            globalDaoData = { dao: {}, supreme_directive: [] };
        }
        if (!globalDaoData.supreme_directive) {
            globalDaoData.supreme_directive = [];
        }
        globalDaoData.supreme_directive.push('');
        refreshDirectiveDisplay();

        const container = document.getElementById('directive-list');
        const inputs = container?.querySelectorAll('input');
        if (inputs?.length > 0) {
            inputs[inputs.length - 1].focus();
        }
    }

    function refreshDirectiveDisplay() {
        const container = document.getElementById('directive-list');
        if (!container || !globalDaoData?.supreme_directive) return;

        container.innerHTML = globalDaoData.supreme_directive.map((directive, index) => `
            <div class="list-item">
                <input type="text" value="${esc(directive)}" oninput="updateDirective(${index}, this.value)">
                <button onclick="removeDirective(${index})"><i class="fas fa-trash"></i></button>
            </div>
        `).join('');
    }

    window.refreshDirectiveDisplay = refreshDirectiveDisplay;
    window.addDirective = addDirective;
    window.removeDirective = removeDirective;
    window.updateDirective = updateDirective;
    window.addAxiom = addAxiom;
    window.removeAxiom = removeAxiom;
    window.updateAxiom = updateAxiom;
    window.updateDaoField = updateDaoField;
    window.renderDao = renderDao;

    document.addEventListener('DOMContentLoaded', () => {
        const loadBtn = document.getElementById('loadBtn');
        const saveBtn = document.getElementById('saveBtn');

        loadBtn?.addEventListener('click', async () => {
            try {
                const response = await axios.get('/api/dao');
                globalDaoData = response.data;
                renderDao(response.data);
                showStatus('道之元典配置加载成功', 'success');
            } catch (error) {
                const detail = error.response?.data?.detail;
                const parsedDetail = window.parseBackendError(detail, window.daoFieldLabels) || detail || error.message;
                showStatus(`加载失败: ${parsedDetail}`, 'error');
            }
        });

        saveBtn?.addEventListener('click', async () => {
            if (!globalDaoData) return showStatus('请先加载配置', 'error');
            if (typeof globalDaoData !== 'object') return showStatus('配置数据格式错误', 'error');

            if (!globalDaoData.dao || typeof globalDaoData.dao !== 'object') {
                globalDaoData.dao = {};
            }
            if (!Array.isArray(globalDaoData.supreme_directive)) {
                globalDaoData.supreme_directive = [];
            }
            if (!Array.isArray(globalDaoData.dao.ontological_axioms)) {
                globalDaoData.dao.ontological_axioms = [];
            }

            const errors = validateDaoData(globalDaoData);
            if (errors.length > 0) {
                showStatus('校验失败:\n' + errors.join('\n'), 'error');
                return;
            }

            const normalizedData = normalizeDaoData(globalDaoData);

            try {
                const response = await axios.post('/api/dao', normalizedData);
                showStatus(`保存成功: ${response.data.message}`, 'success');
            } catch (error) {
                const detail = error.response?.data?.detail;
                const parsedDetail = window.parseBackendError(detail, window.daoFieldLabels) || detail || error.message;
                showStatus(`保存失败: ${parsedDetail}`, 'error');
            }
        });

        loadBtn?.click();

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