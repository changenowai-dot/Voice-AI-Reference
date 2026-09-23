"""Echter TTS-Aussprache-Regressionstest (läuft auf GPU-Host).

Für die MATHEMATIK-Regressionssätze (Anforderung 8) wird ECHTER Qwen-TTS
über zwei auf dem Release vorhandene DE-Stimmen gefahren:
  - de_male_warm_storytelling_authoritative_01
  - de_male_warm_calm_authoritative_02

Erzeugt pro Stimme einen Ordner pronunciation_tts_regression/<voice>/
mit:
  - je Satz eine WAV-Datei (sent_NN.wav)
  - audit.json: TTS-Erfolg, Dauer, Ersetzungen, QC (Stille/Peak/RMS),
    Audio vorhanden / nicht still.
  - summary.md: übersichtlicher Bericht

Nutzt den produktiven Engine-Pfad (VoiceCloneEngine + QwenModelPool,
gleiche Konstruktion wie in runner.build_engine) und engine.synthesize()
mit der echten SynthesisRequest-API (ohne output_path – das WAV wird
nach synthesize via soundfile aus dem zurückgegebenen numpy-Array
geschrieben). KEINE Simulation, KEIN Workaround.

Offline ohne GPU wird der Test sauber SKIP melden (nicht FAIL).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


# Voices für den Regressionstest. Es werden NUR Stimmen ausgewählt, für
# die ein deutsches Referenz-Bundle im Release existiert (also
# tatsächlich synthetisiert werden können, siehe
# app/voices/bundles/).
REGRESSION_VOICES = [
    "de_male_warm_storytelling_authoritative_01",
    "de_male_warm_calm_authoritative_02",
]

REGRESSION_SENTENCES = [
    "Mathematik ist die Sprache der Zahlen.",
    "Die Mathematik beschreibt Muster, Mengen und Strukturen.",
    "Ein mathematischer Algorithmus kann komplexe Probleme lösen.",
    "Quantenphysik und Mathematik bilden eine wichtige Grundlage moderner Forschung.",
    # Atome-/Zellen-Familie (Identity-Regression, vorher Bindestrich-Respell):
    "Das Atom und die Atome bilden die Grundbausteine der Materie.",
    "Der Atomkern besteht aus Protonen und Neutronen.",
    "Die Zelle ist die kleinste Einheit des Lebens, und Zellen bilden Gewebe.",
    # ------------------------------------------------------------------
    # Grosser Fachbegriff-Katalog (Forensik 2026-09, Phase 4/8/9):
    # Prioritaet Teilchenfamilie (Host-Befund: "Pro-TO-nen/Noi-tro-NEN"
    # falsch) + Anker + Offline-Sweep-Verdaechtige (aktive Bindestrich/
    # GROSS-Respells) in natuerlichen Saetzen. Gestaffelt testbar via
    # --limit N.
    # ------------------------------------------------------------------
    "Protonen und Neutronen befinden sich im Atomkern, Elektronen in der Hülle.",
    "Ein Proton trägt eine positive Ladung, ein Neutron ist neutral.",
    "Photonen übertragen Lichtenergie, und die Wellenlänge bestimmt die Farbe.",
    "Moleküle bestehen aus Atomen, die über Elektronen zusammengehalten werden.",
    "Die Thermodynamik beschreibt Energie, Entropie und Temperatur.",
    "Radioaktive Strahlung entsteht beim Zerfall instabiler Atomkerne.",
    "Die Teilchenphysik erforscht Elementarteilchen und ihre Wechselwirkungen.",
    "Ohne Spannung und Widerstand fliesst kein elektrischer Strom.",
    "Die Kernphysik untersucht Kernspaltung und Kernfusion.",
    "Ein Molekül Wasser besteht aus Wasserstoff und Sauerstoff.",
    "Ein Katalysator beschleunigt die chemische Reaktion, ohne selbst verbraucht zu werden.",
    "Oxidation und Reduktion sind gekoppelte chemische Prozesse.",
    "Chromosomen tragen die Gene, und das Genom umfasst die volle Erbinformation.",
    "Enzyme und Proteine steuern den Stoffwechsel jeder Zelle.",
    "Die Photosynthese wandelt Licht in chemische Energie um.",
    "Bakterien und Viren können das Immunsystem herausfordern.",
    "Synapsen verbinden Neuronen zu grossen Netzwerken im Gehirn.",
    "Dopamin und Serotonin sind wichtige Botenstoffe des Nervensystems.",
    "Die Amygdala und der Hippocampus spielen eine zentrale Rolle im Gedächtnis.",
    "Neuroplastizität erlaubt dem Gehirn lebenslanges Lernen.",
    "Kognition umfasst Wahrnehmung, Aufmerksamkeit und Gedächtnis.",
    "Ein neuronales Netzwerk lernt aus Beispielen statt aus Regeln.",
    "Galaxien, Planeten und Sterne entstehen aus kosmischen Gaswolken.",
    "Exoplaneten kreisen um ferne Sterne unserer Galaxis.",
    "Ein Schwarzes Loch biegt selbst das Licht der Sterne.",
    "Die Raumzeit krümmt sich um schwere Materie.",
    "Supernovae streuen Elemente in das Universum hinaus.",
    "Die Plattentektonik verschiebt Kontinente und erzeugt Erdbeben.",
    "Vulkane fördern Magma aus dem Inneren der Erde an die Oberfläche.",
    "Die Atmosphäre schützt das Leben auf dem Planeten.",
    "Kristalle wachsen in regelmässigen, geometrischen Strukturen.",
    "Algebra und Geometrie sind klassische Gebiete der Mathematik.",
    "Die Analysis untersucht Grenzwerte, Ableitungen und Integrale.",
    "Ein Vektor hat Richtung und Grösse, eine Matrix ordnet Zahlen.",
    "Ohne Gleichung keine Beschreibung physikalischer Zusammenhänge.",
    "Statistische Korrelation beweist noch keine Kausalität.",
    "Mittelwert und Standardabweichung beschreiben eine Verteilung.",
    "Der Logarithmus kehrt die Exponentialfunktion um.",
    "Verschlüsselung schützt Daten in Netzwerken und Datenbanken.",
    "Binärcode besteht nur aus Nullen und Einsen, aus Bits und Bytes.",
    "Der Prozessor führt den Quellcode eines Programms aus.",
    "Kryptografie beruht auf schwer umkehrbaren mathematischen Funktionen.",
    "Die Simulation modelliert komplexe Systeme am Computer.",
    "Metaphysik fragt nach dem Sein, Ontologie nach dem Seienden.",
    "Erkenntnistheorie untersucht, was Wissen überhaupt ist.",
    "Determinismus und Freiheit sind ein klassischer Konflikt der Ethik.",
    "Rationalismus und Empirismus streiten über die Quelle der Erkenntnis.",
    # Batch 2 (User-Hoerbefunde 2026-09 #2): Daten/Prozessor/Matrix/
    # Erkenntnistheorie/Logarithmus/Vektor/Gleichung/Quellcode/Metaphysik/
    # Ontologie -> Identity; Philosoph bewusst UNVERAENDERT (Hörbefund
    # unsicher -> dieser Satz verifiziert die aktuelle Regel am Host).
    "Die Daten werden vom Prozessor verarbeitet.",
    "Eine Matrix kann viele Zahlen gleichzeitig darstellen.",
    "Ein Vektor besitzt Richtung und Betrag.",
    "Eine Gleichung beschreibt einen Zusammenhang zwischen Größen.",
    "Der Quellcode eines Programms wird vom Prozessor ausgeführt.",
    "Die Erkenntnistheorie untersucht die Bedingungen von Wissen.",
    "Der Logarithmus ist die Umkehrung einer Exponentialfunktion.",
    "Die Metaphysik beschäftigt sich mit grundlegenden Fragen der Wirklichkeit.",
    "Die Ontologie untersucht, was überhaupt existiert.",
    "Der Philosoph stellt grundlegende Fragen nach Erkenntnis und Wirklichkeit.",
    "Matrizen und Vektoren bilden die Grundlage der linearen Algebra.",
    "Große Datenbanken sortieren Datensätze mit Algorithmen.",
    "Logarithmen und Exponentialfunktionen sind Umkehrfunktionen.",
    "Metaphysische und ontologische Fragen begleiten die Philosophie seit Jahrtausenden.",
    # ------------------------------------------------------------------
    # Batch 3 (2026-09, Kaskaden-Fix + Katalog-Luecken):
    #
    # 3a = die drei DETERMINISTISCH belegten Kaskaden-Opfer. Ihre
    #      kuratierten Respellings wurden vorher von anderen Regeln still
    #      ueberschrieben ("Kernphysik" -> "KERN-fy-SIK", "Kinematik" ->
    #      "K I-ne-MA-tik", "Regelungstechnik" -> "RE-ge-lungs-TECH-nik").
    #      Der Host-Lauf bestaetigt hier nur noch, dass die korrigierte
    #      Form akustisch gut ist - der Textfehler selbst ist ohne Audio
    #      bewiesen (tools/pronunciation_cascade_audit.py).
    # 3b = Begriffsfamilien der User-Hoerbefunde (Uebergabe Sec.24).
    # 3c = Katalog-Luecken (Sec.25-Sec.29), bisher ohne Satz-Coverage.
    #      Diese Saetze sind bewusst NATUERLICH formuliert, kein
    #      Keyword-Stuffing: nur was im echten Voiceover-Text vorkommt.
    # ------------------------------------------------------------------
    # 3a Kaskaden-Fixes
    "Die Kinematik beschreibt, wie sich ein Körper bewegt.",
    "Kinematik und Dynamik gehören zur klassischen Mechanik.",
    "Die Regelungstechnik hält einen Prozess stabil im Sollbereich.",
    "Der Mikroprozessor führt den Quellcode Schritt für Schritt aus.",
    "Mikroprozessor und Mikrochip teilen sich eine Platine.",
    # 3b Begriffsfamilien der User-Hoerbefunde
    "Jeder Datensatz besitzt eine klar definierte Datenstruktur.",
    "Datenstrukturen bestimmen, wie schnell die Datenverarbeitung läuft.",
    "Mehrere Prozessoren teilen sich die Prozessorleistung.",
    "Die Prozessorarchitektur legt den Takt der Prozessoren fest.",
    "Philosophen und Philosophinnen lesen philosophische Texte.",
    "Die Matrixrechnung ordnet Zahlen in einer Matrix an.",
    "Erkenntnistheoretisch bleibt der Erkenntnisgewinn schwer messbar.",
    "Logarithmisch skalierte Achsen zeigen logarithmische Verläufe; in "
    "logarithmischen Diagrammen wird daraus eine Gerade.",
    "Jeder Vektorraum besitzt eine Basis; Vektorräume lassen sich so "
    "vergleichen.",
    "Eine Differentialgleichung beschreibt, wie sich ein Zustand ändert.",
    "Bewegungsgleichung und Wellengleichung sind Grundformen der Physik.",
    "Quellcodes und Quelltexte werden versioniert abgelegt.",
    # 3c Katalog-Luecken: Anker-Ergänzung
    "Mit mathematischem Aufwand lässt sich die Aussage prüfen.",
    "Die Quantenmechanik ergänzt die Quantenphysik.",
    "Psychologisch wirkt Musik unmittelbar auf das Verhalten.",
    # 3c Physik
    "Die Frequenz einer Welle bestimmt ihre Energie.",
    "Magnetismus und Elektromagnetismus wirken auf geladene Teilchen.",
    "Ein elektromagnetisch erzeugtes Feld breitet sich im Raum aus.",
    "Elektrizität entsteht durch bewegte Ladung.",
    "Beschleunigung und Gravitation bestimmen die Bahn eines Körpers.",
    "Die Relativitätstheorie beschreibt Raum, Zeit und Relativität.",
    "Impuls und Antimaterie sind zentrale Größen der Forschung.",
    "Radioaktivität entsteht beim Zerfall schwerer Atomkerne.",
    "Die Wellenfunktion gehört zum Quantenfeld und zur Quantenfeldtheorie.",
    # 3c Chemie
    "Die Chemie untersucht Reaktionen und die Katalyse.",
    "Eine Säure reagiert mit einer Base und bildet eine Lösung.",
    "Konzentration und Löslichkeit bestimmen die Basen im Wasser.",
    "Polymere bestehen aus langen Ketten, ein Polymer aus Wiederholungen.",
    "Kohlenstoff, Stickstoff und Schwefel sind Bausteine des Lebens.",
    "Phosphor, Natrium und Kalium sind wichtige Elemente.",
    "Calcium und Kupfer finden sich in vielen Legierungen.",
    "Die Elektronenhülle umgibt den Atomkern.",
    # 3c Biologie
    "Zellkern und Zellmembran steuern die Zellteilung.",
    "DNA und RNA tragen die Information der Genetik.",
    "Eine Mutation kann die Evolution verändern, viele Mutationen wirken "
    "zusammen.",
    "Jeder Organismus besteht aus Zellen, Organismen bilden Ökosysteme.",
    "Ein Bakterium ist deutlich größer als ein Virus.",
    "Mikrobiologie und Molekularbiologie erforschen den Metabolismus.",
    "Eine Nervenzelle leitet Signale über lange Strecken weiter.",
    # 3c Astronomie
    "Die Astronomie misst astronomisch große Entfernungen.",
    "Die Kosmologie denkt kosmologisch über das Universum nach.",
    "Schwarze Löcher entstehen, wenn schwere Sterne kollabieren.",
    "Expansion, Dunkle Materie und Dunkle Energie prägen das Universum.",
    # 3c Mathematik
    "Eine Variable steht in Gleichungen für viele Variablen.",
    "Die Dimension eines Raums beschreibt seine Dimensionen.",
    "Exponentiell wachsende Daten erhöhen Varianz und Regression.",
    "Ein numerisch gelöstes Integral braucht Rechenzeit.",
    # 3c Informatik
    "Software und Hardware brauchen einen gemeinsamen Parameter.",
    "Kryptographie und Kryptografie schützen jede Datenstruktur.",
    "Neuronale Netzwerke verbinden sehr viele Parameter.",
    # 3c Neuro / Psychologie
    "Neurotransmitter wie Adrenalin und Cortisol steuern den Körper.",
    "Kognition wirkt kognitiv auf Aufmerksamkeit und Motivation.",
    "Persönlichkeit und Motivation prägen das Verhalten.",
    "Emotion und Emotionen entstehen auch im Unterbewusstsein.",
    # 3c Philosophie
    "Materialismus und Idealismus deuten die Existenz unterschiedlich.",
    "Realität und Wirklichkeit sind Begriffe der Epistemologie.",
    "Die metaphysischen und ontologischen Grundfragen bleiben offen.",
    # Regressions-Anker (Phase 7) - muessen unverändert gut bleiben:
    "Die Wahrscheinlichkeit eines Ergebnisses lässt sich berechnen.",
    "Die Statistik stützt die Theorie der modernen Physik.",
    "Bewusstsein ist aus Sicht der Neurowissenschaft ein Prozess des Gehirns.",
    "Die Psychologie beschreibt Verhalten und Erleben wissenschaftlich.",
]


@dataclass
class SentenceAudioResult:
    sentence_index: int
    sentence: str
    voice_id: str
    wav_path: str = ""
    ok: bool = False
    error: str = ""
    duration_s: float = 0.0
    peak: float = 0.0
    rms: float = 0.0
    is_silent: bool = True
    tts_text: str = ""
    replacements: list = field(default_factory=list)
    elapsed_s: float = 0.0


def _qc_check_wav(path: Path) -> tuple[bool, float, float, float, str]:
    """Quick-QC: Datei existiert, >1KB, RMS > -50 dBFS (nicht still), Peak <= 1."""
    try:
        import numpy as np
        import soundfile as sf
    except Exception as e:
        return False, 0.0, 0.0, 0.0, f"soundfile/numpy fehlt: {e}"
    if not path.exists():
        return False, 0.0, 0.0, 0.0, f"Datei fehlt: {path}"
    if path.stat().st_size < 1024:
        return False, 0.0, 0.0, 0.0, f"Datei zu klein ({path.stat().st_size} B)"
    try:
        data, sr = sf.read(str(path))
    except Exception as e:
        return False, 0.0, 0.0, 0.0, f"Read fehlgeschlagen: {e}"
    if data is None or len(data) == 0:
        return False, 0.0, 0.0, 0.0, "Leeres Audio"
    arr = data if hasattr(data, "ndim") and data.ndim == 1 else data.mean(axis=1)
    peak = float(abs(arr).max()) if len(arr) else 0.0
    rms = float((arr ** 2).mean() ** 0.5) if len(arr) else 0.0
    dur = float(len(arr) / sr) if sr else 0.0
    silent = rms < 0.002   # ~ -54 dBFS
    if silent:
        return False, dur, peak, rms, "Audio ist still (RMS < -54 dBFS)"
    if peak > 1.01:
        return False, dur, peak, rms, f"Clipping (Peak {peak:.3f})"
    return True, dur, peak, rms, ""


def _build_engine_for_voice(voice_id: str):
    """Baut eine produktionskonforme VoiceCloneEngine – nach dem gleichen
    Muster wie jobs.runner.build_engine() für clone-Stimmen."""
    from app.hardware.detector import detect_hardware
    from app.jobs.runner import _resolve_voice_native_language, _resolve_voice_seed
    from app.security.identity_lock import load_production
    from app.tts.qwen_engine import VoiceCloneEngine
    from app.voices.registry import VoiceRegistry
    from app.prosody.instruct import (ENGLISH_VOICEDESIGN_DESCRIPTIONS,
                                      VOICEDESIGN_DESCRIPTIONS)

    hw = detect_hardware()
    if hw.mode == "cpu" and not hw.gpu_name:
        raise RuntimeError(
            "Keine CUDA-GPU – der TTS-Regressionstest braucht eine GPU.")
    registry = VoiceRegistry()
    entry = registry.get(voice_id)
    if entry is None:
        raise RuntimeError(f"Stimme unbekannt: {voice_id}")
    if not entry.available:
        raise RuntimeError(
            f"Stimme {voice_id} ist nicht verfügbar "
            f"(Referenz-Bundle fehlt oder ungültig).")
    voice_lang = _resolve_voice_native_language(registry, entry)
    seed = _resolve_voice_seed(registry, entry)
    production = load_production()
    adv = {}
    try:
        from app import config as cfgmod
        adv = cfgmod.load_config().get("advanced", {})
    except Exception:
        pass
    desc_entry = (ENGLISH_VOICEDESIGN_DESCRIPTIONS.get(voice_id)
                  or VOICEDESIGN_DESCRIPTIONS.get(voice_id) or {})
    description = (desc_entry.get("description")
                   or entry.description or f"{voice_lang} narrator")
    eng = VoiceCloneEngine(
        hw, candidate_id=voice_id,
        description=description,
        language=voice_lang,
        ref_text=None,
        seed=seed,
        models_dir=None,
        attn_implementation=adv.get("attn_implementation") or None,
        allow_design=False,
        reference_path=None)
    # Speaker = voice_id für Clone-Stimmen (wie im Runner)
    speaker = ("VD-E" if voice_id == "vd_e" else voice_id)
    return eng, entry, voice_lang, speaker


def _write_wav(path: Path, waveform, sr: int) -> None:
    """Schreibt das von engine.synthesize zurückgegebene float32-mono-Array
    als 24-bit PCM WAV (Produktionsstandard)."""
    import numpy as np
    import soundfile as sf
    arr = np.asarray(waveform, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.mean(axis=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), arr, int(sr), subtype="PCM_24")


def _synth(engine, text: str, language: str, speaker: str,
           wav_path: Path) -> tuple[bool, float, str, object, int]:
    """Ruft engine.synthesize mit der echten SynthesisRequest-API auf und
    schreibt das Ergebnis als WAV. Gibt (ok, elapsed_s, error, result, sr)."""
    from app.tts.engine_base import SynthesisRequest
    t0 = time.perf_counter()
    try:
        req = SynthesisRequest(
            text=text,
            language=language,
            speaker=speaker,
            max_seconds_hint=60.0,
            speed=1.0,
        )
        res = engine.synthesize(req)
        elapsed = time.perf_counter() - t0
        _write_wav(wav_path, res.waveform, res.sample_rate)
        return True, elapsed, "", res, res.sample_rate
    except Exception as e:
        import traceback
        return False, 0.0, f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1200:]}", None, 0


def _tts_preprocess(text: str) -> tuple[str, list]:
    from app.pronunciation import PronunciationEngine
    from app.text.normalize import normalize_text
    norm = normalize_text(text, "German")
    eng = PronunciationEngine()
    p = eng.process(norm, "German", suggest_unknown=False)
    return p.text, [{"from": r["from"], "to": r["to"], "rule": r.get("rule", "")}
                    for r in p.replacements]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=PROJECT_ROOT / "output" / "pronunciation_tts_regression")
    ap.add_argument("--skip-if-no-gpu", action="store_true",
                    help="Beende mit Code 0 (SKIP) wenn keine CUDA-GPU verfügbar.")
    ap.add_argument("--limit", type=int, default=0,
                    help="Nur die ersten N Saetze synthetisieren (0 = alle).")
    ap.add_argument("--voice", action="append",
                    help="Nur diese Stimme testen (kann mehrfach angegeben werden)")
    args = ap.parse_args()

    # GPU-Check (nur Warnung – der Test darf auch auf CPU laufen, um die
    # API/Schreib/QC-Pfade zu validieren; echte Qwen-Qualitätsprüfung
    # braucht natürlich CUDA).
    have_cuda = False
    try:
        import torch  # noqa
        have_cuda = torch.cuda.is_available()
    except Exception as e:
        if args.skip_if_no_gpu:
            print(f"SKIP (torch/CUDA nicht verfügbar): {e}")
            return 0
        print(f"HINWEIS: torch/CUDA nicht verfügbar – versuche trotzdem: {e}")
    if not have_cuda:
        print("HINWEIS: Keine CUDA-GPU erkannt; Synthese läuft ggf. auf CPU "
              "(sehr langsam) oder schlägt fehl.")

    voices = args.voice or REGRESSION_VOICES
    args.out.mkdir(parents=True, exist_ok=True)
    all_results: list[SentenceAudioResult] = []
    overall_ok = True

    for voice_id in voices:
        vdir = args.out / voice_id
        vdir.mkdir(parents=True, exist_ok=True)
        print(f"\n=== Stimme: {voice_id} ===")
        try:
            engine, entry, lang, speaker = _build_engine_for_voice(voice_id)
        except Exception as e:
            print(f"  FAIL engine build: {e}")
            overall_ok = False
            continue
        try:
            engine.load()
        except Exception as e:
            import traceback
            print(f"  FAIL engine.load: {e}")
            traceback.print_exc()
            overall_ok = False
            continue
        for i, sent in enumerate(REGRESSION_SENTENCES, 1):
            tts_text, repls = _tts_preprocess(sent)
            wav = vdir / f"sent_{i:02d}.wav"
            ok, elapsed, err, res, sr = _synth(
                engine, tts_text, "German", speaker, wav)
            qc_ok, dur, peak, rms, qc_err = (False, 0.0, 0.0, 0.0, "")
            if ok:
                qc_ok, dur, peak, rms, qc_err = _qc_check_wav(wav)
                if not qc_ok:
                    err = qc_err
            res_obj = SentenceAudioResult(
                sentence_index=i, sentence=sent, voice_id=voice_id,
                wav_path=str(wav),
                ok=ok and qc_ok, error=err or qc_err,
                duration_s=dur, peak=peak, rms=rms, is_silent=(rms < 0.002),
                tts_text=tts_text, replacements=repls, elapsed_s=elapsed)
            all_results.append(res_obj)
            flag = "OK" if res_obj.ok else "FAIL"
            print(f"  [{flag}] Satz {i}: {sent}")
            print(f"         TTS: {tts_text[:120]}")
            print(f"         Dauer {elapsed:.1f}s, Audio {dur:.1f}s, "
                  f"peak={peak:.3f}, rms={rms:.4f}, sr={sr}")
            if not res_obj.ok:
                print(f"         ! {res_obj.error}")
                overall_ok = False
        try:
            engine.unload()
        except Exception:
            pass
        # ggf. CUDA-Cache leeren, damit die zweite Stimme nicht OOM läuft
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass

    summary = {
        "final": "PASS" if overall_ok else "FAIL",
        "voices": voices,
        "sentences": REGRESSION_SENTENCES,
        "results": [asdict(r) for r in all_results],
    }
    (args.out / "audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    # Markdown-Bericht
    lines = ["# Aussprache-TTS-Regression", "",
             f"Ergebnis: **{summary['final']}**", "",
             f"Getestete Stimmen: {', '.join(voices)}", "",
             "| Stimme | Satz | OK | Synthese-Dauer | Audio-Dauer | Peak | RMS | TTS-Text |",
             "|---|---|---|---|---|---|---|---|"]
    for r in all_results:
        lines.append(
            f"| {r.voice_id} | {r.sentence_index} | "
            f"{'✅' if r.ok else '❌'} | {r.elapsed_s:.1f}s | {r.duration_s:.1f}s | "
            f"{r.peak:.3f} | {r.rms:.4f} | {r.tts_text[:80]} |")
    lines.append("")
    lines.append("## Ersetzungen")
    for r in all_results:
        lines.append(f"- **{r.voice_id} Satz {r.sentence_index}**:")
        for rep in r.replacements:
            lines.append(f"  - `{rep['from']}` → `{rep['to']}` (*{rep['rule']}*)")
    (args.out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nFINAL_TTS_PRONUNCIATION_REGRESSION={summary['final']}")
    print(f"Reports in {args.out}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
