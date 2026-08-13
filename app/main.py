import json
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Optional
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.staticfiles import StaticFiles as _BaseStaticFiles
from starlette.types import Scope as _Scope
from app.config.config import config
from app.utils.logger import LoggerManager as logger
from app.routers import register_all_routers


class CachedStaticFiles(_BaseStaticFiles):
    """给 /static/ 下的静态资源附加强缓存头，避免每次切页都做 304 协商。

    缓存策略（纯静态、内容稳定带版本查询串时安全）：
    - 对不可变资源（js/css/图片/字体，路径带 ?v=x.x 查询串或 md5 后缀）：
      Cache-Control: public, max-age=86400, immutable  (1 天强缓存)
    - favicon.ico 同等处理（按文件后缀扩展不区分查询串）
    - 不影响 pages 路由返回的 HTML：HTML 走 no-cache，在 pages.py 单独设置
    """

    # 命中强缓存的后缀白名单（静态资源默认都能带版本查询串）
    _CACHED_EXT = (
        ".js", ".css",
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
        ".woff", ".woff2", ".ttf", ".otf", ".eot",
        ".mp3", ".wav", ".ogg", ".mp4", ".webm"
    )

    def file_response(
        self,
        full_path: str,
        stat_result: os.stat_result,
        scope: _Scope,
        status_code: int = 200,
    ) -> Response:
        resp = super().file_response(
            full_path=full_path,
            stat_result=stat_result,
            scope=scope,
            status_code=status_code,
        )
        ext = os.path.splitext(full_path)[1].lower()
        if ext in self._CACHED_EXT:
            resp.headers["Cache-Control"] = "public, max-age=86400, immutable"
        return resp

if TYPE_CHECKING:
    from app.core.schedule.scheduler_manager import SchedulerManager

logger.inject_config(config)
CHINESE_NAME = "FastAPI启动中心"
scheduler_instance: Optional['SchedulerManager'] = None


def _reset_stale_tasks(engine) -> int:
    """服务重启时清理残留任务：将所有 pending/running 状态的任务标记为 failed。

    服务重启意味着所有进行中的任务都已中断，不可能再完成，必须标记为失败以解除幂等锁。
    遍历所有作品 → 所有任务，仅更新 status 字段，不影响已保存的内容。
    """
    count = 0
    works = list(engine.work_list() or [])
    for work in works:
        if not isinstance(work, dict):
            continue
        session_id = work.get("session_id")
        if not session_id:
            continue
        try:
            tasks = list(engine.task_list(session_id, None, "created_at", False) or [])
        except (ValueError, TypeError):
            continue
        for task in tasks:
            if not isinstance(task, dict):
                continue
            status = str(task.get("status") or "").lower()
            if status not in ("pending", "running"):
                continue
            task_id = task.get("id")
            if task_id is None:
                continue
            try:
                engine.task_update(str(task_id), json.dumps({"status": "failed"}))
                count += 1
            except Exception:
                pass
    return count


