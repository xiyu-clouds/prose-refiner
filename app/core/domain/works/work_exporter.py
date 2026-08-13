"""作品完整导出：聚合多类任务数据 → 多级结构 → zip 内存打包。

- 跨层 SSOT：task_type 直接从 app.common.values 引用常量，禁止散写字面量。
- 纯业务编排：不操作 HTTP，不碰响应封装，供 routers/works.py 薄路由调用。
- 运行时依赖 engine（Rust PyO3 桥）提供 task_list / work_get，不引入额外 Python 依赖。

ZIP 目录树结构（按卷·章分层，每个章节独立文件，便于直接打开查看）：
    作品创作包/
    ├── 00-全局剧情.md              谋篇剧情 + 摘要
    ├── 第01卷_卷名/                分卷目录，缺失卷名时仅序号
    │   ├── 00-卷纲.md              卷纲剧情 + 摘要
    │   ├── 01-第1章_章名.md        本章全量创作信息（剧情 / 摘要 / 事件链 / 正文）
    │   ├── 01-第1章_章名-正文.txt  仅本章纯正文，便于复制/拆分阅读
    │   ├── 02-第2章_章名.md
    │   └── 02-第2章_章名-正文.txt
    ├── 第02卷_卷名/
    │   └── ...
    ├── 全书正文.txt                纯正文合集（面向发布/发书，仅卷/章标题+正文）
    └── work.json                   完整结构化数据（schema_version / stats / 多级内容）
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.common.values import (
    VAL_TASK_TYPE_CHAPTER_CONTENT,
    VAL_TASK_TYPE_CHAPTER_EVENTS,
    VAL_TASK_TYPE_CHAPTER_OUTLINE,
    VAL_TASK_TYPE_GLOBAL_OUTLINE,
    VAL_TASK_TYPE_VOLUME_OUTLINE,
)


_INVALID_FS_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def _safe_filename(segment: str, fallback: str = "untitled") -> str:
    cleaned = _INVALID_FS_CHARS.sub("_", (segment or "").strip())
    cleaned = cleaned.strip(" ._")
    return cleaned or fallback


def _index_pad(n: int, width: int = 2) -> str:
    """序号前导零格式化：01/02/10/11 —— 保证文件管理器按名称排序与内容顺序一致。"""
    try:
        v = int(n)
    except (TypeError, ValueError):
        v = 0
    return str(max(v, 0) + 1).zfill(width)


def _parse_content_text(raw: Any) -> Any:
    """从 content_text 中提取结构化结果，兼容三种存储格式：

    1. 直接 str 型纯文本（旧正文/纯字符串任务）
    2. {"_v":1,"content_text":"..."} 包装（chapter_content 通用兜底）
       —— 注意：_v + content_text 是两个键，禁止用 len(obj)==1 判断，否则正文会被置空。
    3. {"{capability_id}": {"plot":"...","summary":"..."}} 或 {"{capability_id}": {...,"events":[...]}}
    """
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    if not text:
        return ""
    if not (text.startswith("{") and text.endswith("}")):
        return text
    try:
        obj = json.loads(text)
    except Exception:
        return text
    if not isinstance(obj, dict):
        return text
    # 通用包装 2：只要含 _v 键且有 content_text，就提取纯正文（chapter_content 走此分支）
    if "_v" in obj and isinstance(obj.get("content_text"), str):
        return obj["content_text"]
    # 包装 3：顶层只有一个 capability key
    caps = [
        VAL_TASK_TYPE_GLOBAL_OUTLINE,
        VAL_TASK_TYPE_VOLUME_OUTLINE,
        VAL_TASK_TYPE_CHAPTER_OUTLINE,
        VAL_TASK_TYPE_CHAPTER_EVENTS,
        VAL_TASK_TYPE_CHAPTER_CONTENT,
    ]
    for key in caps:
        inner = obj.get(key)
        if isinstance(inner, dict):
            # chapter_content 的 capability 包装内还有一层 content_text
            if key == VAL_TASK_TYPE_CHAPTER_CONTENT and isinstance(inner.get("content_text"), str):
                return inner["content_text"]
            return inner
    # chapter_events 顶层直接是 {"events":[...]} 也兼容
    if isinstance(obj.get("events"), list):
        return obj
    return obj


def _to_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        n = int(value)
        return n if n >= 0 else None
    except (TypeError, ValueError):
        return None


def _fetch_rows(engine, session_id: str, task_type: str) -> List[Dict[str, Any]]:
    raw = engine.task_list(session_id, task_type, None, None, False)
    if isinstance(raw, dict) and isinstance(raw.get("data"), list):
        return list(raw["data"])
    if isinstance(raw, list):
        return list(raw)
    return []


def _build_work_structure(engine, session_id: str) -> Dict[str, Any]:
    """按会话聚合全部创作任务，返回规范化的多级结构字典。"""
    work_meta: Dict[str, Any] = {"session_id": session_id, "title": session_id}
    try:
        base = engine.work_get(session_id)
        if isinstance(base, dict):
            title = base.get("title")
            if isinstance(title, str) and title.strip():
                work_meta["title"] = title.strip()
            for key in ("created_at", "updated_at", "description"):
                if key in base:
                    work_meta[key] = base[key]
    except Exception:
        pass

    # 1. 全局剧情
    global_rows = _fetch_rows(engine, session_id, VAL_TASK_TYPE_GLOBAL_OUTLINE)
    global_outline: Dict[str, Any] = {"plot": "", "summary": ""}
    if global_rows:
        parsed = _parse_content_text(global_rows[0].get("content_text"))
        if isinstance(parsed, dict):
            if isinstance(parsed.get("plot"), str):
                global_outline["plot"] = parsed["plot"]
            if isinstance(parsed.get("summary"), str):
                global_outline["summary"] = parsed["summary"]
        for key in ("id", "created_at", "updated_at", "title"):
            if global_rows[0].get(key):
                global_outline[key] = global_rows[0][key]

    # 2. 卷纲
    volume_rows = _fetch_rows(engine, session_id, VAL_TASK_TYPE_VOLUME_OUTLINE)
    volumes_map: Dict[int, Dict[str, Any]] = {}
    volume_id_to_vi: Dict[str, int] = {}
    for row in volume_rows:
        vi = _to_int(row.get("volume_index")) or _to_int(row.get("sort_order"))
        if vi is None:
            continue
        parsed = _parse_content_text(row.get("content_text"))
        volume_item: Dict[str, Any] = {
            "volume_index": vi,
            "plot": "",
            "summary": "",
            "chapters": {},
        }
        for key in ("id", "title", "created_at", "updated_at"):
            if row.get(key):
                volume_item[key] = row[key]
        if isinstance(parsed, dict):
            if isinstance(parsed.get("plot"), str):
                volume_item["plot"] = parsed["plot"]
            if isinstance(parsed.get("summary"), str):
                volume_item["summary"] = parsed["summary"]
        volumes_map[vi] = volume_item
        if row.get("id"):
            volume_id_to_vi[str(row["id"])] = vi

    # 3. 章纲
    chapter_rows = _fetch_rows(engine, session_id, VAL_TASK_TYPE_CHAPTER_OUTLINE)
    chapter_outline_id_to_pos: Dict[str, Tuple[int, int]] = {}
    for row in chapter_rows:
        vi = _to_int(row.get("volume_index"))
        ci = _to_int(row.get("chapter_index")) or _to_int(row.get("sort_order"))
        if ci is None:
            continue
        if vi is None and row.get("parent_id"):
            vi = volume_id_to_vi.get(str(row["parent_id"]))
        if vi is None:
            vi = 0
        parsed = _parse_content_text(row.get("content_text"))
        vol = volumes_map.setdefault(
            vi,
            {"volume_index": vi, "plot": "", "summary": "", "chapters": {}},
        )
        chapter_item: Dict[str, Any] = {
            "volume_index": vi,
            "chapter_index": ci,
            "title": "",
            "plot": "",
            "summary": "",
            "events": [],
            "content": "",
        }
        for key in ("id", "title", "created_at", "updated_at"):
            if row.get(key):
                chapter_item[key] = row[key]
        if isinstance(parsed, dict):
            if isinstance(parsed.get("plot"), str):
                chapter_item["plot"] = parsed["plot"]
            if isinstance(parsed.get("summary"), str):
                chapter_item["summary"] = parsed["summary"]
        vol["chapters"][ci] = chapter_item
        if row.get("id"):
            chapter_outline_id_to_pos[str(row["id"])] = (vi, ci)

    # 4. 事件链
    events_rows = _fetch_rows(engine, session_id, VAL_TASK_TYPE_CHAPTER_EVENTS)
    for row in events_rows:
        vi = _to_int(row.get("volume_index"))
        ci = _to_int(row.get("chapter_index")) or _to_int(row.get("sort_order"))
        if vi is None or ci is None:
            if row.get("parent_id"):
                pos = chapter_outline_id_to_pos.get(str(row["parent_id"]))
                if pos:
                    vi, ci = pos
        if vi is None or ci is None:
            continue
        parsed = _parse_content_text(row.get("content_text"))
        events: List[str] = []
        if isinstance(parsed, list):
            events = [s for s in parsed if isinstance(s, str) and s.strip()]
        elif isinstance(parsed, dict) and isinstance(parsed.get("events"), list):
            events = [s for s in parsed["events"] if isinstance(s, str) and s.strip()]
        vol = volumes_map.setdefault(
            vi,
            {"volume_index": vi, "plot": "", "summary": "", "chapters": {}},
        )
        chapter_item = vol["chapters"].setdefault(
            ci,
            {
                "volume_index": vi,
                "chapter_index": ci,
                "title": "",
                "plot": "",
                "summary": "",
                "events": [],
                "content": "",
            },
        )
        if events:
            chapter_item["events"] = events
        if row.get("id"):
            chapter_item["events_task_id"] = row["id"]

    # 5. 正文
    content_rows = _fetch_rows(engine, session_id, VAL_TASK_TYPE_CHAPTER_CONTENT)
    for row in content_rows:
        vi = _to_int(row.get("volume_index"))
        ci = _to_int(row.get("chapter_index")) or _to_int(row.get("sort_order"))
        if vi is None or ci is None:
            if row.get("parent_id"):
                pos = chapter_outline_id_to_pos.get(str(row["parent_id"]))
                if pos:
                    vi, ci = pos
        if vi is None or ci is None:
            continue
        parsed = _parse_content_text(row.get("content_text"))
        content = parsed if isinstance(parsed, str) else ""
        vol = volumes_map.setdefault(
            vi,
            {"volume_index": vi, "plot": "", "summary": "", "chapters": {}},
        )
        chapter_item = vol["chapters"].setdefault(
            ci,
            {
                "volume_index": vi,
                "chapter_index": ci,
                "title": "",
                "plot": "",
                "summary": "",
                "events": [],
                "content": "",
            },
        )
        if isinstance(content, str) and len(content) > len(chapter_item.get("content", "")):
            chapter_item["content"] = content
        if row.get("id"):
            chapter_item["content_task_id"] = row["id"]
        if row.get("word_count"):
            chapter_item["word_count"] = row["word_count"]

    # 归一化：按索引升序转列表
    volume_list: List[Dict[str, Any]] = []
    for vi in sorted(volumes_map.keys()):
        vol = volumes_map[vi]
        chapters_dict: Dict[int, Dict[str, Any]] = vol.get("chapters") or {}
        chapter_list: List[Dict[str, Any]] = []
        for ci in sorted(chapters_dict.keys()):
            chapter_list.append(chapters_dict[ci])
        vol_out = dict(vol)
        vol_out["chapters"] = chapter_list
        volume_list.append(vol_out)

    total_chapters = sum(len(v["chapters"]) for v in volume_list)
    total_words = sum(
        int(c.get("word_count") or (len(c.get("content") or "") if isinstance(c.get("content"), str) else 0))
        for v in volume_list for c in v["chapters"]
    )

    return {
        "schema_version": 2,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "work": work_meta,
        "global_outline": global_outline,
        "volumes": volume_list,
        "stats": {
            "volume_count": len(volume_list),
            "chapter_count": total_chapters,
            "estimated_total_chars": total_words,
        },
    }


# ================ 目录树打包：分卷 / 分章独立文件 ================

def _build_global_outline_md(data: Dict[str, Any]) -> str:
    """00-全局剧情.md：仅谋篇剧情 + 摘要。"""
    title = (data.get("work") or {}).get("title") or data["work"]["session_id"]
    go = data.get("global_outline") or {}
    lines: List[str] = [f"# 《{title}》 · 全局剧情\n"]
    exported_at = data.get("exported_at")
    if exported_at:
        lines.append(f"> 导出时间：{exported_at}\n")
    if isinstance(go, dict):
        plot = str(go.get("plot") or "").rstrip()
        summary = str(go.get("summary") or "").rstrip()
        if plot:
            lines.append("## 剧情\n")
            lines.append(plot + "\n")
        if summary:
            lines.append("## 摘要\n")
            lines.append(summary + "\n")
        if not plot and not summary:
            lines.append("_暂无全局剧情，请先在「谋篇」页面保存剧情与摘要。_\n")
    return "\n".join(lines).rstrip() + "\n"


def _build_volume_outline_md(vol: Dict[str, Any], vi: int, work_title: str) -> str:
    """第XX卷_xxx/00-卷纲.md：仅卷纲剧情 + 摘要。"""
    vi_1 = int(vol.get("volume_index") or vi) + 1
    vol_title = (vol.get("title") or "").strip()
    lines: List[str] = [f"# 《{work_title}》 · 第 {vi_1} 卷 卷纲\n"]
    if vol_title:
        lines.append(f"> 卷标题：{vol_title}\n")
    chapters = vol.get("chapters") or []
    if isinstance(chapters, list) and chapters:
        lines.append(f"> 章节数：{len(chapters)}\n")
    plot = str(vol.get("plot") or "").rstrip()
    summary = str(vol.get("summary") or "").rstrip()
    if plot:
        lines.append("## 卷纲剧情\n")
        lines.append(plot + "\n")
    if summary:
        lines.append("## 卷纲摘要\n")
        lines.append(summary + "\n")
    if not plot and not summary:
        lines.append("_暂无卷纲内容。_\n")
    return "\n".join(lines).rstrip() + "\n"


def _build_chapter_full_md(ch: Dict[str, Any], vi: int, ci: int, work_title: str) -> str:
    """每章独立的整合 md：剧情 / 摘要 / 事件链 / 正文 全部打包，单文件一目了然。"""
    vi_1 = vi + 1
    ci_1 = ci + 1
    ch_title = (ch.get("title") or "").strip()
    lines: List[str] = [f"# 《{work_title}》 · 第 {vi_1} 卷 第 {ci_1} 章\n"]
    if ch_title:
        lines.append(f"> 章标题：{ch_title}\n")
    plot = str(ch.get("plot") or "").rstrip()
    summary = str(ch.get("summary") or "").rstrip()
    events = ch.get("events") if isinstance(ch.get("events"), list) else []
    content = str(ch.get("content") or "").rstrip()
    wc = 0
    if content:
        wc = len(content)
        lines.append(f"> 正文字符数：{wc}\n")
    lines.append("")

    if plot:
        lines.append("## 章纲 · 剧情\n")
        lines.append(plot + "\n")
    if summary:
        lines.append("## 章纲 · 摘要\n")
        lines.append(summary + "\n")
    if events:
        lines.append(f"## 推演 · 事件链（共 {len(events)} 条）\n")
        for i, ev in enumerate(events, 1):
            lines.append(f"{i}. {ev}")
        lines.append("")
    if content:
        lines.append("## 成文 · 正文\n")
        lines.append(content + "\n")
    if not plot and not summary and not events and not content:
        lines.append("_本章暂无内容。_\n")
    return "\n".join(lines).rstrip() + "\n"


def _build_chapter_content_txt(ch: Dict[str, Any]) -> str:
    """每章独立纯正文 txt：仅正文文本，无元信息；方便用户分章复制。"""
    content = str(ch.get("content") or "").rstrip()
    if not content:
        return "_暂无正文内容_\n"
    return content + "\n"


def _build_full_novel_txt(data: Dict[str, Any]) -> str:
    """全书正文合集：面向发布/发书，仅卷标题 + 章标题 + 正文，无创作元信息。"""
    title = (data.get("work") or {}).get("title") or data["work"]["session_id"]
    lines: List[str] = [f"《{title}》", ""]
    volumes = data.get("volumes") or []
    for vol in volumes:
        vi = int(vol.get("volume_index") or 0)
        vol_title_raw = (vol.get("title") or "").strip()
        if vol_title_raw:
            lines.append(f"第 {vi + 1} 卷 · {vol_title_raw}")
        else:
            lines.append(f"第 {vi + 1} 卷")
        chapters = vol.get("chapters") or []
        for ch in chapters:
            ci = int(ch.get("chapter_index") or 0)
            ch_title_raw = (ch.get("title") or "").strip()
            if ch_title_raw:
                lines.append(f"\n第 {ci + 1} 章 · {ch_title_raw}")
            else:
                lines.append(f"\n第 {ci + 1} 章")
            content = str(ch.get("content") or "").rstrip()
            if content:
                lines.append("")
                lines.append(content)
    return "\n".join(lines).rstrip() + "\n"


def export_work_to_zip(engine, session_id: str) -> Tuple[bytes, str]:
    """将完整作品按「卷-章」目录树打包为 zip，返回 (zip_bytes, 推荐文件名(无 .zip 后缀))。

    内部结构（目录 + 文件 分层，便于直接打开使用）：
        [root_dir]
        ├── 00-全局剧情.md
        ├── 第01卷[_卷名]/
        │   ├── 00-卷纲.md
        │   ├── 01-第1章[_章名].md          剧情+摘要+事件链+正文 整合
        │   ├── 01-第1章[_章名]-正文.txt    仅本章纯正文
        │   └── ...
        ├── 第02卷[_卷名]/
        │   └── ...
        ├── 全书正文.txt
        └── work.json
    """
    data = _build_work_structure(engine, session_id)
    work_title = (data.get("work") or {}).get("title") or session_id
    safe_title = _safe_filename(work_title, "作品")
    timestamp = datetime.now().strftime("%Y%m%d%H%M")
    zip_name_no_ext = f"《{safe_title}》-完整创作数据-{timestamp}"

    # zip 根目录：统一套一层文件夹，解压后不会文件乱飞
    root = f"《{safe_title}》-完整创作数据/"

    volumes = data.get("volumes") or []
    vol_width = max(2, len(str(max(1, len(volumes)))))
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as zf:
        # —— 1. 根级：work.json ——
        json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        zf.writestr(root + "work.json", json_bytes)

        # —— 2. 根级：00-全局剧情.md ——
        global_md = _build_global_outline_md(data).encode("utf-8")
        zf.writestr(root + "00-全局剧情.md", global_md)

        # —— 3. 分卷目录 ——（仅用序号，不拼接 task title，避免「卷纲剧情设计」等冗余后缀）
        for idx, vol in enumerate(volumes):
            vi = int(vol.get("volume_index") or idx)
            vol_dir = f"{root}第{_index_pad(vi, vol_width)}卷/"

            # 卷目录下 00-卷纲.md
            vol_md = _build_volume_outline_md(vol, vi, work_title).encode("utf-8")
            zf.writestr(vol_dir + "00-卷纲.md", vol_md)

            chapters = vol.get("chapters") or []
            ch_width = max(2, len(str(max(1, len(chapters)))))
            for ch_idx, ch in enumerate(chapters):
                ci = int(ch.get("chapter_index") or ch_idx)
                # 仅用序号，不拼接 task title，避免「章纲剧情设计（第 1 卷，第 1 章）」等冗余后缀
                base_prefix = f"{_index_pad(ci, ch_width)}-第{ci + 1}章"

                # 章整合 md（剧情+摘要+事件链+正文）
                ch_full_md = _build_chapter_full_md(ch, vi, ci, work_title).encode("utf-8")
                zf.writestr(f"{vol_dir}{base_prefix}.md", ch_full_md)

                # 章纯正文 txt（仅正文，方便复制/独立使用）
                ch_txt = _build_chapter_content_txt(ch).encode("utf-8")
                zf.writestr(f"{vol_dir}{base_prefix}-正文.txt", ch_txt)

        # —— 4. 根级：全书正文.txt ——
        full_txt = _build_full_novel_txt(data).encode("utf-8")
        zf.writestr(root + "全书正文.txt", full_txt)

    return buffer.getvalue(), zip_name_no_ext
