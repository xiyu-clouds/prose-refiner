"""通用翻译服务路由。

对外提供两个 HTTP 接口：
- POST /api/translations/text    通用文本翻译（未来任何翻译需求都走这个）
- POST /api/translations/tag-id  标签 ID 专用：翻译后再 slugize 成可直接写入 DB 的 id

核心逻辑已提取至 core/domain/translations/tmt_client.py，本文件只做薄路由封装。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config.config import config
from app.routers._common import _get_engine
from app.core.domain.translations.tmt_client import (
    TranslationError,
    lazy_sync_if_needed,
    validate_credentials,
    call_tencent_tmt,
    slugize,
)

router = APIRouter(prefix="/api/translations", tags=["translations"])


# ---------------- 请求模型 ----------------

class TranslationTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000, description="待翻译原文")
    source: str = Field("", description="源语言代码，留空则走全局 TRANSLATION_FROM 默认（通常 zh）")
    target: str = Field("", description="目标语言代码，留空则走全局 TRANSLATION_TO 默认（通常 en）")


class TranslationTextResponse(BaseModel):
    provider: str
    source: str
    target: str
    original: str
    translated: str


class TranslationTagIdRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="中文标签名称（或任意希望转成 slug 的文本）")
    source: str = Field("", description="源语言代码，默认 zh")
    target: str = Field("", description="目标语言代码，默认 en")


class TranslationTagIdResponse(BaseModel):
    provider: str
    source: str
    target: str
    name: str
    translated: str
    id: str


# ---------------- 路由 ----------------

@router.post("/text", response_model=TranslationTextResponse)
async def translate_text(
    payload: TranslationTextRequest,
    engine=Depends(_get_engine),
):
    await lazy_sync_if_needed(engine)

    provider = getattr(config, "TRANSLATION_PROVIDER", "tencent_tmt") or "tencent_tmt"
    if provider != "tencent_tmt":
        raise HTTPException(
            status_code=501,
            detail={
                "code": "TRANSLATION_PROVIDER_NOT_IMPLEMENTED",
                "message": f"暂未实现翻译 provider: {provider}，目前仅支持 tencent_tmt",
                "provider": provider,
            },
        )
    try:
        validate_credentials()
    except TranslationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    src_default = getattr(config, "TRANSLATION_FROM", "zh") or "zh"
    tgt_default = getattr(config, "TRANSLATION_TO", "en") or "en"
    src = (payload.source or src_default).strip() or src_default
    tgt = (payload.target or tgt_default).strip() or tgt_default
    text = payload.text.strip()
    try:
        translated = call_tencent_tmt(text, src, tgt)
    except TranslationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return TranslationTextResponse(
        provider=provider,
        source=src,
        target=tgt,
        original=text,
        translated=translated,
    )


@router.post("/tag-id", response_model=TranslationTagIdResponse)
async def translate_to_tag_id(
    payload: TranslationTagIdRequest,
    engine=Depends(_get_engine),
):
    await lazy_sync_if_needed(engine)

    provider = getattr(config, "TRANSLATION_PROVIDER", "tencent_tmt") or "tencent_tmt"
    if provider != "tencent_tmt":
        raise HTTPException(
            status_code=501,
            detail={
                "code": "TRANSLATION_PROVIDER_NOT_IMPLEMENTED",
                "message": f"暂未实现翻译 provider: {provider}，目前仅支持 tencent_tmt",
                "provider": provider,
            },
        )
    try:
        validate_credentials()
    except TranslationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    src_default = getattr(config, "TRANSLATION_FROM", "zh") or "zh"
    tgt_default = getattr(config, "TRANSLATION_TO", "en") or "en"
    src = (payload.source or src_default).strip() or src_default
    tgt = (payload.target or tgt_default).strip() or tgt_default
    name = payload.name.strip()
    try:
        translated = call_tencent_tmt(name, src, tgt)
    except TranslationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    slug = slugize(translated)
    return TranslationTagIdResponse(
        provider=provider,
        source=src,
        target=tgt,
        name=name,
        translated=translated,
        id=slug,
    )
