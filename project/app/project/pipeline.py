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
from ..audio.assemble import apply_speed, assemble, assemble_to_file
from ..audio.master import (
    OUTPUT_FORMAT_WAV_MP3,
    master_file_to_youtube,
    master_to_youtube,
    normalize_output_format,
)
from ..cache.manager import CacheManager, segment_cache_key
from ..hardware.monitor import VRAMGuard
from ..logging_setup import get_logger, plog, qlog, safe_preview
from ..pronunciation import PronunciationEngine
from ..prosody import build_instruct, pacing_hint, speed_instruct
from ..prosody.german import (detect_short_sentence_run, dominant_role,
                              hint_allowed, _HIGH_AROUSAL)
from ..prosody.variation import (apply_sampling_offsets, detect_subtle_emotion,
                                 emphasis_targets, sampling_offsets)
from ..prosody.instruct import detect_emotion
from ..prosody.pauses import assign_pauses
from ..prosody.presets import get_preset
from ..quality import SegmentQC, generate_with_qc
from ..quality.continuity import ContinuityState
from ..quality.final_gate import final_qc_gate
from ..quality.regeneration import AttemptResult
from ..segmentation import SegmentationConfig, segment_text
from ..tts.engine_base import EngineOOMError, SynthesisRequest, TTSError
from ..tts.sampler import PARAM_SET_VERSION, max_new_tokens_for, params_for_set
from ..text.analyze import analyze_text
from ..text.normalize import NormalizationReport, normalize_text
from ..text.langdetect import check_language_plausibility
from ..voices.profiles import get_profile, profile_for_language
from .state import ProjectState, project_id_for

VOICE_CFG_DEFAULTS = {"id": None, "speaker": None,
                       "production_seed": None}


