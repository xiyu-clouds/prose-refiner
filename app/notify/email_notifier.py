import os
import smtplib
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from app.common import keys as ke
from app.notify.notifier import Notifier
from app.utils.logger import LoggerManager as logger


class EmailNotifier(Notifier):
    CHINESE_NAME = "邮件发送"

    def __init__(self, config):
        self.config = config

    async def send(self, title: str, message: str, file_path: str = None):
        try:
            msg = MIMEMultipart()
            msg['Subject'] = Header(title, ke.KEY_UTF_8)
            msg['From'] = formataddr((str(Header('心海', ke.KEY_UTF_8)), self.config[ke.KEY_EMAIL_USERNAME]))
            msg['To'] = ', '.join(self.config[ke.KEY_EMAIL_TO])

            msg.attach(MIMEText(message, ke.KEY_PLAIN, ke.KEY_UTF_8))

            if file_path and os.path.exists(file_path):
                filename = os.path.basename(file_path)

                with open(file_path, ke.KEY_RB) as f:
                    part = MIMEApplication(f.read(), Name=filename)
                    part['Content-Disposition'] = f'attachment; filename="{filename}"'
                    msg.attach(part)

            with smtplib.SMTP_SSL(self.config[ke.KEY_EMAIL_SMTP_SERVER], self.config[ke.KEY_EMAIL_PORT]) as server:
                server.login(self.config[ke.KEY_EMAIL_USERNAME], self.config[ke.KEY_EMAIL_PASSWORD])
                server.sendmail(self.config[ke.KEY_EMAIL_USERNAME], self.config[ke.KEY_EMAIL_TO], msg.as_string())

            logger.info("📧 邮件发送成功", module_name=self.CHINESE_NAME)
        except Exception as e:
            logger.error(f"❌ 邮件发送失败：{e}", module_name=self.CHINESE_NAME, exc_info=True)
