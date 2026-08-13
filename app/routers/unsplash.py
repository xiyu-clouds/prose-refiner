from datetime import datetime
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter, HTTPException, Query

from app.common import keys as ke
from app.common import values as va
from app.config.config import config
from app.utils.logger import LoggerManager as logger

CHINESE_NAME = "Unsplash图片平台"

router = APIRouter(prefix="/api/unsplash", tags=["Unsplash 图片平台"])


def get_unsplash_headers() -> Dict[str, str]:
    return {
        ke.KEY_AUTHORIZATION: f"Client-ID {config.UNSPLASH_ACCESS_KEY}",
        ke.KEY_ACCEPT_VERSION: "v1",
        ke.KEY_USER_AGENT: va.VAL_HEADER_USER_AGENT,
    }


def _map_unsplash_photo_to_frontend(item: Dict[str, Any]) -> Dict[str, Any]:
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
        ke.KEY_AUTHOR_URL: user.get(ke.KEY_LINKS, {}).get(ke.KEY_HTML, ""),
    }


def _check_unsplash_config():
    key = config.UNSPLASH_ACCESS_KEY
    base_path = config.UNSPLASH_BASIC_PATH

    if not key or not key.strip():
        logger.warning("MISSING_UNSPLASH_KEY: Unsplash Access Key 不能为空", module_name=CHINESE_NAME)
        raise HTTPException(
            status_code=500,
            detail="MISSING_UNSPLASH_KEY: Unsplash Access Key 不能为空",
        )

    if key.strip() == "请输入 unsplash 密钥":
        logger.warning(
            "DEFAULT_UNSPLASH_KEY: 请将 XINHAI_UNSPLASH_ACCESS_KEY 替换为真实的 Unsplash Access Key",
            module_name=CHINESE_NAME,
        )
        raise HTTPException(
            status_code=500,
            detail="DEFAULT_UNSPLASH_KEY: 请将 XINHAI_UNSPLASH_ACCESS_KEY 替换为真实的 Unsplash Access Key",
        )

    if not base_path or not base_path.strip():
        config.UNSPLASH_BASIC_PATH = va.VAL_UNSPLASH_BASIC_URL


def _map_collection_to_frontend(item: Dict[str, Any]) -> Dict[str, Any]:
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
        ke.KEY_AUTHOR_URL: user.get(ke.KEY_LINKS, {}).get(ke.KEY_HTML, ""),
    }


@router.get("/search/photos", summary="搜索 Unsplash 照片")
async def search_unsplash_photos(
    query: str = Query(..., min_length=1, description="搜索关键词"),
    page: Optional[int] = Query(1, ge=1),
    per_page: Optional[int] = Query(12, ge=1, le=32),
    order_by: Optional[str] = Query(None, regex="^(relevant|latest)$"),
    color: Optional[str] = Query(
        None,
        regex="^(black_and_white|black|white|red|orange|yellow|green|teal|blue|purple|magenta)$",
    ),
    orientation: Optional[str] = Query(None, regex="^(landscape|portrait|squarish)$"),
    content_filter: Optional[str] = Query(None, regex="^(low|high)$"),
    collections: Optional[str] = Query(None, description="逗号分隔的 collection ID 列表"),
):
    _check_unsplash_config()

    unsplash_params: Dict[str, Any] = {
        ke.KEY_QUERY: query,
        ke.KEY_PAGE: page,
        ke.KEY_PER_PAGE: per_page,
    }

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

    resp = None
    try:
        resp = requests.get(
            f"{config.UNSPLASH_BASIC_PATH}{va.VAL_UNSPLASH_SEARCH_PHOTOS_API_SUFFIX}",
            headers=get_unsplash_headers(),
            params=unsplash_params,
            timeout=10,
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

    raw_results = data.get(ke.KEY_RESULTS, [])
    display_results = [_map_unsplash_photo_to_frontend(item) for item in raw_results]

    return {
        ke.KEY_TOTAL: data.get(ke.KEY_TOTAL, 0),
        ke.KEY_TOTAL_PAGES: data.get(ke.KEY_TOTAL_PAGES, 0),
        ke.KEY_RESULTS: display_results,
    }


@router.get("/search/collections", summary="搜索 Unsplash 收藏集")
async def search_unsplash_collections(
    query: str = Query(..., min_length=1, description="搜索关键词"),
    page: Optional[int] = Query(1, ge=1),
    per_page: Optional[int] = Query(10, ge=1, le=30),
):
    _check_unsplash_config()

    unsplash_params = {
        ke.KEY_QUERY: query,
        ke.KEY_PAGE: page,
        ke.KEY_PER_PAGE: per_page,
    }
    resp = None
    try:
        resp = requests.get(
            f"{config.UNSPLASH_BASIC_PATH}{va.VAL_UNSPLASH_SEARCH_COLLECTIONS_API_SUFFIX}",
            headers=get_unsplash_headers(),
            params=unsplash_params,
            timeout=10,
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

    raw_results = data.get(ke.KEY_RESULTS, [])
    display_results = [_map_collection_to_frontend(item) for item in raw_results]

    return {
        ke.KEY_TOTAL: data.get(ke.KEY_TOTAL, 0),
        ke.KEY_TOTAL_PAGES: data.get(ke.KEY_TOTAL_PAGES, 0),
        ke.KEY_RESULTS: display_results,
    }
