import os
from pathlib import Path
from typing import List

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse
from app.common import keys as ke
from app.common.enums import TreeNode, FileUpdateRequest
from app.config.config import config
from app.utils.file_util import FileUtil
from app.utils.logger import LoggerManager as logger

IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg', 'ico'}


CHINESE_NAME = "文件系统"
file_util = FileUtil()

router = APIRouter(prefix="/api", tags=["文件系统 (Files)"])


def build_tree(path: Path, rel_path: str = "") -> List[TreeNode]:
    nodes = []
    try:
        for item in sorted(path.iterdir()):
            rel_item = os.path.join(rel_path, item.name).replace("\\", "/")
            if item.is_dir():
                children = build_tree(item, rel_item)
                nodes.append(
                    TreeNode(
                        label=item.name,
                        key=rel_item,
                        type=ke.KEY_FOLDER,
                        children=children,
                    )
                )
            else:
                ext = item.suffix.lstrip(".").lower() or ke.KEY_TXT
                nodes.append(
                    TreeNode(
                        label=item.name,
                        key=rel_item,
                        type=ke.KEY_FILE,
                        ext=ext,
                    )
                )
    except PermissionError as e:
        logger.warning(f"无权限访问目录：{path}，错误：{e}", module_name=CHINESE_NAME)
        pass
    except Exception as e:
        logger.error(f"构建目录树时发生未知错误：{e}", module_name=CHINESE_NAME)
        pass
    return nodes


@router.get("/tree", response_model=List[TreeNode], summary="获取 DATA_ROOT 目录树")
async def get_directory_tree():
    logger.info("正在获取目录树结构", module_name=CHINESE_NAME)
    if not config.DATA_ROOT.exists():
        logger.error(f"目录树根路径不存在：{config.DATA_ROOT}", module_name=CHINESE_NAME)
        raise HTTPException(status_code=500, detail=f"Data root not found: {config.DATA_ROOT}")
    tree_data = build_tree(config.DATA_ROOT)
    logger.info(f"目录树构建完成，共找到 {len(tree_data)} 个节点", module_name=CHINESE_NAME)
    return tree_data


def _is_likely_text(data: bytes, sample_size: int = 4096) -> bool:
    if not data:
        return True
    sample = data[:sample_size]
    if b"\x00" in sample:
        return False
    non_text_count = 0
    total = len(sample)
    for byte in sample:
        if byte in (9, 10, 13):
            continue
        if 0 <= byte <= 8 or 11 <= byte <= 12 or 14 <= byte <= 31:
            non_text_count += 1
    if non_text_count / total > 0.1:
        return False
    return True


@router.get("/file", summary="查看 DATA_ROOT 下文件内容")
async def get_file_content(
    path: str = Query(..., description="要查看的文件相对路径（基于 /data 根目录）"),
):
    safe_path = (config.DATA_ROOT / path).resolve()
    if not str(safe_path).startswith(str(config.DATA_ROOT.resolve())):
        raise HTTPException(status_code=403, detail="非法路径：检测到路径穿越尝试")
    if not safe_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    ext = safe_path.suffix.lstrip(".").lower() or ke.KEY_TXT

    if ext in IMAGE_EXTENSIONS:
        logger.info(f"成功读取图片文件: {path} (类型: {ext})", module_name=CHINESE_NAME)
        return FileResponse(safe_path)

    try:
        with open(safe_path, ke.KEY_RB) as f:
            raw_data = f.read(4096)
    except Exception as e:
        raise HTTPException(status_code=500, detail="读取文件失败，请查看后端日志获取详细信息")

    if not _is_likely_text(bytes(raw_data)):
        raise HTTPException(status_code=400, detail="文件不可读（非文本格式）")

    content = file_util.read_file(str(safe_path), auto_decode=True)

    if content and content.count("\ufffd") / len(content) > 0.3:
        logger.warning(f"文件包含大量无法识别的字符，可能已损坏：{path}", module_name=CHINESE_NAME)

    logger.info(f"成功读取文本文件: {path} (类型: {ext})", module_name=CHINESE_NAME)

    return {
        ke.KEY_CONTENT: content,
        ke.KEY_EXT: ext,
        ke.KEY_PATH: path,
    }


@router.put("/file", summary="更新 DATA_ROOT 下文本文件内容")
async def update_file_content(
    path: str = Query(..., description="要更新的文件相对路径（基于 /data 根目录）"),
    request: FileUpdateRequest = Body(...),
):
    safe_path = (config.DATA_ROOT / path).resolve()
    if not str(safe_path).startswith(str(config.DATA_ROOT.resolve())):
        raise HTTPException(status_code=403, detail="非法路径：检测到路径穿越尝试")
    if not safe_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        with open(safe_path, ke.KEY_R, encoding=ke.KEY_UTF_8) as f:
            f.read(1024)
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="无法编辑非文本文件")

    success, error_msg = file_util.write_file_with_error(
        file_path=str(safe_path),
        content=request.content,
        encoding=ke.KEY_UTF_8,
    )

    if not success:
        raise HTTPException(status_code=500, detail="写入文件失败，请查看后端日志获取详细信息")

    logger.info(f"文件已更新: {path}", module_name=CHINESE_NAME)
    return {ke.KEY_MESSAGE: "文件更新成功", ke.KEY_PATH: path}
