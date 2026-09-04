"""Phase 3 – Referenz-erhaltende Optimierung der VD-E-Stimme (§19–24).

Grundsatz REFERENCE-PRESERVING (§23):
- Die VD-E-Referenz (Human-Preferred, „Sample I“) wird GESCHLOSSEN:
  Hash-Manifest, nie neu generiert, nie verändert.
- Keine Variante ändert Stimme/Timbre/Tempo grundsätzlich; optimiert
  werden ausschließlich Textebene (Fachwörter), subtile Sampling-
  Variation und Pausen. Voice-Guard prüft die Tonhöhen-Bandtreue.

Batterien (§20, §21, §22):
  TECH      – Fach-/Fremdwortsätze (Kybalion, Theorie, Quantentheorie …)
  EMOTION   – 12 subtile Zustände (nur inhaltsausgelöst)
  VARIATION – strukturgleiche Sätze (Melodie-Vielfalt)
  MELODY    – Satzrollen-Mix
  LONG      – Kybalion-Text komplett

Varianten:
  BASE      – aktueller Zustand (tech OFF, variation OFF) = Vorher
  TECH      – + Fachwort-Germanisierung
  VAR       – + semantische Sampling-Variation
  TECHVAR   – beides (Erwartungssieger, wird NICHT behauptet sondern
              gemessen + vom Nutzer blind gehört)

Ausgaben NUR unter benchmark/phase3/ (§2-Analogie). Blindvergleich mit
neutralen Buchstaben; apply() ändert NUR Schalter (tech/variation),
niemals die Stimme (§23).
"""
from __future__ import annotations

import hashlib
import random
import time
from pathlib import Path

import numpy as np

from .. import config as cfgmod
from .. import paths
from ..audio.ebu_r128 import integrated_lufs
from ..audio.io import read_wav, write_wav
from ..logging_setup import get_logger, plog, qlog
from ..prosody.instruct import VOICEDESIGN_DESCRIPTIONS
from ..prosody.variation import (apply_sampling_offsets,
                                 detect_subtle_emotion, sampling_offsets,
                                 variation_report)
from ..quality.german_score import f0_series, score_german
from ..segmentation import SegmentationConfig, segment_text
from ..text.analyze import split_blocks
from ..text.normalize import NormalizationReport, normalize_text
from ..tts.engine_base import SynthesisRequest
from ..tts.sampler import params_for_set
from ..utils import read_json, sha256_file, write_json
from .phase2_texts import KYBALION_TEXT

log = get_logger("phase3")

PHASE3_DIR = paths.BENCHMARK_DIR / "phase3"
REF_CANDIDATE = "VD-E"                      # Human-Preferred (§19)
F0_BAND = (0.82, 1.22)                      # Voice-Guard-Toleranz (§23)

# ---------------------------------------------------------------------------
# Test-Batterien
# ---------------------------------------------------------------------------
TECH_SENTENCES = [
    "Die Quantentheorie verändert unser Bild der Wirklichkeit.",
    "Jede Theorie bleibt vorläufig, auch diese.",
    "Das Kybalion beansprucht ein altertümliches Wissen.",
    "Relativitätstheorie, Entropie und Quantenmechanik formen die Physik.",
    "Seine philosophische Haltung blieb grundsätzlich skeptisch.",
    "Die Psychologie spricht von Kognition und Dissonanz.",
]

EMOTION_SENTENCES = [
    ("curious", "Was aber, wenn diese Frage richtig gestellt war?"),
    ("reflective", "Vielleicht liegt die Antwort näher, als wir denken."),
    ("surprised", "Und plötzlich war alles anders."),
    ("suspense", "Doch hinter der Tür wartete etwas."),
    ("menace", "Etwas Dunkles begann, sich zu recken."),
    ("awe", "Unendlich viele Galaxien, und jede ein Gedanke."),
    ("calm", "Danach wurde es still."),
    ("confident", "Wir werden es verstehen."),
    ("doubtful", "Vielleicht irren wir uns auch hier."),
    ("realization", "Und dann wird klar, worum es wirklich ging."),
    ("skeptical", "Sogenannte Gewissheit, behaupten sie."),
    ("serious", "Diese Wahrheit ist alt und schwer."),
]

