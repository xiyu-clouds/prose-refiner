"""业务领域层 —— 纯函数业务逻辑，由 cpython 编译为 .pyd。

设计约束：
- 禁止 import APIRouter / Depends / Query 等 FastAPI 路由设施。
- 入参只允许 engine 句柄 + 原始值；返回值为 Python 原生可序列化类型。
- 不持有 HTTP 请求/响应对象，不抛 HTTPException。
"""