@asynccontextmanager
async def lifespan(app: FastAPI):
    """这里的函数参数不能省"""
    logger.info("系统启动中...", module_name=CHINESE_NAME)
    global scheduler_instance
    from app.core.registry.global_singleton_registry import GlobalSingletonRegistry
    _ = config.TEXT_DEFAULT_VENDOR
    logger.info(f"配置就绪：LLM={config.TEXT_DEFAULT_VENDOR}", module_name=CHINESE_NAME)

    if not config.PATH_FILE_INDEX_HTML.exists():
        logger.warning("主页面 index.html 不存在！", module_name=CHINESE_NAME)

    try:
        from app.core.services.local_tools import LocalTextTools
        text_tools = LocalTextTools.get_instance()
        await text_tools.load_vocab_async()
        logger.info("词库白名单已加载到 jieba", module_name=CHINESE_NAME)
    except Exception as e:
        logger.warning(f"词库白名单加载跳过（非本批次必需）：{e}", module_name=CHINESE_NAME)

    registry = await GlobalSingletonRegistry.get_instance()
    engine = registry.get_or_initialize_cognitive_engine()
    if engine is not None:
        # 清理残留任务：服务重启后，所有 pending/running 任务已中断，标记为 failed 解除幂等锁
        try:
            _stale_count = _reset_stale_tasks(engine)
            if _stale_count > 0:
                logger.info(
                    f"已清理 {_stale_count} 个残留任务（pending/running → failed）",
                    module_name=CHINESE_NAME,
                )
        except Exception as e:
            logger.warning(f"清理残留任务失败（非致命）：{e}", module_name=CHINESE_NAME)

        # 启动期设备授权检查：触发 Rust 引擎明暗双线校验，结果缓存供健康检查读取
        try:
            from app.core.domain.device_auth.auth_probe import init_device_auth_on_startup
            auth_result = init_device_auth_on_startup()
            # 检查是否超限（双重保险：即使 Rust 引擎初始化成功，也要检查授权状态）
            if auth_result:
                verdict = auth_result.get("verdict", "")
                total = auth_result.get("total_unique_devices", 0)
                max_devices = auth_result.get("max_devices", 0)
                if verdict == "over_limit" or total > max_devices:
                    msg = f"设备授权超限（{total}/{max_devices}），服务启动被拒绝。请联系管理员释放设备。"
                    logger.error(msg, module_name=CHINESE_NAME)
                    raise RuntimeError(msg)
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"启动期设备授权检查失败：{e}", module_name=CHINESE_NAME)
    else:
        # 引擎初始化失败：检查是否因设备授权超限导致
        try:
            from app.core.domain.device_auth.auth_probe import probe_device_auth
            auth = probe_device_auth()
            if auth:
                verdict = auth.get("verdict", "")
                total = auth.get("total_unique_devices", 0)
                max_devices = auth.get("max_devices", 0)
                if verdict == "over_limit" or total > max_devices:
                    msg = f"设备授权超限（{total}/{max_devices}），服务启动被拒绝。请联系管理员释放设备。"
                    logger.error(msg, module_name=CHINESE_NAME)
                    raise RuntimeError(msg)
        except RuntimeError:
            raise
        except Exception:
            pass  # 其他异常不阻断

        # 检查是否 Rust 包已安装但初始化失败
        try:
            import cognitor
            # 包已安装但引擎为 None，可能是初始化失败
            logger.error("Rust 引擎初始化失败，服务启动被拒绝", module_name=CHINESE_NAME)
            raise RuntimeError("Rust 引擎初始化失败，服务启动被拒绝。")
        except ModuleNotFoundError:
            # Rust 包未安装，允许降级
            logger.warning("Rust 引擎包未安装，跳过引擎初始化", module_name=CHINESE_NAME)
    if engine is not None and hasattr(config, "sync_from_engine"):
        try:
            changed = await config.sync_from_engine(engine)
            if changed:
                config._load()
            cache_size = len(getattr(config, "_raw_config_cache", {}) or {})
            logger.info(f"配置中心已从 Rust 同步 XINHAI 配置（{cache_size} 项）", module_name=CHINESE_NAME)
        except Exception as e:
            logger.warning(f"从 Rust 同步配置失败（非致命，保留默认）：{e}", module_name=CHINESE_NAME)
    else:
        if engine is None:
            logger.warning("Rust 引擎未就绪，跳过配置同步", module_name=CHINESE_NAME)
        else:
            logger.warning("当前 Config 版本未实现 sync_from_engine，跳过同步", module_name=CHINESE_NAME)

    try:
        from app.core.schedule import start_scheduled_tasks
        scheduler_instance = start_scheduled_tasks()
    except Exception as e:
        logger.warning(f"定时任务调度器启动跳过：{e}", module_name=CHINESE_NAME)

    try:
        from app.core.services.sse_manager import get_sse_manager
        sse_manager = get_sse_manager()
        _app_state = getattr(app, "state", None)
        if _app_state is not None:
            _app_state._sse_manager = sse_manager
        logger.info("SSE 管理器已初始化", module_name=CHINESE_NAME)
    except Exception as e:
        logger.warning(f"SSE 管理器初始化跳过：{e}", module_name=CHINESE_NAME)
        _app_state = getattr(app, "state", None)
        if _app_state is not None:
            _app_state._sse_manager = None

    logger.info("所有启动任务完成", module_name=CHINESE_NAME)

    # 启动阶段 WAL checkpoint：
    # 若上次异常停机（例如 Docker SIGKILL、断电）导致 WAL 中残留未合并数据，
    # 在服务正式对外开放请求前执行一次合并，确保主库文件处于完整状态。
    # Rust 层会先 PASSIVE 查询状态，log==0 时直接跳过，不做多余 fsync。
    try:
        registry = await GlobalSingletonRegistry.get_instance()
        registry.force_wal_checkpoint(stage="startup")
    except Exception as e:
        logger.error(f"启动阶段 WAL checkpoint 异常：{e}", exc_info=True, module_name=CHINESE_NAME)

    yield

    logger.info("系统正在关闭，执行优雅停机...", module_name=CHINESE_NAME)

    # 1. WAL checkpoint：确保所有数据从 WAL 文件合并回主数据库
    try:
        registry = await GlobalSingletonRegistry.get_instance()
        registry.force_wal_checkpoint(stage="shutdown")
    except Exception as e:
        logger.error(f"关闭阶段 WAL checkpoint 异常：{e}", exc_info=True, module_name=CHINESE_NAME)

    _app_state = getattr(app, "state", None)
    if _app_state is not None and getattr(_app_state, '_shutdown_meta', None):
        try:
            await _app_state._shutdown_meta(graceful=True)
        except Exception as e:
            logger.error(f"关闭元认知失败：{e}", exc_info=True)

    if _app_state is not None and getattr(_app_state, '_sse_manager', None):
        try:
            _app_state._sse_manager.clear_event_history()
        except Exception as e:
            logger.error(f"清空 SSE 事件历史失败：{e}", exc_info=True)

    if scheduler_instance:
        try:
            scheduler_instance.shutdown()
        except Exception as e:
            logger.error(f"关闭调度器失败：{e}", exc_info=True)

    try:
        registry = await GlobalSingletonRegistry.get_instance()
        await registry.reload_all()
        logger.info("全局注册中心资源已安全重置", module_name=CHINESE_NAME)
    except Exception as e:
        logger.error(f"关闭全局注册中心异常：{e}", exc_info=True)

    logger.info("系统完全退出", module_name=CHINESE_NAME)


