"""
🏛️ 领域常量类与类型定义 (Domain Constants & Types)
基于 values.py 构建逻辑类，并动态生成 Literal 类型以消除警告。
"""
from enum import Enum, IntEnum
from typing import Literal, List, NamedTuple, Any, Set, Dict, Union, Optional, cast, TypedDict, Type, get_args
from app.common import values as va
from app.common import keys as ke
from pydantic import BaseModel
from app.core.validators.data_validator import IS_LIST, IS_STR, IS_DICT, IS_INT, IS_FLOAT, IS_BOOL
from app.utils.logger import LoggerManager as logger

CHINESE_NAME = "认知架构基石与策略中枢"

"""
# ======================================================================
# 🛠️ 辅助工具与装饰器
# ======================================================================
"""


def build_literal_from_class(cls: type) -> type:
    """
    从常量类动态生成Literal类型（修复原代码bug，仅提取业务常量）
    全局唯一类型生成工具，适配FastAPI/类型校验/配置检查
    """
    values = []
    # 遍历类属性，仅提取非下划线开头、值为字符串的业务常量
    for attr in dir(cls):
        if not attr.startswith("_"):
            attr_value = getattr(cls, attr)
            if isinstance(attr_value, str):
                values.append(attr_value)

    # 去重+排序，保证Literal类型稳定
    unique_values = sorted(list(set(values)))
    if not unique_values:
        logger.warning(f"⚠️ 常量类 {cls.__name__} 未提取到有效字符串常量", module_name=CHINESE_NAME)

    return Literal[tuple(unique_values)]  # type: ignore


"""
# ======================================================================
# 🏛️ 领域常量类 (Domain Constant Classes)
# ======================================================================
"""


class TreeNode(BaseModel):
    """前端文件树节点模型"""
    label: str
    key: str
    type: str
    ext: str = ""
    children: List["TreeNode"] = []


class FileUpdateRequest(BaseModel):
    """文件更新请求模型"""
    content: str


class ConstNodeID:
    """节点 ID"""
    DIVINE_EYE = va.VAL_NODE_DIVINE_EYE                    # 上帝之眼
    LOAD_DATA = va.VAL_NODE_LOAD_DATA                      # 数据加载
    DEBATE_SUBGRAPH = va.VAL_NODE_DEBATE_SUBGRAPH          # 辩论子图
    RATIONAL_SINGLE = va.VAL_NODE_RATIONAL_SINGLE          # 理性暴君单节点
    EMOTIONAL_SINGLE = va.VAL_NODE_EMOTIONAL_SINGLE        # 感性圣母单节点
    DIVINE_HAND = va.VAL_NODE_DIVINE_HAND                  # 上帝之手
    REVISE_AND_DIAGNOSE = va.VAL_NODE_REVISE_AND_DIAGNOSE  # 修复与验证
    GENERATE_SIGNATURE = va.VAL_NODE_GENERATE_SIGNATURE    # 语义签名
    PERSIST_RESULT = va.VAL_NODE_PERSIST_RESULT            # 持久化
    WAIT_HUMAN = va.VAL_NODE_WAIT_HUMAN                    # 人工介入


class NodeStatus:
    """状态码"""
    # -- 运行中 --
    RUNNING = va.VAL_STATUS_RUNNING

    # -- 流程流转 --
    GOTO_LOAD_DATA = va.VAL_STATUS_GOTO_LOAD_DATA          # 数据不足，加载更高层级
    GOTO_DIVINE_EYE = va.VAL_STATUS_GOTO_DIVINE_EYE        # 返回上帝之眼重新审视
    GOTO_DIVINE_HAND = va.VAL_STATUS_GOTO_DIVINE_HAND      # 进入上帝之手裁决
    GOTO_DEBATE_SUBGRAPH = va.VAL_STATUS_GOTO_DEBATE_SUBGRAPH  # 进入辩论子图
    GOTO_RATIONAL_SINGLE = va.VAL_STATUS_GOTO_RATIONAL_SINGLE  # 进入理性暴君单节点
    GOTO_EMOTIONAL_SINGLE = va.VAL_STATUS_GOTO_EMOTIONAL_SINGLE  # 进入感性圣母单节点

    # -- 终止 --
    COMPLETED = va.VAL_STATUS_COMPLETED                    # 优化完成
    COMPLETED_TRIVIAL = va.VAL_STATUS_COMPLETED_TRIVIAL    # 无优化空间
    COMPLETED_BY_BUDGET = va.VAL_STATUS_COMPLETED_BY_BUDGET  # 资源耗尽
    FAILED = va.VAL_STATUS_FAILED                          # 异常失败
    SUSPENDED = va.VAL_STATUS_SUSPENDED                    # 挂起等待人工


class DecisionType:
    # 正向终态
    ACCEPT_CURRENT = va.VAL_DECISION_ACCEPT_CURRENT
    FIX_REQUIRED = va.VAL_DECISION_FIX_REQUIRED

    # 流转与回退
    BACK_TO_EYE = va.VAL_DECISION_BACK_TO_EYE
    CONTINUE_DEBATE = va.VAL_DECISION_CONTINUE_DEBATE
    DEEP_ANALYSIS_RATIONAL = va.VAL_DECISION_DEEP_ANALYSIS_RATIONAL
    DEEP_ANALYSIS_EMOTIONAL = va.VAL_DECISION_DEEP_ANALYSIS_EMOTIONAL

    # 人工介入
    REQUEST_USER_CLARIFICATION = va.VAL_DECISION_REQUEST_USER_CLARIFICATION

    # 终止兜底
    TERMINATE_BY_CONSENSUS = va.VAL_DECISION_TERMINATE_BY_CONSENSUS
    TERMINATE_BY_RESOURCE_EXHAUSTION = va.VAL_DECISION_TERMINATE_BY_RESOURCE_EXHAUSTION
    TERMINATE_BY_ERROR = va.VAL_DECISION_TERMINATE_BY_ERROR