def _voice_cfg(cfg: dict) -> dict:
    v = cfg.get("voice") or {}
    merged = dict(VOICE_CFG_DEFAULTS)
    merged.update(v if isinstance(v, dict) else {})
    return merged


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
                 vram_guard: VRAMGuard | None = None,
                 segment_callback=None):
        self.cfg = cfg
        self.engine = engine
        self.progress = progress
        self.guard = vram_guard or VRAMGuard()
        self.segment_callback = segment_callback  # optional diagnostics hook
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
        # Defaults aus app.config.DEFAULT_CONFIG (420/120/700) – kurze
        # Segmente = mehr natürliche Satzenden im Audiostrom, was wiederum
        # hörbare Pausen und bessere Langform-Konsistenz erzeugt.
        seg_cfg = SegmentationConfig(
            target_chars=int(adv.get("segment_target_chars", 420)),
            min_chars=int(adv.get("segment_min_chars", 120)),
            max_chars=int(adv.get("segment_max_chars", 700)),
            close_slack=float(adv.get("segment_close_slack", 0.45)),
            hard_start_min_chars=int(adv.get("segment_hard_start_min_chars", 200)),
            respect_paragraph_boundary=not bool(adv.get(
                "segment_cross_paragraph", False)),
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
        # Desktop-App (§11/§12): explizite voice_id überschreibt Profilwahl
        voice = _voice_cfg(self.cfg)
        if voice.get("speaker"):
            speaker = voice["speaker"]
        production_seed = voice.get("production_seed")
        german_cfg = self.cfg.get("german", {}) or {}
        german_variant = german_cfg.get(
            "instruct_variant", GERMAN_CFG_DEFAULTS["instruct_variant"])
        min_german_score = float(german_cfg.get(
            "min_german_score", GERMAN_CFG_DEFAULTS["min_german_score"]))
        # Pausenstrategie/Stil: explizite cfg-Einträge haben Vorrang,
        # sonst Preset-Standard (damit narrative_documentary automatisch
        # strategy=narrative aktiviert).
        pause_strategy = adv.get(
            "pause_strategy",
            self.cfg.get("pause_strategy", preset.get("pause_strategy", "classic")))
        de_modifier = getattr(profile, "de_modifier", "")
        speed = float(self.cfg.get("speed", preset.get("speed", 1.0)) or 1.0)
        pause_style = self.cfg.get("pause_style", preset.get("pause_style", "auto"))
        # B-Standard (dokumentiert): pause_style="auto", pause_strategy=
        # "classic" – Presets koennen abweichen (z. B. deep_documentary ->
        # narrative/relaxed), der Fallback-Default bleibt classic/auto.
        log.info("Pausen: preset=%s lang=%s style=%s strategy=%s speed=%.2f "
                 "segs=%d", self.cfg.get("preset", "deep_documentary"),
                 language, pause_style, pause_strategy, speed, len(segments))
        assign_pauses(segments, style=pause_style, speed=speed,
                      strategy=pause_strategy, language=language)
        # B-QC-Diagnostik am Pausenplan (KEIN Gate, nur Transparenz):
        # sehr lange innere Pausen, mechanisch identische Folgen,
        # mechanical_pauses-Metrik + Verteilung je Pausentyp.
        from ..prosody.pauses import diagnose_pause_plan
        pdiag = diagnose_pause_plan(segments, language=language,
                                    strategy=pause_strategy)
        log.info(
            "PAUSE_PLAN_DIAGNOSTIC lang=%s strategy=%s internal=%d "
            "total=%.2fs long=%d mechanical=%d dist=%s",
            language, pause_strategy, pdiag["internal_pauses"],
            pdiag["internal_pause_total_s"],
            len(pdiag["long_internal_pauses"]),
            pdiag["mechanical_pauses"], pdiag["distribution_by_type"])

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
        # Generationseitiger Pacing-Hint (nur wenn das Preset ihn
        # anfordert): entspannter Erzaehlrhythmus BEI DER ERZEUGUNG -
        # keine Zeitdehnung, keine Pitch-/Formant-Aenderung. Das fertige
        # WAV bleibt bei speed=1.0 unangetastet (kein atempo).
        pacing = pacing_hint(language) if preset.get("pacing_hint") else ""
        instructs = self._build_all_instructs(
            segments, base_style, language, speed, german_variant,
            de_modifier, short_run_idx, run_bounds, pacing=pacing)
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
        n_seg = len(segments)
        qc = SegmentQC(language=language)
        max_attempts = int(adv.get("qc_max_attempts", 3))
        min_score = float(adv.get("qc_min_score", 78))
        qc_enabled = bool(adv.get("qc_enabled", True))
        # Stricter final-gate threshold for long-form: a barely-passing
        # segment accumulates into audible degradation across dozens of
        # segments, so we demand a higher floor than a single-shot test.
        final_gate_ratio = float(adv.get("final_gate_ratio", 0.88))
        continuity = ContinuityState() if n_seg > 1 else None

        segment_audio: list = []
        reused = 0
        regenerated = 0
        failed_segments = 0
        scores: list[float] = []

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
            # Deterministischer Segment-Seed.
            #
            # Standard-Modus ("global"): alle Segmente einer Stimme laufen
            # mit demselben production_seed (so funktioniert V1 stabil
            # 25/25 ohne jegliche Regenerationen und ohne Final-Gate-
            # Blockaden – das ist der VOICE-1-Regressionschutz).
            #
            # Modus "per_segment": ein deterministischer, pro Segment
            # UNTERScheidbarer Seed wird aus sha256(voice_seed + cache_key)
            # abgeleitet. Das ist der Stabilitäts-Fix für Stimmen, bei
            # denen der globale Seed systematisch 0.16-s-/Silence- oder
            # Daueroszillationen erzeugt (V2/V3). Der Seed bleibt über
            # Läufe hinweg 100% reproduzierbar.
            from hashlib import sha256
            seed_mode = str(adv.get("segment_seed_mode", "per_segment")).lower()
            if seed_mode == "global" and production_seed is not None:
                # Explizit erzwungener globaler Modus (nur für
                # kontrollierte A/B-Tests; im Longform-Benchmark
                # wird standardmäßig per_segment verwendet).
                seg_seed = int(production_seed)
            else:
                # Per-Segment-Modus (Default): deterministischer
                # Segment-Seed aus sha256(voice_seed + cache_key) –
                # pro Segment ANDERER Seed, aber über Läufe identisch.
                seed_material = (f"{production_seed}:{key}"
                                 if production_seed is not None else key)
                seg_seed = int(sha256(seed_material.encode("utf-8"))
                               .hexdigest()[:8], 16)
            request = SynthesisRequest(
                text=seg.text, language=language, speaker=speaker,
                instruct=instruct, sampling=seg_sampling,
                seed=seg_seed,
                max_seconds_hint=expected_s, speed=speed)

            self.guard.before_call()

            def _regen_progress(attempt: int, ar, _phase="qc") -> None:
                # Fortschrittsanzeige während QC/Regeneration (Anforderung 31)
                self._emit(phase=_phase,
                           attempt=attempt,
                           current_segment=pos + 1,
                           total_segments=n_seg,
                           qc_percent=min(100, int(attempt / max(1, max_attempts) * 100)),
                           tts_percent=int((pos) / n_seg * 100))

            result = generate_with_qc(
                self.engine, request, seg.text, qc,
                max_attempts=(max_attempts if qc_enabled else 1),
                min_score=min_score, min_german_score=min_german_score,
                german_meta=german_meta,
                progress_cb=_regen_progress)
            best: AttemptResult | None = result["best"]
            attempts = result.get("attempts") or []

            # Per-attempt Diagnostik an den Callback geben, damit der
            # Benchmark sie persistent schreiben kann.
            seg_diag = {
                "seg_index": seg.index,
                "text_hash": meta.get("text_hash", ""),
                "base_seed": int(seg_seed),
                "sampling": seg_sampling,
                "expected_s": round(expected_s, 2),
                "instruct": instruct,
                "attempts": [],
            }
            for ar in attempts:
                m = ar.metrics or {}
                seg_diag["attempts"].append({
                    "attempt": ar.attempt,
                    "seed": (ar.params_used or {}).get("seed"),
                    "sampling": (ar.params_used or {}).get("sampling"),
                    "error_class": (ar.params_used or {}).get("error_class"),
                    "score": round(float(ar.score or 0.0), 2),
                    "german_score": ar.german_score,
                    "duration_s": (m.get("duration_s")
                                   if m else (float(len(ar.waveform)) /
                                              float(ar.sample_rate)
                                              if ar.waveform is not None and
                                              ar.sample_rate else 0.0)),
                    "rms": m.get("rms"),
                    "f0_hz": m.get("f0_hz"),
                    "lufs": m.get("lufs"),
                    "silence_ratio": m.get("silence_ratio"),
                    "issues": list(ar.issues or []),
                    "critical": bool(ar.critical),
                    "error": ar.error,
                })

            accepted_in_retry = False
            failure_reason = ""
            final_gate_passed = False
            chosen_wave = None
            chosen_sr = 24000
            chosen_score = 0.0
            chosen_attempt = None
            score_obj_metrics: dict = {}   # populated below for both branches

            if best is None or best.waveform is None:
                # OOM-Notfallpfad: Segment an Satzgrenze halbieren (Anf. 4)
                wav_sr = self._split_fallback(request, seg, qc)
                if wav_sr is None:
                    failed_segments += 1
                    failure_reason = "Synthese endgültig fehlgeschlagen"
                    state.set_segment(seg.index, "failed", attempts=len(attempts),
                                      error=failure_reason)
                    if self.segment_callback:
                        seg_diag.update({"status": "failed",
                                         "failure_reason": failure_reason,
                                         "final_gate_passed": False})
                        try: self.segment_callback(seg_diag)
                        except Exception: pass
                    continue
                wav, sr = wav_sr
                # §4: Auch Split-Fallback VOR Übernahme erneut QC-prüfen
                gate = final_qc_gate(wav, sr, seg.text, qc,
                                     context=f"split-fallback seg{seg.index}",
                                     german_meta=german_meta,
                                     min_score=min_score * final_gate_ratio)
                if not gate.passed:
                    failed_segments += 1
                    failure_reason = (f"Split-Fallback im Final-Gate blockiert: "
                                      f"{gate.reason}")
                    state.set_segment(
                        seg.index, "failed",
                        attempts=len(attempts),
                        error=failure_reason)
                    log.error("Segment %d verworfen (Final-Gate): %s",
                              seg.index, gate.reason)
                    if self.segment_callback:
                        seg_diag.update({"status": "failed",
                                         "failure_reason": failure_reason,
                                         "final_gate_passed": False})
                        try: self.segment_callback(seg_diag)
                        except Exception: pass
                    continue
                chosen_wave, chosen_sr = wav, sr
                chosen_score = float(gate.score)
                chosen_attempt = 99
                accepted_in_retry = True   # split-fallback = regenerated
                final_gate_passed = True
                # split-fallback path: no prior AttemptResult.metrics, so
                # we fill score_obj_metrics below from the waveform itself.
            else:
                # §4: kritisches/niedriges „best“ NICHT blind übernehmen –
                # erneute, unabhängige QC-Prüfung vor Cache/Audio
                gate = final_qc_gate(best.waveform, best.sample_rate,
                                     seg.text, qc,
                                     context=f"segment {seg.index}",
                                     german_meta=german_meta,
                                     min_score=min_score * final_gate_ratio)
                if not gate.passed:
                    failed_segments += 1
                    failure_reason = f"Final-Gate blockiert: {gate.reason}"
                    state.set_segment(
                        seg.index, "failed",
                        attempts=len(attempts),
                        error=failure_reason)
                    log.error("Segment %d verworfen (Final-Gate): %s",
                              seg.index, gate.reason)
                    if self.segment_callback:
                        seg_diag.update({"status": "failed",
                                         "failure_reason": failure_reason,
                                         "final_gate_passed": False})
                        try: self.segment_callback(seg_diag)
                        except Exception: pass
                    continue
                chosen_wave = best.waveform
                chosen_sr = best.sample_rate
                chosen_score = float(gate.score)
                chosen_attempt = int(best.attempt)
                final_gate_passed = True
                if len(attempts) > 1:
                    accepted_in_retry = True
                    regenerated += 1

            # Segment hat Final-Gate bestanden – Audio übernehmen.
            score_val = float(chosen_score)
            # Base metrics dict from the best attempt (regular path) or
            # empty for the split-fallback path (we fill below).
            score_obj_metrics = dict(best.metrics) if (
                best is not None and getattr(best, "metrics", None)
            ) else {}
            # Compute loudness/RMS/duration for continuity tracker from
            # the chosen waveform (works for both regular and split-
            # fallback paths and fills any missing keys on the regular
            # path as a defensive measure).
            import numpy as _np
            _arr = (chosen_wave if isinstance(chosen_wave, _np.ndarray)
                    else chosen_wave.cpu().numpy())
            _arr = _arr.reshape(-1).astype("float32")
            if "rms" not in score_obj_metrics:
                score_obj_metrics["rms"] = float(
                    _np.sqrt(_np.mean(_arr.astype("float32") ** 2)))
            if "duration_s" not in score_obj_metrics:
                score_obj_metrics["duration_s"] = float(
                    len(_arr) / max(1, chosen_sr))
            # Also compute integrated LUFS if available and missing, so
            # continuity tracking has a stable loudness signal even on
            # the split-fallback path.
            if "lufs" not in score_obj_metrics:
                try:
                    from ..audio.ebu_r128 import integrated_lufs as _il
                    score_obj_metrics["lufs"] = float(_il(_arr, chosen_sr))
                except Exception:
                    pass
            if "f0_median_hz" not in score_obj_metrics:
                # f0 extraction is not trivial without parselmouth/dsp;
                # leave None so continuity skips F0 for this segment
                # rather than poisoning the running median.
                score_obj_metrics["f0_median_hz"] = None
            if continuity is not None:
                drift, dflags = continuity.score(score_obj_metrics)
                if drift > 30.0:
                    plog(f"SEG {seg.index:04d} continuity drift={drift:.0f} "
                         f"flags={','.join(dflags)}")
                continuity.observe(score_obj_metrics)
            self.cache.put(key, chosen_wave, chosen_sr, {
                "ok": True, "score": score_val,
                "german_score": (best.german_score if best is not None else None),
                "issues": (best.issues if best is not None else []),
                "metrics": score_obj_metrics,
                "speaker": speaker, "language": language,
                "text_preview": safe_preview(seg.text, 100),
                "instruct": instruct,
                "project_id": project_id,
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            scores.append(score_val)
            state.set_segment(seg.index, "done", score=score_val,
                              attempts=len(attempts))
            segment_audio.append((chosen_wave, chosen_sr, seg))
            self._emit(tts_percent=int((pos + 1) / n_seg * 100),
                       qc_percent=100)
            plog(f"SEG {seg.index:04d} fertig: score={score_val:.1f} "
                 f"versuche={len(attempts)} cache=reused={reused}")
            if self.segment_callback:
                seg_diag.update({
                    "status": "ok",
                    "final_gate_passed": final_gate_passed,
                    "regenerated": bool(accepted_in_retry),
                    "chosen_attempt": chosen_attempt,
                    "final_score": round(score_val, 2),
                    "failure_reason": "",
                })
                try: self.segment_callback(seg_diag)
                except Exception:
                    pass

        # 9) Zusammenfügen (Streaming in Datei, §18 Long-Form) -------------------
        n_successful = len(segment_audio)  # vor Freigabe sichern
        if not segment_audio:
            elapsed = time.perf_counter() - t_start
            report.update({
                "ok": False,
                "wav": None,
                "mp3": None,
                "segments": n_seg,
                "segments_planned": n_seg,
                "segments_successful": 0,
                "reused": reused,
                "regenerated": regenerated,
                "failed_segments": failed_segments,
                "avg_score": round(float(np.mean(scores)), 1) if scores else None,
                "duration_s": 0.0,
                "elapsed_s": round(elapsed, 1),
                "project_id": project_id,
                "wav_complete": False,
                "error": "Keine Segmente erfolgreich.",
            })
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

        from .. import paths as _paths
        out_dir = Path(self.cfg.get("output_dir", "")) if \
            self.cfg.get("output_dir") else _paths.OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        out_wav = out_dir / f"{input_path.stem}.wav"
        out_mp3 = out_dir / f"{input_path.stem}.mp3"
        raw_wav = _paths.CACHE_DIR / "assembly" / \
            f"{input_path.stem}_{int(time.time())}.wav"
        raw_wav.parent.mkdir(parents=True, exist_ok=True)

        # Tempo (pitch-erhaltend) + Pausen skaliert – innerhalb des
        # Streaming-Writers; kein Voll-Array im RAM (120 min sicher)
        sr, total_s, _pause = assemble_to_file(
            segment_audio, raw_wav,
            project_median_lufs=median_lufs,
            precomputed_lufs=collected_lufs,
            speed=speed)
        # Wellenformen-Referenzen freigeben (Anforderung 4); Variable bleibt
        # als leere Liste gebunden, damit der finale Report ohne
        # UnboundLocalError auf die bereits in n_successful gesicherten
        # Zählwerte zugreifen kann.
        segment_audio.clear()

        # 10) Mastering (Anforderung 40+41; dateibasiert, streaming) -----------
        self._emit(phase="mastering")
        # Ausgabeformat aus cfg holen (GUI/CLI/Jobs setzen das; Default = WAV+MP3)
        from ..audio.master import normalize_output_format
        output_format = normalize_output_format(
            self.cfg.get("output_format",
                         self.cfg.get("formats", OUTPUT_FORMAT_WAV_MP3)))
        master_report = master_file_to_youtube(
            raw_wav, out_wav, out_mp3,
            target_lufs=float(adv.get("target_lufs", -14.0)),
            true_peak_dbtp=float(adv.get("true_peak_dbtp", -1.5)),
            wav_sample_rate=int(adv.get("wav_sample_rate", 48000)),
            wav_bit_depth=int(adv.get("wav_bit_depth", 24)),
            mp3_bitrate=str(adv.get("mp3_bitrate", "320k")),
            output_format=output_format,
        )
        volume_db = float(self.cfg.get("volume_db", 0.0) or 0.0)
        if volume_db:
            master_report["volume_db_applied"] = volume_db   # dokumentiert
        try:
            raw_wav.unlink(missing_ok=True)      # Roh-Master aufräumen
        except OSError:
            pass

        elapsed = time.perf_counter() - t_start
        # Nur tatsächlich erzeugte Dateien melden (MP3/WAV ggf. None)
        final_wav = master_report.get("wav")
        final_mp3 = master_report.get("mp3")
        state.set_phase("completed",
                        wav=final_wav or "",
                        mp3=final_mp3 or "")
        # wav_complete = ALLE geplanten Segmente waren erfolgreich UND ein
        # Output-WAV existiert. FAIL-CLOSED: sobald ein Segment fehlschlägt
        # (failed_segments > 0) gilt der Part als unvollständig - der
        # Runner darf daraus KEIN FullScript bauen und muss den Status
        # FAILED/INCOMPLETE liefern.
        all_segments_ok = (n_successful == n_seg and failed_segments == 0)
        wav_complete = bool(all_segments_ok
                            and final_wav and Path(final_wav).exists())
        report.update({
            # ok=True nur, wenn WAV existiert UND alle geplanten Segmente
            # erfolgreich erzeugt wurden (keine stillen Fehlschläge).
            "ok": bool(final_wav and Path(final_wav).exists()
                       and all_segments_ok),
            "wav": final_wav if wav_complete else None,
            "mp3": final_mp3 if wav_complete else None,
            "output_format": output_format,
            "segments": n_seg,
            "segments_planned": n_seg,
            "segments_successful": n_successful,
            "reused": reused,
            "regenerated": regenerated,
            "failed_segments": failed_segments,
            "avg_score": round(float(np.mean(scores)), 1) if scores else None,
            "duration_s": round(total_s, 1),
            "master": master_report,
            "elapsed_s": round(elapsed, 1),
            "project_id": project_id,
            "wav_complete": wav_complete,
            "error": (None if all_segments_ok
                      else f"{failed_segments} von {n_seg} Segmenten fehlgeschlagen - unvollstaendiges Audio"),
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
                             run_bounds: dict, pacing: str = "") -> list[str]:
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
            if pacing:
                instr = instr + " " + pacing
            sp = speed_instruct(speed, language=language)
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
        _preset = get_preset(self.cfg.get("preset", "deep_documentary"))
        if _preset.get("pacing_hint"):
            instr = instr + " " + pacing_hint(language)
        sp = speed_instruct(speed, language=language)
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
