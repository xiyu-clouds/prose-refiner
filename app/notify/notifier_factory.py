from app.common import keys as ke
from app.config.config import config
from app.notify.email_notifier import EmailNotifier
from app.notify.feishu_notifier import FeishuNotifier
from app.notify.wecome_notifier import WecomNotifier


def get_notifiers():
    notifiers = []
    channels = config.NOTIFICATION_CHANNELS

    if ke.KEY_EMAIL in channels:
        email_config = {
            ke.KEY_EMAIL_SMTP_SERVER: config.EMAIL_SMTP_SERVER,
            ke.KEY_EMAIL_PORT: config.EMAIL_PORT,
            ke.KEY_EMAIL_USERNAME: config.EMAIL_USERNAME,
            ke.KEY_EMAIL_PASSWORD: config.EMAIL_PASSWORD,
            ke.KEY_EMAIL_TO: config.EMAIL_TO
        }
        notifiers.append(EmailNotifier(email_config))
    if ke.KEY_FEISHU in channels:
        feishu_config = {
            ke.KEY_FEISHU_WEBHOOK_URL: config.FEISHU_WEBHOOK_URL,
            ke.KEY_FEISHU_AT_USER_IDS: config.FEISHU_AT_USER_IDS
        }
        notifiers.append(FeishuNotifier(feishu_config))
    if ke.KEY_WECOM in channels:
        wecome_config = {
            ke.KEY_WECOM_WEBHOOK_URL: config.WECOM_WEBHOOK_URL,
            ke.KEY_WECOM_AT_USER_IDS: config.WECOM_AT_USER_IDS
        }
        notifiers.append(WecomNotifier(wecome_config))
    return notifiers
