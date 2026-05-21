from typing import cast
from app.common.enums import NodeStatusLiteral, TextOptimizationLevel
from app.utils.logger import LoggerManager as logger
from app.common import keys as ke
from app.common import enums as en
from app.common import values as va
from app.core.meta.state import MetacognitiveOptimizerState


CHINESE_NAME = "元认知路由"


# ==============================================================================
# 通用元路由引擎
# ==============================================================================
def route_with_intelligence(
        state: MetacognitiveOptimizerState,
        context: en.RoutingContext
) -> str:
    current_status = cast(NodeStatusLiteral, state.get(ke.KEY_STATUS, va.VAL_STATUS_RUNNING))  # type: ignore
    records = state.get(context.state_key, [])  # type: ignore

    # --- 第一道防线：状态硬规则拦截 ---
    if current_status == va.VAL_STATUS_SUSPENDED:
        logger.debug(f"🛑 [{context.name}·状态拦截] 挂起状态 [{current_status}] 强制导向人工介入。", module_name=CHINESE_NAME)
        return va.VAL_NODE_WAIT_HUMAN

    # --- 第二道防线：智能决策优先（有有效裁决就信任它） ---
    if records:
        last_rec = records[-1]
        raw_code = last_rec.get(context.code_field)

        if raw_code and raw_code in context.valid_codes:
            config = context.config_map.get(raw_code)
            if config:
                target = config.get(ke.KEY_NEXT_STEP)

                # ========== 辩论节点拦截 ==========
                if target in {va.VAL_NODE_RATIONAL_SINGLE, va.VAL_NODE_EMOTIONAL_SINGLE, va.VAL_NODE_DEBATE_SUBGRAPH}:
                    analysis_reports = state.get(ke.KEY_ANALYSIS_REPORTS, [])  # type: ignore
                    total_turns = len(analysis_reports)
                    max_rounds = state.get(ke.KEY_MAX_DEBATE_ROUNDS, 10)  # type: ignore
                    if total_turns >= max_rounds:
                        logger.warning(f"辩论发言已达上限 {max_rounds}，强制转向上帝之手", module_name=CHINESE_NAME)
                        return va.VAL_NODE_DIVINE_HAND

                # ========== 数据加载节点拦截 ==========
                if target == va.VAL_NODE_LOAD_DATA:
                    current_data = state.get(ke.KEY_CURRENT_DATA, {})  # type: ignore
                    current_level = current_data.get(ke.KEY_LEVEL, 0)
                    if current_level >= TextOptimizationLevel.MAX_LEVEL:
                        logger.warning(f"数据层级已达上限 {TextOptimizationLevel.MAX_LEVEL}，无需继续加载，强制转向上帝之手", module_name=CHINESE_NAME)
                        return va.VAL_NODE_DIVINE_HAND

                if target and target in en.VAL_VALID_NODE_IDS:
                    # 安全策略修正保留
                    if raw_code == context.safety_code and target != context.safety_target:
                        logger.warning(
                            f"⚠️ [{context.name}·安全修正] 代码 [{raw_code}] 指向 [{target}]，修正为 [{context.safety_target}]。", module_name=CHINESE_NAME)
                        return context.safety_target
                    logger.debug(f"🔀 [{context.name}·决策优先] 代码:{raw_code} -> {target}", module_name=CHINESE_NAME)
                    return target

    # --- 第三道防线：无有效裁决时，走状态硬规则 ---
    if current_status in va.VAL_TERMINATION_STATE:
        logger.debug(f"🛑 [{context.name}·状态拦截] 终态 [{current_status}] 强制导向签名生成。", module_name=CHINESE_NAME)
        return va.VAL_NODE_GENERATE_SIGNATURE

    # --- 第四道防线：状态基准路由 ---
    baseline_node = en.get_next_node_from_status(current_status)
    if baseline_node and baseline_node in en.VAL_VALID_NODE_IDS:
        return baseline_node

    # --- 最终兜底 ---
    logger.critical(f"💥 [{context.name}·兜底] 无可路由节点，回退上帝之眼。", module_name=CHINESE_NAME)
    return va.VAL_NODE_DIVINE_EYE


# ==============================================================================
# 上帝之眼后去哪？
# ==============================================================================
EYE_CONTEXT = en.RoutingContext(
    name=va.VAL_EYE_OF_GOD,
    state_key=ke.KEY_EYE_REPORTS,
    code_field=ke.KEY_STRATEGY,
    valid_codes=en.VAL_VALID_STRATEGY,
    config_map=en.VAL_STRATEGY_CONFIGS,
    safety_code=va.VAL_STRATEGY_REQUEST_HUMAN_IN_LOOP,
    safety_target=va.VAL_NODE_WAIT_HUMAN,
    module_name=CHINESE_NAME
)


def route_after_eye(state: MetacognitiveOptimizerState) -> str:
    """上帝之眼路由决策器 (调用通用引擎)"""
    return route_with_intelligence(state, EYE_CONTEXT)


# ==============================================================================
# 上帝之手后去哪？ (双重校验)
# ==============================================================================
HAND_CONTEXT = en.RoutingContext(
    name=va.VAL_HAND_OF_GOD,
    state_key=ke.KEY_HAND_REPORTS,
    code_field=ke.KEY_DECISION,
    valid_codes=en.VAL_VALID_DECISIONS,
    config_map=en.VAL_DECISION_CONFIGS,
    safety_code=va.VAL_DECISION_TERMINATE_BY_ERROR,
    safety_target=va.VAL_NODE_WAIT_HUMAN,
    module_name=CHINESE_NAME
)


def route_after_hand(state: MetacognitiveOptimizerState) -> str:
    """上帝之手路由决策器 (调用通用引擎)"""
    return route_with_intelligence(state, HAND_CONTEXT)
