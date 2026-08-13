import gc
import threading
from collections import OrderedDict
from typing import Callable, Dict, Any, Optional

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    psutil = None  # type: ignore[assignment]
    _HAS_PSUTIL = False

from app.common import keys as ke
from app.config.config import config
from app.utils.logger import LoggerManager as logger


class ModelPoolManager:
    """
    通用模型池管理器（文本、图像、音频等任意轻量模型）
    - LRU 缓存 + 按需加载
    - 进程内存监控 + 自动卸载 + 告警通知
    - 所有参数从全局 config 实时读取（支持热重载）
    """

    CHINESE_NAME = "模型池管理器"

    def __init__(
            self,
            alert_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        """
        Args:
            alert_callback: 告警回调函数，接收 (message: str, context: dict)
        """
        self.alert_callback = alert_callback
        self._loaded_models: OrderedDict[str, Any] = OrderedDict()
        self._model_memory_mb: Dict[str, float] = {}  # 实测内存占用
        self._loaders: Dict[str, Callable[[str], Any]] = {}
        self._lock = threading.RLock()

        # 后台监控线程
        self._stop_monitor = threading.Event()
        self._monitor_thread = threading.Thread(target=self._memory_monitor_loop, daemon=True)
        self._monitor_thread.start()

        logger.info("模型池管理器已启动，配置来源：全局 config", module_name=self.CHINESE_NAME)

    # ---------- 注册 ----------
    def register(self, model_name: str, loader: Callable[[str], Any], estimated_size_mb: float = 800):
        """注册模型：名称、加载函数、预估内存(MB)"""
        with self._lock:
            self._loaders[model_name] = loader
            self._model_memory_mb[model_name] = estimated_size_mb
        logger.info(f"注册模型: {model_name} (预估 {estimated_size_mb}MB)", module_name=self.CHINESE_NAME)

    # ---------- 获取模型 ----------
    def get_model(self, model_name: str) -> Any:
        """
        获取模型实例，自动加载并缓存，线程安全。
        如果内存不足，会按 LRU 自动卸载旧模型。
        """
        with self._lock:
            if model_name in self._loaded_models:
                self._loaded_models.move_to_end(model_name)
                logger.debug(f"命中缓存: {model_name}", module_name=self.CHINESE_NAME)
                return self._loaded_models[model_name]

            if model_name not in self._loaders:
                raise KeyError(f"模型 {model_name} 未注册")

            self._ensure_memory_available(model_name)
            model = self._safe_load(model_name)
            self._loaded_models[model_name] = model
            return model

    def infer(self, model_name: str, *args, **kwargs) -> Any:
        """直接调用模型推理（不控制并发，外层由 ConcurrencyManager 控制）"""
        model = self.get_model(model_name)
        return model(*args, **kwargs)

    # ---------- 手动卸载 ----------
    def evict(self, model_name: str) -> bool:
        with self._lock:
            if model_name in self._loaded_models:
                del self._loaded_models[model_name]
                gc.collect()
                logger.info(f"手动卸载模型: {model_name}", module_name=self.CHINESE_NAME)
                return True
            return False

    # ---------- 状态查询 ----------
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                ke.KEY_LOADED_MODELS: list(self._loaded_models.keys()),
                ke.KEY_MODEL_MEMORY_MB: dict(self._model_memory_mb),
                ke.KEY_PROCESS_MEMORY_MB: self._current_process_memory_mb(),
                ke.KEY_MAX_PROCESS_MEMORY_MB: config.LOCAL_MODEL_MAX_MEMORY_MB,
                ke.KEY_THRESHOLD: config.LOCAL_MODEL_MEMORY_THRESHOLD
            }

    def shutdown(self):
        """停止后台监控线程"""
        self._stop_monitor.set()
        logger.info("监控线程已停止", module_name=self.CHINESE_NAME)

    def _safe_load(self, model_name: str) -> Any:
        loader = self._loaders[model_name]
        mem_before = self._current_process_memory_mb()
        try:
            model = loader(config.MODEL_DIR)
        except Exception as e:
            logger.error(f"加载模型 {model_name} 失败: {e}", module_name=self.CHINESE_NAME)
            raise
        mem_after = self._current_process_memory_mb()
        actual = max(mem_after - mem_before, 1.0)
        self._model_memory_mb[model_name] = actual
        logger.info(
            f"模型加载完成: {model_name}，内存增加 {actual:.1f}MB，当前总内存 {mem_after:.1f}MB",
            module_name=self.CHINESE_NAME
        )
        return model

    @staticmethod
    def _current_process_memory_mb() -> float:
        """获取当前进程 RSS（常驻内存），单位 MB。

        优先 psutil（若已安装），回退 /proc/self/status 的 VmRSS（Linux 零依赖）。
        """
        if _HAS_PSUTIL:
            try:
                return psutil.Process().memory_info().rss / (1024 * 1024)
            except Exception:
                return 0.0
        # 回退：读取 /proc/self/status 的 VmRSS（Linux 容器零依赖）
        try:
            with open("/proc/self/status", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        # 格式: "VmRSS:      12345 kB"
                        return int(line.split()[1]) / 1024  # kB → MB
        except Exception:
            pass
        return 0.0

    def _ensure_memory_available(self, next_model: str):
        """加载前确保内存足够，否则按 LRU 连续卸载直到满足条件或达到最大尝试次数"""
        estimated = self._model_memory_mb.get(next_model, 1500.0)
        max_attempts = config.LOCAL_MODEL_MAX_EVICTION_ATTEMPTS
        for attempt in range(max_attempts):
            current = self._current_process_memory_mb()
            if current + estimated <= config.LOCAL_MODEL_MAX_MEMORY_MB:
                return
            if not self._loaded_models:
                break
            oldest = next(iter(self._loaded_models))
            del self._loaded_models[oldest]
            gc.collect()
            logger.warning(
                f"内存不足，卸载最久未用模型: {oldest} (当前 {current:.1f}MB, 预估 {estimated}MB)",
                module_name=self.CHINESE_NAME
            )
            self._send_alert(
                f"加载新模型时内存不足，已自动卸载最久未用模型: {oldest}。"  # 模型名直接放进消息
                f"当前内存 {current:.1f}MB，预估需 {estimated:.1f}MB，上限 {config.LOCAL_MODEL_MAX_MEMORY_MB}MB。",
                context={
                    ke.KEY_STAGE: ke.KEY_MEMORY_ALERT,
                    ke.KEY_STATUS: ke.KEY_RUNNING
                }
            )
        raise MemoryError(
            f"无法加载 {next_model}：已连续卸载 {max_attempts} 个模型，"
            f"当前内存仍不足（{self._current_process_memory_mb():.1f}MB / 需 {estimated}MB）"
        )

    # ---------- 后台监控 ----------
    def _memory_monitor_loop(self):
        while not self._stop_monitor.is_set():
            self._stop_monitor.wait(config.LOCAL_MODEL_MONITOR_INTERVAL)
            try:
                self._check_high_memory()
            except Exception as e:
                logger.exception(f"内存监控异常: {str(e)}", module_name=self.CHINESE_NAME)

    def _check_high_memory(self):
        current = self._current_process_memory_mb()
        max_mem = config.LOCAL_MODEL_MAX_MEMORY_MB
        threshold = config.LOCAL_MODEL_MEMORY_THRESHOLD
        if current >= max_mem * threshold:
            # 只卸载一个最久未用模型，避免过度反应
            self._force_evict_one(
                f"内存高位告警 (≥{threshold:.0%}): {current:.1f}MB"
            )

    def _force_evict_one(self, reason: str):
        with self._lock:
            if not self._loaded_models:
                return
            oldest = next(iter(self._loaded_models))
            del self._loaded_models[oldest]
            gc.collect()
            logger.warning(f"{reason}，已卸载: {oldest}", module_name=self.CHINESE_NAME)
            self._send_alert(
                f"{reason}，已自动卸载模型: {oldest}。"
                f"当前内存 {self._current_process_memory_mb():.1f}MB，"
                f"上限 {config.LOCAL_MODEL_MAX_MEMORY_MB}MB，"
                f"触发阈值 {config.LOCAL_MODEL_MEMORY_THRESHOLD:.0%}。",
                context={
                    ke.KEY_STAGE: ke.KEY_MEMORY_ALERT,
                    ke.KEY_STATUS: ke.KEY_RUNNING
                }
            )

    # ---------- 通知 ----------
    def _send_alert(self, message: str, context: Optional[Dict] = None):
        if self.alert_callback:
            try:
                self.alert_callback(message, context or {})
            except Exception as e:
                logger.exception(f"告警回调执行失败: {str(e)}", module_name=self.CHINESE_NAME)


# ---------- 模块级单例 ----------
_model_pool_instance: Optional["ModelPoolManager"] = None


def get_model_pool() -> ModelPoolManager:
    """获取模型池全局单例（懒加载）"""
    global _model_pool_instance
    if _model_pool_instance is None:
        _model_pool_instance = ModelPoolManager()
        _register_models_from_config(_model_pool_instance)
    return _model_pool_instance


def _register_models_from_config(pool: ModelPoolManager) -> None:
    """从全局配置注册模型到池"""
    from app.core.services.model_loaders import load_huggingface_pipeline

    models_def = config.LOCAL_MODELS_DEFINITION
    for model_def in models_def:
        name = model_def.get(ke.KEY_NAME, "")
        modality = model_def.get(ke.KEY_MODALITY, ke.KEY_TEXT)
        loader_type = model_def.get(ke.KEY_LOADER_TYPE, "")
        estimated_mb = model_def.get(ke.KEY_ESTIMATED_MEMORY_MB, 800)

        # huggingface_pipeline 和 modelscope_pipeline 都走统一加载器，
        # 由 load_huggingface_pipeline 内部根据任务类型处理
        if loader_type in (ke.KEY_HUGGINGFACE_PIPELINE, ke.KEY_MODELSCOPE_PIPELINE):
            task = model_def.get(ke.KEY_TASK, "")
            model_name_or_path = model_def.get(ke.KEY_MODEL, "")
            loader = lambda cache_dir, t=task, m=model_name_or_path, est=estimated_mb: load_huggingface_pipeline(
                t, m, cache_dir, estimated_mb=est
            )
        else:
            logger.warning(f"跳过未注册的模型类型: {name} (loader_type={loader_type})", module_name="模型池")
            continue

        pool.register(name, loader, estimated_mb)
        logger.info(f"注册模型: {name} (模态: {modality}, 预估: {estimated_mb}MB, 加载器: {loader_type})", module_name="模型池")
