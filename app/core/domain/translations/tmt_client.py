"""腾讯 TMT 翻译客户端 —— SDK 懒加载、密钥占位符检测、TMT 调用、slugize。

从 routers/translations.py 提取。原文件中 _validate_credentials_or_raise / _call_tencent_tmt
直接抛 HTTPException，本模块改为抛 TranslationError（携带 status_code + detail），
由路由层捕获后转为 HTTPException，保持 domain 层零 FastAPI 依赖。
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any, Dict, Optional

from app.config.config import config
from app.utils.logger import LoggerManager as logger


class TranslationError(Exception):
    """翻译领域异常，携带 HTTP status_code + detail dict，供路由层转换。"""

    def __init__(self, status_code: int, detail: Dict[str, Any]):
        self.status_code = status_code
        self.detail = detail
        super().__init__(json.dumps(detail, ensure_ascii=False))


_TMT_IMPORT_LOCK = threading.Lock()
_TMT_STATE: Dict[str, Any] = {"available": False, "error": None, "_loaded": False}

_PLACEHOLDER_MARKERS = (
    "请输入",
    "请填写",
    "your-",
    "YOUR_",
    "xxx",
    "XXX",
    "***",
    "changeme",
    "CHANGEME",
)


def _ensure_tmt_sdk_loaded() -> None:
    """懒加载腾讯 TMT SDK，失败就把错误写入全局状态。只在首次调用时真正 import。"""
    if _TMT_STATE["_loaded"]:
        return
    with _TMT_IMPORT_LOCK:
        if _TMT_STATE["_loaded"]:
            return
        try:
            from tencentcloud.common import credential  # noqa: F401
            from tencentcloud.common.profile.client_profile import ClientProfile  # noqa: F401
            from tencentcloud.tmt.v20180321 import models, tmt_client  # noqa: F401

            _TMT_STATE["available"] = True
            _TMT_STATE["error"] = None
            _TMT_STATE["models"] = models
            _TMT_STATE["tmt_client"] = tmt_client
            _TMT_STATE["credential"] = credential
            _TMT_STATE["ClientProfile"] = ClientProfile
        except Exception as e:  # pragma: no cover - 依赖可选
            _TMT_STATE["available"] = False
            _TMT_STATE["error"] = f"腾讯 TMT SDK 未安装或导入失败: {e}"
        finally:
            _TMT_STATE["_loaded"] = True


def is_placeholder(val: Any) -> bool:
    """判断某个值是不是未被替换的默认占位符。"""
    if val is None:
        return True
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return True
        return any(m in s for m in _PLACEHOLDER_MARKERS)
    return False


async def lazy_sync_if_needed(engine: Any) -> None:
    """
    最小力度的「懒同步」兜底：
      - 如果 Config 单例的两个腾讯密钥属性已经是有效值（非占位符非空），直接返回
      - 如果仍是占位符，立刻调一次 Config.sync_from_engine(engine) + Config.reload()
        把 Rust 引擎 global_config 表里的最新值同步到 Python Config 单例属性上。
    """
    sid = getattr(config, "TENCENT_TMT_SECRET_ID", None)
    skey = getattr(config, "TENCENT_TMT_SECRET_KEY", None)
    if (not is_placeholder(sid)) and (not is_placeholder(skey)):
        return
    if engine is None:
        return
    if not hasattr(config, "sync_from_engine"):
        return
    try:
        changed = bool(await config.sync_from_engine(engine))
        if hasattr(config, "reload") and changed:
            config.reload()
    except Exception:
        return


def validate_credentials() -> None:
    sid = getattr(config, "TENCENT_TMT_SECRET_ID", None)
    skey = getattr(config, "TENCENT_TMT_SECRET_KEY", None)
    sid_s = "" if sid is None else str(sid).strip()
    skey_s = "" if skey is None else str(skey).strip()
    if is_placeholder(sid_s) or is_placeholder(skey_s):
        raise TranslationError(
            status_code=503,
            detail={
                "code": "TRANSLATION_CREDENTIAL_UNCONFIGURED",
                "message": "全局配置未填写腾讯云 SecretId / SecretKey，请在 Rust 全局配置面板（或 /config 配置页）写入有效值后再重试。",
                "provider": getattr(config, "TRANSLATION_PROVIDER", "tencent_tmt") or "tencent_tmt",
            },
        )


def call_tencent_tmt(source_text: str, source_lang: str, target_lang: str) -> str:
    _ensure_tmt_sdk_loaded()
    if not _TMT_STATE["available"]:
        raise TranslationError(
            status_code=503,
            detail={
                "code": "TRANSLATION_SDK_MISSING",
                "message": _TMT_STATE["error"] or "腾讯 TMT SDK 不可用",
                "provider": "tencent_tmt",
            },
        )

    region = getattr(config, "TENCENT_TMT_REGION", "ap-beijing") or "ap-beijing"
    sid = str(getattr(config, "TENCENT_TMT_SECRET_ID", "") or "").strip()
    skey = str(getattr(config, "TENCENT_TMT_SECRET_KEY", "") or "").strip()

    cred_mod = _TMT_STATE["credential"]
    tmt_client_cls = _TMT_STATE["tmt_client"]
    client_profile_cls = _TMT_STATE["ClientProfile"]
    models_mod = _TMT_STATE.get("models")

    try:
        cred = cred_mod.Credential(sid, skey)
        client = tmt_client_cls.TmtClient(cred, region, client_profile_cls())

        params = {
            "Source": source_lang,
            "Target": target_lang,
            "ProjectId": 0,
            "SourceText": source_text,
        }

        logger.info(f"腾讯 TMT 调用开始：source={source_lang}, target={target_lang}, region={region}, text_len={len(source_text)}")

        def _extract_target_text(resp_obj: Any) -> Optional[str]:
            if resp_obj is None:
                return None
            def _pick(d: dict) -> Optional[str]:
                inner = d.get("Response")
                if isinstance(inner, dict):
                    t = inner.get("TargetText") or inner.get("targetText")
                    if isinstance(t, str) and t.strip():
                        return t
                t = d.get("TargetText") or d.get("targetText")
                if isinstance(t, str) and t.strip():
                    return t
                return None
            if isinstance(resp_obj, bytes):
                try:
                    decoded = json.loads(resp_obj.decode("utf-8"))
                    if isinstance(decoded, dict):
                        return _pick(decoded)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
                return None
            if isinstance(resp_obj, dict):
                return _pick(resp_obj)
            for attr in ("TargetText", "targetText"):
                val = getattr(resp_obj, attr, None)
                if isinstance(val, str) and val:
                    return val
            return None

        target_text: Optional[str] = None
        resp = None
        last_err: Optional[Exception] = None

        # --- 策略 1：官方 TextTranslate 便捷方法（主流 SDK 版本） ---
        req_cls = (
            getattr(models_mod, 'TextTranslateRequest', None)
            or getattr(models_mod, 'TextTranslateReq', None)
        ) if models_mod else None

        logger.info(f"TMT 策略1检查：req_cls={'found' if req_cls else 'None'}, has_text_translate={hasattr(client, 'TextTranslate')}")
        if req_cls is not None and hasattr(client, 'TextTranslate'):
            try:
                req = req_cls()
                req.from_json_string(json.dumps(params, ensure_ascii=False))
                resp = client.TextTranslate(req)
                logger.info(f"腾讯 TMT 调用成功(便捷方法)：响应类型={type(resp).__name__}")
                target_text = _extract_target_text(resp)
            except Exception as e:
                last_err = e
                logger.warning(f"腾讯 TMT 便捷方法失败，尝试通用 call 降级: {type(e).__name__}: {e}")

        # --- 策略 2：通用 client.call 降级 ---
        if target_text is None:
            try:
                resp = client.call("TextTranslate", params)
                logger.info(f"腾讯 TMT 调用成功(通用call)：响应类型={type(resp).__name__}")
                target_text = _extract_target_text(resp)
            except Exception as e:
                last_err = e
                logger.warning(f"腾讯 TMT 通用 call 也失败: {type(e).__name__}: {e}")

        if not isinstance(target_text, str) or not target_text.strip():
            logger.error(
                f"腾讯 TMT 返回 TargetText 为空，响应类型={type(resp).__name__ if resp is not None else 'unknown'}，"
                f"最后错误={type(last_err).__name__ if last_err else 'N/A'}"
            )
            if isinstance(resp, dict):
                logger.error(f"响应字典键: {list(resp.keys())}")
            elif isinstance(resp, bytes):
                logger.error(f"响应 bytes 前200字节: {resp[:200]!r}")
            elif resp is not None:
                logger.error(f"响应对象属性: {[a for a in dir(resp) if not a.startswith('_')]}")
            raise RuntimeError("腾讯 TMT 返回 TargetText 为空")

        logger.info(f"腾讯 TMT 翻译完成：原文{len(source_text)}字 → 译文{len(target_text)}字")
        return target_text.strip()
    except TranslationError:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"腾讯 TMT 调用异常：type={type(e).__name__}, msg={e}\n{tb}")
        raise TranslationError(
            status_code=502,
            detail={
                "code": "TRANSLATION_UPSTREAM_ERROR",
                "message": f"调用腾讯 TMT 失败: {e}",
                "provider": "tencent_tmt",
            },
        )


_NON_SLUG_CHARS = re.compile(r"[^A-Za-z0-9_]+")
_MULTI_UNDERSCORE = re.compile(r"_+")


def slugize(english_text: str) -> str:
    s = (english_text or "").strip().lower()
    s = _NON_SLUG_CHARS.sub("_", s)
    s = _MULTI_UNDERSCORE.sub("_", s).strip("_")
    return s or "tag"
