# import copy
# import uuid
# import numpy as np
# from functools import partial
# from typing import List, Dict, Any, Tuple, Optional
# from app.config.config import config
# from app.core.concurrency.concurrency_manager import ConcurrencyManager
# from app.core.engine.local_lightweight_engine import LocalLightweightEngine
# from app.core.services.sse_manager import get_sse_manager
# from app.utils.text_processor import TextProcessor  # 文本预处理工具已移至 utils
# from app.core.steps.text.adaptation import AdaptationStep
# from app.core.steps.text.analysis import AnalysisStep
# from app.core.steps.text.aggregation import AggregationStep
# from app.core.steps.text.polish import PolishStep
# from app.core.collector.execution_context import ExecutionCollector
# from app.core.validators.validator_adapter import validate_step_rules
# from app.registry.global_singleton_registry import GlobalSingletonRegistry
# from app.common import keys as ke
# from app.utils.llm_utils import sort_context_paragraphs, build_user_clarification, clean_serializable
# from app.utils.logger import LoggerManager as logger


# class PipelineOrchestrator:
#     CHINESE_NAME = "管道编排器"

#     def __init__(self):
#         # 并发管理器：一个用于批次级并发，一个用于LLM步骤内部并发
#         self.batch_concurrency = ConcurrencyManager(max_concurrent=config.CURRENT_BATCH_TASK_CONCURRENCY)
#         self.llm_concurrency = ConcurrencyManager(max_concurrent=config.CURRENT_LLM_STEP_CONCURRENCY)

#         # 执行器
#         self.executor = None

#         # 本地轻量引擎
#         self.local_engine = LocalLightweightEngine()
#         # 本地文本清洗器
#         self.local_preprocessor = TextProcessor()  # 已移至 app.utils.text_processor

#     async def initialize(self):
#         """异步初始化，获取全局单例并创建步骤"""
#         registry = await GlobalSingletonRegistry.get_instance()
#         self.executor = await registry.get_executor()

#     async def run(self, injection_params: Dict[str, Any], task_id: Optional[str] = None) -> Dict[str, Any]:
#         await self.initialize()

#         # 每个任务独立实例
#         collector = await ExecutionCollector.get_instance()
#         context_builder = ContextBuilder.get_instance()
#         context_builder.reset()

#         step_kwargs = {
#             ke.KEY_PROMPT_BUILDER: self.prompt_builder,
#             ke.KEY_EXECUTOR: self.executor,
#             ke.KEY_COLLECTOR: collector,
#             ke.KEY_CONTEXT_BUILDER: context_builder,
#             ke.KEY_LLM_CONCURRENCY: self.llm_concurrency,
#             ke.KEY_VALIDATOR_FUNC: validate_step_rules,
#         }

#         adaptation_step = AdaptationStep(**step_kwargs)
#         analysis_step = AnalysisStep(**step_kwargs)
#         aggregation_step = AggregationStep(**step_kwargs)
#         polish_step = PolishStep(**step_kwargs)

#         # 使用传入的 ID，否则自动生成
#         original_params = copy.deepcopy(injection_params)
#         text = original_params.get(ke.KEY_CURRENT_TEXT, "")
#         tid = task_id or str(uuid.uuid4())
#         original_params[ke.KEY_ID] = tid
#         sse = get_sse_manager()
#         logger.set_trace_id(tid)

#         logger.info("🚀 流水线启动", module_name=self.CHINESE_NAME)
#         await sse.send_pipeline_event(tid, ke.KEY_TASK_STARTED, {
#             ke.KEY_TITLE: "任务启动",
#             ke.KEY_CONTENT: "文本优化流水线已开始运行。",
#             ke.KEY_META: {ke.KEY_STAGE: ke.KEY_TASK_STARTED, ke.KEY_STATUS: ke.KEY_START}
#         })

#         # 用于收集各阶段完整文本快照（有序）
#         text_snapshots: List[Dict[str, Any]] = [{
#             ke.KEY_STAGE: ke.KEY_ORIGINAL,
#             ke.KEY_TEXT: text,
#             ke.KEY_LENGTH: len(text)
#         }]

