from typing import Any
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from app.core.collector.execution_context import ExecutionCollector
from app.core.engine.executor import LLMExecutor
from app.core.meta.graphs.subgraphs.debate import build_debate_subgraph
from app.core.meta.nodes.data_loader import data_loader_node
from app.core.meta.nodes.debate import rational_tyrant_analyze, emotional_mother_analyze
from app.core.meta.nodes.divine_eye import divine_eye_node
from app.core.meta.nodes.divine_hand import divine_hand_node
from app.core.meta.nodes.persist import persist_result
from app.core.meta.nodes.revise_and_diagnose import revise_and_diagnose_node
from app.core.meta.nodes.signature import generate_signature
from app.core.meta.nodes.wait_human import wait_human_node
from app.core.meta.routing import route_after_hand, route_after_eye
from app.core.meta.state import MetacognitiveOptimizerState
from app.common import values as va
from app.common import enums as en
from app.core.meta.utils import make_async_node, make_async_node_no_args, make_async_node_with_dao
from app.utils.logger import LoggerManager as logger

CHINESE_NAME = "元认知主图"


def build_and_compile_metacognition_graph(executor: LLMExecutor, collector: ExecutionCollector) -> Any:
    """
    构建并编译元认知文本优化主图。

    整体流转流程（含循环回路）：
    1. START → 上帝之眼（divine_eye）
    2. 上帝之眼 条件路由：
       - 数据不足 → 数据加载（load_data）→ 回到上帝之眼（**循环**）
       - 需辩论 → 辩论子图（debate_subgraph）→ 回到上帝之眼（**循环**）
       - 仅理性 → 理性暴君单节点（rational_single）→ 回到上帝之眼（**循环**）
       - 仅感性 → 感性圣母单节点（emotional_single）→ 回到上帝之眼（**循环**）
       - 信息充足 → 上帝之手（divine_hand）
       - 文本完美 → 语义签名（generate_metacognition_signature）
       - 无法决策 → 人工介入（wait_human）
    3. 上帝之手 条件路由：
       - 需修复 → 修复与验证（revise_and_diagnose）→ 语义签名
       - 接受当前 → 语义签名
       - 继续辩论 → 辩论子图（**回退循环**）
       - 深度理性分析 → 理性暴君单节点（**回退循环**）
       - 深度感性分析 → 感性圣母单节点（**回退循环**）
       - 回退上帝之眼 → 上帝之眼（**回退循环**）
       - 请求用户澄清 → 人工介入
       - 资源耗尽/异常 → 语义签名 或 人工介入
    4. 语义签名 → 持久化（persist_metacognition_result）→ END
    5. 人工介入 → 挂起 → 恢复 （或者挂起超时 语义签名 → 持久化 → END）
    """
    graph = StateGraph(MetacognitiveOptimizerState)

    # 编译子图
    debate_subgraph_compiled = build_debate_subgraph(executor, collector)

    # ==============================
    # 1. 节点注册
    # ==============================
    NODE_IMPLEMENTATIONS = {
        va.VAL_NODE_DIVINE_EYE: make_async_node_with_dao(divine_eye_node, executor, collector, va.VAL_EYE_OF_GOD),
        va.VAL_NODE_LOAD_DATA: make_async_node_no_args(data_loader_node),
        va.VAL_NODE_DIVINE_HAND: make_async_node_with_dao(divine_hand_node, executor, collector, va.VAL_HAND_OF_GOD),
        va.VAL_NODE_RATIONAL_SINGLE: make_async_node_with_dao(rational_tyrant_analyze, executor, collector, va.VAL_RATIONAL_TYRANT),
        va.VAL_NODE_EMOTIONAL_SINGLE: make_async_node_with_dao(emotional_mother_analyze, executor, collector, va.VAL_EMOTIONAL_VIRGIN_MARY),
        va.VAL_NODE_DEBATE_SUBGRAPH: debate_subgraph_compiled,
        va.VAL_NODE_REVISE_AND_DIAGNOSE: make_async_node(revise_and_diagnose_node, executor, collector),
        va.VAL_NODE_WAIT_HUMAN: make_async_node_no_args(wait_human_node),
        va.VAL_NODE_GENERATE_SIGNATURE: make_async_node(generate_signature, executor, collector),
        va.VAL_NODE_PERSIST_RESULT: make_async_node(persist_result, executor, collector),
    }

    missing = set(en.VAL_VALID_NODE_IDS) - set(NODE_IMPLEMENTATIONS.keys())
    if missing:
        raise ValueError(f"🚨 致命缺失：常量 VALID_NODE_IDS 定义的节点 {missing} 未实现！")

    for node_id, func in NODE_IMPLEMENTATIONS.items():
        graph.add_node(node_id, func)

    # ==============================
    # 2. 固定拓扑
    # ==============================
    # 起点 → 上帝之眼
    graph.add_edge(START, va.VAL_NODE_DIVINE_EYE)

    # 数据加载后返回上帝之眼重新审视
    graph.add_edge(va.VAL_NODE_LOAD_DATA, va.VAL_NODE_DIVINE_EYE)

    # 辩论子图 / 单节点执行完后统一先回上帝之眼，修正分析后再由眼路由
    for exec_node in [va.VAL_NODE_DEBATE_SUBGRAPH, va.VAL_NODE_RATIONAL_SINGLE, va.VAL_NODE_EMOTIONAL_SINGLE]:
        graph.add_edge(exec_node, va.VAL_NODE_DIVINE_EYE)

    # 修复与验证完成后进入语义签名
    graph.add_edge(va.VAL_NODE_REVISE_AND_DIAGNOSE, va.VAL_NODE_GENERATE_SIGNATURE)

    # 人工介入后回到上帝之手，重新裁决
    graph.add_edge(va.VAL_NODE_WAIT_HUMAN, va.VAL_NODE_DIVINE_HAND)

    # 语义签名 → 持久化 → END
    graph.add_edge(va.VAL_NODE_GENERATE_SIGNATURE, va.VAL_NODE_PERSIST_RESULT)
    graph.add_edge(va.VAL_NODE_PERSIST_RESULT, END)

    # ==============================
    # 3. 条件边
    # ==============================
    identity_routes_map = {node_id: node_id for node_id in en.VAL_VALID_NODE_IDS}

    graph.add_conditional_edges(va.VAL_NODE_DIVINE_EYE, route_after_eye, identity_routes_map)
    graph.add_conditional_edges(va.VAL_NODE_DIVINE_HAND, route_after_hand, identity_routes_map)

    logger.info(f"📊 图谱概览: {len(NODE_IMPLEMENTATIONS)} 个节点 | 路由策略: 状态兜底，眼/手动态决策。", module_name=CHINESE_NAME)
    logger.info(f"👁️ {va.VAL_EYE_OF_GOD}: 基于战略码动态调度 -> {len(en.VAL_VALID_NODE_IDS)} 个潜在目标", module_name=CHINESE_NAME)
    logger.info(f"🤚 {va.VAL_HAND_OF_GOD}: 基于决策码动态裁决 -> {len(en.VAL_VALID_NODE_IDS)} 个潜在目标", module_name=CHINESE_NAME)
    logger.info(f"🔒 安全校验: 所有路由已绑定 VALID_NODE_IDS 白名单", module_name=CHINESE_NAME)
    return graph.compile()
