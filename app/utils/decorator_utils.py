from app.utils.logger import LoggerManager as logger
from app.common import keys as ke


def log_function_event(
        action: str,
        func_name: str,
        module_name: str,
        **kwargs
):
    """
    统一日志记录接口，用于函数执行监控。

    Args:
        action: 动作类型，如 'start', 'success', 'timeout', 'exception', 'failure'
        func_name: 函数名
        module_name: 模块名（用于日志分类）
        **kwargs: 其他上下文字段
    """
    log_data = {
        ke.KEY_FUNC_NAME: func_name,
        ke.KEY_MODULE_NAME: module_name,
        **kwargs
    }

    message = f"函数 {func_name} {action}"

    if action == ke.KEY_START:
        logger.info(message, **log_data)
    elif action in [ke.KEY_SUCCESS, ke.KEY_COMPLETED]:
        logger.info(f"{message}，耗时 {kwargs.get(ke.KEY_DURATION, 0):.4f} 秒", **log_data)
    elif action == ke.KEY_TIMEOUT:
        logger.error(message, **log_data)
    elif action == ke.KEY_EXCEPTION:
        logger.exception(f"{message}: {kwargs.get(ke.KEY_EXCEPTION)}", **log_data)
    elif action == ke.KEY_FAILURE:
        logger.exception(f"{message}，耗时 {kwargs.get(ke.KEY_DURATION, 0):.4f} 秒，异常: {kwargs.get(ke.KEY_EXCEPTION)}", **log_data)
    else:
        logger.info(message, **log_data)