#         # --- 预处理开始 ---
#         await sse.send_pipeline_event(tid, ke.KEY_PREPROCESSING_PROGRESS, {
#             ke.KEY_TITLE: "本地预处理",
#             ke.KEY_CONTENT: "正在执行本地预处理流程",
#             ke.KEY_META: {ke.KEY_STAGE: ke.KEY_PREPROCESSING_PROGRESS, ke.KEY_STATUS: ke.KEY_START}
#         })

#         await sse.send_pipeline_event(tid, ke.KEY_PREPROCESSING_PROGRESS, {
#             ke.KEY_TITLE: "本地预处理",
#             ke.KEY_CONTENT: "正在执行标点修正与错词检查...",
#             ke.KEY_META: {ke.KEY_STAGE: ke.KEY_PREPROCESSING_PROGRESS, ke.KEY_STATUS: ke.KEY_RUNNING}
#         })

#         # 本地预处理
#         local_result = await self.local_preprocessor.process(text)
#         cleaned_text = local_result[ke.KEY_CLEANED_TEXT]
#         paragraphs = local_result[ke.KEY_PARAGRAPHS]
#         injection_params[ke.KEY_FIX_RECORDS] = local_result.get(ke.KEY_FIX_RECORDS, [])
#         logger.info(f"本地预处理完成，段落数: {len(paragraphs)}", module_name=self.CHINESE_NAME)
#         await sse.send_pipeline_event(tid, ke.KEY_PREPROCESSING_PROGRESS, {
#             ke.KEY_TITLE: "本地预处理",
#             ke.KEY_CONTENT: f"文本已清洗至 {len(cleaned_text)} 字符，初步划分为 {len(paragraphs)} 个段落。",
#             ke.KEY_META: {ke.KEY_STAGE: ke.KEY_PREPROCESSING_PROGRESS, ke.KEY_STATUS: ke.KEY_RUNNING}
#         })

#         # 本地清洗后全文
#         text_snapshots.append({
#             ke.KEY_STAGE: ke.KEY_LOCAL_CLEANED,
#             ke.KEY_TEXT: cleaned_text,
#             ke.KEY_LENGTH: len(cleaned_text)
#         })

#         # 智能合并过短段落，控制并发数
#         paragraphs = self._merge_short_paragraphs(paragraphs, target_chars=config.PARAGRAPH_TARGET_CHARS,
#                                                   tolerance=config.PARAGRAPH_TOLERANCE)
#         logger.info(f"智能合并过短段落，控制并发数，合并后段落数: {len(paragraphs)}", module_name=self.CHINESE_NAME)
#         await sse.send_pipeline_event(tid, ke.KEY_PREPROCESSING_PROGRESS, {
#             ke.KEY_TITLE: "本地预处理",
#             ke.KEY_CONTENT: f"合并过短段落完成，段落数优化至 {len(paragraphs)} 个",
#             ke.KEY_META: {ke.KEY_STAGE: ke.KEY_PREPROCESSING_PROGRESS, ke.KEY_STATUS: ke.KEY_RUNNING}
#         })

#         # ---- 本地文本特征提取 (jieba + 词库过滤) ----
#         await sse.send_pipeline_event(tid, ke.KEY_PREPROCESSING_PROGRESS, {
#             ke.KEY_TITLE: "本地预处理",
#             ke.KEY_CONTENT: "正在提取关键词、实体，并与知识库进行匹配...",
#             ke.KEY_META: {ke.KEY_STAGE: ke.KEY_PREPROCESSING_PROGRESS, ke.KEY_STATUS: ke.KEY_RUNNING}
#         })
#         # 调用本地引擎，内部包含分词、关键词提取、词库过滤、embedding
#         nlp_features = await self.local_engine.analyze_text(cleaned_text)
#         nlp_summary = nlp_features.get(ke.KEY_NLP_SUMMARY, '')
#         original_params[ke.KEY_NLP_SUMMARY] = nlp_summary
#         embedding = nlp_features.get(ke.KEY_EMBEDDING)
#         injection_params[ke.KEY_NLP_SUMMARY] = nlp_summary
#         await sse.send_pipeline_event(tid, ke.KEY_PREPROCESSING_PROGRESS, {
#             ke.KEY_TITLE: "本地预处理",
#             ke.KEY_CONTENT: nlp_summary or "特征提取完成",
#             ke.KEY_META: {ke.KEY_STAGE: ke.KEY_PREPROCESSING_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
#         })

