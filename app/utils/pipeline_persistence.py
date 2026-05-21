import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from app.config.config import config
from app.common import keys as ke
from app.db.memory_db import MemoryPhaseDB
from app.utils.file_util import FileUtil
from app.utils.json_serializer import safe_json_dumps
from app.utils.logger import LoggerManager as logger


CHINESE_NAME = "持久化工具"

# 模块级单例，避免重复创建
_file_util = FileUtil()


def get_db() -> MemoryPhaseDB:
    """获取数据库单例，统一入口便于后续维护"""
    return MemoryPhaseDB.get_instance(config.DB_PATH)


def _extract_audit_data(collector) -> tuple:
    """从收集器中提取审计数据，调用方无需关心内部结构"""
    errors = getattr(collector, 'errors', None)
    prompts = getattr(collector, 'prompts', None)
    responses = getattr(collector, 'responses', None)
    return errors, prompts, responses


async def _save_business_snapshot(
        task_id: str,
        data: Dict[str, Any],
        subdir: Path,
        path_key: str,
) -> Path:
    """保存业务快照 JSON 文件到指定目录，并更新主表路径"""
    db = get_db()

    base_dir = _file_util.get_todays_subdir(subdir)
    filepath = base_dir / f"{task_id}.json"
    base_dir.mkdir(parents=True, exist_ok=True)

    json_str = safe_json_dumps(data, indent=2)
    filepath.write_text(json_str, encoding=ke.KEY_UTF_8)

    await db.update_file_paths(task_id, {path_key: str(filepath)})
    logger.info(f"📦 [{task_id}] 业务快照已保存 | 路径: {filepath}", module_name=CHINESE_NAME)
    return filepath


async def _get_or_create_dye_vat_path(task_id: str) -> Path:
    """获取大染缸文件路径，优先从数据库读取，否则创建新路径"""
    db = get_db()

    stored = await db.get_file_path(task_id, ke.KEY_PATH_DYE_VAT)
    if stored:
        return Path(stored)

    dye_dir = _file_util.get_todays_subdir(config.DYE_VAT_DIR)
    dye_path = dye_dir / f"{task_id}.json"
    dye_dir.mkdir(parents=True, exist_ok=True)

    await db.update_file_paths(task_id, {ke.KEY_PATH_DYE_VAT: str(dye_path)})
    return dye_path


async def append_dye_vat(
        task_id: str,
        phase: str,
        vendor: str,
        model: str,
        errors: Optional[list] = None,
        prompts: Optional[list] = None,
        responses: Optional[list] = None,
) -> None:
    """追加审计数据到大染缸 JSON 文件，兼容首次写入和后续追加"""
    has_data = bool(errors) or bool(prompts) or bool(responses)
    if not has_data:
        return

    dye_path = await _get_or_create_dye_vat_path(task_id)

    existing_data: Dict[str, Any] = {}
    if dye_path.exists():
        try:
            raw = dye_path.read_text(encoding=ke.KEY_UTF_8)
            existing_data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            logger.warning(f"大染缸文件损坏，将重建 | 任务: {task_id}", module_name=CHINESE_NAME)

    # 防御性更新 ID：只在缺失或不同时写入
    if ke.KEY_ID not in existing_data or existing_data[ke.KEY_ID] != task_id:
        existing_data[ke.KEY_ID] = task_id

    audit_entry = {
        ke.KEY_VENDOR: vendor,
        ke.KEY_MODEL: model,
        ke.KEY_TIMESTAMP: datetime.now().isoformat(),
    }
    if errors:
        audit_entry[ke.KEY_ERRORS] = errors
    if prompts:
        audit_entry[ke.KEY_PROMPTS] = prompts
    if responses:
        audit_entry[ke.KEY_RESPONSES] = responses

    existing_data[phase] = audit_entry

    dye_path.write_text(
        safe_json_dumps(existing_data, indent=2),
        encoding=ke.KEY_UTF_8,
    )
    logger.info(f"💉 [{task_id}] 大染缸已更新 | 阶段: {phase}", module_name=CHINESE_NAME)


async def _persist_pipeline_result(
        task_id: str,
        data: Dict[str, Any],
        vendor: str,
        model: str,
        collector,
        config_dir: Path,
        path_key: str,
        phase: str,
        table_name: str,
) -> None:
    """
    通用三轨持久化：
    1. SQLite 子表（table_name）
    2. 业务快照 JSON（config_dir / path_key）
    3. 大染缸审计（phase）
    """
    db = get_db()

    # 轨道1：SQLite
    await db.save_phase(
        structured_data=data,
        table_name=table_name,
        write_to_main_table=not await db.has_record(task_id, table_name),
    )

    # 轨道2：业务快照 JSON
    await _save_business_snapshot(
        task_id=task_id,
        data=data,
        subdir=config_dir,
        path_key=path_key,
    )

    # 轨道3：大染缸
    errors, prompts, responses = _extract_audit_data(collector)
    await append_dye_vat(
        task_id=task_id,
        phase=phase,
        vendor=vendor,
        model=model,
        errors=errors,
        prompts=prompts,
        responses=responses,
    )

    logger.info(f"📦 [{task_id}] 阶段 [{phase}] 持久化全部完成", module_name=CHINESE_NAME)


async def save_text_processing_result(
        task_id: str,
        data: Dict[str, Any],
        vendor: str,
        model: str,
        collector,
) -> None:
    """
    文本处理阶段持久化入口
    """
    await _persist_pipeline_result(
        task_id=task_id,
        data=data,
        vendor=vendor,
        model=model,
        collector=collector,
        config_dir=config.TEXT_DIR,
        path_key=ke.KEY_PATH_TEXT,
        phase=ke.KEY_TEXT_PROCESSING,
        table_name=ke.KEY_TEXT_PROCESSING_DATA,
    )


async def save_metacognition_result(
        task_id: str,
        data: Dict[str, Any],
        vendor: str,
        model: str,
        collector,
) -> None:
    """
    元认知阶段持久化入口
    """
    await _persist_pipeline_result(
        task_id=task_id,
        data=data,
        vendor=vendor,
        model=model,
        collector=collector,
        config_dir=config.METACOGNITION_DIR,
        path_key=ke.KEY_PATH_METACOGNITION,
        phase=ke.KEY_METACOGNITION,
        table_name=ke.KEY_METACOGNITION_DATA,
    )
