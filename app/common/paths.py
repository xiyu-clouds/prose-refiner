"""
🌊 基础设施常量池 (Infrastructure Constants)
管理：项目根目录、目录名、文件名、绝对路径对象、宿主机挂载点。

⚠️ 所有 `DIR_*`、`FILE_*` 常量仅在本模块内部用于构造 PATH，外部请勿直接引用。
外部请统一使用 `PA.PATH_*` 或 `PA.MOUNT_*` 路径常量。
"""
from pathlib import Path
from typing import Final

from app.common import keys as ke

# ======================================================================
# 1. 根目录 (Root Directories)
# ======================================================================
ROOT_DIR: Final[Path] = Path(__file__).parent.parent.parent.resolve()

# ======================================================================
# 2. 目录名 (Directory Names — 仅内部用，构造 PATH)
# ======================================================================
_DIR_DATA = "data"
_DIR_APP = "app"
_DIR_STATIC = "static"
_DIR_TEMPLATES = "templates"
_DIR_OTHER = "other"
_DIR_COMPONENTS = "components"

# ======================================================================
# 3. 文件名 (File Names — 仅内部用，构造 PATH)
# ======================================================================
_FILE_PROSE_REFINER_DB = "prose_refiner.db"
_FILE_INDEX_HTML = "index.html"
_FILE_STOPWORDS_TXT = "stopwords.txt"
_FILE_JIEBA_USERDICT_TXT = "jieba_userdict.txt"

# ======================================================================
# 4. 项目内的绝对路径 (App-Internal Paths)
# ======================================================================
_PATH_DIR_APP = ROOT_DIR / _DIR_APP

# 前端入口（index.html）
PATH_FILE_INDEX_HTML: Final[Path] = _PATH_DIR_APP / _DIR_TEMPLATES / _FILE_INDEX_HTML

# jieba 停用词
PATH_FILE_STOPWORDS_TXT: Final[Path] = _PATH_DIR_APP / _DIR_STATIC / _DIR_OTHER / _FILE_STOPWORDS_TXT

# jieba 自定义词典（基于 semantic_vocabulary.name 动态生成，add_word 权重 5 / 词性 n）
PATH_FILE_JIEBA_USERDICT_TXT: Final[Path] = _PATH_DIR_APP / _DIR_STATIC / _DIR_OTHER / _FILE_JIEBA_USERDICT_TXT

# ======================================================================
# 5. 宿主机挂载点 (Container Mount Paths)
# ======================================================================
# 容器内数据根目录，开发环境自动回退到项目根目录下的 data 目录
_container_data_root = Path(f"/{_DIR_DATA}")
DATA_ROOT: Final[Path] = _container_data_root if _container_data_root.exists() else ROOT_DIR / _DIR_DATA

# 日志
MOUNT_LOGS_DIR: Final[Path] = DATA_ROOT / ke.KEY_LOGS
MOUNT_LOGS_FALLBACK_DIR: Final[Path] = DATA_ROOT / ke.KEY_LOGS_FALLBACK

# SQLite
MOUNT_SQLITE_DIR: Final[Path] = DATA_ROOT / ke.KEY_SQLITE

# 本地模型缓存
MOUNT_LOCAL_MODEL_CACHE_DIR: Final[Path] = DATA_ROOT / ke.KEY_MODEL

# 媒体资源
MOUNT_IMAGE_DIR: Final[Path] = DATA_ROOT / ke.KEY_IMAGE
MOUNT_AUDIO_DIR: Final[Path] = DATA_ROOT / ke.KEY_AUDIO
MOUNT_VIDEO_DIR: Final[Path] = DATA_ROOT / ke.KEY_VIDEO
MOUNT_LYRIC_DIR: Final[Path] = DATA_ROOT / ke.KEY_LYRIC

# ======================================================================
# 6. 对外暴露的文件名常量 (config.py 引用，兼容旧写法)
# ======================================================================
FILE_PROSE_REFINER_DB: Final[str] = _FILE_PROSE_REFINER_DB