#         await sse.send_pipeline_event(task_id, ke.KEY_PIPELINE_PROGRESS, {
#             ke.KEY_TITLE: "文本处理pipeline",
#             ke.KEY_CONTENT: "开始执行文本处理pipeline",
#             ke.KEY_META: {ke.KEY_STAGE: ke.KEY_PIPELINE_PROGRESS, ke.KEY_STATUS: ke.KEY_START}
#         })

#         # 场景适配
#         await adaptation_step.execute(original_params)
#         scene_guide = context_builder.context.get(ke.KEY_SCENE_GUIDE, {})
#         if scene_guide:
#             original_params[ke.KEY_CHARACTER_PROFILES] = scene_guide.get(ke.KEY_CHARACTER_PROFILES, [])
#             original_params[ke.KEY_RELATIONSHIP_MAP] = scene_guide.get(ke.KEY_RELATIONSHIP_MAP, [])
#             original_params[ke.KEY_WORLDVIEW_RULES] = scene_guide.get(ke.KEY_WORLDVIEW_RULES, [])
#             original_params[ke.KEY_STYLE_PREFERENCE] = scene_guide.get(ke.KEY_STYLE_PREFERENCE, [])

#         # 段落级并发处理
#         polished_paragraphs = await self._process_paragraphs_concurrently(paragraphs, original_params, context_builder,
#                                                                           analysis_step, aggregation_step, polish_step)

#         # 组装全文
#         assembled_text = "\n\n".join(polished_paragraphs)
#         repaired_text = assembled_text
#         logger.info(f"全文组装完成，长度: {len(repaired_text)}", module_name=self.CHINESE_NAME)

#         # 段落级打磨后组装全文
#         text_snapshots.append({
#             ke.KEY_STAGE: ke.KEY_PARAGRAPH_POLISHED,
#             ke.KEY_TEXT: repaired_text,
#             ke.KEY_LENGTH: len(repaired_text)
#         })

#         injection_params[ke.KEY_SEMANTIC_SHIFT] = await self._detect_semantic_shift(embedding, repaired_text, tid)

#         # 持久化与启动后续工作流
#         return await self._finalize_pipeline(
#             task_id=tid,
#             text_snapshots=text_snapshots,
#             repaired_text=repaired_text,
#             injection_params=injection_params,
#             context_builder=context_builder,
#             collector=collector,
#         )

#     async def batch_run(self, batch_params: List[Dict[str, Any]], task_ids: Optional[List[str]] = None) -> List[
#         Dict[str, Any]]:
#         if not batch_params:
#             return []

#         if task_ids is None:
#             task_ids = [str(uuid.uuid4()) for _ in batch_params]
#         elif len(task_ids) != len(batch_params):
#             raise ValueError("task_ids 与 batch_params 长度必须一致")

#         tasks = [
#             partial(self.run, injection_params=p, task_id=tid)
#             for p, tid in zip(batch_params, task_ids)
#         ]

#         results = await self.batch_concurrency.run_tasks_with_exceptions(tasks)
#         return results

#     async def _process_paragraphs_concurrently(
#             self,
#             paragraphs: List[str],
#             injection_params: Dict[str, Any],
#             context_builder: ContextBuilder,
#             analysis_step: AnalysisStep,
#             aggregation_step: AggregationStep,
#             polish_step: PolishStep
#     ) -> List[str]:
#         """使用 ConcurrencyManager 并发处理所有段落，返回打磨后的段落列表（保持原顺序）"""

#         async def process_one(idx: int, para: str) -> Tuple[int, str]:
#             params = copy.deepcopy(injection_params)  # 使用深拷贝避免并发修改冲突
#             params[ke.KEY_CURRENT_TEXT] = para
#             params[ke.KEY_INIT_TEXT] = para
#             logger.info(f"开始处理段落 {idx + 1}", module_name=self.CHINESE_NAME)
#             context_builder.set_current_paragraph_index(idx)
#             await self._process_single_paragraph(params, analysis_step, aggregation_step, polish_step)
#             polished = params[ke.KEY_CURRENT_TEXT]
#             logger.info(f"段落 {idx + 1} 处理完成", module_name=self.CHINESE_NAME)
#             return idx, polished