class StrategyCode:
    """
    上帝之眼战略代码
    每次预分析产出唯一战略，驱动下一步路由。
    """
    TERMINATE_TRIVIAL = va.VAL_STRATEGY_TERMINATE_TRIVIAL      # 文本已高度自洽，直接结束
    UPGRADE_DATA = va.VAL_STRATEGY_UPGRADE_DATA                # 信息不足，加载更高数据层级
    HAND_DIRECT = va.VAL_STRATEGY_HAND_DIRECT                  # 信息充足，直接交付上帝之手
    DEBATE = va.VAL_STRATEGY_DEBATE                            # 需多视角辩论，进入辩论子图
    RATIONAL_ONLY = va.VAL_STRATEGY_RATIONAL_ONLY              # 仅需逻辑一致性分析
    EMOTIONAL_ONLY = va.VAL_STRATEGY_EMOTIONAL_ONLY            # 仅需情感表达力分析
    REQUEST_HUMAN_IN_LOOP = va.VAL_STRATEGY_REQUEST_HUMAN_IN_LOOP  # 系统无法决策，挂起等人工


class FocusArea:
    """
    聚焦领域 (Focus Areas)
    """
    PLOT_COHERENCE = va.VAL_FOCUS_PLOT_COHERENCE
    CHARACTER_CONSISTENCY = va.VAL_FOCUS_CHARACTER_CONSISTENCY
    BALANCE = va.VAL_FOCUS_BALANCE
    EMOTIONAL_AUTHENTICITY = va.VAL_FOCUS_EMOTIONAL_AUTHENTICITY
    PROSE_RHYTHM = va.VAL_FOCUS_PROSE_RHYTHM
    WORLD_RULE_VIOLATION = va.VAL_FOCUS_WORLD_RULE_VIOLATION
    DIALOGUE_NATURALNESS = va.VAL_FOCUS_DIALOGUE_NATURALNESS
    NONE = va.VAL_FOCUS_NONE


class RoutingContext:
    """
    路由上下文配置对象
    用于将通用的路由逻辑参数化，适配上帝之眼和上帝之手
    """

    def __init__(
            self,
            name: str,
            state_key: str,
            code_field: str,
            valid_codes: Set[Optional[Union[StrategyCode, DecisionType]]],
            config_map: Dict[Optional[Union[StrategyCode, DecisionType]], Dict[str, Any]],
            safety_code: Optional[Union[StrategyCode, DecisionType]],
            safety_target: str,
            module_name: str
    ):
        self.name = name
        self.state_key = state_key
        self.code_field = code_field
        self.valid_codes = valid_codes
        self.config_map = config_map
        self.safety_code = safety_code
        self.safety_target = safety_target
        self.module_name = module_name


class ValidationRule(NamedTuple):
    path: str
    required: bool
    validator: Any
    description: str
    strip_quotes: bool = False


class StorageType(str, Enum):
    """步骤类型枚举，统一管理所有步骤的类型标识"""
    LOCAL = ke.KEY_LOCAL
    REDIS = ke.KEY_REDIS


# class TextOptimizationLevel(IntEnum):
#     """
#     文本优化专用数据层级。
#     层级越高，信息量越大，细粒度越高。
#     层级值直接对应加载的数据深度。
#     """
#     # 0 级：最终选定全文 + 用户补充信息
#     FINAL_TEXT = 0
#
#     # 1 级：全文级诊断聚合摘要
#     FULL_DIAGNOSIS = 1
#
#     # 2 级：段落级诊断详情
#     PARAGRAPH_DIAGNOSIS = 2
#
#     @classmethod
#     def get_valid_level(cls):
#         return va.VAL_LEVEL_DESCRIPTIONS.keys()
#
#     @classmethod
#     def get_description(cls, value: int) -> str:
#         """获取层级的中文描述"""
#         return va.VAL_LEVEL_DESCRIPTIONS.get(value, "未知层级")
#
#     @classmethod
#     def get_prompt_lines(cls) -> List[str]:
#         """生成用于 Prompt 注入的列表，格式: 'ID - 描述'"""
#         return [f"{level} - {desc}" for level, desc in va.VAL_LEVEL_DESCRIPTIONS.items()]
#
#     @classmethod
#     def get_options_string(cls) -> str:
#         """直接生成用于 Prompt 中 level_options 的字符串"""
#         return "\n".join(cls.get_prompt_lines())
#
#     @classmethod
#     def clamp(cls, value: int) -> int:
#         """将任意整数钳制在合法层级范围内"""
#         valid_values = [level.value for level in cls]
#         return max(min(value, max(valid_values)), min(valid_values))

class TextOptimizationLevel(IntEnum):
    """文本优化数据层级，层级值对应加载的数据深度"""

    FINAL_TEXT = 0
    """最终选定全文 + 用户补充信息"""

    FULL_DIAGNOSIS = 1
    """全文级诊断聚合摘要"""

    PARAGRAPH_DIAGNOSIS = 2
    """段落级诊断聚合摘要"""

    @classmethod
    def get_description(cls, value: int) -> str:
        """获取层级的中文描述"""
        level = cls(value)
        return level.__doc__.strip() if level.__doc__ else "未知层级"

    @classmethod
    def get_prompt_lines(cls) -> List[str]:
        """生成用于 Prompt 注入的列表，格式: 'ID - 描述'"""
        return [f"{level.value} - {level.__doc__.strip()}" for level in cls]

    @classmethod
    def get_options_string(cls) -> str:
        """直接生成用于 Prompt 中 level_options 的字符串"""
        return "\n".join(cls.get_prompt_lines())

    @classmethod
    def clamp(cls, value: int) -> int:
        """将任意整数钳制在合法层级范围内"""
        valid_values = [level.value for level in cls]
        return max(min(value, max(valid_values)), min(valid_values))


TextOptimizationLevel.MIN_LEVEL = min(member.value for member in TextOptimizationLevel)
TextOptimizationLevel.MAX_LEVEL = max(member.value for member in TextOptimizationLevel)

"""
# ======================================================================
# 🏷️ 动态生成的类型别名 (Generated Type Aliases)
# ======================================================================
"""

ConstNodeIDLiteral = cast(Type, build_literal_from_class(ConstNodeID))


class DecisionOption(TypedDict):
    description: str
    max_rounds: int
    next_step: ConstNodeIDLiteral  # type: ignore


class StrategyOption(TypedDict):
    description: str
    next_step: ConstNodeIDLiteral  # type: ignore
    focus_areas: list[FocusArea]
    max_rounds: int


NodeStatusLiteral = build_literal_from_class(NodeStatus)

DecisionTypeLiteral = build_literal_from_class(DecisionType)

StrategyCodeLiteral = build_literal_from_class(StrategyCode)

FocusAreaLiteral = build_literal_from_class(FocusArea)

