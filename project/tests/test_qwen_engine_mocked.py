"""Tests: QwenTTSEngine mit gemocktem qwen_tts/torch-Modul.

Prüft die echten Aufrufpfale der Produktions-Engine (Parameter, Fehler-
behandlung, OOM-Pfad), ohne Modell herunterladen zu müssen. Die
End-to-End-Verifikation auf echter Hardware übernimmt der
System-Benchmark (erster Start auf dem Zielsystem).
"""
from __future__ import annotations

import sys
import types


def _install_fakes():
    """Minimal-Torch + qwen_tts-Fakes in sys.modules legen."""
    torch = types.ModuleType("torch")

    class _DType:
        def __init__(self, name):
            self.name = name

        def __repr__(self):
            return f"torch.{self.name}"

    torch.bfloat16 = _DType("bfloat16")
    torch.float32 = _DType("float32")
    torch.float16 = _DType("float16")

    cuda = types.ModuleType("torch.cuda")
    cuda.is_available = lambda: False
    cuda.manual_seed_all = lambda s: None
    cuda.empty_cache = lambda: None
    torch.cuda = cuda
    torch.manual_seed = lambda s: None

    calls = {"from_pretrained": [], "generate": [], "unload": 0}

    import numpy as np

    class FakeModel:
        def __init__(self):
            self.loaded_via = None

        @classmethod
        def from_pretrained(cls, path, **kwargs):
            calls["from_pretrained"].append((path, kwargs))
            if kwargs.get("device_map") == "cuda:0" and \
                    kwargs.get("_fail_gpu", False):
                raise RuntimeError("CUDA error: out of memory during load")
            m = cls()
            m.loaded_via = (path, kwargs)
            return m

        def get_supported_speakers(self):
            return ["aiden", "ryan", "serena", "uncle_fu", "vivian",
                    "sohee", "ono_anna", "dylan", "eric"]

        def get_supported_languages(self):
            return ["chinese", "english", "german", "french"]

        def generate_custom_voice(self, text, language, speaker,
                                  instruct=None, **kwargs):
            import numpy as np
            calls["generate"].append({"text": text, "language": language,
                                      "speaker": speaker, "instruct": instruct,
                                      "kwargs": kwargs})
            if kwargs.get("_boom") == "oom":
                raise RuntimeError("CUDA out of memory. Tried to allocate ...")
            if kwargs.get("_boom") == "empty":
                return [np.zeros(0, dtype=np.float32)], 24000
            dur = max(1.0, len(text) / 200.0)
            t = np.linspace(0, dur, int(dur * 24000), dtype=np.float32)
            return [0.5 * np.sin(2 * np.pi * 120 * t).astype(np.float32)], 24000

    qwen_tts = types.ModuleType("qwen_tts")
    qwen_tts.Qwen3TTSModel = FakeModel
    sys.modules.setdefault("torch", torch)
    sys.modules["qwen_tts"] = qwen_tts
    return calls


def test_engine_synthesize_passes_correct_args():
    calls = _install_fakes()
    from app.hardware.detector import HardwareInfo
    from app.tts.engine_base import SynthesisRequest
    from app.tts.qwen_engine import QwenTTSEngine

    hw = HardwareInfo()
    hw.mode = "cpu"
    eng = QwenTTSEngine(hw, model_size="1.7B")
    eng.load()
    path, kwargs = calls["from_pretrained"][-1]
    assert "1.7B-CustomVoice" in path
    assert kwargs["device_map"] == "cpu"

    res = eng.synthesize(SynthesisRequest(
        text="Ein Testsatz für die Engine.", language="German",
        speaker="Ryan", instruct="Speak calmly.",
        sampling={"temperature": 0.7, "top_k": 50, "max_new_tokens": 500},
        seed=1234))
    assert res.sample_rate == 24000
    assert res.duration_s > 0.5
    g = calls["generate"][-1]
    assert g["text"] == "Ein Testsatz für die Engine."
    assert g["language"] == "German"
    assert g["speaker"] == "Ryan"
    assert g["instruct"] == "Speak calmly."
    assert g["kwargs"]["temperature"] == 0.7
    assert g["kwargs"]["max_new_tokens"] == 500
    assert res.params_used["seed"] == 1234
    assert res.engine.startswith("qwen3-tts")


def test_engine_oom_raises_special_error():
    calls = _install_fakes()
    from app.hardware.detector import HardwareInfo
    from app.tts.engine_base import EngineOOMError, SynthesisRequest
    from app.tts.qwen_engine import QwenTTSEngine

    hw = HardwareInfo()
    hw.mode = "cpu"
    eng = QwenTTSEngine(hw, model_size="0.6B")
    eng.load()
    try:
        eng.synthesize(SynthesisRequest(
            text="Text", language="German", speaker="Ryan",
            sampling={"_boom": "oom"}))
        raised = False
    except EngineOOMError:
        raised = True
    assert raised


def test_engine_empty_audio_raises():
    calls = _install_fakes()
    from app.hardware.detector import HardwareInfo
    from app.tts.engine_base import SynthesisRequest, TTSError
    from app.tts.qwen_engine import QwenTTSEngine

    hw = HardwareInfo()
    hw.mode = "cpu"
    eng = QwenTTSEngine(hw, model_size="1.7B")
    eng.load()
    try:
        eng.synthesize(SynthesisRequest(
            text="Text", language="German", speaker="Ryan",
            sampling={"_boom": "empty"}))
        raised = False
    except TTSError:
        raised = True
    assert raised


def test_engine_unload_safe_without_cuda():
    _install_fakes()
    from app.hardware.detector import HardwareInfo
    from app.tts.qwen_engine import QwenTTSEngine
    hw = HardwareInfo()
    hw.mode = "cpu"
    eng = QwenTTSEngine(hw, model_size="1.7B")
    eng.load()
    eng.unload()          # darf ohne CUDA nicht crashen
    assert not eng.is_loaded()


def test_missing_package_clear_error():
    calls = _install_fakes()
    saved = sys.modules.pop("qwen_tts", None)     # Fake entfernen
    try:
        from app.hardware.detector import HardwareInfo
        from app.tts.engine_base import TTSError
        from app.tts.qwen_engine import QwenTTSEngine
        hw = HardwareInfo()
        hw.mode = "cpu"
        eng = QwenTTSEngine(hw, model_size="1.7B")
        try:
            eng.load()
            raised = False
        except TTSError as e:
            raised = True
            assert "qwen-tts" in str(e)
        assert raised
    finally:
        if saved:
            sys.modules["qwen_tts"] = saved
