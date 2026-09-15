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
from .rng import set_deterministic_seed
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
        # Sicherstellen, dass Dropout/NN-Dropout-RNGs nicht im Train-Modus
        # laufen (sonst variieren mehrere identisch geseedete Aufrufe
        # je nach internem Zustand und erzeugen 0.16-s-/Silence-Artefakte).
        try:
            self._model.eval()
        except Exception:
            pass
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

        # Deterministischer Seed (CPU + alle CUDA-Geräte + passender
        # torch.Generator). Siehe app.tts.rng für die Begründung.
        if request.seed is not None:
            gen = set_deterministic_seed(int(request.seed))
        else:
            gen = None

        gen_kwargs = dict(request.sampling or {})
        gen_kwargs.setdefault("max_new_tokens",
                              max_new_tokens_for(request.max_seconds_hint))

        # Wenn die zugrundeliegende generate()-Methode einen ``generator=``
        # unterstützt (transformers/accelerate tun das), übergeben wir
        # unseren explizit gesetzten Generator. Sonst still ignorieren.
        import inspect as _insp
        try:
            _gen_fn = self._model.generate_custom_voice
            if "generator" in _insp.signature(_gen_fn).parameters and gen is not None:
                gen_kwargs["generator"] = gen
        except Exception:
            pass

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
        # CUDA synchronisieren, damit RNG-/Kernel-Zustände nicht in den
        # nächsten Versuch hinüberleaken.
        if torch.cuda.is_available():
            try:
                torch.cuda.synchronize()
            except Exception:
                pass
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
                 attn_implementation: str | None = None,
                 allow_design: bool = False,
                 reference_path: Path | None = None,
                 language: str = "German",
                 ref_text: str | None = None,
                 seed: int | None = None):
        """allow_design=False (PRODUCTION DEFAULT, §12): die
        Referenzdatei MUSS vorhanden sein – niemals stumm neu designen.

        Nur der explizite Materialisierungspfad (tools/materialize_references.py)
        setzt allow_design=True via VOICEOVER_ALLOW_VOICEDESIGN_MATERIALIZE=1.

        reference_path: Optional explicit override for the reference WAV path.
        If None, uses default paths.VOICE_REFS_DIR / f"{candidate_id}.wav".

        language: "German" oder "English" — wählt den passenden
                  Standard-Referenztext für create_voice_clone_prompt.
        ref_text: Optional canonical reference text. When provided it MUST
                  match the actual spoken content of reference_path exactly.
                  If None, resolved from language via VOICEDESIGN_REF_TEXT_*.
        seed:     Optionaler Seed für die VoiceDesign-Referenzgenerierung.
        """
        log.debug("[DIAG-D.1] VoiceCloneEngine.__init__() entered")
        
        log.debug("[DIAG-F] Importing QwenModelPool")
        from .model_pool import QwenModelPool
        log.debug("[DIAG-F] Importing QwenVoiceStudio")
        from .voice_studio import QwenVoiceStudio
        
        self.hw = hw
        self.candidate_id = candidate_id
        self.description = description
        self.allow_design = allow_design
        self.reference_path = reference_path  # Test harness override
        self._language = language
        self._ref_text_override = ref_text
        self._design_seed = seed
        
        log.debug("[DIAG-F] Creating QwenModelPool (models_dir=%s)", models_dir)
        self.pool = QwenModelPool(hw, models_dir=models_dir,
                                  attn_implementation=attn_implementation)
        log.debug("[DIAG-F] QwenModelPool created")
        
        log.debug("[DIAG-G] Creating QwenVoiceStudio")
        self.studio = QwenVoiceStudio(self.pool)
        log.debug("[DIAG-G] QwenVoiceStudio created")
        
        self._prompt = None
        self._ref = None
        log.debug("[DIAG-D.2] VoiceCloneEngine.__init__() completed")

    def _ensure_prompt(self):
        if self._prompt is not None:
            return
        from .. import paths
        from .voice_studio import VoiceRef
        from ..prosody.instruct import (VOICEDESIGN_REF_TEXT_DE,
                                        VOICEDESIGN_REF_TEXT_EN)
        # Use explicit override if provided (test harness/runtime reference),
        # otherwise fall back to default cache location
        if self.reference_path is not None:
            ref_path = Path(self.reference_path)
        else:
            ref_path = paths.VOICE_REFS_DIR / f"{self.candidate_id}.wav"
        # Make sure the reference is a 24 kHz mono WAV before handing it to
        # create_voice_clone_prompt. If the configured reference is an MP3
        # (e.g. a shortlist audition file we are re-using as a reference),
        # transcode it once via ffmpeg into the cache and point at the WAV.
        # This keeps clone conditioning consistent across runs and avoids
        # passing MP3 bytes to an API that expects WAV.
        ref_path = self._ensure_wav_reference(ref_path)
        # Pick language-appropriate reference text for clone conditioning
        lang = getattr(self, "_language", None) or "German"
        default_ref_text = (VOICEDESIGN_REF_TEXT_EN if lang == "English"
                            else VOICEDESIGN_REF_TEXT_DE)
        ref_text_for_clone = getattr(self, "_ref_text_override", None) or default_ref_text
        # Allow description to carry per-voice info (voice JSON / recipe)
        if ref_path.exists():
            self._ref = VoiceRef(candidate_id=self.candidate_id,
                                 description=self.description,
                                 ref_text=ref_text_for_clone,
                                 wav_path=ref_path,
                                 language=lang)
        else:
            if not self.allow_design:
                raise TTSError(
                    f"VD-E-Referenz fehlt: {ref_path}. Neuerzeugung ist "
                    "gesperrt (LOCKED PRODUCTION, §12/§24).")
            self._ref = self.studio.design_reference(
                self.candidate_id, self.description, language=lang,
                ref_text=ref_text_for_clone, seed=self._design_seed)
        self._prompt = self.studio.build_clone_prompt(self._ref)

    def _ensure_wav_reference(self, ref_path: Path) -> Path:
        """Production-reference guard.

        A production clone-conditioning reference MUST be a 24 kHz mono WAV
        living under ``cache/voice_refs/`` (or another location explicitly
        supplied by a test harness / runtime override), previously generated
        by ``QwenVoiceStudio.design_reference()``.

        Audition-MP3s (benchmark/fast_audition*/*.mp3 etc.) are final renders
        for human listening — they speak the AUDITION text ("Every discovery
        begins with a question…" / "Jede Entdeckung beginnt…") while
        ``build_clone_prompt`` is called with ``VOICEDESIGN_REF_TEXT_EN/DE``
        ("There is a book…" / "Es gibt ein Buch…"). Passing them through
        would create a text/audio mismatch → corrupt clone prompt → garbled
        output. We therefore refuse non-WAV references outright in
        production and only accept them if the caller explicitly set the
        ``VOICEOVER_REFS_ACCEPT_NONWAV`` env flag (test harness / explicit
        user override). Missing files are returned as-is so the caller can
        trigger VoiceDesign (allow_design=True) or fail with a clear error
        (allow_design=False).
        """
        import os as _os
        if not ref_path.exists():
            return ref_path
        suf = ref_path.suffix.lower()
        if suf == ".wav":
            return ref_path
        accept_nonwav = bool(_os.environ.get("VOICEOVER_REFS_ACCEPT_NONWAV"))
        if not accept_nonwav:
            from .engine_base import TTSError
            raise TTSError(
                f"Produktions-Referenz {ref_path} ist kein WAV "
                f"(Suffix '{suf}'). Audition-/Benchmark-MP3s sind Hör-Renders, "
                "keine Clone-Konditionierungsreferenzen (Text/Audio-Mismatch "
                "→ korrumpierter Prompt → Stimm-Korruption).\n"
                "Die kanonische Referenz muss per VoiceDesign erzeugt "
                "werden und unter cache/voice_refs/ als 24 kHz mono WAV "
                "vorliegen. Nutze tools/materialize_references.py auf dem "
                "GPU-Host oder setze VOICEOVER_REFS_ACCEPT_NONWAV=1 nur für "
                "explizite Tests.")
        from .. import paths as _p
        from hashlib import sha256
        conv_dir = _p.VOICE_REFS_DIR / "_converted"
        conv_dir.mkdir(parents=True, exist_ok=True)
        key = (ref_path.name + "_" + str(ref_path.stat().st_size) + "_"
               + str(int(ref_path.stat().st_mtime)))
        digest = sha256(key.encode("utf-8")).hexdigest()[:12]
        out_wav = conv_dir / f"{ref_path.stem}_{digest}_24k_mono.wav"
        if out_wav.exists():
            return out_wav
        try:
            from ..audio.ffmpeg import run_ffmpeg
            ok, _msg = run_ffmpeg([
                "-y", "-i", str(ref_path),
                "-ar", "24000", "-ac", "1",
                "-c:a", "pcm_s16le", str(out_wav),
            ], timeout_s=120)
            if ok and out_wav.exists() and out_wav.stat().st_size > 0:
                log.warning(
                    "Reference %s ist kein WAV — akzeptiert nur, weil "
                    "VOICEOVER_REFS_ACCEPT_NONWAV gesetzt ist. "
                    "Transkodiert nach %s (Text/Audio-Mismatch möglich!).",
                    ref_path, out_wav)
                return out_wav
            log.warning("ffmpeg-Transkodierung fehlgeschlagen (%s); "
                        "versuche Original-Pfad direkt zu verwenden.", _msg)
        except Exception as e:
            log.warning("ffmpeg-Transkodierung nicht verfügbar: %s", e)
        return ref_path

    def load(self) -> None:
        self._ensure_prompt()

    def is_loaded(self) -> bool:
        return self._prompt is not None

    def unload(self) -> None:
        self._prompt = None
        # Auch den Cache im VoiceStudio leeren, damit beim engine-Wechsel
        # keine Prompt-Tensoren/Modelle im Speicher hängen bleiben.
        try:
            if getattr(self, "studio", None) is not None:
                self.studio._clone_prompts.clear()
        except Exception:
            pass
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
