"""
💎 全局值常量 (Pure Values)
单一事实来源 (Single Source of Truth)。
所有业务逻辑无需任何依赖使用的具体字符串、数字、集合均在此定义。
所有常量均以 VAL_ 开头。
"""
import signal
from typing import Final, Set, Tuple, List
from app.common import keys as ke
from app.core.validators.data_validator import IS_STR, IS_INT, IS_LIST, IS_BOOL, IS_FLOAT, IS_DICT

"""
# ======================================================================
# 0. 系统核心配置 (System Core Configuration)
# ======================================================================
"""
# [LangSmith 配置]
VAL_LANGSMITH_PROJECT = "prose_refiner"
VAL_LANGSMITH_ENDPOINT = "https://api.smith.langchain.com"
# 环境变量
VAL_LANGCHAIN_TRACING_V2 = "LANGCHAIN_TRACING_V2"
VAL_LANGCHAIN_API_KEY = "LANGCHAIN_API_KEY"
VAL_LANGCHAIN_PROJECT = "LANGCHAIN_PROJECT"
VAL_LANGCHAIN_ENDPOINT = "LANGCHAIN_ENDPOINT"

# 定时任务扫描包
VAL_TASKS_PACKAGE = "app.tasks"
VAL_SIGNAL_CONFIG_DICT = {signal.SIGINT: "SIGINT", signal.SIGTERM: "SIGTERM"}

"""
# ======================================================================
# 1. 通用基础配置 (Generic Structure & Enums)
# ======================================================================
"""
VAL_STOP_FLAG = [
    "```",  # 你的原版：防止生成代码块（适合纯文本回复场景）
    "\n```",  # 你的原版：防止换行后的代码块
    "<|eot_id|>",  # Llama 3 / DeepSeek 常用结束符
    "<|end_of_text|>",  # 通用结束符
    "<|im_end|>",  # ChatML 格式结束符
    "<｜end▁of▁sentence｜>",  # Qwen (通义千问) 常用结束符
    "\n\nUser:",  # 防止模型自问自答
    "\n\nHuman:",  # 防止模型自问自答
]
# 判断 true 标识字典
VAL_SUCCESS_FLAG = ("true", "1", "yes", "on", "ok", "success")
# [用于校验日志配置是否为整型数值]
VAL_LOG_CONFIG_FIELD: Final = ["LOG_KEEP_DAYS", "LOG_MAX_BYTES", "LOG_BACKUP_COUNT"]
# 合法存储端类型
VAL_VALIEDSTORAGE_TYPE: Final = {ke.KEY_LOCAL, ke.KEY_REDIS}

# 日志兜底配置
VAL_LOG_KEEP_DAYS: Final = 7
VAL_LOG_MAX_BYTES: Final = 10 * 1024 * 1024
VAL_LOG_BACKUP_COUNT: Final = 10

# 最大批量文件字节数
VAL_MAX_BATCH_FILE_SIZE_BYTES: Final = 2 * 1024 * 1024  # 2 MB

# LLM 兜底配置
VAL_RECOMMENDED_PARAMS = {
    ke.KEY_TEMPERATURE: 0.6,
    ke.KEY_TOP_P: 0.85,
    ke.KEY_MAX_TOKENS: 1536,
    ke.KEY_RESPONSE_FORMAT: {
        ke.KEY_TYPE: ke.KEY_JSON_OBJECT
    }
}

# 重试 兜底配置
VAL_DEFAULT_RETRY_CONFIG = {
    ke.KEY_MAX_RETRIES: 3,
    ke.KEY_ENABLE_EXP_BACKOFF: True,
    ke.KEY_EXP_MULTIPLIER: 1.0,
    ke.KEY_EXP_MAX_WAIT: 10.0,
    ke.KEY_MIN_WAIT: 0.1,
    ke.KEY_RERAISE: True
}

# [存储策略]
VAL_REDIS_NAMESPACE: Final = "prose_refiner"

# 报告默认标题
VAL_TEXT_REPORT_PREFIX = "心海·文本分析报告"
VAL_REPORT_SUFFIX = ".html"
VAL_DYE_VAT_FILE_BACKUP_SUFFIX = ".json.bad"
# 报告水印相关配置
VAL_WATERMARK_CONTENT = "内部审计·严禁外传"
VAL_WATERMARK_COLOR = "rgba(54, 52, 52, 0.9)"

