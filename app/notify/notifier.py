from abc import ABCMeta, abstractmethod


class Notifier(metaclass=ABCMeta):
    @abstractmethod
    async def send(self, title: str, message: str, file_path: str = None):
        """
        发送通知的抽象方法
        :param title: 消息标题
        :param message: 消息正文
        :param file_path: 附件路径（可选）
        """
        pass
