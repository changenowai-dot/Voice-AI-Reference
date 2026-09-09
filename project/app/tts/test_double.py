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
        # Neue englische Teststimmen: gender-spezifische F0-Hebung
        sp = request.speaker.lower()
        if "female" in sp or "en_female" in sp:
            base_f0 += 55.0
            # weiblich calm 01 tiefer (warm_low), calm 02 heller (bright_calm)
            if "calm_02" in sp or "bright" in sp:
                base_f0 += 12.0
        if "calm_deep" in sp:
            base_f0 = 85.0 + (seed % 300) / 10.0      # 85–115 Hz calm deep, low+clear
        elif "warm_storytelling" in sp:
            base_f0 = 95.0 + (seed % 300) / 10.0      # 95–125 Hz warm storytelling authoritative
        elif "male_deep_01" in sp:
            base_f0 = 88.0 + (seed % 300) / 10.0      # 88–118 Hz tiefster
        elif "male_deep_02" in sp:
            base_f0 = 102.0 + (seed % 300) / 10.0     # 102–132 Hz warm

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
    wird respektiert, Sprecher-Wechsel ausgeschlossen (§3).

    Für VD-E gilt strikter Lock; für neue Teststimmen (en_male_deep_*
    etc.) wird die voice_id als deterministischer Sprecher-Schlüssel
    verwendet, Referenzpfad ist per voice_id unterscheidbar und
    allow_design hat pro Stimme eigene Semantik.
    """

    name = "test-double-clone"
    ENGINE_VERSION = "td-clone-v1"

    def __init__(self, sample_rate: int = 24000, allow_design: bool = True,
                 voice_id: str | None = None, candidate_id: str | None = None):
        super().__init__(sample_rate)
        self.allow_design = allow_design
        # voice_id bzw. candidate_id steuert die deterministische „Stimme“
        self.voice_id = voice_id or candidate_id or "VD-E"
        # legacy _speaker_key für Kompatibilität
        if self.voice_id == "VD-E" or self.voice_id == "vd_e":
            self._speaker_key = "VD-E-TEST"
        else:
            # Hash-basierter aber unterschiedlicher F0-Hash je Stimme
            # en_male_deep_01 -> tiefer F0 (100-120), en_female_calm_02 -> höher (165-195)
            self._speaker_key = f"TEST-{self.voice_id.upper()}"
        self.candidate_id = candidate_id or voice_id

    def load(self) -> None:
        from .. import paths
        # VD-E strikt locked; andere Stimmen dürfen im Prüfstand ohne Datei laden
        # (echte Produktion prüft Datei-Existenz separat in jobs/runner)
        if not self.allow_design and self.voice_id in ("VD-E", "vd_e", "VD-E-TEST"):
            ref = paths.VOICE_REFS_DIR / "VD-E.wav"
            if not ref.exists():
                from .engine_base import TTSError
                raise TTSError(
                    f"VD-E-Referenz fehlt: {ref}. Neuerzeugung gesperrt "
                    "(LOCKED PRODUCTION, §12/§24).")
        if not self.allow_design and self.voice_id.startswith("en_"):
            # Für en_* Clone-Teststimmen: Referenz sollte existieren, aber im Prüfstand
            # erlauben wir fehlende Datei (deterministische Synthese ohne Prompt)
            # – Produktion (jobs/runner) prüft strikter.
            pass
        self._loaded = True

    def synthesize(self, request):
        req = SynthesisRequest(
            text=request.text, language=request.language,
            speaker=self._speaker_key,       # Identität konstant je Stimme
            instruct=request.instruct,
            sampling=request.sampling, seed=request.seed,
            max_seconds_hint=request.max_seconds_hint)
        return super().synthesize(req)