# 启用的通知通道
VAL_NOTIFICATION_CHANNELS = [ke.KEY_FEISHU, ke.KEY_EMAIL, ke.KEY_WECOM]
VAL_EMAIL_SMTP_SERVER = "smtp.QQ.com"
VAL_EMAIL_PORT = 465
VAL_EMAIL_USERNAME = "发件邮箱账号"
VAL_EMAIL_PASSWORD = "邮箱授权码（非登录密码），敏感信息，请勿泄露"
VAL_FEISHU_WEBHOOK_URL = "飞书 Webhook 地址，敏感信息"
VAL_WECOM_WEBHOOK_URL = "企业微信 Webhook 地址，敏感信息"

# [外部 API 密钥与配置]
VAL_UNSPLASH_BASIC_URL = "https://api.unsplash.com"
VAL_UNSPLASH_SEARCH_PHOTOS_API_SUFFIX = "/search/photos"
VAL_UNSPLASH_SEARCH_COLLECTIONS_API_SUFFIX = "/search/collections"
VAL_UNSPLASH_ALLOWED_ORDER_BY: Set[str] = {'relevant', 'latest'}
VAL_UNSPLASH_ALLOWED_ORIENTATION: Set[str] = {'landscape', 'portrait', 'squarish'}
VAL_UNSPLASH_ALLOWED_CONTENT_FILTER: Set[str] = {'low', 'high'}
VAL_UNSPLASH_ALLOWED_COLORS: Set[str] = {
    "black_and_white", "black", "white", "red", "orange", "yellow",
    "green", "teal", "blue", "purple", "magenta"
}

VAL_PEXELS_BASIC_URL = "https://api.pexels.com"
VAL_PEXELS_SEARCH_PHOTOS_API_SUFFIX = "/v1/search"
VAL_PEXELS_SEARCH_VIDEOS_API_SUFFIX = "/videos/search"
VAL_PEXELS_ALLOWED_SIZES: Set[str] = {'large', 'medium', 'small'}
VAL_PEXELS_ALLOWED_ORIENTATIONS: Set[str] = {'landscape', 'portrait', 'square'}
VAL_PEXELS_ALLOWED_LOCALES: Set[str] = {
    "zh-CN", "en-US", "pt-BR", "es-ES", "ca-ES", "de-DE", "it-IT", "fr-FR", "sv-SE",
    "id-ID", "pl-PL", "ja-JP", "zh-TW", "ko-KR", "th-TH", "nl-NL", "hu-HU", "vi-VN",
    "cs-CZ", "da-DK", "fi-FI", "uk-UA", "el-GR", "ro-RO", "nb-NO", "sk-SK", "tr-TR", "ru-RU"
}
VAL_PEXELS_ALLOWED_COLORS: Set[str] = {
    'black', 'soft-red', 'white', 'soft-orange', 'soft-yellow',
    'soft-green', 'turquoise', 'sky-blue', 'violet', 'soft-pink'
}

# Ollama
VAL_OLLAMA_BASE_URL = "http://localhost:11434"
VAL_OLLAMA_MODEL = "qwen2.5:3b-instruct-q4_K_M"
VAL_OLLAMA_PARAMS = {
    ke.KEY_TEMPERATURE: 0.01,
    ke.KEY_NUM_PREDICT: 512,
    ke.KEY_TOP_P: 0.5
}

# [插件校验]
VAL_PLUGIN_SCHEMA = {
    ke.KEY_ID: (str, True),
    ke.KEY_NAME: (str, True),
    ke.KEY_TYPE: (str, True),
    ke.KEY_ENABLED: (bool, True),
    ke.KEY_PARAMS: (dict, True),
    ke.KEY_META_CONSTITUTION_INJECTED: (bool, True),
    ke.KEY_STEP_RULES: (list, True),
    ke.KEY_VERSION: (str, True),

    ke.KEY_DESCRIPTION: (str, False),
    ke.KEY_ROLE: (str, False),
    ke.KEY_INFORMATION_SOURCE: (str, False),
    ke.KEY_OUTPUT_PREFIX: (list, False),
    ke.KEY_FIELDS: (dict, False),
    ke.KEY_EMPTY_RESULT_FALLBACK: (str, False),
    ke.KEY_OUTPUT_SUFFIX: (list, False),
    ke.KEY_TAGS: (list, False)
}
VAL_LLM_PARAMS_SCHEMA = {
    ke.KEY_TEMPERATURE: (float, True),
    ke.KEY_TOP_P: (float, True),
    ke.KEY_MAX_TOKENS: (int, True),
    ke.KEY_RESPONSE_FORMAT: (str, True)
}

