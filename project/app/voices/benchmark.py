"""Stimmen-Benchmark (Anforderung 20 + 51).

Erzeugt für Kandidaten-Speaker standardisierte Tests in Deutsch und
Englisch, analysiert sie objektiv (Sprechrate, Tonlage, Prosodie-
Varianz, Lautheit, Integrität) und schreibt beurteilbare WAV-Dateien
plus Bericht. Die finale Auswahl der sechs Hauptstimmen erfolgt auf
Basis dieser Messungen UND durch Anhören (Dateien liegen in
benchmark/voices/). Ohne Modell (z. B. im CI) nicht ausführbar.
"""
from __future__ import annotations

import time

import numpy as np
from pathlib import Path

from .. import paths
from ..audio.io import write_wav
from ..logging_setup import get_logger, qlog
from ..quality.metrics import analyze_segment_audio
from ..prosody.instruct import variant_text
from ..tts.engine_base import SynthesisRequest
from ..tts.sampler import params_for_set
from ..voices.profiles import SUPPORTED_SPEAKERS

log = get_logger("voicebench")

TEST_SENTENCES_DE = [
    "Im Herzen jeder Stadt liegt eine Geschichte, die niemand je vollständig erzählt hat.",
    ("Friedrich Nietzsche schrieb im neunzehnten Jahrhundert in Sils-Maria seine "
     "aufsehenerregenden Notizen, während über Europa der Schatten zweier "
     "Weltkriege wartete, die erst 1914 und 1939 beginnen sollten."),
    "Warum wiederholen Menschen Muster, die sie eigentlich durchschaut haben?",
    "Die Messung ergab 3,7 Prozent bei einer Temperatur von minus 12,5 Grad Celsius.",
    ("An Göbekli Tepe, nahe der türkischen Stadt Şanlıurfa, ragen monolithische "
     "Pfeiler in den Himmel, die vor rund elftausendfünfhundert Jahren errichtet wurden."),
]

TEST_SENTENCES_EN = [
    "Every city keeps a story that no one has ever fully told.",
    ("In nineteen sixty-nine, a quiet experiment at CERN changed how we "
     "understand the smallest building blocks of matter, decades before "
     "anyone spoke of artificial intelligence or NVIDIA GPUs."),
    "Why do people repeat the very patterns they claim to understand?",
    "The reading was 3.7 percent at a temperature of minus 10.4 degrees Celsius.",
    "There is a difference between knowing the path and walking the path.",
]

# Relevante Kandidaten für Erzählstimmen (DE/EN)
CANDIDATE_SPEAKERS = ["Ryan", "Aiden", "Uncle_Fu", "Dylan", "Eric",
                      "Serena", "Vivian", "Sohee", "Ono_Anna"]

NARRATOR_STYLE_DE = ("Speak as a calm, deep, credible German documentary narrator: "
                     "serious, warm, natural intonation, even pacing.")
NARRATOR_STYLE_EN = ("Speak as a calm, deep, credible English documentary narrator: "
                     "serious, warm, natural intonation, even pacing.")


