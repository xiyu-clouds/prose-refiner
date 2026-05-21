import requests
import os
from app.common import keys as ke
from app.notify.notifier import Notifier
from app.utils.logger import LoggerManager as logger


class WecomNotifier(Notifier):
    CHINESE_NAME = "企业微信通知"

    def __init__(self, config):
        self.webhook_url = config.get(ke.KEY_WECOM_WEBHOOK_URL)
        self.at_user_ids = config.get(ke.KEY_WECOM_AT_USER_IDS)

        if isinstance(self.at_user_ids, str):
            self.at_user_ids = [self.at_user_ids]

    async def send(self, title: str, message: str, file_path: str = None):
        """
        发送企业微信机器人通知（支持文本 + 文件）
        :param title: 消息标题
        :param message: 正文内容
        :param file_path: 本地文件路径（如 .zip 压缩包）
        """
        # 构造基础文本消息
        content = f"【{title}】\n\n{message}"
        if file_path:
            content += f"\n\n📎 详情见附件"

        # 先发文本消息
        self._send_text(content)

        # 如果有文件，再上传并发送文件消息
        if file_path and os.path.exists(file_path):
            self._send_file(file_path)
        elif file_path:
            logger.error(f"❌ 文件不存在：{file_path}", module_name=self.CHINESE_NAME)

    def _send_text(self, content: str):
        """发送文本消息"""
        payload = {
            ke.KEY_MSGTYPE: ke.KEY_TEXT,
            ke.KEY_TEXT: {
                ke.KEY_CONTENT: content,
                ke.KEY_MENTIONED_LIST: self.at_user_ids
            }
        }
        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            logger.info(f"💬 文本消息发送状态：{response.status_code}", module_name=self.CHINESE_NAME)
            logger.info(f"📩 响应内容：{response.text}", module_name=self.CHINESE_NAME)
        except Exception as e:
            logger.error(f"❌ 文本消息发送失败：{e}", exc_info=True, module_name=self.CHINESE_NAME)

    def _send_file(self, file_path: str):
        """上传并发送文件消息"""
        try:
            # 第一步：提取 webhook 中的 key
            if f'{ke.KEY_KEY}=' not in self.webhook_url:
                logger.error("❌ Webhook URL 缺少 key 参数")
                return

            key = self.webhook_url.split(f'{ke.KEY_KEY}=')[1].split('&')[0]

            # 第二步：上传文件获取 media_id
            upload_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?key={key}&type=file"
            file_name = os.path.basename(file_path)

            with open(file_path, ke.KEY_RB) as f:
                files = {ke.KEY_FILE: (file_name, f)}
                response = requests.post(upload_url, files=files, timeout=30)

            result = response.json()
            if result.get(ke.KEY_ERRCODE) != 0:
                logger.error(f"❌ 文件上传失败：{result.get(ke.KEY_ERRMSG)}", module_name=self.CHINESE_NAME)
                return

            media_id = result.get(ke.KEY_MEDIA_ID)
            if not media_id:
                logger.error(f"❌ 未获取到 {ke.KEY_MEDIA_ID}", module_name=self.CHINESE_NAME)

            logger.info(f"✅ 文件上传成功，{ke.KEY_MEDIA_ID}: {media_id}", module_name=self.CHINESE_NAME)

            # 第三步：发送文件消息
            payload = {
                ke.KEY_MSGTYPE: ke.KEY_FILE,
                ke.KEY_FILE: {
                    ke.KEY_MEDIA_ID: media_id
                }
            }

            send_response = requests.post(self.webhook_url, json=payload, timeout=10)
            send_result = send_response.json()

            if send_result.get(ke.KEY_ERRCODE) == 0:
                logger.info(f"📎 文件 '{file_name}' 发送成功", module_name=self.CHINESE_NAME)
            else:
                logger.error(f"❌ 文件发送失败：{send_result.get(ke.KEY_ERRMSG)}", module_name=self.CHINESE_NAME)

        except Exception as e:
            logger.error(f"❌ 文件发送异常：{e}", exc_info=True, module_name=self.CHINESE_NAME)
