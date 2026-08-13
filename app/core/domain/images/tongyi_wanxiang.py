"""通义万相文生图 API 调用 —— 同步端点请求构建与响应解析。

从 routers/image_generation.py 提取，保持行为完全一致。
"""

import json
from typing import Any, Dict, Optional

import requests

from app.common.llm_constants import LLMModel

_SYNC_ENDPOINT_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"


def build_sync_parameters(
    model: str, size: str, negative_prompt: str, n: int,
    thinking_mode: Optional[bool], enable_sequential: Optional[bool],
    color_palette: Optional[list], seed: Optional[int] = None,
) -> Dict[str, Any]:
    """按模型能力构建同步端点 parameters（差异：negative_prompt / prompt_extend / n / wan2.7 特有参数）。

    wan2.7 互斥规则（按官方文档）：
    - enable_sequential=true → thinking_mode 与 color_palette 不可用；n 范围 1~12
    - enable_sequential=false（默认）→ thinking_mode、color_palette 可用；n 范围 1~4
    """
    params: Dict[str, Any] = {"size": size}
    if model == LLMModel.WANX2_7_IMAGE:
        params["n"] = n
        if enable_sequential:
            params["enable_sequential"] = True
        else:
            if thinking_mode is not None:
                params["thinking_mode"] = bool(thinking_mode)
            if color_palette and isinstance(color_palette, list) and len(color_palette) >= 3:
                params["color_palette"] = color_palette
    elif model == LLMModel.QWEN_IMAGE_PLUS:
        params["prompt_extend"] = False
        params["watermark"] = False
        if negative_prompt:
            params["negative_prompt"] = negative_prompt
        if seed is not None:
            params["seed"] = seed
    else:
        params["prompt_extend"] = False
        if negative_prompt:
            params["negative_prompt"] = negative_prompt
        if seed is not None:
            params["seed"] = seed
    return params


def call_sync_image_api(
    model: str, prompt: str, size: str, negative_prompt: str, n: int, api_key: str,
    thinking_mode: Optional[bool] = None, enable_sequential: Optional[bool] = None,
    color_palette: Optional[list] = None, seed: Optional[int] = None,
) -> list:
    """
    调用同步端点 multimodal-generation/generation 生成图片，返回图片 URL 列表。

    chat 风格 messages 请求体；图片 URL 在 output.choices[].message.content[].image。
    n 由调用方按模型能力决定（wan2.7 传 batch_size 一次多张，其余传 1）。
    同步阻塞，由调用方包入 asyncio.to_thread。
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "input": {
            "messages": [{"role": "user", "content": [{"text": prompt}]}]
        },
        "parameters": build_sync_parameters(
            model, size, negative_prompt, n,
            thinking_mode, enable_sequential, color_palette, seed,
        ),
    }
    resp = requests.post(_SYNC_ENDPOINT_URL, headers=headers, json=payload, timeout=180)
    if resp.status_code != 200:
        try:
            err = resp.json()
        except ValueError:
            err = {"message": resp.text[:200]}
        err_msg = f"{err.get('code', '')} {err.get('message', '')}".strip()
        if resp.status_code >= 500 or resp.status_code == 429:
            raise requests.exceptions.HTTPError(
                f"通义万相同步生成失败({resp.status_code}): {err_msg}", response=resp
            )
        raise RuntimeError(f"通义万相同步生成失败({resp.status_code}): {err_msg}")

    data = resp.json()
    if data.get("code") and data.get("output") is None:
        raise RuntimeError(
            f"通义万相同步生成失败: {data.get('code', '')} {data.get('message', '')}"
        )
    urls = []
    for choice in data.get("output", {}).get("choices", []):
        for item in choice.get("message", {}).get("content", []):
            img = item.get("image", "")
            if img:
                urls.append(img)
    if not urls:
        raise RuntimeError(
            f"通义万相同步生成无图片URL: {json.dumps(data.get('output', {}), ensure_ascii=False)[:200]}"
        )
    return urls
