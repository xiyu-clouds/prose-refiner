import asyncio
import math
import os
import time
import requests
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Request, HTTPException, Query, Body
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, StreamingResponse
from starlette.staticfiles import StaticFiles
from app.common import keys as ke
from app.common import values as va
from app.common import paths as pa
from app.common.enums import TreeNode, FileUpdateRequest
from app.common.llm_constants import LLMVendor, LLMModel
from app.config.config import config
from app.core.prompt.prompt_builder import PromptBuilder
from app.core.services.pipeline_orchestrator import PipelineOrchestrator
from app.core.services.sse_manager import get_sse_manager
from app.core.steps.basic.config_loader import ConfigLoader
from app.utils.file_util import FileUtil
from app.utils.logger import LoggerManager as logger
from app.utils.config_validators import ConfigValidator as cv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schedule.scheduler_manager import SchedulerManager

logger.inject_config(config)
file_util = FileUtil()
config_loader = ConfigLoader()
builder = PromptBuilder()
CHINESE_NAME = "FastAPI启动中心"
scheduler_instance: Optional['SchedulerManager'] = None


def is_service_ready() -> bool:
    """判断服务是否已就绪（配置加载完成且 LLM 后端合法）"""
    return (
            hasattr(config, 'LLM_DEFAULT_VENDOR') and
            config.LLM_DEFAULT_VENDOR in LLMVendor.all()
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """这里的函数参数不能省"""
    logger.info("🚀 系统启动中...", module_name=CHINESE_NAME)
    global scheduler_instance
    from app.db.schema import init_database_schema
    from app.schedule import start_scheduled_tasks
    from app.core.meta.executor import start_metacognition_workers
    from app.core.meta.executor import shutdown_metacognition_workers
    from app.registry.global_singleton_registry import GlobalSingletonRegistry
    _ = config.LLM_DEFAULT_VENDOR  # 触发加载
    logger.info(f"🟢 配置就绪：LLM={config.LLM_DEFAULT_VENDOR}", module_name=CHINESE_NAME)

    if not config.PATH_FILE_INDEX_HTML.exists():
        logger.warning("⚠️ 主页面 index.html 不存在！", module_name=CHINESE_NAME)

    # 初始化数据库表结构
    init_database_schema()

    # 启动元认知工作者（消费者）
    start_metacognition_workers()

    # 启动定时任务调度器（生产者）
    scheduler_instance = start_scheduled_tasks()

    # 启动 SSE 代理
    sse_manager = get_sse_manager()
    sse_manager.start_proxy()

    # 预编译prompt
    builder.initialize()

    logger.info("🎉 所有启动任务完成", module_name=CHINESE_NAME)

    yield

    logger.info("🛑 系统正在关闭，执行优雅停机...", module_name=CHINESE_NAME)

    await shutdown_metacognition_workers(graceful=True)

    sse_manager.stop_proxy()

    if scheduler_instance:
        scheduler_instance.shutdown()

    try:
        registry = await GlobalSingletonRegistry.get_instance()
        await registry.reload_all()
        logger.info("✅ 全局注册中心资源已安全重置", module_name=CHINESE_NAME)
    except Exception as e:
        logger.error(f"💥 关闭全局注册中心异常：{e}", exc_info=True)

    logger.info("🏁 系统完全退出", module_name=CHINESE_NAME)


app = FastAPI(lifespan=lifespan, title="心海")

# 挂载静态文件
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {ke.KEY_REQUEST: request})