app = FastAPI(lifespan=lifespan, title="心海")

app.mount("/static", CachedStaticFiles(directory="app/static"), name="static")
app.mount("/media/image", CachedStaticFiles(directory=str(config.IMAGE_DIR)), name="media-image")
app.mount("/media/audio", CachedStaticFiles(directory=str(config.AUDIO_DIR)), name="media-audio")
app.mount("/media/video", CachedStaticFiles(directory=str(config.VIDEO_DIR)), name="media-video")
app.mount("/media/lyric", CachedStaticFiles(directory=str(config.LYRIC_DIR)), name="media-lyric")


@app.middleware("http")
async def _html_no_cache_middleware(request: Request, call_next):
    """兜底：所有 text/html 响应强制禁用强缓存 + 迁移期清浏览器 HTTP cache。

    Headers 五层组合彻底清掉所有旧缓存：
    - Cache-Control: no-cache, no-store, must-revalidate, max-age=0  （永不落本地，允许 304 协商）
    - Pragma: no-cache                         （HTTP/1.0 代理/老浏览器兼容）
    - Expires: 0                               （老浏览器立即过期语义）
    - Vary: *                                  （任何维度变化都不允许用缓存副本）
    - Clear-Site-Data: "cache"                 （迁移期强制清掉浏览器磁盘里的旧 HTML + 旧静态资源 404 缓存响应）
    """
    resp = await call_next(request)
    ct = resp.headers.get("content-type") or resp.headers.get("Content-Type") or ""
    if "text/html" in ct:
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        resp.headers["Vary"] = "*"
        resp.headers["Clear-Site-Data"] = '"cache"'
    return resp


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError):
    """Rust 层 PyO3 桥接抛出的业务校验错误统一映射为 HTTP 400 + 中文可读描述，避免 500 裸错误。

    触发来源：
    - 语义词汇（temporal.sort_index 冲突、字段校验失败等）；
    - 其他 Rust 控制器经 cognitor_to_py_err 映射的 CognitorError。

    Python 内部非业务 RuntimeError 也会走这里：日志会保留原始堆栈，响应层仍返回 400 文本，
    总比默认 500 + 通用错误更可读。
    """
    msg = str(exc) or "运行时错误"
    logger.error(
        f"Rust/Python RuntimeError 已转 400: {msg}",
        module_name=CHINESE_NAME,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=400,
        content={"detail": msg},
    )


register_all_routers(app)

logger.info("FastAPI 应用初始化完成！", module_name=CHINESE_NAME)
logger.info("本工具基于 MIT 许可证发布，商业/个人使用前请查阅 LICENSE 与 EULA 文件。", module_name=CHINESE_NAME)