VAL_HEADER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"

# [包装键优先级 (Wrapper Keys Priority)]
# 🔴 第一梯队：纯容器键 (优先级最高)
VAL_HIGH_PRIORITY_KEYS = (
    'value', 'data', 'result', 'content', 'body', 'payload',
    'item', 'output', 'response', 'info'
)
# 🟡 第二梯队：类型/数值标记键 (优先级中)
VAL_MEDIUM_PRIORITY_KEYS = (
    'type', 'val', 'number', 'score', 'code', 'id',
    'key', 'label', 'text', 'message', 'status'
)
# 🟢 第三梯队：语义业务键 (优先级低)
VAL_LOW_PRIORITY_KEYS = (
    'reason', 'action', 'option', 'strategy', 'decision',
    'mode', 'command', 'instruction', 'name'
)
# 合并总表
VAL_COMMON_WRAPPER_KEYS: Tuple[str, ...] = VAL_HIGH_PRIORITY_KEYS + VAL_MEDIUM_PRIORITY_KEYS + VAL_LOW_PRIORITY_KEYS

# [情绪标签（只增不减）]
VAL_EMOTION_CATEGORIES: List[str] = [
    "neutral", "joy", "sadness", "anger", "fear", "surprise", "disgust",
    "shame", "guilt", "pride", "envy", "gratitude", "hope", "despair",
    "anxiety", "frustration", "confusion", "overwhelm", "loneliness",
    "regret", "resentment", "bitterness", "melancholy", "apprehension",
    "dread", "relief", "contentment", "nostalgia", "ambivalence", "inexpressible",
    "tension", "unease", "restlessness", "emptiness", "numbness", "complex"
]

"""
# ======================================================================
# 2. 路径、状态与节点定义 (Paths, Status & Node IDs)
# ======================================================================
"""
# ==============================================================================
# 节点 ID
# ==============================================================================
VAL_NODE_DIVINE_EYE = "divine_eye"  # 上帝之眼：全局预分析与路由决策
VAL_NODE_LOAD_DATA = "load_data"  # 数据加载：按需加载更高层级诊断数据
VAL_NODE_DEBATE_SUBGRAPH = "debate_subgraph"  # 辩论子图：理性暴君与感性圣母多轮交替分析
VAL_NODE_RATIONAL_SINGLE = "rational_single"  # 理性暴君单节点：仅逻辑一致性分析
VAL_NODE_EMOTIONAL_SINGLE = "emotional_single"  # 感性圣母单节点：仅情感表达力分析
VAL_NODE_DIVINE_HAND = "divine_hand"  # 上帝之手：聚合分析，产出问题清单
VAL_NODE_REVISE_AND_DIAGNOSE = "revise_and_diagnose"  # 修复与验证：执行修复并诊断修复后文本
VAL_NODE_GENERATE_SIGNATURE = "generate_metacognition_signature"  # 语义签名：生成元认知语义指纹
VAL_NODE_PERSIST_RESULT = "persist_metacognition_result"  # 持久化：存储全链路数据并生成报告
VAL_NODE_WAIT_HUMAN = "wait_human"  # 人工介入：挂起并推送 SSE 等待用户补充信息
VAL_NODE_DAO = "dao_node"  # 道之洞见：价值过滤与直觉生成（非图谱节点，仅供其他智能节点调用）

# ==============================================================================
# 状态码
# ==============================================================================
VAL_STATUS_RUNNING = "running"  # 运行中