def score_speaker(metrics_by_test: list[dict]) -> dict:
    """Objektive Heuristik: Startup-Konsistenz, Intonationsbreite, Tempo,
    Integrität. KEINE absolute Natürlichkeitsmessung (Anforderung 46)."""
    import numpy as np
    durs = [m["duration_s"] for m in metrics_by_test]
    f0s = [m.get("f0_median_hz", 0) for m in metrics_by_test if m.get("f0_median_hz")]
    lufs = [m.get("lufs", -20) for m in metrics_by_test]
    cvs = [m.get("f0_cv", 0) for m in metrics_by_test]
    score = {}
    if f0s:
        f0 = float(np.mean(f0s))
        f0_dev = float(np.std(f0s))
        score["pitch_hz"] = round(f0, 1)
        score["pitch_stability"] = round(max(0.0, 100 - f0_dev * 4), 1)
    else:
        score["pitch_hz"] = 0
        score["pitch_stability"] = 0
    if cvs:
        cv = float(np.mean(cvs))
        # leichte Varianz ist gut (0.05-0.15 ideal), 0 = monoton
        score["intonation_range"] = round(min(cv / 0.10, 1.0) * 100, 1)
    if durs:
        score["duration_consistency"] = round(max(0.0, 100 - float(np.std(durs)) * 12), 1)
    if lufs:
        score["loudness_stability"] = round(max(0.0, 100 - float(np.std(lufs)) * 8), 1)
    integ = [m.get("clip_ratio", 0) for m in metrics_by_test]
    score["integrity"] = round(100 - sum(integ) * 20000, 1)
    parts = [score.get("pitch_stability", 0), score.get("intonation_range", 0),
             score.get("duration_consistency", 0), score.get("loudness_stability", 0),
             score.get("integrity", 100)]
    score["overall"] = round(float(np.mean(parts)), 1)
    return score


def run_voice_benchmark(engine, speakers: list[str] | None = None,
                        languages: tuple[str, ...] = ("German", "English"),
                        quick: bool = False) -> dict:
    speakers = [s for s in (speakers or CANDIDATE_SPEAKERS)
                if s in SUPPORTED_SPEAKERS]
    out_dir = paths.BENCHMARK_DIR / "voices"
    out_dir.mkdir(parents=True, exist_ok=True)
    sampling = params_for_set("balanced")
    results = {}
    log.info("Stimmen-Benchmark: %s Speaker × %s Sprachen", len(speakers), len(languages))
    for speaker in speakers:
        results[speaker] = {}
        for lang in languages:
            key = "de" if lang.lower().startswith("ger") else "en"
            sentences = TEST_SENTENCES_DE if key == "de" else TEST_SENTENCES_EN
            if quick:
                sentences = sentences[:2]
            style = NARRATOR_STYLE_DE if key == "de" else NARRATOR_STYLE_EN
            metrics_list = []
            files = []
            for i, sent in enumerate(sentences):
                req = SynthesisRequest(
                    text=sent, language=lang, speaker=speaker,
                    instruct=style, sampling=dict(sampling),
                    seed=hash((speaker, lang, i)) % (2**31),
                    max_seconds_hint=max(6.0, len(sent) / 13.0))
                try:
                    res = engine.synthesize(req)
                except Exception as e:
                    log.warning("Speaker %s (%s) Satz %d fehlgeschlagen: %s",
                                speaker, lang, i, e)
                    continue
                p = out_dir / f"{speaker}_{key}_{i:02d}.wav"
                write_wav(p, res.waveform, res.sample_rate, bit_depth=16)
                files.append(str(p))
                m = analyze_segment_audio(res.waveform, res.sample_rate)
                m["chars_per_sec"] = round(len(sent) / max(m["duration_s"], 0.1), 2)
                m["realtime_factor"] = res.realtime_factor
                metrics_list.append(m)
            results[speaker][key] = {
                "metrics": metrics_list,
                "score": score_speaker(metrics_list),
                "files": files,
            }
            qlog(f"VOICEBENCH {speaker} {lang}: "
                 f"{results[speaker][key]['score']}")

    # Empfehlung: bester männlicher + bester weiblicher DE-Speaker
    male = ["Ryan", "Aiden", "Uncle_Fu", "Dylan", "Eric"]
    female = ["Serena", "Vivian", "Sohee", "Ono_Anna"]

    def _best(group):
        cand = [(s, results[s]["de"]["score"].get("overall", 0))
                for s in group if s in results and "de" in results[s]]
        return sorted(cand, key=lambda kv: -kv[1])

    recommendation = {
        "best_male": _best(male),
        "best_female": _best(female),
    }
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "engine": engine.info(),
        "speakers": {s: {k: {"score": v["score"], "files": v["files"]}
                         for k, v in langs.items()}
                     for s, langs in results.items()},
        "recommendation": recommendation,
    }
    from ..utils import write_json
    write_json(paths.BENCHMARK_DIR / "voice_benchmark.json", report)
    _write_md(report)
    log.info("Stimmen-Benchmark abgeschlossen: benchmark/voice_benchmark.json")
    return report


