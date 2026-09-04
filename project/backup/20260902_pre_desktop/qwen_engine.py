"""Qwen3-TTS-Engine – die einzige Produktions-Engine (Anforderung 2).

Kapselt das `qwen_tts`-Paket (Qwen3TTSModel):
- lazy Import & Modell-Ladung (0.6B/1.7B CustomVoice)
- device/dtype je nach Hardware-Modus (GPU bf16 / CPU fp32)
- deterministische Seeds pro Segment (Reproduzierbarkeit + Variation)
- Sampling-Parameter (Anforderung 49)
- OOM-Behandlung mit klarer Fehlerklasse für Retry-Logik (Anforderung 72)
- VRAM-Schutz über VRAMGuard

Die Modellauswahl 0.6B vs. 1.7B trifft der System-Benchmark (Anf. 48):
1.7B liefert deutlich bessere Deutsch-Qualität (WER 0.634 vs. 0.990 lt.
Modellkarte) und passt in 8 GB VRAM; 0.6B ist der CPU-/Notfallpfad.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from ..hardware.detector import HardwareInfo
from ..logging_setup import Timer, get_logger
from .engine_base import (EngineOOMError, SynthesisRequest, SynthesisResult,
                          TTSError, TTSEngine)
from .sampler import max_new_tokens_for

log = get_logger("tts.qwen")

ENGINE_NAME = "qwen3-tts-customvoice"
ENGINE_VERSION = "qwen-tts-0.1.1+app1"


class QwenTTSEngine(TTSEngine):
    name = ENGINE_NAME

    def __init__(self, hw: HardwareInfo, model_size: str = "1.7B",
                 models_dir: Path | None = None, dtype_hint: str | None = None,
                 device_hint: str | None = None,
                 attn_implementation: str | None = None):
        from .. import paths
        self.hw = hw
        self.attn_implementation = attn_implementation  # z. B. "sdpa"
        self.model_size = model_size if model_size in ("0.6B", "1.7B") else "1.7B"
        self.repo_id = {
            "1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
            "0.6B": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
        }[self.model_size]
        self.models_dir = Path(models_dir) if models_dir else paths.MODELS_DIR
        self.device_hint = device_hint
        self.dtype_hint = dtype_hint
        self._model = None
        self._model_path: str | None = None
        self._sample_rate: int | None = None

    # ------------------------------------------------------------------ Laden
    def _resolve_model_path(self) -> str:
        """Lokales Verzeichnis (falls vorab heruntergeladen) sonst Repo-ID."""
        local = self.models_dir / self.repo_id.split("/")[-1]
        if (local / "config.json").exists():
            return str(local)
        return self.repo_id

    def load(self) -> None:
        if self._model is not None:
            return
        import torch  # lokale Abhängigkeit, erst hier importieren

        try:
            from qwen_tts import Qwen3TTSModel
        except ImportError as e:
            raise TTSError(
                "Das Python-Paket 'qwen-tts' ist nicht installiert. "
                "Bitte install.ps1 ausführen." ) from e

        use_gpu = (self.device_hint == "cuda") or (
            self.device_hint is None and self.hw.mode.startswith("gpu"))
        dtype = torch.bfloat16 if (use_gpu and (
            self.dtype_hint == "bfloat16" or self.dtype_hint is None)
        ) else torch.float32
        if use_gpu and self.hw.device_capability is not None:
            # bf16 braucht Ampere+; ältere Karten -> fp16
            if tuple(self.hw.device_capability) < (8, 0):
                dtype = torch.float16

        path = self._resolve_model_path()
        log.info("Lade Qwen3-TTS %s (%s) auf %s (%s, attn=%s)",
                 self.model_size, path,
                 "CUDA" if use_gpu else "CPU", str(dtype),
                 self.attn_implementation or "sdpa(default)")
        load_kwargs = dict(
            device_map="cuda:0" if use_gpu else "cpu",
            dtype=dtype,
        )
        if self.attn_implementation:
            load_kwargs["attn_implementation"] = self.attn_implementation
        t0 = time.perf_counter()
        try:
            self._model = Qwen3TTSModel.from_pretrained(path, **load_kwargs)
        except MemoryError as e:
            raise EngineOOMError(f"Modellladung: RAM/VRAM zu klein: {e}") from e
        except Exception as e:
            msg = str(e)
            if "out of memory" in msg.lower() or "oom" in msg.lower():
                raise EngineOOMError(f"CUDA OOM beim Laden: {msg}") from e
            if use_gpu:
                log.warning("GPU-Ladung fehlgeschlagen (%s) – versuche CPU", msg)
                self._model = Qwen3TTSModel.from_pretrained(
                    path, device_map="cpu", dtype=torch.float32)
            else:
                raise TTSError(f"Modell konnte nicht geladen werden: {e}") from e
        load_s = time.perf_counter() - t0
        log.info("Modell geladen in %.1f s", load_s)
        try:
            speakers = self._model.get_supported_speakers() or []
            log.info("Unterstützte Speaker: %s", speakers)
        except Exception:
            pass

    def is_loaded(self) -> bool:
        return self._model is not None

    def unload(self) -> None:
        if self._model is None:
            return
        import gc
        import torch
        self._model = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        log.info("Modell entladen")

    # -------------------------------------------------------------- Synthese
    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        import numpy as np

        self.load()
        import torch

        # deterministischer Seed pro Anfrage (Reproduzierbarkeit)
        if request.seed:
            torch.manual_seed(request.seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(request.seed)

        gen_kwargs = dict(request.sampling or {})
        gen_kwargs.setdefault("max_new_tokens",
                              max_new_tokens_for(request.max_seconds_hint))

        log.debug("Synthese: %d Zeichen, speaker=%s, seed=%s, kwargs=%s",
                  len(request.text), request.speaker, request.seed, gen_kwargs)
        t0 = time.perf_counter()
        try:
            wavs, sr = self._model.generate_custom_voice(
                text=request.text,
                language=request.language,
                speaker=request.speaker,
                instruct=request.instruct or None,
                **gen_kwargs,
            )
        except Exception as e:
            msg = str(e)
            low = msg.lower()
            if "out of memory" in low or "oom" in low or "alloc" in low:
                self._cuda_cleanup()
                raise EngineOOMError(f"CUDA OOM bei Synthese: {msg}") from e
            raise TTSError(f"Qwen3-TTS Synthese fehlgeschlagen: {msg}") from e
        elapsed = time.perf_counter() - t0

        wav = wavs[0] if isinstance(wavs, (list, tuple)) and wavs else wavs
        wav = np.asarray(wav, dtype=np.float32).reshape(-1)
        if wav.size == 0:
            raise TTSError("Leeres Audio zurückgegeben")
        duration = float(len(wav) / sr)
        self._sample_rate = int(sr)
        return SynthesisResult(
            waveform=wav,
            sample_rate=int(sr),
            duration_s=round(duration, 3),
            elapsed_s=round(elapsed, 3),
            engine=self.name,
            params_used={"gen_kwargs": gen_kwargs, "seed": request.seed,
                         "speaker": request.speaker, "instruct": request.instruct,
                         "language": request.language},
        )

    @property
    def sample_rate(self) -> int | None:
        return self._sample_rate

    def _cuda_cleanup(self) -> None:
        try:
            import gc
            import torch
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def info(self) -> dict:
        return {
            "engine": self.name,
            "engine_version": ENGINE_VERSION,
            "model_size": self.model_size,
            "repo": self.repo_id,
            "loaded": self.is_loaded(),
            "hardware_mode": self.hw.mode,
        }


# ===========================================================================
# Phase 2: Clone-Engine für production VoiceDesign-Stimmen
# ===========================================================================
class VoiceCloneEngine(TTSEngine):
    """Produktions-Engine für eine gestaltete (VoiceDesign-)Stimme.

    Lädt die persistent gespeicherte Referenz aus cache/voice_refs/
    (oder erzeugt sie einmalig mit dem VoiceDesign-Modell) und baut den
    wiederverwendbaren Clone-Prompt auf dem Base-Modell. Alle Segmente
    laufen mit demselben Prompt -> maximale Langform-Konsistenz.
    """
    name = "qwen3-tts-clone"
    ENGINE_VERSION_CLONE = "qwen-voicestudio-v1"

    def __init__(self, hw: HardwareInfo, candidate_id: str,
                 description: str, models_dir: Path | None = None,
                 attn_implementation: str | None = None):
        from .model_pool import QwenModelPool
        from .voice_studio import QwenVoiceStudio
        self.hw = hw
        self.candidate_id = candidate_id
        self.description = description
        self.pool = QwenModelPool(hw, models_dir=models_dir,
                                  attn_implementation=attn_implementation)
        self.studio = QwenVoiceStudio(self.pool)
        self._prompt = None
        self._ref = None

    def _ensure_prompt(self):
        if self._prompt is not None:
            return
        from .. import paths
        from .voice_studio import VoiceRef
        ref_path = paths.VOICE_REFS_DIR / f"{self.candidate_id}.wav"
        if ref_path.exists():
            from ..prosody.instruct import VOICEDESIGN_REF_TEXT_DE
            self._ref = VoiceRef(candidate_id=self.candidate_id,
                                 description=self.description,
                                 ref_text=VOICEDESIGN_REF_TEXT_DE,
                                 wav_path=ref_path)
        else:
            self._ref = self.studio.design_reference(
                self.candidate_id, self.description)
        self._prompt = self.studio.build_clone_prompt(self._ref)

    def load(self) -> None:
        self._ensure_prompt()

    def is_loaded(self) -> bool:
        return self._prompt is not None

    def unload(self) -> None:
        self._prompt = None
        self.pool.unload()

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        self._ensure_prompt()
        return self.studio.synth_clone(self._prompt, request)

    def info(self) -> dict:
        return {
            "engine": self.name,
            "engine_version": self.ENGINE_VERSION_CLONE,
            "model_size": "1.7B",
            "repo": "VoiceDesign->Base-Clone",
            "loaded": self.is_loaded(),
            "hardware_mode": self.hw.mode,
            "candidate_id": self.candidate_id,
        }