# -- 流程流转状态 --
VAL_STATUS_GOTO_LOAD_DATA = "goto_load_data"  # 数据不足，需加载更高层级数据
VAL_STATUS_GOTO_DIVINE_EYE = "goto_divine_eye"  # 返回上帝之眼（数据加载后重新审视）
VAL_STATUS_GOTO_DIVINE_HAND = "goto_divine_hand"  # 进入上帝之手裁决
VAL_STATUS_GOTO_DEBATE_SUBGRAPH = "goto_debate_subgraph"  # 进入辩论子图（多角色交替分析）
VAL_STATUS_GOTO_RATIONAL_SINGLE = "goto_rational_single"  # 进入理性暴君单节点分析
VAL_STATUS_GOTO_EMOTIONAL_SINGLE = "goto_emotional_single"  # 进入感性圣母单节点分析

# -- 终止状态 --
VAL_STATUS_COMPLETED = "completed"  # 优化完成（正常结束）
VAL_STATUS_COMPLETED_TRIVIAL = "completed_trivial"  # 无优化空间（文本已高度自洽）
VAL_STATUS_COMPLETED_BY_BUDGET = "completed_by_budget"  # 资源耗尽终止（LLM 调用或循环次数超限）
VAL_STATUS_FAILED = "failed"  # 异常失败
VAL_STATUS_SUSPENDED = "suspended"  # 挂起等待人工输入

# ==============================================================================
# 战略代码 - 上帝之眼路由决策
# ==============================================================================
VAL_STRATEGY_TERMINATE_TRIVIAL = "terminate_trivial"  # 文本已高度自洽，无需优化，直接结束
VAL_STRATEGY_UPGRADE_DATA = "upgrade_data"  # 信息不足，加载更高数据层级后重新审视
VAL_STRATEGY_HAND_DIRECT = "hand_direct"  # 信息充足，直接交付上帝之手裁决
VAL_STRATEGY_DEBATE = "debate"  # 需多视角深度分析，进入辩论子图
VAL_STRATEGY_RATIONAL_ONLY = "rational_only"  # 仅需逻辑一致性分析，进入理性暴君单节点
VAL_STRATEGY_EMOTIONAL_ONLY = "emotional_only"  # 仅需情感表达力分析，进入感性圣母单节点
VAL_STRATEGY_REQUEST_HUMAN_IN_LOOP = "request_human_in_loop"  # 系统无法决策，挂起等待人工介入

# ==============================================================================
# 决策类型 - 上帝之手裁决输出
# ==============================================================================
VAL_DECISION_ACCEPT_CURRENT = "accept_current"  # 接受当前文本，无需修复
VAL_DECISION_FIX_REQUIRED = "fix_required"  # 存在问题，需进入修复与验证节点
VAL_DECISION_REQUEST_USER_CLARIFICATION = "request_user_clarification"  # 信息不足，挂起等待用户澄清
VAL_DECISION_TERMINATE_BY_CONSENSUS = "terminate_by_consensus"  # 分析达成一致，正常终止
VAL_DECISION_TERMINATE_BY_RESOURCE_EXHAUSTION = "terminate_by_resource_exhaustion"  # 资源耗尽终止
VAL_DECISION_TERMINATE_BY_ERROR = "terminate_by_error"  # 异常终止
VAL_DECISION_BACK_TO_EYE = "back_to_eye"  # 回退至上帝之眼重新审视
VAL_DECISION_CONTINUE_DEBATE = "continue_debate"  # 继续辩论子图
VAL_DECISION_DEEP_ANALYSIS_RATIONAL = "deep_analysis_rational"  # 深度理性分析
VAL_DECISION_DEEP_ANALYSIS_EMOTIONAL = "deep_analysis_emotional"  # 深度感性分析

# ==============================================================================
# 聚焦领域 - 辩论角色可调用的分析维度
# ==============================================================================
VAL_FOCUS_PLOT_COHERENCE = "plot_coherence"  # 情节连贯性
VAL_FOCUS_CHARACTER_CONSISTENCY = "character_consistency"  # 人物一致性
VAL_FOCUS_EMOTIONAL_AUTHENTICITY = "emotional_authenticity"  # 情感真实性
VAL_FOCUS_PROSE_RHYTHM = "prose_rhythm"  # 文笔节奏
VAL_FOCUS_WORLD_RULE_VIOLATION = "world_rule_violation"  # 世界观规则违反
VAL_FOCUS_DIALOGUE_NATURALNESS = "dialogue_naturalness"  # 对话自然度
VAL_FOCUS_BALANCE = "balance"  # 多维度均衡
VAL_FOCUS_NONE = "none"  # 无特定聚焦

