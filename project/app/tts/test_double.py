"""TestDouble-Engine – KEIN Produktionsersatz (Anforderung 2!).

Deterministischer Offline-Prüfstand ausschließlich für automatisierte
Tests (Tests A–Q) der umgebenden Pipeline: Segmentierung, Cache, Resume,
Batch, QC, Regeneration, Mastering. Erzeugt aus dem Text eine synthetische,
reproduzierbare „Sprach“-Welle (Silbenrhythmus + Tonhöhenkontur), damit
Audio-Analyse, Lautheitsmessung und Pauserkennung realistisch arbeiten
können. Wird nur aktiviert, wenn Tests dies explizit anfordern
(--engine test_double bzw. VOICEOVER_TEST_ENGINE=1).
"""
from __future__ import annotations

import hashlib
import math

import numpy as np

from .engine_base import SynthesisRequest, SynthesisResult, TTSEngine

ENGINE_NAME = "test-double"
ENGINE_VERSION = "td-v1"


class TestDoubleEngine(TTSEngine):
    name = ENGINE_NAME

    def __init__(self, sample_rate: int = 24000):
        self.sample_rate = sample_rate
        self._loaded = False

    def load(self) -> None:
        self._loaded = True

    def is_loaded(self) -> bool:
        return self._loaded

    def unload(self) -> None:
        self._loaded = False

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        self.load()
        t0_sim = 0.05
        words = request.text.split()
        # „Sprechtempo“: deutsche Dokumentarlesart ≈ 4,2 Silben/s
        # (Silben über Vokalgruppen genähert; entspricht der
        #  GermanScore-Erwartung und ~14 Zeichen/s)
        import re as _re
        syllables = sum(max(1, len(_re.findall(r"[aeiouäöüy]+",
                                               w.lower())))
                        for w in words)
        speaking_s = max(0.6, syllables / 4.2)
        sr = self.sample_rate
        n = int(speaking_s * sr)
        t = np.arange(n, dtype=np.float32) / sr

        # Grundstimme je nach Speaker (F0), deterministisch
        seed = int(hashlib.sha256(request.speaker.encode()).hexdigest()[:8], 16)
        base_f0 = 100.0 + (seed % 700) / 10.0          # 100–170 Hz
        if request.speaker in ("Serena", "Vivian", "Sohee", "Ono_Anna"):
            base_f0 += 60.0

        # Satzmelodie: leichter Abfall über das Segment + Fragemelodie
        progress = t / max(speaking_s, 1e-6)
        contour = 1.0 - 0.12 * progress
        if request.text.rstrip().endswith("?"):
            contour += 0.18 * np.clip((progress - 0.8) * 5.0, 0, 1)

        f0 = base_f0 * contour
        phase = 2 * np.pi * np.cumsum(f0) / sr
        wave = 0.6 * np.sin(phase).astype(np.float32)

        # Silbenpuls (Amplitudenmodulation ~4 Hz) für Rhythmus
        pulse = 0.55 + 0.45 * np.sin(2 * np.pi * 4.1 * t).astype(np.float32)
        # sanftes Attack/Release, kein Clipping
        env = np.minimum(1.0, np.minimum(t / 0.03, (speaking_s - t) / 0.05))
        env = np.clip(env, 0.0, 1.0).astype(np.float32)
        wav = np.clip(wave * pulse * env * 0.7, -0.95, 0.95).astype(np.float32)

        # kleine Sprechpausen (Stille) zwischen „Sätzen“
        for frac in (0.35, 0.7):
            i0 = int(n * frac)
            wav[i0: i0 + int(0.12 * sr)] *= 0.02

        duration = len(wav) / sr
        return SynthesisResult(
            waveform=wav, sample_rate=sr,
            duration_s=round(duration, 3), elapsed_s=t0_sim,
            engine=self.name,
            params_used={"speaker": request.speaker, "seed": request.seed,
                         "words": len(words)},
        )


class TestDoubleCloneEngine(TestDoubleEngine):
    """Prüfstand-Clone-Engine (VD-E-Pfad-Mechanik, §12): gleiche
    deterministische „Stimme“ für alle Segmente, allow_design=False
    wird respektiert, Sprecher-Wechsel ausgeschlossen (§3)."""

    name = "test-double-clone"
    ENGINE_VERSION = "td-clone-v1"

    def __init__(self, sample_rate: int = 24000, allow_design: bool = True):
        super().__init__(sample_rate)
        self.allow_design = allow_design
        self._speaker_key = "VD-E-TEST"

    def load(self) -> None:
        from .. import paths
        if not self.allow_design:
            ref = paths.VOICE_REFS_DIR / "VD-E.wav"
            if not ref.exists():
                from .engine_base import TTSError
                raise TTSError(
                    f"VD-E-Referenz fehlt: {ref}. Neuerzeugung gesperrt "
                    "(LOCKED PRODUCTION, §12/§24).")
        self._loaded = True

    def synthesize(self, request):
        req = SynthesisRequest(
            text=request.text, language=request.language,
            speaker=self._speaker_key,       # Identität konstant
            instruct=request.instruct,
            sampling=request.sampling, seed=request.seed,
            max_seconds_hint=request.max_seconds_hint)
        return super().synthesize(req)