VARIATION_SENTENCES = [
    "Sieben Gesetze tragen das Universum.",
    "Sieben Prinzipien tragen das Denken.",
    "Sieben Regeln tragen die Ordnung.",
    "Sieben Siegel tragen das Geheimnis.",
]

MELODY_SENTENCES = [
    "Es gibt ein Buch, das niemand geschrieben haben will.",
    "Doch sein Inhalt beansprucht ein Alter, das jede Zeitrechnung sprengt.",
    ("Wer sie versteht, besitzt den Schlüssel zum Bauplan der "
     "Wirklichkeit."),
    "Für die meisten blieb dies eine mystische Behauptung.",
    "Doch etwas Merkwürdiges geschieht, wenn man sie heute betrachtet.",
]


def _tts_text(text: str, tech: bool) -> str:
    from ..pronunciation import PronunciationEngine
    from ..pronunciation.dictionary import PronunciationDictionary
    d = PronunciationDictionary()
    eng = PronunciationEngine(d, tech_germanization=tech)
    norm = normalize_text(text, "German", NormalizationReport())
    return eng.process(norm, "German", collect_meta=False).text


# ---------------------------------------------------------------------------
# Referenz-Schutz (§23)
# ---------------------------------------------------------------------------
def reference_path() -> Path:
    return paths.VOICE_REFS_DIR / f"{REF_CANDIDATE}.wav"


def ensure_reference(studio) -> Path:
    """VD-E-Referenz: vorhanden → sperren; sonst einmalig erzeugen."""
    paths.VOICE_REFS_DIR.mkdir(parents=True, exist_ok=True)
    path = reference_path()
    if not path.exists():
        desc = VOICEDESIGN_DESCRIPTIONS["vd_e"]["description"]
        ref = studio.design_reference(REF_CANDIDATE, desc)
        path = ref.wav_path
    manifest = {
        "candidate_id": REF_CANDIDATE,
        "locked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sha256": sha256_file(path),
        "note": "Human-Preferred-Reference (Sample I) – nicht verändern "
                "(§23 REFERENCE-PRESERVING).",
    }
    write_json(PHASE3_DIR / "reference_lock.json", manifest)
    return path


def reference_f0(path: Path) -> float | None:
    try:
        wav, sr = read_wav(path)
    except Exception:
        return None
    series = [f for _, f in f0_series(wav, sr) if f > 0]
    return float(np.median(series)) if series else None


# ---------------------------------------------------------------------------
# Bewertung
# ---------------------------------------------------------------------------
def _score_battery(studio, prompt, texts: list, out_dir: Path, *,
                   tech: bool, variation: bool,
                   seed_base: int) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    base_sampling = params_for_set("balanced")
    results = []
    wavs, srs, durs = [], [], []
    for i, raw in enumerate(texts):
        tts = _tts_text(raw, tech)
        sampling = dict(base_sampling)
        if variation:
            from ..prosody.german import dominant_role
            sem, se_int = detect_subtle_emotion(tts)
            sampling = apply_sampling_offsets(
                sampling, sampling_offsets(dominant_role(tts), sem, se_int,
                                           "subtle"))
        req = SynthesisRequest(text=tts, language="German", speaker="-",
                               instruct="", sampling=sampling,
                               seed=seed_base + i * 7,
                               max_seconds_hint=max(6.0, len(tts) / 13))
        res = studio.synth_clone(prompt, req)
        g = score_german(res.waveform, res.sample_rate, tts)
        write_wav(out_dir / f"{i:02d}.wav", res.waveform, res.sample_rate,
                  bit_depth=16)
        results.append({"de": g.to_dict(),
                        "dur": res.duration_s})
        wavs.append(res.waveform)
        srs.append(res.sample_rate)
        durs.append(res.duration_s)
    de = [r["de"]["overall"] for r in results]
    var = variation_report(wavs, srs, [0.5] * len(wavs))
    return {
        "de_mean": round(float(np.mean(de)), 2),
        "pronunciation": round(float(np.mean(
            [r["de"]["pronunciation"] for r in results])), 2),
        "naturalness": round(float(np.mean(
            [r["de"]["naturalness"] for r in results])), 2),
        "prosody_de": round(float(np.mean(
            [r["de"]["prosody_de"] for r in results])), 2),
        "critical": sum(1 for r in results if r["de"].get("critical")),
        "variation": var,
        "files": [str(out_dir / f"{i:02d}.wav") for i in range(len(texts))],
    }