#         # 使用 partial 绑定参数，生成无参可调用对象
#         callables = [partial(process_one, idx, para) for idx, para in enumerate(paragraphs)]

#         # 通过并发管理器执行
#         results = await self.batch_concurrency.run_tasks(callables)

#         # 按索引排序确保顺序
#         sorted_results = sorted(results, key=lambda x: x[0])
#         return [para for _, para in sorted_results]

#     @staticmethod
#     async def _process_single_paragraph(
#             params: Dict[str, Any],
#             analysis_step: AnalysisStep,
#             aggregation_step: AggregationStep,
#             polish_step: PolishStep
#     ) -> None:
#         """处理单个段落：诊断 -> 聚合 -> 打磨"""
#         await analysis_step.execute(params)
#         await aggregation_step.execute(params)
#         await polish_step.execute(params)

#     @staticmethod
#     async def _process_full_text(
#             params: Dict[str, Any],
#             cleaned_text: str,
#             context_builder: ContextBuilder,
#             analysis_step: AnalysisStep,
#             aggregation_step: AggregationStep,
#             polish_step: PolishStep
#     ) -> str:
#         """全文级处理：诊断 -> 聚合 -> 打磨 -> 增强"""
#         context_builder.set_current_paragraph_index(None)  # 标记为全文模式
#         params[ke.KEY_INIT_TEXT] = cleaned_text
#         await analysis_step.execute(params)
#         await aggregation_step.execute(params)
#         await polish_step.execute(params)
#         return params[ke.KEY_CURRENT_TEXT]

#     @staticmethod
#     def _merge_short_paragraphs(paragraphs: List[str], target_chars: int = 550, tolerance: int = 100) -> List[str]:
#         """
#         智能合并段落，使每段长度趋向 [target_chars - tolerance, target_chars + tolerance] 区间。

#         核心原则：
#         1. 单段落已在区间内 → 直接提交。
#         2. 合并后仍在区间内 → 提交合并结果，清空缓冲区。
#         3. 合并后短于下限 → 继续合并下一段。
#         4. 合并后超过上限 → 若缓冲区已满足下限则提交缓冲区，当前段落另起；否则强制合并并提交。

#         Args:
#             paragraphs: 待合并的段落列表。
#             target_chars: 目标字数。
#             tolerance: 允许的偏移量。

#         Returns:
#             合并后的段落列表。
#         """
#         if not paragraphs:
#             return []

#         lower_bound = target_chars - tolerance
#         upper_bound = target_chars + tolerance
#         merged = []
#         buffer = ""

#         for para in paragraphs:
#             para_len = len(para)

#             # 情况1：当前段落本身已在目标区间内
#             if lower_bound <= para_len <= upper_bound:
#                 # 先提交缓冲区（如果有）
#                 if buffer:
#                     merged.append(buffer.strip())
#                     buffer = ""
#                 # 直接提交当前段落
#                 merged.append(para)
#                 continue

#             # 情况2：尝试将当前段落与缓冲区合并
#             candidate = f"{buffer}\n\n{para}".strip() if buffer else para
#             candidate_len = len(candidate)

#             # 情况2a：合并后长度在目标区间内 → 完美，提交并清空
#             if lower_bound <= candidate_len <= upper_bound:
#                 merged.append(candidate)
#                 buffer = ""
#                 continue

#             # 情况2b：合并后仍短于下限 → 继续累积
#             if candidate_len < lower_bound:
#                 buffer = candidate
#                 continue

#             # 情况2c：合并后超过上限
#             # 判断缓冲区本身是否已满足下限
#             if buffer and len(buffer) >= lower_bound:
#                 # 缓冲区已足够好，提交缓冲区，当前段落作为新起点
#                 merged.append(buffer.strip())
#                 buffer = para
#             else:
#                 # 缓冲区还不够，但加上当前段又超了 → 强制提交合并结果
#                 merged.append(candidate)
#                 buffer = ""

#         # 处理尾部残余
#         if buffer:
#             buffer_len = len(buffer)
#             if buffer_len >= lower_bound:
#                 merged.append(buffer.strip())
#             elif merged:
#                 # 尾部太短，合并到最后一段
#                 merged[-1] = f"{merged[-1]}\n\n{buffer}".strip()
#             else:
#                 merged.append(buffer.strip())