# [上帝之眼战略代码配置]
VAL_STRATEGY_CONFIGS: Dict[StrategyCode, StrategyOption] = {
    va.VAL_STRATEGY_TERMINATE_TRIVIAL: {
        ke.KEY_DESCRIPTION: "文本已高度自洽，无需进一步优化",
        ke.KEY_NEXT_STEP: va.VAL_NODE_GENERATE_SIGNATURE,
        ke.KEY_FOCUS_AREAS: [va.VAL_FOCUS_NONE],
        ke.KEY_MAX_ROUNDS: 0,
    },
    va.VAL_STRATEGY_UPGRADE_DATA: {
        ke.KEY_DESCRIPTION: "信息不足以支撑判断，需加载更高层级诊断数据",
        ke.KEY_NEXT_STEP: va.VAL_NODE_LOAD_DATA,
        ke.KEY_FOCUS_AREAS: [va.VAL_FOCUS_NONE],
        ke.KEY_MAX_ROUNDS: 0,
    },
    va.VAL_STRATEGY_HAND_DIRECT: {
        ke.KEY_DESCRIPTION: "信息充足，直接交付上帝之手做最终裁决",
        ke.KEY_NEXT_STEP: va.VAL_NODE_DIVINE_HAND,
        ke.KEY_FOCUS_AREAS: [va.VAL_FOCUS_BALANCE],
        ke.KEY_MAX_ROUNDS: 0,
    },
    va.VAL_STRATEGY_DEBATE: {
        ke.KEY_DESCRIPTION: "启动理性暴君与感性圣母多视角辩论，深度分析文本",
        ke.KEY_NEXT_STEP: va.VAL_NODE_DEBATE_SUBGRAPH,
        ke.KEY_FOCUS_AREAS: [va.VAL_FOCUS_BALANCE],
        ke.KEY_MAX_ROUNDS: 2,
    },
    va.VAL_STRATEGY_RATIONAL_ONLY: {
        ke.KEY_DESCRIPTION: "仅需理性暴君分析情节连贯性、人物一致性与世界观规则",
        ke.KEY_NEXT_STEP: va.VAL_NODE_RATIONAL_SINGLE,
        ke.KEY_FOCUS_AREAS: [
            va.VAL_FOCUS_PLOT_COHERENCE,
            va.VAL_FOCUS_CHARACTER_CONSISTENCY,
            va.VAL_FOCUS_WORLD_RULE_VIOLATION,
        ],
        ke.KEY_MAX_ROUNDS: 1,
    },
    va.VAL_STRATEGY_EMOTIONAL_ONLY: {
        ke.KEY_DESCRIPTION: "仅需感性圣母评估情感真实性、文笔节奏与对话自然度",
        ke.KEY_NEXT_STEP: va.VAL_NODE_EMOTIONAL_SINGLE,
        ke.KEY_FOCUS_AREAS: [
            va.VAL_FOCUS_EMOTIONAL_AUTHENTICITY,
            va.VAL_FOCUS_PROSE_RHYTHM,
            va.VAL_FOCUS_DIALOGUE_NATURALNESS,
        ],
        ke.KEY_MAX_ROUNDS: 1,
    },
    va.VAL_STRATEGY_REQUEST_HUMAN_IN_LOOP: {
        ke.KEY_DESCRIPTION: "系统无法自主决策，挂起等待人工介入提供关键信息",
        ke.KEY_NEXT_STEP: va.VAL_NODE_WAIT_HUMAN,
        ke.KEY_FOCUS_AREAS: [va.VAL_FOCUS_NONE],
        ke.KEY_MAX_ROUNDS: 0,
    },
}

# [合法战略代码]
VAL_VALID_STRATEGY: Set[StrategyCode] = set(VAL_STRATEGY_CONFIGS.keys())

# [上帝之手决策配置]
VAL_DECISION_CONFIGS: Dict[DecisionType, StrategyOption] = {
    # -- 正向终态 --
    va.VAL_DECISION_ACCEPT_CURRENT: {
        ke.KEY_DESCRIPTION: "文本已满足优化目标，采纳当前版本并结束任务",
        ke.KEY_MAX_ROUNDS: 0,
        ke.KEY_NEXT_STEP: va.VAL_NODE_GENERATE_SIGNATURE,
    },
    va.VAL_DECISION_FIX_REQUIRED: {
        ke.KEY_DESCRIPTION: "问题清单明确，进入修复与验证节点",
        ke.KEY_MAX_ROUNDS: 0,
        ke.KEY_NEXT_STEP: va.VAL_NODE_REVISE_AND_DIAGNOSE,
    },

    # -- 流转与回退 --
    va.VAL_DECISION_BACK_TO_EYE: {
        ke.KEY_DESCRIPTION: "信息不足或需要重新评估，回退至上帝之眼重新审视",
        ke.KEY_MAX_ROUNDS: 0,
        ke.KEY_NEXT_STEP: va.VAL_NODE_DIVINE_EYE,
    },
    va.VAL_DECISION_CONTINUE_DEBATE: {
        ke.KEY_DESCRIPTION: "分析不充分，继续辩论子图进行更多轮次多视角分析",
        ke.KEY_MAX_ROUNDS: 2,
        ke.KEY_NEXT_STEP: va.VAL_NODE_DEBATE_SUBGRAPH,
    },
    va.VAL_DECISION_DEEP_ANALYSIS_RATIONAL: {
        ke.KEY_DESCRIPTION: "需要理性暴君对特定问题进行更深层次分析",
        ke.KEY_MAX_ROUNDS: 1,
        ke.KEY_NEXT_STEP: va.VAL_NODE_RATIONAL_SINGLE,
    },
    va.VAL_DECISION_DEEP_ANALYSIS_EMOTIONAL: {
        ke.KEY_DESCRIPTION: "需要感性圣母对特定问题进行更深层次分析",
        ke.KEY_MAX_ROUNDS: 1,
        ke.KEY_NEXT_STEP: va.VAL_NODE_EMOTIONAL_SINGLE,
    },

    # -- 人工介入 --
    va.VAL_DECISION_REQUEST_USER_CLARIFICATION: {
        ke.KEY_DESCRIPTION: "缺少关键信息无法裁决，挂起等待用户补充",
        ke.KEY_MAX_ROUNDS: 0,
        ke.KEY_NEXT_STEP: va.VAL_NODE_WAIT_HUMAN,
    },

    # -- 终止兜底 --
    va.VAL_DECISION_TERMINATE_BY_CONSENSUS: {
        ke.KEY_DESCRIPTION: "分析达成一致，正常结束任务",
        ke.KEY_MAX_ROUNDS: 0,
        ke.KEY_NEXT_STEP: va.VAL_NODE_GENERATE_SIGNATURE,
    },
    va.VAL_DECISION_TERMINATE_BY_RESOURCE_EXHAUSTION: {
        ke.KEY_DESCRIPTION: "资源耗尽，强制终止并生成当前阶段的签名",
        ke.KEY_MAX_ROUNDS: 0,
        ke.KEY_NEXT_STEP: va.VAL_NODE_GENERATE_SIGNATURE,
    },
    va.VAL_DECISION_TERMINATE_BY_ERROR: {
        ke.KEY_DESCRIPTION: "发生系统错误，挂起等待人工处理",
        ke.KEY_MAX_ROUNDS: 0,
        ke.KEY_NEXT_STEP: va.VAL_NODE_WAIT_HUMAN,
    },
}

