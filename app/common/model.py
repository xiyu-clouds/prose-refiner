"""
模型名称常量
⚠️ 仅保留当前业务在使用的模型名，废弃模型不做兜底。
"""

# -------------------- DeepSeek（文本，LangChain 执行器）--------------------
# V4 Flash（默认，速度/性价比最优）
MODEL_DEEPSEEK_V4_FLASH = "deepseek-v4-flash"

# V4 Pro（最强能力：全文级润色、元认知、复杂推理）
MODEL_DEEPSEEK_V4_PRO = "deepseek-v4-pro"

# -------------------- 通义千问（文本，DashScope OpenAI 兼容端点）--------------------
MODEL_QWEN3_7_MAX = "qwen3.7-max"
MODEL_QWEN3_7_PLUS = "qwen3.7-plus"
MODEL_QWEN3_7_FLASH = "qwen3.7-flash"
# Qwen3.8 Max（新一代最强主力，全文级与元认知场景）
MODEL_QWEN3_8_MAX = "qwen3.8-max"

# -------------------- 通义 CosyVoice（语音合成系列，DashScope 原生 API）--------------------
MODEL_COSYVOICE_V1 = "cosyvoice-v1"
MODEL_COSYVOICE_V2 = "cosyvoice-v2"
MODEL_COSYVOICE_V3_PLUS = "cosyvoice-v3-plus"
MODEL_COSYVOICE_V3_FLASH = "cosyvoice-v3-flash"

# -------------------- 通义 Sambert（早期语音合成系列，稳定可靠）--------------------
# 模型值为 "sambert"，实际调用时根据用户选择的音色 ID（如 sambert-betty-v1）作为真实模型名传递
MODEL_SAMBERT = "sambert"

# -------------------- 通义万相（文生图系列，DashScope 异步任务 API）--------------------
MODEL_Z_IMAGE_TURBO = "z-image-turbo"
MODEL_WANX2_7_IMAGE = "wan2.7-image"
MODEL_QWEN_IMAGE_PLUS = "qwen-image-plus"
