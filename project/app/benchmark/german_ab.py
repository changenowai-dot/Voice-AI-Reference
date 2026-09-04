"""Deutsche Baseline & A/B-Benchmark (Phase 1, Anforderung 5 + 25 + 31).

Ablauf:
1. ``ensure_baseline``  – erzeugt EINMAL die unveränderbare Baseline
   (v1.0-Konfiguration: klassischer Instruct, balanced-Sampling,
   Segmentgröße 420) über GERMAN-01…12. Audio + Metriken + Scores +
   Parameter landen in ``benchmark/baseline/``. Ein vorhandene Baseline
   wird geschützt (Anforderung: darf niemals verloren gehen).
2. ``run_ab`` – testet gestuft und kontrolliert:
      Stufe 1: Instruct-Varianten (§15/§16)
      Stufe 2: Sampling-Sets (stable/expressive)
      Stufe 3: Segmentgrößen (220/700) auf dem Long-Form-Text
   Jede Variante schreibt Audio nach ``benchmark/optimized/<id>/`` und
   wird gegen die Baseline UND die bisher beste Variante verglichen
   (Vorher/Nachher, §47). Der Bericht landet in
   ``benchmark/comparisons/report_AB.md``; die Gewinnereinstellungen
   werden in config/config.json übernommen.

Alle Messungen nutzen den GermanNaturalnessScore als VERGLEICHSmaßstab
(keine absolute Menschlichkeitsmessung, Anforderung 24/38).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from .. import config as cfgmod
from .. import paths
from ..audio.io import write_wav
from ..logging_setup import get_logger, plog, qlog
from ..prosody.instruct import INSTRUCT_VARIANTS, variant_text
from ..quality.german_score import score_german
from ..quality.metrics import analyze_segment_audio
from ..tts.engine_base import SynthesisRequest
from ..tts.sampler import PARAM_SETS, params_for_set
from ..utils import read_json, write_json
from .german_texts import GERMAN_TEXTS, category_map

log = get_logger("german_ab")

BASELINE_DIR = paths.BENCHMARK_DIR / "baseline"
OPTIMIZED_DIR = paths.BENCHMARK_DIR / "optimized"
COMPARISONS_DIR = paths.BENCHMARK_DIR / "comparisons"

# v1.0-Referenzkonfiguration (Baseline-Definition)
BASELINE_PARAMS = {
    "instruct_variant": "de_doc_classic",
    "sampling": "balanced",
    "segment_target_chars": 420,
    "speaker": "Ryan",
    "seed_base": 7301,
}


# ---------------------------------------------------------------------------
# Bewertung einer Variante
# ---------------------------------------------------------------------------

def _score_texts(engine, texts: list[dict], *, instruct: str,
                 sampling: dict, speaker: str, seed_base: int,
                 out_dir: Path | None, label: str) -> dict:
    """Erzeugt + bewertet alle Texte mit einer festen Konfiguration."""
    results = []
    for i, t in enumerate(texts):
        req = SynthesisRequest(
            text=t["text"], language="German", speaker=speaker,
            instruct=instruct, sampling=dict(sampling),
            seed=seed_base + i * 17,
            max_seconds_hint=max(6.0, len(t["text"]) / 13.0))
        try:
            res = engine.synthesize(req)
        except Exception as e:                          # noqa: BLE001
            log.warning("[%s] %s fehlgeschlagen: %s", label, t["id"], e)
            results.append({"id": t["id"], "error": str(e),
                            "german": None})
            continue
        g = score_german(res.waveform, res.sample_rate, t["text"])
        m = analyze_segment_audio(res.waveform, res.sample_rate)
        m["realtime_factor"] = res.realtime_factor
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            write_wav(out_dir / f"{t['id']}.wav", res.waveform,
                      res.sample_rate, bit_depth=16)
        results.append({
            "id": t["id"], "category": t["category"],
            "german": g.to_dict(),
            "duration_s": m["duration_s"],
            "f0_median_hz": m.get("f0_median_hz"),
            "realtime_factor": m.get("realtime_factor"),
        })
    valid = [r for r in results if r.get("german")]
    scores = [r["german"]["overall"] for r in valid]
    summary = {
        "label": label,
        "n": len(valid), "n_failed": len(results) - len(valid),
        "german_overall": round(float(np.mean(scores)), 2) if scores else 0.0,
        "naturalness": round(float(np.mean(
            [r["german"]["naturalness"] for r in valid])), 2) if valid else 0.0,
        "prosody_de": round(float(np.mean(
            [r["german"]["prosody_de"] for r in valid])), 2) if valid else 0.0,
        "rhythm": round(float(np.mean(
            [r["german"]["rhythm"] for r in valid])), 2) if valid else 0.0,
        "pronunciation": round(float(np.mean(
            [r["german"]["pronunciation"] for r in valid])), 2) if valid else 0.0,
        "critical_count": sum(1 for r in valid if r["german"].get("critical")),
        "results": results,
    }
    return summary


def _variant_key(summary: dict) -> float:
    """Vergleichsschlüssel: Qualität vor Tempo (Anforderung 63/32)."""
    return (summary["german_overall"]
            - 5.0 * summary.get("critical_count", 0)
            + 0.25 * summary["prosody_de"])


# ---------------------------------------------------------------------------
# 1) Baseline (unveränderbar)
# ---------------------------------------------------------------------------

def ensure_baseline(engine, force: bool = False) -> dict:
    manifest = BASELINE_DIR / "manifest.json"
    if manifest.exists() and not force:
        log.info("Baseline vorhanden – wird geschützt: %s", manifest)
        return read_json(manifest, {}) or {}
    if BASELINE_DIR.exists() and force:
        import shutil
        bak = BASELINE_DIR.with_name(
            f"baseline_backup_{time.strftime('%Y%m%d_%H%M%S')}")
        shutil.copytree(BASELINE_DIR, bak)
        log.info("Alte Baseline gesichert unter %s", bak)

    params = dict(BASELINE_PARAMS)
    summary = _score_texts(
        engine, GERMAN_TEXTS,
        instruct=variant_text(params["instruct_variant"]),
        sampling=params_for_set(params["sampling"]),
        speaker=params["speaker"], seed_base=params["seed_base"],
        out_dir=BASELINE_DIR, label="baseline")
    summary["params"] = params
    summary["created"] = time.strftime("%Y-%m-%d %H:%M:%S")
    summary["engine"] = engine.info()
    write_json(manifest, summary)
    qlog(f"GERMAN-BASELINE erstellt: DE-Score {summary['german_overall']} "
         f"({summary['n']} Texte, kritisch: {summary['critical_count']})")
    _write_md("baseline", summary)
    return summary


# ---------------------------------------------------------------------------
# 2) A/B-Optimierung
# ---------------------------------------------------------------------------

def run_ab(engine, quick: bool = False) -> dict:
    baseline = ensure_baseline(engine)
    base_key = _variant_key(baseline)
    cfg = cfgmod.load_config()
    speaker = ((cfg.get("voices", {}) or {}).get("speaker_map", {})
               .get("male_1", BASELINE_PARAMS["speaker"]))
    german_best = (cfg.get("german", {}) or {}).get("best_speaker")
    if german_best:
        speaker = german_best

    comparisons: list[dict] = [{
        "label": "BASELINE (v1.0)", "key": round(base_key, 2),
        "german_overall": baseline.get("german_overall"),
        "critical": baseline.get("critical_count", 0),
    }]
    winner = {"instruct_variant": BASELINE_PARAMS["instruct_variant"],
              "sampling": BASELINE_PARAMS["sampling"],
              "segment_target_chars": BASELINE_PARAMS["segment_target_chars"],
              "german_overall": baseline.get("german_overall", 0.0)}
    best_key = base_key

    # ---------- Stufe 1: Instruct-Varianten (§15) --------------------------
    texts = GERMAN_TEXTS
    if quick:
        texts = [t for t in GERMAN_TEXTS
                 if t["id"] in ("GERMAN-01", "GERMAN-03", "GERMAN-04",
                                "GERMAN-08", "GERMAN-10")]
    for vid in ("de_doc_native", "de_audiobook", "de_psych",
                "de_restrained", "de_calm_authoritative", "de_cinematic",
                "de_lang_de"):
        summary = _score_texts(
            engine, texts,
            instruct=variant_text(vid),
            sampling=params_for_set(winner["sampling"]),
            speaker=speaker, seed_base=BASELINE_PARAMS["seed_base"],
            out_dir=OPTIMIZED_DIR / vid, label=vid)
        key = _variant_key(summary)
        comparisons.append({"label": vid, "key": round(key, 2),
                            "german_overall": summary["german_overall"],
                            "critical": summary.get("critical_count", 0)})
        write_json(OPTIMIZED_DIR / vid / "summary.json", summary)
        qlog(f"AB instruct {vid}: DE={summary['german_overall']} "
             f"(Baseline {baseline.get('german_overall')})")
        if key > best_key:
            best_key = key
            winner["instruct_variant"] = vid
            winner["german_overall"] = summary["german_overall"]

    # ---------- Stufe 2: Sampling-Sets (§49/§15) ---------------------------
    for sname in ("stable", "expressive"):
        summary = _score_texts(
            engine, texts,
            instruct=variant_text(winner["instruct_variant"]),
            sampling=params_for_set(sname),
            speaker=speaker, seed_base=BASELINE_PARAMS["seed_base"] + 91,
            out_dir=OPTIMIZED_DIR / f"sampling_{sname}",
            label=f"sampling_{sname}")
        key = _variant_key(summary)
        comparisons.append({"label": f"sampling_{sname}", "key": round(key, 2),
                            "german_overall": summary["german_overall"],
                            "critical": summary.get("critical_count", 0)})
        write_json(OPTIMIZED_DIR / f"sampling_{sname}" / "summary.json",
                   summary)
        if key > best_key:
            best_key = key
            winner["sampling"] = sname
            winner["german_overall"] = summary["german_overall"]

    # ---------- Stufe 3: Segmentgröße (§18, Long-Form-Text) ----------------
    # (Wirkt auf die Produktions-Pipeline; hier als Qualitätsprüfung der
    #  Prosodie-Konsistenz bei unterschiedlicher Textlänge pro Aufruf.)
    if not quick:
        lf = [t for t in GERMAN_TEXTS if t["id"] == "GERMAN-10"]
        for size_label, chunk_chars in (("seg_220", 220), ("seg_700", 700)):
            parts = _split_text(lf[0]["text"], chunk_chars)
            per_part = []
            for pi, part in enumerate(parts):
                req = SynthesisRequest(
                    text=part, language="German", speaker=speaker,
                    instruct=variant_text(winner["instruct_variant"]),
                    sampling=params_for_set(winner["sampling"]),
                    seed=BASELINE_PARAMS["seed_base"] + pi * 3,
                    max_seconds_hint=max(6.0, len(part) / 13.0))
                try:
                    res = engine.synthesize(req)
                    per_part.append(score_german(
                        res.waveform, res.sample_rate, part).to_dict())
                    write_wav(OPTIMIZED_DIR / size_label / f"part_{pi}.wav",
                              res.waveform, res.sample_rate, bit_depth=16)
                except Exception as e:                  # noqa: BLE001
                    log.warning("%s Teil %d fehlgeschlagen: %s",
                                size_label, pi, e)
            if per_part:
                mean_de = round(float(np.mean(
                    [p["overall"] for p in per_part])), 2)
                f0s = [p.get("consistency", 100) for p in per_part]
                # Konsistenz zwischen Teilen: F0-Streuung fehlt hier,
                # daher Score-Mittel + niedrige Streuung belohnen
                spread = float(np.std([p["overall"] for p in per_part]))
                key = mean_de - spread
                comparisons.append({"label": size_label,
                                    "key": round(key, 2),
                                    "german_overall": mean_de, "critical": 0})
                if key > best_key:
                    best_key = key
                    winner["segment_target_chars"] = chunk_chars
                    winner["german_overall"] = mean_de

    # ---------- Gewinnereinstellungen übernehmen ---------------------------
    applied = []
    cfg = cfgmod.load_config()
    gcfg = cfg.setdefault("german", {})
    if gcfg.get("instruct_variant") != winner["instruct_variant"]:
        gcfg["instruct_variant"] = winner["instruct_variant"]
        applied.append(f"instruct_variant={winner['instruct_variant']}")
    sp = PARAM_SETS[winner["sampling"]]
    adv = cfg.setdefault("advanced", {})
    for k in ("temperature", "top_k", "top_p", "repetition_penalty"):
        if adv.get(k) != sp[k]:
            adv[k] = sp[k]
            applied.append(f"{k}={sp[k]}")
    if adv.get("segment_target_chars") != winner["segment_target_chars"]:
        adv["segment_target_chars"] = winner["segment_target_chars"]
        applied.append(
            f"segment_target_chars={winner['segment_target_chars']}")
    cfgmod.save_config(cfg)

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "engine": engine.info(),
        "baseline": {
            "german_overall": baseline.get("german_overall"),
            "params": baseline.get("params"),
        },
        "comparisons": comparisons,
        "winner": winner,
        "applied_changes": applied,
    }
    COMPARISONS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(COMPARISONS_DIR / "report_AB.json", report)
    _write_ab_md(report)
    plog(f"GERMAN-AB fertig: Baseline DE={baseline.get('german_overall')} "
         f"-> Gewinner DE={winner['german_overall']} "
         f"({', '.join(applied) or 'keine Änderung'})")
    return report


def _split_text(text: str, chunk_chars: int) -> list[str]:
    from ..text.analyze import split_sentences
    sentences = split_sentences(text)
    parts, buf, size = [], "", 0
    for s in sentences:
        if size + len(s) > chunk_chars and buf:
            parts.append(buf.strip())
            buf, size = "", 0
        buf += " " + s
        size += len(s) + 1
    if buf.strip():
        parts.append(buf.strip())
    return parts


def _write_md(kind: str, summary: dict) -> None:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# Deutsche Baseline (unveränderbar)", "",
             f"Erstellt: {summary.get('created')}", "",
             f"| Text | Kategorie | DE-Score | Natürlichkeit | Melodie | "
             f"Rhythmus | Aussprache |", "|" + "---|" * 6]
    for r in summary.get("results", []):
        g = r.get("german") or {}
        lines.append(
            f"| {r['id']} | {r.get('category', '')} "
            f"| {g.get('overall', '-')} | {g.get('naturalness', '-')} "
            f"| {g.get('prosody_de', '-')} | {g.get('rhythm', '-')} "
            f"| {g.get('pronunciation', '-')} |")
    lines.append("")
    lines.append(f"**DE-Gesamt: {summary.get('german_overall')}** "
                 f"(kritisch: {summary.get('critical_count')})")
    (BASELINE_DIR / "report_baseline.md").write_text(
        "\n".join(lines), encoding="utf-8")


def _write_ab_md(report: dict) -> None:
    lines = ["# Deutscher A/B-Vergleich (Phase 1)", "",
             f"Zeit: {report['timestamp']}  ",
             f"Engine: {report['engine'].get('engine_version', '?')}", "",
             f"Baseline DE-Score: **{report['baseline']['german_overall']}**",
             "",
             "| Variante | DE-Score | Vergleichsschlüssel | Kritisch |",
             "|---|---|---|---|"]
    for c in report["comparisons"]:
        lines.append(f"| {c['label']} | {c['german_overall']} "
                     f"| {c['key']} | {c.get('critical', 0)} |")
    lines += ["", f"**Gewinner:** `{report['winner']['instruct_variant']}` / "
              f"sampling `{report['winner']['sampling']}` / "
              f"Segmentgröße {report['winner']['segment_target_chars']} "
              f"(DE-Score {report['winner']['german_overall']})", ""]
    lines.append("Übernommene Änderungen: " +
                 (", ".join(report["applied_changes"]) or "keine"))
    lines += ["", "> Hinweis: Scores sind interne VERGLEICHSmaßstäbe auf",
              "> Signalebene (keine Messung menschlicher Wahrnehmung).",
              "> Hörproben: benchmark/baseline/, benchmark/optimized/."]
    (COMPARISONS_DIR / "report_AB.md").write_text("\n".join(lines),
                                                  encoding="utf-8")
