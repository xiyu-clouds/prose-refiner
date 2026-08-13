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
VAL_LANGSMITH_PROJECT = ke.KEY_PROSE_REFINER
VAL_LANGSMITH_ENDPOINT = "https://api.smith.langchain.com"
# 环境变量
VAL_LANGCHAIN_TRACING_V2 = "LANGCHAIN_TRACING_V2"
VAL_LANGCHAIN_API_KEY = "LANGCHAIN_API_KEY"
VAL_LANGCHAIN_PROJECT = "LANGCHAIN_PROJECT"
VAL_LANGCHAIN_ENDPOINT = "LANGCHAIN_ENDPOINT"

# 定时任务扫描包
VAL_TASKS_PACKAGE = "app.core.tasks"
VAL_SIGNAL_CONFIG_DICT = {signal.SIGINT: "SIGINT", signal.SIGTERM: "SIGTERM"}

# 本地模型支持的模态和加载器
VAL_SUPPORTED_MODALITIES = ["text", "image", "audio", "video"]
VAL_SUPPORTED_LOADER_TYPES = ["huggingface_pipeline"]
VAL_SUPPORTED_TASK_TYPES = ["feature-extraction"]

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
VAL_REDIS_NAMESPACE: Final = ke.KEY_PROSE_REFINER

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
VAL_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
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
# 2. 织网字段字符限制 (Weave Semantic Vocabulary Limits)
# 单一真源（SSOT）：前端模态框 maxlength、后端保存兜底裁剪均以此为准。
# 注入层阈值已从 global.json 移至此处（VAL_INJECT_*），CRUD 上限与注入上限统一对齐。
# ======================================================================
"""
# ===== 注入层阈值（Prompt注入裁剪用）=====
VAL_INJECT_CHARACTER_COUNT: Final = 2
VAL_INJECT_CHARACTER_CHARS: Final = 2000
VAL_INJECT_TIMELINE_COUNT: Final = 1
VAL_INJECT_TIMELINE_CHARS: Final = 1000
VAL_INJECT_LOCATION_COUNT: Final = 1
VAL_INJECT_LOCATION_CHARS: Final = 2000
VAL_INJECT_SESSION_MEMORY_COUNT: Final = 5
VAL_INJECT_SESSION_MEMORY_CHARS: Final = 200
VAL_INJECT_NLP_SUMMARY_CHARS: Final = 1000
VAL_INJECT_MATCH_KEYWORDS_TOP_K: Final = 20

# ===== 共用字段限制 =====
VAL_WEAVE_ATTR_KEY_MAX: Final = 15
VAL_WEAVE_ATTR_VALUE_MAX: Final = 80
VAL_WEAVE_NAME_MAX: Final = 15
VAL_WEAVE_TYPE_MAX: Final = 15
VAL_WEAVE_ALIASES_MAX: Final = 120
VAL_WEAVE_REL_TYPE_MAX: Final = 15
VAL_WEAVE_IDENTITY_MAX: Final = 120

# ===== 共用：自定义属性数量上限（设为999，实际上无限制，通过前端软提示引导） =====
VAL_WEAVE_ATTRS_MAX_COUNT_CHARACTER: Final = 999
VAL_WEAVE_ATTRS_MAX_COUNT_TEMPORAL: Final = 999
VAL_WEAVE_ATTRS_MAX_COUNT_LOCATION: Final = 999
# 角色关联关系条数上限
VAL_WEAVE_RELS_MAX_COUNT_CHARACTER: Final = 99

# ===== 织网实体总字段上限（与注入层对齐，后端总上限截断用）=====
VAL_WEAVE_CHAR_TOTAL_MAX: Final = VAL_INJECT_CHARACTER_CHARS  # 2000
VAL_WEAVE_TIME_TOTAL_MAX: Final = VAL_INJECT_TIMELINE_CHARS    # 1000
VAL_WEAVE_LOC_TOTAL_MAX: Final = VAL_INJECT_LOCATION_CHARS    # 2000

# ===== 织网实体字段级上限（前端 maxlength 属性限制用）=====
VAL_WEAVE_CHAR_SECRET_MAX: Final = 1000
VAL_WEAVE_TIME_DESC_MAX: Final = 500
VAL_WEAVE_LOC_DESC_MAX: Final = 1000

# ======================================================================
# 2.1 谋篇（Global Outline）字段字符限制（单一真源 SSOT）
#    单一真源（SSOT）：前端 textarea 计数器、后端保存兜底、Prompt 裁剪统一从此取。
#    建议/最大双层策略：
#      - plot：建议 1500 字符，最大 2000 字符
#      - summary：建议 200 字符，最大 300 字符
#    - 旧常量 VAL_OUTLINE_GLOBAL_PLOT_MAX_CHARS / VAL_OUTLINE_GLOBAL_SUMMARY_MAX_CHARS
#      直接指向 SUGGEST，保持 meta 旧 key 兼容不破坏既有逻辑。
# ======================================================================
VAL_OUTLINE_GLOBAL_PLOT_SUGGEST_CHARS: Final = 1500
VAL_OUTLINE_GLOBAL_PLOT_HARD_CHARS: Final = 2000
VAL_OUTLINE_GLOBAL_SUMMARY_SUGGEST_CHARS: Final = 200
VAL_OUTLINE_GLOBAL_SUMMARY_HARD_CHARS: Final = 300

VAL_OUTLINE_GLOBAL_PLOT_MAX_CHARS: Final = VAL_OUTLINE_GLOBAL_PLOT_SUGGEST_CHARS
VAL_OUTLINE_GLOBAL_SUMMARY_MAX_CHARS: Final = VAL_OUTLINE_GLOBAL_SUMMARY_SUGGEST_CHARS

# ======================================================================
# 2.2 卷纲（Volume Outline）字段字符限制（单一真源 SSOT）
#    建议/最大双层策略：
#      - plot：建议 1500 字符，最大 2000 字符
#      - summary：建议 200 字符，最大 300 字符
# ======================================================================
VAL_OUTLINE_VOLUME_PLOT_SUGGEST_CHARS: Final = 1500
VAL_OUTLINE_VOLUME_PLOT_HARD_CHARS: Final = 2000
VAL_OUTLINE_VOLUME_SUMMARY_SUGGEST_CHARS: Final = 200
VAL_OUTLINE_VOLUME_SUMMARY_HARD_CHARS: Final = 300

# ======================================================================
# 2.3 章纲（Chapter Outline）字段字符限制（单一真源 SSOT）
#    建议/最大双层策略：
#      - plot：建议 1500 字符，最大 2000 字符
#      - summary：建议 200 字符，最大 300 字符
# ======================================================================
VAL_OUTLINE_CHAPTER_PLOT_SUGGEST_CHARS: Final = 1500
VAL_OUTLINE_CHAPTER_PLOT_HARD_CHARS: Final = 2000
VAL_OUTLINE_CHAPTER_SUMMARY_SUGGEST_CHARS: Final = 200
VAL_OUTLINE_CHAPTER_SUMMARY_HARD_CHARS: Final = 300

# ======================================================================
# 2.4 推演（Deduction Event）字段字符限制（单一真源 SSOT）
#    与 capabilities.json chapter_events_design 规则对齐：
#      - 每条事件建议 200 字，硬截断 300 字
# ======================================================================
VAL_DEDUCTION_EVENT_SUGGEST_CHARS: Final = 200
VAL_DEDUCTION_EVENT_HARD_CHARS: Final = 300

# ======================================================================
# 2.5 图像提示词（Image Prompt）字符限制（单一真源 SSOT）
#    前端画面提示词文本框 maxlength、后端 image_generation 路由长度校验、
#    meta/frontend-thresholds 接口返回值三者统一从此取，禁止任何层散写字面量。
# ======================================================================
VAL_IMAGE_PROMPT_MAX_CHARS: Final = 800


"""
# ======================================================================
# 3. 任务类型常量 (Task Type Constants)
#    单一真源（SSOT）：与 capabilities.json 中各能力的 capability_id 对齐。
#    task_type 字段存储能力配置ID字符串，用于语义唯一键 (session_id, parent_id, task_type, sort_order)。
#    层级语义：parent_id 指向父任务实现层级关系，sort_order 为同级排序。
#    注：core_plot 为用户原始输入，非能力配置，使用保留字符串 "core_plot"。
# ======================================================================
"""
VAL_TASK_TYPE_CORE_PLOT: Final[str] = "core_plot"
VAL_TASK_TYPE_EXTRACTION: Final[str] = "extract_session_memory"
VAL_TASK_TYPE_GLOBAL_OUTLINE: Final[str] = "global_plot_design"
VAL_TASK_TYPE_VOLUME_OUTLINE: Final[str] = "volume_plot_design"
VAL_TASK_TYPE_CHAPTER_OUTLINE: Final[str] = "chapter_plot_design"
VAL_TASK_TYPE_CHAPTER_EVENTS: Final[str] = "chapter_events_design"
VAL_TASK_TYPE_CHAPTER_CONTENT: Final[str] = "chapter_content_generation"
# 图像提示词优化：与 capabilities.json capability_id 完全对齐（SSOT）
VAL_TASK_TYPE_IMAGE_PROMPT_REFINE: Final[str] = "image_prompt_refine"

VAL_TASK_TYPE_ALL: Final = (
    VAL_TASK_TYPE_CORE_PLOT,
    VAL_TASK_TYPE_EXTRACTION,
    VAL_TASK_TYPE_GLOBAL_OUTLINE,
    VAL_TASK_TYPE_VOLUME_OUTLINE,
    VAL_TASK_TYPE_CHAPTER_OUTLINE,
    VAL_TASK_TYPE_CHAPTER_EVENTS,
    VAL_TASK_TYPE_CHAPTER_CONTENT,
    VAL_TASK_TYPE_IMAGE_PROMPT_REFINE,
)
"""
# ======================================================================
# 4. 任务与运行时参数 (Tasks & Runtime Parameters)
# ======================================================================
"""
VAL_API_KEY_DESC = "请输入密钥"

# 句子结束标点
VAL_SENTENCE_END_PUNCT = '。！？…’”’'

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


"""
# ======================================================================
# 5. Prompt 注入字段中文化映射（单一真源 SSOT）
#    适用范围：所有能力调用（global_plot_design / volume / chapter / events 等）
#      在将织网三剑客（角色/时间/地点）与标签、关系等结构化数据注入
#      LLM Prompt 前，统一将数据字典里的英文字段名映射成可被模型准确
#      理解的中文标签，避免中英混用或无标签造成的歧义。
#    规则：
#      1) 键：原始数据中的字段名（英文/中文/缩写）；值：注入 Prompt 时展示的中文标签
#      2) 中文键保持原值，无需重复映射（命中字典就用值，未命中保持原 key）
#      3) name/aliases 是行首主信息，不添加 「姓名:」「昵称:」前缀（直接拼接空格）
#      4) 空值 / None / 空字符串 一律跳过，避免出现「身份:」「隐秘:」这种空标签
#      5) relationships / attributes 等嵌套结构，递归应用同样的映射规则
# ======================================================================
"""

# --------------------------- 5.1 字段拼接优先级（裁剪/匹配/展示共用） ---------------------------
# 角色（category=entity）字段输出顺序（严格对齐前端新增角色默认字段与拓展字段）
VAL_PROMPT_CHAR_FIELD_PRIORITY: Tuple[str, ...] = (
    "name", "aliases",
    "gender", "identity", "type", "secret",
    "age", "profession", "birthplace", "family",
    "修为本质", "relationships", "attributes",
)

# 时间（category=temporal）字段输出顺序
VAL_PROMPT_TIME_FIELD_PRIORITY: Tuple[str, ...] = (
    "name", "aliases",
    "type", "description",
    "start", "end", "duration",
    "attributes",
)

# 地点（category=location）字段输出顺序
VAL_PROMPT_LOC_FIELD_PRIORITY: Tuple[str, ...] = (
    "name", "aliases",
    "parent_id", "type", "description",
    "coord", "size", "population",
    "attributes",
)

# --------------------------- 5.2 通用英→中映射（只放后端「确定固定字段」，避免几百个同义词冗余） ---------------------------
# 注意：只列前端/持久化层实际确定在用的英文键；同义词砍掉（比如 gender 就写一个 gender，不写 sex/ages 这种）
VAL_PROMPT_GENERIC_FIELD_ZH: dict = {
    # ===== 角色固定字段 =====
    "name": "姓名",
    "aliases": "别名",
    "gender": "性别",
    "identity": "身份",
    "type": "类型",
    "secret": "隐秘",
    "age": "年龄",
    "profession": "职业",
    "birthplace": "出生地",
    "family": "家庭背景",
    "description": "描述",

    # ===== 时间固定字段 =====
    "sort_index": "排序",
    "start": "起始",
    "end": "截止",
    "duration": "时长",

    # ===== 地点固定字段 =====
    "parent_id": "上级地点",
    "coord": "坐标",
    "size": "规模",
    "population": "人口",
    "location_type": "地点类型",

    # ===== 关系（relationships[x] 内部固定字段） =====
    "targetId": "目标",
    "target_id": "目标",
    "target": "目标",
    "rel_type": "关系",
    "degree": "亲密度",
}

# --------------------------- 5.3 角色场景特有映射（只写和通用不同的 key，不再继承通用几百个） ---------------------------
# 通用里 gender→性别 identity→身份 都一样正确，只写 type 值含义不同这一个
VAL_PROMPT_CHAR_FIELD_ZH: dict = {
    "type": "身份类型",  # 角色场景：男主/女主/配角（通用类型太模糊）
}

# --------------------------- 5.4 时间场景特有映射（只写和通用不同的 key） ---------------------------
VAL_PROMPT_TIME_FIELD_ZH: dict = {
    "parent_id": "上级时间",   # 通用是「上级地点」，时间线父子链要改
    "start": "起始时间",
    "end": "截止时间",
    "duration": "持续时间",
    "type": "时间类型",       # 节日/节气/事件
}

# --------------------------- 5.5 地点场景特有映射（只写和通用不同的 key） ---------------------------
VAL_PROMPT_LOC_FIELD_ZH: dict = {
    "type": "地点类型",  # 通用「类型」太宽泛，地点上下文用精确的
}

# --------------------------- 5.6 关系列表条目映射（只写和通用不同的 key） ---------------------------
VAL_PROMPT_REL_FIELD_ZH: dict = {
    "type": "关系",       # relationships[x].type 是关系类型，不是通用类型
    "degree": "亲密度",
    "desc": "说明",
    "description": "关系说明",
}

# --------------------------- 5.7 按 category → 映射表快速分发 ---------------------------
VAL_PROMPT_FIELD_ZH_BY_CATEGORY: dict = {
    "entity": VAL_PROMPT_CHAR_FIELD_ZH,
    "temporal": VAL_PROMPT_TIME_FIELD_ZH,
    "location": VAL_PROMPT_LOC_FIELD_ZH,
    "relationship": VAL_PROMPT_REL_FIELD_ZH,
}

# --------------------------- 5.8 用户自定义属性（attributes）常用创作字段映射【重点补充】 ---------------------------
# 用户可能在自定义属性里随手写的英文键 → 中文标签（后端固定字段不会出现在此）
# 覆盖网文/剧本/角色卡最常见的 30 个常用属性：外貌/性格/爱好/弱点/动机/修为/背景故事/口头禅……
VAL_PROMPT_ATTRIBUTE_FIELD_ZH: dict = {
    # ===== 外貌外形 =====
    "appearance": "外貌",
    "appearance_desc": "外貌",
    "look": "外貌",
    "looks": "外貌",
    "face": "面容",
    "figure": "身形",
    "height": "身高",
    "weight": "体重",
    "hair": "发型发色",
    "eyes": "眼睛",
    "eyes_color": "瞳色",
    "outfit": "服饰",
    "clothes": "服饰",
    "clothing": "服饰",
    "dress": "穿着",
    "accessory": "配饰",
    "accessories": "配饰",
    "scar": "伤疤",
    "tattoo": "纹身",
    "mark": "印记",

    # ===== 性格与特质 =====
    "personality": "性格",
    "character": "性格",
    "trait": "特质",
    "traits": "特质",
    "temperament": "气质",
    "habit": "习惯",
    "habits": "习惯",
    "hobby": "爱好",
    "hobbies": "爱好",
    "interest": "兴趣",
    "interests": "兴趣",
    "catchphrase": "口头禅",
    "motto": "座右铭",
    "speech_style": "说话风格",

    # ===== 动机目标 =====
    "motivation": "动机",
    "goal": "目标",
    "dream": "梦想",
    "ambition": "野心",
    "wish": "心愿",
    "regret": "遗憾",
    "obsession": "执念",
    "fear": "恐惧",
    "weakness": "弱点",
    "flaw": "缺陷",
    "strength": "优点",
    "advantage": "长处",
    "disadvantage": "短处",
    "likes": "喜欢",
    "loves": "挚爱",
    "dislikes": "厌恶",
    "hates": "痛恨",

    # ===== 能力与武力 =====
    "ability": "能力",
    "abilities": "能力",
    "power": "力量",
    "skill": "技能",
    "skills": "技能",
    "spell": "术法",
    "magic": "术法",
    "cultivation": "修为境界",
    "realm": "境界",
    "level": "等级",
    "weapon": "武器",
    "weapons": "武器",
    "mount": "坐骑",
    "pet": "宠物",
    "artifact": "法宝",
    "treasure": "宝物",
    "essence": "修为本质",
    "core_essence": "修为本质",

    # ===== 背景故事 =====
    "background": "背景",
    "backstory": "背景故事",
    "story": "经历",
    "experience": "经历",
    "experiences": "经历",
    "past": "过往",
    "history": "生平",
    "origin": "出身",
    "childhood": "童年",
    "education": "学历",
    "social": "社会关系",
    "reputation": "名声",

    # ===== 地点补充 =====
    "terrain": "地形",
    "climate": "气候",
    "resources": "特产资源",
    "custom": "风俗",
    "tradition": "传统",

    # ===== 时间补充 =====
    "event": "事件",
    "incident": "事件",
    "significance": "意义",
}

# --------------------------- 5.9 字段值中文化映射（只保留前端真实枚举，砍掉拼音废话） ---------------------------
# 结构：字段名（英文） → { 原始值（大小写不敏感）: 中文标准值 }
VAL_PROMPT_VALUE_ZH: dict = {
    # ===== 性别：前端真实枚举 =====
    "gender": {
        "male": "男", "m": "男", "Male": "男", "MALE": "男",
        "female": "女", "f": "女", "Female": "女", "FEMALE": "女",
        "unknown": "未知", "other": "其他",
    },
    # ===== 角色身份类型：前端真实枚举 =====
    "type": {
        # 男女主
        "hero": "男主", "male_lead": "男主", "male_protagonist": "男主",
        "heroine": "女主", "female_lead": "女主", "female_protagonist": "女主",
        # 主角/配角/反派
        "protagonist": "主角", "main": "主角", "lead": "主角",
        "supporting": "配角", "support": "配角", "side": "配角", "secondary": "配角",
        "villain": "反派", "antagonist": "反派", "boss": "BOSS",
        "mentor": "导师", "teacher": "导师", "master": "师父",
        "rival": "对手", "enemy": "敌人",
        "family": "家人", "friend": "朋友",
        "colleague": "同事", "passerby": "路人", "npc": "NPC", "cameo": "客串",
    },
    # ===== 关系类型中文化 =====
    "rel_type": {
        "lover": "恋人", "love": "爱慕", "adore": "贪恋", "obsession": "执念",
        "husband": "丈夫", "wife": "妻子", "spouse": "配偶",
        "father": "父亲", "mother": "母亲", "son": "儿子", "daughter": "女儿",
        "brother": "兄弟", "sister": "姐妹", "sibling": "兄弟姐妹",
        "elder_brother": "大哥", "younger_brother": "小弟",
        "elder_sister": "大姐", "younger_sister": "小妹",
        "friend": "朋友", "best_friend": "挚友",
        "enemy": "敌人", "rival": "对手",
        "master": "师父", "disciple": "徒弟", "student": "弟子",
        "boss": "老大", "subordinate": "手下", "henchman": "小弟",
        "colleague": "同事", "classmate": "同学",
    },
    # ===== 亲密度量化标签 =====
    "degree": {
        "close": "亲密", "intimate": "亲密", "best": "至交",
        "good": "友好", "normal": "普通",
        "distant": "疏远", "cold": "冷淡",
        "hostile": "敌对", "hate": "仇恨",
    },
    # ===== 地点类型 =====
    "location_type": {
        "city": "城市", "province": "省份", "country": "国家",
        "town": "城镇", "village": "村庄", "region": "区域", "district": "行政区",
        "continent": "大洲", "realm": "界域", "sect": "门派", "school": "学院",
        "building": "建筑", "shop": "店铺", "house": "住宅",
        "company": "公司", "scenic": "景区", "mountain": "山脉", "river": "河流",
    },
    # ===== 时间类型 =====
    "time_type": {
        "era": "时代", "dynasty": "朝代", "year": "年份",
        "season": "季节", "month": "月份", "week": "周次",
        "festival": "节日", "holiday": "假期", "solar_term": "节气",
        "event": "事件", "phase": "阶段", "period": "时段", "moment": "时刻",
    },
}


DANMAKU_MAX_CHARS = 200
DANMAKU_MAX_VISIBLE = 30
DANMAKU_MAX_BASE_SPEED = 80


# --------------------------- 5.10 标签 ID→名称映射（动态构建） ---------------------------
# 输入：label_config（来自引擎 label_config_get 返回，结构同 labels.json）
# 结构：{"label_categories": {"subject": [{"id": "xxx", "name": "xxx", ...}, ...], ...}, "forbidden_tags": [...]}
# 返回：{"subject": {"id": "name"}, "style": {"id": "name"}, ...}
def build_label_id_name_map(label_config: dict) -> dict:
    result = {}
    categories = label_config.get("label_categories", {})
    for cat, items in categories.items():
        if isinstance(items, list):
            result[cat] = {item.get("id"): item.get("name", item.get("id")) for item in items if isinstance(item, dict) and item.get("id")}
    return result


def get_label_name(label_id_name_map: dict, category: str, label_id: str) -> str:
    return label_id_name_map.get(category, {}).get(label_id, label_id)
