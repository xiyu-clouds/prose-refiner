"""通义 TTS 合成 —— CosyVoice / Sambert 系列模型调用与结果校验。

从 routers/audios.py 提取，保持行为完全一致。
被 domain/audios/tts_generator.py 和 routers/audios.py（refine_image_prompt 间接）引用。
"""


class TTSResultError(RuntimeError):
    """TTS 返回结果异常（空音频、HTTP 业务错误码等），归类为可重试异常。"""
    pass


_MIN_AUDIO_BYTES = 128  # 小于 128B 视为空音频/截断，触发重试


def synthesize_tongyi_tts(model: str, voice: str, text: str) -> bytes:
    """
    调用通义 TTS 合成音频（同步阻塞，由调用方包入 asyncio.to_thread）。

    按模型系列分发到对应 DashScope SDK：
      - CosyVoice 系列 → tts_v2.SpeechSynthesizer.call(text) 返回 bytes
      - Sambert 系列   → tts.SpeechSynthesizer.call(model, text, voice=...) 返回 result.get_audio_data()

    额外防御：
      - 校验 DashScope 结果对象的 status_code（非 2000000 视为业务失败）
      - 校验返回字节长度（< _MIN_AUDIO_BYTES 视为空音频/截断）
      - 以上两种情况抛出 TTSResultError（归属于可重试异常）
    """
    if model.startswith("cosyvoice"):
        from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat
        synthesizer = SpeechSynthesizer(
            model=model,
            voice=voice,
            format=AudioFormat.MP3_22050HZ_MONO_256KBPS,
        )
        result = synthesizer.call(text)
        # CosyVoice: .call 直接返回 bytes
        if result is None:
            raise TTSResultError("CosyVoice 返回 None")
        if not isinstance(result, (bytes, bytearray)):
            # 部分版本返回 Result 对象时，优先查 status_code
            sc = getattr(result, "status_code", None)
            if sc is not None and str(sc) != "2000000":
                msg = getattr(result, "message", None) or getattr(result, "output", None) or str(result)
                raise TTSResultError(f"CosyVoice 业务失败: status_code={sc}, message={msg}")
            audio_bytes = getattr(result, "get_audio_data", lambda: None)() if hasattr(result, "get_audio_data") else None
            if not audio_bytes:
                raise TTSResultError("CosyVoice 返回音频数据为空")
            result = audio_bytes
        if len(result) < _MIN_AUDIO_BYTES:
            raise TTSResultError(f"CosyVoice 音频数据过小: {len(result)} bytes")
        return bytes(result)
    elif model.startswith("sambert"):
        from dashscope.audio.tts import SpeechSynthesizer
        # Sambert: 每个音色即独立模型，voice ID 为完整模型名（如 sambert-betty-v1）
        actual_model = voice if voice.startswith("sambert") else model
        result = SpeechSynthesizer.call(
            model=actual_model,
            text=text,
            format='mp3',
            sample_rate=16000,
        )
        sc = getattr(result, "status_code", None)
        if sc is not None and str(sc) != "2000000":
            msg = getattr(result, "message", None) or getattr(result, "output", None) or str(result)
            request_id = getattr(result, "request_id", None)
            raise TTSResultError(
                f"Sambert 业务失败: status_code={sc}, message={msg}, request_id={request_id}"
            )
        audio_bytes = None
        gae = getattr(result, "get_audio_data", None)
        if callable(gae):
            audio_bytes = gae()
        if audio_bytes is None:
            output = getattr(result, "output", None)
            if isinstance(output, dict):
                audio_bytes = output.get("audio_data") or output.get("audio")
        if not audio_bytes or len(audio_bytes) < _MIN_AUDIO_BYTES:
            request_id = getattr(result, "request_id", None)
            raise TTSResultError(
                f"Sambert 返回音频数据为空或过小: size={len(audio_bytes) if audio_bytes else 0} bytes, request_id={request_id}"
            )
        return bytes(audio_bytes)
    raise ValueError(f"不支持的 TTS 模型: {model}")
