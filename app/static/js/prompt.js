(function () {
    const dataRef = { current: null };
    const dataManager = window.createPromptDataManager(dataRef);

    function renderPrompts(data) {
        const container = document.getElementById('pluginsContainer');
        if (!container) return;
        container.innerHTML = '';

        const prompts = data?.prompts || [];
        if (!prompts.length) {
            container.innerHTML = '<div class="alert alert-warning" style="display:block">未找到 Prompt 配置</div>';
            return;
        }

        prompts.forEach((prompt, index) => {
            const isExpanded = index === 0;
            const rulesText = Array.isArray(prompt.rules) ? prompt.rules.join('\n') : window.esc(prompt.rules || '');
            const paramsText = window.esc(JSON.stringify(prompt.params || {}, null, 2));
            const outputSchemaText = window.esc(JSON.stringify(prompt.output_schema || {}, null, 2));
            const isEnabled = prompt.enabled === true;
            const isConstitutionEnabled = prompt.meta_constitution_injected === true;
            let tagsStr = prompt.tags || '';
            if (Array.isArray(tagsStr)) tagsStr = tagsStr.join(', ');

            const cardDiv = document.createElement('div');
            cardDiv.className = 'plugin-card';
            cardDiv.dataset.index = index;

            cardDiv.innerHTML =
                '<div class="plugin-header" onclick="toggleCard(this)">' +
                    '<span>' + window.esc(prompt.name) + ' <small style="color:#888;">(' + prompt.id + ')</small></span>' +
                    '<i class="fas fa-chevron-' + (isExpanded ? 'up' : 'down') + '"></i>' +
                '</div>' +
                '<div class="plugin-body ' + (isExpanded ? 'open' : '') + '">' +
                    '<div class="alert alert-warning" id="alert-' + index + '"></div>' +
                    '<div class="form-grid compact-grid">' +
                        '<div class="form-group"><label>ID</label><input type="text" class="form-control" value="' + window.esc(prompt.id) + '" readonly></div>' +
                        '<div class="form-group"><label>名称</label><input type="text" class="form-control" id="name-' + index + '" value="' + window.esc(prompt.name) + '" oninput="updateData(' + index + ', \'name\', this.value)"></div>' +
                        '<div class="form-group"><label>类型</label><input type="text" class="form-control" value="' + window.esc(prompt.type) + '" readonly></div>' +
                        '<div class="form-group"><label>版本</label><input type="text" class="form-control" id="version-' + index + '" value="' + window.esc(prompt.version) + '" oninput="updateData(' + index + ', \'version\', this.value)"></div>' +
                        '<div class="form-group"><label>启用状态</label><select class="form-control" id="enabled-' + index + '" onchange="updateData(' + index + ', \'enabled\', this.value === \'true\')">' +
                            '<option value="true" ' + (isEnabled ? 'selected' : '') + '>启用</option>' +
                            '<option value="false" ' + (!isEnabled ? 'selected' : '') + '>禁用</option>' +
                        '</select></div>' +
                        '<div class="form-group"><label>元规则注入</label><select class="form-control" id="meta_constitution_injected-' + index + '" onchange="updateData(' + index + ', \'meta_constitution_injected\', this.value === \'true\')">' +
                            '<option value="true" ' + (isConstitutionEnabled ? 'selected' : '') + '>启用</option>' +
                            '<option value="false" ' + (!isConstitutionEnabled ? 'selected' : '') + '>禁用</option>' +
                        '</select></div>' +
                    '</div>' +
                    '<div class="form-group full-width" style="margin-top: 10px;">' +
                        '<label>Tags <small>(用逗号分隔)</small></label>' +
                        '<input type="text" class="form-control" id="tags-' + index + '" value="' + tagsStr + '" oninput="updateData(' + index + ', \'tags\', this.value)">' +
                    '</div>' +
                    '<hr style="border:0; border-top:1px solid #eee; margin:15px 0;">' +
                    '<div class="form-group full-width"><label>描述</label><textarea class="form-control" id="description-' + index + '" rows="2" oninput="updateData(' + index + ', \'description\', this.value)">' + window.esc(prompt.description || '') + '</textarea></div>' +
                    '<div class="form-group full-width"><label>LLM 参数</label><textarea class="form-control" id="params-' + index + '" rows="5" oninput="updateData(' + index + ', \'params\', this.value)">' + paramsText + '</textarea></div>' +
                    '<div class="form-group full-width"><label>角色</label><textarea class="form-control" id="role-' + index + '" rows="3" oninput="updateData(' + index + ', \'role\', this.value)">' + window.esc(prompt.role || '') + '</textarea></div>' +
                    '<div class="form-group full-width"><label>信息源</label><textarea class="form-control" id="information_source-' + index + '" rows="3" oninput="updateData(' + index + ', \'information_source\', this.value)">' + window.esc(prompt.information_source || '') + '</textarea></div>' +
                    '<div class="form-group full-width"><label>规则</label><textarea class="form-control" id="rules-' + index + '" rows="12" oninput="updateData(' + index + ', \'rules\', this.value)">' + rulesText + '</textarea></div>' +
                    '<div class="form-group full-width"><label>输出前缀</label><textarea class="form-control" id="output_prefix-' + index + '" rows="2" oninput="updateData(' + index + ', \'output_prefix\', this.value)">' + window.esc(prompt.output_prefix || '') + '</textarea></div>' +
                    '<div class="form-group full-width"><label>输出结构</label><textarea class="form-control" id="output_schema-' + index + '" rows="8" readonly>' + outputSchemaText + '</textarea></div>' +
                    '<div class="form-group full-width"><label>空结果回退</label><textarea class="form-control" id="empty_result_fallback-' + index + '" rows="3" oninput="updateData(' + index + ', \'empty_result_fallback\', this.value)">' + window.esc(prompt.empty_result_fallback || '') + '</textarea></div>' +
                    '<div class="form-group full-width"><label>输出后缀</label><textarea class="form-control" id="output_suffix-' + index + '" rows="2" oninput="updateData(' + index + ', \'output_suffix\', this.value)">' + window.esc(prompt.output_suffix || '') + '</textarea></div>' +
                '</div>';

            container.appendChild(cardDiv);
        });
    }

    function updateData(index, key, value) {
        dataManager.update(index, key, value);
    }

    window.updateData = updateData;
    window.renderPrompts = renderPrompts;

    document.addEventListener('DOMContentLoaded', () => {
        const loadBtn = document.getElementById('loadBtn');
        const saveBtn = document.getElementById('saveBtn');

        loadBtn?.addEventListener('click', async () => {
            try {
                const response = await axios.get('/api/prompts');
                dataRef.current = response.data;
                renderPrompts(response.data);
                showStatus('配置加载成功', 'success');
            } catch (error) {
                showStatus(`加载失败: ${error.response?.data?.detail || error.message}`, 'error');
            }
        });

        saveBtn?.addEventListener('click', async () => {
            if (!dataRef.current) return showStatus('请先加载配置', 'error');
            try {
                const normalizedData = dataManager.normalize();
                const response = await axios.post('/api/prompts', normalizedData);
                showStatus(`保存成功: ${response.data.message}`, 'success');
            } catch (error) {
                const detail = error.response?.data?.detail;
                const parsedDetail = window.parseBackendError(detail) || detail || error.message;
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
    });

    window.addEventListener('DOMContentLoaded', () => {
        initSSEForNotifications();
    });
})();