@app.get("/novel", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("novel.html", {ke.KEY_REQUEST: request})


@app.get("/resources", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("resources.html", {ke.KEY_REQUEST: request})


@app.get("/config", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("config.html", {ke.KEY_REQUEST: request})


@app.get("/prompt", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("prompt.html", {ke.KEY_REQUEST: request})


@app.get("/plugin", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("plugin.html", {ke.KEY_REQUEST: request})


@app.get("/dao", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("dao.html", {ke.KEY_REQUEST: request})


@app.get("/rule", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("rule.html", {ke.KEY_REQUEST: request})


# 健康检查
@app.get("/api/healthz")
async def health_check():
    if is_service_ready():
        return JSONResponse(status_code=200, content={ke.KEY_STATUS: ke.KEY_READY})
    raise HTTPException(status_code=503, detail="Service not ready")


@app.get("/api/config")
async def get_config_api():
    logger.info("📥 收到获取配置的请求", module_name=CHINESE_NAME)
    try:
        data = file_util.read_json_file(config.PATH_FILE_SETTINGS_JSON)
        logger.info("📄 配置文件读取成功", module_name=CHINESE_NAME)
        return data
    except Exception as e:
        logger.error(f"❌ 读取配置文件失败：{e}", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"读取配置失败: {str(e)}")


@app.post("/api/config")
async def save_config_api(request: Request):
    logger.info("📥 收到保存配置的请求", module_name=CHINESE_NAME)
    try:
        new_config = await request.json()
        if not isinstance(new_config, dict):
            raise HTTPException(status_code=400, detail="配置必须是 JSON 对象")

        errors = _validate_and_normalize_config(new_config)

        if errors:
            error_msg = "配置校验失败:\n" + "\n".join(errors)
            logger.warning(f"⚠️ 配置校验失败: {error_msg}", module_name=CHINESE_NAME)
            raise HTTPException(status_code=400, detail=error_msg)

        # 保存并重载
        file_util.write_json(new_config, config.MOUNT_PATH_FILE_SETTINGS_JSON)
        logger.info("💾 配置已写入文件", module_name=CHINESE_NAME)
        await config.reload()

        return {ke.KEY_STATUS: ke.KEY_SUCCESS, ke.KEY_MESSAGE: "配置已保存并重载"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("💥 保存配置时发生未预期错误")
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


def _validate_and_normalize_config(data: dict) -> list[str]:
    errors = []
    d = data

    # 浮点字段标准化
    for field in ["XINHAI_WATERMARK_OPACITY", "XINHAI_METACOGNITION_QUEUE_HIGH_WATERMARK", "XINHAI_METACOGNITION_QUEUE_MID_WATERMARK", "XINHAI_FULL_TEXT_TOKENS_RATIO"]:
        if field in d and isinstance(d[field], int):
            d[field] = float(d[field])

    # ==================== 校验规则定义 ====================
    checks = [
        # 1. LLM 基础
        (cv.str_check, ("XINHAI_LLM_DEFAULT_VENDOR",)),
        (cv.str_check, ("XINHAI_LLM_DEFAULT_MODEL",)),
        (cv.model_valid_check, ("XINHAI_LLM_DEFAULT_MODEL", LLMModel.all())),
        (cv.int_check, ("XINHAI_LLM_API_TIMEOUT", 1, 600)),
        (cv.str_check, ("XINHAI_LLM_DEEPSEEK_API_KEY",)),

        # 2. LangSmith
        (cv.bool_check, ("XINHAI_LANGSMITH_ENABLED",)),
        (cv.str_check, ("XINHAI_LANGSMITH_API_KEY",)),
        (cv.str_check, ("XINHAI_LANGSMITH_PROJECT",)),
        (cv.str_check, ("XINHAI_LANGSMITH_ENDPOINT",)),

        # 3. 元认知总控
        (cv.bool_check, ("XINHAI_METACOGNITION_ENABLED",)),
        (cv.int_check, ("XINHAI_METACOGNITION_MAX_LLM_CALLS", 30, 100)),
        (cv.int_check, ("XINHAI_METACOGNITION_MAX_DEBATE_ROUNDS", 1, 50)),
        (cv.int_check, ("XINHAI_METACOGNITION_QUEUE_MAXSIZE", 10, 200)),
        (cv.int_check, ("XINHAI_METACOGNITION_MAX_CONCURRENT_LOOPS", 1, 10)),
        (cv.int_check, ("XINHAI_METACOGNITION_EXPIRES_AT", 120, 3600)),
        (cv.int_check, ("XINHAI_METACOGNITION_MAX_CHARS_PER_TURN", 200, 3000)),
        (cv.int_check, ("XINHAI_METACOGNITION_MAX_DEBATE_TURNS_TO_INJECT", 1, 5)),
        (cv.int_check, ("XINHAI_METACOGNITION_MAX_ISSUES_TO_DISPLAY", 1, 15)),
        (cv.int_check, ("XINHAI_METACOGNITION_DATA_LOADER_DEFAULT_LEVEL", 0, 2)),

        # 4. 队列监控
        (cv.int_check, ("XINHAI_METACOGNITION_MONITOR_ALERT_COOLDOWN", 0, 7200)),
        (cv.float_check, ("XINHAI_METACOGNITION_QUEUE_HIGH_WATERMARK", 0.5, 1)),
        (cv.float_check, ("XINHAI_METACOGNITION_QUEUE_MID_WATERMARK", 0.1, 0.8)),
        (cv.int_check, ("XINHAI_METACOGNITION_QUEUE_CHECK_INTERVAL", 10, 600)),

        # 5. 段落与步骤级 Token
        (cv.int_check, ("XINHAI_METACOGNITION_TARGET_CHARS", 500, 1500)),
        (cv.int_check, ("XINHAI_METACOGNITION_TOLERANCE", 0, 300)),
        (cv.int_check, ("XINHAI_POLISH_AUXILIARY_TASK_LIMIT", 1, 15)),

        # 6. 日志
        (cv.int_check, ("XINHAI_LOG_KEEP_DAYS", 1, 365)),
        (cv.int_check, ("XINHAI_LOG_MAX_BYTES", 1048576, 1073741824)),
        (cv.int_check, ("XINHAI_LOG_BACKUP_COUNT", 1, 50)),

        # 7. 并发控制
        (cv.int_check, ("XINHAI_MAX_LLM_STEP_CONCURRENCY", 1, 30)),
        (cv.int_check, ("XINHAI_CURRENT_LLM_STEP_CONCURRENCY", 1, 30)),
        (cv.int_check, ("XINHAI_MEDIUM_LLM_STEP_CONCURRENCY", 1, 30)),
        (cv.int_check, ("XINHAI_MAX_BATCH_TASK_CONCURRENCY", 1, 15)),
        (cv.int_check, ("XINHAI_CURRENT_BATCH_TASK_CONCURRENCY", 1, 15)),
        (cv.int_check, ("XINHAI_MEDIUM_BATCH_TASK_CONCURRENCY", 1, 15)),
        (cv.int_check, ("XINHAI_MAX_BATCH_TASKS", 1, 200)),
        (cv.int_check, ("XINHAI_MAX_BATCH_FILE_SIZE_BYTES", 1024, 104857600)),

        # 8. 重试与全局
        (cv.int_check, ("XINHAI_GLOBAL_MAX_RETRIES", 1, 100000)),
        (cv.int_check, ("XINHAI_GLOBAL_RETRY_TIMEOUT", 60, 7200)),
        (cv.bool_check, ("XINHAI_GLOBAL_ENABLE_METRICS",)),

        # 9. 存储
        (cv.str_check, ("XINHAI_STORAGE_BACKEND",)),
        (cv.int_check, ("XINHAI_LLM_CACHE_MAX_SIZE", 128, 65536)),
        (cv.int_check, ("XINHAI_LLM_CACHE_TTL", 0, 2592000)),
        (cv.str_check, ("XINHAI_REDIS_HOST",)),
        (cv.int_check, ("XINHAI_REDIS_PORT", 1, 65535)),
        (cv.int_check, ("XINHAI_REDIS_DB", 0, 15)),
        (cv.str_check, ("XINHAI_REDIS_PASSWORD",)),
        (cv.int_check, ("XINHAI_REDIS_TIMEOUT", 1, 30)),

        # 10. 水印
        (cv.bool_check, ("XINHAI_WATERMARK_ENABLED",)),
        (cv.str_check, ("XINHAI_WATERMARK_TEXT",)),
        (cv.str_check, ("XINHAI_WATERMARK_COLOR",)),
        (cv.float_check, ("XINHAI_WATERMARK_OPACITY", 0, 1)),
        (cv.int_check, ("XINHAI_WATERMARK_FONT_SIZE", 8, 120)),
        (cv.int_check, ("XINHAI_WATERMARK_ANGLE", -180, 180)),
        (cv.int_check, ("XINHAI_WATERMARK_SPACING_COLS", 1, 20)),
        (cv.int_check, ("XINHAI_WATERMARK_SPACING_ROWS", 1, 20)),
        (cv.int_check, ("XINHAI_WATERMARK_PADDING", 0, 200)),

        # 11. 通知与挂起
        (cv.bool_check, ("XINHAI_NOTIFICATION_ENABLED",)),
        (cv.channels_valid_check, ("XINHAI_NOTIFICATION_CHANNELS", va.VAL_NOTIFICATION_CHANNELS)),
        (cv.str_check, ("XINHAI_EMAIL_SMTP_SERVER",)),
        (cv.int_check, ("XINHAI_EMAIL_PORT", 1, 65535)),
        (cv.str_check, ("XINHAI_EMAIL_USERNAME",)),
        (cv.str_check, ("XINHAI_EMAIL_PASSWORD",)),
        (cv.comma_separated_str_list_check, ("XINHAI_EMAIL_TO",)),
        (cv.comma_separated_str_list_check, ("XINHAI_FEISHU_AT_USER_IDS",)),
        (cv.comma_separated_str_list_check, ("XINHAI_WECOM_AT_USER_IDS",)),
        (cv.str_check, ("XINHAI_FEISHU_WEBHOOK_URL",)),
        (cv.str_check, ("XINHAI_WECOM_WEBHOOK_URL",)),
        (cv.int_check, ("XINHAI_SUSPEND_TIMEOUT_SECONDS", 60, 604800)),

        # 12. 图片平台
        (cv.str_check, ("XINHAI_UNSPLASH_ACCESS_KEY",)),
        (cv.str_check, ("XINHAI_UNSPLASH_BASIC_PATH",)),
        (cv.str_check, ("XINHAI_PEXELS_ACCESS_KEY",)),
        (cv.str_check, ("XINHAI_PEXELS_BASIC_PATH",)),

        # 13. Ollama
        (cv.bool_check, ("XINHAI_OLLAMA_ENABLED",)),
        (cv.str_check, ("XINHAI_OLLAMA_BASE_URL",)),
        (cv.str_check, ("XINHAI_OLLAMA_MODEL",)),
        (cv.dict_check, ("XINHAI_OLLAMA_PARAMS",)),
        (cv.int_check, ("XINHAI_OLLAMA_TIMEOUT", 60, 1800)),

        # 14. 报告
        (cv.str_check, ("XINHAI_TEXT_REPORT_TITLE",)),

        # 15. SSE
        (cv.str_check, ("XINHAI_PROXY_BACKEND_SSE_URL",)),
        (cv.int_check, ("XINHAI_SSE_HEARTBEAT_INTERVAL", 10, 120)),

        # 16. token扩容倍数
        (cv.float_check, ("XINHAI_MAX_TOKENS_EXPANSION_FACTOR", 1.0, 10.0)),
        (cv.float_check, ("XINHAI_FULL_TEXT_TOKENS_RATIO", 1.0, 10.0)),

        # 17. 首页卡片配置
        (cv.int_check, ("XINHAI_IMAGE_COUNT", 38, 1000)),
        (cv.int_check, ("XINHAI_REFRESH_INTERVAL_MS", 30000, 7200000)),

        (cv.int_check, ("XINHAI_MAX_LENGTH_RETRIES", 1, 10)),
        (cv.float_check, ("XINHAI_FACTOR_INCREMENT", 0.1, 1.0)),

        (cv.bool_check, ("XINHAI_REASONING_AUTO_INJECT",)),
        (cv.dict_check, ("XINHAI_REASONING_EFFORT_MAP",)),
    ]

    # ==================== 执行校验 ====================
    cv.run_checks(errors, d, checks)

    # ==================== 嵌套结构校验（保留原有精细逻辑） ====================
    llm_params = d.get("XINHAI_LLM_PARAMS")
    if llm_params is not None:
        if not isinstance(llm_params, dict):
            errors.append("XINHAI_LLM_PARAMS 必须是字典")
        else:
            for k, v_min, v_max in [("temperature", 0, 1), ("max_tokens", 1, 100000), ("top_p", 0, 1)]:
                if k in llm_params:
                    val = llm_params[k]
                    if not isinstance(val, (int, float)) or val < v_min or val > v_max:
                        errors.append(f"XINHAI_LLM_PARAMS.{k} 必须是 {v_min}-{v_max} 的数字")
            if "response_format" in llm_params and not isinstance(llm_params["response_format"], dict):
                errors.append("XINHAI_LLM_PARAMS.response_format 必须是字典")
            if "stop" in llm_params and not isinstance(llm_params["stop"], list):
                errors.append("XINHAI_LLM_PARAMS.stop 必须是列表")

    retry_cfg = d.get("XINHAI_DEFAULT_RETRY_CONFIG")
    if retry_cfg is not None:
        if not isinstance(retry_cfg, dict):
            errors.append("XINHAI_DEFAULT_RETRY_CONFIG 必须是字典")
        else:
            if "max_retries" in retry_cfg:
                v = retry_cfg["max_retries"]
                if not isinstance(v, int) or v < 0 or v > 20:
                    errors.append("XINHAI_DEFAULT_RETRY_CONFIG.max_retries 必须是 0-20 的整数")
            if "enable_exp_backoff" in retry_cfg and not isinstance(retry_cfg["enable_exp_backoff"], bool):
                errors.append("XINHAI_DEFAULT_RETRY_CONFIG.enable_exp_backoff 必须是布尔值")
            if "reraise" in retry_cfg and not isinstance(retry_cfg["reraise"], bool):
                errors.append("XINHAI_DEFAULT_RETRY_CONFIG.reraise 必须是布尔值")

    return errors


@app.get("/api/reasoning-types")
async def get_reasoning_types():
    """返回所有可配置的推理模式注入的类型"""
    logger.info("📥 收到获取所有可配置的推理模式注入类型请求", module_name=CHINESE_NAME)
    try:
        types = builder.get_all_reasoning_types()
        logger.info("📄 推理模式注入类型获取成功", module_name=CHINESE_NAME)
        return {ke.KEY_TYPES: types}
    except Exception as e:
        logger.error(f"❌ 获取推理模式注入类型失败：{e}", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"获取推理模式注入类型失败: {str(e)}")


@app.get("/api/vendor-model")
async def get_vendor_model():
    """返回所有可配置的厂商和模型"""
    logger.info("📥 收到获取所有可配置的厂商和模型请求", module_name=CHINESE_NAME)
    try:
        vendor = LLMVendor.all()
        model = LLMModel.all()
        logger.info("📄 可配置的厂商和模型获取成功", module_name=CHINESE_NAME)
        return {ke.KEY_VENDOR: vendor, ke.KEY_MODEL: model}
    except Exception as e:
        logger.error(f"❌ 获取可配置的厂商和模型失败：{e}", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"获取可配置的厂商和模型失败: {str(e)}")


@app.get("/api/tree", response_model=List[TreeNode])
async def get_directory_tree():
    logger.info("📂 正在获取目录树结构", module_name=CHINESE_NAME)
    if not config.DATA_ROOT.exists():
        logger.error(f"❌ 目录树根路径不存在：{config.DATA_ROOT}", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"Data root not found: {config.DATA_ROOT}")
    tree_data = build_tree(config.DATA_ROOT)
    logger.info(f"✅ 目录树构建完成，共找到 {len(tree_data)} 个节点", module_name=CHINESE_NAME)
    return tree_data


def build_tree(path: Path, rel_path: str = "") -> List[TreeNode]:
    """递归构建目录树"""
    nodes = []
    try:
        for item in sorted(path.iterdir()):
            rel_item = os.path.join(rel_path, item.name).replace("\\", "/")
            if item.is_dir():
                # logger.debug(f"📁 发现文件夹：{rel_item}", module_name=CHINESE_NAME)
                children = build_tree(item, rel_item)
                nodes.append(
                    TreeNode(
                        label=item.name,
                        key=rel_item,
                        type=ke.KEY_FOLDER,
                        children=children
                    )
                )
            else:
                ext = item.suffix.lstrip(".").lower() or ke.KEY_TXT
                # logger.debug(f"📄 发现文件：{rel_item} ({ext})", module_name=CHINESE_NAME)
                nodes.append(
                    TreeNode(
                        label=item.name,
                        key=rel_item,
                        type=ke.KEY_FILE,
                        ext=ext
                    )
                )
    except PermissionError as e:
        logger.warning(f"⚠️ 无权限访问目录：{path}，错误：{e}", module_name=CHINESE_NAME)
        pass
    except Exception as e:
        logger.error(f"❌ 构建目录树时发生未知错误：{e}", module_name=CHINESE_NAME)
        pass
    return nodes


@app.get("/api/file")
async def get_file_content(path: str = Query(..., description="要查看的文件相对路径（基于 /data 根目录）")):
    """
    获取指定路径下的文本文件内容。
    安全校验：
      - 防止路径穿越
      - 确保文件在 DATA_ROOT 内
      - 仅返回可文本解码的文件内容
    返回：
      - content: 文件内容（str）
      - ext: 文件扩展名（小写，无点）
      - path: 原始请求路径
    """
    # === 路径安全校验（与 PUT 保持一致）===
    safe_path = (config.OUTPUT_ROOT / path).resolve()
    if not str(safe_path).startswith(str(config.OUTPUT_ROOT.resolve())):
        raise HTTPException(status_code=403, detail="非法路径：检测到路径穿越尝试")

    if not safe_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    # === 先读原始字节，用于文本性检测 ===
    try:
        with open(safe_path, ke.KEY_RB) as f:
            raw_data = f.read(4096)  # 只读前 4KB 足够判断
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取文件失败: {e}")

    # === 判断是否为文本文件（基于字节特征）===
    if not _is_likely_text(bytes(raw_data)):
        raise HTTPException(status_code=400, detail="文件不可读（非文本格式）")

    # === 现在安全地进行自动编码解码 ===
    content = file_util.read_file(str(safe_path), auto_decode=True)

    # === 二次保险：如果解码后全是 replacement char，也拒绝 ===
    if content and content.count('\ufffd') / len(content) > 0.3:
        logger.warning(f"⚠️ 文件包含大量无法识别的字符，可能已损坏：{path}", module_name=CHINESE_NAME)

    # === 返回结果 ===
    ext = safe_path.suffix.lstrip(".").lower() or ke.KEY_TXT
    logger.info(f"📖 成功读取文本文件: {path} (类型: {ext})", module_name=CHINESE_NAME)

    return {
        ke.KEY_CONTENT: content,
        ke.KEY_EXT: ext,
        ke.KEY_PATH: path
    }


def _is_likely_text(data: bytes, sample_size: int = 4096) -> bool:
    """
    基于字节特征快速判断是否为文本文件。
    策略：
      - 检查是否有空字节 \x00（二进制文件常见）
      - 检查不可打印 ASCII 比例（0x00-0x08, 0x0B-0x0C, 0x0E-0x1F）
      - 允许换行、制表等控制字符
    """
    if not data:
        return True  # 空文件视为文本

    sample = data[:sample_size]

    # 如果包含 null byte，极大概率是二进制
    if b'\x00' in sample:
        return False

    # 统计“明显非文本”的字节
    non_text_count = 0
    total = len(sample)

    for byte in sample:
        # 允许的控制字符：\t(9), \n(10), \r(13)
        if byte in (9, 10, 13):
            continue
        # 不可见且非标准文本字符（0-8, 11-12, 14-31）
        if 0 <= byte <= 8 or 11 <= byte <= 12 or 14 <= byte <= 31:
            non_text_count += 1

    # 如果“坏字节”比例 > 10%，认为是二进制
    if non_text_count / total > 0.1:
        return False

    return True


@app.put("/api/file")
async def update_file_content(
        path: str = Query(..., description="要更新的文件相对路径（基于 /data 根目录）"),
        request: FileUpdateRequest = Body(...)
):
    """
    更新指定路径下的文本文件内容。
    安全校验：
      - 防止路径穿越（..）
      - 确保目标在 PATH_DATA 内
      - 仅允许更新已存在的文本文件（防止创建任意文件）
    返回：
      - 200: 成功
      - 403: 路径非法
      - 404: 文件不存在
      - 400: 非文本文件或内容非字符串
      - 500: 写入失败
    """
    # === 路径安全校验 ===
    safe_path = (config.OUTPUT_ROOT / path).resolve()
    if not safe_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    # === 检查是否为文本文件（避免覆盖二进制文件）===
    try:
        with open(safe_path, ke.KEY_R, encoding=ke.KEY_UTF_8) as f:
            f.read(1024)  # 尝试读取前 1KB
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="无法编辑非文本文件")

    # === 写入新内容===
    success, error_msg = file_util.write_file_with_error(
        file_path=str(safe_path),
        content=request.content,
        encoding=ke.KEY_UTF_8
    )

    if not success:
        raise HTTPException(status_code=500, detail=f"写入失败: {error_msg}")

    logger.info(f"✅ 文件已更新: {path}", module_name=CHINESE_NAME)
    return {ke.KEY_MESSAGE: "文件更新成功", ke.KEY_PATH: path}


@app.get("/api/prompts")
async def get_prompts():
    """获取步骤级 Prompt 配置"""
    logger.info("📥 收到查询 Prompt 配置请求", module_name=CHINESE_NAME)
    try:
        data = file_util.read_json_file(config.PATH_FILE_PROMPTS_JSON)
        logger.info(f"📄 读取 Prompt 配置成功，共 {len(data.get(ke.KEY_PROMPTS, []))} 个 Prompt", module_name=CHINESE_NAME)
        return data
    except Exception as e:
        logger.error(f"❌ 读取 Prompt 配置失败: {e}", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"读取 Prompt 配置失败: {str(e)}")


@app.post("/api/prompts")
async def save_prompts(request: Request):
    """保存步骤级 Prompt 配置"""
    logger.info("📥 收到保存 Prompt 配置请求", module_name=CHINESE_NAME)
    try:
        prompts_data = await request.json()

        validation_errors = validate_step_config_structure(prompts_data)
        if validation_errors:
            error_msg = "Prompt 配置校验失败:\n" + "\n".join(validation_errors)
            logger.warning(f"⚠️ {error_msg}", module_name=CHINESE_NAME)
            raise HTTPException(status_code=400, detail=error_msg)

        file_util.write_json(prompts_data, config.MOUNT_PATH_FILE_PROMPTS_JSON)
        logger.info(f"💾 Prompt 配置已写入文件，共保存 {len(prompts_data[ke.KEY_PROMPTS])} 个 Prompt", module_name=CHINESE_NAME)

        try:
            builder.reload_prompts()
        except Exception as e:
            logger.exception(f"❌ Prompt 热重载失败：{str(e)}", module_name=CHINESE_NAME)

        return {
            ke.KEY_STATUS: ke.KEY_SUCCESS,
            ke.KEY_MESSAGE: f"Prompt 配置已保存并重载，共 {len(prompts_data[ke.KEY_PROMPTS])} 个 Prompt"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("💥 保存 Prompt 配置时发生未预期错误", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@app.get("/api/plugins")
async def get_plugins():
    """获取插件配置"""
    logger.info("📥 收到查询插件配置请求", module_name=CHINESE_NAME)
    try:
        # 读取插件文件
        data = file_util.read_json_file(config.PATH_FILE_PLUGINS_JSON)
        logger.info(f"📄 读取插件配置成功，共 {len(data.get(ke.KEY_PROMPTS, []))} 个插件", module_name=CHINESE_NAME)
        return data
    except Exception as e:
        logger.error(f"❌ 读取插件配置失败: {e}", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"读取插件配置失败: {str(e)}")


@app.post("/api/plugins")
async def save_plugins(request: Request):
    """保存插件配置"""
    logger.info("📥 收到保存插件配置请求", module_name=CHINESE_NAME)
    try:
        plugins_data = await request.json()

        validation_errors = validate_step_config_structure(plugins_data)
        if validation_errors:
            error_msg = "插件配置校验失败:\n" + "\n".join(validation_errors)
            logger.warning(f"⚠️ {error_msg}", module_name=CHINESE_NAME)
            raise HTTPException(status_code=400, detail=error_msg)

        # 写入文件
        file_util.write_json(plugins_data, config.MOUNT_PATH_FILE_PLUGINS_JSON)
        logger.info(f"💾 插件配置已写入文件，共保存 {len(plugins_data[ke.KEY_PROMPTS])} 个插件", module_name=CHINESE_NAME)

        try:
            builder.reload_plugins()
        except Exception as e:
            logger.exception(f"❌ 插件热重载失败：{str(e)}", module_name=CHINESE_NAME)

        return {ke.KEY_STATUS: ke.KEY_SUCCESS, ke.KEY_MESSAGE: f"插件配置已保存并重载，共 {len(plugins_data[ke.KEY_PROMPTS])} 个插件"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("💥 保存插件配置时发生未预期错误", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


def validate_step_config_structure(data: dict) -> list[str]:
    """校验步骤级配置结构（统一使用 'prompts' 键）"""
    errors = []

    list_key = ke.KEY_PROMPTS

    if not isinstance(data, dict):
        return ["配置必须是 JSON 对象"]
    if list_key not in data:
        return [f"缺少 '{list_key}' 字段"]
    if not isinstance(data[list_key], list):
        return [f"'{list_key}' 必须是数组"]

    items = data[list_key]
    seen_indices = {}

    for idx, item in enumerate(items):
        pid = item.get(ke.KEY_ID, f"prompt#{idx}")

        # 必填字段
        required_fields = {
            ke.KEY_INDEX: int,
            ke.KEY_ENABLED: bool,
            ke.KEY_RULES: list,
            ke.KEY_PARAMS: dict,
            ke.KEY_OUTPUT_KEY: str,
            ke.KEY_OUTPUT_SCHEMA: dict,
        }
        for field, expected_type in required_fields.items():
            if field not in item:
                errors.append(f"[{pid}] 缺少必填字段: {field}")
                continue
            value = item[field]
            if not isinstance(value, expected_type):
                errors.append(f"[{pid}] 字段 '{field}' 应为 {expected_type.__name__}，实际 {type(value).__name__}")

        # index 唯一性
        if ke.KEY_INDEX in item:
            index_val = item[ke.KEY_INDEX]
            if isinstance(index_val, int):
                if index_val in seen_indices:
                    errors.append(f"[{pid}] {ke.KEY_INDEX}={index_val} 与 [{seen_indices[index_val]}] 重复")
                else:
                    seen_indices[index_val] = pid

        # rules 必须是字符串列表
        if ke.KEY_RULES in item and isinstance(item[ke.KEY_RULES], list):
            for ri, rule in enumerate(item[ke.KEY_RULES]):
                if not isinstance(rule, str):
                    errors.append(f"[{pid}] {ke.KEY_RULES}[{ri}] 必须是字符串")

        # output_schema 结构
        if ke.KEY_OUTPUT_SCHEMA in item and isinstance(item[ke.KEY_OUTPUT_SCHEMA], dict):
            schema = item[ke.KEY_OUTPUT_SCHEMA]
            for top_key, top_value in schema.items():
                if not isinstance(top_value, dict):
                    errors.append(f"[{pid}] {ke.KEY_OUTPUT_SCHEMA}.{top_key} 必须是对象")
                elif top_value.get(ke.KEY_TYPE) != ke.KEY_OBJECT:
                    errors.append(f"[{pid}] {ke.KEY_OUTPUT_SCHEMA}.{top_key}.{ke.KEY_TYPE} 必须为 '{ke.KEY_OBJECT}'")
                elif not isinstance(top_value.get(ke.KEY_PROPERTIES), dict):
                    errors.append(f"[{pid}] {ke.KEY_OUTPUT_SCHEMA}.{top_key}.{ke.KEY_PROPERTIES} 缺失或不是对象")

        # params 修复与校验
        if ke.KEY_PARAMS in item and isinstance(item[ke.KEY_PARAMS], dict):
            llm = item[ke.KEY_PARAMS]
            for key, (typ, req) in va.VAL_LLM_PARAMS_SCHEMA.items():
                if req and key not in llm:
                    llm[key] = va.VAL_RECOMMENDED_PARAMS.get(key)
                if key in llm:
                    val = llm[key]
                    if isinstance(val, str) and typ in (int, float):
                        try:
                            llm[key] = float(val) if typ is float else int(val)
                        except ValueError:
                            llm[key] = va.VAL_RECOMMENDED_PARAMS.get(key)
                    elif not isinstance(val, typ):
                        llm[key] = va.VAL_RECOMMENDED_PARAMS.get(key)
            rf = llm.get(ke.KEY_RESPONSE_FORMAT)
            if rf is not None and (not isinstance(rf, dict) or rf.get(ke.KEY_TYPE) != ke.KEY_JSON_OBJECT):
                errors.append(f"[{pid}] {ke.KEY_RESPONSE_FORMAT} 必须为 {{\"{ke.KEY_TYPE}\":\"{ke.KEY_JSON_OBJECT}\"}}")

        # 可选字段基础类型
        for field, expected_type in [
            (ke.KEY_ID, str), (ke.KEY_NAME, str), (ke.KEY_DESCRIPTION, str),
            (ke.KEY_ROLE, str), (ke.KEY_INFORMATION_SOURCE, str), (ke.KEY_VERSION, str),
            (ke.KEY_TAGS, list), (ke.KEY_CHANGELOG, list),
            (ke.KEY_OUTPUT_PREFIX, (str, list)), (ke.KEY_OUTPUT_SUFFIX, (str, list)),
            (ke.KEY_EMPTY_RESULT_FALLBACK, str),
        ]:
            if field in item:
                if not isinstance(item[field], expected_type):
                    errors.append(f"[{pid}] 字段 '{field}' 类型错误")

    return errors


def get_unsplash_headers() -> Dict[str, str]:
    return {
        ke.KEY_AUTHORIZATION: f"Client-ID {config.UNSPLASH_ACCESS_KEY}",
        ke.KEY_ACCEPT_VERSION: "v1",
        ke.KEY_USER_AGENT: va.VAL_HEADER_USER_AGENT
    }


def _map_unsplash_photo_to_frontend(item: Dict[str, Any]) -> Dict[str, Any]:
    """将 Unsplash 原始图片数据映射为前端所需结构"""
    urls = item.get(ke.KEY_URLS, {})
    user = item.get(ke.KEY_USER, {})
    return {
        ke.KEY_ID: item.get(ke.KEY_ID),
        ke.KEY_DESCRIPTION: item.get(ke.KEY_DESCRIPTION) or "",
        ke.KEY_TITLE: item.get(ke.KEY_ALT_DESCRIPTION) or "",
        ke.KEY_URL: urls.get(ke.KEY_REGULAR),
        ke.KEY_THUMBNAIL_URL: urls.get(ke.KEY_SMALL),
        ke.KEY_WIDTH: item.get(ke.KEY_WIDTH),
        ke.KEY_HEIGHT: item.get(ke.KEY_HEIGHT),
        ke.KEY_LIKES: item.get(ke.KEY_LIKES, 0),
        ke.KEY_CREATE_AT: item.get(ke.KEY_CREATE_AT, datetime.now().isoformat()),
        ke.KEY_AUTHOR_NAME: user.get(ke.KEY_NAME, ""),
        ke.KEY_AUTHOR_URL: user.get(ke.KEY_LINKS, {}).get(ke.KEY_HTML, "")
    }


def _check_unsplash_config():
    key = config.UNSPLASH_ACCESS_KEY
    base_path = config.UNSPLASH_BASIC_PATH

    # 校验并处理 Access Key
    if not key or not key.strip():
        logger.warning("MISSING_UNSPLASH_KEY: Unsplash Access Key 不能为空", module_name=CHINESE_NAME)
        raise HTTPException(
            status_code=500,
            detail="MISSING_UNSPLASH_KEY: Unsplash Access Key 不能为空"
        )

    if key.strip() == "请输入 unsplash 密钥":
        logger.warning("DEFAULT_UNSPLASH_KEY: 请将 XINHAI_UNSPLASH_ACCESS_KEY 替换为真实的 Unsplash Access Key",
                       module_name=CHINESE_NAME)
        raise HTTPException(
            status_code=500,
            detail="DEFAULT_UNSPLASH_KEY: 请将 XINHAI_UNSPLASH_ACCESS_KEY 替换为真实的 Unsplash Access Key"
        )

    # 校验并自动修复 BASIC_PATH
    if not base_path or not base_path.strip():
        # 自动修复为默认官方地址
        config.UNSPLASH_BASIC_PATH = va.VAL_UNSPLASH_BASIC_URL


@app.get("/api/unsplash/search/photos")
async def search_unsplash_photos(
        query: str = Query(..., min_length=1, description="搜索关键词"),
        page: Optional[int] = Query(1, ge=1),
        per_page: Optional[int] = Query(12, ge=1, le=32),
        order_by: Optional[str] = Query(None, regex="^(relevant|latest)$"),
        color: Optional[str] = Query(
            None,
            regex="^(black_and_white|black|white|red|orange|yellow|green|teal|blue|purple|magenta)$"
        ),
        orientation: Optional[str] = Query(None, regex="^(landscape|portrait|squarish)$"),
        content_filter: Optional[str] = Query(None, regex="^(low|high)$"),
        collections: Optional[str] = Query(None, description="逗号分隔的 collection ID 列表")
):
    """
    搜索 Unsplash 照片（透传支持所有合法参数）
    """

    _check_unsplash_config()

    # 构建透传参数
    unsplash_params: Dict[str, Any] = {
        ke.KEY_QUERY: query,
        ke.KEY_PAGE: page,
        ke.KEY_PER_PAGE: per_page,
    }

    # 安全注入可选参数
    if order_by in va.VAL_UNSPLASH_ALLOWED_ORDER_BY:
        unsplash_params[ke.KEY_ORDER_BY] = order_by
    if color in va.VAL_UNSPLASH_ALLOWED_COLORS:
        unsplash_params[ke.KEY_COLOR] = color
    if orientation in va.VAL_UNSPLASH_ALLOWED_ORIENTATION:
        unsplash_params[ke.KEY_ORIENTATION] = orientation
    if content_filter in va.VAL_UNSPLASH_ALLOWED_CONTENT_FILTER:
        unsplash_params[ke.KEY_CONTENT_FILTER] = content_filter
    if collections:
        unsplash_params[ke.KEY_COLLECTIONS] = collections

    # 调用 Unsplash API
    resp = None
    try:
        resp = requests.get(
            f"{config.UNSPLASH_BASIC_PATH}{va.VAL_UNSPLASH_SEARCH_PHOTOS_API_SUFFIX}",
            headers=get_unsplash_headers(),
            params=unsplash_params,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

    except requests.Timeout:
        raise HTTPException(status_code=504, detail="请求 Unsplash 超时，请稍后重试")
    except requests.ConnectionError:
        raise HTTPException(status_code=502, detail="无法连接 Unsplash 服务")
    except requests.HTTPError:
        status = resp.status_code
        if status == 401:
            detail = "Unsplash Access Key 无效或已过期"
        elif status == 403:
            detail = "Unsplash 请求频率超限"
        elif status == 400:
            detail = "请求参数错误"
        else:
            detail = f"Unsplash 返回错误 ({status})"
        raise HTTPException(status_code=400 if status in (400, 401, 403) else 500, detail=detail)
    except Exception:
        raise HTTPException(status_code=500, detail="服务器内部错误")

    # 映射结果
    raw_results = data.get(ke.KEY_RESULTS, [])
    display_results = [_map_unsplash_photo_to_frontend(item) for item in raw_results]

    return {
        ke.KEY_TOTAL: data.get(ke.KEY_TOTAL, 0),
        ke.KEY_TOTAL_PAGES: data.get(ke.KEY_TOTAL_PAGES, 0),
        ke.KEY_RESULTS: display_results
    }


def _map_collection_to_frontend(item: Dict[str, Any]) -> Dict[str, Any]:
    """将 Unsplash Collection 原始数据映射为前端所需结构"""
    cover = item.get(ke.KEY_COVER_PHOTO, {}) or {}
    cover_urls = cover.get(ke.KEY_URLS, {}) or {}
    user = item.get(ke.KEY_USER, {}) or {}

    return {
        ke.KEY_ID: item.get(ke.KEY_ID),
        ke.KEY_TITLE: item.get(ke.KEY_TITLE, ""),
        ke.KEY_DESCRIPTION: item.get(ke.KEY_DESCRIPTION, ""),
        ke.KEY_COLLECT_URL: item.get(ke.KEY_LINKS, {}).get(ke.KEY_HTML, ""),
        ke.KEY_URL: cover_urls.get(ke.KEY_REGULAR),
        ke.KEY_THUMBNAIL_URL: cover_urls.get(ke.KEY_SMALL),
        ke.KEY_WIDTH: cover.get(ke.KEY_WIDTH),
        ke.KEY_HEIGHT: cover.get(ke.KEY_HEIGHT),
        ke.KEY_LIKES: cover.get(ke.KEY_LIKES, 0),
        ke.KEY_CREATE_AT: cover.get(ke.KEY_CREATE_AT, datetime.now().isoformat()),
        ke.KEY_AUTHOR_NAME: user.get(ke.KEY_NAME, ""),
        ke.KEY_AUTHOR_URL: user.get(ke.KEY_LINKS, {}).get(ke.KEY_HTML, "")
    }


@app.get("/api/unsplash/search/collections")
async def search_unsplash_collections(
        query: str = Query(..., min_length=1, description="搜索关键词"),
        page: Optional[int] = Query(1, ge=1),
        per_page: Optional[int] = Query(10, ge=1, le=30)
):
    """
    搜索 Unsplash 收藏集（Collections）
    仅支持 query, page, per_page 参数
    """
    _check_unsplash_config()

    unsplash_params = {
        ke.KEY_QUERY: query,
        ke.KEY_PAGE: page,
        ke.KEY_PER_PAGE: per_page
    }
    resp = None
    try:
        resp = requests.get(
            f"{config.UNSPLASH_BASIC_PATH}{va.VAL_UNSPLASH_SEARCH_COLLECTIONS_API_SUFFIX}",
            headers=get_unsplash_headers(),
            params=unsplash_params,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

    except requests.Timeout:
        raise HTTPException(status_code=504, detail="请求 Unsplash 超时")
    except requests.ConnectionError:
        raise HTTPException(status_code=502, detail="无法连接 Unsplash 服务")
    except requests.HTTPError:
        status = resp.status_code
        if status == 401:
            detail = "Unsplash Access Key 无效"
        elif status == 403:
            detail = "请求频率超限"
        else:
            detail = f"请求失败 ({status})"
        raise HTTPException(status_code=400 if status in (400, 401, 403) else 500, detail=detail)
    except Exception:
        raise HTTPException(status_code=500, detail="服务器内部错误")

    # 映射结果
    raw_results = data.get(ke.KEY_RESULTS, [])
    display_results = [_map_collection_to_frontend(item) for item in raw_results]

    return {
        ke.KEY_TOTAL: data.get(ke.KEY_TOTAL, 0),
        ke.KEY_TOTAL_PAGES: data.get(ke.KEY_TOTAL_PAGES, 0),
        ke.KEY_RESULTS: display_results
    }


def get_pexels_headers() -> Dict[str, str]:
    return {
        ke.KEY_USER_AGENT: va.VAL_HEADER_USER_AGENT,
        ke.KEY_AUTHORIZATION: config.PEXELS_ACCESS_KEY
    }


def _check_pexels_config():
    key = config.PEXELS_ACCESS_KEY
    base_path = config.PEXELS_BASIC_PATH

    # 校验并处理 Access Key
    if not key or not key.strip():
        logger.warning("MISSING_PEXELES_KEY: Pexels Access Key 不能为空", module_name=CHINESE_NAME)
        raise HTTPException(
            status_code=500,
            detail="MISSING_PEXELES_KEY: Pexels Access Key 不能为空"
        )

    if key.strip() == "请输入 pexels 密钥":
        logger.warning("DEFAULT_PEXELS_KEY: 请将 XINHAI_PEXELS_ACCESS_KEY 替换为真实的 Pexels Access Key",
                       module_name=CHINESE_NAME)
        raise HTTPException(
            status_code=500,
            detail="DEFAULT_PEXELS_KEY: 请将 XINHAI_PEXELS_BASIC_PATH 替换为真实的 Pexels Access Key"
        )

    # 校验并自动修复 BASIC_PATH
    if not base_path or not base_path.strip():
        # 自动修复为默认官方地址
        config.PEXELS_BASIC_PATH = va.VAL_PEXELS_BASIC_URL


def _map_pexels_photo_to_frontend(item: Dict[str, Any]) -> Dict[str, Any]:
    """将 Pexels 原始图片数据映射为前端所需结构"""
    return {
        ke.KEY_ID: item.get(ke.KEY_ID),
        ke.KEY_DESCRIPTION: item.get(ke.KEY_ALT, ""),
        ke.KEY_TITLE: item.get(ke.KEY_ALT, ""),
        ke.KEY_URL: item[ke.KEY_SRC].get(ke.KEY_LARGE),
        ke.KEY_THUMBNAIL_URL: item[ke.KEY_SRC].get(ke.KEY_SMALL),
        ke.KEY_WIDTH: item.get(ke.KEY_WIDTH),
        ke.KEY_HEIGHT: item.get(ke.KEY_HEIGHT),
        ke.KEY_AUTHOR_NAME: item.get(ke.KEY_PHOTOGRAPHER),
        ke.KEY_AUTHOR_URL: item.get(ke.KEY_PHOTOGRAPHER_URL),
    }


def _map_pexels_video_to_frontend(item: Dict[str, Any]) -> Dict[str, Any]:
    """将 Pexels 原始视频数据映射为前端所需结构"""
    video_files = item.get(ke.KEY_VIDEO_FILES, [])
    full_video = find_best_video_match(video_files, ke.KEY_HD, 1280, 720)
    small_video = find_best_video_match(video_files, ke.KEY_SD, 640, 360)

    return {
        ke.KEY_ID: item.get(ke.KEY_ID),
        ke.KEY_URL: full_video[ke.KEY_LINK] if full_video else None,
        ke.KEY_THUMBNAIL_URL: small_video[ke.KEY_LINK] if small_video else None,
        ke.KEY_WIDTH: full_video.get(ke.KEY_WIDTH) if full_video else None,
        ke.KEY_HEIGHT: full_video.get(ke.KEY_HEIGHT) if full_video else None,
        ke.KEY_AUTHOR_NAME: item[ke.KEY_USER].get(ke.KEY_NAME),
        ke.KEY_AUTHOR_URL: item[ke.KEY_USER].get(ke.KEY_URL),
    }


def find_best_video_match(video_files: list, target_quality: str, target_width: int, target_height: int):
    if not video_files:
        return None

    exact = next(
        (vf for vf in video_files
         if vf[ke.KEY_QUALITY] == target_quality
         and vf[ke.KEY_WIDTH] == target_width
         and vf[ke.KEY_HEIGHT] == target_height),
        None
    )
    if exact:
        return exact

    same_quality = [vf for vf in video_files if vf[ke.KEY_QUALITY] == target_quality]
    if same_quality:
        target_area = target_width * target_height
        return min(same_quality, key=lambda vf: abs(vf[ke.KEY_WIDTH] * vf[ke.KEY_HEIGHT] - target_area))

    target_area = target_width * target_height
    return min(video_files, key=lambda vf: abs(vf[ke.KEY_WIDTH] * vf[ke.KEY_HEIGHT] - target_area))


@app.get("/api/pexels/search/photos")
async def search_pexels_photos(
    query: str = Query(..., min_length=1),
    page: Optional[int] = Query(1, ge=1),
    per_page: Optional[int] = Query(12, ge=1, le=80),
    size: Optional[str] = None,
    orientation: Optional[str] = None,
    color: Optional[str] = None,
    locale: Optional[str] = None,
):
    _check_pexels_config()

    params = {ke.KEY_QUERY: query, ke.KEY_PAGE: page, ke.KEY_PER_PAGE: per_page}

    if size and size in va.VAL_PEXELS_ALLOWED_SIZES:
        params[ke.KEY_SIZE] = size
    if orientation and orientation in va.VAL_PEXELS_ALLOWED_ORIENTATIONS:
        params[ke.KEY_ORIENTATION] = orientation
    if color and color in va.VAL_PEXELS_ALLOWED_COLORS:
        params[ke.KEY_COLOR] = color
    if locale and locale in va.VAL_PEXELS_ALLOWED_LOCALES:
        params[ke.KEY_LOCALE] = locale

    resp = None
    try:
        resp = requests.get(
            f"{config.PEXELS_BASIC_PATH}{va.VAL_PEXELS_SEARCH_PHOTOS_API_SUFFIX}",
            headers=get_pexels_headers(),
            params=params,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.Timeout:
        raise HTTPException(status_code=504, detail="请求 Pexels 超时")
    except requests.ConnectionError:
        raise HTTPException(status_code=502, detail="无法连接 Pexels 服务")
    except requests.HTTPError:
        status = resp.status_code
        if status == 401:
            detail = "Pexels Access Key 无效"
        elif status == 429:
            detail = "请求频率超限"
        else:
            detail = f"Pexels 请求失败 ({status})"
        raise HTTPException(status_code=400 if status in (400, 401, 429) else 502, detail=detail)
    except Exception as e:
        logger.error(f"[Pexels Photos] Unexpected error: {e}", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail="服务器内部错误")

    photos = data.get(ke.KEY_PHOTOS, [])
    total_results = data.get(ke.KEY_TOTAL_RESULTS, 0)
    per_page_val = data.get(ke.KEY_PER_PAGE, per_page)
    total_pages = math.ceil(total_results / per_page_val) if per_page_val else 1

    results = [_map_pexels_photo_to_frontend(photo) for photo in photos]

    return {
        ke.KEY_TOTAL: total_results,
        ke.KEY_TOTAL_PAGES: total_pages,
        ke.KEY_RESULTS: results
    }


@app.get("/api/pexels/search/videos")
async def search_pexels_videos(
    query: str = Query(..., min_length=1),
    page: Optional[int] = Query(1, ge=1),
    per_page: Optional[int] = Query(12, ge=1, le=80),
    size: Optional[str] = None,
    orientation: Optional[str] = None,
    locale: Optional[str] = None,
):
    """
    搜索 Pexels 视频
    """
    _check_pexels_config()

    pexels_params = {ke.KEY_QUERY: query, ke.KEY_PAGE: page, ke.KEY_PER_PAGE: per_page}

    if size and size in va.VAL_PEXELS_ALLOWED_SIZES:
        pexels_params[ke.KEY_SIZE] = size
    if orientation and orientation in va.VAL_PEXELS_ALLOWED_ORIENTATIONS:
        pexels_params[ke.KEY_ORIENTATION] = orientation
    if locale and locale in va.VAL_PEXELS_ALLOWED_LOCALES:
        pexels_params[ke.KEY_LOCALE] = locale

    resp = None
    try:
        resp = requests.get(
            f"{config.PEXELS_BASIC_PATH}{va.VAL_PEXELS_SEARCH_VIDEOS_API_SUFFIX}",
            headers=get_pexels_headers(),
            params=pexels_params,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.Timeout:
        raise HTTPException(status_code=504, detail="请求超时")
    except requests.ConnectionError:
        raise HTTPException(status_code=502, detail="网络连接失败")
    except requests.HTTPError:
        status = resp.status_code
        if status == 401:
            raise HTTPException(status_code=401, detail="Pexels Access Key 无效")
        elif status == 429:
            raise HTTPException(status_code=429, detail="请求频率超限")
        else:
            raise HTTPException(status_code=502, detail=f"Pexels 返回错误 ({status})")
    except Exception:
        raise HTTPException(status_code=500, detail="服务器内部错误")

    videos = data.get(ke.KEY_VIDEOS, [])
    total_results = data.get(ke.KEY_TOTAL_RESULTS, 0)
    per_page_val = data.get(ke.KEY_PER_PAGE, per_page)
    total_pages = math.ceil(total_results / per_page_val) if per_page_val else 1

    results = [_map_pexels_video_to_frontend(video) for video in videos]

    return {
        ke.KEY_TOTAL: total_results,
        ke.KEY_TOTAL_PAGES: total_pages,
        ke.KEY_RESULTS: results
    }


@app.get("/api/sse")
async def sse_endpoint():
    sse = get_sse_manager()
    queue = sse.register()

    # 立即推送连接成功事件，使用标准格式
    await sse.broadcast(ke.KEY_CONNECTION_START, {
        ke.KEY_TASK_ID: None,
        ke.KEY_TIMESTAMP: time.time(),
        ke.KEY_TITLE: "SSE 连接已建立",
        ke.KEY_CONTENT: "全局事件监听已就绪",
        ke.KEY_META: {ke.KEY_STAGE: ke.KEY_CONNECTION_START, ke.KEY_STATUS: ke.KEY_START}
    })
    logger.info("SSE 端点已连接", module_name=CHINESE_NAME)

    heartbeat = config.SSE_HEARTBEAT_INTERVAL

    async def event_generator():
        try:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                    yield message
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
        except asyncio.CancelledError:
            logger.info("SSE 连接被取消", module_name="SSE接口")
        finally:
            sse.unregister(queue)
            logger.info("SSE 端点已断开", module_name="SSE接口")

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/sse-proxy")
async def sse_proxy_endpoint(request: Request):
    sse_manager = get_sse_manager()
    queue = sse_manager.register()
    heartbeat = config.SSE_HEARTBEAT_INTERVAL

    async def event_generator():
        try:
            # 新客户端连上，先补发最新缓存
            latest = sse_manager.get_latest_event()
            if latest:
                yield latest
            # 持续转发后续事件
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                    yield message
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
        finally:
            sse_manager.unregister(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/resume/{task_id}")
async def resume_task(task_id: str, request: Request):
    """用户补充信息后恢复挂起的元认知任务"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 格式")

    user_clarification = body.get(ke.KEY_USER_CLARIFICATION, "").strip()
    if not user_clarification:
        raise HTTPException(status_code=400, detail="补充信息不能为空")

    # 调用恢复逻辑，内部处理内存事件丢失兜底
    from app.core.meta.nodes.wait_human import resume_suspended_task
    try:
        await resume_suspended_task(task_id, user_clarification)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {ke.KEY_STATUS: ke.KEY_SUCCESS, ke.KEY_MESSAGE: "任务已恢复执行", ke.KEY_TASK_ID: task_id}


@app.post("/api/process")
async def process_single(request: Request):
    """单条处理接口"""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须是合法 JSON")

    await validate_process_request()

    current_text = payload.get(ke.KEY_CURRENT_TEXT, "").strip()
    if not current_text:
        raise HTTPException(status_code=400, detail=f"{ke.KEY_CURRENT_TEXT} 不能为空")

    injection_params = {
        ke.KEY_CURRENT_TEXT: current_text,
        ke.KEY_CHARACTER_PROFILES: payload.get(ke.KEY_CHARACTER_PROFILES, []),
        ke.KEY_RELATIONSHIP_MAP: payload.get(ke.KEY_RELATIONSHIP_MAP, []),
        ke.KEY_WORLDVIEW_RULES: payload.get(ke.KEY_WORLDVIEW_RULES, []),
        ke.KEY_STYLE_PREFERENCE: payload.get(ke.KEY_STYLE_PREFERENCE, ""),
    }

    orchestrator = PipelineOrchestrator()
    result = await orchestrator.run(injection_params)
    return result


@app.post("/api/process/batch")
async def process_batch(request: Request):
    """批量处理接口。接收 {'tasks': [...] }，返回每个任务的结果列表。"""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须是合法 JSON")

    await validate_process_request()

    tasks = payload.get(ke.KEY_TASKS)
    if not tasks or not isinstance(tasks, list):
        raise HTTPException(status_code=400, detail=f"缺少 {ke.KEY_TASKS} 数组")

    batch_params = []
    for i, task in enumerate(tasks):
        current_text = task.get(ke.KEY_CURRENT_TEXT, "").strip()
        if not current_text:
            raise HTTPException(status_code=400, detail=f"第 {i+1} 个任务的 {ke.KEY_CURRENT_TEXT} 不能为空")

        batch_params.append({
            ke.KEY_CURRENT_TEXT: current_text,
            ke.KEY_CHARACTER_PROFILES: payload.get(ke.KEY_CHARACTER_PROFILES, []),
            ke.KEY_RELATIONSHIP_MAP: payload.get(ke.KEY_RELATIONSHIP_MAP, []),
            ke.KEY_WORLDVIEW_RULES: payload.get(ke.KEY_WORLDVIEW_RULES, []),
            ke.KEY_STYLE_PREFERENCE: payload.get(ke.KEY_STYLE_PREFERENCE, ""),
        })

    orchestrator = PipelineOrchestrator()
    results = await orchestrator.batch_run(batch_params)
    return {ke.KEY_RESULTS: results, ke.KEY_TOTAL: len(results)}


async def validate_process_request() -> None:
    """
    单条/批量处理请求的前置校验。
    1. 检查 LLM 厂商和模型是否已配置
    2. 检查对应的 API Key 是否有效
    """
    # 检查厂商和模型是否已配置
    if not config.LLM_DEFAULT_VENDOR or not config.LLM_DEFAULT_MODEL:
        raise HTTPException(status_code=400, detail="请前往中枢控制台页面设置有效的厂商和模型后重试。")

    # 动态构造厂商对应的密钥字段名并检查
    api_key_field = f"LLM_{config.LLM_DEFAULT_VENDOR.upper()}_API_KEY"
    api_key_value = getattr(config, api_key_field, None)
    default_placeholder_values = ["请输入密钥"]

    if not api_key_value or api_key_value.strip() in default_placeholder_values:
        raise HTTPException(status_code=400, detail="请前往中枢控制台页面设置有效的大模型 API 密钥后重试。")


@app.get("/api/config/adaptation")
async def get_adaptation_limits():
    """
    获取场景适配的四项输入上限配置。
    返回 character_profiles, relationship_map, worldview_rules, style_preference 的最大条数。
    """
    logger.info("📥 查询场景适配输入上限", module_name=CHINESE_NAME)
    try:
        return {
            ke.KEY_CHARACTER_PROFILES: config.CHARACTER_PROFILES or 8,
            ke.KEY_RELATIONSHIP_MAP: config.RELATIONSHIP_MAP or 8,
            ke.KEY_WORLDVIEW_RULES: config.WORLDVIEW_RULES or 8,
            ke.KEY_STYLE_PREFERENCE: config.STYLE_PREFERENCE or 8,
        }
    except Exception as e:
        logger.exception("❌ 获取场景适配输入上限配置失败", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"获取场景适配输入上限配置失败: {str(e)}")


@app.get("/api/dao")
async def get_dao_config():
    """获取道之元典配置"""
    logger.info("📥 收到查询道之元典配置请求", module_name=CHINESE_NAME)
    try:
        data = file_util.read_json_file(config.PATH_FILE_THE_WAY_JSON)
        logger.info("📄 读取道之元典配置成功", module_name=CHINESE_NAME)
        return data
    except Exception as e:
        logger.error(f"❌ 读取道之元典配置失败: {e}", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"读取道之元典配置失败: {str(e)}")


@app.post("/api/dao")
async def save_dao_config(request: Request):
    """保存道之元典配置"""
    logger.info("📥 收到保存道之元典配置请求", module_name=CHINESE_NAME)
    try:
        new_data = await request.json()

        errors = []

        # 顶层结构校验
        if not isinstance(new_data, dict):
            raise HTTPException(status_code=400, detail="配置必须是 JSON 对象")
        if ke.KEY_SUPREME_DIRECTIVE not in new_data or not isinstance(new_data[ke.KEY_SUPREME_DIRECTIVE], list):
            raise HTTPException(status_code=400, detail=f"'{ke.KEY_SUPREME_DIRECTIVE}' 必须是数组且不能为空")

        # 核心校验：dao 内部子字段
        cv.structure_check(errors, new_data, ke.KEY_DAO, {
            ke.KEY_TITLE: (str, True),
            ke.KEY_STATEMENT: (str, True),
            ke.KEY_ELABORATION: (list, True),
            ke.KEY_ONTOLOGICAL_AXIOMS: (list, True),
        })

        if errors:
            raise HTTPException(status_code=400, detail="配置校验失败:\n" + "\n".join(errors))

        file_util.write_json(new_data, config.MOUNT_PATH_FILE_THE_WAY_JSON)
        logger.info("💾 道之元典配置已写入文件", module_name=CHINESE_NAME)

        # 热重载
        try:
            builder.reload_dao()
        except Exception as e:
            logger.exception(f"❌ 道之元典热重载失败：{str(e)}", module_name=CHINESE_NAME)

        return {
            ke.KEY_STATUS: ke.KEY_SUCCESS,
            ke.KEY_MESSAGE: "道之元典配置已保存并重载"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("💥 保存道之元典配置时发生未预期错误")
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@app.get("/api/punctuation-rules")
async def get_punctuation_rules():
    """获取标点规则配置"""
    logger.info("📥 收到查询标点规则配置请求", module_name=CHINESE_NAME)
    try:
        data = file_util.read_json_file(config.PATH_FILE_PUNCTUATION_RULES_JSON)
        logger.info("📄 读取标点规则配置成功", module_name=CHINESE_NAME)
        return data
    except Exception as e:
        logger.error(f"❌ 读取标点规则配置失败: {e}", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"读取标点规则配置失败: {str(e)}")


@app.post("/api/punctuation-rules")
async def save_punctuation_rules(request: Request):
    """保存标点规则配置"""
    logger.info("📥 收到保存标点规则配置请求", module_name=CHINESE_NAME)
    try:
        new_data = await request.json()

        errors = []

        # 顶层结构校验
        if not isinstance(new_data, dict):
            raise HTTPException(status_code=400, detail="配置必须是 JSON 对象")

        # 核心校验
        if not isinstance(new_data.get(ke.KEY_HALF_TO_FULL), dict):
            errors.append(f"'{ke.KEY_HALF_TO_FULL}' 必须是对象")

        for field in [ke.KEY_INVALID_PUNCTUATION_PATTERNS, ke.KEY_MISSING_SPACE_PATTERNS,
                      ke.KEY_WRONG_PUNCTUATION_PATTERNS]:
            patterns = new_data.get(field)
            if not isinstance(patterns, list):
                errors.append(f"'{field}' 必须是列表")
            elif len(patterns) == 0:
                errors.append(f"'{field}' 不能为空")

        if errors:
            raise HTTPException(status_code=400, detail="配置校验失败:\n" + "\n".join(errors))

        file_util.write_json(new_data, config.MOUNT_PATH_FILE_PUNCTUATION_RULES_JSON)
        logger.info("💾 标点规则配置已写入文件", module_name=CHINESE_NAME)

        # 热重载
        try:
            config_loader.reload(pa.FILE_PUNCTUATION_RULES_JSON)
            logger.info("🔄 标点规则热重载完成", module_name=CHINESE_NAME)
        except Exception as e:
            logger.exception(f"❌ 标点规则热重载失败：{str(e)}", module_name=CHINESE_NAME)

        return {
            ke.KEY_STATUS: ke.KEY_SUCCESS,
            ke.KEY_MESSAGE: "标点规则配置已保存并重载"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("💥 保存标点规则配置时发生未预期错误", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@app.get("/api/analysis-rules")
async def get_analysis_rules():
    """获取分析规则配置"""
    logger.info("📥 收到查询分析规则配置请求", module_name=CHINESE_NAME)
    try:
        data = file_util.read_json_file(config.PATH_FILE_ANALYSIS_RULES_JSON)
        logger.info("📄 读取分析规则配置成功", module_name=CHINESE_NAME)
        return data
    except Exception as e:
        logger.error(f"❌ 读取分析规则配置失败: {e}", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"读取分析规则配置失败: {str(e)}")


@app.post("/api/analysis-rules")
async def save_analysis_rules(request: Request):
    """保存分析规则配置"""
    logger.info("📥 收到保存分析规则配置请求", module_name=CHINESE_NAME)
    try:
        new_data = await request.json()
        errors = []

        # 顶层结构
        if not isinstance(new_data, dict):
            raise HTTPException(status_code=400, detail="配置必须是 JSON 对象")

        # 必填顶层字段
        top_fields = [
            ke.KEY_PATTERNS, ke.KEY_THRESHOLDS, ke.KEY_READABILITY,
            ke.KEY_READABILITY_FALLBACK, ke.KEY_PARAGRAPH_SPLITTER, ke.KEY_STYLE_CHECKS
        ]
        for field in top_fields:
            if field not in new_data:
                errors.append(f"缺少顶层字段：'{field}'")

        if errors:
            raise HTTPException(status_code=400, detail="配置校验失败:\n" + "\n".join(errors))

        # ---- 校验 patterns ----
        patterns = new_data[ke.KEY_PATTERNS]
        if not isinstance(patterns, dict):
            errors.append(f"'{ke.KEY_PATTERNS}' 必须是字典")
        else:
            required_patterns = [ke.KEY_SENTENCE, ke.KEY_WORD, ke.KEY_CHINESE]
            for key in required_patterns:
                if key not in patterns:
                    errors.append(f"{ke.KEY_PATTERNS}.{key} 不能为空")
                elif not isinstance(patterns[key], str) or not patterns[key].strip():
                    errors.append(f"{ke.KEY_PATTERNS}.{key} 必须是非空字符串")

        # ---- 校验 thresholds ----
        thresholds = new_data[ke.KEY_THRESHOLDS]
        if not isinstance(thresholds, dict):
            errors.append(f"'{ke.KEY_THRESHOLDS}' 必须是字典")
        else:
            cv.int_check(errors, thresholds, ke.KEY_MAX_SENTENCE_LENGTH, 50, 500)
            cv.int_check(errors, thresholds, ke.KEY_MIN_SENTENCE_LENGTH, 1, 10)
            cv.int_check(errors, thresholds, ke.KEY_REPEATED_WORD_MIN_LENGTH, 1, 5)
            cv.int_check(errors, thresholds, ke.KEY_REPEATED_WORD_MIN_COUNT, 1, 10)
            cv.int_check(errors, thresholds, ke.KEY_REPEATED_PHRASE_MIN_LENGTH, 2, 10)
            cv.int_check(errors, thresholds, ke.KEY_REPEATED_PHRASE_MAX_LENGTH, 5, 20)
            cv.int_check(errors, thresholds, ke.KEY_REPEATED_PHRASE_LIMIT, 1, 20)
            cv.int_check(errors, thresholds, ke.KEY_MAX_PARAGRAPH_LENGTH, 100, 2000)
            cv.int_check(errors, thresholds, ke.KEY_MIN_PARAGRAPH_LENGTH, 5, 100)
            cv.int_check(errors, thresholds, ke.KEY_REPEATED_PHRASE_NGRAM_MIN, 1, 5)
            cv.int_check(errors, thresholds, ke.KEY_REPEATED_PHRASE_NGRAM_MAX, 2, 5)

        # ---- 校验 readability ----
        readability = new_data[ke.KEY_READABILITY]
        if not isinstance(readability, list) or len(readability) == 0:
            errors.append(f"'{ke.KEY_READABILITY}' 必须是非空列表")
        else:
            for i, item in enumerate(readability):
                if not isinstance(item, dict):
                    errors.append(f"{ke.KEY_READABILITY}[{i}] 必须是对象")
                    continue
                cv.int_check(errors, item, ke.KEY_MIN, 0, None)
                cv.int_check(errors, item, ke.KEY_MAX, None, None)
                cv.int_check(errors, item, ke.KEY_SCORE, 0, 100)
                cv.str_check(errors, item, ke.KEY_LEVEL)
                cv.str_check(errors, item, ke.KEY_SUGGESTION)

        # ---- 校验 readability_fallback ----
        fallback = new_data[ke.KEY_READABILITY_FALLBACK]
        if not isinstance(fallback, dict):
            errors.append(f"'{ke.KEY_READABILITY_FALLBACK}' 必须是对象")
        else:
            cv.int_check(errors, fallback, ke.KEY_SCORE, 0, 100)
            cv.str_check(errors, fallback, ke.KEY_LEVEL)
            cv.str_check(errors, fallback, ke.KEY_SUGGESTION)

        # ---- 校验 readability_chinese_bonus / ratio_threshold ----
        cv.int_check(errors, new_data, ke.KEY_READABILITY_CHINESE_BONUS, 0, 50)
        cv.float_check(errors, new_data, ke.KEY_READABILITY_CHINESE_RATIO_THRESHOLD, 0.1, 1.0)

        # ---- 校验 paragraph_splitter ----
        splitter = new_data[ke.KEY_PARAGRAPH_SPLITTER]
        if not isinstance(splitter, dict):
            errors.append(f"'{ke.KEY_PARAGRAPH_SPLITTER}' 必须是对象")
        else:
            cv.int_check(errors, splitter, ke.KEY_MIN_CHARS, 1, 100)
            cv.int_check(errors, splitter, ke.KEY_TARGET_CHARS, 100, 1000)
            cv.int_check(errors, splitter, ke.KEY_CHAR_TOLERANCE, 0, 200)

        # ---- 校验 style_checks ----
        style = new_data[ke.KEY_STYLE_CHECKS]
        if not isinstance(style, dict):
            errors.append(f"'{ke.KEY_STYLE_CHECKS}' 必须是对象")
        else:
            for list_field in [ke.KEY_PASSIVE_VOICE_PATTERNS, ke.KEY_WORDINESS_PATTERNS, ke.KEY_BUZZWORD_PATTERNS]:
                if list_field in style:
                    if not isinstance(style[list_field], list):
                        errors.append(f"{ke.KEY_STYLE_CHECKS}.{list_field} 必须是列表")
                else:
                    errors.append(f"{ke.KEY_STYLE_CHECKS}.{list_field} 不能为空")

        if errors:
            raise HTTPException(status_code=400, detail="配置校验失败:\n" + "\n".join(errors))

        # 保存文件
        file_util.write_json(new_data, config.MOUNT_PATH_FILE_ANALYSIS_RULES_JSON)
        logger.info("💾 分析规则配置已写入文件", module_name=CHINESE_NAME)

        # 热重载
        try:
            config_loader.reload(pa.FILE_ANALYSIS_RULES_JSON)
            logger.info("🔄 分析规则热重载完成", module_name=CHINESE_NAME)
        except Exception as e:
            logger.exception(f"❌ 分析规则热重载失败：{str(e)}", module_name=CHINESE_NAME)

        return {
            ke.KEY_STATUS: ke.KEY_SUCCESS,
            ke.KEY_MESSAGE: "分析规则配置已保存并重载"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("💥 保存分析规则配置时发生未预期错误", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@app.get("/api/spell-rules")
async def get_spell_rules():
    """获取拼写规则配置"""
    logger.info("📥 收到查询拼写规则配置请求", module_name=CHINESE_NAME)
    try:
        data = file_util.read_json_file(config.PATH_FILE_SPELL_RULES_JSON)
        logger.info("📄 读取拼写规则配置成功", module_name=CHINESE_NAME)
        return data
    except Exception as e:
        logger.error(f"❌ 读取拼写规则配置失败: {e}", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"读取拼写规则配置失败: {str(e)}")


@app.post("/api/spell-rules")
async def save_spell_rules(request: Request):
    """保存拼写规则配置"""
    logger.info("📥 收到保存拼写规则配置请求", module_name=CHINESE_NAME)
    try:
        new_data = await request.json()
        errors = []

        # 顶层结构校验
        if not isinstance(new_data, dict):
            raise HTTPException(status_code=400, detail="配置必须是 JSON 对象")

        # 必填顶层字段
        required_top_fields = [
            ke.KEY_WRONG_CHARACTERS, ke.KEY_SIMILAR_CHARACTERS, ke.KEY_COMMON_ERRORS, ke.KEY_DE_FIX_PAIRS
        ]
        for field in required_top_fields:
            if field not in new_data:
                errors.append(f"缺少顶层字段：'{field}'")

        if errors:
            raise HTTPException(status_code=400, detail="配置校验失败:\n" + "\n".join(errors))

        # ---- 校验 wrong_characters ----
        wc = new_data[ke.KEY_WRONG_CHARACTERS]
        if not isinstance(wc, dict):
            errors.append(f"'{ke.KEY_WRONG_CHARACTERS}' 必须是字典")
        else:
            for key, value in wc.items():
                if not isinstance(value, list) or len(value) == 0:
                    errors.append(f"{ke.KEY_WRONG_CHARACTERS}['{key}'] 必须是非空列表")

        # ---- 校验 similar_characters ----
        sc = new_data[ke.KEY_SIMILAR_CHARACTERS]
        if not isinstance(sc, dict):
            errors.append(f"'{ke.KEY_SIMILAR_CHARACTERS}' 必须是字典")
        else:
            for key, value in sc.items():
                if not isinstance(value, list) or len(value) == 0:
                    errors.append(f"{ke.KEY_SIMILAR_CHARACTERS}['{key}'] 必须是非空列表")

        # ---- 校验 common_errors ----
        ce = new_data[ke.KEY_COMMON_ERRORS]
        if not isinstance(ce, dict):
            errors.append(f"'{ke.KEY_COMMON_ERRORS}' 必须是字典")
        else:
            for key, value in ce.items():
                if not isinstance(value, list) or len(value) == 0:
                    errors.append(f"{ke.KEY_COMMON_ERRORS}['{key}'] 必须是非空列表")

        # ---- 校验 de_fix_pairs ----
        dfp = new_data[ke.KEY_DE_FIX_PAIRS]
        if not isinstance(dfp, dict):
            errors.append(f"'{ke.KEY_DE_FIX_PAIRS}' 必须是字典")
        else:
            for key, value in dfp.items():
                if not isinstance(key, str) or not key.strip():
                    errors.append(f"{ke.KEY_DE_FIX_PAIRS} 的键必须是非空字符串")
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{ke.KEY_DE_FIX_PAIRS}['{key}'] 的值必须是非空字符串")

        if errors:
            raise HTTPException(status_code=400, detail="配置校验失败:\n" + "\n".join(errors))

        # 保存文件
        file_util.write_json(new_data, config.MOUNT_PATH_FILE_SPELL_RULES_JSON)
        logger.info("💾 拼写规则配置已写入文件", module_name=CHINESE_NAME)

        # 热重载
        try:
            config_loader.reload(pa.FILE_SPELL_RULES_JSON)
            logger.info("🔄 拼写规则热重载完成", module_name=CHINESE_NAME)
        except Exception as e:
            logger.exception(f"❌ 拼写规则热重载失败：{str(e)}", module_name=CHINESE_NAME)

        return {
            ke.KEY_STATUS: ke.KEY_SUCCESS,
            ke.KEY_MESSAGE: "拼写规则配置已保存并重载"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("💥 保存拼写规则配置时发生未预期错误", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@app.get("/api/card-config")
async def get_card_config():
    logger.info("查询首页卡片配置", module_name=CHINESE_NAME)
    try:
        image_count = config.IMAGE_COUNT or 218
        refresh_interval_ms = config.REFRESH_INTERVAL_MS or 300000
        return {
            ke.KEY_IMAGE_COUNT: image_count,
            ke.KEY_REFRESH_INTERVAL_MS: refresh_interval_ms
        }
    except Exception as e:
        logger.exception("❌ 获取首页卡片配置失败", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"获取首页卡片配置: {str(e)}")


# @app.get("/api/test")
# async def get_test():
#     try:
#         sse_manager = get_sse_manager()
#         await sse_manager.send_pipeline_event("test-0123", ke.KEY_HUMAN_INTERVENTION_REQUIRED, {
#             ke.KEY_TITLE: va.VAL_HUMAN_USER,
#             ke.KEY_CONTENT: "测试内容",
#             ke.KEY_META: {ke.KEY_STAGE: ke.KEY_HUMAN_INTERVENTION_REQUIRED, ke.KEY_STATUS: ke.KEY_RUNNING}
#         })
#         logger.info("📡 SSE 通知已发送 | 任务: test-0123", module_name=CHINESE_NAME)
#         return {
#             ke.KEY_STATUS: ke.KEY_SUCCESS,
#             ke.KEY_MESSAGE: "SSE 通知发送成功"
#         }
#     except Exception as e:
#         logger.error(f"SSE 通知发送失败: {e}", module_name=CHINESE_NAME)
#         raise HTTPException(status_code=500, detail=f"SSE 通知发送失败: {str(e)}")


logger.info("🎉 FastAPI 应用初始化完成！", module_name=CHINESE_NAME)
logger.info("📜 本工具基于 MIT 许可证发布，商业/个人使用前请查阅 LICENSE 与 EULA 文件。", module_name=CHINESE_NAME)
