import re
from typing import List, Dict, Tuple
from app.common import keys as ke
from app.core.registry.global_singleton_registry import GlobalSingletonRegistry


class SpellChecker:
    """拼写检查器 - 从引擎获取错别字与形近字检测规则"""
    CHINESE_NAME = "拼写检查器"

    def __init__(self):
        rules = self._load_rules()
        self.common_errors = rules.get(ke.KEY_COMMON_ERRORS, {})
        self.de_fix_pairs = rules.get(ke.KEY_DE_FIX_PAIRS, {})

    @staticmethod
    def _get_engine():
        registry = GlobalSingletonRegistry.get_instance_sync()
        return registry.get_cognitive_engine()

    def _load_rules(self) -> Dict:
        try:
            engine = self._get_engine()
            if engine and hasattr(engine, 'text_correction_config_get_config'):
                rules = engine.text_correction_config_get_config()
                if isinstance(rules, dict):
                    return rules
        except Exception:
            pass
        return {
            ke.KEY_COMMON_ERRORS: {},
            ke.KEY_DE_FIX_PAIRS: {}
        }

    def auto_fix_de_errors(self, text: str) -> Tuple[str, List[Dict]]:
        f_text = text
        f = []
        applied_fixes = set()

        sorted_pairs = sorted(self.de_fix_pairs.items(), key=lambda item: len(item[0]), reverse=True)

        for wrong, correct in sorted_pairs:
            if wrong in f_text and (wrong, correct) not in applied_fixes:
                f_text = f_text.replace(wrong, correct)
                applied_fixes.add((wrong, correct))
                f.append({
                    ke.KEY_TYPE: ke.KEY_FIXED_DE_ERROR,
                    ke.KEY_DESCRIPTION: f"将 '{wrong}' 替换为 '{correct}'",
                    ke.KEY_COUNT: f_text.count(correct)
                })

        return f_text, f

    def auto_fix_wrong_characters(self, text: str) -> Tuple[str, List[Dict]]:
        f_text = text
        f = []
        applied_fixes = set()

        for correct, wrong_list in self.common_errors.items():
            for wrong in wrong_list:
                if wrong in f_text:
                    f_text, count = re.subn(re.escape(wrong), correct, f_text)
                    if count > 0 and (wrong, correct) not in applied_fixes:
                        applied_fixes.add((wrong, correct))
                        f.append({
                            ke.KEY_TYPE: ke.KEY_FIXED_WRONG_CHARACTER,
                            ke.KEY_DESCRIPTION: f"将 '{wrong}' 替换为 '{correct}'",
                            ke.KEY_COUNT: count
                        })

        return f_text, f