def run_phase3(studio, quick: bool = False) -> dict:
    PHASE3_DIR.mkdir(parents=True, exist_ok=True)
    (PHASE3_DIR / "comparisons").mkdir(exist_ok=True)
    (PHASE3_DIR / "blind").mkdir(exist_ok=True)

    # 1) Referenz schützen + Clone-Prompt (bleibt für ALLE Varianten identisch)
    ref = ensure_reference(studio)
    ref_f0 = reference_f0(ref)
    prompt = studio.build_clone_prompt(_mk_ref_obj(ref))

    batteries = {
        "TECH": TECH_SENTENCES,
        "EMOTION": [t for _, t in EMOTION_SENTENCES],
        "VARIATION": VARIATION_SENTENCES,
        "MELODY": MELODY_SENTENCES,
    }
    if not quick:
        batteries["LONG"] = None  # Kybalion via Segmentierung unten

    variants = {
        "BASE": {"tech": False, "variation": False},
        "TECH": {"tech": True, "variation": False},
        "VAR": {"tech": False, "variation": True},
        "TECHVAR": {"tech": True, "variation": True},
    }
    results = {}
    for vid, flags in variants.items():
        vdir = PHASE3_DIR / "voicedesign" / vid
        scores = {}
        f0s = []
        for name, texts in batteries.items():
            if texts is None:
                texts = _kybalion_tts_texts(flags["tech"])
            s = _score_battery(studio, prompt, texts, vdir / name,
                               tech=flags["tech"],
                               variation=flags["variation"], seed_base=9300)
            scores[name] = s
            for f in s["files"]:
                f0 = reference_f0(Path(f))
                if f0:
                    f0s.append(f0)
        # Voice-Guard (§23): Median-F0 über alle Batterien nahe Referenz
        f0_med = float(np.median(f0s)) if f0s else None
        guard_ok = (ref_f0 is None or f0_med is None or
                    F0_BAND[0] <= f0_med / ref_f0 <= F0_BAND[1])
        results[vid] = {
            "flags": flags,
            "batteries": scores,
            "f0_median": round(f0_med, 1) if f0_med else None,
            "reference_f0": round(ref_f0, 1) if ref_f0 else None,
            "voice_guard_ok": guard_ok,
            "composite": round(float(np.mean(
                [b["de_mean"] for b in scores.values()])), 2),
        }
        qlog(f"PHASE3 {vid}: composite={results[vid]['composite']} "
             f"F0={results[vid]['f0_median']} guard={guard_ok}")

    # LONG-Datei (komplettes Kybalion je Variante)
    for vid, flags in variants.items():
        _assemble_long(studio, prompt, flags, PHASE3_DIR / "voicedesign" /
                       vid / "LONG_full.wav")

    # Empfehlung: composite + Guard + Aussprache-Gewichtung (§20 Priorität)
    def key(vid):
        r = results[vid]
        tech_bonus = 0.6 * np.mean([b["pronunciation"] for b in
                                    r["batteries"].values()]) / 10
        return (r["composite"] + tech_bonus + (5 if r["voice_guard_ok"]
                                               else -20))
    ranked = sorted(variants, key=lambda v: -key(v))
    recommended = ranked[0] if results[ranked[0]]["voice_guard_ok"] else None

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "reference": {"candidate": REF_CANDIDATE, "f0": ref_f0,
                      "locked": True, "path": str(ref)},
        "quick": quick,
        "variants": results,
        "ranked": ranked,
        "recommended": recommended,
        "user_pick_required": True,
    }
    write_json(PHASE3_DIR / "comparisons" / "report_phase3.json", report)
    _write_blind(results, variants, quick)
    _write_md(report)
    plog(f"PHASE3 fertig: ranking={ranked}, Empfehlung={recommended}, "
         f"Referenz F0={ref_f0}")
    return report


