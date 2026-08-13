/**
 * NovelAPI.CONST —— 跨层语义常量（前端 SSOT）
 * 取值必须与 Python 端 app/common/values.py VAL_TASK_TYPE_*、
 * capabilities.json 中各能力的 capability_id 完全对齐。
 * task_type 字段存储能力配置ID字符串，用于语义唯一键 (session_id, parent_id, task_type, sort_order)。
 * 层级模型（parent_id / sort_order 替代旧 scope_key_1/scope_key_2）：
 *   - EXTRACTION ('extract_session_memory') 会话记忆提取 —— parent_id=null, sort_order=0
 *   - GLOBAL_OUTLINE ('global_plot_design') 全局剧情设计 —— parent_id=null, sort_order=0
 *   - VOLUME_OUTLINE ('volume_plot_design') 卷级大纲 —— parent_id=global_outline.id, sort_order=volume_index(0-based)
 *   - CHAPTER_OUTLINE ('chapter_plot_design') 章级大纲 —— parent_id=volume_outline.id, sort_order=chapter_index(0-based)
 *   - CHAPTER_EVENTS ('chapter_events_design') 章级事件 —— parent_id=chapter_outline.id, sort_order=chapter_index(0-based)
 *   - CHAPTER_CONTENT ('chapter_content_generation') 章级内容 —— parent_id=chapter_outline.id, sort_order=chapter_index(0-based)
 * 语义唯一性由后端 (session_id, parent_id, task_type, sort_order) 复合索引保证，
 * 前端直接走 POST /api/tasks/semantic-upsert 单例覆写。
 */
const _T = {
  TASK_TYPE_CORE_PLOT: 'core_plot',
  TASK_TYPE_EXTRACTION: 'extract_session_memory',
  TASK_TYPE_GLOBAL_OUTLINE: 'global_plot_design',
  TASK_TYPE_VOLUME_OUTLINE: 'volume_plot_design',
  TASK_TYPE_CHAPTER_OUTLINE: 'chapter_plot_design',
  TASK_TYPE_CHAPTER_EVENTS: 'chapter_events_design',
  TASK_TYPE_CHAPTER_CONTENT: 'chapter_content_generation',
  // 图像提示词优化：与 capabilities.json capability_id 完全对齐（SSOT）
  TASK_TYPE_IMAGE_PROMPT_REFINE: 'image_prompt_refine',
};

/* ============== Task 契约 SSOT（与 Rust src/entity/task.rs Task struct、Python app/routers/tasks.py _TASK_ALLOWED_FIELDS 完全一一对应） ============== */
const _TASK_WHITELIST_FIELDS = Object.freeze([
  'id',
  'session_id',
  'task_type',
  'sequence',
  'parent_id',
  'sort_order',
  'volume_index',
  'chapter_index',
  'status',
  'title',
  'content_text',
  'word_count',
  'created_at',
  'updated_at',
]);
const _TASK_UPDATE_IMMUTABLE_KEYS = Object.freeze([
  'id', 'session_id', 'sequence', 'parent_id', 'sort_order', 'volume_index', 'chapter_index', 'created_at', 'updated_at',
]);
/** create 时严格过滤到白名单字段，防止未知字段触发后端/引擎 strict mode。 */
function _sanitizeTaskCreatePayload(raw) {
  if (!raw || typeof raw !== 'object') return {};
  const out = {};
  for (let i = 0; i < _TASK_WHITELIST_FIELDS.length; i++) {
    const k = _TASK_WHITELIST_FIELDS[i];
    if (Object.prototype.hasOwnProperty.call(raw, k)) out[k] = raw[k];
  }
  return out;
}
/** update 时过滤到白名单 & 剥离不可变字段（id/session_id/parent_id/sort_order / 时间戳），避免破坏唯一索引。 */
function _sanitizeTaskUpdatePatch(raw) {
  if (!raw || typeof raw !== 'object') return {};
  const immutableSet = {};
  for (let i = 0; i < _TASK_UPDATE_IMMUTABLE_KEYS.length; i++) immutableSet[_TASK_UPDATE_IMMUTABLE_KEYS[i]] = true;
  const out = {};
  for (let i = 0; i < _TASK_WHITELIST_FIELDS.length; i++) {
    const k = _TASK_WHITELIST_FIELDS[i];
    if (!Object.prototype.hasOwnProperty.call(raw, k)) continue;
    if (immutableSet[k]) continue;
    out[k] = raw[k];
  }
  return out;
}

let _timeoutsCache = null;
let _timeoutsPromise = null;

async function _ensureTimeouts() {
    if (_timeoutsCache) return _timeoutsCache;
    if (_timeoutsPromise) return _timeoutsPromise;
    _timeoutsPromise = axios.get('/api/meta/frontend-timeout', { timeout: 5000 })
        .then(res => {
            _timeoutsCache = res.data || {};
            return _timeoutsCache;
        })
        .catch(err => {
            console.warn('Failed to fetch frontend timeouts, using defaults:', err?.message || err);
            _timeoutsCache = {};
            return _timeoutsCache;
        });
    return _timeoutsPromise;
}

function _getTimeoutSeconds(key, defaultSeconds) {
    if (_timeoutsCache && typeof _timeoutsCache[key] === 'number') {
        return _timeoutsCache[key];
    }
    return defaultSeconds;
}

function _toMs(seconds) {
    return seconds * 1000;
}

