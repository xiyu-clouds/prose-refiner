from __future__ import annotations
import traceback
from app.common import keys as ke
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict


class LLMResponse(BaseModel):
    """
    【终极通用版】LLM 统一响应协议
    适用所有场景：文本 / JSON / 函数调用 / 多模态 / 流式 / 插件
    无业务绑定、零冗余、可永久使用
    """
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        frozen=False,
        arbitrary_types_allowed=True
    )

    # --------------------------------------------------------------------------
    # 核心状态（2 个字段定义一切）
    # --------------------------------------------------------------------------
    ok: bool = Field(
        default=False,
        alias="ok",
        description="✅ 调用成功：网络正常 + 模型响应（不代表内容有效）"
    )

    valid: bool = Field(
        default=False,
        alias="valid",
        description="✅ 内容有效：格式正确 + 非空 + 校验通过"
    )

    # --------------------------------------------------------------------------
    # 输出内容（统一承载所有类型）
    # --------------------------------------------------------------------------
    content: Union[str, Dict[str, Any], List[Any], None] = Field(
        default=None,
        description="最终输出内容：str | dict | list | null"
    )

    raw: Optional[str] = Field(
        default=None,
        alias="raw",
        description="模型原始返回字符串"
    )

    # --------------------------------------------------------------------------
    # 错误体系（行业标准四层结构）
    # --------------------------------------------------------------------------
    err: Optional[str] = Field(
        default=None,
        alias="err",
        description="错误类型：api / validation / network / timeout / system"
    )

    msg: Optional[str] = Field(
        default=None,
        alias="msg",
        description="错误简要信息"
    )

    errors: List[str] = Field(
        default_factory=list,
        alias="errors",
        description="结构化校验错误列表"
    )

    stack: Optional[str] = Field(
        default=None,
        alias="stack",
        description="系统异常堆栈（仅调试）"
    )

    # --------------------------------------------------------------------------
    # 可观测性（监控、 tracing、日志、审计）
    # --------------------------------------------------------------------------
    model: str = Field(default="unknown", description="模型名称：gpt-4o, qwen-max, deepseek-chat")
    vendor: str = Field(default="unknown", description="厂商：openai / qwen / deepseek / anthropic")
    cost: Dict[str, any] = Field(default_factory=dict, description="tokens 消耗：prompt, completion, total")
    elapsed_ms: float = Field(default=0.0, description="请求耗时（毫秒）")
    created: float = Field(default=0.0, description="创建时间戳")

    # --------------------------------------------------------------------------
    # 业务唯一判断入口
    # --------------------------------------------------------------------------
    def success(self) -> bool:
        return self.ok and self.valid

    # --------------------------------------------------------------------------
    # 序列化
    # --------------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_unset=True)

    # --------------------------------------------------------------------------
    # 工厂方法（真正极简）
    # --------------------------------------------------------------------------
    @classmethod
    def ok_content(
            cls,
            content: Union[str, Dict, List],
            raw: str,
            vendor: str,
            model: str,
            elapsed_ms: float = 0.0,
            cost: Optional[Dict[str, int]] = None
    ) -> LLMResponse:
        return cls(
            ok=True,
            valid=True,
            content=content,
            raw=raw,
            vendor=vendor,
            model=model,
            elapsed_ms=elapsed_ms,
            cost=cost or {}
        )

    @classmethod
    def invalid(
            cls,
            errors: List[str],
            content: Any,
            vendor: str,
            model: str,
            msg: str
    ) -> LLMResponse:
        return cls(
            ok=True,
            valid=False,
            content=content,
            errors=errors,
            err="validation",
            msg=msg,
            vendor=vendor,
            model=model
        )

    @classmethod
    def api_fail(
            cls,
            msg: str,
            vendor: str,
            model: str,
            elapsed_ms: float = 0.0
    ) -> LLMResponse:
        return cls(
            ok=False,
            valid=False,
            err="api",
            msg=msg,
            vendor=vendor,
            model=model,
            elapsed_ms=elapsed_ms
        )

    @classmethod
    def sys_fail(
            cls,
            msg: str,
            vendor: str = ke.KEY_UNKNOWN,
            model: str = ke.KEY_UNKNOWN,
            with_stack: bool = True
    ) -> LLMResponse:
        return cls(
            ok=False,
            valid=False,
            err="system",
            msg=msg,
            stack=traceback.format_exc() if with_stack else None,
            vendor=vendor,
            model=model
        )