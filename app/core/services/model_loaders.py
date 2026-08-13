import os
import threading
import time
from typing import Any, Callable, Optional
from transformers import BertTokenizer
import torch
from app.common import keys as ke
from transformers import AutoModel
from modelscope import HubApi
from app.utils.logger import LoggerManager as logger
from modelscope.hub.snapshot_download import snapshot_download

CHINESE_NAME = "模型加载器"

# 全局进度回调，由引擎注入
_download_progress_callback: Optional[Callable[[str, float, float], None]] = None


def set_download_progress_callback(cb: Optional[Callable[[str, float, float], None]]):
    """设置模型下载进度回调（模型名, 已下载(MB), 总大小(MB)）"""
    global _download_progress_callback
    _download_progress_callback = cb


def _ensure_model_cached(model_id: str, cache_dir: str) -> bool:
    """
    检查模型是否已完整缓存（直接检查文件系统）。
    依据：
    - ModelScope 缓存目录存在 {cache_dir}/{model_id}/ 目录
    - 目录中至少有 model 相关文件（configuration.json / config.json / asset 等）
    """
    target_dir = os.path.join(cache_dir, model_id)
    if not os.path.isdir(target_dir):
        return False
    # 目录必须非空，且至少有一个有效文件大小 > 1MB 的文件或者存在配置文件
    has_config = (
        os.path.exists(os.path.join(target_dir, "configuration.json"))
        or os.path.exists(os.path.join(target_dir, "config.json"))
        or os.path.exists(os.path.join(target_dir, "config", "config.json"))
    )
    if has_config:
        return True
    # 兜底：检查目录下是否有 > 1MB 的文件（表示模型权重已下载）
    for root, dirs, files in os.walk(target_dir):
        for f in files:
            fp = os.path.join(root, f)
            if os.path.isfile(fp) and os.path.getsize(fp) > 1024 * 1024:
                return True
    return False


def _get_accurate_total_size(model_id: str) -> int:
    """
    通过 ModelScope API 获取模型文件列表，计算总字节数。
    若失败，返回 0。
    """
    try:
        api = HubApi()
        files = api.get_model_files(model_id, recursive=True)
        total = sum(f['Size'] for f in files if f['Type'] == 'blob')
        return total
    except Exception as e:
        logger.warning(f"无法获取模型 {model_id} 的准确文件大小，将使用预估值: {e}", module_name=CHINESE_NAME)
        return 0


def _monitor_download_directory(
        dir_path: str,
        model_name: str,
        stop_event: threading.Event,
        expected_total_bytes: int = 0,
):
    """后台轮询目录大小，每跨越 5% 进度时通过全局回调推送一次"""
    last_reported_percent = -1  # 上一次推送的百分比（整数）
    downloaded_mb = 0.0
    total_mb = expected_total_bytes / (1024 * 1024) if expected_total_bytes else 0

    while not stop_event.is_set():
        # 计算当前已下载大小
        downloaded_bytes = 0
        if os.path.exists(dir_path):
            for root, dirs, files in os.walk(dir_path):
                for file in files:
                    fp = os.path.join(root, file)
                    if os.path.isfile(fp):
                        downloaded_bytes += os.path.getsize(fp)

        downloaded_mb = downloaded_bytes / (1024 * 1024)
        if total_mb > 0:
            current_percent = int((downloaded_bytes / expected_total_bytes) * 100)
        else:
            current_percent = 0

        # 仅在跨越 5% 的倍数时推送（包括 0% 的首次推送）
        if current_percent // 5 > last_reported_percent // 5 or last_reported_percent == -1:
            if _download_progress_callback:
                _download_progress_callback(model_name, downloaded_mb, total_mb)
            last_reported_percent = current_percent

        time.sleep(0.5)  # 轮询间隔

    # 下载结束后强制推送一次最终进度（确保100%被发送）
    if _download_progress_callback:
        _download_progress_callback(model_name, downloaded_mb, total_mb)


