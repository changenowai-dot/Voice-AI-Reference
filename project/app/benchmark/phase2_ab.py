"""Phase-2-Vergleich: CustomVoice vs. VoiceDesign (§17–§20, §23).

Schützt Phase 1 strikt (§2): ALLE Ausgaben landen unter
``benchmark/phase2/`` – Baseline/Konfiguration/Audio/Berichte der
Phase 1 werden nie angetastet (harter Pfad-Check unten).

Kandidaten (§17):
  PHASE1-CURRENT   – exakt die Konfiguration des Nutzers (Legacy-Instruct,
                     so wie er sie gehört hat)
  PHASE1-BEST-*    – CustomVoice-Sweep (beste Instruct-Varianten × Speaker)
  VOICEDESIGN-A…F  – gestaltete Stimmen (Design->Clone, langformstabil)
  VD-B-DIRECT      – VoiceDesign ohne Clone (nur Volltest; Vergleich der
                     Konsistenz-Strategie)

Blindvergleich (§18): neutrale Dateien ``blind/sample_A.wav…`` mit
separatem Schlüssel ``blind_key.json``. Der automatische Score entscheidet
NICHT allein (§18/§20): ``recommendation.json`` enthält nur eine
Empfehlung; übernommen wird erst nach Nutzer-Auswahl (§23).
"""
from __future__ import annotations

import random
import time
from pathlib import Path

import numpy as np

from .. import config as cfgmod
from .. import paths
from ..audio.assemble import assemble
from ..audio.ebu_r128 import integrated_lufs
from ..audio.io import write_wav
from ..logging_setup import get_logger, plog, qlog
from ..prosody import (VOICEDESIGN_DESCRIPTIONS, build_instruct,
                       assign_pauses, variant_text)
from ..prosody.german import dominant_role, profile_sentence
from ..prosody.instruct import detect_emotion
from ..quality.german_score import f0_series, score_german
from ..segmentation import SegmentationConfig, segment_text
from ..text.analyze import split_blocks
from ..text.normalize import NormalizationReport, normalize_text
from ..tts.engine_base import SynthesisRequest
from ..tts.sampler import PARAM_SET_VERSION, params_for_set
from ..utils import read_json, write_json
from .phase2_texts import KYBALION_TEXT

log = get_logger("phase2")

PHASE2_DIR = paths.BENCHMARK_DIR / "phase2"
SUBDIRS = ("baseline", "customvoice", "voicedesign", "comparisons", "blind",
           "pause_probe")

# Phase-1-Verzeichnisse, die NIE geschrieben werden dürfen (§2)
_PROTECTED = [paths.BENCHMARK_DIR / "baseline", paths.BENCHMARK_DIR /
              "optimized", paths.BENCHMARK_DIR / "comparisons"]


def ensure_phase2_dirs() -> Path:
    for d in _PROTECTED:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)   # nur anlegen, nie löschen
    for sub in SUBDIRS:
        (PHASE2_DIR / sub).mkdir(parents=True, exist_ok=True)
    return PHASE2_DIR


def assert_no_phase1_write(path: Path) -> None:
    p = Path(path).resolve()
    for prot in _PROTECTED:
        if str(p).startswith(str(prot.resolve())):
            raise RuntimeError(f"Schutzverletzung: {p} liegt in Phase-1-"
                               f"Verzeichnis {prot}")


