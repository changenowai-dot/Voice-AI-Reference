"""Desktop-Voice-Benchmark (§14/§15): jede Stimme DE + EN testen.

Testsätze exakt nach §14 plus ein Longer-Mix (Zahlen, Jahre, Abkür-
zungen, Eigennamen, Fremdwörter, Technik, Fragen, Ausrufe, Langsatz).
Messe: Audio erzeugt, Segmentanzahl, QC-Score, Pronunciation,
Naturalness, Prosodie, Integrity, Dauer, Regenerationen, Fehler.
Klassifikation: Empfohlen / Sehr gut / Gut / Experimentell.
VD-E bleibt unabhängig vom Ergebnis Standard (§15).

Produktionsmodus: nutzt load_production + echte Engines; für Tests
kann ein Studio mitgegeben werden (Prüfstand).
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from .. import paths
from ..audio.io import write_wav
from ..logging_setup import get_logger, qlog
from ..quality import SegmentQC
from ..quality.metrics import analyze_segment_audio
from ..security.identity_lock import load_production
from ..tts.engine_base import SynthesisRequest
from ..tts.sampler import params_for_set
from ..utils import write_json
from ..voices.registry import VoiceRegistry

log = get_logger("desktop_voices")

DE_TEST = "Dies ist ein natürlicher deutscher Testsatz für die " \
          "VoiceOver-Anwendung."
EN_TEST = "This is a natural English test sentence for the VoiceOver " \
          "application."

DE_LONG = ("Im Jahr 1989 fielen Mauern, 1914 begann ein Krieg, und rund "
           "3,7 % aller Daten blieben u.a. im CERN unveröffentlicht. "
           "Nietzsche, Göbekli Tepe und die Quantentheorie – warum nur "
           "wiederholen Menschen Muster, die sie längst durchschaut "
           "haben? Aber dann, plötzlich, kam die Erkenntnis, die alles "
           "veränderte, obwohl niemand damit gerechnet hatte, wirklich "
           "niemand!")
EN_LONG = ("In 1989 walls fell, in 1914 a war began, and roughly 3.7 "
           "percent of all data stayed unpublished at CERN, e.g. for "
           "decades. Nietzsche, Göbekli Tepe and quantum theory – why do "
           "people repeat patterns they long understood? But then, "
           "suddenly, came the insight that changed everything, though "
           "nobody had expected it, really nobody!")


def _score_texts(engine, speaker: str | None, texts: list[str],
                 language: str, out_dir: Path, clone: bool) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    qc = SegmentQC(language=language)
    sampling = params_for_set("balanced")
    results = []
    ok_count = 0
    regen = 0
    err = 0
    from ..quality.regeneration import generate_with_qc
    for i, t in enumerate(texts):
        req = SynthesisRequest(
            text=t, language=language, speaker=speaker or "-",
            sampling=dict(sampling), seed=61000 + i * 11,
            max_seconds_hint=max(6.0, len(t) / 13.0))
        try:
            if clone:
                prompt = engine._prompt if getattr(engine, "_prompt", None) \
                    else None
                res = engine.synthesize(req)
            else:
                out = generate_with_qc(engine, req, t, qc, max_attempts=3,
                                       min_score=75)
                best = out.get("best")
                if best is None or best.waveform is None:
                    err += 1
                    results.append({"error": "Synthese fehlgeschlagen"})
                    continue
                regen += max(0, len(out.get("attempts", [])) - 1)
                res = best
            score_obj, metrics = qc.check(res.waveform, res.sample_rate, t)
            write_wav(out_dir / f"{i:02d}.wav", res.waveform,
                      res.sample_rate, bit_depth=16)
            ok_count += 1
            results.append({
                "qc": round(score_obj.overall, 1),
                "pronunciation": round(
                    score_obj.pronunciation_plausibility, 1),
                "naturalness": round(score_obj.naturalness, 1),
                "prosody": round(score_obj.prosody, 1),
                "integrity": round(score_obj.audio_integrity, 1),
                "duration_s": metrics.get("duration_s"),
                "issues": score_obj.issues,
            })
        except Exception as e:                        # noqa: BLE001
            err += 1
            results.append({"error": str(e)[:200]})
    ok = [r for r in results if "qc" in r]
    return {
        "audio_ok": ok_count, "errors": err, "regenerations": regen,
        "segments": len(texts),
        "qc": round(float(np.mean([r["qc"] for r in ok])), 1) if ok else 0,
        "pronunciation": round(float(np.mean(
            [r["pronunciation"] for r in ok])), 1) if ok else 0,
        "naturalness": round(float(np.mean(
            [r["naturalness"] for r in ok])), 1) if ok else 0,
        "prosody": round(float(np.mean(
            [r["prosody"] for r in ok])), 1) if ok else 0,
        "integrity": round(float(np.mean(
            [r["integrity"] for r in ok])), 1) if ok else 0,
        "results": results,
    }


def _classify(voice_id: str, de: dict, en: dict) -> tuple[str, str]:
    if voice_id == "vd_e":
        return "Empfohlen", "Produktionsstandard (locked)"
    m = min(de.get("qc", 0), en.get("qc", 0))
    errs = de.get("errors", 0) + en.get("errors", 0)
    if errs:
        return "Experimentell", f"{errs} Fehler im Test"
    if m >= 85:
        return "Sehr gut", ""
    if m >= 72:
        return "Gut", ""
    return "Experimentell", f"QC {m}"


def run_desktop_voice_benchmark(studio=None) -> dict:
    """§15: alle Stimmen DE+EN testen, Report + Klassifikation."""
    out_base = paths.BENCHMARK_DIR / "desktop_voices"
    out_base.mkdir(parents=True, exist_ok=True)
    registry = VoiceRegistry()
    production = load_production()
    voices_out = []
    for entry in registry.entries():
        vid = entry.voice_id
        log.info("Desktop-Voice-Test: %s", vid)
        try:
            if entry.backend_mode == "clone":
                from ..security.identity_lock import assert_vd_e_usable
                assert_vd_e_usable(production)
                if studio is not None:
                    from ..tts.test_double import TestDoubleCloneEngine
                    engine = TestDoubleCloneEngine(allow_design=False)
                else:
                    from ..hardware.detector import detect_hardware
                    from ..tts.qwen_engine import VoiceCloneEngine
                    engine = VoiceCloneEngine(
                        detect_hardware(), candidate_id="VD-E",
                        description="produktion", allow_design=False)
                engine.load()
                de = _score_texts(engine, None, [DE_TEST, DE_LONG],
                                  "German", out_base / vid / "de",
                                  clone=True)
                en = _score_texts(engine, None, [EN_TEST, EN_LONG],
                                  "English", out_base / vid / "en",
                                  clone=True)
            else:
                if studio is not None:
                    from ..tts.test_double import TestDoubleEngine
                    engine = TestDoubleEngine()
                else:
                    from ..jobs.runner import build_engine
                    engine, _e = build_engine(
                        _spec_for(vid), production)
                engine.load()
                de = _score_texts(engine, entry.speaker_name,
                                  [DE_TEST, DE_LONG], "German",
                                  out_base / vid / "de", clone=False)
                en = _score_texts(engine, entry.speaker_name,
                                  [EN_TEST, EN_LONG], "English",
                                  out_base / vid / "en", clone=False)
        except Exception as e:                        # noqa: BLE001
            log.exception("Voice-Test %s fehlgeschlagen", vid)
            voices_out.append({"voice_id": vid,
                               "display_name": entry.display_name,
                               "error": str(e)[:300],
                               "class": "Experimentell",
                               "note": "Test fehlgeschlagen"})
            continue
        klass, note = _classify(vid, de, en)
        voices_out.append({
            "voice_id": vid, "display_name": entry.display_name,
            "gender": entry.gender, "class": klass, "note": note,
            "de": de, "en": en,
            "de_score": de.get("qc"), "en_score": en.get("qc"),
        })
        qlog(f"DESKTOP-VOICE {vid}: DE={de.get('qc')} EN={en.get('qc')} "
             f"-> {klass}")
    report = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
              "voices": voices_out}
    write_json(out_base / "report.json", report)
    _write_md(out_base / "report.md", report)
    return report


def _spec_for(voice_id: str):
    from ..jobs.runner import JobSpec
    return JobSpec(voice_id=voice_id)


def _write_md(path: Path, report: dict) -> None:
    lines = ["# Desktop-Voice-Benchmark (§15)", "",
             f"Zeit: {report['timestamp']}", "",
             "> Klassifikation dient nur der Markierung in der GUI. "
             "VD-E bleibt unabhängig davon Standard (locked).", "",
             "| Stimme | Typ | DE-QC | EN-QC | Aussprache | Natürlich | "
             "Prosodie | Integrität | Fehler | Klasse |", "|" + "---|" * 10]
    for v in report["voices"]:
        if v.get("error"):
            lines.append(f"| {v['display_name']} | | FEHLER: "
                         f"{v['error'][:40]} | | | | | | {v['class']} |")
            continue
        de, en = v.get("de", {}), v.get("en", {})
        lines.append(
            f"| {v['display_name']} | {v.get('gender')} "
            f"| {de.get('qc')} | {en.get('qc')} "
            f"| {de.get('pronunciation')}/{en.get('pronunciation')} "
            f"| {de.get('naturalness')}/{en.get('naturalness')} "
            f"| {de.get('prosody')}/{en.get('prosody')} "
            f"| {de.get('integrity')}/{en.get('integrity')} "
            f"| {de.get('errors', 0) + en.get('errors', 0)} "
            f"| {v['class']} {v.get('note', '')} |")
    path.write_text("\n".join(lines), encoding="utf-8")
