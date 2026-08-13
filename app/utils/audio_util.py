from typing import Optional
from pathlib import Path
from app.utils.logger import LoggerManager as logger


class AudioUtils:
    CHINESE_NAME = "音频工具函数"

    def normalize_audio_directory(self, directory: str, overwrite: bool = False) -> None:
        """
        递归规范化指定目录及子目录下的所有音频文件：
        1. 将非 MP3 格式的音频转换为 MP3（需要 ffmpeg）
        2. 将非 {数字}.mp3 格式的文件重命名为下一个可用的整型编号
        3. 如果文件已经满足规范 (数字.mp3)，则跳过

        :param directory: 要处理的根目录路径
        :param overwrite: 是否覆盖已存在的目标文件，默认 False
        """
        audio_extensions = {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a'}

        def is_already_processed(file_path: Path) -> bool:
            return file_path.suffix.lower() == '.mp3' and file_path.stem.isdigit()

        def find_first_available_number(dir_path: Path) -> int:
            i = 1
            while True:
                candidate = dir_path / f'{i}.mp3'
                if not candidate.exists():
                    return i
                i += 1

        def process_directory(dir_path: Path) -> None:
            audios = [f for f in dir_path.iterdir() if f.is_file() and f.suffix.lower() in audio_extensions]
            audios.sort()

            for audio in audios:
                if is_already_processed(audio):
                    logger.debug(f"跳过已规范文件: {audio.name}", module_name=self.CHINESE_NAME)
                    continue

                try:
                    new_number = find_first_available_number(dir_path)
                    new_path = dir_path / f'{new_number}.mp3'

                    if not overwrite and new_path.exists():
                        logger.warning(f"目标文件 {new_path} 已存在，跳过 {audio.name}", module_name=self.CHINESE_NAME)
                        continue

                    if audio.suffix.lower() == '.mp3':
                        if audio.resolve() != new_path.resolve():
                            audio.rename(new_path)
                            logger.info(f"已重命名: {audio.name} -> {new_number}.mp3", module_name=self.CHINESE_NAME)
                    else:
                        try:
                            import subprocess
                            subprocess.run(
                                ['ffmpeg', '-i', str(audio), '-codec:a', 'libmp3lame', '-q:a', '2', str(new_path)],
                                capture_output=True,
                                check=True
                            )
                            audio.unlink()
                            logger.info(f"已转换并规范化: {audio.name} -> {new_number}.mp3", module_name=self.CHINESE_NAME)
                        except FileNotFoundError:
                            logger.warning(f"未找到 ffmpeg，跳过格式转换: {audio.name}", module_name=self.CHINESE_NAME)
                            if audio.resolve() != new_path.resolve():
                                audio.rename(new_path)
                                logger.info(f"已重命名(未转换): {audio.name} -> {new_number}{audio.suffix}",
                                            module_name=self.CHINESE_NAME)
                        except Exception as e:
                            logger.error(f"转换文件 {audio.name} 时出错: {e}", module_name=self.CHINESE_NAME)

                except Exception as e:
                    logger.error(f"处理文件 {audio.name} 时出错: {e}", module_name=self.CHINESE_NAME)

            subdirs = [d for d in dir_path.iterdir() if d.is_dir()]
            for subdir in subdirs:
                process_directory(subdir)

        root = Path(directory)
        if not root.exists():
            raise FileNotFoundError(f"目录不存在: {directory}")
        process_directory(root)

    def get_audio_duration(self, file_path: str) -> Optional[float]:
        """
        获取音频文件时长（秒）。

        :param file_path: 音频文件路径
        :return: 时长（秒），失败返回 None
        """
        p = Path(file_path)
        if not p.exists():
            logger.error(f"文件不存在: {file_path}", module_name=self.CHINESE_NAME)
            return None

        try:
            import subprocess
            result = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_entries', 'format=duration', str(p)],
                capture_output=True,
                text=True,
                check=True
            )
            import json
            data = json.loads(result.stdout)
            return float(data['format']['duration'])
        except FileNotFoundError:
            logger.warning(f"未找到 ffprobe，无法获取音频时长: {file_path}", module_name=self.CHINESE_NAME)
            return None
        except Exception as e:
            logger.error(f"获取音频时长失败: {e}", module_name=self.CHINESE_NAME)
            return None

    def format_duration(self, seconds: float) -> str:
        """
        将秒数格式化为 MM:SS 或 HH:MM:SS。

        :param seconds: 时长（秒）
        :return: 格式化的字符串
        """
        if seconds is None or seconds <= 0:
            return "00:00"

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    @staticmethod
    def get_audio_info(file_path: str) -> Optional[dict]:
        """
        获取音频文件的详细信息。

        :param file_path: 音频文件路径
        :return: 包含时长、比特率等信息的字典，失败返回 None
        """
        p = Path(file_path)
        if not p.exists():
            return None

        try:
            import subprocess
            result = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_entries',
                 'format=duration,bit_rate,filename', '-show_entries', 'stream=codec_name,sample_rate,channels'],
                input=str(p),
                capture_output=True,
                text=True,
                check=True
            )
            return json.loads(result.stdout)
        except Exception:
            return None

    @staticmethod
    def merge_audio_fragments(fragments: list, output_path: str, sample_rate: int = 32000) -> bool:
        """
        将多个音频片段（numpy 数组）合并为完整音频文件。

        :param fragments: numpy 数组列表，每个数组代表一个音频片段
        :param output_path: 输出文件路径
        :param sample_rate: 采样率，默认 32000Hz
        :return: 是否成功
        """
        if not fragments:
            logger.error("音频片段列表为空", module_name="音频工具函数")
            return False

        try:
            import numpy as np
            import soundfile as sf

            # 确保所有片段是 numpy 数组
            audio_data = []
            for i, frag in enumerate(fragments):
                if isinstance(frag, np.ndarray):
                    audio_data.append(frag)
                elif isinstance(frag, (list, tuple)):
                    audio_data.append(np.array(frag, dtype=np.float32))
                else:
                    logger.error(f"片段 {i} 格式不支持: {type(frag)}", module_name="音频工具函数")
                    return False

            # 拼接所有片段
            merged = np.concatenate(audio_data)

            # 保存为 wav 文件
            sf.write(output_path, merged, sample_rate, subtype='PCM_16')
            logger.info(f"音频合并完成: {output_path}", module_name="音频工具函数")
            return True

        except ImportError as e:
            logger.error(f"缺少依赖库: {e}", module_name="音频工具函数")
            return False
        except Exception as e:
            logger.error(f"音频合并失败: {e}", module_name="音频工具函数")
            return False

    @staticmethod
    def numpy_to_wav(audio_array, output_path: str, sample_rate: int = 32000) -> bool:
        """
        将 numpy 数组保存为 WAV 音频文件。

        :param audio_array: numpy 数组 (float32 或 int16)
        :param output_path: 输出文件路径
        :param sample_rate: 采样率
        :return: 是否成功
        """
        try:
            import numpy as np
            import soundfile as sf

            if not isinstance(audio_array, np.ndarray):
                audio_array = np.array(audio_array, dtype=np.float32)

            sf.write(output_path, audio_array, sample_rate, subtype='PCM_16')
            return True
        except Exception as e:
            logger.error(f"保存音频文件失败: {e}", module_name="音频工具函数")
            return False
