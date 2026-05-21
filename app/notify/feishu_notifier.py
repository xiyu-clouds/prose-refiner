import requests
import json
from app.common import keys as ke
from app.notify.notifier import Notifier
from app.utils.logger import LoggerManager as logger


class FeishuNotifier(Notifier):
    CHINESE_NAME = "飞书通知"

    def __init__(self, config):
        self.webhook_url = config.get(ke.KEY_FEISHU_WEBHOOK_URL)
        # 支持多个用户 ID 列表
        self.at_user_ids = config.get(ke.KEY_FEISHU_AT_USER_IDS) or []

        if isinstance(self.at_user_ids, str):
            self.at_user_ids = [self.at_user_ids]  # 统一转成列表

    async def send(self, title: str, message: str, file_path: str = ""):
        """
        发送飞书群机器人通知
        :param title: 消息标题
        :param message: 正文内容
        :param file_path: 文件链接（可选），例如飞书共享链接
        """
        # 构造消息内容块
        content_blocks = [[
            {
                ke.KEY_TAG: ke.KEY_TEXT,
                ke.KEY_TEXT: f"{title}\n\n{message}"
            }
        ]]

        # 添加文件链接（如果有）
        if file_path:
            content_blocks.append([
                {
                    ke.KEY_TAG: ke.KEY_TEXT,
                    ke.KEY_TEXT: f"\n\n📎 文件: {file_path}"
                }
            ])

        # 添加 @ 用户
        for user_id in self.at_user_ids:
            content_blocks.append([{
                ke.KEY_TAG: ke.KEY_AT,
                ke.KEY_USER_ID: user_id
            }])

        # 构造最终 Payload
        payload = {
            ke.KEY_MSG_TYPE: ke.KEY_POST,
            ke.KEY_CONTENT: {
                ke.KEY_POST: {
                    ke.KEY_ZH_CN: {
                        ke.KEY_TITLE: title,
                        ke.KEY_CONTENT: content_blocks
                    }
                }
            }
        }

        try:
            response = requests.post(self.webhook_url, data=json.dumps(payload))
            logger.info(f"🕊️ 飞书消息发送状态：{response.status_code}", module_name=self.CHINESE_NAME)
            logger.info(f"📩 响应内容：{response.text}", module_name=self.CHINESE_NAME)
            return response.json()
        except Exception as e:
            logger.error(f"❌ 飞书消息发送失败：{e}", exc_info=True, module_name=self.CHINESE_NAME)
            return None