def load_huggingface_pipeline(
        task: str,
        model: str,
        cache_dir: str,
        estimated_mb: int = 500
) -> Callable[..., Any]:
    """
    统一的模型加载器，当前只支持:
    - feature-extraction: 文本向量（GTE 模型）
    """
    os.environ["MODELSCOPE_ENDPOINT"] = "https://modelscope.cn"
    logger.info(f"准备加载模型: {model}，任务: {task}", module_name=CHINESE_NAME)

    # 下载模型
    target_dir = os.path.join(cache_dir, model)
    if not _ensure_model_cached(model, cache_dir):
        logger.info(f"模型 {model} 未缓存，开始下载到 {target_dir}", module_name=CHINESE_NAME)
        accurate_bytes = _get_accurate_total_size(model)
        expected_total_bytes = accurate_bytes if accurate_bytes > 0 else estimated_mb * 1024 * 1024
        logger.info(f"模型 {model} 大小信息 - 预估: {estimated_mb}MB, "
                    f"API获取: {accurate_bytes / (1024 * 1024):.2f}MB, "
                    f"最终使用: {expected_total_bytes / (1024 * 1024):.2f}MB",
                    module_name=CHINESE_NAME)

        stop_event = threading.Event()
        monitor_thread = threading.Thread(
            target=_monitor_download_directory,
            args=(target_dir, model, stop_event, expected_total_bytes),
            daemon=True,
        )
        try:
            monitor_thread.start()
            snapshot_download(
                model_id=model,
                local_dir=target_dir,
                max_workers=1,
            )
            logger.info(f"模型 {model} 下载完成", module_name=CHINESE_NAME)
        except Exception as e:
            logger.error(f"下载失败: {e}", module_name=CHINESE_NAME)
            raise
        finally:
            stop_event.set()
            monitor_thread.join(timeout=2)
    else:
        logger.debug(f"模型 {model} 已缓存，直接加载", module_name=CHINESE_NAME)

    # 根据任务类型分发
    logger.info(f"开始加载模型组件: {model}", module_name=CHINESE_NAME)

    if task == ke.KEY_FEATURE_EXTRACTION:
        # GTE 文本向量模型
        tokenizer = BertTokenizer.from_pretrained(target_dir, local_files_only=True, use_fast=False)
        base_model = AutoModel.from_pretrained(target_dir, local_files_only=True)

        def embedding_inference(text: str) -> torch.Tensor:
            # 长文本分块处理
            max_len = 510
            stride = 256
            inputs = tokenizer(
                text,
                return_tensors=ke.KEY_PT,
                truncation=True,
                max_length=max_len,
                stride=stride,
                return_overflowing_tokens=True,
                padding=True
            )
            num_chunks = len(inputs[ke.KEY_INPUT_IDS])
            chunk_vecs = []
            for i in range(num_chunks):
                # 仅保留模型能接受的三个关键字段，避免传入 overflow 等额外参数
                chunk_inputs = {
                    ke.KEY_INPUT_IDS: inputs[ke.KEY_INPUT_IDS][i:i + 1],
                    ke.KEY_ATTENTION_MASK: inputs[ke.KEY_ATTENTION_MASK][i:i + 1],
                    ke.KEY_TOKEN_TYPE_IDS: inputs.get(ke.KEY_TOKEN_TYPE_IDS, None)
                }
                # 若 token_type_ids 不存在则移除
                if chunk_inputs[ke.KEY_TOKEN_TYPE_IDS] is not None:
                    chunk_inputs[ke.KEY_TOKEN_TYPE_IDS] = chunk_inputs[ke.KEY_TOKEN_TYPE_IDS][i:i + 1]
                else:
                    del chunk_inputs[ke.KEY_TOKEN_TYPE_IDS]
                outputs = base_model(**chunk_inputs)
                # 取平均池化
                hidden = outputs.last_hidden_state.squeeze(0)
                chunk_vec = hidden.mean(dim=0)
                chunk_vecs.append(chunk_vec)
            if chunk_vecs:
                avg_vec = torch.stack(chunk_vecs).mean(dim=0)
            else:
                avg_vec = torch.zeros(base_model.config.hidden_size)
            return avg_vec.detach().numpy()

        logger.info(f"GTE 模型加载完成: {model}", module_name=CHINESE_NAME)
        return embedding_inference

    raise ValueError(f"不支持的任务类型: {task}")