# [合法决策类型]
VAL_VALID_DECISIONS: Set[DecisionType] = set(VAL_DECISION_CONFIGS.keys())

# [正向映射：节点 ID -> 状态码]
VAL_NODE_TO_STATUS_MAP: Dict[ConstNodeIDLiteral, NodeStatusLiteral] = {
    # 中间流转节点
    va.VAL_NODE_LOAD_DATA: va.VAL_STATUS_GOTO_LOAD_DATA,
    va.VAL_NODE_DIVINE_EYE: va.VAL_STATUS_GOTO_DIVINE_EYE,
    va.VAL_NODE_DEBATE_SUBGRAPH: va.VAL_STATUS_GOTO_DEBATE_SUBGRAPH,
    va.VAL_NODE_RATIONAL_SINGLE: va.VAL_STATUS_GOTO_RATIONAL_SINGLE,
    va.VAL_NODE_EMOTIONAL_SINGLE: va.VAL_STATUS_GOTO_EMOTIONAL_SINGLE,
    va.VAL_NODE_DIVINE_HAND: va.VAL_STATUS_GOTO_DIVINE_HAND,

    # 终态节点
    va.VAL_NODE_REVISE_AND_DIAGNOSE: va.VAL_STATUS_COMPLETED,
    va.VAL_NODE_GENERATE_SIGNATURE: va.VAL_STATUS_COMPLETED,
    va.VAL_NODE_PERSIST_RESULT: va.VAL_STATUS_COMPLETED,
    va.VAL_NODE_WAIT_HUMAN: va.VAL_STATUS_SUSPENDED,
}

# [反向映射：状态码 -> 节点 ID]
VAL_STATUS_TO_NODE_MAP: Dict[NodeStatusLiteral, ConstNodeIDLiteral] = {
    # 流程流转
    va.VAL_STATUS_GOTO_LOAD_DATA: va.VAL_NODE_LOAD_DATA,
    va.VAL_STATUS_GOTO_DIVINE_EYE: va.VAL_NODE_DIVINE_EYE,
    va.VAL_STATUS_GOTO_DEBATE_SUBGRAPH: va.VAL_NODE_DEBATE_SUBGRAPH,
    va.VAL_STATUS_GOTO_RATIONAL_SINGLE: va.VAL_NODE_RATIONAL_SINGLE,
    va.VAL_STATUS_GOTO_EMOTIONAL_SINGLE: va.VAL_NODE_EMOTIONAL_SINGLE,
    va.VAL_STATUS_GOTO_DIVINE_HAND: va.VAL_NODE_DIVINE_HAND,

    # 终止状态 → 语义签名
    va.VAL_STATUS_COMPLETED: va.VAL_NODE_GENERATE_SIGNATURE,
    va.VAL_STATUS_COMPLETED_TRIVIAL: va.VAL_NODE_GENERATE_SIGNATURE,
    va.VAL_STATUS_COMPLETED_BY_BUDGET: va.VAL_NODE_GENERATE_SIGNATURE,

    # 异常/挂起 → 人工介入
    va.VAL_STATUS_SUSPENDED: va.VAL_NODE_WAIT_HUMAN,
    va.VAL_STATUS_FAILED: va.VAL_NODE_WAIT_HUMAN,

    # 兜底
    va.VAL_STATUS_RUNNING: va.VAL_NODE_DIVINE_HAND,
}

# [合法节点集合]
VAL_VALID_NODE_IDS: Set[str] = set(get_args(ConstNodeIDLiteral))

# [合法状态集合]
VAL_VALID_STATUS: Set[str] = set(get_args(NodeStatusLiteral))

# [合法聚焦领域集合]
VAL_VALID_FOCUS_AREA: Set[str] = set(get_args(FocusAreaLiteral))


def get_status_from_node(node_id: str) -> NodeStatusLiteral:
    """
    【通用工具】Node -> Status。完全依赖常量映射。
    """
    if node_id in VAL_NODE_TO_STATUS_MAP:
        return VAL_NODE_TO_STATUS_MAP[cast(ConstNodeIDLiteral, node_id)]

    logger.warning(f"⚠️ 节点 [{node_id}] 未在映射表中，默认返回 '{NodeStatus.RUNNING}'", module_name=CHINESE_NAME)
    return cast(NodeStatusLiteral, NodeStatus.RUNNING)


def get_next_node_from_status(current_status: NodeStatusLiteral) -> ConstNodeIDLiteral:
    """
    【通用工具】Status -> Node。完全依赖常量映射。
    """
    if current_status in VAL_STATUS_TO_NODE_MAP:
        return VAL_STATUS_TO_NODE_MAP[current_status]

    logger.warning(f"⚠️ 未知状态 [{current_status}]，默认路由至 {ConstNodeID.DIVINE_EYE}", module_name=CHINESE_NAME)
    return cast(ConstNodeIDLiteral, ConstNodeID.DIVINE_EYE)


"""
# ======================================================================
# 🏷️ 校验规则
# ======================================================================
"""