const NovelAPI = {
  CONST: Object.freeze({
    ..._T,
    // Task 字段白名单 SSOT（前端 create/update 前强制过滤）
    TASK_FIELDS_WHITELIST: _TASK_WHITELIST_FIELDS,
    TASK_UPDATE_IMMUTABLE_KEYS: _TASK_UPDATE_IMMUTABLE_KEYS,
  }),

  async getWorks() {
    const res = await axios.get("/api/works/", { timeout: 10000 });
    return res.data;
  },

  async createWork(data) {
    const res = await axios.post("/api/works/", data, { timeout: 10000 });
    return res.data;
  },

  async updateWork(id, data) {
    const res = await axios.patch(`/api/works/${id}`, data, { timeout: 10000 });
    return res.data;
  },

  async deleteWork(id) {
    const res = await axios.delete(`/api/works/${id}`, { timeout: 10000 });
    return res.data;
  },

  async getSessionMemories(sessionId) {
    const res = await axios.get('/api/session-memories/', {
      params: { session_id: sessionId },
      timeout: 10000,
    });
    return res.data;
  },

  async invokeCapability(sessionId, capabilityId, variables, taskId) {
    await _ensureTimeouts();
    const payload = {
      session_id: sessionId,
      capability_id: capabilityId,
      variables: variables || {},
    };
    if (taskId !== undefined && taskId !== null && taskId !== '') {
      const n = Number(taskId);
      if (Number.isInteger(n) && n > 0) payload.task_id = n;
    }
    const timeoutMs = _toMs(_getTimeoutSeconds('text_api_timeout_seconds', 180));
    const res = await axios.post('/api/capabilities/invoke', payload, { timeout: timeoutMs });
    return res.data;
  },

  /**
   * 带锁与 SSE 竞态裁决的能力调用公共工具。
   *
   * 设计依据（基于后端实际逻辑，非推测）：
   *  - 后端 _invoke_capability_single 是同步等待 LLM 完成后才 return HTTP；
   *    期间通过 SSE 广播进度，最终态事件（progress=100 & success=...）先于 HTTP 响应到达。
   *  - SSE 最终态事件只携带 meta（task_id/token_cost/volume_index/chapter_index），
   *    不携带 content_text 等结果数据；结果数据只在 HTTP 响应体中。
   *
   * 竞态裁决策略（HTTP 优先，SSE 兜底）：
   *  1. HTTP 成功 → 直接用 HTTP 结果（覆盖绝大多数正常路径，结果完整）。
   *  2. HTTP 失败（超时/网络错误/非 409）→ 等待 SSE 最终态（宽限期 30s，容忍后端重试）：
   *     - SSE success=true → 任务实际成功，但 HTTP 未拿到结果，返回 needRefetch=true
   *       由调用方按各自的 task 加载逻辑重新拉取结果（各页面已有 listTasks + 解析逻辑）。
   *     - SSE success=false → 任务失败，返回失败。
   *     - 宽限期超时仍未到 → 返回 HTTP 错误（任务可能仍在后台进行）。
   *  3. HTTP 409 冲突 → 立即返回 conflict=true（后端幂等检查命中，SSE 失败事件已广播）。
   *
   * 并发保护：基于 lockKey 的进程内锁拒绝并发调用；后端另有 409 幂等检查双保险。
   *
   * SSE 事件结构：listenSSE 派发的 detail 形如 { eventType, data: { title, content, meta } }，
   * 索引字段位于 detail.data.meta，与后端 _build_sse_meta 输出严格对齐。
   *
   * @param {object} opts
   * @param {string} opts.capabilityId  能力 ID（用 NovelAPI.CONST.TASK_TYPE_* 传入，避免硬编码）
   * @param {object} opts.variables     请求变量
   * @param {string} opts.lockKey       幂等锁键（必填，调用方按维度拼接，如 `content_0_2`）
   * @param {number} [opts.volumeIndex] SSE 匹配用 volume_index（卷/章类能力必填）
   * @param {number} [opts.chapterIndex] SSE 匹配用 chapter_index（章类能力必填）
   * @param {string|number} [opts.taskId]
   * @returns {Promise<{ok:boolean, result:object|null, error:Error|null, conflict:boolean, source:'sse'|'http'|'none', needRefetch:boolean}>}
   */
  async runCapabilityWithSSE(opts) {
    const o = opts || {};
    const capabilityId = o.capabilityId;
    const variables = o.variables || {};
    const lockKey = String(o.lockKey || capabilityId || '');

    if (!window._capabilityLocks) window._capabilityLocks = Object.create(null);
    if (!capabilityId) {
      return { ok: false, result: null, error: new Error('capabilityId 为必填'), conflict: false, source: 'none', needRefetch: false };
    }
    if (window._capabilityLocks[lockKey]) {
      return {
        ok: false, result: null,
        error: new Error('该任务正在生成中，请稍候...'),
        conflict: true, source: 'none', needRefetch: false,
      };
    }

    window._capabilityLocks[lockKey] = true;
    let sseUnsubscribe = null;

    try {
      // SSE 监听：等待与本调用匹配的最终态事件（progress=100 & success 已确定 & 索引匹配）
      let sseResolve = null;
      const ssePromise = new Promise((resolve) => { sseResolve = resolve; });

      if (typeof window.listenSSE === 'function') {
        sseUnsubscribe = window.listenSSE('task_progress', (detail) => {
          // detail 结构：{ eventType, data: { title, content, meta } }
          const data = detail && detail.data;
          const meta = data && data.meta;
          if (!meta || String(meta.capability_id) !== String(capabilityId)) return;
          if (meta.progress !== 100) return;
          if (meta.success !== true && meta.success !== false) return;
          // 索引匹配：volume/chapter 维度
          if (o.volumeIndex !== undefined && meta.volume_index !== undefined
              && Number(meta.volume_index) !== Number(o.volumeIndex)) return;
          if (o.chapterIndex !== undefined && meta.chapter_index !== undefined
              && Number(meta.chapter_index) !== Number(o.chapterIndex)) return;
          // 幂等冲突事件（error=ALREADY_IN_PROGRESS）不作为最终结果，由 HTTP 409 路径处理
          if (meta.error === 'ALREADY_IN_PROGRESS') return;
          sseResolve({
            ok: meta.success === true,
            meta: meta, data: data,
          });
        });
      }

      // HTTP 请求（捕获错误，避免 Promise.all 因 HTTP 失败而短路）
      const httpPromise = NovelAPI.invokeCapability(
        window.currentWorkId, capabilityId, variables, o.taskId,
      ).then((data) => ({ ok: true, data, httpErr: null }))
       .catch((err) => {
         // 409 冲突：后端幂等检查命中
         if (err && err.response && err.response.status === 409) {
           const detail = (err.response.data && err.response.data.detail) || '该任务正在生成中，请稍候...';
           return { ok: false, data: null, httpErr: new Error(detail), conflict: true };
         }
         return { ok: false, data: null, httpErr: err, conflict: false };
       });

      const httpResult = await httpPromise;

      // HTTP 命中冲突，直接返回（SSE 失败事件已由后端广播，前端其他监听者会处理）
      if (httpResult.conflict) {
        return {
          ok: false, result: null,
          error: httpResult.httpErr,
          conflict: true, source: 'http', needRefetch: false,
        };
      }

      // HTTP 成功 → 直接用 HTTP 结果（结果完整，无需 SSE 兜底）
      if (httpResult.ok) {
        return {
          ok: true, result: httpResult.data,
          error: null, conflict: false, source: 'http', needRefetch: false,
        };
      }

      // HTTP 失败（非冲突）→ 等待 SSE 最终态作为兜底（宽限期 30s，容忍后端重试耗时）
      const SSE_GRACE_MS = 30000;
      let graceTimer = null;
      const graceTimeout = new Promise((resolve) => {
        graceTimer = setTimeout(() => resolve({ timeout: true }), SSE_GRACE_MS);
      });

      const sseFinal = await Promise.race([ssePromise, graceTimeout]);
      if (graceTimer) { clearTimeout(graceTimer); graceTimer = null; }

      if (sseFinal && !sseFinal.timeout) {
        // SSE 给出最终态
        if (sseFinal.ok) {
          // 任务实际成功，但 HTTP 未拿到结果 → 调用方需重新拉取
          return {
            ok: true, result: null,
            error: null, conflict: false, source: 'sse', needRefetch: true,
          };
        }
        const errMsg = (sseFinal.data && sseFinal.data.content) || '任务执行失败';
        return {
          ok: false, result: null,
          error: new Error(errMsg),
          conflict: false, source: 'sse', needRefetch: false,
        };
      }

      // SSE 宽限期超时仍未到达 → 返回 HTTP 错误（任务可能仍在后台进行）
      return {
        ok: false, result: null,
        error: httpResult.httpErr || new Error('未知错误'),
        conflict: false, source: 'http', needRefetch: false,
      };
    } finally {
      // 确保锁与 SSE 订阅一定被释放
      if (window._capabilityLocks[lockKey]) {
        delete window._capabilityLocks[lockKey];
      }
      if (typeof sseUnsubscribe === 'function') {
        try { sseUnsubscribe(); } catch (_e) {}
      }
    }
  },

  async previewInjection(sessionId, capabilityId, variables) {
    const safeVariables = variables && typeof variables === 'object' ? variables : {};
    console.info(
      `[预览注入请求] workId=${sessionId} capabilityId=${capabilityId} ` +
      `variablesKeys=${Object.keys(safeVariables).join(',')}`
    );
    const payload = {
      session_id: sessionId,
      capability_id: capabilityId,
      variables: safeVariables,
    };
    try {
      const res = await axios.post('/api/capabilities/preview-injection', payload, { timeout: 15000 });
      const data = res && res.data ? res.data : {};
      const slots = data.slots || {};
      const char = slots.characters || { selected: [], unselected: [] };
      const time = slots.temporals || { selected: [], unselected: [] };
      const loc = slots.locations || { selected: [], unselected: [] };
      const mem = slots.session_memories || { selected: [], unselected: [] };
      const summary = data.summary || {};
      console.info(
        `[预览注入收到] workId=${sessionId} capabilityId=${capabilityId} ` +
        `slots=角色(${char.selected.length}/${char.unselected.length}) ` +
        `时间(${time.selected.length}/${time.unselected.length}) ` +
        `地点(${loc.selected.length}/${loc.unselected.length}) ` +
        `记忆(${mem.selected.length}/${mem.unselected.length}) ` +
        `totalChars=${summary.total_chars || 0}`
      );
      return data;
    } catch (err) {
      const msg = (err && err.message) ? err.message : String(err);
      console.warn(
        `[预览注入失败] workId=${sessionId} capabilityId=${capabilityId} err=${msg}；请检查网络或后端日志`
      );
      if (typeof showStatus === 'function') {
        showStatus(`预览注入失败：${msg}；请检查网络或后端日志`, 'error');
      }
      throw err;
    }
  },

  async invokeCapabilityBatch(sessionId, capabilityId, variablesList, taskId) {
    await _ensureTimeouts();
    const payload = {
      session_id: sessionId,
      capability_id: capabilityId,
      batch: Array.isArray(variablesList) ? variablesList : [],
    };
    if (taskId !== undefined && taskId !== null && taskId !== '') {
      const n = Number(taskId);
      if (Number.isInteger(n) && n > 0) payload.task_id = n;
    }
    const timeoutMs = _toMs(_getTimeoutSeconds('batch_api_timeout_seconds', 300));
    const res = await axios.post('/api/capabilities/invoke-batch', payload, { timeout: timeoutMs });
    return res.data;
  },

  async listSemanticVocabularies(sessionId, category) {
    const res = await axios.get('/api/semantic-vocabularies/', {
      params: { session_id: sessionId, category: category },
      timeout: 10000,
    });
    return res.data;
  },
  async createSemanticVocabulary(payload) {
    const res = await axios.post('/api/semantic-vocabularies/', payload, { timeout: 10000 });
    return res.data;
  },

  async updateSemanticVocabulary(id, patch) {
    const res = await axios.patch(`/api/semantic-vocabularies/${encodeURIComponent(id)}`, patch, {
      timeout: 10000,
    });
    return res.data;
  },

  async deleteSemanticVocabulary(id) {
    const res = await axios.delete(`/api/semantic-vocabularies/${encodeURIComponent(id)}`, {
      timeout: 10000,
    });
    return res.data;
  },

  async getNextTimelineSortIndex(sessionId, category = 'temporal') {
    const fallbackLocal = () => {
      const list = Array.isArray(window?.weaveData?.timelines) ? window.weaveData.timelines : [];
      let max = -1;
      for (const t of list) {
        const v = Number(t?.sort_index);
        if (!Number.isNaN(v) && v >= 0 && v > max) max = v;
      }
      return max < 0 ? 0 : max + 1;
    };
    try {
      const res = await axios.get('/api/semantic-vocabularies/actions/next-sort-index', {
        params: { session_id: sessionId, category: category },
        timeout: 8000,
      });
      const val = Number(res?.data?.next_sort_index);
      if (!Number.isNaN(val) && Number.isFinite(val)) return Math.trunc(val);
      console.warn('[NovelAPI.getNextTimelineSortIndex] 接口返回无效值，回退本地计算');
      return fallbackLocal();
    } catch (err) {
      console.warn('[NovelAPI.getNextTimelineSortIndex] 接口失败，回退本地计算:', err?.message || err);
      return fallbackLocal();
    }
  },

  async listTasks(sessionId, taskType, orderBy = 'id', desc = true, excludeContent = false) {
    const res = await axios.get('/api/tasks/', {
      params: {
        session_id: sessionId,
        task_type: taskType !== undefined && taskType !== null ? taskType : undefined,
        order_by: orderBy,
        desc: desc ? true : undefined,
        exclude_content: excludeContent ? true : undefined,
      },
      timeout: 10000,
    });
    const data = res?.data;
    return Array.isArray(data) ? data : (Array.isArray(data?.data) ? data.data : []);
  },

  async createTask(payload) {
    const safe = _sanitizeTaskCreatePayload(payload || {});
    const res = await axios.post('/api/tasks/', safe, { timeout: 10000 });
    return res?.data || {};
  },

  async updateTask(taskId, patch) {
    const safe = _sanitizeTaskUpdatePatch(patch || {});
    const res = await axios.patch(`/api/tasks/${encodeURIComponent(String(taskId))}`, safe, { timeout: 10000 });
    return res?.data || {};
  },

  async deleteTask(taskId) {
    const res = await axios.delete(`/api/tasks/${encodeURIComponent(String(taskId))}`, { timeout: 10000 });
    return res?.data || {};
  },

  async cascadeDelete(taskId) {
    const res = await axios.delete(`/api/tasks/cascade/${encodeURIComponent(String(taskId))}`, { timeout: 10000 });
    return res?.data || {};
  },

  async semanticUpsertTask(payload) {
    /** 语义化 upsert（单例覆写入口，后端唯一索引真实保证唯一性）。
     *  POST /api/tasks/semantic-upsert → engine.task_upsert_semantic
     *  键：(session_id, parent_id, task_type, sort_order)
     *  - 存在：保持原 id/sequence/parent_id/sort_order 不变，仅重置业务字段
     *  - 不存在：新插入，sequence = 当前 session 下 MAX(sequence)+1
     *  返回：{ ok: true, task_id: number }
     */
    const safe = _sanitizeTaskCreatePayload(payload || {});
    const res = await axios.post('/api/tasks/semantic-upsert', safe, { timeout: 10000 });
    return res?.data || {};
  },

  /** 导出完整作品创作包（谋篇剧情+分卷+章纲+事件链+正文）。
   *  GET /api/works/{session_id}/export → zip 二进制流，浏览器触发下载到 Downloads。
   *  返回 { blob, suggestedName }，上层负责用 <a download> 触发。
   *  超时放宽到 60s：长作品需要聚合多轮 listTasks 并压缩。
   */
  async exportWork(sessionId) {
    const sid = typeof sessionId === 'string' ? sessionId.trim() : '';
    if (!sid) throw new Error('exportWork: session_id 不能为空');
    const timeoutMs = _getTimeoutSeconds('work_export_timeout_sec', 60) * 1000;
    const res = await axios.get(`/api/works/${encodeURIComponent(sid)}/export`, {
      responseType: 'blob',
      timeout: timeoutMs,
    });
    const blob = res?.data instanceof Blob ? res.data : null;
    if (!blob) throw new Error('exportWork: 响应缺失 blob 数据');
    let suggestedName = '';
    try {
      const disp = String(res.headers && res.headers['content-disposition'] ? res.headers['content-disposition'] : '');
      const match = disp.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
      if (match && match[1]) suggestedName = decodeURIComponent(match[1].trim());
    } catch (_e) { /* ignore parse error */ }
    if (!suggestedName) suggestedName = `作品创作包-${Date.now()}.zip`;
    return { blob, suggestedName };
  },

  async upsertCorePlot(sessionId, text) {
    const content = typeof text === 'string' ? text : '';
    const wc = content.length;
    const res = await this.semanticUpsertTask({
      session_id: sessionId,
      task_type: NovelAPI.CONST.TASK_TYPE_CORE_PLOT,
      sequence: 0,
      parent_id: null,
      sort_order: 0,
      volume_index: null,
      chapter_index: null,
      status: 'completed',
      title: '剧情核心输入',
      content_text: content,
      word_count: wc,
    });
    return res || {};
  },

  async upsertOutline(sessionId, plot, summary) {
    const getThHard = (key, fallback) => {
      if (typeof window === 'undefined' || !window.frontendThresholds || typeof window.frontendThresholds !== 'object') return fallback;
      const v = window.frontendThresholds[key];
      if (v === undefined || v === null || v === '') return fallback;
      const n = Number(v);
      return Number.isFinite(n) && n > 0 ? n : fallback;
    };
    const PLOT_HARD = getThHard('global_plot_hard_chars', 2000);
    const SUM_HARD = getThHard('global_summary_hard_chars', 300);
    const pRaw = typeof plot === 'string' ? plot : '';
    const sRaw = typeof summary === 'string' ? summary : '';
    const p = pRaw.length > PLOT_HARD ? pRaw.slice(0, PLOT_HARD) : pRaw;
    const s = sRaw.length > SUM_HARD ? sRaw.slice(0, SUM_HARD) : sRaw;
    if ((p.length !== pRaw.length || s.length !== sRaw.length) && typeof showStatus === 'function') {
      const tips = [];
      if (p.length !== pRaw.length) tips.push(`全局剧情超过最大硬截断上限 ${PLOT_HARD} 字，已自动舍弃末尾注水内容`);
      if (s.length !== sRaw.length) tips.push(`剧情摘要超过最大硬截断上限 ${SUM_HARD} 字，已自动舍弃末尾注水内容`);
      if (tips.length) showStatus(tips.join('；') + '，可手动调整后重新保存。', 'warn');
    }
    const contentObj = { _v: 2, plot: p, summary: s };
    const contentText = JSON.stringify(contentObj);
    const wc = (p + s).length;
    const res = await this.semanticUpsertTask({
      session_id: sessionId,
      task_type: NovelAPI.CONST.TASK_TYPE_GLOBAL_OUTLINE,
      sequence: 0,
      parent_id: null,
      sort_order: 0,
      volume_index: null,
      chapter_index: null,
      status: 'completed',
      title: '全局剧情设计',
      content_text: contentText,
      word_count: wc,
    });
    return res || {};
  },

  /** 图像提示词优化入口：仅前端点击「优化提示词」按钮时调用（不默认触发）。
   *  POST /api/images/generate/refine-prompt
   *  返回：{ ok:true, prompt_text: string }
   */
  async refineImagePrompt(sessionId, userPrompt) {
    const sid = typeof sessionId === 'string' ? sessionId : '';
    const text = typeof userPrompt === 'string' ? userPrompt : '';
    if (!sid || !text.trim()) return { ok: false, prompt_text: '' };
    const res = await axios.post('/api/images/generate/refine-prompt', {
      session_id: sid,
      user_prompt: text,
    }, { timeout: 60000 });
    return (res && res.data) ? res.data : { ok: false, prompt_text: '' };
  },

  /** 图像提示词 upsert（单例覆写），每章一条，用于下次进入章节自动回填。
   *  语义唯一键：(session_id, parent_id=null, task_type=image_prompt_refine, sort_order=volIdx*1000+chapIdx)
   *  volume_index/chapter_index 同时写入，便于直接定位。
   */
  async upsertImagePrompt(sessionId, volumeIndex, chapterIndex, prompt) {
    const vi = Number.isFinite(Number(volumeIndex)) ? Number(volumeIndex) : 0;
    const ci = Number.isFinite(Number(chapterIndex)) ? Number(chapterIndex) : 0;
    const sortOrder = vi * 1000 + ci;
    const content = typeof prompt === 'string' ? prompt : '';
    const res = await this.semanticUpsertTask({
      session_id: typeof sessionId === 'string' ? sessionId : '',
      task_type: NovelAPI.CONST.TASK_TYPE_IMAGE_PROMPT_REFINE,
      sequence: 0,
      parent_id: null,
      sort_order: sortOrder,
      volume_index: vi,
      chapter_index: ci,
      status: 'completed',
      title: `卷${vi + 1}章${ci + 1}图像提示词`,
      content_text: content,
      word_count: content.length,
    });
    return res || {};
  },

  /** 查询某章最近的 image_prompt_refine task（已完成状态）。返回 task 或 null。 */
  async fetchImagePrompt(sessionId, volumeIndex, chapterIndex) {
    const vi = Number.isFinite(Number(volumeIndex)) ? Number(volumeIndex) : 0;
    const ci = Number.isFinite(Number(chapterIndex)) ? Number(chapterIndex) : 0;
    const sid = typeof sessionId === 'string' ? sessionId : '';
    const rows = await this.listTasks(sid, NovelAPI.CONST.TASK_TYPE_IMAGE_PROMPT_REFINE, 'id', true);
    if (!Array.isArray(rows) || rows.length === 0) return null;
    for (const r of rows) {
      if (!r) continue;
      if (Number(r.volume_index) === vi && Number(r.chapter_index) === ci) {
        if (String(r.status || '').toLowerCase() === 'completed') return r;
      }
    }
    return null;
  },

  async getFrontendThresholds() {
    const res = await axios.get('/api/meta/frontend-thresholds', { timeout: 10000 });
    return res.data || {};
  },

  async fetchLatestCompletedTask(sessionId, taskType) {
    /** 语义唯一索引保证单例，但任务可能处于 pending/failed 状态。
     *  必须过滤 completed，避免取到失败/进行中的任务导致下游级联错误。
     *  用 id desc 确保取到最新（id 最大）的已完成任务，避免旧残留任务被误取。 */
    const rows = await this.listTasks(sessionId, taskType, 'id', true);
    if (!Array.isArray(rows) || rows.length === 0) return null;
    for (const r of rows) {
      if (r && String(r.status || '').toLowerCase() === 'completed') return r;
    }
    return null;
  },

  async findTaskBySortOrder(sessionId, taskType, sortOrder, parentId = undefined) {
    /** 查找任务（分级大纲任务已切到 volume_index / chapter_index 优先的幂等）。
     *  优先匹配 volume_index / chapter_index（与 Rust 层的大纲幂等键对齐，parent_id 重建不影响命中）；
     *  对非大纲任务 / 无 volume_index 的旧数据，再按 task_type + sort_order (+ parent_id) 兜底。
     *  用 id desc 取最新，兼容历史重复数据。
     */
    const rows = await this.listTasks(sessionId, taskType, 'id', true);
    if (!Array.isArray(rows) || rows.length === 0) return null;
    const targetSort = Number(sortOrder);
    const isOutline = (taskType === NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE)
      || (taskType === NovelAPI.CONST.TASK_TYPE_CHAPTER_OUTLINE)
      || (taskType === NovelAPI.CONST.TASK_TYPE_CHAPTER_EVENTS);
    // 大纲类：先按 volume_index / chapter_index 找（忽略 parent_id，与 Rust 层 upsert 键保持一致）
    if (isOutline) {
      for (const r of rows) {
        const rVi = (r.volume_index !== null && r.volume_index !== undefined) ? Number(r.volume_index) : NaN;
        if (isNaN(rVi)) continue;
        // 卷纲：只匹配 volume_index（chapter_index 应为 NULL/0），且用传入的 sortOrder 与 volume_index 对齐
        if (taskType === NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE) {
          if (rVi === targetSort) return r;
          continue;
        }
        // 章纲 / 章事件：sort_order 语义是 chapter_index，且 volume_index 是外层卷的下标（需由调用方保证）
        // 注意：findTaskBySortOrder 的签名只收一个 sortOrder 数字，所以此处无法精确校验 volume_index，
        // 但大多数情况下"同 sort_order 的最新章"是正确的；若需要严格匹配，由 get_by_volume_chapter_key 后端直接查。
        const rCi = (r.chapter_index !== null && r.chapter_index !== undefined) ? Number(r.chapter_index) : NaN;
        if (!isNaN(rCi) && rCi === targetSort) return r;
        // 旧数据：chapter_index 为空时按 sort_order 匹配
        if (isNaN(rCi) && Number(r.sort_order) === targetSort) return r;
      }
    }
    // 兜底：按 sort_order + parent_id 匹配（非大纲类任务沿用旧语义，大纲类按 volume_index 没命中时的兼容路径）
    for (const r of rows) {
      if (Number(r.sort_order) !== targetSort) continue;
      if (parentId !== undefined) {
        const rPid = r.parent_id;
        if (parentId === null) {
          if (rPid !== null && rPid !== undefined && rPid !== 0 && rPid !== '0' && rPid !== '') continue;
        } else {
          if (Number(rPid) !== Number(parentId)) continue;
        }
      }
      return r;
    }
    return null;
  },

  async createVolumeOutline(sessionId, volumeIndex, events, extra, prebuiltContentText, prebuiltWc) {
    const vi = Number.isInteger(Number(volumeIndex)) ? Number(volumeIndex) : 0;
    const globalOutlineTask = await this.fetchLatestCompletedTask(sessionId, NovelAPI.CONST.TASK_TYPE_GLOBAL_OUTLINE);
    const parentId = globalOutlineTask ? globalOutlineTask.id : null;
    let contentText = '';
    let wc = 0;
    let cleanEvents = [];
    if (typeof prebuiltContentText === 'string' && prebuiltContentText) {
      contentText = prebuiltContentText;
      wc = Number(prebuiltWc) || 0;
      cleanEvents = (Array.isArray(events) ? events : []).filter(e => e && (typeof e.plot === 'string' || typeof e.summary === 'string'));
    } else {
      const arr = Array.isArray(events) ? events : [];
      cleanEvents = arr.filter(e => e && (typeof e.plot === 'string' || typeof e.summary === 'string')).map(e => ({
        plot: typeof e.plot === 'string' ? e.plot : '',
        summary: typeof e.summary === 'string' ? e.summary : '',
      }));
      const meta = {};
      if (typeof extra === 'object' && extra && !Array.isArray(extra)) {
        if (typeof extra.global_plot === 'string' && extra.global_plot.trim()) {
          meta.global_plot_ref = extra.global_plot.trim().slice(0, 400);
        }
        if (typeof extra.global_summary === 'string' && extra.global_summary.trim()) {
          meta.global_summary_ref = extra.global_summary.trim().slice(0, 400);
        }
        if (typeof extra.prev_plot === 'string' && extra.prev_plot.trim()) {
          meta.prev_plot_ref = extra.prev_plot.trim().slice(0, 400);
        }
        if (typeof extra.prev_summary === 'string' && extra.prev_summary.trim()) {
          meta.prev_summary_ref = extra.prev_summary.trim().slice(0, 400);
        }
      }
      const firstEvent = cleanEvents[0] || {};
      const plot = typeof firstEvent.plot === 'string' ? firstEvent.plot : '';
      const summary = typeof firstEvent.summary === 'string' ? firstEvent.summary : '';
      wc += plot.length + summary.length;
      if (meta.global_plot_ref) wc += meta.global_plot_ref.length;
      if (meta.global_summary_ref) wc += meta.global_summary_ref.length;
      if (meta.prev_plot_ref) wc += meta.prev_plot_ref.length;
      if (meta.prev_summary_ref) wc += meta.prev_summary_ref.length;
      const contentObj = { _v: 2, plot: plot, summary: summary };
      if (Object.keys(meta).length > 0) contentObj._meta = meta;
      contentText = JSON.stringify(contentObj);
    }
    return this.semanticUpsertTask({
      session_id: sessionId,
      task_type: NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE,
      sequence: 0,
      parent_id: parentId,
      sort_order: vi,
      volume_index: vi,
      chapter_index: null,
      status: 'completed',
      title: `卷纲剧情设计（第 ${vi + 1} 卷）`,
      content_text: contentText,
      word_count: wc,
    });
  },

  async createChapterOutline(sessionId, volumeIndex, chapterIndex, events, extra, prebuiltContentText, prebuiltWc) {
    const vi = Number.isInteger(Number(volumeIndex)) ? Number(volumeIndex) : 0;
    const ci = Number.isInteger(Number(chapterIndex)) ? Number(chapterIndex) : 0;
    // 必须先拿到 global outline 的 id 作为 parentId，再查 volume outline，避免重复记录时找错 parent
    const globalOutlineTask = await this.fetchLatestCompletedTask(sessionId, NovelAPI.CONST.TASK_TYPE_GLOBAL_OUTLINE);
    const globalParentId = globalOutlineTask ? globalOutlineTask.id : null;
    const volumeOutlineTask = await this.findTaskBySortOrder(sessionId, NovelAPI.CONST.TASK_TYPE_VOLUME_OUTLINE, vi, globalParentId);
    const parentId = volumeOutlineTask ? volumeOutlineTask.id : null;
    let contentText = '';
    let wc = 0;
    let cleanEvents = [];
    if (typeof prebuiltContentText === 'string' && prebuiltContentText) {
      contentText = prebuiltContentText;
      wc = Number(prebuiltWc) || 0;
      cleanEvents = (Array.isArray(events) ? events : []).filter(e => e && (typeof e.event === 'string' || typeof e.summary === 'string'));
    } else {
      const arr = Array.isArray(events) ? events : [];
      cleanEvents = arr.filter(e => e && (typeof e.event === 'string' || typeof e.summary === 'string')).map(e => ({
        event: typeof e.event === 'string' ? e.event : '',
        summary: typeof e.summary === 'string' ? e.summary : '',
      }));
      const meta = {};
      if (typeof extra === 'object' && extra && !Array.isArray(extra)) {
        if (typeof extra.volume_plot === 'string' && extra.volume_plot.trim()) {
          meta.volume_plot_ref = extra.volume_plot.trim().slice(0, 400);
        }
        if (typeof extra.volume_summary === 'string' && extra.volume_summary.trim()) {
          meta.volume_summary_ref = extra.volume_summary.trim().slice(0, 400);
        }
      }
      for (const e of cleanEvents) {
        wc += (e.event || '').length + (e.summary || '').length;
      }
      if (meta.volume_plot_ref) wc += meta.volume_plot_ref.length;
      if (meta.volume_summary_ref) wc += meta.volume_summary_ref.length;
      const contentObj = { _v: 2, plot: cleanEvents[0]?.event || '', summary: cleanEvents[0]?.summary || '' };
      if (Object.keys(meta).length > 0) contentObj._meta = meta;
      contentText = JSON.stringify(contentObj);
    }
    return this.semanticUpsertTask({
      session_id: sessionId,
      task_type: NovelAPI.CONST.TASK_TYPE_CHAPTER_OUTLINE,
      sequence: 0,
      parent_id: parentId,
      sort_order: ci,
      volume_index: vi,
      chapter_index: ci,
      status: 'completed',
      title: `章纲剧情设计（第 ${vi + 1} 卷，第 ${ci + 1} 章）`,
      content_text: contentText,
      word_count: wc,
    });
  },

  initSSEListener() {
    if (window.connectGlobalSSE) window.connectGlobalSSE();

    if (window.listenSSE) {
      window.listenSSE('upload_progress', (detail) => {
        handleSSEEvent(detail.eventType, detail.data);
      });

      window.listenSSE('task_progress', (detail) => {
        handleSSEEvent(detail.eventType, detail.data);
      });

      window.listenSSE('feature_model_download_progress', (detail) => {
        handleSSEEvent(detail.eventType, detail.data);
      });

      window.listenSSE('tts_progress', (detail) => {
        handleSSEEvent(detail.eventType, detail.data);
      });
    }
  },

  async generateAudio(sessionId, volumeIndex, chapterIndex, text, speakerId = '', model = '') {
    await _ensureTimeouts();
    const payload = {
      session_id: sessionId,
      volume_index: volumeIndex,
      chapter_index: chapterIndex,
      text: text,
      speaker_id: speakerId,
    };
    if (model) payload.model = model;
    const timeoutMs = _toMs(_getTimeoutSeconds('audio_gen_timeout_seconds', 600));
    const res = await axios.post('/api/audios/tts-generate', payload, {
      timeout: timeoutMs,
    });
    return res.data;
  },

  async getSpeakers(model) {
    const params = {};
    if (model) params.model = model;
    const res = await axios.get('/api/audios/speakers', { params });
    return res.data;
  },

  async getAudioCapabilities() {
    const res = await axios.get('/api/audios/capabilities', { timeout: 10000 });
    return res.data;
  },

  async getTtsAudioByChapter(sessionId, volumeIndex, chapterIndex) {
    const res = await axios.get('/api/audios/tts/by-chapter', {
      params: { session_id: sessionId, volume_index: volumeIndex, chapter_index: chapterIndex },
    });
    return res.data;
  },

  async generateImages(sessionId, volumeIndex, chapterIndex, options = {}) {
    await _ensureTimeouts();
    const params = {
      session_id: sessionId,
      volume_index: volumeIndex,
      chapter_index: chapterIndex,
      user_prompt: options.user_prompt || '',
      image_size: options.image_size || '720*1280',
      negative_prompt: options.negative_prompt || '',
      batch_size: options.batch_size || 2,
      model: options.model || '',
    };
    // wan2.7 特有参数：仅传有效值（布尔显式传 true/false，颜色主题仅非空时传）
    if (typeof options.thinking_mode === 'boolean') {
      params.thinking_mode = options.thinking_mode;
    }
    if (typeof options.enable_sequential === 'boolean') {
      params.enable_sequential = options.enable_sequential;
    }
    if (typeof options.color_palette === 'string' && options.color_palette.trim()) {
      params.color_palette = options.color_palette.trim();
    }
    const timeoutMs = _toMs(_getTimeoutSeconds('image_gen_timeout_seconds', 180));
    const res = await axios.post('/api/images/generate/', null, { params, timeout: timeoutMs });
    return res.data;
  },

  async getImagesByChapter(sessionId, volumeIndex, chapterIndex, imageType) {
    const params = { session_id: sessionId, volume_index: volumeIndex, chapter_index: chapterIndex };
    if (imageType !== undefined && imageType !== null) {
      params.image_type = imageType;
    }
    const res = await axios.get('/api/images/generate/by-chapter', { params });
    return res.data;
  },

  async getImageCapabilities() {
    const res = await axios.get('/api/images/generate/capabilities', { timeout: 10000 });
    return res.data;
  },

  async generateVideo(sessionId, volumeIndex, chapterIndex, config = {}) {
    await _ensureTimeouts();
    const payload = {
      session_id: sessionId,
      volume_index: volumeIndex,
      chapter_index: chapterIndex,
      ...config,
    };
    const timeoutMs = _toMs(_getTimeoutSeconds('video_gen_timeout_seconds', 1800));
    const res = await axios.post('/api/videos/generate', payload, {
      timeout: timeoutMs,
    });
    return res.data;
  },

  async getVideoByChapter(sessionId, volumeIndex, chapterIndex) {
    const res = await axios.get('/api/videos/by-chapter', {
      params: { session_id: sessionId, volume_index: volumeIndex, chapter_index: chapterIndex },
    });
    return res.data;
  },

  /* ============== 公共任务定位函数（三页面复用：chapter/deduction/content） ============== */

  /** 按 volume_index + chapter_index 查找活跃任务（completed 优先于 pending）。
   *  返回 task_id 或 null。单次 listTasks 调用，无需 parent 链反查。
   *  当 chapIdx 为 null 时只按 volume_index 过滤（用于章纲等不区分章号的查询）。 */
  async findActiveTaskId(sessionId, taskType, volIdx, chapIdx) {
    const rows = await this.listTasks(sessionId, taskType, 'id', true);
    if (!Array.isArray(rows) || rows.length === 0) return null;
    const vi = Number(volIdx);
    const ci = chapIdx === null ? null : Number(chapIdx);
    const matched = rows.filter(r => {
      if (!r) return false;
      if (Number(r.volume_index) !== vi) return false;
      return !(ci !== null && Number(r.chapter_index) !== ci);

    });
    if (matched.length === 0) return null;
    const completed = matched.filter(r => {
      const s = String(r.status || '').toLowerCase();
      return s === 'completed' || s === 'success';
    });
    if (completed.length > 0) return completed[0].id;
    const pending = matched.filter(r => String(r.status || '').toLowerCase() === 'pending');
    if (pending.length > 0) return pending[0].id;
    return matched[0].id || null;
  },

  /** 按 volume_index + chapter_index 加载某任务类型的全部任务。
   *  返回 Map: "vi-ci" → task（含 id, status, content_text 等）。
   *  对于 chapIdx 为 null 的任务（如章纲），key 为 "vi-"。 */
  async loadAllChapterTasks(sessionId, taskType) {
    const rows = await this.listTasks(sessionId, taskType, 'id', true);
    const map = new Map();
    if (!Array.isArray(rows) || rows.length === 0) return map;
    for (const r of rows) {
      if (!r) continue;
      const vi = r.volume_index;
      const ci = r.chapter_index;
      const key = `${vi}-${ci === null || ci === undefined ? '' : ci}`;
      if (!map.has(key)) map.set(key, r);
    }
    return map;
  },

  /** 解析 chapter_outline 的 parent_id，供 doSave 时使用。
   *  单次 listTasks(CHAPTER_OUTLINE) + volume_index/chapter_index 过滤。
   *  用 id desc 确保取到最新（id 最大）的章纲任务作为 parent。 */
  async resolveChapterParentId(sessionId, volIdx, chapIdx) {
    const rows = await this.listTasks(sessionId, NovelAPI.CONST.TASK_TYPE_CHAPTER_OUTLINE, 'id', true);
    if (!Array.isArray(rows) || rows.length === 0) return null;
    const vi = Number(volIdx);
    const ci = Number(chapIdx);
    for (const r of rows) {
      if (!r) continue;
      if (Number(r.volume_index) === vi && Number(r.chapter_index) === ci) {
        return r.id || null;
      }
    }
    return null;
  },
};

function handleSSEEvent(eventType, data) {
  try {
    const { message, title } = window.formatSSEMessage(eventType, data);
    if (window.addLog) window.addLog(message, 'info');
    if (title && window.TaskNotifications) {
      let displayText = data.content || data.title || '任务进度';
      if (data.meta) {
        if (data.meta.progress !== undefined) displayText += ` [${data.meta.progress}%]`;
        if (data.meta.success !== undefined) displayText += data.meta.success ? ' ✅' : ' ❌';
      }
      window.TaskNotifications.add(title || '任务进度', displayText);
    }
  } catch (e) {
    if (window.addLog) window.addLog(`解析事件数据失败: ${JSON.stringify(data)}`, 'error');
  }
}

window.NovelAPI = NovelAPI;
window.handleSSEEvent = handleSSEEvent;