#         return merged

#     async def _detect_semantic_shift(self, embedding_before, repaired_text: str, tid: str) -> Optional[str]:
#         """计算语义偏移，若超过阈值则返回自然语言告警，否则返回 None。"""
#         sse = get_sse_manager()

#         await sse.send_pipeline_event(tid, ke.KEY_PIPELINE_PROGRESS, {
#             ke.KEY_TITLE: "计算语义偏移",
#             ke.KEY_CONTENT: "开始计算文本处理前后的语义偏移量",
#             ke.KEY_META: {
#                 ke.KEY_STAGE: ke.KEY_PIPELINE_PROGRESS,
#                 ke.KEY_STATUS: ke.KEY_START
#             }
#         })

#         if embedding_before is None:
#             await sse.send_pipeline_event(tid, ke.KEY_PIPELINE_PROGRESS, {
#                 ke.KEY_TITLE: "计算语义偏移",
#                 ke.KEY_CONTENT: "计算失败，缺失原始内容的文本向量",
#                 ke.KEY_META: {
#                     ke.KEY_STAGE: ke.KEY_PIPELINE_PROGRESS,
#                     ke.KEY_STATUS: ke.KEY_FAILED
#                 }
#             })
#             return None

#         embedding_after = await self.local_engine.get_embedding(repaired_text)
#         if embedding_after is None:
#             await sse.send_pipeline_event(tid, ke.KEY_PIPELINE_PROGRESS, {
#                 ke.KEY_TITLE: "计算语义偏移",
#                 ke.KEY_CONTENT: "计算失败，缺失打磨后内容的文本向量",
#                 ke.KEY_META: {
#                     ke.KEY_STAGE: ke.KEY_PIPELINE_PROGRESS,
#                     ke.KEY_STATUS: ke.KEY_FAILED
#                 }
#             })
#             return None

#         cosine_sim = float(np.dot(embedding_before, embedding_after) / (
#                 np.linalg.norm(embedding_before) * np.linalg.norm(embedding_after)
#         ))
#         logger.info(f"语义相似度: {cosine_sim:.4f}", module_name=self.CHINESE_NAME)

#         if cosine_sim >= config.SEMANTIC_SIMILARITY_THRESHOLD:
#             await sse.send_pipeline_event(tid, ke.KEY_PIPELINE_PROGRESS, {
#                 ke.KEY_TITLE: "计算语义偏移",
#                 ke.KEY_CONTENT: f"计算成功，语义偏移幅度满足于设定的阈值：{cosine_sim:.4f}",
#                 ke.KEY_META: {
#                     ke.KEY_STAGE: ke.KEY_PIPELINE_PROGRESS,
#                     ke.KEY_STATUS: ke.KEY_COMPLETED
#                 }
#             })
#             return None

#         logger.warning(f"⚠️ 语义偏移过大 ({cosine_sim:.4f})", module_name=self.CHINESE_NAME)

#         # 自然语言描述，前端直接展示
#         alert_msg = (
#             f"润色后文本语义相似度仅 {cosine_sim:.2f}，低于阈值 {config.SEMANTIC_SIMILARITY_THRESHOLD}，建议人工复核。"
#         )

#         await sse.send_pipeline_event(tid, ke.KEY_PIPELINE_PROGRESS, {
#             ke.KEY_TITLE: "计算语义偏移",
#             ke.KEY_CONTENT: alert_msg,
#             ke.KEY_META: {
#                 ke.KEY_STAGE: ke.KEY_PIPELINE_PROGRESS,
#                 ke.KEY_STATUS: ke.KEY_COMPLETED
#             }
#         })

#         return alert_msg

