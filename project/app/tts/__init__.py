from .engine_base import (EngineOOMError, SynthesisRequest, SynthesisResult,  # noqa: F401
                          TTSError, TTSEngine)
from .sampler import PARAM_SETS, max_new_tokens_for, params_for_set, variation_for_attempt  # noqa: F401


def create_engine(engine_name: str, **kwargs):
    """Factory. Produktions-Engine ist ausschließlich Qwen3-TTS.
    Der TestDouble ist nur für automatisierte Tests."""
    if engine_name == "test_double":
        from .test_double import TestDoubleEngine
        return TestDoubleEngine()
    if engine_name in ("qwen", "qwen3-tts", "qwen3_tts-customvoice", ""):
        from .qwen_engine import QwenTTSEngine
        return QwenTTSEngine(**kwargs)
    raise ValueError(f"Unbekannte Engine: {engine_name!r}")
