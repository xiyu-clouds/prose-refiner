from app.utils.logger import LoggerManager as logger
from app.common import keys as ke

# 全局描述函数注册表
CONTEXT_DESCRIPTORS = []
CHINESE_NAME = "上下文描述注册器"


def register_descriptor(*keys):
    """
    装饰器：注册描述函数，并声明它依赖的顶层键
    自动记录注册日志，便于调试和确认上下文感知能力
    """
    def decorator(func):
        descriptor_info = {
            ke.KEY_FUNC: func,
            ke.KEY_KEYS: keys,
            ke.KEY_NAME: func.__name__
        }
        CONTEXT_DESCRIPTORS.append(descriptor_info)

        # 使用 extra 传入自定义字段
        logger.info(
            "上下文描述符已注册",
            extra={
                ke.KEY_DESCRIPTOR_NAME: func.__name__,
                ke.KEY_DEPENDENT_KEYS: list(keys),
                ke.KEY_TOTAL_REGISTERED: len(CONTEXT_DESCRIPTORS)
            },
            module_name=CHINESE_NAME,
            location=ke.KEY_REGISTER_DESCRIPTOR
        )

        return func

    return decorator