# ---------------------------------------------------------------------------
# Phase-1-Instruct-Emulation (so klang es für den Nutzer)
# ---------------------------------------------------------------------------
def legacy_phase1_instruct(seg_text: str, variant_id: str,
                           language: str = "German") -> str:
    from ..prosody.german import german_instruct_hints
    parts = [variant_text(variant_id).strip().rstrip(".")]
    em, inten = detect_emotion(seg_text, "German")
    if em != "neutral":
        from ..prosody.instruct import _EMOTION_INSTRUCT, _INTENSITY_WORDS
        parts.append(_EMOTION_INSTRUCT[em])
        parts.append(f"Emotional coloring: {_INTENSITY_WORDS[inten]}.")
    prof = profile_sentence(seg_text)
    hints = german_instruct_hints(prof, language, is_heading=False)
    if seg_text.rstrip().endswith("?") and not hints:
        hints = ["End with a natural German rising question melody."]
    parts.extend(hints)
    parts.append("Keep voice identity, pace and loudness perfectly consistent.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Kandidaten-Definition
# ---------------------------------------------------------------------------
def build_candidates(cfg: dict, quick: bool = False) -> list[dict]:
    german_cfg = cfg.get("german", {}) or {}
    cur_variant = german_cfg.get("instruct_variant", "de_doc_native")
    spk_map = (cfg.get("voices", {}) or {}).get("speaker_map", {}) or {}
    cur_speaker = spk_map.get("male_1", "Ryan")

    cands = [{
        "id": "P1-CURRENT", "kind": "customvoice", "legacy": True,
        "speaker": cur_speaker, "variant": cur_variant,
        "label": f"PHASE1-CURRENT ({cur_variant}/{cur_speaker})",
    }]
    # CustomVoice-Sweep (§17 PHASE1-BEST-INSTRUCT)
    speakers = [cur_speaker] + [s for s in ("Uncle_Fu", "Aiden")
                                if s != cur_speaker]
    variants = ["de_doc_native", "de_audiobook"]
    if not quick:
        variants.append("de_calm_authoritative")
    seen = {(cur_variant, cur_speaker)}
    for spk in speakers[: (1 if quick else 3)]:
        for var in variants:
            if (var, spk) in seen:
                continue
            seen.add((var, spk))
            cands.append({
                "id": f"P1-{var.split('_', 1)[1].upper()[:6]}-{spk[:4].upper()}",
                "kind": "customvoice", "legacy": False, "speaker": spk,
                "variant": var,
                "label": f"PHASE1 {var} / {spk}"})
    # VoiceDesign (§3)
    vd_keys = ["vd_a", "vd_b", "vd_c"] if quick else \
        list(VOICEDESIGN_DESCRIPTIONS)
    for key in vd_keys:
        cands.append({
            "id": key.upper().replace("_", "-"),       # VD-A …
            "kind": "voicedesign", "legacy": False,
            "description_key": key,
            "description": VOICEDESIGN_DESCRIPTIONS[key]["description"],
            "label": VOICEDESIGN_DESCRIPTIONS[key]["label"],
        })
    if not quick:
        cands.append({
            "id": "VD-B-DIRECT", "kind": "voicedesign_direct",
            "legacy": False,
            "description_key": "vd_b",
            "description": VOICEDESIGN_DESCRIPTIONS["vd_b"]["description"],
            "label": "VoiceDesign B (direkt, ohne Clone)"})
    return cands


# ---------------------------------------------------------------------------
# Synthese + Bewertung eines Kandidaten
# ---------------------------------------------------------------------------
def _kybalion_segments(target_chars: int = 300) -> list:
    rep = NormalizationReport()
    pron = __import__("app.pronunciation", fromlist=["PronunciationEngine"])\
        .PronunciationEngine()

    def tts_provider(block):
        norm = normalize_text(block.text, "German", rep)
        return pron.process(norm, "German", collect_meta=False).text

    return segment_text(split_blocks(KYBALION_TEXT), tts_provider,
                        SegmentationConfig(target_chars=target_chars,
                                           min_chars=100, max_chars=500))


def _phase2_instruct(seg, idx: int, last_high_idx) -> str:
    from ..prosody.german import hint_allowed, _HIGH_AROUSAL
    instr = build_instruct(
        "", seg.text, "German", german_variant="de_doc_native",
        seg_index=idx, last_high_idx=last_high_idx,
        long_sentence=(len(seg.text.split()) > 25))
    role = dominant_role(seg.text)
    if role in _HIGH_AROUSAL and hint_allowed(idx, role, last_high_idx):
        return instr, idx
    return instr, last_high_idx


def _evaluate_candidate(studio, cand: dict, segments: list,
                        out_dir: Path, quick: bool = False) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    assert_no_phase1_write(out_dir)
    sampling = params_for_set("balanced")
    per_seg = []
    wavs: list = []
    clone_prompt = None
    ref = None
    last_high = None

    for i, seg in enumerate(segments):
        if cand["kind"] == "voicedesign":
            if ref is None:
                ref = studio.design_reference(cand["id"], cand["description"])
                clone_prompt = studio.build_clone_prompt(ref)
            instr, last_high = _phase2_instruct(seg, i, last_high)
            req = SynthesisRequest(text=seg.text, language="German",
                                   speaker="-", instruct="",
                                   sampling=dict(sampling), seed=8100 + i * 13,
                                   max_seconds_hint=max(6.0, len(seg.text) / 13))
            res = studio.synth_clone(clone_prompt, req)
        elif cand["kind"] == "voicedesign_direct":
            # Direktes VoiceDesign pro Segment (Beschreibung als Instruct)
            model = studio.pool.get("voicedesign")
            import torch
            torch.manual_seed(8100 + i * 13)
            wavs_raw, sr = model.generate_voice_design(
                text=seg.text, language="German",
                instruct=cand["description"], **dict(sampling))
            from ..tts.engine_base import SynthesisResult
            res = SynthesisResult(
                waveform=np.asarray(wavs_raw[0], dtype=np.float32),
                sample_rate=int(sr),
                duration_s=round(len(wavs_raw[0]) / sr, 3),
                elapsed_s=1.0, engine="vd-direct", params_used={})
        else:
            if cand.get("legacy"):
                instr = legacy_phase1_instruct(seg.text, cand["variant"])
            else:
                instr, last_high = _phase2_instruct(seg, i, last_high)
            req = SynthesisRequest(text=seg.text, language="German",
                                   speaker=cand["speaker"], instruct=instr,
                                   sampling=dict(sampling), seed=8100 + i * 13,
                                   max_seconds_hint=max(6.0, len(seg.text) / 13))
            res = studio.synth_customvoice(req)
        g = score_german(res.waveform, res.sample_rate, seg.text)
        f0s = [f for _, f in f0_series(res.waveform, res.sample_rate) if f > 0]
        per_seg.append({
            "de": g.to_dict(),
            "f0": float(np.median(f0s)) if f0s else 0.0,
            "lufs": integrated_lufs(res.waveform, res.sample_rate),
            "dur": res.duration_s,
        })
        wavs.append((res.waveform, res.sample_rate, seg))

    # Zwischen-Segment-Pausen (klassisch) + Zusammenfügen
    assign_pauses(segments, style="auto", speed=1.0, strategy="classic")
    from ..segmentation import Segment  # noqa: F401
    assembled, sr = assemble(wavs)
    write_wav(out_dir / "kybalion.wav", assembled, sr, bit_depth=16)

    de = [p["de"]["overall"] for p in per_seg]
    f0_all = [p["f0"] for p in per_seg if p["f0"] > 0]
    lufs_all = [p["lufs"] for p in per_seg if p["lufs"] > -60]
    durs = [p["dur"] for p in per_seg]
    rates = [len(segments[i].text) / max(durs[i], 0.1)
             for i in range(len(durs))]
    consistency = float(np.clip(
        100 - (np.std(f0_all) * 4 if f0_all else 30) -
        (max(0.0, np.std(lufs_all) - 1.0) * 10 if lufs_all else 20) -
        (np.std(rates) * 60), 0, 100)) if len(per_seg) > 1 else 80.0
    summary = {
        "id": cand["id"], "label": cand["label"], "kind": cand["kind"],
        "params": {k: cand.get(k) for k in
                   ("speaker", "variant", "description")},
        "n_segments": len(per_seg),
        "de_mean": round(float(np.mean(de)), 2),
        "naturalness": round(float(np.mean(
            [p["de"]["naturalness"] for p in per_seg])), 2),
        "prosody_de": round(float(np.mean(
            [p["de"]["prosody_de"] for p in per_seg])), 2),
        "pronunciation": round(float(np.mean(
            [p["de"]["pronunciation"] for p in per_seg])), 2),
        "rhythm": round(float(np.mean(
            [p["de"]["rhythm"] for p in per_seg])), 2),
        "pauses": round(float(np.mean(
            [p["de"]["pauses"] for p in per_seg])), 2),
        "f0_median": round(float(np.median(f0_all)), 1) if f0_all else None,
        "consistency": round(consistency, 2),
        "critical_segments": sum(1 for p in per_seg
                                 if p["de"].get("critical")),
        "total_dur_s": round(sum(durs), 1),
        "file": str(out_dir / "kybalion.wav"),
        "per_segment": per_seg,
    }
    return summary


# ---------------------------------------------------------------------------
# Hauptlauf
# ---------------------------------------------------------------------------
def run_phase2(studio, quick: bool = False, cfg: dict | None = None) -> dict:
    ensure_phase2_dirs()
    cfg = cfg or cfgmod.load_config()
    segments = _kybalion_segments()
    if not segments:
        raise RuntimeError("Kybalion-Segmentierung leer")
    candidates = build_candidates(cfg, quick=quick)

    results = []
    for cand in candidates:
        sub = "voicedesign" if cand["kind"].startswith("voicedesign") \
            else "customvoice"
        if cand["id"] == "P1-CURRENT":
            sub = "baseline"
        out_dir = PHASE2_DIR / sub / cand["id"]
        log.info("Phase-2-Kandidat: %s (%s)", cand["id"], cand["label"])
        try:
            summary = _evaluate_candidate(studio, cand, list(segments),
                                          out_dir, quick=quick)
            results.append(summary)
            qlog(f"PHASE2 {cand['id']}: DE={summary['de_mean']} "
                 f"Konsistenz={summary['consistency']} "
                 f"F0={summary['f0_median']} kritischn="
                 f"{summary['critical_segments']}")
        except Exception as e:                        # noqa: BLE001
            log.exception("Kandidat %s fehlgeschlagen: %s", cand["id"], e)
            results.append({"id": cand["id"], "label": cand["label"],
                            "kind": cand["kind"], "error": str(e)})

    # ---------- Blindproben (§18): neutrale Buchstaben --------------------
    blind_dir = PHASE2_DIR / "blind"
    for old in blind_dir.glob("sample_*.wav"):
        old.unlink()
    valid = [r for r in results if not r.get("error")]
    order = [r["id"] for r in valid]
    rng = random.Random(20260828)                      # deterministisch
    rng.shuffle(order)
    blind_map = {}
    letters = [chr(ord("A") + i) for i in range(len(order))]
    for letter, cid in zip(letters, order):
        src = next(Path(r["file"]) for r in valid if r["id"] == cid)
        dst = blind_dir / f"sample_{letter}.wav"
        dst.write_bytes(src.read_bytes())
        assert_no_phase1_write(dst)
        blind_map[letter] = cid
    write_json(PHASE2_DIR / "blind" / "blind_key.json",
               {"created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "mapping": blind_map})

    # ---------- Empfehlung (NICHT automatisch angewandt, §23) -------------
    base = next((r for r in valid if r["id"] == "P1-CURRENT"), None)

    def composite(r):
        # §25: Aussprache/Natürlichkeit vor F0; Konsistenz stark gewichtet
        return (0.45 * r["de_mean"] + 0.25 * r["naturalness"] +
                0.20 * r["consistency"] + 0.10 * r["pronunciation"])

    ranked = sorted(valid, key=lambda r: -composite(r))
    best = ranked[0] if ranked else None
    beats = False
    reason = ""
    if best and base and best["id"] != base["id"]:
        beats = (best["de_mean"] >= base["de_mean"] + 2.0 and
                 best["consistency"] >= base["consistency"] - 2.0 and
                 best["critical_segments"] == 0)
        reason = (f"{best['id']} DE {best['de_mean']} vs. Baseline "
                  f"{base['de_mean']}, Konsistenz {best['consistency']} vs. "
                  f"{base['consistency']}"
                  + ("" if beats else " – Abstand zu gering, Phase 1 bleibt "
                     "Produktionsfallback"))
    elif best:
        reason = "Baseline bleibt vorn (kein Kandidat deutlich besser)"

    recommendation = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ranked": [r["id"] for r in ranked],
        "recommended": best["id"] if beats else None,
        "beats_phase1": beats,
        "reason": reason,
        "user_pick_required": True,
        "note": ("Automatische Empfehlung ersetzt Phase 1 NICHT. "
                 "Finale Auswahl: Blindvergleich durch den Nutzer "
                 "(UI oder benchmark/phase2/blind/)."),
    }
    write_json(PHASE2_DIR / "comparisons" / "recommendation.json",
               recommendation)

    report = {
        "timestamp": recommendation["timestamp"],
        "text": "Kybalion (§16, wörtlich)",
        "n_segments": len(segments),
        "quick": quick,
        "baseline_phase1": ({k: base[k] for k in
                             ("id", "label", "de_mean", "consistency",
                              "f0_median", "critical_segments")}
                            if base else None),
        "candidates": results,
        "recommendation": recommendation,
        "blind_mapping": blind_map,
    }
    write_json(PHASE2_DIR / "comparisons" / "report_phase2.json", report)
    _write_md(report)
    plog(f"PHASE2 fertig: {len(valid)} Kandidaten, Blindproben A–"
         f"{letters[-1] if letters else '-'}, Empfehlung: "
         f"{recommendation['recommended'] or 'keine (Phase 1 bleibt)'}")
    return report


# ---------------------------------------------------------------------------
# Pausen-Sonde (§10): classic vs. semantic vs. flow
# ---------------------------------------------------------------------------
def run_pause_probe(studio, cfg: dict | None = None) -> dict:
    ensure_phase2_dirs()
    cfg = cfg or cfgmod.load_config()
    segments = _kybalion_segments()
    sampling = params_for_set("balanced")
    from ..prosody.pauses import pause_after
    out = {}
    # Segmente einmal synthetisieren, Pausenstrategien nur auf dem Join
    # vergleichen (gleiche Audio-Basis -> isolierter Pausenvergleich)
    wavs = []
    for i, seg in enumerate(segments):
        req = SynthesisRequest(text=seg.text, language="German",
                               speaker="Ryan", instruct="calm narration.",
                               sampling=dict(sampling), seed=8100 + i)
        res = studio.synth_customvoice(req)
        wavs.append((res.waveform, res.sample_rate, seg))
    from ..prosody.german import PAUSE_STRATEGIES
    for strategy in PAUSE_STRATEGIES:
        segs2 = list(segments)
        assign_pauses(segs2, style="auto", speed=1.0, strategy=strategy)
        pauses = [s.pause_after_s for s in segs2]
        assembled, sr = assemble(wavs)
        out[strategy] = {
            "pause_mean_s": round(float(np.mean(pauses)), 3),
            "pause_std_s": round(float(np.std(pauses)), 3),
            "pause_min_s": round(float(min(pauses)), 3),
            "pause_max_s": round(float(max(pauses)), 3),
            "total_s": round(len(assembled) / sr, 1),
        }
        write_wav(PHASE2_DIR / "pause_probe" / f"{strategy}.wav",
                  assembled, sr, bit_depth=16)
    write_json(PHASE2_DIR / "pause_probe" / "report.json",
               {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "strategies": out})
    return out


# ---------------------------------------------------------------------------
# Blind-Auswahl des Nutzers (§20) + Übernahme (§23)
# ---------------------------------------------------------------------------
def blind_status() -> dict:
    key_file = PHASE2_DIR / "blind" / "blind_key.json"
    pick_file = PHASE2_DIR / "blind" / "user_pick.json"
    rec = read_json(PHASE2_DIR / "comparisons" / "recommendation.json", None)
    key = read_json(key_file, None)
    pick = read_json(pick_file, None)
    samples = sorted([p.stem.split("_")[1] for p in
                      (PHASE2_DIR / "blind").glob("sample_*.wav")])
    report = read_json(PHASE2_DIR / "comparisons" / "report_phase2.json",
                       None)
    picked = bool(pick)
    return {
        "has_run": bool(report),
        "samples": samples,
        "picked": picked,
        "pick": (pick or {}).get("letter"),
        # Mapping erst NACH Auswahl enthüllen (Blind-Prinzip §18)
        "mapping": (key or {}).get("mapping") if picked else None,
        "recommendation": {k: rec.get(k) for k in
                           ("recommended", "beats_phase1", "reason")}
        if rec else None,
        "scores": ([{k: c.get(k) for k in
                     ("id", "label", "de_mean", "naturalness", "prosody_de",
                      "pronunciation", "rhythm", "pauses", "consistency",
                      "f0_median", "critical_segments", "kind")}
                    for c in report.get("candidates", [])]
                   if picked and report else None),
    }


def save_blind_pick(letter: str) -> dict:
    key = read_json(PHASE2_DIR / "blind" / "blind_key.json", {}) or {}
    mapping = key.get("mapping", {})
    letter = letter.strip().upper()
    if letter not in mapping:
        raise ValueError(f"Unbekannte Blindprobe: {letter!r} "
                         f"(erlaubt: {sorted(mapping)})")
    write_json(PHASE2_DIR / "blind" / "user_pick.json", {
        "letter": letter,
        "candidate_id": mapping[letter],
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    qlog(f"PHASE2 Nutzer-Blindauswahl: {letter} -> {mapping[letter]}")
    return blind_status()


def apply_pick_or_candidate(candidate_id: str | None = None) -> dict:
    """Übernimmt die Auswahl in die PRODUKTIONSKonfiguration (§23).

    Reihenfolge: explizite candidate_id, sonst gespeicherte Nutzer-
    Blindauswahl. VoiceDesign-Kandidaten werden als Clone-Stimme aktiviert
    (engine_mode=voicedesign), CustomVoice als Speaker+Variante.
    """
    report = read_json(PHASE2_DIR / "comparisons" / "report_phase2.json",
                       {}) or {}
    if candidate_id is None:
        pick = read_json(PHASE2_DIR / "blind" / "user_pick.json", {}) or {}
        candidate_id = pick.get("candidate_id")
    if not candidate_id:
        raise ValueError("Keine Auswahl vorhanden (Blindvergleich zuerst).")
    cand = next((c for c in report.get("candidates", [])
                 if c.get("id") == candidate_id), None)
    if cand is None:
        raise ValueError(f"Kandidat {candidate_id!r} nicht im Phase-2-"
                         "Bericht gefunden.")
    cfg = cfgmod.load_config()
    gcfg = cfg.setdefault("german", {})
    if cand["kind"].startswith("voicedesign"):
        gcfg["engine_mode"] = "voicedesign"
        gcfg["voicedesign"] = {
            "candidate_id": cand["id"],
            "description": cand.get("params", {}).get("description"),
        }
        applied = f"voicedesign:{cand['id']}"
    else:
        gcfg["engine_mode"] = "customvoice"
        gcfg["instruct_variant"] = cand.get("params", {}).get(
            "variant", gcfg.get("instruct_variant"))
        spk = cand.get("params", {}).get("speaker")
        if spk:
            cfg.setdefault("voices", {}).setdefault("speaker_map", {})
            cfg["voices"]["speaker_map"]["male_1"] = spk
        applied = (f"customvoice:{cand['id']} "
                   f"({gcfg['instruct_variant']}/{spk})")
    cfgmod.save_config(cfg)
    qlog(f"PHASE2 angewandt: {applied}")
    return {"ok": True, "applied": applied}


def _write_md(report: dict) -> None:
    lines = ["# Phase 2 – Voice-Vergleich (Kybalion)", "",
             f"Zeit: {report['timestamp']}  ",
             f"Segmente: {report['n_segments']}  ·  Modus: "
             f"{'Schnelltest' if report['quick'] else 'Volltest'}", "",
             "> Blindproben: `benchmark/phase2/blind/sample_X.wav` –",
             "> Zuordnung in `blind_key.json` (wird in der UI erst NACH",
             "> deiner Auswahl enthüllt). Scores sind interne Vergleichs-",
             "> maßstäbe; dein Höreindruck hat Vorrang (§20).", "",
             "| Kandidat | Typ | DE | Natürlich | Melodie | Ausspr. | "
             "Rhythmus | Konsistenz | F0 | Kritisch |", "|" + "---|" * 10]
    for c in report["candidates"]:
        if c.get("error"):
            lines.append(f"| {c['id']} | {c.get('kind', '?')} | FEHLER: "
                         f"{c['error'][:40]} | | | | | | | |")
            continue
        lines.append(
            f"| {c['id']} | {c['kind']} | {c['de_mean']} "
            f"| {c['naturalness']} | {c['prosody_de']} "
            f"| {c['pronunciation']} | {c['rhythm']} "
            f"| {c['consistency']} | {c['f0_median']} "
            f"| {c['critical_segments']} |")
    rec = report["recommendation"]
    lines += ["", "## Empfehlung (automatisch, NICHT angewandt)", "",
              f"Ranking: {', '.join(rec['ranked'][:5])} …", "",
              "Empfohlen: **" + str(rec["recommended"] or
                                    "keine – Phase 1 bleibt "
                                    "Produktionsfallback") + "**",
              "", rec["reason"], "",
              "## Nächster Schritt",
              "", "1. Blindproben anhören (UI ‚Phase 2 – Voice Studio‘ oder "
              "Dateien direkt).", "2. Gewinnern auswählen (UI/CLI).",
              "3. Erst dann wird die Produktion umgestellt (§23)."]
    (PHASE2_DIR / "comparisons" / "report_phase2.md").write_text(
        "\n".join(lines), encoding="utf-8")
