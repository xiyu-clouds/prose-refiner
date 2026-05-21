from pathlib import Path
from typing import Dict, Any, Optional, Union
from jinja2 import Environment, FileSystemLoader
from app.utils.file_util import FileUtil
from app.utils.time_utils import format_timestamp_with_weekday
from app.common import keys as ke
from app.common import values as va
from app.utils.logger import LoggerManager as logger


class ReportGenerator:
    CHINESE_NAME = "报告生成器"

    def __init__(self, file_util: FileUtil, template_dir: Path):
        self.file_util = file_util
        self.env = Environment(loader=FileSystemLoader(str(template_dir)))
        self.env.filters[ke.KEY_FORMAT_WEEKDAY] = format_timestamp_with_weekday

    def render_report_to_html(
            self,
            data: Dict[str, Any],
            template_name: str,
            filename_prefix: str,
            reports_dir: Union[str, Path]
    ) -> Optional[Path]:
        try:
            template = self.env.get_template(template_name)
            html_output = template.render(data=data)

            # 使用传入的前缀生成文件名
            filename = self.file_util.generate_filename(
                prefix=filename_prefix,
                suffix=va.VAL_REPORT_SUFFIX,
                include_timestamp=True
            )
            base_dir = self.file_util.get_todays_subdir(reports_dir)
            output_path = base_dir / filename

            success = self.file_util.write_file(
                file_path=str(output_path),
                content=html_output,
                encoding=ke.KEY_UTF_8,
                as_json=False,
                file_type=ke.KEY_HTML
            )
            if not success:
                logger.error("HTML 报告写入失败", module_name=self.CHINESE_NAME, extra={ke.KEY_PATH: str(output_path)})
                return None

            logger.info("📄 HTML 报告已生成", module_name=self.CHINESE_NAME, extra={ke.KEY_PATH: str(output_path)})
            return output_path
        except Exception as e:
            logger.exception("💥 HTML 报告生成失败", module_name=self.CHINESE_NAME, extra={ke.KEY_ERROR: str(e)})
            return None