# [聚焦领域标签字典]
VAL_FOCUS_AREA_DEFINITIONS = {
    VAL_FOCUS_PLOT_COHERENCE: "检视事件因果链是否完整、无断裂",
    VAL_FOCUS_CHARACTER_CONSISTENCY: "核验角色性格、动机、行为是否前后统一",
    VAL_FOCUS_EMOTIONAL_AUTHENTICITY: "洞察情感表达是否真挚、不矫饰、有冲击力",
    VAL_FOCUS_PROSE_RHYTHM: "审视语句长短、段落呼吸感与阅读流畅度",
    VAL_FOCUS_WORLD_RULE_VIOLATION: "检查是否违反已设定的故事世界法则",
    VAL_FOCUS_DIALOGUE_NATURALNESS: "评估人物对话是否符合身份与情境",
    VAL_FOCUS_BALANCE: "多维度综合权衡，寻求全局最优",
    VAL_FOCUS_NONE: "无特定聚焦，用于终止或通用处理",
}

# ==============================================================================
# 角色常量
# ==============================================================================
VAL_EYE_OF_GOD = "上帝之眼"  # 全局预分析与路由决策
VAL_HAND_OF_GOD = "上帝之手"  # 聚合分析，产出问题清单
VAL_RATIONAL_TYRANT = "理性暴君"  # 逻辑一致性分析视角
VAL_EMOTIONAL_VIRGIN_MARY = "感性圣母"  # 情感表达力分析视角
VAL_REVISE_DIAGNOSTICIAN = "修复匠人"  # 执行文本修复并诊断修复后文本
VAL_SEMANTIC_SIGNER = "生成语义签名"  # 生成元认知语义指纹
VAL_DATA_LOADER = "数据加载器"  # 按需加载更高层级诊断数据
VAL_HUMAN_USER = "用户介入"  # 挂起等待用户补充信息
VAL_PERSISTENCE_AGENT = "持久化存储"  # 存储全链路数据并生成报告
VAL_START_NODE = "流程启动"
VAL_END_NODE = "流程终结"
VAL_DAO = "道之洞见"  # 价值过滤与直觉生成，所有智能节点的底层分析语境

"""
# ======================================================================
# 3. 任务与运行时参数 (Tasks & Runtime Parameters)
# ======================================================================
"""
VAL_API_KEY_DESC = "请输入密钥"

# 句子结束标点
VAL_SENTENCE_END_PUNCT = '。！？…’”’'

VAL_WEEKDAY = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

VAL_TYPE_VALIDATOR_TO_STR_MAP = {
    IS_STR: ke.KEY_STR,
    IS_INT: ke.KEY_INT,
    IS_LIST: ke.KEY_LIST,
    IS_BOOL: ke.KEY_BOOL,
    IS_FLOAT: ke.KEY_FLOAT,
    IS_DICT: ke.KEY_DICT
}

# [序列化时需要排除的特定字段]
VAL_REMOVE_KEYS = {
    ke.KEY_CALLBACK
}

# 串行打磨的优先级排序
VAL_PRIORITY_ORDER = {ke.KEY_P0: 0, ke.KEY_P1: 1, ke.KEY_P2: 2}

# [终止状态]
VAL_TERMINATION_STATE = {
    VAL_STATUS_COMPLETED_TRIVIAL,
    VAL_STATUS_COMPLETED,
    VAL_STATUS_COMPLETED_BY_BUDGET,
    VAL_STATUS_FAILED
}

# 调用方角色 -> 其报告在 state 中的存储 key
VAL_CALLER_REPORT_KEY_MAP = {
    VAL_EYE_OF_GOD: ke.KEY_EYE_REPORTS,
    VAL_HAND_OF_GOD: ke.KEY_HAND_REPORTS,
    VAL_DAO: ke.KEY_DAO_REPORTS,
    VAL_RATIONAL_TYRANT: ke.KEY_ANALYSIS_REPORTS,
    VAL_EMOTIONAL_VIRGIN_MARY: ke.KEY_ANALYSIS_REPORTS,
}

# 合法子表名白名单
VAL_VALID_SUB_TABLES = {ke.KEY_TEXT_PROCESSING_DATA, ke.KEY_METACOGNITION_DATA}