def _write_md(report: dict) -> None:
    lines = [
        "# Stimmen-Benchmark (Qwen3-TTS)",
        "",
        f"Zeit: {report['timestamp']}  ",
        f"Engine: {report['engine'].get('engine_version', '?')}",
        "",
        "> Hinweis: Die Scores sind objektive Signalkriterien (Tonlagen- und",
        "> Lautheitsstabilität, Intonationsbreite, Integrität) zum VERGLEICH.",
        "> Die finale Auswahl sollte durch Anhören der Dateien in",
        "> `benchmark/voices/` bestätigt werden (Anforderung 19+20).",
        "",
        "| Speaker | DE Score | DE F0 | EN Score | EN F0 | Bemerkung |",
        "|---------|----------|-------|----------|-------|-----------|",
    ]
    for spk, langs in report["speakers"].items():
        de = langs.get("de", {}).get("score", {})
        en = langs.get("en", {}).get("score", {})
        lines.append(
            f"| {spk} | {de.get('overall', '-')} | {de.get('pitch_hz', '-')} Hz "
            f"| {en.get('overall', '-')} | {en.get('pitch_hz', '-')} Hz | |")
    rec = report["recommendation"]
    lines += ["", "## Empfehlung (objektive Heuristik)", ""]
    lines.append("Männlich: " + ", ".join(f"{s} ({v})" for s, v in rec["best_male"]))
    lines.append("Weiblich: " + ", ".join(f"{s} ({v})" for s, v in rec["best_female"]))
    (paths.BENCHMARK_DIR / "voice_benchmark.md").write_text(
        "\n".join(lines), encoding="utf-8")


# ===========================================================================
# Phase 1 (§19): DEUTSCHER Stimmen-Benchmark – eigener Test für Deutsch,
# unabhängig von englischen Ergebnissen. Ermittelt DEFAULT BEST GERMAN
# NARRATOR und belegt die 6 Profile aus den tatsächlichen Messungen.
# ===========================================================================
GERMAN_SPEAKER_TEXTS = [
    "Im Sommer 1934 begann eine Ausgrabung, die niemand für möglich "
    "gehalten hätte. Die Forscher brauchten acht Jahre, um zu verstehen, "
    "was sie gefunden hatten – und noch einmal vierzig, um es zu glauben.",
    "Friedrich Nietzsche und Søren Kierkegaard lasen Descartes, während "
    "1914 die Welt einen anderen Weg nahm. Warum bleiben manche Fragen "
    "offen, obwohl die Antwort längst auf dem Tisch liegt?",
    "Es begann wie jede andere Geschichte: mit einer Frage, die niemand "
    "stellte. Die Stadt schlief, die Laternen flackerten, und irgendwo "
    "hinter einem Fenster saß ein Mensch, der nicht schlafen konnte. Er "
    "dachte über das Vergessen nach – leise, geduldig, unerbittlich.",
]


def _depth_score(f0_hz: float, gender: str) -> float:
    """Stimm-Plausibilität (Phase 2 §4/§25): F0 bewertet NUR als
    natürliches Band für dokumentarische Erzählstimmen – ausdrücklich
    NICHT „tiefer = besser" (künstlich tiefe Stimmen sind keine Qualität)."""
    import numpy as np
    bands = {"male": (92, 150), "female": (150, 230)}
    lo, hi = bands.get(gender, (90, 230))
    if lo <= f0_hz <= hi:
        return 100.0
    dist = min(abs(f0_hz - lo), abs(f0_hz - hi))
    return float(np.clip(100 - dist * 2.5, 0, 100))