VAL_STEP_CHECK_RULES: Dict[str, List[ValidationRule]] = {
    # 串行 - 场景适配
    va.VAL_RULE_SCENE_ADAPTATION: [
        ValidationRule(ke.KEY_SCENE_GUIDE, True, IS_DICT, f"{ke.KEY_SCENE_GUIDE}（场景适配）：", False),
        ValidationRule(f"{ke.KEY_SCENE_GUIDE}.{ke.KEY_CHARACTER_PROFILES}", False, IS_LIST, f"{ke.KEY_CHARACTER_PROFILES}（角色设定）：",
                       True),
        ValidationRule(f"{ke.KEY_SCENE_GUIDE}.{ke.KEY_RELATIONSHIP_MAP}", False, IS_LIST,
                       f"{ke.KEY_RELATIONSHIP_MAP}（人物关系）：", True),
        ValidationRule(f"{ke.KEY_SCENE_GUIDE}.{ke.KEY_WORLDVIEW_RULES}", False, IS_LIST,
                       f"{ke.KEY_WORLDVIEW_RULES}（世界观规则）：", True),
        ValidationRule(f"{ke.KEY_SCENE_GUIDE}.{ke.KEY_STYLE_PREFERENCE}", False, IS_LIST,
                       f"{ke.KEY_STYLE_PREFERENCE}（风格倾向）：", True)
    ],

    # 串行 预处理
    va.VAL_RULE_PREPROCESS_CHINESE_TEXT: [
        ValidationRule(ke.KEY_PREPROCESS_FIX, True, IS_DICT, f"{ke.KEY_PREPROCESS_FIX}（基础校对）：", False),
        ValidationRule(f"{ke.KEY_PREPROCESS_FIX}.{ke.KEY_CLEANED_TEXT}", True, IS_STR, f"{ke.KEY_CLEANED_TEXT}（清洗后文本）：",
                       True),
        ValidationRule(f"{ke.KEY_PREPROCESS_FIX}.{ke.KEY_ISSUES_FIXED}", False, IS_LIST,
                       f"{ke.KEY_ISSUES_FIXED}（修正记录）：", True),
    ],
    va.VAL_RULE_CONTEXTUAL_TYPO_FIX: [
        ValidationRule(ke.KEY_CONTEXT_TYPO_FIX, True, IS_DICT, f"{ke.KEY_CONTEXT_TYPO_FIX}（语义校勘）：", False),
        ValidationRule(f"{ke.KEY_CONTEXT_TYPO_FIX}.{ke.KEY_CLEANED_TEXT}", True, IS_STR,
                       f"{ke.KEY_CLEANED_TEXT}（清洗后文本）：",
                       True),
        ValidationRule(f"{ke.KEY_CONTEXT_TYPO_FIX}.{ke.KEY_ISSUES_FIXED}", False, IS_LIST,
                       f"{ke.KEY_ISSUES_FIXED}（修正记录）：",
                       True),
    ],
    va.VAL_RULE_SYNTAX_SEMANTIC_POLISH: [
        ValidationRule(ke.KEY_SYNTAX_FIX, True, IS_DICT, f"{ke.KEY_SYNTAX_FIX}（句式疏通）：", False),
        ValidationRule(f"{ke.KEY_SYNTAX_FIX}.{ke.KEY_CLEANED_TEXT}", True, IS_STR, f"{ke.KEY_CLEANED_TEXT}（清洗后文本）：",
                       True),
        ValidationRule(f"{ke.KEY_SYNTAX_FIX}.{ke.KEY_ISSUES_FIXED}", False, IS_LIST, f"{ke.KEY_ISSUES_FIXED}（修正记录）：",
                       True),
    ],

    # 并行 诊断
    va.VAL_RULE_EXPRESSIVENESS_DIAGNOSIS: [
        ValidationRule(ke.KEY_EXPRESS_DIAGNOSIS, True, IS_DICT, f"{ke.KEY_EXPRESS_DIAGNOSIS}（表达效果诊断）：", False),
        ValidationRule(f"{ke.KEY_EXPRESS_DIAGNOSIS}.{ke.KEY_MODIFIER_FLUENCY}", False, IS_LIST,
                       f"{ke.KEY_MODIFIER_FLUENCY}（修饰词流畅度）：",
                       True),
        ValidationRule(f"{ke.KEY_EXPRESS_DIAGNOSIS}.{ke.KEY_RHETORIC_QUALITY}", False, IS_LIST,
                       f"{ke.KEY_RHETORIC_QUALITY}（修辞质量）：",
                       True),
        ValidationRule(f"{ke.KEY_EXPRESS_DIAGNOSIS}.{ke.KEY_DESCRIPTION_BALANCE}", False, IS_LIST,
                       f"{ke.KEY_DESCRIPTION_BALANCE}（描述平衡）：",
                       True),
        ValidationRule(f"{ke.KEY_EXPRESS_DIAGNOSIS}.{ke.KEY_EMOTION_CURVE}", False, IS_LIST,
                       f"{ke.KEY_EMOTION_CURVE}（情绪曲线）：",
                       True),
        ValidationRule(f"{ke.KEY_EXPRESS_DIAGNOSIS}.{ke.KEY_STYLE_REGISTER}", False, IS_LIST,
                       f"{ke.KEY_STYLE_REGISTER}（样式注册）：",
                       True),
        ValidationRule(f"{ke.KEY_EXPRESS_DIAGNOSIS}.{ke.KEY_STRUCTURE_REDUNDANCY}", False, IS_LIST,
                       f"{ke.KEY_STRUCTURE_REDUNDANCY}（结构冗余）：",
                       True),
        ValidationRule(f"{ke.KEY_EXPRESS_DIAGNOSIS}.{ke.KEY_OPENING_ENDING}", False, IS_LIST,
                       f"{ke.KEY_OPENING_ENDING}（开头结尾）：",
                       True),
    ],
    va.VAL_RULE_EVENT_LOGIC_DIAGNOSIS: [
        ValidationRule(ke.KEY_EVENT_LOGIC_DIAGNOSIS, True, IS_DICT, f"{ke.KEY_EVENT_LOGIC_DIAGNOSIS}（叙事逻辑诊断）：", False),
        ValidationRule(f"{ke.KEY_EVENT_LOGIC_DIAGNOSIS}.{ke.KEY_EVENT_CHAIN}", False, IS_LIST,
                       f"{ke.KEY_EVENT_CHAIN}（事件链）：",
                       True),
        ValidationRule(f"{ke.KEY_EVENT_LOGIC_DIAGNOSIS}.{ke.KEY_CAUSALITY_GAPS}", False, IS_LIST,
                       f"{ke.KEY_CAUSALITY_GAPS}（因果关系缺口）：",
                       True),
        ValidationRule(f"{ke.KEY_EVENT_LOGIC_DIAGNOSIS}.{ke.KEY_INFO_JUMPS}", False, IS_LIST,
                       f"{ke.KEY_INFO_JUMPS}（信息跳转）：",
                       True),
        ValidationRule(f"{ke.KEY_EVENT_LOGIC_DIAGNOSIS}.{ke.KEY_TIMELINE}", False, IS_LIST,
                       f"{ke.KEY_TIMELINE}（时间线）：",
                       True),
        ValidationRule(f"{ke.KEY_EVENT_LOGIC_DIAGNOSIS}.{ke.KEY_TIMELINE_CONFLICTS}", False, IS_LIST,
                       f"{ke.KEY_TIMELINE_CONFLICTS}（时间线冲突）：",
                       True),
        ValidationRule(f"{ke.KEY_EVENT_LOGIC_DIAGNOSIS}.{ke.KEY_FORESHADOWING}", False, IS_LIST,
                       f"{ke.KEY_FORESHADOWING}（铺垫）：",
                       True),
        ValidationRule(f"{ke.KEY_EVENT_LOGIC_DIAGNOSIS}.{ke.KEY_INFO_UNSUPPORTED}", False, IS_LIST,
                       f"{ke.KEY_INFO_UNSUPPORTED}（信息跃迁）：",
                       True)
    ],
    va.VAL_RULE_CHARACTER_CONSISTENCY_DIAGNOSIS: [
        ValidationRule(ke.KEY_CHARACTER_CONSISTENCY_DIAGNOSIS, True, IS_DICT,
                       f"{ke.KEY_CHARACTER_CONSISTENCY_DIAGNOSIS}（角色一致性诊断）：", False),
        ValidationRule(f"{ke.KEY_CHARACTER_CONSISTENCY_DIAGNOSIS}.{ke.KEY_BEHAVIORS}", False, IS_LIST,
                       f"{ke.KEY_BEHAVIORS}（行为）：",
                       True),
        ValidationRule(f"{ke.KEY_CHARACTER_CONSISTENCY_DIAGNOSIS}.{ke.KEY_CONTRADICTIONS}", False, IS_LIST,
                       f"{ke.KEY_CONTRADICTIONS}（矛盾）：",
                       True),
        ValidationRule(f"{ke.KEY_CHARACTER_CONSISTENCY_DIAGNOSIS}.{ke.KEY_MOTIVATION_GAPS}", False, IS_LIST,
                       f"{ke.KEY_MOTIVATION_GAPS}（动机差距）：",
                       True)
    ],
    va.VAL_RULE_DIALOGUE_TONE_DIAGNOSIS: [
        ValidationRule(ke.KEY_DIALOGUE_TONE_DIAGNOSIS, True, IS_DICT, f"{ke.KEY_DIALOGUE_TONE_DIAGNOSIS}（对话语气诊断）：",
                       False),
        ValidationRule(f"{ke.KEY_DIALOGUE_TONE_DIAGNOSIS}.{ke.KEY_DIALOGUE_SEGMENTS}", False, IS_LIST,
                       f"{ke.KEY_DIALOGUE_SEGMENTS}（对话片段）：",
                       True),
        ValidationRule(f"{ke.KEY_DIALOGUE_TONE_DIAGNOSIS}.{ke.KEY_TONE_MISMATCHES}", False, IS_LIST,
                       f"{ke.KEY_TONE_MISMATCHES}（音调不匹配）：",
                       True)
    ],
    va.VAL_RULE_WORLDVIEW_CONSISTENCY_DIAGNOSIS: [
        ValidationRule(ke.KEY_WORLDVIEW_DIAGNOSIS, True, IS_DICT, f"{ke.KEY_WORLDVIEW_DIAGNOSIS}（世界观诊断）：", False),
        ValidationRule(f"{ke.KEY_WORLDVIEW_DIAGNOSIS}.{ke.KEY_WORLDVIEW_ELEMENTS}", False, IS_LIST,
                       f"{ke.KEY_WORLDVIEW_ELEMENTS}（世界观要素）：",
                       True),
        ValidationRule(f"{ke.KEY_WORLDVIEW_DIAGNOSIS}.{ke.KEY_VIOLATIONS}", False, IS_LIST,
                       f"{ke.KEY_VIOLATIONS}（违规）：",
                       True)
    ],
    va.VAL_RULE_STYLE_ALIGNMENT_DIAGNOSIS: [
        ValidationRule(ke.KEY_STYLE_ALIGNMENT_DIAGNOSIS, True, IS_DICT, f"{ke.KEY_STYLE_ALIGNMENT_DIAGNOSIS}（风格倾向诊断）：", False),
        ValidationRule(f"{ke.KEY_STYLE_ALIGNMENT_DIAGNOSIS}.{ke.KEY_STYLE_FEATURES}", False, IS_LIST,
                       f"{ke.KEY_STYLE_FEATURES}（文本风格特征描述）：",
                       True),
        ValidationRule(f"{ke.KEY_STYLE_ALIGNMENT_DIAGNOSIS}.{ke.KEY_STYLE_MISMATCHES}", False, IS_LIST,
                       f"{ke.KEY_STYLE_MISMATCHES}（风格偏离标记及说明）：",
                       True)
    ],

    # 串行 聚合
    va.VAL_RULE_AGGREGATE_DIAGNOSIS: [
        ValidationRule(ke.KEY_FIX_INSTRUCTION, True, IS_DICT, f"{ke.KEY_FIX_INSTRUCTION}（修复方案生成）：", False),
        ValidationRule(f"{ke.KEY_FIX_INSTRUCTION}.{ke.KEY_TASKS}", False, IS_LIST, f"{ke.KEY_TASKS}（任务）：",
                       True),
        ValidationRule(f"{ke.KEY_FIX_INSTRUCTION}.{ke.KEY_AGGREGATION_NOTES}", False, IS_LIST,
                       f"{ke.KEY_AGGREGATION_NOTES}（聚合注释）：",
                       True),

        ValidationRule(f"{ke.KEY_FIX_INSTRUCTION}.{ke.KEY_TASKS}.*.{ke.KEY_PRIORITY}", False, IS_STR,
                       f"{ke.KEY_PRIORITY}（优先级）：",
                       True),
        ValidationRule(f"{ke.KEY_FIX_INSTRUCTION}.{ke.KEY_TASKS}.*.{ke.KEY_CATEGORY}", False,
                       IS_STR,
                       f"{ke.KEY_CATEGORY}（分类）：",
                       True),
        ValidationRule(f"{ke.KEY_FIX_INSTRUCTION}.{ke.KEY_TASKS}.*.{ke.KEY_TARGET_ISSUE}", False,
                       IS_STR,
                       f"{ke.KEY_TARGET_ISSUE}（目标问题）：",
                       True),
        ValidationRule(f"{ke.KEY_FIX_INSTRUCTION}.{ke.KEY_TASKS}.*.{ke.KEY_ORIGINAL_FRAGMENT}", False,
                       IS_STR,
                       f"{ke.KEY_ORIGINAL_FRAGMENT}（原始片段）：",
                       True),
        ValidationRule(f"{ke.KEY_FIX_INSTRUCTION}.{ke.KEY_TASKS}.*.{ke.KEY_SUGGESTED_ACTION}", False,
                       IS_STR,
                       f"{ke.KEY_SUGGESTED_ACTION}（建议的行动）：",
                       True),
    ],

    # 串行 打磨
    va.VAL_RULE_CONSISTENCY_FIX: [
            ValidationRule(ke.KEY_CONSISTENCY_FIX, True, IS_DICT, f"{ke.KEY_CONSISTENCY_FIX}（叙事润色）：", False),
            ValidationRule(f"{ke.KEY_CONSISTENCY_FIX}.{ke.KEY_CLEANED_TEXT}", True, IS_STR,
                           f"{ke.KEY_CLEANED_TEXT}（清洗后文本）：", True),
            ValidationRule(f"{ke.KEY_CONSISTENCY_FIX}.{ke.KEY_ISSUES_FIXED}", False, IS_LIST,
                           f"{ke.KEY_ISSUES_FIXED}（修正记录）：", True),
        ],
    va.VAL_RULE_STRUCTURE_TRANSITION_POLISH: [
        ValidationRule(ke.KEY_STRUCTURE_FIX, True, IS_DICT, f"{ke.KEY_STRUCTURE_FIX}（结构润色）：", False),
        ValidationRule(f"{ke.KEY_STRUCTURE_FIX}.{ke.KEY_CLEANED_TEXT}", True, IS_STR,
                       f"{ke.KEY_CLEANED_TEXT}（清洗后文本）：", True),
        ValidationRule(f"{ke.KEY_STRUCTURE_FIX}.{ke.KEY_ISSUES_FIXED}", False, IS_LIST,
                       f"{ke.KEY_ISSUES_FIXED}（修正记录）：", True),
    ],
    va.VAL_RULE_RHETORIC_SYNTAX_POLISH: [
        ValidationRule(ke.KEY_RHETORIC_SYNTAX_FIX, True, IS_DICT, f"{ke.KEY_RHETORIC_SYNTAX_FIX}（文辞润色）：", False),
        ValidationRule(f"{ke.KEY_RHETORIC_SYNTAX_FIX}.{ke.KEY_CLEANED_TEXT}", True, IS_STR,
                       f"{ke.KEY_CLEANED_TEXT}（清洗后文本）：", True),
        ValidationRule(f"{ke.KEY_RHETORIC_SYNTAX_FIX}.{ke.KEY_ISSUES_FIXED}", False, IS_LIST,
                       f"{ke.KEY_ISSUES_FIXED}（修正记录）：", True),
    ],

    # 串行 增强
    va.VAL_RULE_CREATIVE_ENHANCE: [
        ValidationRule(ke.KEY_CREATIVE_ENHANCE, True, IS_DICT, f"{ke.KEY_CREATIVE_ENHANCE}（创意增强）：", False),
        ValidationRule(f"{ke.KEY_CREATIVE_ENHANCE}.{ke.KEY_CLEANED_TEXT}", True, IS_STR,
                       f"{ke.KEY_CLEANED_TEXT}（清洗后文本）：", True),
        ValidationRule(f"{ke.KEY_CREATIVE_ENHANCE}.{ke.KEY_ISSUES_FIXED}", False, IS_LIST,
                       f"{ke.KEY_ISSUES_FIXED}（修正记录）：", True),
    ],
    va.VAL_RULE_CANDIDATE_GENERATION: [
        ValidationRule(ke.KEY_CANDIDATES_OUTPUT, True, IS_DICT, f"{ke.KEY_CANDIDATES_OUTPUT}（多候选版本生成）：", False),
        ValidationRule(f"{ke.KEY_CANDIDATES_OUTPUT}.{ke.KEY_CANDIDATES}", True, IS_LIST,
                       f"{ke.KEY_CANDIDATES}（候选列表）：", True),
    ],
    va.VAL_RULE_INTELLIGENT_SELECTION: [
        ValidationRule(ke.KEY_SELECTION_RESULT, True, IS_DICT, f"{ke.KEY_SELECTION_RESULT}（版本选择）：", False),
        ValidationRule(f"{ke.KEY_SELECTION_RESULT}.{ke.KEY_SELECTED_INDEX}", True, IS_INT,
                       f"{ke.KEY_SELECTED_INDEX}（选择结果索引）：", True),
        ValidationRule(f"{ke.KEY_SELECTION_RESULT}.{ke.KEY_REASON}", False, IS_STR,
                       f"{ke.KEY_REASON}（选择结果理由）：", True),
    ],
    va.VAL_RULE_FIDELITY_REPAIR: [
        ValidationRule(ke.KEY_FIDELITY_REPAIR, True, IS_DICT, f"{ke.KEY_FIDELITY_REPAIR}（保真修复）：", False),
        ValidationRule(f"{ke.KEY_FIDELITY_REPAIR}.{ke.KEY_CLEANED_TEXT}", True, IS_STR,
                       f"{ke.KEY_CLEANED_TEXT}（清洗后文本）：", True),
        ValidationRule(f"{ke.KEY_FIDELITY_REPAIR}.{ke.KEY_ISSUES_FIXED}", False, IS_LIST,
                       f"{ke.KEY_ISSUES_FIXED}（修正记录）：", True),
    ],
}

