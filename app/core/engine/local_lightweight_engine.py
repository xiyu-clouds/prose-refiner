import asyncio
from typing import Any, Dict, List, Optional
from app.config.config import config
from app.common import keys as ke
from app.core.concurrency.concurrency_manager import ConcurrencyManager
from app.core.services.model_manager import ModelPoolManager
from app.core.services.local_tools import LocalTextTools
from app.core.services.model_loaders import load_huggingface_pipeline, set_download_progress_callback
from app.core.services.sse_manager import get_sse_manager
from app.notify.notifier_factory import get_notifiers
from app.utils.logger import LoggerManager as logger


class LocalLightweightEngine:
    CHINESE_NAME = "本地轻量模型引擎"

    def __init__(self):
        self._main_event_loop = asyncio.get_running_loop()
        # 设置下载进度推送
        set_download_progress_callback(self._on_download_progress)
        self.model_pool = ModelPoolManager(alert_callback=self._alert_callback)
        self.text_tools = LocalTextTools.get_instance()
        self.local_model_concurrency = ConcurrencyManager(
            max_concurrent=config.LOCAL_MODEL_CONCURRENCY
        )

        self._task_registry: Dict[str, dict] = {}
        self._load_models_from_config()
        logger.info(
            f"引擎初始化完成，已注册任务: {list(self._task_registry.keys())}",
            module_name=self.CHINESE_NAME
        )

    def _on_download_progress(self, model_name: str, downloaded_mb: float, total_mb: float):
        """接收模型下载进度，异步推送到前端"""
        percent = min(1.0, downloaded_mb / total_mb) if total_mb else 0
        # 获取主事件循环，从后台线程安全地提交协程
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 如果当前没有事件循环（比如在后台线程中），需要用其他方式获取
            # 这里假设引擎初始化时保存了主事件循环引用
            loop = self._main_event_loop
        asyncio.run_coroutine_threadsafe(
            self._send_download_progress(model_name, downloaded_mb, total_mb, percent),
            loop
        )

    async def _send_download_progress(self, model_name: str, downloaded_mb: float, total_mb: float, percent: float):
        logger.info(f"下载进度: {model_name} - {percent:.1%} ({downloaded_mb:.1f}MB/{total_mb:.1f}MB)",
                    module_name=self.CHINESE_NAME)
        try:
            sse_manager = get_sse_manager()
            await sse_manager.send_pipeline_event(
                task_id=ke.KEY_SYSTEM,
                event=ke.KEY_FEATURE_MODEL_DOWNLOAD_PROGRESS,
                data={
                    ke.KEY_TITLE: "模型下载",
                    ke.KEY_CONTENT: f"{model_name}",
                    ke.KEY_META: {
                        ke.KEY_STAGE: ke.KEY_FEATURE_MODEL_DOWNLOAD_PROGRESS,
                        ke.KEY_STATUS: ke.KEY_RUNNING,
                        ke.KEY_DOWNLOADED_MB: downloaded_mb,
                        ke.KEY_TOTAL_MB: total_mb,
                        ke.KEY_PERCENT: f"{percent:.1%}"
                    }
                }
            )
        except Exception as e:
            logger.error(f"下载进度推送失败: {e}", module_name=self.CHINESE_NAME)

    def _load_models_from_config(self):
        models_def = config.LOCAL_MODELS_DEFINITION
        for model_def in models_def:
            name = model_def[ke.KEY_NAME]
            modality = model_def.get(ke.KEY_MODALITY, ke.KEY_TEXT)
            loader_type = model_def[ke.KEY_LOADER_TYPE]
            estimated_mb = model_def.get(ke.KEY_ESTIMATED_MEMORY_MB, 800)

            if loader_type == ke.KEY_HUGGINGFACE_PIPELINE:
                task = model_def[ke.KEY_TASK]
                model_name_or_path = model_def[ke.KEY_MODEL]
                loader = lambda cache_dir, t=task, m=model_name_or_path, est=estimated_mb: load_huggingface_pipeline(
                    t, m, cache_dir, estimated_mb=est
                )
            else:
                raise ValueError(f"不支持的加载器类型: {loader_type}")

            self.model_pool.register(name, loader, estimated_mb)

            self._task_registry[name] = {
                ke.KEY_MODALITY: modality,
                ke.KEY_INFER: lambda *args, _name=name, **kwargs: self.model_pool.infer(_name, *args, **kwargs),
            }
            logger.info(
                f"动态注册模型: {name} (模态: {modality}, 预估内存: {estimated_mb}MB)",
                module_name=self.CHINESE_NAME
            )

    async def analyze(self, input_data: Any, tasks: List[str], modality: str = ke.KEY_TEXT, **extra_kwargs) -> Dict[
        str, Any]:
        selected = [t for t in tasks if
                    t in self._task_registry and self._task_registry[t][ke.KEY_MODALITY] == modality]
        logger.debug(f"执行分析: 模态={modality}, 任务={selected}", module_name=self.CHINESE_NAME)

        async def _run_one(task_name: str) -> Any:
            infer_func = self._task_registry[task_name][ke.KEY_INFER]
            return await asyncio.to_thread(infer_func, input_data)

        coro_tasks = [lambda t=t: _run_one(t) for t in selected]
        results = await self.local_model_concurrency.run_tasks(coro_tasks)
        return {name: result for name, result in zip(selected, results)}

    async def analyze_text(self, text: str, tasks: Optional[List[str]] = None, refine: bool = True) -> Dict[str, Any]:
        if tasks is None:
            tasks = [t.strip() for t in config.TEXT_ANALYSIS_TASKS.split(",") if t.strip()]

        # 1. 分词、关键词提取（只执行一次）
        words = self.text_tools.cut_words(text)
        keywords = self.text_tools.extract_keywords(text)

        # 2. 模型推理（当前只有 embedding）
        raw = await self.analyze(input_data=text, modality=ke.KEY_TEXT, tasks=tasks)

        # 3. 组装原始结果
        raw[ke.KEY_WORDS] = words
        raw[ke.KEY_KEYWORDS] = keywords
        raw[ke.KEY_TEXT] = text

        if not refine:
            return raw

        # 4. 提炼最终输出
        return self.refine_analysis(raw)

    async def get_embedding(self, text: str) -> Optional[Any]:
        """只计算文本向量，不做分词和关键词提取。"""
        if ke.KEY_EMBEDDING not in self._task_registry:
            return None
        infer_func = self._task_registry[ke.KEY_EMBEDDING][ke.KEY_INFER]
        return await asyncio.to_thread(infer_func, text)

    def _alert_callback(self, message: str, context: Dict[str, Any]):
        asyncio.create_task(self._send_alert_async(message, context))

    async def _send_alert_async(self, message: str, context: Dict[str, Any]):
        try:
            sse_manager = get_sse_manager()
            await sse_manager.send_pipeline_event(
                task_id=ke.KEY_SYSTEM,
                event=ke.KEY_MEMORY_ALERT,
                data={
                    ke.KEY_TITLE: "⚠️ 模型池内存告警",
                    ke.KEY_CONTENT: message,
                    ke.KEY_META: context
                }
            )
            logger.info("SSE 内存告警已发送", module_name=self.CHINESE_NAME)
        except Exception as e:
            logger.error(f"SSE 内存告警发送失败: {e}", module_name=self.CHINESE_NAME)

        try:
            notifiers = get_notifiers()
            if notifiers:
                for notifier in notifiers:
                    await notifier.send(
                        title="⚠️ 模型池内存告警",
                        message=message,
                        file_path=None
                    )
                logger.info("传统通知已发送", module_name=self.CHINESE_NAME)
        except Exception as e:
            logger.error(f"传统通知发送失败: {e}", module_name=self.CHINESE_NAME)

    def refine_analysis(self, raw_result: Dict[str, Any]) -> Dict[str, Any]:
        words = raw_result.get(ke.KEY_WORDS, [])
        keywords = raw_result.get(ke.KEY_KEYWORDS, [])
        text = raw_result.get(ke.KEY_TEXT, '')
        embedding = raw_result.get(ke.KEY_EMBEDDING)

        stats = self.text_tools.get_text_stats(text, words, keywords)

        parts = []

        # 基础统计信息
        char_count = stats.get('总字符数', 0)
        word_count = stats.get('总词数', 0)
        if char_count or word_count:
            parts.append(f"文本规模：{char_count}字符，{word_count}词")

        # 关键主题词
        keywords = stats.get('关键主题词', [])
        if keywords:
            parts.append(f"关键主题词：{'、'.join(keywords[:config.VOCAB_FILTER_MAX_WORDS])}")

        # 分类实体
        for key, value in stats.items():
            if key not in ["总字符数", "总词数", "关键主题词", "高频词"] and isinstance(value, list):
                parts.append(f"{key}：{'、'.join(value[:config.VOCAB_FILTER_MAX_WORDS])}")

        # 高频词
        freq_words = stats.get('高频词', [])
        if freq_words:
            parts.append(f"高频词汇：{'、'.join(freq_words[:config.VOCAB_FILTER_MAX_FREQWORDS])}")

        return {
            ke.KEY_NLP_SUMMARY: '；'.join(parts) if parts else "",
            ke.KEY_EMBEDDING: embedding,
            ke.KEY_KEYWORDS: keywords
        }