#     async def _finalize_pipeline(
#             self,
#             task_id: str,
#             text_snapshots: list,
#             repaired_text: str,
#             injection_params: Dict[str, Any],
#             context_builder: ContextBuilder,
#             collector: ExecutionCollector
#     ) -> Dict[str, Any]:
#         """
#         收尾步骤：组装文本处理结果、持久化到三轨存储、提交元认知任务。
#         返回标准化的任务状态摘要。
#         """
#         context_builder.context = sort_context_paragraphs(context_builder.context)
#         context_builder.context = clean_serializable(context_builder.context)
#         sse = get_sse_manager()
#         semantic_shift = injection_params.pop(ke.KEY_SEMANTIC_SHIFT, None)
#         fix_records = injection_params.pop(ke.KEY_FIX_RECORDS, [])
#         nlp_summary = injection_params.pop(ke.KEY_NLP_SUMMARY, None)

#         # 组装持久化数据
#         text_pipeline_data = {
#             ke.KEY_ID: task_id,
#             ke.KEY_TEXT_SNAPSHOTS: text_snapshots,
#             ke.KEY_CONTEXT: context_builder.context,
#             ke.KEY_SEMANTIC_SHIFT: semantic_shift,  # 记录偏移信息
#             ke.KEY_FIX_RECORDS: fix_records,
#             ke.KEY_NLP_SUMMARY: nlp_summary
#         }

#         # 持久化
#         try:
#             await save_text_processing_result(
#                 task_id=task_id,
#                 data=text_pipeline_data,
#                 vendor=self.executor.vendor,
#                 model=self.executor.model,
#                 collector=collector,
#             )
#             logger.info(f"✅ [{task_id}] 文本处理持久化完成", module_name=self.CHINESE_NAME)
#             await sse.send_pipeline_event(task_id, ke.KEY_PIPELINE_PROGRESS, {
#                 ke.KEY_TITLE: "文本处理pipeline",
#                 ke.KEY_CONTENT: "文本处理持久化成功",
#                 ke.KEY_META: {ke.KEY_STAGE: ke.KEY_PIPELINE_PROGRESS, ke.KEY_STATUS: ke.KEY_COMPLETED}
#             })
#         except Exception as e:
#             logger.exception(f"💥 [{task_id}] 持久化失败", module_name=self.CHINESE_NAME)
#             # 推送失败事件
#             await sse.send_pipeline_event(task_id, ke.KEY_TASK_FAILED, {
#                 ke.KEY_TITLE: "文本处理pipeline",
#                 ke.KEY_CONTENT: "文本处理持久化失败",
#                 ke.KEY_META: {ke.KEY_STAGE: ke.KEY_PIPELINE_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
#             })
#             return {
#                 ke.KEY_ID: task_id,
#                 ke.KEY_STATUS: ke.KEY_FAIL,
#                 ke.KEY_MESSAGE: f"文本处理持久化失败: {str(e)}",
#             }

#         # 提交元认知任务
#         try:
#             user_clarification = build_user_clarification(injection_params)
#             from app.core.meta.executor import submit_metacognition_task
#             await submit_metacognition_task(
#                 id=task_id,
#                 content=repaired_text,
#                 user_clarification=user_clarification,
#             )
#             logger.info(f"🧠 [{task_id}] 元认知任务已提交", module_name=self.CHINESE_NAME)

#             await sse.send_pipeline_event(task_id, ke.KEY_METACOGNITION_PROGRESS, {
#                 ke.KEY_TITLE: "元认知分析",
#                 ke.KEY_CONTENT: "元认知任务已提交，即将开始分析。",
#                 ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_START}
#             })
#         except Exception as e:
#             logger.exception(f"💥 [{task_id}] 提交元认知任务失败", module_name=self.CHINESE_NAME)
#             # 推送失败事件
#             await sse.send_pipeline_event(task_id, ke.KEY_TASK_FAILED, {
#                 ke.KEY_TITLE: "元认知分析",
#                 ke.KEY_CONTENT: "元认知任务提交失败",
#                 ke.KEY_META: {ke.KEY_STAGE: ke.KEY_METACOGNITION_PROGRESS, ke.KEY_STATUS: ke.KEY_FAILED}
#             })
#             return {
#                 ke.KEY_ID: task_id,
#                 ke.KEY_STATUS: ke.KEY_FAIL,
#                 ke.KEY_MESSAGE: f"元认知任务提交失败: {str(e)}",
#             }
#         return {
#             ke.KEY_ID: task_id,
#             ke.KEY_STATUS: ke.KEY_SUCCESS,
#             ke.KEY_MESSAGE: "文本处理完成，元认知分析已启动",
#         }
