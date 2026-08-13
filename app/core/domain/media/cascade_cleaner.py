"""跨 media 类型级联清理工具。

统一处理：
  - 删除作品（按 session_id 过滤 audio/image/video 记录 → 删物理文件 → 删 DB 记录）
  - 删除任务 / 级联删除任务（按 task_id 集合过滤 media → 删物理文件 → 删 DB 记录）

依赖 Rust 引擎层后续在 image/audio/video 实体上补充的 `session_id` / `task_id` 归属字段；
若实体尚未提供该字段，则本模块自动退化为「不清理 media」，保证删除作品/任务的主流程不抛错。

所有清理操作对单条失败静默兜底（记录 warning 但不抛异常），避免一条孤儿文件导致整体删除失败。
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, Iterable, List, Optional, Set

from app.core.domain.audios.physical_file_cleaner import physically_delete_audio_files
from app.core.domain.images.physical_file_cleaner import physically_delete_image_files
from app.core.domain.videos.physical_file_cleaner import physically_delete_video_files
from app.utils.logger import LoggerManager as logger

LOG_MODULE = "Media级联清理"


# ---------------------------------------------------------------------------
# 1) 任务子树收集
# ---------------------------------------------------------------------------

def _safe_list_tasks(engine, session_id: str) -> List[Dict[str, Any]]:
    """调用 engine.task_list 并做 Dict 化，异常时返回空列表。"""
    try:
        raw = engine.task_list(session_id, None, "id", False, True)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[收集子任务] 拉取 session={session_id} 的任务列表失败，将跳过子任务级联识别: {e}",
            module_name=LOG_MODULE,
        )
        return []
    if raw is None:
        return []
    # engine 返回的可能是 JSON 字符串或 list of dict
    if isinstance(raw, str):
        import json
        try:
            parsed = json.loads(raw)
            return list(parsed) if isinstance(parsed, list) else []
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[收集子任务] 解析 task_list JSON 失败: {e}", module_name=LOG_MODULE)
            return []
    if isinstance(raw, (list, tuple)):
        return [r for r in raw if isinstance(r, dict)]
    return []


def collect_task_subtree_ids(engine, root_task_id: int) -> Set[int]:
    """收集某个任务自身 + 其全部后代任务的 id（基于 parent_id 递归）。

    若 engine 中无法拿到该 task 的 session_id，则返回只包含 root_task_id 的单元素集合。
    """
    root = int(root_task_id)
    # 1. 先拿 root task 本身，读取 session_id
    try:
        root_raw = engine.task_get(str(root))
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[收集子任务] task_get({root}) 失败，退化为只清理 root 自己: {e}",
            module_name=LOG_MODULE,
        )
        return {root}
    if root_raw is None:
        return {root}
    root_obj: Dict[str, Any] = root_raw
    if isinstance(root_raw, str):
        import json
        try:
            root_obj = json.loads(root_raw)
        except Exception:  # noqa: BLE001
            root_obj = {}
    session_id = root_obj.get("session_id") if isinstance(root_obj, dict) else None
    if not isinstance(session_id, str) or not session_id.strip():
        return {root}

    all_tasks = _safe_list_tasks(engine, session_id)
    children_map: Dict[int, List[int]] = {}
    for t in all_tasks:
        pid_raw = t.get("parent_id")
        if pid_raw is None or pid_raw == 0 or pid_raw == "0" or pid_raw == "":
            continue
        try:
            pid = int(pid_raw)
        except (TypeError, ValueError):
            continue
        try:
            tid = int(t.get("id"))
        except (TypeError, ValueError):
            continue
        children_map.setdefault(pid, []).append(tid)

    collected: Set[int] = {root}
    queue: deque = deque([root])
    while queue:
        cur = queue.popleft()
        for child in children_map.get(cur, ()):
            if child not in collected:
                collected.add(child)
                queue.append(child)
    return collected


# ---------------------------------------------------------------------------
# 2) media 记录按归属过滤 + 物理文件 + DB 记录清理
# ---------------------------------------------------------------------------

def _iter_items(items) -> Iterable[Dict[str, Any]]:
    """engine.audio_list/image_list/video_list 返回值统一规整为 iter[dict]。"""
    if items is None:
        return []
    if isinstance(items, str):
        import json
        try:
            parsed = json.loads(items)
            return [x for x in parsed if isinstance(x, dict)]
        except Exception:  # noqa: BLE001
            return []
    if isinstance(items, (list, tuple)):
        return [x for x in items if isinstance(x, dict)]
    return []


def _has_attrib(obj: Dict[str, Any], key: str) -> bool:
    """判断 dict 中是否包含某个非空字段（用于检测 Rust 层已补归属字段）。"""
    if not isinstance(obj, dict):
        return False
    v = obj.get(key)
    if v is None:
        return False
    if isinstance(v, str) and not v.strip():
        return False
    return True


def _cleanup_audios(engine, session_id: Optional[str], task_ids: Optional[Set[int]]) -> int:
    """按 session_id / task_ids 过滤 audio 并清理物理文件+DB 记录，返回清理条数。"""
    try:
        all_audio = engine.audio_list()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[清理audio] audio_list 调用失败，跳过: {e}", module_name=LOG_MODULE)
        return 0
    matched_ids: List[str] = []
    for a in _iter_items(all_audio):
        if not a.get("id"):
            continue
        if session_id and _has_attrib(a, "session_id"):
            if str(a.get("session_id")) != str(session_id):
                continue
        elif session_id:
            # Rust 层尚未返回 session_id 归属 → 无法按作品过滤，跳过
            continue
        if task_ids and _has_attrib(a, "task_id"):
            try:
                tid = int(a.get("task_id"))
            except (TypeError, ValueError):
                continue
            if tid not in task_ids:
                continue
        elif task_ids:
            # Rust 层尚未返回 task_id 归属 → 无法按任务过滤，跳过
            continue
        matched_ids.append(str(a["id"]))
        physically_delete_audio_files(a)

    for mid in matched_ids:
        try:
            engine.audio_delete(mid)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[清理audio] DB 删除 audio id={mid} 失败: {e}", module_name=LOG_MODULE)
    return len(matched_ids)


def _cleanup_images(engine, session_id: Optional[str], task_ids: Optional[Set[int]]) -> int:
    """按 session_id / task_ids 过滤 image 并清理物理文件+DB 记录，返回清理条数。"""
    try:
        all_images = engine.image_list()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[清理image] image_list 调用失败，跳过: {e}", module_name=LOG_MODULE)
        return 0
    matched_ids: List[str] = []
    for im in _iter_items(all_images):
        if not im.get("id"):
            continue
        if session_id and _has_attrib(im, "session_id"):
            if str(im.get("session_id")) != str(session_id):
                continue
        elif session_id:
            continue
        if task_ids and _has_attrib(im, "task_id"):
            try:
                tid = int(im.get("task_id"))
            except (TypeError, ValueError):
                continue
            if tid not in task_ids:
                continue
        elif task_ids:
            continue
        matched_ids.append(str(im["id"]))
        physically_delete_image_files(im)

    for mid in matched_ids:
        try:
            engine.image_delete(mid)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[清理image] DB 删除 image id={mid} 失败: {e}", module_name=LOG_MODULE)
    return len(matched_ids)


def _cleanup_videos(engine, session_id: Optional[str], task_ids: Optional[Set[int]]) -> int:
    """按 session_id / task_ids 过滤 video 并清理物理文件+DB 记录，返回清理条数。"""
    try:
        all_videos = engine.video_list()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[清理video] video_list 调用失败，跳过: {e}", module_name=LOG_MODULE)
        return 0
    matched_ids: List[str] = []
    for v in _iter_items(all_videos):
        if not v.get("id"):
            continue
        if session_id and _has_attrib(v, "session_id"):
            if str(v.get("session_id")) != str(session_id):
                continue
        elif session_id:
            continue
        if task_ids and _has_attrib(v, "task_id"):
            try:
                tid = int(v.get("task_id"))
            except (TypeError, ValueError):
                continue
            if tid not in task_ids:
                continue
        elif task_ids:
            continue
        matched_ids.append(str(v["id"]))
        physically_delete_video_files(v)

    for mid in matched_ids:
        try:
            engine.video_delete(mid)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[清理video] DB 删除 video id={mid} 失败: {e}", module_name=LOG_MODULE)
    return len(matched_ids)


def cascade_cleanup_media_by_work(engine, session_id: str) -> Dict[str, int]:
    """删除作品前调用：按 session_id 清理 audio/image/video 记录与物理文件。

    Rust 层尚未补归属字段时，全部跳过并返回 0；补完后自动生效。
    """
    if not isinstance(session_id, str) or not session_id.strip():
        return {"audio": 0, "image": 0, "video": 0}
    a = _cleanup_audios(engine, session_id=session_id, task_ids=None)
    i = _cleanup_images(engine, session_id=session_id, task_ids=None)
    v = _cleanup_videos(engine, session_id=session_id, task_ids=None)
    logger.info(
        f"[按作品清理media] session={session_id!r} 完成: audio={a}, image={i}, video={v}",
        module_name=LOG_MODULE,
    )
    return {"audio": a, "image": i, "video": v}


def cascade_cleanup_media_by_task_ids(engine, task_ids: Iterable[int]) -> Dict[str, int]:
    """删除任务（含级联删除子任务）前调用：按 task_id 集合清理 media。"""
    ids = {int(t) for t in task_ids}
    if not ids:
        return {"audio": 0, "image": 0, "video": 0}
    a = _cleanup_audios(engine, session_id=None, task_ids=ids)
    i = _cleanup_images(engine, session_id=None, task_ids=ids)
    v = _cleanup_videos(engine, session_id=None, task_ids=ids)
    logger.info(
        f"[按任务清理media] task_ids({len(ids)}条) 完成: audio={a}, image={i}, video={v}",
        module_name=LOG_MODULE,
    )
    return {"audio": a, "image": i, "video": v}


# ---------------------------------------------------------------------------
# 3) 便捷：写入归属（在创建 media 路由中使用）
# ---------------------------------------------------------------------------

def attach_ownership(
    payload: Dict[str, Any],
    session_id: Optional[str] = None,
    task_id: Optional[int] = None,
) -> Dict[str, Any]:
    """在不覆盖 payload 中已显式填写值的前提下，补齐 session_id / task_id 归属字段。

    直接就地修改并返回 payload，方便链式调用：
        payload = attach_ownership(payload, session_id=sid, task_id=t)
    """
    if not isinstance(payload, dict):
        return payload
    if session_id is not None and isinstance(session_id, str) and session_id.strip():
        payload.setdefault("session_id", session_id)
    if task_id is not None:
        try:
            payload.setdefault("task_id", int(task_id))
        except (TypeError, ValueError):
            pass
    return payload
