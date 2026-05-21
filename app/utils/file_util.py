import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Set, List, Union, Tuple, Dict, Any
import glob
import json
import pandas as pd
import chardet
from app.utils.logger import LoggerManager as logger


class FileUtil:
    """
    文件操作工具类（单例模式）
    提供文件读写、编码检测、目录操作、JSON 处理、停用词加载等常用功能
    """

    CHINESE_NAME = "FileUtil"
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            logger.info("📁 FileUtil 初始化完成（单例模式）")
            self._initialized = True

    @staticmethod
    def to_posix_str(path: Any) -> str:
        """
        将路径对象或字符串规范化为 POSIX 风格的正斜杠字符串。
        适用于存储到数据库、写入配置文件或跨平台日志记录。
        """
        if isinstance(path, Path):
            return path.as_posix()
        return str(path).replace(os.sep, '/')

    # ===================== 文件读写相关 =====================
    def read_file(self, file_path: str, auto_decode: bool = False) -> str:
        """读取文件内容，智能处理编码"""
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read()

            if not raw_data:
                return ""

            # === 策略：先尝试 UTF-8（最常见且安全）===
            try:
                # 先试严格模式（不忽略错误）
                content = raw_data.decode('utf-8')
                logger.info(f"✅ UTF-8 解码成功: {file_path}", module_name=self.CHINESE_NAME)
                return content
            except UnicodeDecodeError:
                pass  # UTF-8 失败，继续尝试其他编码

            # === 如果启用了 auto_decode，再做编码探测 ===
            if auto_decode:
                # 使用更可靠的 charset-normalizer（如果已安装）
                try:
                    from charset_normalizer import from_bytes
                    result = from_bytes(raw_data).best()
                    if result:
                        content = str(result)
                        detected_encoding = result.encoding
                        logger.info(f"🔍 charset-normalizer 检测: {file_path} -> {detected_encoding}", module_name=self.CHINESE_NAME)
                        return content
                except ImportError:
                    # 回退到 chardet
                    pass

                # 使用 chardet（兼容性兜底）
                result = chardet.detect(raw_data)
                detected_encoding = result.get('encoding') or 'utf-8'
                confidence = result.get('confidence', 0)

                # 如果置信度太低，优先用 latin1（不会出错）
                if confidence < 0.7:
                    detected_encoding = 'latin1'

                try:
                    content = raw_data.decode(detected_encoding, errors='replace')
                    logger.info(f"🔍 chardet 检测 (conf={confidence:.2f}): {file_path} -> {detected_encoding}", module_name=self.CHINESE_NAME)
                    return content
                except Exception as e:
                    logger.warning(f"⚠️ 编码 {detected_encoding} 解码失败，回退到 latin1: {e}", module_name=self.CHINESE_NAME)

            # === 最终 fallback：latin1（每个字节都能映射，永不抛错）===
            content = raw_data.decode('latin1', errors='replace')
            logger.info(f"🛡️ 最终 fallback (latin1): {file_path}", module_name=self.CHINESE_NAME)
            return content

        except Exception as e:
            logger.error(f"❌ 读取文件失败: {file_path} - {e}", module_name=self.CHINESE_NAME, exc_info=True)
            return ""

    def file_encoding(self, file_path: str) -> str:
        """检测文件编码"""
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read()
            result = chardet.detect(raw_data)
            encoding = result['encoding']
            logger.debug(f"📐 检测到文件编码: {file_path} -> {encoding}", module_name=self.CHINESE_NAME)
            return encoding
        except Exception as e:
            logger.warning(f"⚠️ 获取文件编码失败: {file_path} - {e}", module_name=self.CHINESE_NAME)
            return "unknown"

    def write_file(self, file_path: str, content, encoding: str = "utf-8", as_json: bool = False,
                   file_type: str = "text") -> bool:
        """
        写入文件，自动创建父目录。

        :param file_path: 文件路径
        :param content: 内容（str 或 dict/list 当 as_json=True）
        :param encoding: 编码
        :param as_json: 是否以 JSON 格式写入
        :param file_type: 内容类型提示，用于日志（如 "html", "text", "log"），不影响写入逻辑
        """
        try:
            self.ensure_directory(os.path.dirname(file_path))
            with open(file_path, 'w', encoding=encoding) as f:
                if as_json:
                    json.dump(content, f, ensure_ascii=False, indent=4)
                    logger.debug(f"📦 写入 JSON 文件: {file_path}", module_name=self.CHINESE_NAME)
                else:
                    f.write(str(content))
                    # 根据 file_type 显示更友好的日志
                    type_display = file_type.upper() if file_type != "text" else "文本"
                    logger.debug(f"📝 写入 {type_display} 文件: {file_path}", module_name=self.CHINESE_NAME)
            return True
        except Exception as e:
            logger.error(f"❌ 写入文件失败: {file_path} - {e}", module_name=self.CHINESE_NAME, exc_info=True)
            return False

    def write_file_with_error(self, file_path: str, content, encoding: str = "utf-8") -> tuple[bool, str]:
        try:
            parent_dir = os.path.dirname(file_path)
            self.ensure_directory(parent_dir)

            # 检查父目录是否可写！
            if not os.access(parent_dir, os.W_OK):
                return False, f"Directory not writable: {parent_dir}"

            # 创建临时文件（在同一目录，确保跨设备安全）
            with tempfile.NamedTemporaryFile(
                    mode='w',
                    encoding=encoding,
                    dir=parent_dir,
                    delete=False
            ) as tmp_file:
                tmp_file.write(str(content))
                tmp_path = tmp_file.name

            # 原子替换（覆盖原文件）
            os.replace(tmp_path, file_path)
            return True, ""

        except Exception as e:
            return False, str(e)

    # ===================== 文件名生成 =====================
    @staticmethod
    def generate_filename(prefix: str, suffix: str = ".json", include_timestamp: bool = True) -> str:
        """
        生成标准格式的唯一文件名
        格式: {prefix}_{uuid8}_{timestamp}.xxx
        :param prefix: 前缀，如 category 名
        :param suffix: 后缀，默认 .json
        :param include_timestamp: 是否包含时间戳
        :return: 文件名字符串
        """
        safe_prefix = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '_', prefix)  # 过滤非法字符
        unique_id = str(uuid.uuid4())[:8]
        timestamp = str(int(time.time()))
        if include_timestamp:
            filename = f"{safe_prefix}_{unique_id}_{timestamp}{suffix}"
        else:
            filename = f"{safe_prefix}_{unique_id}{suffix}"
        return filename

    # ===================== 专用 JSON 写入方法 =====================
    def write_json(self, data: dict, file_path: Union[str, Path], indent: int = 4,
                   ensure_ascii: bool = False) -> bool:
        """
        专用 JSON 写入方法，自动创建目录，支持 Path 对象
        :param data: 要写入的字典数据
        :param file_path: 文件路径（str 或 Path）
        :param indent: JSON 缩进
        :param ensure_ascii: 是否转义非 ASCII 字符
        :return: 是否成功
        """
        path = None
        try:
            path = Path(file_path)
            self.ensure_directory(path.parent)  # 确保目录存在（已有方法）
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)
            logger.debug(f"✅ 成功写入 JSON 文件: {path}")
            return True
        except Exception as e:
            logger.error(f"❌ 写入 JSON 文件失败: {path} - {e}", exc_info=True)
            return False

    @staticmethod
    def ensure_directory(dir_path: Union[str, Path]) -> bool:
        """确保目录存在，不存在则创建"""
        try:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"❌ 创建目录失败: {dir_path} - {e}", exc_info=True)
            return False

    # ===================== 文件/目录操作 =====================

    @staticmethod
    def delete_file(file_path: str) -> bool:
        """删除指定文件"""
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
                logger.info(f"🗑️ 已删除文件: {file_path}")
                return True
            logger.debug(f"ℹ️ 文件不存在，跳过删除: {file_path}")
            return False
        except Exception as e:
            logger.error(f"❌ 删除文件失败: {file_path} - {e}")
            return False

    @staticmethod
    def delete_dir(dir_path: str) -> bool:
        """递归删除目录及内容"""
        try:
            if os.path.isdir(dir_path):
                shutil.rmtree(dir_path)
                logger.info(f"🗑️ 已删除目录: {dir_path}")
                return True
            logger.debug(f"ℹ️ 目录不存在，跳过删除: {dir_path}")
            return False
        except Exception as e:
            logger.error(f"❌ 删除目录失败: {dir_path} - {e}", exc_info=True)
            return False

    @staticmethod
    def list_files(dir_path: str, ext_filter: Union[str, None] = None) -> List[str]:
        """列出目录下所有文件（支持后缀过滤）"""
        files = []
        try:
            for root, _, filenames in os.walk(dir_path):
                for filename in filenames:
                    if ext_filter is None or filename.endswith(ext_filter):
                        file_path = os.path.join(root, filename)
                        files.append(file_path)
            logger.debug(f"📄 扫描目录: {dir_path}, 找到 {len(files)} 个文件")
        except Exception as e:
            logger.error(f"❌ 列出文件失败: {dir_path} - {e}")
        return files

    def replace_in_file(self, file_path: str, old_str: str, new_str: str) -> bool:
        """替换文件中的某段文字"""
        try:
            content = self.read_file(file_path)
            if not content:
                logger.warning(f"⚠️ 文件为空或读取失败，无法替换: {file_path}")
                return False
            new_content = content.replace(old_str, new_str)
            if content == new_content:
                logger.debug(f"🔄 替换内容未变化: {file_path}")
            else:
                logger.info(f"🔄 替换成功: '{old_str}' -> '{new_str}' in {file_path}")
            return self.write_file(file_path, new_content)
        except Exception as e:
            logger.error(f"❌ 替换文件内容失败: {file_path} - {e}")
            return False

    @staticmethod
    def ensure_newline_at_end(file_path: str) -> bool:
        """确保文件结尾有换行符"""
        try:
            if not os.path.exists(file_path):
                logger.warning(f"⚠️ 文件不存在: {file_path}")
                return False
            with open(file_path, 'ab+') as f:
                f.seek(-1, os.SEEK_END)
                last_char = f.read(1)
                if last_char != b'\n':
                    f.write(b'\n')
                    logger.debug(f"↩️ 补充换行符: {file_path}")
            return True
        except Exception as e:
            logger.error(f"❌ 确保文件结尾换行失败: {file_path} - {e}")
            return False

    # ===================== JSON 操作 =====================

    def read_json_file(self, file_path: str) -> Dict:
        """读取 JSON 文件"""
        try:
            content = self.read_file(file_path)
            if not content:
                raise FileNotFoundError(f"配置文件内容为空: {file_path}")

            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError(f"配置文件根节点必须是对象 (Dict)，当前类型: {type(data)}")

            logger.info(f"📥 成功加载配置文件: {file_path}")
            return data
        except Exception as e:
            logger.critical(f"❌ 致命错误：无法加载配置文件 {file_path} - {e}")
            raise

    def read_all_json_files_in_dir(self, dir_path: str) -> List:
        """读取目录下所有 JSON 文件并合并"""
        all_data = []
        files = self.list_files(dir_path, ".json")
        logger.info(f"📂 开始读取 {len(files)} 个 JSON 文件...")
        for file in files:
            data = self.read_json_file(file)
            if isinstance(data, list):
                all_data.extend(data)
            else:
                all_data.append(data)
        logger.info(f"✅ 合并完成，共 {len(all_data)} 条数据")
        return all_data

    # ===================== DataFrame 操作 =====================

    def read_json_to_dataframe(self, file_path: str) -> pd.DataFrame:
        """读取 JSON 文件转为 DataFrame"""
        data = self.read_json_file(file_path)
        df = pd.DataFrame(data)
        logger.info(f"📊 已加载 DataFrame: {file_path} -> {df.shape}")
        return df

    @staticmethod
    def save_dataframe_to_json(df: pd.DataFrame, file_path: str) -> bool:
        """保存 DataFrame 为 JSON"""
        try:
            df.to_json(file_path, orient='records', ensure_ascii=False, indent=2)
            logger.info(f"💾 保存 DataFrame 为 JSON: {file_path} ({len(df)} 条)")
            return True
        except Exception as e:
            logger.error(f"❌ 保存 DataFrame 失败: {file_path} - {e}")
            return False

    # ===================== 停用词与品牌词加载 =====================

    def load_stopwords(self, filepath: str) -> Set[str]:
        """加载停用词文件"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = (line.strip() for line in f)
                stopwords = {line for line in lines if line}
            logger.info(f"✅ 成功加载停用词: {filepath} -> {len(stopwords)} 个")
            return stopwords
        except FileNotFoundError:
            logger.error(f"❌ 停用词文件未找到: {filepath}")
            return set()
        except Exception as e:
            logger.error(f"❌ 读取停用词文件失败: {filepath} - {e}", exc_info=True)
            return set()

    def load_brands(self, filepath: str) -> Set[str]:
        """加载品牌词文件（英文或常见缩写）"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = (line.strip().lower() for line in f)
                brands = {line for line in lines if line and not line.startswith('#')}
            logger.info(f"✅ 成功加载品牌词: {filepath} -> {len(brands)} 个")
            return brands
        except FileNotFoundError:
            logger.error(f"❌ 英文品牌词文件未找到: {filepath}")
            return set()
        except Exception as e:
            logger.error(f"❌ 读取英文品牌词文件失败: {filepath} - {e}", exc_info=True)
            return set()

    # ===================== 目录搜索 =====================

    def find_directories(self, base_dir: str, keywords: Union[str, List[str], Tuple[str, ...]]) -> List[str]:
        """搜索包含任意一个关键字的目录（模糊匹配）"""
        base_dir = os.path.normpath(base_dir)
        logger.info(f"🔍 开始在目录 {base_dir} 中搜索包含以下任一关键字的子目录: {keywords}")

        if not os.path.exists(base_dir):
            logger.error(f"🚫 基础目录不存在: {base_dir}")
            return []

        if isinstance(keywords, str):
            keywords = [keywords]
        elif not isinstance(keywords, (list, tuple)):
            logger.error("🚨 keywords 必须是字符串、列表或元组")
            raise TypeError("keywords 必须是字符串、列表或元组")

        matched_dirs = []
        for d in os.listdir(base_dir):
            dir_path = os.path.join(base_dir, d)
            if os.path.isdir(dir_path) and any(kw.lower() in d.lower() for kw in keywords):
                matched_dirs.append(d)

        full_paths = [os.path.join(base_dir, d) for d in matched_dirs]
        logger.info(f"✅ 找到 {len(full_paths)} 个匹配目录: {full_paths}")
        return full_paths

    def read_json_files_in_dir(self, dir_path: str) -> pd.DataFrame:
        """读取指定目录下的所有 JSON 文件并合并为一个 DataFrame"""
        dir_path = os.path.normpath(dir_path)

        if not os.path.isdir(dir_path):
            logger.error(f"🚫 无效目录: {dir_path}")
            return pd.DataFrame()

        logger.info(f"📂 开始读取目录 {dir_path} 下的所有 JSON 文件")
        json_files = glob.glob(os.path.join(dir_path, "*.json"))
        logger.info(f"📄 共找到 {len(json_files)} 个 JSON 文件")

        if not json_files:
            logger.warning(f"⚠️ 未在目录 {dir_path} 中找到任何 .json 文件")
            return pd.DataFrame()

        dfs = []
        for file in json_files:
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, list) and all(isinstance(item, dict) for item in data):
                    df = pd.DataFrame(data)
                    dfs.append(df)
                    has_ts = any('timestamp' in item for item in data)
                    logger.debug(f"📊 文件 {file} {'含' if has_ts else '不含'} timestamp 字段，已加载")
                else:
                    logger.error(f"❌ 文件 {file} 的结构不合法，应为字典列表")
            except Exception as e:
                logger.error(f"💥 读取 JSON 文件失败: {file} - {e}", exc_info=True)

        if dfs:
            combined_df = pd.concat(dfs, ignore_index=True)
            logger.info(f"✅ 成功合并 {len(dfs)} 个 JSON 文件，总数据行数: {len(combined_df)}")
            return combined_df
        else:
            logger.warning("📭 未读取到任何有效的 JSON 数据")
            return pd.DataFrame()

    # ===================== ZIP 打包 =====================

    def zip_task_dir(self, datacleaner) -> str:
        """将整个任务目录打包为 ZIP"""
        try:
            task_dir = Path(datacleaner.task_dir)
            zip_path = task_dir.with_suffix(".zip")

            if not task_dir.exists():
                logger.error(f"❌ 无法压缩: 任务目录不存在 {datacleaner.task_dir}")
                return ""

            if zip_path.exists():
                logger.info(f"🗑️ 删除已存在的 ZIP 文件: {zip_path}")
                zip_path.unlink()

            logger.info(f"📦 开始压缩目录: {datacleaner.task_dir} -> {zip_path}")

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file in task_dir.rglob("*"):
                    if file.is_file():
                        arcname = file.relative_to(task_dir.parent)
                        zipf.write(file, arcname=arcname)
                        logger.debug(f"📎 添加文件到 ZIP: {arcname}")

            zip_size_kb = zip_path.stat().st_size / 1024
            logger.info(f"✅ 压缩完成: {zip_path} (大小: {zip_size_kb:.2f} KB)")
            return str(zip_path)

        except Exception as e:
            logger.error(f"❌ 压缩目录失败: {e}", exc_info=True)
            return ""

    # 返回 base_dir/YYYY-MM-DD/ 路径，并确保目录存在。
    def get_todays_subdir(self, base_dir: Union[str, Path]) -> Path:
        """
        返回 base_dir/YYYY-MM-DD/ 路径，并确保目录存在。
        """
        # 统一转换为 Path 对象
        base_dir = Path(base_dir)
        today_str = datetime.now().strftime("%Y-%m-%d")
        dated_dir = base_dir / today_str
        dated_dir.mkdir(parents=True, exist_ok=True)
        return dated_dir
