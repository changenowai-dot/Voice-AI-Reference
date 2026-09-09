"""Basisklasse und Datenstrukturen für TTS-Engines.

Es gibt genau EINE Produktions-Engine: Qwen3-TTS (Anforderung 2).
Der „TestDouble“ ist kein Produktions-/Fallback-Engine, sondern ein
deterministischer Offline-Prüfstand ausschließlich für automatisierte
Tests der Pipeline (Cache, Resume, QC, Batch …), wenn kein Modell
verfügbar ist (z. B. CI-Sandbox ohne GPU/RAM).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SynthesisRequest:
    text: str
    language: str                    # "German" | "English"
    speaker: str
    instruct: str = ""
    sampling: dict = field(default_factory=dict)
    seed: int = 0
    max_seconds_hint: float = 30.0
    speed: float = 1.0               # nur Info; Speed wird im Audio-Mastering gesetzt


@dataclass
class SynthesisResult:
    waveform: object                 # np.ndarray float32 mono
    sample_rate: int
    duration_s: float
    elapsed_s: float
    engine: str
    params_used: dict = field(default_factory=dict)

    @property
    def realtime_factor(self) -> float:
        return round(self.elapsed_s / max(self.duration_s, 1e-6), 3)


class TTSError(RuntimeError):
    pass


class EngineOOMError(TTSError):
    """CUDA-Out-of-Memory – kann mit kleineren Segmenten/Parametern
    wiederholt werden (Anforderung 72)."""


class TTSEngine:
    name: str = "base"

    def load(self) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def is_loaded(self) -> bool:  # pragma: no cover - abstract
        return False

    def unload(self) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        raise NotImplementedError

    def info(self) -> dict:
        return {"engine": self.name}
