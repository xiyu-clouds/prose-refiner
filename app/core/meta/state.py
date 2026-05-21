from typing import TypedDict, Literal, List, Optional, Dict, Any
from app.common.enums import StrategyCode, DecisionType


class DataPayload(TypedDict, total=False):
    """
    运行时数据载荷。
    """
    content: str  # 按当前层级组装好的自然语言文本，直接注入 Prompt
    level: int  # 当前已加载的最高数据层级（0-2）
    data_store: Dict[int, Any]  # 已加载的各层级数据缓存，key=层级编号


class DaoInsightRecord(TypedDict):
    """
    道节点的操作产出记录。
    每次智能节点执行前调用道，产出一份直觉假设并存入此记录。
    """
    timestamp: float         # 调用时间戳（用于审计执行顺序）
    caller: str              # 调用方节点标识（divine_eye / divine_hand / rational_tyrant / emotional_mother）
    content: str             # 道基于当前状态产出的直觉假设与价值过滤结果
    confidence: float        # 道对本次直觉的自我置信度评估


class AnalysisTurn(TypedDict):
    """
    辩论发言记录。
    理性暴君和感性圣母交替发言，各自基于道的直觉和当前数据，
    按需调用插件进行深度验证，产出多视角分析结果。
    """
    timestamp: float                          # 发言时间戳
    role: Literal["理性暴君", "感性圣母"]        # 分析视角角色
    content: str                              # 本轮发言的核心观点与分析内容
    confidence: float                         # 本角色对本次分析的自我置信度
    plugin_result: Optional[Dict[str, Any]]   # 本轮调用的插件验证报告（由辩论子图内部管理）


class DivineEyeInsight(TypedDict):
    """
    上帝之眼觉知报告。
    基于道的直觉和当前数据，对文本优化方向做出预判，
    决定是否需要加载更高数据层级、进入辩论、交付裁决或直接结束。
    """
    timestamp: float                     # 觉知产出时间戳
    strategy: StrategyCode               # 建议的路由策略码（驱动下一步流向）
    content: str                         # 对文本可能存在问题的初步假设列表
    confidence: float                    # 上帝之眼对本次预分析的自我置信度
    requested_level: int                 # 需加载的最低数据层级（若当前数据不足以决策）
    abort_recommendation: bool           # 是否建议提前终止（文本优化空间不大）
    abort_reason: Optional[str]          # 终止原因说明


class DivineHandVerdict(TypedDict):
    """
    上帝之手裁决报告。
    聚合所有前序分析（道的直觉、上帝之眼预分析、辩论结果），
    输出按优先级排序的问题清单，为修复节点提供执行依据。
    """
    timestamp: float                       # 裁决产出时间戳
    decision: DecisionType                 # 裁决类型码（驱动下一步流向）
    content: str                           # 裁决理由与综合分析说明
    priority_issues: List[Dict[str, Any]]  # 按优先级排序的问题清单，格式: [{"priority": "P0", "category": "...", "issue": "...", "suggested_fix": "..."}]
    confidence: float                      # 上帝之手对本次裁决的自我置信度


class TraceNode(TypedDict):
    """
    执行轨迹节点。
    以有序链表形式记录元认知引擎的完整决策路径，
    用于可视化回溯和流程审计。
    """
    seq_id: int                     # 顺序标识，从 1 递增
    node_id: str                    # 物理节点 ID
    prev_node_id: Optional[str]     # 上一个节点 ID（用于回溯决策来源）
    next_node_id: Optional[str]     # 下一个节点 ID（用于前瞻决策去向）
    status: str                     # 节点执行状态快照


class MetacognitiveOptimizerState(TypedDict, total=False):
    """
    元认知文本优化器主状态。
    贯穿整个文本优化流程的唯一状态对象，承载所有阶段的分析、决策与修复结果。
    各节点通过 immutable 更新函数 _update_state() 写入，保持状态的不可变性。
    """

    # ==========================
    # A. 核心身份
    # ==========================
    id: str  # 任务唯一 ID，贯穿全流程，用于数据库关联和报告生成

    # ==========================
    # B. 数据仓库与执行轨迹
    # ==========================
    initial_snapshot: Dict[str, Any]      # 任务启动时的原始种子数据（用户注入的角色设定、世界观、风格偏好等）
    current_data: DataPayload             # 当前运行时数据载荷，按需从 SQLite 加载并组装
    execution_trace: List[TraceNode]      # 全链路执行轨迹链表，记录每个节点的入口、状态和出口

    # ==========================
    # C. 上帝双相报告
    # ==========================
    eye_reports: List[DivineEyeInsight]   # 上帝之眼历次觉知报告，驱动路由决策
    hand_reports: List[DivineHandVerdict]  # 上帝之手历次裁决报告，产出问题清单

    # ==========================
    # D. 深度分析与价值过滤
    # ==========================
    analysis_reports: List[AnalysisTurn]      # 辩论子图产出的多视角分析记录（理性暴君与感性圣母交替发言）
    dao_reports: List[DaoInsightRecord]       # 道节点全量操作记录，完整保留每次调用道的产出

    # ==========================
    # E. 资源控制与外部交互
    # ==========================
    max_llm_calls: int                   # 最大允许 LLM 调用次数（预算上限）
    llm_calls_count: int                 # 已使用 LLM 调用次数（计数器，每次 LLM 调用后 +1）
    expires_at: float                    # 任务超时失效时间戳（Unix 时间戳）
    max_iterations: int  # 最大允许的主循环次数（（eye → load_data 循环）
    max_debate_rounds: int  # 上帝之眼触发辩论的最大次数
    max_chars_per_turn: int  # 单轮发言/报告最大字符数（截断阈值）
    max_debate_turns_to_inject: int  # 辩论记录最大注入轮次（最近 N 轮）
    max_issues_to_display: int  # 上帝之手报告中最多展示的问题条目数
    user_clarification: Optional[str]  # 用户注入的澄清或补充信息

    # ==========================
    # F. 最终产物
    # ==========================
    status: str                          # 当前任务状态码，用于路由兜底和最终状态判断
    message: Optional[str]               # 状态附加消息，记录当前节点的简要说明
    metacognition_signature: Optional[str]  # 生成的元认知语义指纹，标识本次分析的唯一输出

    # ==========================
    # G. 修复与验证
    # ==========================
    revised_text: Optional[str]          # 修复后的最终文本，由修复节点产出
    revision_fix_records: List[Dict[str, Any]]  # 修复后对文本进行诊断的验证记录