def run_german_speaker_benchmark(engine, speakers: list[str] | None = None,
                                 quick: bool = False) -> dict:
    """Testet alle Speaker gezielt auf DEUTSCH (Anforderung 19).

    Kriterien (gewichtet): GermanNaturalnessScore 55 %, Tiefe 15 %,
    Langform-Konsistenz 15 %, Tempo im Naturbereich 15 %.
    Empfehlung: bester männlicher + bester weiblicher Speaker; die
    6 Profile werden aus den Top-3 je Geschlecht belegt (Male 3 =
    tiefster männlicher F0 der Top-Kandidaten, §20).
    """
    from ..quality.german_score import score_german
    from ..utils import write_json as _wj

    speakers = [s for s in (speakers or SUPPORTED_SPEAKERS)
                if s in SUPPORTED_SPEAKERS]
    texts = GERMAN_SPEAKER_TEXTS[:2] if quick else GERMAN_SPEAKER_TEXTS
    out_dir = paths.BENCHMARK_DIR / "german_voices"
    out_dir.mkdir(parents=True, exist_ok=True)
    sampling = params_for_set("balanced")
    results = {}
    log.info("Deutsch-Stimmen-Benchmark: %d Speaker", len(speakers))

    for speaker in speakers:
        per_text = []
        wavs = []
        for i, txt in enumerate(texts):
            req = SynthesisRequest(
                text=txt, language="German", speaker=speaker,
                instruct=variant_text("de_doc_native"),
                sampling=dict(sampling),
                seed=4400 + i * 23,
                max_seconds_hint=max(6.0, len(txt) / 13.0))
            try:
                res = engine.synthesize(req)
            except Exception as e:                       # noqa: BLE001
                log.warning("Speaker %s Text %d fehlgeschlagen: %s",
                            speaker, i, e)
                continue
            write_wav(out_dir / f"{speaker}_{i}.wav", res.waveform,
                      res.sample_rate, bit_depth=16)
            m = analyze_segment_audio(res.waveform, res.sample_rate)
            g = score_german(res.waveform, res.sample_rate, txt)
            per_text.append({"metrics": m, "german": g.to_dict()})
            wavs.append((res.waveform, res.sample_rate, m))
        if not per_text:
            results[speaker] = {"error": "alle Tests fehlgeschlagen"}
            continue

        german_scores = [p["german"]["overall"] for p in per_text]
        f0s = [p["metrics"].get("f0_median_hz") for p in per_text
               if p["metrics"].get("f0_median_hz")]
        f0_med = float(np.mean(f0s)) if f0s else 0.0
        f0_spread = float(np.std(f0s)) if len(f0s) > 1 else 0.0
        gender = "female" if speaker in ("Vivian", "Serena", "Sohee",
                                         "Ono_Anna") else "male"
        depth = _depth_score(f0_med, gender) if f0_med else 0.0
        # Tempo im Naturbereich (Silben/s 3,1-5,6) über Metrik-Dauern
        rates_ok = _rates_ok(per_text, texts)
        overall = float(np.clip(
            0.55 * float(np.mean(german_scores)) +
            0.15 * depth +
            0.15 * max(0.0, 100 - f0_spread * 4) +
            0.15 * (100 if rates_ok else 55), 0, 100))
        results[speaker] = {
            "gender": gender,
            "german_mean": round(float(np.mean(german_scores)), 2),
            "f0_median_hz": round(f0_med, 1),
            "f0_spread_hz": round(f0_spread, 2),
            "depth_score": round(depth, 1),
            "rates_ok": rates_ok,
            "overall": round(overall, 2),
            "files": [str(out_dir / f"{speaker}_{i}.wav")
                      for i in range(len(texts))],
        }
        qlog(f"GERMAN-SPEAKER {speaker}: DE={results[speaker]['german_mean']} "
             f"F0={f0_med:.0f}Hz Tiefe={depth:.0f} "
             f"gesamt={overall:.1f}")

    # ---- Empfehlung + Profilbelegung (§19+20) -----------------------------
    male = [(s, r) for s, r in results.items() if r.get("gender") == "male"]
    female = [(s, r) for s, r in results.items() if r.get("gender") == "female"]
    male.sort(key=lambda kv: -kv[1]["overall"])
    female.sort(key=lambda kv: -kv[1]["overall"])

    def _map_profiles(group, ids):
        mapping = {}
        if len(group) >= 3:
            top3 = [s for s, _ in group[:3]]
            # Male 3 / Female 3: tiefster F0 unter den Top-3
            deepest = min(top3, key=lambda s: results[s]["f0_median_hz"])
            rest = [s for s in top3 if s != deepest]
            mapping = {ids[0]: rest[0], ids[1]: rest[1], ids[2]: deepest}
        return mapping

    speaker_map = {}
    speaker_map.update(_map_profiles(male, ["male_1", "male_2", "male_3"]))
    speaker_map.update(_map_profiles(female,
                                      ["female_1", "female_2", "female_3"]))
    best_male = male[0][0] if male else None
    best_female = female[0][0] if female else None
    best_german = best_male or best_female
    if best_german:
        speaker_map.setdefault("male_1", best_german)

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "engine": engine.info(),
        "note": ("Vergleichs-Scores auf Signalebene; finale Auswahl durch "
                 "Anhören der Dateien in benchmark/german_voices/ "
                 "bestätigen (§19)."),
        "speakers": results,
        "best_male": best_male,
        "best_female": best_female,
        "best_german_narrator": best_german,
        "speaker_map": speaker_map,
    }
    _wj(paths.BENCHMARK_DIR / "german_speakers.json", report)
    _write_german_md(report)

    # Gewinnereinstellungen in Konfiguration übernehmen
    if best_german:
        from .. import config as cfgmod
        cfg = cfgmod.load_config()
        cfg.setdefault("german", {})["best_speaker"] = best_german
        if speaker_map:
            cfg.setdefault("voices", {})["speaker_map"] = speaker_map
        cfgmod.save_config(cfg)
        log.info("DEFAULT BEST GERMAN NARRATOR: %s (Konfiguration "
                 "aktualisiert, Profil-Map: %s)", best_german, speaker_map)
    return report


