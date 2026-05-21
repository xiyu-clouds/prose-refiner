from typing import Dict, Any, List
from app.common import keys as ke
from app.common.llm_response import LLMResponse


class ExecutionCollector:
    CHINESE_NAME = "通用收集器"

    def __init__(self):
        self.prompts: Dict[str, List[Dict[str, str]]] = {}
        self.responses: Dict[str, List[Dict[str, Any]]] = {}
        self.errors: List[Dict[str, Any]] = []

    @classmethod
    async def get_instance(cls) -> "ExecutionCollector":
        """创建并返回一个新的收集器实例"""
        return cls()

    async def record_step_data(self, response: LLMResponse, current_type: str, current_id: str, current_prompt: str):
        """异步记录单步骤的数据 - 从LLMResponse对象中提取数据"""
        # 记录prompt
        if current_type not in self.prompts:
            self.prompts[current_type] = []
        self.prompts[current_type].append({
            ke.KEY_KEY: current_id,
            ke.KEY_VALUE: current_prompt
        })

        # 记录response
        if current_type not in self.responses:
            self.responses[current_type] = []
        if response.raw is not None:
            self.responses[current_type].append({
                ke.KEY_KEY: current_id,
                ke.KEY_VALUE: response.raw
            })

        # 根据LLMResponse的状态记录错误
        if not response.ok:  # 网络或API层面失败
            error_info = {
                ke.KEY_KEY: current_id,
                ke.KEY_VALUE: f"步骤 [{current_id}] 调用失败：{response.msg or 'API Error'}"
            }
            if response.stack:
                error_info[ke.KEY_TRACEBACK] = response.stack
            self.errors.append(error_info)
        elif not response.valid:  # 内容验证失败
            if response.err == ke.KEY_VALIDATION and response.errors:
                for err_msg in response.errors:
                    self.errors.append({
                        ke.KEY_KEY: current_id,
                        ke.KEY_VALUE: f"步骤 [{current_id}] 校验未通过：{err_msg}"
                    })
            elif response.msg:  # 其他验证失败情况
                self.errors.append({
                    ke.KEY_KEY: current_id,
                    ke.KEY_VALUE: f"步骤 [{current_id}] 内容验证失败：{response.msg}"
                })

    async def get_prompts_by_type(self, type_name: str) -> List[Dict[str, str]]:
        return self.prompts.get(type_name, [])

    async def get_responses_by_type(self, type_name: str) -> List[Dict[str, Any]]:
        return self.responses.get(type_name, [])

    async def get_all_errors(self) -> List[Dict[str, Any]]:
        return self.errors

    async def get_all_prompts(self) -> Dict[str, List[Dict[str, str]]]:
        return self.prompts.copy()

    async def get_all_responses(self) -> Dict[str, List[Dict[str, Any]]]:
        return self.responses.copy()

    async def clear(self):
        """异步清空所有数据"""
        self.prompts.clear()
        self.responses.clear()
        self.errors.clear()
