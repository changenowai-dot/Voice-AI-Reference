"""Voice-Studio (Phase 2, §3): CustomVoice- UND VoiceDesign-Synthese.

VoiceDesign-Pipeline (long-form-sicher, nach offizieller Qwen3-TTS-
Empfehlung „Voice Design then Clone"):
  1. VoiceDesign-Modell erzeugt eine kurze Referenzaufnahme in der
     Ziel-Persona (Beschreibung A–F)
  2. Base-Modell baut daraus einen wiederverwendbaren Clone-Prompt
     (create_voice_clone_prompt)
  3. Alle Segmente werden über generate_voice_clone mit DEMSELBEN
     Prompt erzeugt -> maximale Langform-Konsistenz

Trade-off (dokumentiert, §22): Clone-Synthese trägt keinen Stil-Instruct
mehr; Prosodie-Kontrolle läuft dann über Textgestaltung (Normalisierung,
Kommata, Pausen, Segmentierung) + Sampling. Der A/B-Vergleich misst,
ob der Stimmgewinn das aufwiegt.

TestDoubleVoiceStudio ist der deterministische Prüfstand für Tests.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from .. import paths
from ..logging_setup import get_logger
from ..tts.engine_base import SynthesisRequest, SynthesisResult, TTSError

log = get_logger("voicestudio")


@dataclass
class VoiceRef:
    """Referenzaufnahme einer gestalteten Stimme (persistent speicherbar)."""
    candidate_id: str
    description: str
    ref_text: str
    wav_path: Path
    language: str = "German"


class BaseVoiceStudio:
    """Gemeinsame Schnittstelle für Produktion und Prüfstand."""
    name = "studio-base"

    def synth_customvoice(self, request: SynthesisRequest) -> SynthesisResult:
        raise NotImplementedError

    def design_reference(self, candidate_id: str, description: str,
                         language: str = "German") -> VoiceRef:
        raise NotImplementedError

    def build_clone_prompt(self, ref: VoiceRef):
        raise NotImplementedError

    def synth_clone(self, prompt, request: SynthesisRequest) -> SynthesisResult:
        raise NotImplementedError

    def info(self) -> dict:
        return {"studio": self.name}


# ===========================================================================
# Produktion: Qwen3-TTS (CustomVoice + VoiceDesign + Base via Modell-Pool)
# ===========================================================================
class QwenVoiceStudio(BaseVoiceStudio):
    name = "qwen-voicestudio"

    def __init__(self, pool):
        self.pool = pool
        self._clone_prompts: dict[str, object] = {}

    # -------------------------------------------------- CustomVoice -------
    def synth_customvoice(self, request: SynthesisRequest) -> SynthesisResult:
        import numpy as np
        import time
        model = self.pool.get("customvoice")
        import torch
        if request.seed:
            torch.manual_seed(request.seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(request.seed)
        gen_kwargs = dict(request.sampling or {})
        from .sampler import max_new_tokens_for
        gen_kwargs.setdefault("max_new_tokens",
                              max_new_tokens_for(request.max_seconds_hint))
        t0 = time.perf_counter()
        try:
            wavs, sr = model.generate_custom_voice(
                text=request.text, language=request.language,
                speaker=request.speaker,
                instruct=request.instruct or None, **gen_kwargs)
        except Exception as e:
            low = str(e).lower()
            if "out of memory" in low or "oom" in low:
                from .engine_base import EngineOOMError
                self.pool.unload()
                raise EngineOOMError(f"CUDA OOM: {e}") from e
            raise TTSError(f"VoiceStudio CustomVoice: {e}") from e
        wav = np.asarray(wavs[0] if isinstance(wavs, (list, tuple)) else wavs,
                         dtype=np.float32).reshape(-1)
        if wav.size == 0:
            raise TTSError("Leeres Audio zurückgegeben")
        return SynthesisResult(waveform=wav, sample_rate=int(sr),
                               duration_s=round(len(wav) / sr, 3),
                               elapsed_s=round(time.perf_counter() - t0, 3),
                               engine=self.name,
                               params_used={"seed": request.seed,
                                            "speaker": request.speaker})

    # -------------------------------------------------- VoiceDesign -------
    def design_reference(self, candidate_id: str, description: str,
                         language: str = "German") -> VoiceRef:
        """Schritt 1+2: Referenz klängen (VoiceDesign) und speichern."""
        import numpy as np
        from ..prosody.instruct import VOICEDESIGN_REF_TEXT_DE
        from .sampler import params_for_set
        from ..audio.io import write_wav
        model = self.pool.get("voicedesign")
        ref_text = VOICEDESIGN_REF_TEXT_DE
        res = None
        last_err: Exception | None = None
        for attempt in range(1, 4):
            import torch
            torch.manual_seed(5100 + attempt * 7)
            try:
                wavs, sr = model.generate_voice_design(
                    text=ref_text, language=language, instruct=description,
                    **params_for_set("balanced"))
                res = (wavs[0] if isinstance(wavs, (list, tuple)) else wavs, sr)
                break
            except Exception as e:                     # noqa: BLE001
                last_err = e
                log.warning("VoiceDesign-Versuch %d fehlgeschlagen: %s",
                            attempt, e)
        if res is None:
            raise TTSError(f"VoiceDesign schlug fehl: {last_err}")
        wav, sr = res
        wav = np.asarray(wav, dtype=np.float32).reshape(-1)
        paths.VOICE_REFS_DIR.mkdir(parents=True, exist_ok=True)
        out = paths.VOICE_REFS_DIR / f"{candidate_id}.wav"
        write_wav(out, wav, int(sr), bit_depth=16)
        log.info("VoiceDesign-Referenz %s -> %s (%.1f s)", candidate_id,
                 out, len(wav) / sr)
        return VoiceRef(candidate_id=candidate_id, description=description,
                        ref_text=ref_text, wav_path=out, language=language)

    def build_clone_prompt(self, ref: VoiceRef):
        """Schritt 2: wiederverwendbarer Clone-Prompt (Base-Modell)."""
        key = f"{ref.candidate_id}:{ref.wav_path.stat().st_mtime}"
        if key in self._clone_prompts:
            return self._clone_prompts[key]
        model = self.pool.get("base")
        prompt = model.create_voice_clone_prompt(
            ref_audio=str(ref.wav_path), ref_text=ref.ref_text,
            x_vector_only_mode=False)
        self._clone_prompts[key] = prompt
        log.info("Clone-Prompt gebaut: %s", ref.candidate_id)
        return prompt

    # -------------------------------------------------- Clone-Synthese ----
    def synth_clone(self, prompt, request: SynthesisRequest) -> SynthesisResult:
        import numpy as np
        import time
        model = self.pool.get("base")
        import torch
        if request.seed:
            torch.manual_seed(request.seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(request.seed)
        gen_kwargs = dict(request.sampling or {})
        from .sampler import max_new_tokens_for
        gen_kwargs.setdefault("max_new_tokens",
                              max_new_tokens_for(request.max_seconds_hint))
        t0 = time.perf_counter()
        try:
            wavs, sr = model.generate_voice_clone(
                text=request.text, language=request.language,
                voice_clone_prompt=prompt, **gen_kwargs)
        except Exception as e:
            low = str(e).lower()
            if "out of memory" in low or "oom" in low:
                from .engine_base import EngineOOMError
                self.pool.unload()
                raise EngineOOMError(f"CUDA OOM: {e}") from e
            raise TTSError(f"VoiceStudio Clone: {e}") from e
        wav = np.asarray(wavs[0] if isinstance(wavs, (list, tuple)) else wavs,
                         dtype=np.float32).reshape(-1)
        if wav.size == 0:
            raise TTSError("Leeres Audio zurückgegeben")
        return SynthesisResult(waveform=wav, sample_rate=int(sr),
                               duration_s=round(len(wav) / sr, 3),
                               elapsed_s=round(time.perf_counter() - t0, 3),
                               engine=self.name,
                               params_used={"seed": request.seed,
                                            "clone": True})


# ===========================================================================
# Prüfstand: deterministische TestDouble-Implementierung (nur für Tests)
# ===========================================================================
class TestDoubleVoiceStudio(BaseVoiceStudio):
    name = "testdouble-voicestudio"

    def __init__(self):
        from .test_double import TestDoubleEngine
        self._engines: dict[str, TestDoubleEngine] = {}

    def _engine_for(self, key: str) -> TestDoubleEngine:
        if key not in self._engines:
            from .test_double import TestDoubleEngine
            self._engines[key] = TestDoubleEngine()
        return self._engines[key]

    def synth_customvoice(self, request: SynthesisRequest) -> SynthesisResult:
        return self._engine_for("cv").synthesize(request)

    def design_reference(self, candidate_id: str, description: str,
                         language: str = "German") -> VoiceRef:
        import numpy as np
        from ..audio.io import write_wav
        from ..prosody.instruct import VOICEDESIGN_REF_TEXT_DE
        # deterministische "Stimme" aus der Beschreibung
        digest = hashlib.sha256(description.encode()).hexdigest()[:8]
        speaker_key = f"VD{int(digest[:4], 16) % 97}"
        req = SynthesisRequest(text=VOICEDESIGN_REF_TEXT_DE, language=language,
                               speaker=speaker_key, seed=5100)
        res = self._engine_for(f"vd:{speaker_key}").synthesize(req)
        paths.VOICE_REFS_DIR.mkdir(parents=True, exist_ok=True)
        out = paths.VOICE_REFS_DIR / f"{candidate_id}.wav"
        write_wav(out, res.waveform, res.sample_rate, bit_depth=16)
        return VoiceRef(candidate_id=candidate_id, description=description,
                        ref_text=VOICEDESIGN_REF_TEXT_DE, wav_path=out,
                        language=language)

    def build_clone_prompt(self, ref: VoiceRef):
        # Prüfstand: Prompt = (Engine-Key, Referenz-Wellenform-Statistik)
        from ..audio.io import read_wav
        wav, sr = read_wav(ref.wav_path)
        digest = hashlib.sha256(wav.tobytes()).hexdigest()[:8]
        return ("clone", f"{ref.candidate_id}:{digest}")

    def synth_clone(self, prompt, request: SynthesisRequest) -> SynthesisResult:
        key = prompt[1]
        req = SynthesisRequest(text=request.text,
                               language=request.language,
                               speaker=key,           # gleiche Stimme!
                               instruct=request.instruct,
                               sampling=request.sampling,
                               seed=request.seed,
                               max_seconds_hint=request.max_seconds_hint)
        return self._engine_for(key).synthesize(req)