def _rates_ok(per_text: list, texts: list) -> bool:
    from ..quality.german_score import count_syllables_de
    for p, t in zip(per_text, texts):
        dur = p["metrics"].get("duration_s", 0) or 0
        if dur <= 0:
            return False
        rate = count_syllables_de(t) / dur
        if not (3.1 <= rate <= 5.8):
            return False
    return True


def _write_german_md(report: dict) -> None:
    lines = ["# Deutscher Stimmen-Benchmark (Phase 1 §19)", "",
             f"Zeit: {report['timestamp']}  ",
             f"Engine: {report['engine'].get('engine_version', '?')}", "",
             "> DEFAULT BEST GERMAN NARRATOR wird aus DEUTSCHEN Tests ",
             "> ermittelt (nicht aus englischen). Scores sind Vergleichs-",
             "> maßstäbe; Hörproben: `benchmark/german_voices/`.", "",
             "| Speaker | Geschlecht | DE-Score | F0 (Hz) | Tiefe | "
             "Gesamt |", "|---|---|---|---|---|---|"]
    for s, r in sorted(report["speakers"].items(),
                       key=lambda kv: -kv[1].get("overall", 0)):
        lines.append(f"| {s} | {r.get('gender', '?')} "
                     f"| {r.get('german_mean', '-')} "
                     f"| {r.get('f0_median_hz', '-')} "
                     f"| {r.get('depth_score', '-')} "
                     f"| {r.get('overall', '-')} |")
    lines += ["",
              f"**DEFAULT BEST GERMAN NARRATOR (m):** "
              f"{report.get('best_male')}", "",
              f"**Beste weibliche Stimme:** {report.get('best_female')}", "",
              f"Profil-Belegung: `{report.get('speaker_map')}`", ""]
    (paths.BENCHMARK_DIR / "german_speakers.md").write_text(
        "\n".join(lines), encoding="utf-8")
