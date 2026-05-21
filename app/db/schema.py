import sqlite3
from app.config.config import config
from app.db.memory_db import MemoryPhaseDB
from app.utils.logger import LoggerManager as logger

CHINESE_NAME = "数据库模式初始化"


def init_database_schema():
    """
    在服务启动时调用，确保所有表存在。
    主表存放任务基础元数据与文件路径索引，子表存放完整结构化数据。
    """
    db = MemoryPhaseDB.get_instance(config.DB_PATH)
    conn = sqlite3.connect(str(db.db_path))
    cursor = conn.cursor()

    try:
        # 启用外键支持（SQLite 默认关闭）
        cursor.execute("PRAGMA foreign_keys = ON;")

        # 创建主表 + 5 子表，并单独创建索引（SQLite 不支持内联 INDEX）
        create_tables_sql = """
        CREATE TABLE IF NOT EXISTS optimization_tasks (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived', 'deleted')),
            path_text TEXT,
            path_dye_vat TEXT,             
            path_metacognition TEXT,
            path_report TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_optimization_tasks_created ON optimization_tasks (created_at);

        CREATE TABLE IF NOT EXISTS text_processing_data (
            id TEXT PRIMARY KEY REFERENCES optimization_tasks(id) ON DELETE CASCADE,
            structured_data JSON NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_text_results_created ON text_processing_data (created_at);
        
        CREATE TABLE IF NOT EXISTS metacognition_data (
            id TEXT PRIMARY KEY REFERENCES optimization_tasks(id) ON DELETE CASCADE,
            structured_data JSON NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_metacognition_reports_created ON metacognition_data (created_at);
        """

        cursor.executescript(create_tables_sql)
        conn.commit()
        logger.info("✅ 数据库表结构已初始化", module_name=CHINESE_NAME)

    except Exception as e:
        logger.error(f"❌ 初始化数据库失败: {e}", module_name=CHINESE_NAME)
        raise
    finally:
        conn.close()
