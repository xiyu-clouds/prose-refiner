import json
import time
from pathlib import Path
from typing import Dict, Optional, Any
import aiosqlite
from app.common import values as va
from app.common import keys as ke
from app.utils.logger import LoggerManager as logger


CHINESE_NAME = "SQL中枢"


class MemoryPhaseDB:
    _instance: Optional["MemoryPhaseDB"] = None
    _db_path: Optional[Path] = None

    def __init__(self, db_path: Path):
        if MemoryPhaseDB._instance is not None:
            raise RuntimeError("请使用 MemoryPhaseDB.get_instance() 获取单例")
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_instance(cls, db_path: Path) -> "MemoryPhaseDB":
        if cls._instance is None:
            cls._instance = MemoryPhaseDB(db_path)
            cls._db_path = db_path
        elif cls._db_path != db_path:
            raise ValueError(f"单例已初始化为 {cls._db_path}，不能切换到 {db_path}")
        return cls._instance

    # ==============================================================================
    # 内部工具：子表名校验
    # ==============================================================================
    @staticmethod
    def _is_valid_table_name(table_name: str) -> bool:
        """校验子表名是否合法，返回布尔值而非异常，守卫式调用更自然"""
        return table_name in va.VAL_VALID_SUB_TABLES

    # ==============================================================================
    # 通用查询：从子表获取结构化数据
    # ==============================================================================
    async def get_structured_data(self, phase_id: str, table_name: str) -> Optional[Dict[str, Any]]:
        """
        从指定子表查询完整结构化数据。

        Args:
            phase_id: 任务 ID
            table_name: 子表名
        """
        if not self._is_valid_table_name(table_name):
            logger.error(f"非法子表名: {table_name}", module_name=CHINESE_NAME)
            return None

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT structured_data FROM {table_name} WHERE id = ?",
                (phase_id,)
            )
            row = await cursor.fetchone()
            return json.loads(row[ke.KEY_STRUCTURED_DATA]) if row else None

    async def get_text_processing_data(self, phase_id: str) -> Optional[Dict[str, Any]]:
        """从文本处理子表查询结构化数据"""
        return await self.get_structured_data(phase_id, ke.KEY_TEXT_PROCESSING_DATA)

    async def get_metacognition_data(self, phase_id: str) -> Optional[Dict[str, Any]]:
        """从元认知子表查询结构化数据"""
        return await self.get_structured_data(phase_id, ke.KEY_METACOGNITION_DATA)

    # ==============================================================================
    # 去重检查
    # ==============================================================================
    async def has_record(self, phase_id: str, table_name: str) -> bool:
        """检查指定子表是否已存在记录"""
        if not self._is_valid_table_name(table_name):
            return False

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"SELECT id FROM {table_name} WHERE id = ?",
                (phase_id,)
            )
            row = await cursor.fetchone()
            return row is not None

    async def has_text_processing_record(self, phase_id: str) -> bool:
        return await self.has_record(phase_id, ke.KEY_TEXT_PROCESSING_DATA)

    async def has_metacognition_record(self, phase_id: str) -> bool:
        return await self.has_record(phase_id, ke.KEY_METACOGNITION_DATA)

    async def _main_table_has_record(self, phase_id: str) -> bool:
        """检查主表 optimization_tasks 是否已有该任务的记录"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id FROM optimization_tasks WHERE id = ?",
                (phase_id,)
            )
            row = await cursor.fetchone()
            return row is not None

    # ==============================================================================
    # 保存：原子性写入（主表写入由参数控制）
    # ==============================================================================
    async def save_phase(
            self,
            structured_data: Dict[str, Any],
            *,
            table_name: str,
            write_to_main_table: bool = False,
            file_paths: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        通用保存方法。

        Args:
            structured_data: 完整结构化数据，必须包含 "id" 字段
            table_name: 目标子表名
            write_to_main_table: 是否同步写入主表（同一任务首次保存时设为 True）
            file_paths: 需要同步更新的文件路径字典（仅在 write_to_main_table 为 True 时生效）
        """
        if not self._is_valid_table_name(table_name):
            raise ValueError(f"非法子表名: {table_name}，必须是 {va.VAL_VALID_SUB_TABLES}")

        phase_id = structured_data.get(ke.KEY_ID)
        if not phase_id:
            raise ValueError(f"{ke.KEY_STRUCTURED_DATA} 必须包含 '{ke.KEY_ID}' 字段")

        # 校验并过滤路径键
        safe_paths = {}
        if file_paths:
            for k, v in file_paths.items():
                if k in va.VAL_VALID_PATH_KEYS:
                    safe_paths[k] = v
                else:
                    logger.warning(f"忽略非法路径键: {k}", module_name=CHINESE_NAME)

        now = int(time.time())
        safe_data = json.dumps(structured_data, ensure_ascii=False, separators=(',', ':'))

        async with aiosqlite.connect(self.db_path) as db:
            # 写入主表（仅在 write_to_main_table 为 True 时）
            if write_to_main_table:
                path_cols = list(safe_paths.keys())
                path_vals = list(safe_paths.values())

                base_cols = [ke.KEY_ID, ke.KEY_CREATE_AT, ke.KEY_UPDATED_AT]
                base_vals = [phase_id, now, now]

                all_cols = base_cols + path_cols
                all_vals = base_vals + path_vals

                update_parts = [f"{ke.KEY_UPDATED_AT} = {ke.KEY_EXCLUDED}.{ke.KEY_UPDATED_AT}"]
                for col in path_cols:
                    update_parts.append(f"{col} = {ke.KEY_EXCLUDED}.{col}")

                sql = f"""
                    INSERT INTO optimization_tasks ({', '.join(all_cols)})
                    VALUES ({', '.join(['?'] * len(all_vals))})
                    ON CONFLICT(id) DO UPDATE SET
                        {', '.join(update_parts)}
                """
                await db.execute(sql, all_vals)

            # 写入子表（每次保存都执行）
            await db.execute(
                f"""INSERT OR REPLACE INTO {table_name} ({ke.KEY_ID}, {ke.KEY_STRUCTURED_DATA}, {ke.KEY_CREATE_AT}, {ke.KEY_UPDATED_AT})
                    VALUES (?, ?, ?, ?)""",
                (phase_id, safe_data, now, now)
            )

            await db.commit()

        logger.debug(f"已保存 {phase_id} 到 {table_name}", module_name=CHINESE_NAME)
        return phase_id

    async def save_text_processing_data(
            self, structured_data: Dict[str, Any], file_paths: Optional[Dict[str, str]] = None
    ) -> str:
        """
        保存文本处理数据。
        首次调用时写入主表 + 子表；后续调用只更新子表。
        """
        already_exists = await self.has_text_processing_record(structured_data[ke.KEY_ID])
        return await self.save_phase(
            structured_data,
            table_name=ke.KEY_TEXT_PROCESSING_DATA,
            write_to_main_table=not already_exists,
            file_paths=file_paths,
        )

    async def save_metacognition_data(
            self, structured_data: Dict[str, Any], file_paths: Optional[Dict[str, str]] = None
    ) -> str:
        """
        保存元认知数据。
        首次调用时写入主表 + 子表；后续调用只更新子表。
        """
        phase_id = structured_data[ke.KEY_ID]
        main_table_exists = await self._main_table_has_record(phase_id)
        return await self.save_phase(
            structured_data,
            table_name=ke.KEY_METACOGNITION_DATA,
            write_to_main_table=not main_table_exists,
            file_paths=file_paths,
        )

    # ==============================================================================
    # 文件路径管理
    # ==============================================================================
    async def update_file_paths(self, phase_id: str, path_updates: Dict[str, str]) -> bool:
        """批量更新任务的文件路径"""
        safe_updates = {}
        for k, v in path_updates.items():
            if k in va.VAL_VALID_PATH_KEYS:
                safe_updates[k] = v
            else:
                logger.warning(f"非法的路径键名被忽略: {k}", module_name=CHINESE_NAME)

        if not safe_updates:
            return False

        async with aiosqlite.connect(self.db_path) as db:
            set_clauses = [f"{key} = ?" for key in safe_updates.keys()]
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            values = list(safe_updates.values()) + [phase_id]

            sql = f"""
                UPDATE optimization_tasks 
                SET {', '.join(set_clauses)} 
                WHERE id = ?
            """
            cursor = await db.execute(sql, values)
            await db.commit()
            return cursor.rowcount > 0

    async def get_file_path(self, phase_id: str, path_key: str) -> Optional[str]:
        """获取指定文件路径"""
        if path_key not in va.VAL_VALID_PATH_KEYS:
            logger.error(f"非法的路径键名: {path_key}", module_name=CHINESE_NAME)
            return None

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT {path_key} FROM optimization_tasks WHERE id = ?",
                (phase_id,)
            )
            row = await cursor.fetchone()
            return row[path_key] if row else None

    async def get_all_file_paths(self, phase_id: str) -> Dict[str, Optional[str]]:
        """一次性获取所有四个文件路径"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""SELECT {ke.KEY_PATH_TEXT}, {ke.KEY_PATH_DYE_VAT}, 
                           {ke.KEY_PATH_METACOGNITION}, {ke.KEY_PATH_REPORT} 
                    FROM optimization_tasks WHERE id = ?""",
                (phase_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return {}
            return {
                ke.KEY_PATH_TEXT: row[ke.KEY_PATH_TEXT],
                ke.KEY_PATH_DYE_VAT: row[ke.KEY_PATH_DYE_VAT],
                ke.KEY_PATH_METACOGNITION: row[ke.KEY_PATH_METACOGNITION],
                ke.KEY_PATH_REPORT: row[ke.KEY_PATH_REPORT],
            }

    # ==============================================================================
    # 组装数据
    # ==============================================================================
    @staticmethod
    async def fetch_level_0_content(full_data: Dict[str, Any]) -> str:
        """组装层级 0 内容：最终选定全文"""
        text_snapshots = full_data.get(ke.KEY_TEXT_SNAPSHOTS, [])
        if isinstance(text_snapshots, list):
            for snapshot in reversed(text_snapshots):
                if snapshot.get(ke.KEY_STAGE) == ke.KEY_FULL_REPAIRED:
                    return snapshot.get(ke.KEY_TEXT, "")
        return ""

    async def fetch_level_1_content(self, full_data: Dict[str, Any]) -> str:
        """组装层级 1 内容：全文级诊断聚合摘要"""
        tasks = (
            full_data.get(ke.KEY_CONTEXT, {}).get(ke.KEY_FULL_TEXT, {}).get(ke.KEY_FIX_INSTRUCTION, {}).get(ke.KEY_TASKS, [])
        )

        p0 = [t for t in tasks if t.get(ke.KEY_PRIORITY) == ke.KEY_P0]
        p1 = [t for t in tasks if t.get(ke.KEY_PRIORITY) == ke.KEY_P1]
        p2 = [t for t in tasks if t.get(ke.KEY_PRIORITY) == ke.KEY_P2]

        if not p0 and not p1 and not p2:
            return ""

        parts = ["### 全文诊断聚合摘要", self._format_issue_list("P0 级问题", p0), self._format_issue_list("P1 级问题", p1),
                 self._format_issue_list("P2 级优化项", p2)]

        return "\n".join(filter(None, parts))

    async def fetch_level_2_content(self, full_data: Dict[str, Any]) -> str:
        """组装层级 2 内容：段落级诊断详情"""
        paragraphs_data = (
            full_data.get(ke.KEY_CONTEXT, {}).get(ke.KEY_PARAGRAPHS, {})
        )

        if not paragraphs_data:
            return ""

        # 收集所有段落的问题
        all_p0 = []
        all_p1 = []
        all_p2 = []

        for idx, para_data in sorted(paragraphs_data.items()):
            if not isinstance(para_data, dict):
                continue

            tasks = (
                para_data.get(ke.KEY_FIX_INSTRUCTION, {}).get(ke.KEY_TASKS, [])
            )
            if not tasks:
                continue

            for task in tasks:
                priority = task.get(ke.KEY_PRIORITY, "")
                if priority == ke.KEY_P0:
                    all_p0.append(task)
                elif priority == ke.KEY_P1:
                    all_p1.append(task)
                elif priority == ke.KEY_P2:
                    all_p2.append(task)

        if not all_p0 and not all_p1 and not all_p2:
            return ""

        parts = ["### 段落级诊断详情", self._format_issue_list("P0 级问题", all_p0), self._format_issue_list("P1 级问题", all_p1),
                 self._format_issue_list("P2 级优化项", all_p2)]

        return "\n".join(filter(None, parts))

    @staticmethod
    def _format_issue_list(level_label: str, issues: list) -> str:
        """格式化问题列表，所有级别统一拼接逻辑"""
        if not issues:
            return ""
        lines = [f"\n**{level_label}（{len(issues)} 项）**："]
        for item in issues:
            lines.append(f"- [{item.get(ke.KEY_CATEGORY, '')}] {item.get(ke.KEY_TARGET_ISSUE, '')}")
            if item.get(ke.KEY_SUGGESTED_ACTION):
                lines.append(f"  建议: {item[ke.KEY_SUGGESTED_ACTION]}")
        return "\n".join(lines)
