import traceback
from abc import ABC, abstractmethod
from functools import partial
from typing import Dict, Any, List
from app.common import keys as ke
from app.common.llm_response import LLMResponse
from app.config.config import config
from app.core.services.sse_manager import get_sse_manager
from app.utils.logger import LoggerManager as logger
from app.utils.prompt_util import safe_format_prompt, extract_placeholders


class BaseSteps(ABC):
    """
    步骤执行抽象基类。
    支持串行/并行两种模式，子类只需关注类型标识、任务获取、后处理。
    """

    CHINESE_NAME = "抽象步骤"

    def __init__(self, prompt_builder, executor, collector, context_builder, llm_concurrency, validator_func):
        self.prompt_builder = prompt_builder
        self.executor = executor
        self.collector = collector
        self.context_builder = context_builder
        self.llm_concurrency = llm_concurrency
        self.validator_func = validator_func  # 校验

    @abstractmethod
    def get_step_type(self) -> str:
        """返回当前步骤在 PromptBuilder 中注册的类型标识"""
        pass

    @abstractmethod
    def execution_mode(self) -> str:
        """
        返回执行模式，必须是 "serial" 或 "parallel"。
        子类必须明确指定，无默认值。
        """
        pass

    def build_tasks(self) -> List[dict]:
        """根据 step_type 构建任务配置列表"""
        return self.prompt_builder.get_configs_by_type(self.get_step_type(), True)

    @staticmethod
    async def pre_check() -> bool:
        """前置校验，返回 False 则跳过执行。子类可按需重写。"""
        return True

    async def post_process(self, results: List[tuple]) -> None:
        """
        后处理钩子，在所有任务执行完毕后调用。
        子类在此处更新上下文、记录日志、处理错误等。
        """
        pass

    def collect_error(self, step_name: str, error: Exception) -> None:
        self.collector.errors.append({
            ke.KEY_KEY: step_name,
            ke.KEY_VALUE: f"步骤 [{step_name}] 崩溃：{error}",
            ke.KEY_TRACEBACK: traceback.format_exc()
        })

    def create_error_response(self, error: Exception) -> LLMResponse:
        """
        构造标准的失败响应字典。
        """
        return LLMResponse.sys_fail(
            msg=str(error),
            vendor=self.executor.vendor,
            model=self.executor.model,
            with_stack=True
        )

    def on_error(self, step_name: str, error: Exception) -> LLMResponse:
        """
        异常兜底总入口：组合“收集”与“构造”两个动作。
        """
        self.collect_error(step_name, error)
        return self.create_error_response(error)

    async def _execute_single_task(self, task, injection_params: Dict[str, Any]) -> LLMResponse:
        """ 执行单个任务 """
        step_id = task.get(ke.KEY_ID)
        params = task.get(ke.KEY_PARAMS)
        step_name = task.get(ke.KEY_NAME)
        type_str = task.get(ke.KEY_TYPE)
        output_key = task.get(ke.KEY_OUTPUT_KEY)
        current_text = injection_params.get(ke.KEY_CURRENT_TEXT, "")

        # 基于当前输入文本长度动态计算 max_tokens
        calculated_max = self.resolve_max_tokens(output_key, len(current_text))
        # 设置 1536 作为安全兜底值，防止因输入过短导致扩容倍率过小，进而引发输出截断
        safe_min = 2048
        params[ke.KEY_MAX_TOKENS] = max(safe_min, calculated_max)
        logger.debug(f"步骤 {step_name} max_tokens 动态计算为 {calculated_max}，"
                     f"应用兜底后最终设置为 {params[ke.KEY_MAX_TOKENS]}", module_name=self.CHINESE_NAME)

        tid = injection_params.get(ke.KEY_ID) if injection_params else None
        sse = get_sse_manager() if tid else None
        is_full_text_mode = self.context_builder.get_current_paragraph_index() is None

        # ======================================================
        #   统一推送：步骤开始
        # ======================================================
        if sse:
            await sse.send_pipeline_event(tid, ke.KEY_PIPELINE_PROGRESS, {
                ke.KEY_TITLE: f"{step_name}",
                ke.KEY_CONTENT: f"正在执行：{step_name}...",
                ke.KEY_META: {
                    ke.KEY_STAGE: type_str,
                    ke.KEY_STATUS: ke.KEY_START,
                    ke.KEY_LEVEL: ke.KEY_FULL_TEXT if is_full_text_mode else ke.KEY_PARAGRAPH
                }
            })

        try:
            prompt_template = self.prompt_builder.get_compiled_prompt(step_id, is_prompt=True)
            if not prompt_template:
                error_msg = f"Prompt ID {step_id} 未找到"
                if sse:
                    await sse.send_pipeline_event(tid, ke.KEY_PIPELINE_PROGRESS, {
                        ke.KEY_TITLE: f"{step_name}",
                        ke.KEY_CONTENT: f"{step_name}未找到预编译的模板",
                        ke.KEY_META: {
                            ke.KEY_STAGE: type_str,
                            ke.KEY_STATUS: ke.KEY_FAILED,
                            ke.KEY_LEVEL: ke.KEY_FULL_TEXT if is_full_text_mode else ke.KEY_PARAGRAPH
                        }
                    })
                return self.on_error(step_name, Exception(error_msg))

            logger.debug(f"[{self.get_step_type()}] 正在渲染 Prompt: {step_id}", module_name=self.CHINESE_NAME)
            used_vars = extract_placeholders(prompt_template)
            # 只保留模板需要的参数
            filtered_params = {k: v for k, v in injection_params.items() if k in used_vars}
            rendered_prompt = safe_format_prompt(
                template=prompt_template,
                **filtered_params
            )
            logger.debug(f"[{self.get_step_type()}] Prompt 渲染完成: {step_id}", module_name=self.CHINESE_NAME)

            if sse:
                await sse.send_pipeline_event(tid, ke.KEY_PIPELINE_PROGRESS, {
                    ke.KEY_TITLE: f"{step_name}",
                    ke.KEY_CONTENT: "正在提交分析请求...",
                    ke.KEY_META: {
                        ke.KEY_STAGE: type_str,
                        ke.KEY_STATUS: ke.KEY_RUNNING,
                        ke.KEY_LEVEL: ke.KEY_FULL_TEXT if is_full_text_mode else ke.KEY_PARAGRAPH
                    }
                })
            response = await self.executor.json(
                prompt=rendered_prompt,
                type_str=type_str,
                prompt_id=step_id,
                params=params,
                validator_func=self.validator_func,
                current_text=current_text,
                on_retry=lambda attempt, factor: sse.send_pipeline_event(tid, ke.KEY_PIPELINE_PROGRESS, {
                    ke.KEY_TITLE: f"{step_name}",
                    ke.KEY_CONTENT: f"输出长度不足，正在自动扩容重试（第{attempt}次，当前倍率{factor}）...",
                    ke.KEY_META: {
                        ke.KEY_STAGE: type_str,
                        ke.KEY_STATUS: ke.KEY_RUNNING,
                        ke.KEY_LEVEL: ke.KEY_FULL_TEXT if is_full_text_mode else ke.KEY_PARAGRAPH
                    }
                })
            )

            await self.collector.record_step_data(response, type_str, step_id, rendered_prompt)

            # ======================================================
            #   统一推送：步骤完成 (根据结果判断成功或失败)
            # ======================================================
            if sse:
                step_status = ke.KEY_COMPLETED if response.success() else ke.KEY_FAILED
                await sse.send_pipeline_event(tid, ke.KEY_PIPELINE_PROGRESS, {
                    ke.KEY_TITLE: f"{step_name}",
                    ke.KEY_CONTENT: f"{step_name} 执行{'成功' if response.success() else '失败'}",
                    ke.KEY_META: {
                        ke.KEY_STAGE: type_str,
                        ke.KEY_STATUS: step_status,
                        ke.KEY_LEVEL: ke.KEY_FULL_TEXT if is_full_text_mode else ke.KEY_PARAGRAPH
                    }
                })
            return response
        except Exception as e:
            # 执行异常，推送失败事件后，再交给错误处理
            if sse:
                await sse.send_pipeline_event(tid, ke.KEY_PIPELINE_PROGRESS, {
                    ke.KEY_TITLE: f"{step_name} 完成",
                    ke.KEY_CONTENT: f"{step_name} 执行失败",
                    ke.KEY_META: {
                        ke.KEY_STAGE: type_str,
                        ke.KEY_STATUS: ke.KEY_FAILED,
                        ke.KEY_LEVEL: ke.KEY_FULL_TEXT if is_full_text_mode else ke.KEY_PARAGRAPH
                    }
                })
            logger.error(f"[{self.get_step_type()}] 任务执行异常: {step_name}", exc_info=True, module_name=self.CHINESE_NAME)
            return self.on_error(step_name, e)

    async def _execute_serial(self, tasks: List[Dict], injection_params: Dict[str, Any]) -> List[tuple]:
        """串行执行所有任务"""
        results = []
        for task in tasks:
            logger.info(f"🚀 准备执行任务: {task.get(ke.KEY_NAME)} | 当前上下文Keys: {list(injection_params.keys())}", module_name=self.CHINESE_NAME)
            task = dict(task)
            output_key = task.get(ke.KEY_OUTPUT_KEY)

            result = await self._execute_single_task(task, injection_params)
            results.append((result, task))
            if not result.success():
                continue

            content = result.content
            if not isinstance(content, dict):
                continue

            fix_data = content.get(output_key)
            if not isinstance(fix_data, dict):
                continue

            # === 特殊处理：候选生成步骤 ===
            if output_key == ke.KEY_CANDIDATES_OUTPUT:
                candidates = fix_data.get(ke.KEY_CANDIDATES, [])
                # 将三个候选版本按约定键名注入参数字典
                for i, key in enumerate([ke.KEY_CANDIDATE_0, ke.KEY_CANDIDATE_1, ke.KEY_CANDIDATE_2]):
                    val = candidates[i] if i < len(candidates) else ""
                    injection_params[key] = val
                continue  # 该步骤不更新 current_text，直接跳过后续常规处理

            # === 特殊处理：智能选择 ===
            if output_key == ke.KEY_SELECTION_RESULT:
                selected_index = fix_data.get(ke.KEY_SELECTED_INDEX)
                if selected_index is not None:
                    selected_text = self._resolve_selected_text(selected_index, injection_params)
                    injection_params[ke.KEY_CURRENT_TEXT] = selected_text
                continue

            # === 常规处理：提取 cleaned_text 并更新 current_text ===
            cleaned_text = fix_data.get(ke.KEY_CLEANED_TEXT)
            if cleaned_text:
                injection_params[ke.KEY_CURRENT_TEXT] = cleaned_text

        return results

    async def _execute_parallel(self, tasks: List[Dict], injection_params: Dict[str, Any]) -> List[tuple]:
        """并行执行所有任务"""

        async def task_wrapper(t):
            result = await self._execute_single_task(t, injection_params)
            return result, t

        callables = [partial(task_wrapper, t) for t in tasks]
        return await self.llm_concurrency.run_tasks(callables)

    async def execute(self, injection_params: Dict[str, Any] = None) -> None:
        """
        统一执行入口，根据 execution_mode 自动选择串行或并行。
        """
        if not await self.pre_check():
            logger.info(f"[{self.get_step_type()}] 前置校验未通过，跳过执行", module_name=self.CHINESE_NAME)
            return

        tasks = self.build_tasks()
        if not tasks:
            logger.warning(f"[{self.get_step_type()}] 未构建出任何任务，跳过执行", module_name=self.CHINESE_NAME)
            return

        mode = self.execution_mode()
        logger.info(f"[{self.get_step_type()}] 开始执行，共 {len(tasks)} 个任务，模式: {mode}", module_name=self.CHINESE_NAME)

        if mode == ke.KEY_SERIAL:
            results = await self._execute_serial(tasks, injection_params)
        else:
            results = await self._execute_parallel(tasks, injection_params)

        # 统计执行结果
        total = len(results)
        success_count = 0
        for result, _ in results:
            if result.success():
                success_count += 1

        failed_count = total - success_count
        logger.info(
            f"[{self.get_step_type()}] 执行完成 | 总计: {total} | 成功: {success_count} | 失败: {failed_count}",
            module_name=self.CHINESE_NAME
        )

        await self.post_process(results)

    @staticmethod
    def _extract_cleaned_text(result: LLMResponse, output_key: str, target_key: str):
        if not result.success():
            return None
        content = result.content
        if not isinstance(content, dict):
            return None
        fix_data = content.get(output_key)
        if not isinstance(fix_data, dict):
            return None
        return fix_data.get(target_key)

    @staticmethod
    def _resolve_selected_text(selected_idx: int, params: Dict[str, Any]) -> str:
        if selected_idx == 0:
            return params[ke.KEY_ORIGINAL_TEXT]
        if selected_idx == 1:
            return params[ke.KEY_CURRENT_TEXT]
        if selected_idx == 2:
            return params[ke.KEY_CANDIDATE_0]
        if selected_idx == 3:
            return params[ke.KEY_CANDIDATE_1]
        if selected_idx == 4:
            return params[ke.KEY_CANDIDATE_2]

    @staticmethod
    def resolve_max_tokens(output_key: str, char_count: int) -> int:
        base = int(char_count * config.FULL_TEXT_TOKENS_RATIO)
        # 兜底下限 768，保证短文本也有足够空间
        min_limit = 768
        computed = base * 3 if output_key == ke.KEY_CANDIDATES_OUTPUT else base
        return max(computed, min_limit)
