"""Verarbeitungs-Pipeline pro Datei (Anforderung 6 + 80).

Analyse -> Normalisierung -> Aussprache -> Segmentierung -> Qwen3-TTS
(natürliche Prosodie) -> Qualitätsprüfung -> automatische Regeneration
-> Zusammenfügen -> Lautheitsnormalisierung -> YouTube-Master -> WAV+MP3
-> Cache -> Bericht.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import numpy as np

from .. import config as cfgmod
from ..audio.assemble import apply_speed, assemble
from ..audio.master import master_to_youtube
from ..cache.manager import CacheManager, segment_cache_key
from ..hardware.monitor import VRAMGuard
from ..logging_setup import get_logger, plog, qlog, safe_preview
from ..pronunciation import PronunciationEngine
from ..prosody import build_instruct, speed_instruct
from ..prosody.german import (detect_short_sentence_run, dominant_role,
                              hint_allowed, _HIGH_AROUSAL)
from ..prosody.variation import (apply_sampling_offsets, detect_subtle_emotion,
                                 emphasis_targets, sampling_offsets)
from ..prosody.instruct import detect_emotion
from ..prosody.pauses import assign_pauses
from ..prosody.presets import get_preset
from ..quality import SegmentQC, generate_with_qc
from ..quality.regeneration import AttemptResult
from ..segmentation import SegmentationConfig, segment_text
from ..tts.engine_base import EngineOOMError, SynthesisRequest, TTSError
from ..tts.sampler import PARAM_SET_VERSION, max_new_tokens_for, params_for_set
from ..text.analyze import analyze_text
from ..text.normalize import NormalizationReport, normalize_text
from ..text.langdetect import check_language_plausibility
from ..voices.profiles import get_profile, profile_for_language
from .state import ProjectState, project_id_for

GERMAN_CFG_DEFAULTS = {"instruct_variant": "de_doc_native",
                       "min_german_score": 75.0,
                       "tech_germanization": True,
                       "variation": {"enabled": None, "strength": "subtle"}}

def _variation_enabled(cfg: dict, engine) -> bool:
    """Phase 3 §22: Sampling-Variation – Clone-Stimmen per Default."""
    var_cfg = ((cfg.get("german", {}) or {}).get("variation", {}) or {})
    if var_cfg.get("enabled") is not None:
        return bool(var_cfg["enabled"])
    engine_name = getattr(engine, "name", "") or ""
    return "clone" in engine_name        # VoiceCloneEngine ohne Instruct

log = get_logger("pipeline")


class PipelineCancelled(RuntimeError):
    """Kooperativer Abbruch (Resume bleibt möglich)."""


class Pipeline:
    def __init__(self, cfg: dict, engine, progress=None,
                 vram_guard: VRAMGuard | None = None):
        self.cfg = cfg
        self.engine = engine
        self.progress = progress
        self.guard = vram_guard or VRAMGuard()
        self.cache = CacheManager(enabled=bool(
            cfgmod.get(cfg, "advanced.cache_enabled", True)))
        gcfg0 = cfg.get("german", {}) or {}
        self.pron_engine = PronunciationEngine(
            tech_germanization=bool(
                gcfg0.get("tech_germanization",
                          GERMAN_CFG_DEFAULTS["tech_germanization"])))
        self.variation_on = _variation_enabled(cfg, engine)
        self.variation_strength = ((gcfg0.get("variation", {}) or {})
                                   .get("strength", "subtle"))
        self.engine_info = engine.info()

    # ---------------------------------------------------------------------
    def _emit(self, **kw) -> None:
        if self.progress:
            self.progress.update(**kw)

    def process_file(self, input_path: Path) -> dict:
        t_start = time.perf_counter()
        input_path = Path(input_path)
        language = self.cfg.get("language", "German")
        lang_key = "de" if language.lower().startswith("ger") else "en"
        report: dict = {"file": input_path.name, "ok": False, "warnings": []}

        # 1) Lesen -----------------------------------------------------------
        text = _read_text(input_path)
        if not text.strip():
            report["error"] = "Datei ist leer."
            return report
        report["chars"] = len(text)

        # 2) Sprach-Plausibilität (nur Warnung, Anforderung 8) ---------------
        lang_check = check_language_plausibility(text, language)
        if not lang_check.plausible:
            report["warnings"].append(lang_check.warning)
            log.warning("[%s] %s", input_path.name, lang_check.warning)

        # 3) Analyse ----------------------------------------------------------
        analysis = analyze_text(text, language)
        report["analysis"] = {
            "words": analysis.stats.words,
            "sentences": analysis.stats.sentences,
            "paragraphs": analysis.stats.paragraphs,
            "headings": analysis.stats.headings,
            "estimated_seconds": analysis.stats.estimated_seconds,
        }

        # 4) Normalisierung (Original bleibt getrennt, Anforderung 11) --------
        norm_report = NormalizationReport()
        adv = self.cfg.get("advanced", {})

        def tts_text_provider(block):
            normalized = normalize_text(block.text, language, norm_report)
            pronounced = self.pron_engine.process(normalized, language,
                                                  suggest_unknown=False)
            return pronounced.text

        # 5) Aussprache über gesamten Text (für Bericht/Vorschläge) -----------
        full_normalized = normalize_text(text, language, norm_report)
        pron_result = self.pron_engine.process(full_normalized, language)
        report["normalizations"] = norm_report.count
        report["pronunciation_replacements"] = len(pron_result.replacements)
        report["pronunciation_suggestions"] = [
            u["term"] for u in pron_result.unknown_problem_words[:15]]

        # 6) Segmentierung ------------------------------------------------------
        seg_cfg = SegmentationConfig(
            target_chars=int(adv.get("segment_target_chars", 420)),
            min_chars=int(adv.get("segment_min_chars", 120)),
            max_chars=int(adv.get("segment_max_chars", 700)),
        )
        segments = segment_text(analysis.blocks, tts_text_provider, seg_cfg)
        if not segments:
            report["error"] = "Keine Segmente erzeugt."
            return report

        # Phase 2: Short-Run-Erkennung ("Sieben Prinzipien. …", §12)
        short_run_idx = set(detect_short_sentence_run(
            [s.text for s in segments]))
        run_bounds = _run_bounds([s.text for s in segments],
                                 short_run_idx)

        preset = get_preset(self.cfg.get("preset", "deep_documentary"))
        profile = get_profile(self.cfg.get("voice_profile"))
        speaker_map = (self.cfg.get("voices", {}) or {}).get("speaker_map", {})
        speaker = speaker_map.get(profile.id, profile.speaker)
        german_cfg = self.cfg.get("german", {}) or {}
        german_variant = german_cfg.get(
            "instruct_variant", GERMAN_CFG_DEFAULTS["instruct_variant"])
        min_german_score = float(german_cfg.get(
            "min_german_score", GERMAN_CFG_DEFAULTS["min_german_score"]))
        pause_strategy = adv.get("pause_strategy", "classic")
        de_modifier = getattr(profile, "de_modifier", "")
        speed = float(self.cfg.get("speed", 1.0) or 1.0)
        pause_style = self.cfg.get("pause_style", preset.get("pause_style", "auto"))
        assign_pauses(segments, style=pause_style, speed=speed,
                      strategy=pause_strategy)

        # Sampling-Parameter (Anforderung 49)
        sampling = params_for_set("balanced", {
            "do_sample": adv.get("do_sample", True),
            "temperature": adv.get("temperature", 0.7),
            "top_k": adv.get("top_k", 50),
            "top_p": adv.get("top_p", 0.90),
            "repetition_penalty": adv.get("repetition_penalty", 1.05),
        })

        base_style = profile_for_language(profile, language)

        # 7) Projekt-State + Resume (Anforderung 37) ----------------------------
        project_id = project_id_for(input_path, language)
        state = ProjectState(project_id)
        from ..utils import sha256_str
        seg_metas = []
        instructs = self._build_all_instructs(
            segments, base_style, language, speed, german_variant,
            de_modifier, short_run_idx, run_bounds)
        for pos, seg in enumerate(segments):
            instruct = instructs[pos]
            key = segment_cache_key(
                engine=self.engine_info.get("engine", "qwen"),
                engine_version=self.engine_info.get("engine_version", "?"),
                model_size=str(self.engine_info.get("model_size", "")),
                speaker=speaker,
                instruct=instruct,
                language=language,
                text=seg.text,
                sampling=sampling,
                param_version=PARAM_SET_VERSION,
            )
            seg_metas.append({"index": seg.index, "text_hash": sha256_str(seg.text),
                              "cache_key": key, "preview": seg.source_preview,
                              "pause_after_s": seg.pause_after_s})
        state.init_segments(seg_metas, {
            "language": language, "voice_profile": profile.id,
            "speaker": profile.speaker, "preset": self.cfg.get("preset"),
            "speed": speed, "engine": self.engine_info.get("engine_version"),
        }, str(input_path))
        done_before = state.done_indices()

        # 8) TTS + QC + Regeneration + Cache ------------------------------------
        qc = SegmentQC(language=language)
        max_attempts = int(adv.get("qc_max_attempts", 3))
        min_score = float(adv.get("qc_min_score", 78))
        qc_enabled = bool(adv.get("qc_enabled", True))

        segment_audio: list = []
        reused = 0
        regenerated = 0
        failed_segments = 0
        scores: list[float] = []
        n_seg = len(segments)

        for pos, seg in enumerate(segments):
            if (self.progress is not None
                    and getattr(self.progress, "should_cancel", None)
                    and self.progress.should_cancel()):
                state.set_phase("cancelled")
                raise PipelineCancelled(
                    f"Abbruch durch Benutzer nach Segment {pos}/{n_seg} "
                    f"(Resume möglich)")
            meta = seg_metas[pos]
            key = meta["cache_key"]
            self._emit(current_segment=pos + 1, total_segments=n_seg,
                       tts_percent=int((pos) / n_seg * 100),
                       qc_percent=0)
            # Cache/Resume
            if state.data["segments"][pos]["status"] == "done" or self.cache.has(key):
                got = self.cache.get(key)
                if got:
                    wav, sr, cmeta = got
                    segment_audio.append((wav, sr, seg))
                    if cmeta.get("metrics"):
                        qc.observe_good(cmeta["metrics"])
                    if cmeta.get("score") is not None:
                        scores.append(float(cmeta["score"]))
                    reused += 1
                    state.set_segment(seg.index, "done",
                                      score=cmeta.get("score"))
                    continue

            instruct = instructs[pos]
            expected_s = max(4.0, len(seg.text) / (13.8 if lang_key == "de" else 15.0))
            # deutsche Meta-Daten für GermanNaturalnessScore (Namen/Fremdwörter)
            german_meta = None
            if lang_key == "de":
                pr = self.pron_engine.process(seg.text, language,
                                              suggest_unknown=False,
                                              collect_meta=True)
                fw_total = len(pr.foreign_decisions)
                fw_decided = sum(1 for d in pr.foreign_decisions
                                 if d.action != "leave")
                german_meta = {
                    "names": pr.coverage,
                    "foreign_words": {"total": fw_total, "decided": fw_decided},
                }
            seg_sampling = dict(sampling)
            if self.variation_on and lang_key == "de":
                sem, se_int = detect_subtle_emotion(seg.text)
                offsets = sampling_offsets(dominant_role(seg.text), sem,
                                           se_int, self.variation_strength)
                seg_sampling = apply_sampling_offsets(seg_sampling, offsets)
            request = SynthesisRequest(
                text=seg.text, language=language, speaker=speaker,
                instruct=instruct, sampling=seg_sampling,
                seed=abs(hash(key)) % (2**31),
                max_seconds_hint=expected_s, speed=speed)

            self.guard.before_call()

            def _regen_progress(attempt: int, ar) -> None:
                # Fortschrittsanzeige während QC/Regeneration (Anforderung 31)
                self._emit(qc_percent=min(100, int(attempt / max(1, max_attempts) * 100)))

            result = generate_with_qc(
                self.engine, request, seg.text, qc,
                max_attempts=(max_attempts if qc_enabled else 1),
                min_score=min_score, min_german_score=min_german_score,
                german_meta=german_meta,
                progress_cb=_regen_progress)
            best: AttemptResult | None = result["best"]

            if best is None or best.waveform is None:
                # OOM-Notfallpfad: Segment an Satzgrenze halbieren (Anf. 4)
                wav_sr = self._split_fallback(request, seg, qc)
                if wav_sr is None:
                    failed_segments += 1
                    state.set_segment(seg.index, "failed", attempts=len(result["attempts"]),
                                      error="Synthese endgültig fehlgeschlagen")
                    continue
                wav, sr = wav_sr
                best = AttemptResult(attempt=99, score=60.0, waveform=wav,
                                     sample_rate=sr)
                regenerated += 1
            else:
                if len(result["attempts"]) > 1:
                    regenerated += 1

            score_val = float(best.score)
            score_obj_metrics = best.metrics or {}
            self.cache.put(key, best.waveform, best.sample_rate, {
                "ok": True, "score": score_val,
                "german_score": best.german_score,
                "issues": best.issues, "metrics": score_obj_metrics,
                "speaker": speaker, "language": language,
                "text_preview": safe_preview(seg.text, 100),
                "instruct": instruct,
                "project_id": project_id,
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            scores.append(score_val)
            state.set_segment(seg.index, "done", score=score_val,
                              attempts=len(result["attempts"]))
            segment_audio.append((best.waveform, best.sample_rate, seg))
            self._emit(tts_percent=int((pos + 1) / n_seg * 100),
                       qc_percent=100)
            plog(f"SEG {seg.index:04d} fertig: score={score_val:.1f} "
                 f"versuche={len(result['attempts'])} cache=reused={reused}")

        # 9) Zusammenfügen ------------------------------------------------------
        if not segment_audio:
            report["error"] = "Keine Segmente erfolgreich."
            state.set_phase("failed")
            return report
        state.set_phase("assembling")
        self._emit(phase="assembling")
        # Median-LUFS der Segmente für die Konsistenz-Voranpassung
        collected_lufs = []
        for wav, sr, seg in segment_audio:
            from ..audio.ebu_r128 import integrated_lufs as _il
            collected_lufs.append(_il(wav, sr))
        if collected_lufs:
            median_lufs = float(np.median(collected_lufs))

        assembled, sr = assemble(segment_audio,
                                 project_median_lufs=median_lufs,
                                 precomputed_lufs=collected_lufs)
        segment_audio.clear()          # Speicher freigeben (Anforderung 4)
        del segment_audio

        # Tempo (Anforderung 24): auf das Gesamtaudio (pitch-erhaltend)
        if abs(speed - 1.0) >= 0.02:
            self._emit(phase="speed")
            assembled, sr = apply_speed(assembled, sr, speed)

        # 10) Mastering (Anforderung 40 + 41) ------------------------------------
        self._emit(phase="mastering")
        out_dir = Path(self.cfg.get("output_dir", "")) if self.cfg.get("output_dir") else None
        from .. import paths
        out_dir = out_dir or paths.OUTPUT_DIR
        out_wav = out_dir / f"{input_path.stem}.wav"
        out_mp3 = out_dir / f"{input_path.stem}.mp3"
        master_report = master_to_youtube(
            assembled, sr, out_wav, out_mp3,
            target_lufs=float(self.cfg.get("advanced", {}).get("target_lufs", -14.0)),
            true_peak_dbtp=float(self.cfg.get("advanced", {}).get("true_peak_dbtp", -1.5)),
            wav_sample_rate=int(self.cfg.get("advanced", {}).get("wav_sample_rate", 48000)),
            wav_bit_depth=int(self.cfg.get("advanced", {}).get("wav_bit_depth", 24)),
            mp3_bitrate=str(self.cfg.get("advanced", {}).get("mp3_bitrate", "320k")),
            volume_db=float(self.cfg.get("volume_db", 0.0) or 0.0),
        )

        elapsed = time.perf_counter() - t_start
        state.set_phase("completed", wav=str(out_wav), mp3=str(out_mp3))
        report.update({
            "ok": True,
            "wav": str(out_wav), "mp3": str(out_mp3),
            "segments": n_seg, "reused": reused,
            "regenerated": regenerated,
            "failed_segments": failed_segments,
            "avg_score": round(float(np.mean(scores)), 1) if scores else None,
            "duration_s": round(len(assembled) / sr, 1),
            "master": master_report,
            "elapsed_s": round(elapsed, 1),
            "project_id": project_id,
        })
        qlog(f"FILE {input_path.name}: ok segments={n_seg} reused={reused} "
             f"regen={regenerated} failed={failed_segments} "
             f"score={report['avg_score']} dur={report['duration_s']}s")
        self._emit(file_done=True)
        return report

    # ---------------------------------------------------------------------
    @staticmethod
    def _build_all_instructs(segments, base_style: str, language: str,
                             speed: float, german_variant: str | None,
                             de_modifier: str, short_run_idx: set,
                             run_bounds: dict) -> list[str]:
        """Baut alle Segment-Instructs mit Budget-Tracking (§7) und
        Short-Run-Positionen (§12) – deterministisch, einmal pro Lauf."""
        instructs = []
        last_high_idx = None
        for seg in segments:
            words = len(seg.text.split())
            pos = None
            if seg.index in short_run_idx:
                first, last = run_bounds.get(seg.index, (None, None))
                if seg.index == first:
                    pos = "first"
                elif seg.index == last:
                    pos = "last"
                else:
                    pos = "middle"
            emph = emphasis_targets(seg.text) if language.lower().                startswith("ger") else []
            instr = build_instruct(
                base_style, seg.text, language,
                emotion="AUTO",
                intensity="AUTO",
                heading=(seg.block_kind == "heading"),
                profile_modifier=de_modifier,
                german_variant=german_variant if language.lower().startswith(
                    "ger") else None,
                seg_index=seg.index,
                last_high_idx=last_high_idx,
                short_run_pos=pos,
                long_sentence=(words > 25),
                emphasis_words=emph,
            )
            # Budget-Tracking: hochdramatische Rolle gemeldet?
            if language.lower().startswith("ger"):
                role = dominant_role(seg.text)
                if role in _HIGH_AROUSAL and hint_allowed(
                        seg.index, role, last_high_idx):
                    last_high_idx = seg.index
            sp = speed_instruct(speed)
            if sp:
                instr = instr + " " + sp
            instructs.append(instr)
        return instructs

    def _segment_instruct(self, seg, base_style: str, language: str,
                          speed: float, german_variant: str | None = None,
                          profile_modifier: str = "") -> str:
        emotion = self.cfg.get("emotion", "AUTO") or "AUTO"
        intensity = self.cfg.get("intensity", "AUTO")
        if emotion == "AUTO" and self.cfg.get("preset"):
            preset = get_preset(self.cfg.get("preset"))
            if preset.get("emotion") not in (None, "AUTO"):
                emotion = preset["emotion"]
            if preset.get("intensity") not in (None, "AUTO") and intensity == "AUTO":
                intensity = preset["intensity"]
        instr = build_instruct(
            base_style, seg.text, language,
            emotion=emotion, intensity=intensity,
            heading=(seg.block_kind == "heading"),
            profile_modifier=profile_modifier,
            german_variant=german_variant if language.lower().startswith("ger")
            else None)
        sp = speed_instruct(speed)
        if sp:
            instr = instr + " " + sp
        return instr

    def _split_fallback(self, request: SynthesisRequest, seg, qc):
        """OOM-Notfall: Segment an Satzgrenze teilen (Anforderung 4/72)."""
        from ..text.analyze import split_sentences
        sentences = split_sentences(seg.text)
        if len(sentences) < 2:
            return None
        mid = len(sentences) // 2
        parts = [" ".join(sentences[:mid]), " ".join(sentences[mid:])]
        waves = []
        sr_out = None
        for p in parts:
            req = SynthesisRequest(
                text=p, language=request.language, speaker=request.speaker,
                instruct=request.instruct, sampling=request.sampling,
                seed=request.seed + 7, max_seconds_hint=max(4.0, len(p) / 13.8))
            try:
                res = self.engine.synthesize(req)
                waves.append(res.waveform)
                sr_out = res.sample_rate
            except (TTSError, EngineOOMError) as e:
                log.error("Split-Fallback fehlgeschlagen: %s", e)
                return None
        if not waves:
            return None
        return np.concatenate(waves), sr_out


def _read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            return Path(path).read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _run_bounds(texts: list[str], short_run_idx: set) -> dict:
    """first/last-Index je Short-Run (für Build-, Middle-, Last-Hinweise)."""
    bounds = {}
    idx_list = sorted(short_run_idx)
    i = 0
    while i < len(idx_list):
        j = i
        while j + 1 < len(idx_list) and idx_list[j + 1] == idx_list[j] + 1:
            j += 1
        run = idx_list[i:j + 1]
        for k in run:
            bounds[k] = (run[0], run[-1])
        i = j + 1
    return bounds
