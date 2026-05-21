from typing import Dict, Any, Tuple, List
from app.core.steps.rule.base import BaseSteps
from app.common import keys as ke
from app.utils.llm_utils import format_character_profiles, format_relationship_map, format_worldview_rules, \
    format_style_preference


class AdaptationStep(BaseSteps):
    CHINESE_NAME = "串行 - 场景适配"

    def execution_mode(self) -> str:
        return ke.KEY_SERIAL

    def get_step_type(self) -> str:
        return ke.KEY_SERIAL_ADAPTATION

    @staticmethod
    def _format_basic_data(injection_params: Dict[str, Any] = None) -> Tuple:
        global_character = format_character_profiles(
            injection_params.get(ke.KEY_CHARACTER_PROFILES, []),
            title="### 全局角色设定"
        )
        global_relationships = format_relationship_map(
            injection_params.get(ke.KEY_RELATIONSHIP_MAP, []),
            title="### 全局人物关系"
        )
        global_worldview = format_worldview_rules(
            injection_params.get(ke.KEY_WORLDVIEW_RULES, []),
            title="### 全局世界观规则"
        )
        global_style = format_style_preference(
            injection_params.get(ke.KEY_STYLE_PREFERENCE, ""),
            title="### 全局风格倾向"
        )
        return global_character, global_relationships, global_worldview, global_style

    async def execute(self, injection_params: Dict[str, Any] = None) -> None:
        if injection_params is None:
            injection_params = {}

        global_character, global_relationships, global_worldview, global_style = self._format_basic_data(injection_params)
        injection_params[ke.KEY_CHARACTER_PROFILES] = global_character or ""
        injection_params[ke.KEY_RELATIONSHIP_MAP] = global_relationships or ""
        injection_params[ke.KEY_WORLDVIEW_RULES] = global_worldview or ""
        injection_params[ke.KEY_STYLE_PREFERENCE] = global_style or ""

        await super().execute(injection_params)

    async def post_process(self, results: List[tuple]) -> None:
        for result, task in results:
            if not result.success():
                continue

            content = result.content
            if isinstance(content, dict):
                guide = content.get(ke.KEY_SCENE_GUIDE)
                if isinstance(guide, dict):
                    self.context_builder.context[ke.KEY_SCENE_GUIDE] = guide
