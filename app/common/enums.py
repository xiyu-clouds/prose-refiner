"""
🏛️ 领域常量类与类型定义 (Domain Constants & Types)
基于 values.py 构建逻辑类，并动态生成 Literal 类型以消除警告。
"""
from enum import Enum
from typing import Literal, List, NamedTuple, Any, Dict
from app.common import keys as ke
from pydantic import BaseModel
from app.core.validators.data_validator import IS_LIST, IS_STR, IS_DICT
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
        logger.warning(f"常量类 {cls.__name__} 未提取到有效字符串常量", module_name=CHINESE_NAME)

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


# ======================================================================
# 🏷️ 校验规则
# ======================================================================

VAL_STEP_CHECK_RULES: Dict[str, List[ValidationRule]] = {
    # 创作设定提取
    "extract_session_memory": [
        ValidationRule("extract_session_memory", True, IS_DICT, "extract_session_memory（会话记忆提取顶层）：", False),
        ValidationRule("extract_session_memory.memories", False, IS_LIST, "memories（记忆列表）：", True),
    ],

    # 图像提示词优化
    "image_prompt_refine": [
        ValidationRule("image_prompt_refine", True, IS_DICT, "image_prompt_refine（图像提示词优化顶层）：", False),
        ValidationRule("image_prompt_refine.prompt_text", True, IS_STR, "prompt_text（图像生成提示词）：", True),
    ],

    # 全局剧情设计（谋篇页输出）
    "global_plot_design": [
        ValidationRule("global_plot_design", True, IS_DICT, "global_plot_design（全局剧情设计顶层）：", False),
        ValidationRule("global_plot_design.plot", True, IS_STR, "plot（全局剧情描述）：", True),
        ValidationRule("global_plot_design.summary", True, IS_STR, "summary（全局剧情摘要）：", True),
    ],

    # 卷纲剧情设计
    "volume_plot_design": [
        ValidationRule("volume_plot_design", True, IS_DICT, "volume_plot_design（卷纲剧情设计顶层）：", False),
        ValidationRule("volume_plot_design.plot", True, IS_STR, "plot（卷纲剧情描述）：", True),
        ValidationRule("volume_plot_design.summary", True, IS_STR, "summary（卷纲剧情摘要）：", True),
    ],

    # 章纲剧情设计
    "chapter_plot_design": [
        ValidationRule("chapter_plot_design", True, IS_DICT, "chapter_plot_design（章纲剧情设计顶层）：", False),
        ValidationRule("chapter_plot_design.plot", True, IS_STR, "plot（章纲剧情描述）：", True),
        ValidationRule("chapter_plot_design.summary", True, IS_STR, "summary（章纲剧情摘要）：", True),
    ],

    # 章节事件设计
    "chapter_events_design": [
        ValidationRule("chapter_events_design", True, IS_DICT, "chapter_events_design（章节事件设计顶层）：", False),
        ValidationRule("chapter_events_design.events", False, IS_LIST, "events（章节事件字符串列表）：", True),
    ],

    # 章节正文生成：走文本模式（executor.text()），返回纯文本，无需结构校验

    # 诊断：表达效果
    "expressiveness_audit": [
        ValidationRule("expressiveness_audit", True, IS_DICT, "expressiveness_audit（表达效果诊断顶层）：", False),
        ValidationRule("expressiveness_audit.modifier_fluency", False, IS_LIST, "modifier_fluency（修饰通顺度发现）：", True),
        ValidationRule("expressiveness_audit.rhetoric_quality", False, IS_LIST, "rhetoric_quality（修辞质量发现）：", True),
        ValidationRule("expressiveness_audit.description_balance", False, IS_LIST, "description_balance（描写平衡发现）：", True),
        ValidationRule("expressiveness_audit.emotion_curve", False, IS_LIST, "emotion_curve（情感曲线发现）：", True),
        ValidationRule("expressiveness_audit.structure_redundancy", False, IS_LIST, "structure_redundancy（结构冗余发现）：", True),
        ValidationRule("expressiveness_audit.opening_ending", False, IS_LIST, "opening_ending（开头结尾发现）：", True),
    ],

    # 诊断：叙事逻辑
    "narrative_logic_audit": [
        ValidationRule("narrative_logic_audit", True, IS_DICT, "narrative_logic_audit（叙事逻辑诊断顶层）：", False),
        ValidationRule("narrative_logic_audit.event_chain", False, IS_LIST, "event_chain（事件链提取）：", True),
        ValidationRule("narrative_logic_audit.causality_gaps", False, IS_LIST, "causality_gaps（因果缺口发现）：", True),
        ValidationRule("narrative_logic_audit.info_jumps", False, IS_LIST, "info_jumps（信息跳空发现）：", True),
        ValidationRule("narrative_logic_audit.timeline", False, IS_LIST, "timeline（时间线提取）：", True),
        ValidationRule("narrative_logic_audit.timeline_conflicts", False, IS_LIST, "timeline_conflicts（时间线冲突发现）：", True),
        ValidationRule("narrative_logic_audit.foreshadowing", False, IS_LIST, "foreshadowing（伏笔发现）：", True),
        ValidationRule("narrative_logic_audit.info_unsupported", False, IS_LIST, "info_unsupported（信息跃迁发现）：", True),
    ],

    # 诊断：角色一致性
    "character_consistency_audit": [
        ValidationRule("character_consistency_audit", True, IS_DICT, "character_consistency_audit（角色一致性诊断顶层）：", False),
        ValidationRule("character_consistency_audit.behaviors", False, IS_LIST, "behaviors（角色行为摘要）：", True),
        ValidationRule("character_consistency_audit.contradictions", False, IS_LIST, "contradictions（行为矛盾发现）：", True),
        ValidationRule("character_consistency_audit.motivation_gaps", False, IS_LIST, "motivation_gaps（动机缺失发现）：", True),
    ],

    # 诊断：对话语气
    "dialogue_tone_audit": [
        ValidationRule("dialogue_tone_audit", True, IS_DICT, "dialogue_tone_audit（对话语气诊断顶层）：", False),
        ValidationRule("dialogue_tone_audit.dialogue_segments", False, IS_LIST, "dialogue_segments（对话段落分析）：", True),
        ValidationRule("dialogue_tone_audit.tone_mismatches", False, IS_LIST, "tone_mismatches（语气-关系背离发现）：", True),
    ],

    # 诊断：世界观一致性
    "worldview_consistency_audit": [
        ValidationRule("worldview_consistency_audit", True, IS_DICT, "worldview_consistency_audit（世界观诊断顶层）：", False),
        ValidationRule("worldview_consistency_audit.worldview_elements", False, IS_LIST, "worldview_elements（世界观要素提取）：", True),
        ValidationRule("worldview_consistency_audit.violations", False, IS_LIST, "violations（设定违规发现）：", True),
    ],

    # 诊断：风格倾向
    "style_alignment_audit": [
        ValidationRule("style_alignment_audit", True, IS_DICT, "style_alignment_audit（风格倾向诊断顶层）：", False),
        ValidationRule("style_alignment_audit.style_features", False, IS_LIST, "style_features（文本风格特征）：", True),
        ValidationRule("style_alignment_audit.style_mismatches", False, IS_LIST, "style_mismatches（风格偏离发现）：", True),
    ],

    # 诊断：信息密度与节奏
    "pacing_density_audit": [
        ValidationRule("pacing_density_audit", True, IS_DICT, "pacing_density_audit（信息密度与节奏诊断顶层）：", False),
        ValidationRule("pacing_density_audit.density_curve", False, IS_LIST, "density_curve（信息密度异常片段）：", True),
        ValidationRule("pacing_density_audit.speed_shifts", False, IS_LIST, "speed_shifts（叙事速度突兀变化）：", True),
        ValidationRule("pacing_density_audit.paragraph_rhythm", False, IS_LIST, "paragraph_rhythm（段落节奏单调）：", True),
        ValidationRule("pacing_density_audit.plot_efficiency", False, IS_LIST, "plot_efficiency（情节推进效率低）：", True),
    ],

    # 打磨：表达效果
    "expression_polish": [
        ValidationRule("expression_polish", True, IS_DICT, "expression_polish（表达效果修复顶层）：", False),
        ValidationRule("expression_polish.cleaned_text", True, IS_STR, "cleaned_text（修复后完整文本）：", True),
        ValidationRule("expression_polish.issues_fixed", False, IS_LIST, "issues_fixed（修复条目记录）：", True),
    ],

    # 打磨：结构与节奏
    "structural_polish": [
        ValidationRule("structural_polish", True, IS_DICT, "structural_polish（结构与节奏修复顶层）：", False),
        ValidationRule("structural_polish.cleaned_text", True, IS_STR, "cleaned_text（修复后完整文本）：", True),
        ValidationRule("structural_polish.issues_fixed", False, IS_LIST, "issues_fixed（修复条目记录）：", True),
    ],

    # 打磨：内容逻辑
    "logic_consistency_polish": [
        ValidationRule("logic_consistency_polish", True, IS_DICT, "logic_consistency_polish（内容逻辑修复顶层）：", False),
        ValidationRule("logic_consistency_polish.cleaned_text", True, IS_STR, "cleaned_text（修复后完整文本）：", True),
        ValidationRule("logic_consistency_polish.issues_fixed", False, IS_LIST, "issues_fixed（修复条目记录）：", True),
    ],

    # 打磨：对话语气
    "dialogue_polish": [
        ValidationRule("dialogue_polish", True, IS_DICT, "dialogue_polish（对话语气修复顶层）：", False),
        ValidationRule("dialogue_polish.cleaned_text", True, IS_STR, "cleaned_text（修复后完整文本）：", True),
        ValidationRule("dialogue_polish.issues_fixed", False, IS_LIST, "issues_fixed（修复条目记录）：", True),
    ],

    # 打磨：世界观
    "worldview_polish": [
        ValidationRule("worldview_polish", True, IS_DICT, "worldview_polish（世界观修复顶层）：", False),
        ValidationRule("worldview_polish.cleaned_text", True, IS_STR, "cleaned_text（修复后完整文本）：", True),
        ValidationRule("worldview_polish.issues_fixed", False, IS_LIST, "issues_fixed（修复条目记录）：", True),
    ],

    # 升华：文学质感
    "literary_elevation": [
        ValidationRule("literary_elevation", True, IS_DICT, "literary_elevation（文学升华顶层）：", False),
        ValidationRule("literary_elevation.cleaned_text", True, IS_STR, "cleaned_text（升华后完整文本）：", True),
        ValidationRule("literary_elevation.issues_fixed", False, IS_LIST, "issues_fixed（升华条目记录）：", True),
    ],

    # 校验：信息保真
    "fidelity_repair": [
        ValidationRule("fidelity_repair", True, IS_DICT, "fidelity_repair（信息保真修复顶层）：", False),
        ValidationRule("fidelity_repair.cleaned_text", True, IS_STR, "cleaned_text（修复后完整文本）：", True),
        ValidationRule("fidelity_repair.issues_fixed", False, IS_LIST, "issues_fixed（移除实质性增改条目）：", True),
    ],
}