def _mk_ref_obj(path: Path):
    from ..prosody.instruct import VOICEDESIGN_REF_TEXT_DE
    from ..tts.voice_studio import VoiceRef
    return VoiceRef(candidate_id=REF_CANDIDATE,
                    description=VOICEDESIGN_DESCRIPTIONS["vd_e"]
                    ["description"],
                    ref_text=VOICEDESIGN_REF_TEXT_DE, wav_path=path)


def _kybalion_tts_texts(tech: bool) -> list[str]:
    rep = NormalizationReport()
    from ..pronunciation import PronunciationEngine
    eng = PronunciationEngine(tech_germanization=tech)

    def provider(block):
        return eng.process(normalize_text(block.text, "German", rep),
                           "German").text
    segs = segment_text(split_blocks(KYBALION_TEXT), provider,
                        SegmentationConfig(target_chars=300, min_chars=100,
                                           max_chars=500))
    return [s.text for s in segs]


def _assemble_long(studio, prompt, flags: dict, out_path: Path) -> None:
    from ..audio.assemble import assemble
    from ..segmentation import Segment
    texts = _kybalion_tts_texts(flags["tech"])
    base = params_for_set("balanced")
    wavs = []
    for i, tts in enumerate(texts):
        sampling = dict(base)
        if flags["variation"]:
            from ..prosody.german import dominant_role
            sem, se_int = detect_subtle_emotion(tts)
            sampling = apply_sampling_offsets(
                sampling, sampling_offsets(dominant_role(tts), sem, se_int,
                                           "subtle"))
        req = SynthesisRequest(text=tts, language="German", speaker="-",
                               sampling=sampling, seed=9300 + i * 7)
        res = studio.synth_clone(prompt, req)
        seg = Segment(index=i, text=tts, pause_after_s=0.5)
        wavs.append((res.waveform, res.sample_rate, seg))
    assembled, sr = assemble(wavs)
    write_wav(out_path, assembled, sr, bit_depth=16)


