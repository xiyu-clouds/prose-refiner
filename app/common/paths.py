"""
🌊 基础设施常量池 (Infrastructure Constants)
专注管理：根目录、目录名、文件名、绝对路径对象。
"""
from pathlib import Path
from typing import Final

# ======================================================================
# 🏗️ 一、根目录定义 (Root Directories)
# ======================================================================
# 自动定位项目根目录
ROOT_DIR: Final[Path] = Path(__file__).parent.parent.parent.resolve()

# ======================================================================
# 📂 二、目录名常量 (Directory Names)
# ======================================================================
DIR_DATA = "data"
DIR_APP = "app"
DIR_TEST = "test"

DIR_COMMON = "common"
DIR_CONFIG = "config"
DIR_CORE = "core"
DIR_VALIDATORS = "validators"
DIR_STEPS = "steps"
DIR_GRAPH = "meta"
DIR_SCHEDULE = "schedule"
DIR_SERVICES = "services"
DIR_DB = "db"
DIR_MODELS = "models"
DIR_NOTIFY = "notify"
DIR_UTILS = "utils"
DIR_STATIC = "static"
DIR_TEMPLATES = "templates"
DIR_TASKS = "tasks"

DIR_CACHE = "cache"
DIR_COLLECTOR = "collector"
DIR_ENGINE = "engine"
DIR_REGISTRY = "registry"
DIR_TRACER = "tracer"
DIR_CSS = "css"
DIR_JS = "js"
DIR_IMAGES = "images"
DIR_LYRICS = "lyrics"
DIR_MUSIC = "music"
DIR_OTHER = "other"
DIR_WEBFONTS = "webfonts"
DIR_COMPONENTS = "components"

# ======================================================================
# 📂 三、文件名常量 (File Names)
# ======================================================================
FILE_THE_WAY_JSON = "the_way.json"
FILE_PLUGINS_JSON = "plugins.json"
FILE_PROMPTS_JSON = "prompts.json"
FILE_SETTINGS_JSON = "settings.json"
FILE_PUNCTUATION_RULES_JSON = "punctuation_rules.json"
FILE_SPELL_RULES_JSON = "spell_rules.json"
FILE_ANALYSIS_RULES_JSON = "analysis_rules.json"

FILE_PROSE_REFINER_DB = "prose_refiner.db"

FILE_INDEX_HTML = "index.html"
FILE_REPORT_TEMPLATE_HTML = "report_template.html"

FILE_STOPWORDS_TXT = "stopwords.txt"

# ======================================================================
# 📂 四、路径常量 (Path Names)
# ======================================================================
# 基础
PATH_DIR_APP = ROOT_DIR / DIR_APP
# 配置文件默认都在项目内的 config 目录下
DEFAULT_CONFIG_DIR = PATH_DIR_APP / DIR_CONFIG

# 模板文件
PATH_FILE_INDEX_HTML = PATH_DIR_APP / DIR_TEMPLATES / FILE_INDEX_HTML
PATH_FILE_REPORT_TEMPLATE_HTML = PATH_DIR_APP / DIR_STATIC / DIR_COMPONENTS / FILE_REPORT_TEMPLATE_HTML
# 停用词文件
PATH_FILE_STOPWORDS_TXT = PATH_DIR_APP / DIR_STATIC / DIR_OTHER / FILE_STOPWORDS_TXT

# ======================================================================
# 📂 五、挂载点路径 (Mount Paths - 宿主机挂载点)
# ======================================================================
# 宿主机挂载的数据根目录
DATA_ROOT = Path(f"/{DIR_DATA}")
# 挂载点下的配置目录
MOUNT_CONFIG_DIR = DATA_ROOT / DIR_CONFIG

MOUNT_PATH_FILE_SETTINGS_JSON = MOUNT_CONFIG_DIR / FILE_SETTINGS_JSON
MOUNT_PATH_FILE_THE_WAY_JSON = MOUNT_CONFIG_DIR / FILE_THE_WAY_JSON
MOUNT_PATH_FILE_PLUGINS_JSON = MOUNT_CONFIG_DIR / FILE_PLUGINS_JSON
MOUNT_PATH_FILE_PROMPTS_JSON = MOUNT_CONFIG_DIR / FILE_PROMPTS_JSON
MOUNT_PATH_FILE_PUNCTUATION_RULES_JSON = MOUNT_CONFIG_DIR / FILE_PUNCTUATION_RULES_JSON
MOUNT_PATH_FILE_SPELL_RULES_JSON = MOUNT_CONFIG_DIR / FILE_SPELL_RULES_JSON
MOUNT_PATH_FILE_ANALYSIS_RULES_JSON = MOUNT_CONFIG_DIR / FILE_ANALYSIS_RULES_JSON