VAL_METACOGNITION_CHECK_RULES: Dict[str, List[ValidationRule]] = {
    va.VAL_INTERNAL_DAO_INSIGHT: [
        ValidationRule(ke.KEY_DAO, True, IS_DICT, f"{ke.KEY_DAO}（道之洞见）：", False),
        ValidationRule(f"{ke.KEY_DAO}.{ke.KEY_CONTENT}", True, IS_STR, f"{ke.KEY_CONTENT}（核心直觉洞见与方向预判）：",
                       True),
        ValidationRule(f"{ke.KEY_DAO}.{ke.KEY_CONFIDENCE}", False, IS_FLOAT,
                       f"{ke.KEY_CONFIDENCE}（自我置信度）：", True)
    ],

    va.VAL_INTERNAL_DIVINE_EYE_INTUITION: [
        ValidationRule(ke.KEY_DIVINE_EYE, True, IS_DICT, f"{ke.KEY_DIVINE_EYE}（上帝之眼）：", False),
        ValidationRule(f"{ke.KEY_DIVINE_EYE}.{ke.KEY_STRATEGY}", True, IS_STR, f"{ke.KEY_STRATEGY}（唯一战略码）：",
                       True),
        ValidationRule(f"{ke.KEY_DIVINE_EYE}.{ke.KEY_CONTENT}", True, IS_STR, f"{ke.KEY_CONTENT}（精炼的研判文本）：",
                       True),
        ValidationRule(f"{ke.KEY_DIVINE_EYE}.{ke.KEY_CONFIDENCE}", False, IS_FLOAT,
                       f"{ke.KEY_CONFIDENCE}（自我置信度）：", True),
        ValidationRule(f"{ke.KEY_DIVINE_EYE}.{ke.KEY_REQUESTED_LEVEL}", False, IS_INT,
                       f"{ke.KEY_REQUESTED_LEVEL}（需要请求的数据层级）：", True),
        ValidationRule(f"{ke.KEY_DIVINE_EYE}.{ke.KEY_ABORT_RECOMMENDATION}", False, IS_BOOL,
                       f"{ke.KEY_ABORT_RECOMMENDATION}（是否建议终止）：", True),
        ValidationRule(f"{ke.KEY_DIVINE_EYE}.{ke.KEY_ABORT_REASON}", False, IS_STR,
                       f"{ke.KEY_ABORT_REASON}（终止理由）：", True)
    ],

    va.VAL_INTERNAL_DIVINE_HAND_VERDICT: [
        ValidationRule(ke.KEY_DIVINE_HAND, True, IS_DICT, f"{ke.KEY_DIVINE_HAND}（上帝之手）：", False),
        ValidationRule(f"{ke.KEY_DIVINE_HAND}.{ke.KEY_DECISION}", True, IS_STR, f"{ke.KEY_DECISION}（唯一裁决码）：",
                       True),
        ValidationRule(f"{ke.KEY_DIVINE_HAND}.{ke.KEY_CONTENT}", True, IS_STR, f"{ke.KEY_CONTENT}（裁决理由与综合分析）：",
                       True),
        ValidationRule(f"{ke.KEY_DIVINE_HAND}.{ke.KEY_CONFIDENCE}", False, IS_FLOAT,
                       f"{ke.KEY_CONFIDENCE}（自我置信度）：", True),
        ValidationRule(f"{ke.KEY_DIVINE_HAND}.{ke.KEY_PRIORITY_ISSUES}", False, IS_LIST,
                       f"{ke.KEY_PRIORITY_ISSUES}（问题清单）：", True),

        ValidationRule(f"{ke.KEY_DIVINE_HAND}.{ke.KEY_PRIORITY_ISSUES}.*.{ke.KEY_PRIORITY}", False, IS_STR,
                       f"{ke.KEY_PRIORITY}（问题层级）：", True),
        ValidationRule(f"{ke.KEY_DIVINE_HAND}.{ke.KEY_PRIORITY_ISSUES}.*.{ke.KEY_CATEGORY}", False, IS_STR,
                       f"{ke.KEY_CATEGORY}（问题类别）：", True),
        ValidationRule(f"{ke.KEY_DIVINE_HAND}.{ke.KEY_PRIORITY_ISSUES}.*.{ke.KEY_ISSUE}", False, IS_STR,
                       f"{ke.KEY_ISSUE}（问题描述）：", True),
        ValidationRule(f"{ke.KEY_DIVINE_HAND}.{ke.KEY_PRIORITY_ISSUES}.*.{ke.KEY_SUGGESTED_FIX}", False, IS_STR,
                       f"{ke.KEY_SUGGESTED_FIX}（修复方向）：", True)
    ],

    va.VAL_INTERNAL_RATIONAL_TYRANT_ANALYSIS: [
        ValidationRule(ke.KEY_ANALYSIS_TURN, True, IS_DICT, f"{ke.KEY_ANALYSIS_TURN}（理性暴君）：", False),
        ValidationRule(f"{ke.KEY_ANALYSIS_TURN}.{ke.KEY_CONTENT}", True, IS_STR, f"{ke.KEY_CONTENT}（逻辑分析内容）：",
                       True),
        ValidationRule(f"{ke.KEY_ANALYSIS_TURN}.{ke.KEY_CONFIDENCE}", False, IS_FLOAT,
                       f"{ke.KEY_CONFIDENCE}（自我置信度）：", True)
    ],

    va.VAL_INTERNAL_EMOTIONAL_VIRGIN_MARY_ANALYSIS: [
        ValidationRule(ke.KEY_ANALYSIS_TURN, True, IS_DICT, f"{ke.KEY_ANALYSIS_TURN}（感性圣母）：", False),
        ValidationRule(f"{ke.KEY_ANALYSIS_TURN}.{ke.KEY_CONTENT}", True, IS_STR, f"{ke.KEY_CONTENT}（情感分析内容）：",
                       True),
        ValidationRule(f"{ke.KEY_ANALYSIS_TURN}.{ke.KEY_CONFIDENCE}", False, IS_FLOAT,
                       f"{ke.KEY_CONFIDENCE}（自我置信度）：", True)
    ],

    va.VAL_INTERNAL_METACOGNITION_SIGNATURE: [
        ValidationRule(ke.KEY_METACOGNITION_SIGNATURE, True, IS_DICT, f"{ke.KEY_METACOGNITION_SIGNATURE}（语义签名）：", False),
        ValidationRule(f"{ke.KEY_METACOGNITION_SIGNATURE}.{ke.KEY_SIGNATURE}", True, IS_STR, f"{ke.KEY_SIGNATURE}（签名）：",
                       True)
    ],
}
