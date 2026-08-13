import json
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.routers._common import _get_engine

router = APIRouter(prefix="/api/label-configs", tags=["标签配置 (Label Configs)"])


@router.get("/config/get", summary="获取作品标签配置（快捷单例接口）")
async def get_label_config_shortcut(
    session_id: str = Query(..., description="作品会话 ID"),
    engine=Depends(_get_engine),
) -> Any:
    return engine.label_config_get(session_id)


@router.post("/config/save", summary="保存作品标签配置（快捷单例接口：存在则 UPSERT 更新，不存在则创建）")
async def save_label_config_shortcut(
    session_id: str = Query(..., description="作品会话 ID"),
    payload: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    if "config_json" in payload:
        cfg = _parse_config_json(payload.get("config_json"))
        _validate_offsets(cfg)
        payload["config_json"] = json.dumps(cfg, ensure_ascii=False)
    existing = engine.label_config_get(session_id)
    if existing and isinstance(existing, dict):
        engine.label_config_update(session_id, json.dumps(payload, ensure_ascii=False))
    else:
        payload.setdefault("session_id", session_id)
        engine.label_config_create(json.dumps(payload, ensure_ascii=False))
    return {"ok": True}


def _parse_config_json(payload: Any) -> Dict[str, Any]:
    """把 config_json 字段统一解析成 dict，兼容字符串和对象两种形式。"""
    if payload is None:
        return {"label_categories": {"subject": [], "style": [], "length": []}, "forbidden_tags": []}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            raise HTTPException(status_code=422, detail={"code": "CONFIG_JSON_INVALID", "message": "config_json 不是合法 JSON"})
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail={"code": "CONFIG_JSON_INVALID", "message": "config_json 必须是对象"})
    if not isinstance(payload.get("label_categories"), dict):
        payload["label_categories"] = {"subject": [], "style": [], "length": []}
    for k in ("subject", "style", "length"):
        if not isinstance(payload["label_categories"].get(k), list):
            payload["label_categories"][k] = []
    if not isinstance(payload.get("forbidden_tags"), list):
        payload["forbidden_tags"] = []
    return payload


def _validate_offsets(cfg: Dict[str, Any]) -> None:
    """对所有分类下所有标签的 literary offsets 做 [-0.5, 0.5] 闭区间校验。"""
    OFFSET_MIN = -0.5
    OFFSET_MAX = 0.5
    lc = cfg.get("label_categories") or {}
    for cat in ("subject", "style", "length"):
        items = lc.get(cat) or []
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            offsets = item.get("offsets")
            if offsets is None:
                continue
            if not isinstance(offsets, dict):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "OFFSETS_INVALID_TYPE",
                        "message": f"[{cat}] 第 {idx + 1} 个标签的 offsets 必须是对象",
                        "category": cat,
                        "index": idx,
                    },
                )
            for dim, v in offsets.items():
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "OFFSETS_NOT_NUMBER",
                            "message": f"[{cat}] 第 {idx + 1} 个标签维度 {dim} 的偏移必须是数字",
                            "category": cat,
                            "index": idx,
                            "dimension": dim,
                        },
                    )
                if v < OFFSET_MIN or v > OFFSET_MAX:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "OFFSETS_OUT_OF_RANGE",
                            "message": f"[{cat}] 第 {idx + 1} 个标签维度 {dim} 的偏移必须在 [{OFFSET_MIN}, {OFFSET_MAX}] 区间内，当前值 {v}",
                            "category": cat,
                            "index": idx,
                            "dimension": dim,
                            "value": v,
                            "offset_min": OFFSET_MIN,
                            "offset_max": OFFSET_MAX,
                        },
                    )


@router.get("/", summary="查询标签配置列表")
async def list_label_configs(engine=Depends(_get_engine)) -> Any:
    return engine.label_config_list()


@router.get("/{session_id}", summary="查询作品的标签配置")
async def get_label_config(session_id: str, engine=Depends(_get_engine)) -> Any:
    return engine.label_config_get(session_id)


@router.post("/", summary="创建标签配置")
async def create_label_config(
    payload: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    cfg = _parse_config_json(payload.get("config_json"))
    _validate_offsets(cfg)
    payload["config_json"] = json.dumps(cfg, ensure_ascii=False)
    engine.label_config_create(json.dumps(payload, ensure_ascii=False))
    return {"ok": True}


@router.patch("/{session_id}", summary="更新作品的标签配置")
async def update_label_config(
    session_id: str,
    patch: Dict[str, Any] = Body(...),
    engine=Depends(_get_engine),
) -> Any:
    if "config_json" in patch:
        cfg = _parse_config_json(patch.get("config_json"))
        _validate_offsets(cfg)
        patch["config_json"] = json.dumps(cfg, ensure_ascii=False)
    engine.label_config_update(session_id, json.dumps(patch, ensure_ascii=False))
    return {"ok": True}


@router.delete("/{session_id}", summary="删除作品的标签配置")
async def delete_label_config(session_id: str, engine=Depends(_get_engine)) -> Any:
    engine.label_config_delete(session_id)
    return {"ok": True}


@router.delete("/{session_id}/tag/{category}/{tag_id}", summary="删除某分类下指定 id 的标签")
async def delete_category_tag(
    session_id: str,
    category: str,
    tag_id: str,
    engine=Depends(_get_engine),
) -> Any:
    if category not in ("subject", "style", "length"):
        raise HTTPException(
            status_code=422,
            detail={"code": "CATEGORY_INVALID", "message": f"非法分类：{category}，只允许 subject/style/length"},
        )
    raw = engine.label_config_get(session_id)
    payload = (raw and isinstance(raw, dict)) and raw or {}
    cfg = _parse_config_json(payload.get("config_json"))
    items: List[Any] = cfg["label_categories"].get(category) or []
    filtered = [it for it in items if isinstance(it, dict) and str(it.get("id", "")) != str(tag_id)]
    if len(filtered) == len(items):
        raise HTTPException(
            status_code=404,
            detail={"code": "TAG_NOT_FOUND", "message": f"[{category}] 未找到 id={tag_id} 的标签", "category": category, "id": tag_id},
        )
    cfg["label_categories"][category] = filtered
    engine.label_config_update(
        session_id,
        json.dumps({"config_json": json.dumps(cfg, ensure_ascii=False)}, ensure_ascii=False),
    )
    return {"ok": True, "removed_id": tag_id, "category": category}


@router.delete("/{session_id}/forbidden/{tag_name:path}", summary="删除禁止雷点中的指定名称")
async def delete_forbidden_tag(
    session_id: str,
    tag_name: str,
    engine=Depends(_get_engine),
) -> Any:
    raw = engine.label_config_get(session_id)
    payload = (raw and isinstance(raw, dict)) and raw or {}
    cfg = _parse_config_json(payload.get("config_json"))
    forbidden: List[Any] = cfg.get("forbidden_tags") or []
    target = str(tag_name).strip()
    if not target:
        raise HTTPException(status_code=422, detail={"code": "TAG_NAME_EMPTY", "message": "tag_name 不能为空"})
    filtered = [t for t in forbidden if str(t) != target]
    if len(filtered) == len(forbidden):
        raise HTTPException(
            status_code=404,
            detail={"code": "FORBIDDEN_TAG_NOT_FOUND", "message": f"forbidden_tags 中未找到「{target}」"},
        )
    cfg["forbidden_tags"] = filtered
    engine.label_config_update(
        session_id,
        json.dumps({"config_json": json.dumps(cfg, ensure_ascii=False)}, ensure_ascii=False),
    )
    return {"ok": True, "removed_name": target}