def _write_blind(results, variants, quick) -> None:
    blind_dir = PHASE3_DIR / "blind"
    for old in blind_dir.glob("sample_*.wav"):
        old.unlink()
    order = list(variants)
    rng = random.Random(20260830)
    rng.shuffle(order)
    mapping = {}
    for letter, vid in zip([chr(ord("A") + i) for i in range(len(order))],
                           order):
        src = PHASE3_DIR / "voicedesign" / vid / "LONG" / "00.wav"
        if not src.exists():                      # quick ohne LONG-Batterie
            srcs = sorted((PHASE3_DIR / "voicedesign" / vid).rglob("00.wav"))
            src = srcs[0] if srcs else None
        if src and src.exists():
            dst = blind_dir / f"sample_{letter}.wav"
            dst.write_bytes(src.read_bytes())
            mapping[letter] = vid
    write_json(blind_dir / "blind_key.json",
               {"created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "mapping": mapping})


def _write_md(report: dict) -> None:
    lines = ["# Phase 3 – Referenz-erhaltende Optimierung (VD-E)", "",
             f"Zeit: {report['timestamp']}  ",
             f"Referenz: {report['reference']['candidate']} (gesperrt, "
             f"F0 {report['reference']['f0']} Hz)", "",
             "> Achtung: Scores sind Vergleichsmaßstäbe. Die finale "
             "Wahl trifft der Nutzer im Blindvergleich (Sample A–…); die "
             "Stimme VD-E selbst bleibt in allen Varianten identisch "
             "(§23).", "",
             "| Variante | Fachwörter | Variation | Composite | Aussprache "
             "(TECH) | F0 | Voice-Guard |", "|" + "---|" * 7]
    for vid, r in report["variants"].items():
        tech = r["batteries"].get("TECH", {})
        lines.append(
            f"| {vid} | {'an' if r['flags']['tech'] else 'aus'} "
            f"| {'an' if r['flags']['variation'] else 'aus'} "
            f"| {r['composite']} | {tech.get('pronunciation', '-')} "
            f"| {r['f0_median']} | {'OK' if r['voice_guard_ok'] else 'ABW'} |")
    lines += ["", f"Ranking: {', '.join(report['ranked'])}",
              f"Empfehlung: **{report['recommended']}** "
              "(bestätigen durch Blindvergleich)", "",
              "Blindproben: `benchmark/phase3/blind/sample_X.wav` → "
              "UI ‚Phase 3‘ oder `--phase3-pick X` → `--phase3-apply`."]
    (PHASE3_DIR / "comparisons" / "report_phase3.md").write_text(
        "\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Status / Auswahl / Übernahme (stimmt nie die Stimme an, §23)
# ---------------------------------------------------------------------------
def phase3_status() -> dict:
    key = read_json(PHASE3_DIR / "blind" / "blind_key.json", None)
    pick = read_json(PHASE3_DIR / "blind" / "user_pick.json", None)
    report = read_json(PHASE3_DIR / "comparisons" / "report_phase3.json",
                       None)
    samples = sorted(p.stem.split("_")[1] for p in
                     (PHASE3_DIR / "blind").glob("sample_*.wav"))
    picked = bool(pick)
    return {
        "has_run": bool(report),
        "samples": samples,
        "picked": picked,
        "pick": (pick or {}).get("letter"),
        "mapping": (key or {}).get("mapping") if picked else None,
        "recommended": (report or {}).get("recommended"),
        "variants": ([{"id": vid, "flags": r["flags"],
                       "composite": r["composite"],
                       "voice_guard_ok": r["voice_guard_ok"]}
                      for vid, r in (report or {}).get("variants", {}).items()]
                     if picked else None),
    }


def save_phase3_pick(letter: str) -> dict:
    key = read_json(PHASE3_DIR / "blind" / "blind_key.json", {}) or {}
    mapping = key.get("mapping", {})
    letter = letter.strip().upper()
    if letter not in mapping:
        raise ValueError(f"Unbekannte Phase-3-Blindprobe: {letter!r} "
                         f"(erlaubt: {sorted(mapping)})")
    write_json(PHASE3_DIR / "blind" / "user_pick.json", {
        "letter": letter, "variant": mapping[letter],
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
    qlog(f"PHASE3 Nutzer-Blindauswahl: {letter} -> {mapping[letter]}")
    return phase3_status()


def apply_phase3_pick(variant_id: str | None = None) -> dict:
    """Übernimmt NUR Schalter – die VD-E-Stimme bleibt Referenz (§23)."""
    if variant_id is None:
        pick = read_json(PHASE3_DIR / "blind" / "user_pick.json", {}) or {}
        variant_id = pick.get("variant")
    if not variant_id:
        raise ValueError("Keine Phase-3-Auswahl vorhanden.")
    report = read_json(PHASE3_DIR / "comparisons" / "report_phase3.json",
                       {}) or {}
    v = (report.get("variants", {}) or {}).get(variant_id)
    if v is None:
        raise ValueError(f"Unbekannte Phase-3-Variante: {variant_id!r}")
    cfg = cfgmod.load_config()
    gcfg = cfg.setdefault("german", {})
    gcfg["tech_germanization"] = bool(v["flags"]["tech"])
    gcfg.setdefault("variation", {})["enabled"] = bool(v["flags"]["variation"])
    gcfg["engine_mode"] = "voicedesign"
    gcfg["voicedesign"] = {"candidate_id": REF_CANDIDATE,
                           "description": VOICEDESIGN_DESCRIPTIONS["vd_e"]
                           ["description"]}
    cfgmod.save_config(cfg)
    applied = (f"VD-E + tech_germanization={v['flags']['tech']}, "
               f"variation={v['flags']['variation']}")
    qlog(f"PHASE3 angewandt: {applied}")
    return {"ok": True, "applied": applied, "variant": variant_id}
