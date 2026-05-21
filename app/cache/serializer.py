from aiocache.serializers import BaseSerializer
import json


class UTF8JsonSerializer(BaseSerializer):
    """
    返回原始 UTF-8 JSON 字符串（非 base64，非 ASCII 转义），
    便于在 redis-cli 中直接查看内容。
    dumps() 返回 str，loads() 接收 str。
    """

    def dumps(self, value):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'))

    def loads(self, value):
        if value is None or value == "":
            return None
        return json.loads(value)
