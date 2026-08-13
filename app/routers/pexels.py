import math
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter, HTTPException, Query

from app.common import keys as ke
from app.common import values as va
from app.config.config import config
from app.utils.logger import LoggerManager as logger

CHINESE_NAME = "Pexels素材平台"

router = APIRouter(prefix="/api/pexels", tags=["Pexels 素材平台"])


def get_pexels_headers() -> Dict[str, str]:
    return {
        ke.KEY_USER_AGENT: va.VAL_HEADER_USER_AGENT,
        ke.KEY_AUTHORIZATION: config.PEXELS_ACCESS_KEY,
    }


def _check_pexels_config():
    key = config.PEXELS_ACCESS_KEY
    base_path = config.PEXELS_BASIC_PATH

    if not key or not key.strip():
        logger.warning("MISSING_PEXELES_KEY: Pexels Access Key 不能为空", module_name=CHINESE_NAME)
        raise HTTPException(
            status_code=500,
            detail="MISSING_PEXELES_KEY: Pexels Access Key 不能为空",
        )

    if key.strip() == "请输入 pexels 密钥":
        logger.warning(
            "DEFAULT_PEXELS_KEY: 请将 XINHAI_PEXELS_ACCESS_KEY 替换为真实的 Pexels Access Key",
            module_name=CHINESE_NAME,
        )
        raise HTTPException(
            status_code=500,
            detail="DEFAULT_PEXELS_KEY: 请将 XINHAI_PEXELS_BASIC_PATH 替换为真实的 Pexels Access Key",
        )

    if not base_path or not base_path.strip():
        config.PEXELS_BASIC_PATH = va.VAL_PEXELS_BASIC_URL


def _map_pexels_photo_to_frontend(item: Dict[str, Any]) -> Dict[str, Any]:
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


def find_best_video_match(video_files: list, target_quality: str, target_width: int, target_height: int):
    if not video_files:
        return None

    exact = next(
        (
            vf
            for vf in video_files
            if vf[ke.KEY_QUALITY] == target_quality
            and vf[ke.KEY_WIDTH] == target_width
            and vf[ke.KEY_HEIGHT] == target_height
        ),
        None,
    )
    if exact:
        return exact

    same_quality = [vf for vf in video_files if vf[ke.KEY_QUALITY] == target_quality]
    if same_quality:
        target_area = target_width * target_height
        return min(
            same_quality,
            key=lambda vf: abs(vf[ke.KEY_WIDTH] * vf[ke.KEY_HEIGHT] - target_area),
        )

    target_area = target_width * target_height
    return min(
        video_files,
        key=lambda vf: abs(vf[ke.KEY_WIDTH] * vf[ke.KEY_HEIGHT] - target_area),
    )


def _map_pexels_video_to_frontend(item: Dict[str, Any]) -> Dict[str, Any]:
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


@router.get("/search/photos", summary="搜索 Pexels 图片")
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
            timeout=10,
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
        ke.KEY_RESULTS: results,
    }


@router.get("/search/videos", summary="搜索 Pexels 视频")
async def search_pexels_videos(
    query: str = Query(..., min_length=1),
    page: Optional[int] = Query(1, ge=1),
    per_page: Optional[int] = Query(12, ge=1, le=80),
    size: Optional[str] = None,
    orientation: Optional[str] = None,
    locale: Optional[str] = None,
):
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
            timeout=10,
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
        ke.KEY_RESULTS: results,
    }
