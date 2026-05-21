/**
 * 小说卡片管理组件 - 单任务版本
 * 支持角色设定、人物关系、世界观规则、风格倾向四种卡片类型
 */
(function(window) {
  const NovelCards = {
    data: {
      character_profiles: [],
      relationship_map: [],
      worldview_rules: [],
      style_preference: [],
    },

    limits: {
      character_profiles: 8,
      relationship_map: 8,
      worldview_rules: 8,
      style_preference: 8,
    },

    currentEditType: null,
    currentEditIndex: null,

    typeConfig: {
      character: {
        dataKey: 'character_profiles',
        addBtn: '[data-add-btn="character"]',
        container: 'characterCards',
        titleAdd: '添加角色',
        titleEdit: '编辑角色',
      },
      relationship: {
        dataKey: 'relationship_map',
        addBtn: '[data-add-btn="relationship"]',
        container: 'relationshipCards',
        titleAdd: '添加关系',
        titleEdit: '编辑关系',
      },
      worldview: {
        dataKey: 'worldview_rules',
        addBtn: '[data-add-btn="worldview"]',
        container: 'worldviewCards',
        titleAdd: '添加规则',
        titleEdit: '编辑规则',
      },
      style: {
        dataKey: 'style_preference',
        addBtn: '[data-add-btn="style"]',
        container: 'styleCards',
        titleAdd: '添加风格',
        titleEdit: '编辑风格',
      },
    },

    init() {
      this.fetchLimits();
      this.renderAll();
    },

    async fetchLimits() {
      try {
        const res = await axios.get("/api/config/adaptation");
        if (res.data) {
          this.limits.character_profiles = res.data.character_profiles || 8;
          this.limits.relationship_map = res.data.relationship_map || 8;
          this.limits.worldview_rules = res.data.worldview_rules || 8;
          this.limits.style_preference = res.data.style_preference || 8;
        }
      } catch (err) {
        console.error("获取适配限制配置失败:", err);
      }
      this.updateAddButtons();
    },

    updateAddButtons() {
      Object.keys(this.typeConfig).forEach(type => {
        const config = this.typeConfig[type];
        const btn = document.querySelector(config.addBtn);
        if (btn) {
          const current = this.data[config.dataKey].length;
          const limit = this.limits[config.dataKey];
          btn.innerHTML = `<i class="fas fa-plus"></i> 添加 (${current}/${limit})`;
        }
      });
    },

    canAddCard(type) {
      const config = this.typeConfig[type];
      return this.data[config.dataKey].length < this.limits[config.dataKey];
    },

    addCard(type) {
      if (!this.canAddCard(type)) {
        const config = this.typeConfig[type];
        showStatus(`已达上限 ${this.limits[config.dataKey]} 条，如需注入更多卡片，请前往中枢控制台的辅助任务配置中修改上限`, 'error');
        return;
      }
      this.openModal(type, null);
    },

    editCard(type, index) {
      this.openModal(type, index);
    },

    deleteCard(type, index) {
      const overlay = document.createElement('div');
      overlay.className = 'modal-overlay active';
      overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.6);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1000;
      `;
      overlay.innerHTML = `
        <div class="modal-content-wrapper confirm-modal" style="background: #ffffff; border-radius: 8px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3); max-width: 400px; width: 90%;">
          <div class="modal-header">
            <h3 class="modal-title">确认删除</h3>
            <button class="modal-close" onclick="document.body.removeChild(document.querySelector('.modal-overlay.active'))">&times;</button>
          </div>
          <div style="padding: 20px; text-align: center;">
            <p>确定要删除吗？</p>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn-secondary" onclick="document.body.removeChild(document.querySelector('.modal-overlay.active'))">取消</button>
            <button type="button" class="btn-primary" onclick="window.NovelCards.confirmDelete('${type}', ${index})">确定</button>
          </div>
        </div>
      `;
      document.body.appendChild(overlay);
    },

    confirmDelete(type, index) {
      document.body.removeChild(document.querySelector('.modal-overlay.active'));
      const config = this.typeConfig[type];
      this.data[config.dataKey].splice(index, 1);
      this.render(type);
    },

    openModal(type, index = null) {
      this.currentEditType = type;
      this.currentEditIndex = index;
      const overlay = document.getElementById('modalOverlay');
      const content = document.getElementById('modalContent');

      const config = this.typeConfig[type];
      const title = index !== null ? config.titleEdit : config.titleAdd;

      content.innerHTML = `
        <div class="modal-content-wrapper">
          <div class="modal-header">
            <h3 class="modal-title">${title}</h3>
            <button class="modal-close" onclick="window.NovelCards.closeModal()">&times;</button>
          </div>
          <form onsubmit="window.NovelCards.saveCard(event)">
            ${this.renderForm(type, index)}
            <div class="modal-footer">
              <button type="button" class="btn-secondary" onclick="window.NovelCards.closeModal()">取消</button>
              <button type="submit" class="btn-primary">保存</button>
            </div>
          </form>
        </div>
      `;

      overlay.classList.add('active');
    },

    closeModal() {
      document.getElementById('modalOverlay').classList.remove('active');
      this.currentEditType = null;
      this.currentEditIndex = null;
    },

    renderForm(type, index) {
      const dataKey = this.typeConfig[type].dataKey;
      const item = index !== null ? this.data[dataKey][index] : null;

      switch (type) {
        case 'character':
          return `
            <div class="form-group">
              <label class="form-label">角色标识 <span>*</span></label>
              <input type="text" id="charName" class="form-input" value="${item ? this.escapeHtml(item.name) : ''}" placeholder="例如：张三">
            </div>
            <div class="form-group">
              <label class="form-label">核心身份 <span>*</span></label>
              <textarea id="charIdentity" class="form-textarea" placeholder="例如：圣心大教堂主教的养子，乌尔姆斯学府的教师">${item ? this.escapeHtml(item.identity) : ''}</textarea>
            </div>
            <div class="form-group">
              <label class="form-label">性格特质（用逗号分隔）</label>
              <input type="text" id="charPersonality" class="form-input" value="${item && item.personality ? item.personality.join(', ') : ''}" placeholder="例如：勇敢,善良,固执">
            </div>
            <div class="form-group">
              <label class="form-label">内心隐秘</label>
              <textarea id="charSecret" class="form-textarea" placeholder="角色内心的隐秘、软肋或矛盾...">${item ? this.escapeHtml(item.secret || '') : ''}</textarea>
            </div>
            <div class="form-group">
              <label class="form-label">感官细节</label>
              <textarea id="charPresence" class="form-textarea" placeholder="关键的感官细节，增加故事的真实感...">${item ? this.escapeHtml(item.presence || '') : ''}</textarea>
            </div>
            <div class="form-group">
              <label class="form-label">扩展信息（JSON格式）</label>
              <textarea id="charCustom" class="form-textarea" placeholder='{"key": "value"}'>${item && item.custom ? this.escapeHtml(JSON.stringify(item.custom, null, 2)) : ''}</textarea>
            </div>
          `;

        case 'relationship':
          return `
            <div class="form-group">
              <label class="form-label">关系描述 <span>*</span></label>
              <textarea id="relDescription" class="form-textarea" placeholder="例如：张三和李四是青梅竹马...">${item ? this.escapeHtml(item) : ''}</textarea>
            </div>
          `;

        case 'worldview':
          return `
            <div class="form-group">
              <label class="form-label">规则标识 <span>*</span></label>
              <input type="text" id="ruleName" class="form-input" value="${item ? this.escapeHtml(item.name) : ''}" placeholder="例如：魔法系统/时间法则">
            </div>
            <div class="form-group">
              <label class="form-label">规则说明 <span>*</span></label>
              <textarea id="ruleDescription" class="form-textarea" placeholder="详细描述这个规则...">${item ? this.escapeHtml(item.description) : ''}</textarea>
            </div>
            <div class="form-group">
              <label class="form-label">限制/代价</label>
              <textarea id="ruleLimitation" class="form-textarea" placeholder="规则的限制或代价...">${item ? this.escapeHtml(item.limitation || '') : ''}</textarea>
            </div>
            <div class="form-group">
              <label class="form-label">扩展条款（JSON格式）</label>
              <textarea id="ruleCustom" class="form-textarea" placeholder='{"key": "value"}'>${item && item.custom ? this.escapeHtml(JSON.stringify(item.custom, null, 2)) : ''}</textarea>
            </div>
          `;

        case 'style':
          return `
            <div class="form-group">
              <label class="form-label">风格描述 <span>*</span></label>
              <textarea id="styleDescription" class="form-textarea" placeholder="例如：古风、悬疑、浪漫、现实主义等...">${item ? this.escapeHtml(item) : ''}</textarea>
            </div>
          `;

        default:
          return '';
      }
    },

    saveCard(event) {
      event.preventDefault();
      const type = this.currentEditType;

      try {
        if (type === 'character') {
          const name = document.getElementById('charName').value.trim();
          const identity = document.getElementById('charIdentity').value.trim();
          const personalityStr = document.getElementById('charPersonality').value.trim();
          const secret = document.getElementById('charSecret').value.trim();
          const presence = document.getElementById('charPresence').value.trim();
          const customStr = document.getElementById('charCustom').value.trim();

          if (!name || !identity) {
          showStatus('角色标识和核心身份为必填项', 'error');
          return;
        }

          const personality = personalityStr ? personalityStr.split(',').map(p => p.trim()).filter(p => p) : [];
          let custom = {};
          if (customStr) {
            custom = JSON.parse(customStr);
          }

          const character = { name, identity, personality, secret, presence, custom };

          if (this.currentEditIndex !== null) {
            this.data.character_profiles[this.currentEditIndex] = character;
          } else {
            this.data.character_profiles.push(character);
          }

        } else if (type === 'relationship') {
          const description = document.getElementById('relDescription').value.trim();
          if (!description) {
            showStatus('关系描述为必填项', 'error');
            return;
          }

          if (this.currentEditIndex !== null) {
            this.data.relationship_map[this.currentEditIndex] = description;
          } else {
            this.data.relationship_map.push(description);
          }

        } else if (type === 'worldview') {
          const name = document.getElementById('ruleName').value.trim();
          const description = document.getElementById('ruleDescription').value.trim();
          const limitation = document.getElementById('ruleLimitation').value.trim();
          const customStr = document.getElementById('ruleCustom').value.trim();

          if (!name || !description) {
            showStatus('规则标识和规则说明为必填项', 'error');
            return;
          }

          let custom = {};
          if (customStr) {
            custom = JSON.parse(customStr);
          }

          const rule = { name, description, limitation, custom };

          if (this.currentEditIndex !== null) {
            this.data.worldview_rules[this.currentEditIndex] = rule;
          } else {
            this.data.worldview_rules.push(rule);
          }

        } else if (type === 'style') {
          const description = document.getElementById('styleDescription').value.trim();
          if (!description) {
            showStatus('风格描述为必填项', 'error');
            return;
          }

          if (this.currentEditIndex !== null) {
            this.data.style_preference[this.currentEditIndex] = description;
          } else {
            this.data.style_preference.push(description);
          }
        }

        this.render(type);
        this.closeModal();

      } catch (e) {
        showStatus('数据格式有误，请检查', 'error');
        console.error('保存失败:', e);
      }
    },

    render(type) {
      const config = this.typeConfig[type];
      const container = document.getElementById(config.container);
      const data = this.data[config.dataKey];

      if (data.length === 0) {
        container.innerHTML = this.renderEmptyState(type);
        this.updateAddButtons();
        return;
      }

      container.innerHTML = data.map((item, index) => {
        switch (type) {
          case 'character':
            return this.renderCharacterCard(item, index);
          case 'relationship':
            return this.renderRelationshipCard(item, index);
          case 'worldview':
            return this.renderWorldviewCard(item, index);
          case 'style':
            return this.renderStyleCard(item, index);
          default:
            return '';
        }
      }).join('');

      this.updateAddButtons();
    },

    renderAll() {
      Object.keys(this.typeConfig).forEach(type => this.render(type));
    },

    renderEmptyState(type) {
      const icons = {
        character: 'fa-user-plus',
        relationship: 'fa-link',
        worldview: 'fa-book',
        style: 'fa-palette',
      };
      const messages = {
        character: '暂无角色设定，点击上方按钮添加',
        relationship: '暂无人际关系，点击上方按钮添加',
        worldview: '暂无世界观规则，点击上方按钮添加',
        style: '暂无风格倾向，点击上方按钮添加',
      };

      return `
        <div class="empty-state" style="grid-column: 1/-1;">
          <i class="fas ${icons[type]}"></i>
          <p>${messages[type]}</p>
        </div>
      `;
    },

    renderCharacterCard(char, index) {
      return `
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-name">${this.escapeHtml(char.name)}</div>
              <div class="card-identity">${this.escapeHtml(char.identity)}</div>
            </div>
            <div class="card-actions">
              <button class="card-action-btn" onclick="window.NovelCards.editCard('character', ${index})" title="编辑">
                <i class="fas fa-edit"></i>
              </button>
              <button class="card-action-btn" onclick="window.NovelCards.deleteCard('character', ${index})" title="删除">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </div>
          ${char.personality && char.personality.length > 0 ? `
            <div class="card-field">
              <div class="card-field-label">性格特质</div>
              <div class="card-tags">
                ${char.personality.map(p => `<span class="card-tag">${this.escapeHtml(p)}</span>`).join('')}
              </div>
            </div>
          ` : ''}
          ${char.secret ? `
            <div class="card-field">
              <div class="card-field-label">内心隐秘</div>
              <div class="card-field-value">${this.escapeHtml(char.secret)}</div>
            </div>
          ` : ''}
          ${char.presence ? `
            <div class="card-field">
              <div class="card-field-label">感官细节</div>
              <div class="card-field-value">${this.escapeHtml(char.presence)}</div>
            </div>
          ` : ''}
          ${char.custom && Object.keys(char.custom).length > 0 ? `
            <div class="card-field">
              <div class="card-field-label">扩展信息</div>
              <div class="card-field-value">${this.escapeHtml(JSON.stringify(char.custom, null, 2))}</div>
            </div>
          ` : ''}
        </div>
      `;
    },

    renderRelationshipCard(rel, index) {
      return `
        <div class="card">
          <div class="card-header">
            <div class="card-name">关系 #${index + 1}</div>
            <div class="card-actions">
              <button class="card-action-btn" onclick="window.NovelCards.editCard('relationship', ${index})" title="编辑">
                <i class="fas fa-edit"></i>
              </button>
              <button class="card-action-btn" onclick="window.NovelCards.deleteCard('relationship', ${index})" title="删除">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </div>
          <div class="card-field">
            <div class="card-field-value">${this.escapeHtml(rel)}</div>
          </div>
        </div>
      `;
    },

    renderWorldviewCard(rule, index) {
      return `
        <div class="card">
          <div class="card-header">
            <div class="card-name">${this.escapeHtml(rule.name)}</div>
            <div class="card-actions">
              <button class="card-action-btn" onclick="window.NovelCards.editCard('worldview', ${index})" title="编辑">
                <i class="fas fa-edit"></i>
              </button>
              <button class="card-action-btn" onclick="window.NovelCards.deleteCard('worldview', ${index})" title="删除">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </div>
          <div class="card-field">
            <div class="card-field-label">规则说明</div>
            <div class="card-field-value">${this.escapeHtml(rule.description)}</div>
          </div>
          ${rule.limitation ? `
            <div class="card-field">
              <div class="card-field-label">限制/代价</div>
              <div class="card-field-value">${this.escapeHtml(rule.limitation)}</div>
            </div>
          ` : ''}
          ${rule.custom && Object.keys(rule.custom).length > 0 ? `
            <div class="card-field">
              <div class="card-field-label">扩展条款</div>
              <div class="card-field-value">${this.escapeHtml(JSON.stringify(rule.custom, null, 2))}</div>
            </div>
          ` : ''}
        </div>
      `;
    },

    renderStyleCard(style, index) {
      return `
        <div class="card">
          <div class="card-header">
            <div class="card-name">风格 #${index + 1}</div>
            <div class="card-actions">
              <button class="card-action-btn" onclick="window.NovelCards.editCard('style', ${index})" title="编辑">
                <i class="fas fa-edit"></i>
              </button>
              <button class="card-action-btn" onclick="window.NovelCards.deleteCard('style', ${index})" title="删除">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </div>
          <div class="card-field">
            <div class="card-field-value">${this.escapeHtml(style)}</div>
          </div>
        </div>
      `;
    },

    getData() {
      return { ...this.data };
    },

    setData(data) {
      if (data.character_profiles) this.data.character_profiles = data.character_profiles;
      if (data.relationship_map) this.data.relationship_map = data.relationship_map;
      if (data.worldview_rules) this.data.worldview_rules = data.worldview_rules;
      if (data.style_preference) this.data.style_preference = data.style_preference;
      this.renderAll();
    },

    escapeHtml(text) {
      if (!text) return '';
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    },
  };

  document.addEventListener('DOMContentLoaded', () => {
    NovelCards.init();

    document.addEventListener('click', (e) => {
      const overlay = document.getElementById('modalOverlay');
      if (overlay && e.target === overlay && overlay.classList.contains('active')) {
        NovelCards.closeModal();
      }
    });
  });
  
  window.NovelCards = NovelCards;
})(window);