# 合法路径键名白名单
VAL_VALID_PATH_KEYS = {ke.KEY_PATH_TEXT, ke.KEY_PATH_DYE_VAT, ke.KEY_PATH_METACOGNITION, ke.KEY_PATH_REPORT}

# 触发配置热重载的字典
VAL_LLM_SENSITIVE_KEYS = {
    # LLM 核心
    "LLM_DEFAULT_VENDOR",
    "LLM_DEFAULT_MODEL",
    "LLM_DEEPSEEK_API_KEY",
    "LLM_API_TIMEOUT",
    "LLM_PARAMS",
    "LLM_RECOMMENDED_PARAMS",

    # LangSmith
    "LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT",
    "LANGSMITH_ENDPOINT",

    # 元认知总控
    "METACOGNITION_ENABLED",
    "METACOGNITION_MAX_LLM_CALLS",
    "METACOGNITION_MAX_ITERATIONS",
    "METACOGNITION_EXPIRES_AT",
    "METACOGNITION_MAX_CHARS_PER_TURN",

    # 辩论子图
    "DEBATE_DEFAULT_MAX_ROUNDS",
    "DEBATE_CONSENSUS_THRESHOLD",
}

# 角色名 -> 兜底流转目标
VAL_DEFAULT_NEXT_DEST_MAP = {
    VAL_EYE_OF_GOD: VAL_STATUS_GOTO_DIVINE_HAND,
    VAL_HAND_OF_GOD: VAL_STATUS_GOTO_DIVINE_EYE,
}

"""
# ======================================================================
# 4. 提示词配置值 (Prompt Config Values)
# ======================================================================
"""
# 步骤 prompt id
VAL_RULE_SCENE_ADAPTATION = "rule/scene_adaptation"
VAL_RULE_PREPROCESS_CHINESE_TEXT = "rule/preprocess_chinese_text"
VAL_RULE_CONTEXTUAL_TYPO_FIX = "rule/contextual_typo_fix"
VAL_RULE_SYNTAX_SEMANTIC_POLISH = "rule/syntax_semantic_polish"
VAL_RULE_EXPRESSIVENESS_DIAGNOSIS = "rule/expressiveness_diagnosis"
VAL_RULE_EVENT_LOGIC_DIAGNOSIS = "rule/event_logic_diagnosis"
VAL_RULE_CHARACTER_CONSISTENCY_DIAGNOSIS = "rule/character_consistency_diagnosis"
VAL_RULE_DIALOGUE_TONE_DIAGNOSIS = "rule/dialogue_tone_diagnosis"
VAL_RULE_WORLDVIEW_CONSISTENCY_DIAGNOSIS = "rule/worldview_consistency_diagnosis"
VAL_RULE_STYLE_ALIGNMENT_DIAGNOSIS = "rule/style_alignment_diagnosis"
VAL_RULE_AGGREGATE_DIAGNOSIS = "rule/aggregate_diagnosis"
VAL_RULE_RHETORIC_SYNTAX_POLISH = "rule/rhetoric_syntax_polish"
VAL_RULE_STRUCTURE_TRANSITION_POLISH = "rule/structure_transition_polish"
VAL_RULE_CONSISTENCY_FIX = "rule/consistency_fix"
VAL_RULE_CREATIVE_ENHANCE = "rule/creative_enhance"
VAL_RULE_CANDIDATE_GENERATION = "rule/candidate_generation"
VAL_RULE_INTELLIGENT_SELECTION = "rule/intelligent_selection"
VAL_RULE_FIDELITY_REPAIR = "rule/fidelity_repair"

# 插件步骤id
VAL_INTERNAL_DAO_INSIGHT = "internal/dao_insight"
VAL_INTERNAL_DIVINE_EYE_INTUITION = "internal/divine_eye_intuition"
VAL_INTERNAL_DIVINE_HAND_VERDICT = "internal/divine_hand_verdict"
VAL_INTERNAL_RATIONAL_TYRANT_ANALYSIS = "internal/rational_tyrant_analysis"
VAL_INTERNAL_EMOTIONAL_VIRGIN_MARY_ANALYSIS = "internal/emotional_virgin_mary_analysis"
VAL_INTERNAL_METACOGNITION_SIGNATURE = "internal/metacognition_signature"
