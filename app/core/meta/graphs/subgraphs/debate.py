from typing import Any
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from app.common import values as va
from app.common import keys as ke
from app.core.meta.nodes.debate import rational_tyrant_analyze, emotional_mother_analyze
from app.core.meta.state import MetacognitiveOptimizerState
from app.core.collector.execution_context import ExecutionCollector
from app.core.engine.executor import LLMExecutor
from app.core.meta.utils import make_async_node_with_dao
from app.utils.logger import LoggerManager as logger
from app.common import enums as en


CHINESE_NAME = "元认知辩论子图"


def build_debate_subgraph(executor: LLMExecutor, collector: ExecutionCollector) -> Any:
    """
    构建辩论子图。

    职责：执行多轮理性暴君与感性圣母交替辩论，深度分析文本。
    辩论轮次由上帝之眼战略配置中的 max_rounds 控制。
    辩论结束后直接返回主图，由主图的上帝之眼接手修正分析。

    内部流转：
    START → 理性暴君 / 感性圣母（交替发言）→ END
    """
    sub_graph = StateGraph(MetacognitiveOptimizerState)

    # 只注册两个辩论节点
    sub_graph.add_node(va.VAL_NODE_RATIONAL_SINGLE,
                       make_async_node_with_dao(rational_tyrant_analyze, executor, collector,
                                                va.VAL_RATIONAL_TYRANT, va.VAL_STATUS_GOTO_EMOTIONAL_SINGLE))
    sub_graph.add_node(va.VAL_NODE_EMOTIONAL_SINGLE,
                       make_async_node_with_dao(emotional_mother_analyze, executor, collector,
                                                va.VAL_EMOTIONAL_VIRGIN_MARY, va.VAL_STATUS_GOTO_RATIONAL_SINGLE))

    def get_starting_speaker(state: MetacognitiveOptimizerState) -> str:
        """
        确定辩论的启动角色。
        默认由理性暴君先发言，若上帝之手明确要求特定角色深度分析则优先响应。
        """
        hand_reports = state.get(ke.KEY_HAND_REPORTS, [])  # type: ignore
        if hand_reports:
            last_decision = hand_reports[-1].get(ke.KEY_DECISION, "")
            if last_decision == va.VAL_DECISION_DEEP_ANALYSIS_EMOTIONAL:
                return va.VAL_NODE_EMOTIONAL_SINGLE
        # 默认理性暴君先发言
        return va.VAL_NODE_RATIONAL_SINGLE

    def route_after_speech(state: MetacognitiveOptimizerState) -> str:
        """
        每轮发言后决定：继续辩论（切换角色）还是结束子图。
        轮次限制从上帝之眼的最新战略配置中获取。
        """
        analysis_log = state.get(ke.KEY_ANALYSIS_REPORTS, [])  # type: ignore
        current_turn_count = len(analysis_log)  # type: ignore

        # 从上帝之眼战略配置中获取最大轮次
        eye_reports = state.get(ke.KEY_EYE_REPORTS, [])  # type: ignore
        max_rounds = 2  # 默认保底
        if eye_reports:
            last_strategy = eye_reports[-1].get(ke.KEY_STRATEGY, "")
            strategy_cfg = en.VAL_STRATEGY_CONFIGS.get(last_strategy, {})
            max_rounds = strategy_cfg.get(ke.KEY_MAX_ROUNDS, 2)

        max_speaker_turns = max_rounds * 2

        if current_turn_count >= max_speaker_turns:
            logger.info(
                f"🏁 [子图] 辩论达到上限，返回主图。",
                module_name=CHINESE_NAME,
            )
            return END

        # 切换角色：理性暴君 ↔ 感性圣母
        last_role = analysis_log[-1].get(ke.KEY_ROLE, "") if analysis_log else ""  # type: ignore
        if last_role == va.VAL_RATIONAL_TYRANT:
            return va.VAL_NODE_EMOTIONAL_SINGLE
        return va.VAL_NODE_RATIONAL_SINGLE

    # 条件边：起点分发
    sub_graph.add_conditional_edges(
        START,
        get_starting_speaker,
        {
            va.VAL_NODE_RATIONAL_SINGLE: va.VAL_NODE_RATIONAL_SINGLE,
            va.VAL_NODE_EMOTIONAL_SINGLE: va.VAL_NODE_EMOTIONAL_SINGLE,
        },
    )

    # 条件边：每轮发言后路由
    debate_routes = {
        va.VAL_NODE_RATIONAL_SINGLE: va.VAL_NODE_RATIONAL_SINGLE,
        va.VAL_NODE_EMOTIONAL_SINGLE: va.VAL_NODE_EMOTIONAL_SINGLE,
        END: END,
    }
    sub_graph.add_conditional_edges(va.VAL_NODE_RATIONAL_SINGLE, route_after_speech, debate_routes)
    sub_graph.add_conditional_edges(va.VAL_NODE_EMOTIONAL_SINGLE, route_after_speech, debate_routes)

    logger.info(f"📊 [子图] 辩论子图已构建 | 最大轮次由上帝之眼战略配置控制。", module_name=CHINESE_NAME)
    return sub_graph.compile()
