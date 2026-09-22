"""A/B-Hoertest (R1-Korrektur): (A) natuerliches Pacing bei speed=1.0 vs.
0.9-Stretch, (B) "Mathematik" M1 vs. M2 ueber den ECHTEN Produktionspfad,
(C) Fachbegriff-Entscheidung M2 (respelled) vs. M3 (Identity-Ausnahme).

Laeuft NUR auf dem GPU-Host (echter Qwen-TTS); ohne CUDA sauberer SKIP.

Varianten PACING (je Stimme & Text):
  V1_current : speed=1.0, kein Pacing-Hint          (aktueller Stand)
  V2_pacing  : speed=1.0 + Pacing-Hint im Instruct  (neu, nur Erzeugung)
  V3_speed09 : speed_instruct(0.9) + apply_speed(0.9) auf dem fertigen WAV
               (exakte Emulation des bisherigen 0.9-Pfads: atempo-Stretch)

Varianten MATHEMATIK (nur DE-Stimmen, je 4 Regressionssaetze):
  M1_altrespell : VOLLSTAENDIGER Produktionspfad (PronunciationEngine),
                  alle TECH_TERMS_DE-Regeln aktiv; NUR die 7 DE_MATH-
                  Werte werden temporaer auf die alten Respelling-Werte
                  von a0c79e6 gesetzt (kontextsicherer Restore).
                  = echte Emulation des alten Produktionspfads.
  M2_neu_plain  : vollstaendiger Produktionspfad von 9b026c6 (unveraendert):
                  Math-Familie Identity, alle uebrigen Regeln aktiv.

Varianten FACHBEGRIFFE M2-vs-M3 (nur DE-Stimmen, je Einwort + Satz):
  M2_respelled  : Produktionspfad unveraendert (Bindestrich-Respelling).
  M3_plain      : Produktionspfad mit gezielter Identity-Ausnahme NUR
                  fuer den jeweils getesteten Begriff.

Automatische Text-Level-Checks (landen in audit.json -> "checks"):
  - math_only_diff   : M1/M2 unterscheiden sich PRO Satz ausschliesslich
                       durch die 7 DE_MATH-Ersetzungen (alle uebrigen
                       Woerter identisch).
  - term_only_diff   : M2/M3 unterscheiden sich pro Fachbegriff
                       ausschliesslich durch den getesteten Begriff.
  - tech_terms_restore : TECH_TERMS_DE nach dem Lauf byte-identisch zum
                       Zustand davor (keine dauerhafte Aenderung).

Ausgabe: output/pacing_math_ab/<voice>/*.wav + audit.json + summary.md
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import types
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Headless-Tkinter-Stub (wie test_pronunciation_live.py)
try:
    import tkinter  # noqa: F401
except ModuleNotFoundError:
    class _M(types.ModuleType):
        TclError = type("TclError", (Exception,), {})
        class Tk: pass
        class Frame: pass
        class StringVar:
            def __init__(s, *a, **k): pass
            def get(s): return ""
            def set(s, v): pass
        class BooleanVar:
            def __init__(s, *a, **k): pass
            def get(s): return False
            def set(s, v): pass
        class DoubleVar:
            def __init__(s, *a, **k): pass
            def get(s): return 1.0
            def set(s, v): pass
        NONE = N = S = E = W = CENTER = LEFT = RIGHT = TOP = BOTTOM = ""
        HORIZONTAL = VERTICAL = BOTH = ALL = END = X = Y = ""
        DISABLED = NORMAL = ACTIVE = WORD = ""
        def __getattr__(s, n):
            return lambda *a, **k: None
    for _n in ("tkinter", "tkinter.ttk", "tkinter.filedialog",
               "tkinter.messagebox"):
        sys.modules[_n] = _M(_n)

import numpy as np  # noqa: E402

from app import paths  # noqa: E402
paths.ensure_directories()
from app.audio.assemble import apply_speed  # noqa: E402
from app.hardware.detector import detect_hardware  # noqa: E402
from app.jobs.runner import JobSpec, build_engine  # noqa: E402
from app.pronunciation import PronunciationEngine  # noqa: E402
from app.pronunciation.tech_terms import TECH_TERMS_DE  # noqa: E402
from app.prosody.instruct import pacing_hint, speed_instruct  # noqa: E402
from app.security.identity_lock import load_production  # noqa: E402
from app.text.normalize import NormalizationReport, normalize_text  # noqa: E402
from app.tts.engine_base import SynthesisRequest  # noqa: E402

OUT_DIR = paths.OUTPUT_DIR / "pacing_math_ab"

DE_VOICES = ["de_male_warm_storytelling_authoritative_01",
             "de_male_warm_calm_authoritative_02"]
EN_VOICES = ["en_male_warm_storytelling_authoritative_01"]

PACING_TEXTS = {
    "German": [
        ("de_doc_1",
         "Die Entstehung des Weltalls, die Bildung der ersten Sterne, das "
         "Werden der Galaxien - all diese Vorgaenge vollzogen sich ueber "
         "Zeitraeume, die sich der menschlichen Vorstellungskraft entziehen, "
         "und doch lassen sich ihre Spuren heute noch in jedem Winkel des "
         "Nachthimmels finden."),
        ("de_doc_2",
         "Es sind nicht die grossen Ereignisse, die Geschichte machen, "
         "sondern die leisen Entscheidungen vieler Menschen, die Tag fuer "
         "Tag, oft unbemerkt, die Richtung veraendern, in der eine Gesellschaft "
         "sich bewegt."),
    ],
    "English": [
        ("en_doc_1",
         "The mathematics, the physics, the chemistry, and the quiet "
         "practice of careful observation form the foundation upon which "
         "modern science, with all its rigor and all its beauty, has been "
         "built over centuries of inquiry, doubt, and wonder."),
        ("en_doc_2",
         "It is not the great events that shape history, but the quiet "
         "decisions of many people who, day after day, often unnoticed, "
         "change the direction in which a society is moving."),
    ],
}

MATH_SENTENCES = [
    "Mathematik ist die Sprache der Zahlen.",
    "Die Mathematik beschreibt Muster, Mengen und Strukturen.",
    "Ein mathematischer Algorithmus kann komplexe Probleme lösen.",
    "Quantenphysik und Mathematik bilden eine wichtige Grundlage moderner Forschung.",
]

# Die 7 DE_MATH-Werte EXAKT wie im Stand a0c79e6 (fuer die M1-Emulation).
# Quelle: git show a0c79e6302e9b0e3cd62d5d9cb4ecd12f92f81f4:.../tech_terms.py
OLD_MATH_RESPARRY = {
    "Mathematik": "Ma-te-MA-tik",
    "mathematisch": "ma-te-MA-tisch",
    "Mathematische": "Ma-te-MA-ti-sche",
    "mathematische": "ma-te-MA-ti-sche",
    "mathematischen": "ma-te-MA-ti-schen",
    "mathematischer": "ma-te-MA-ti-scher",
    "mathematischem": "ma-te-MA-ti-schem",
}

# Fachbegriffe fuer die M2-vs-M3-Entscheidung (R2-Gate). Jeder Begriff
# wird mit Identity-Ausnahme NUR fuer diesen Begriff getestet.
TRIAL_TERMS = [
    ("Algorithmus", "Ein Algorithmus kann komplexe Probleme lösen."),
    ("Algorithmen", "Algorithmen entscheiden heute über viele Abläufe."),
    ("Quantenphysik", "Quantenphysik verändert unser Weltbild."),
    ("Quantenmechanik", "Die Quantenmechanik beschreibt kleinste Teilchen."),
    ("Neurowissenschaft", "Die Neurowissenschaft erforscht das menschliche Gehirn."),
    ("Statistik", "Die Statistik belegt den Trend deutlich."),
    ("Psychologie", "Die Psychologie erklärt viele Verhaltensweisen."),
    ("psychologisch", "Das ist ein psychologisch interessanter Effekt."),
    ("Theorie", "Die Theorie ist bisher ungeschlagen."),
    ("Wahrscheinlichkeit", "Die Wahrscheinlichkeit steigt mit jedem Versuch."),
]


@contextmanager
def _tech_terms_override(overrides: dict):
    """Temporaere TECH_TERMS_DE-Aenderung mit GARANTIERTEM Restore.

    Alle nicht ueberschriebenen Regeln bleiben uneingeschraenkt aktiv;
    nach dem with-Block ist TECH_TERMS_DE byte-identisch zum Zustand
    davor (wird zusaetzlich ueber Hash-Check in checks geprueft).
    """
    backup = {k: TECH_TERMS_DE.get(k, _MISSING) for k in overrides}
    try:
        TECH_TERMS_DE.update(overrides)
        yield TECH_TERMS_DE
    finally:
        for k, v in backup.items():
            if v is _MISSING:
                TECH_TERMS_DE.pop(k, None)
            else:
                TECH_TERMS_DE[k] = v


class _Missing:
    pass


_MISSING = _Missing()


@contextmanager
def _term_identity_override(term: str, dictionary=None):
    """Identity-Ausnahme NUR fuer einen Fachbegriff ueber ALLE Layer.

    Der Begriff wird temporaer auf natuerliche Orthographie gesetzt in:
      1. TECH_TERMS_DE (TECH-Layer, live gelesen),
      2. dem Built-in-Woerterbuch (dictionary._builtin_de), und
      3. dem Benutzer-Woerterbuch (dictionary._user) — falls dort ein
         Eintrag fuer den Begriff existiert (User-Layer hat hoechste
         Prioritaet und wuerde die Identity sonst wieder ueberschreiben;
         das ist umgebungsabhaengig, daher generisch gehandhabt).

    Alle UEBRIGEN Regeln aller Layer bleiben uneingeschraenkt aktiv.
    Restore garantiert in finally; der _compiled-Cache wird durch die
    len-Aenderungen im Cache-Key automatisch invalidiert (zusaetzlich
    defensiv auf None gesetzt).
    """
    backup_tech = TECH_TERMS_DE.get(term, _MISSING)
    backup_builtin = None
    had_builtin = False
    backup_user = None
    had_user = False
    if dictionary is not None:
        had_builtin = term in getattr(dictionary, "_builtin_de", {})
        backup_builtin = dictionary._builtin_de.get(term) if had_builtin else None
        had_user = term in getattr(dictionary, "_user", {})
        backup_user = dictionary._user.get(term) if had_user else None
    try:
        TECH_TERMS_DE[term] = term
        if dictionary is not None and had_builtin:
            del dictionary._builtin_de[term]
            dictionary._compiled = None
        if dictionary is not None and had_user:
            del dictionary._user[term]
            dictionary._compiled = None
        yield
    finally:
        if backup_tech is _MISSING:
            TECH_TERMS_DE.pop(term, None)
        else:
            TECH_TERMS_DE[term] = backup_tech
        if dictionary is not None and had_builtin:
            dictionary._builtin_de[term] = backup_builtin
            dictionary._compiled = None
        if dictionary is not None and had_user:
            dictionary._user[term] = backup_user
            dictionary._compiled = None


def _tech_terms_hash() -> str:
    return hashlib.sha256(
        json.dumps({k: TECH_TERMS_DE[k] for k in sorted(TECH_TERMS_DE)},
                   ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _math_only_diff_check(m1: str, m2: str) -> bool:
    """True, wenn m1 aus m2 entsteht, indem NUR die 7 DE_MATH-Woerter
    durch die alten Bindestrich-Respellings ersetzt wurden (case- und
    positionsunabhaengig, da die Apply-Logik identisch laeuft)."""
    a = m1.lower()
    for k, v in OLD_MATH_RESPARRY.items():
        a = a.replace(v.lower(), k.lower())
    return a == m2.lower()


def _term_only_diff_check(m2: str, m3: str, term: str) -> bool:
    """True, wenn sich m2 -> m3 AUSSCHLIESSLICH beim Zielbegriff aendert.

    Token-basiert und vakuum-sicher: gleiche Tokenanzahl, mindestens eine
    Differenz, und jede differierende Position muss im M3-Token den
    plain-Zielbegriff enthalten. (Ein vorheriges 'replace'-Verfahren konnte
    vakuoes durchschlagen, wenn M2/M3 identisch waren.)"""
    tl = term.lower()
    if tl not in m3.lower():
        return False
    t2, t3 = m2.split(), m3.split()
    if len(t2) != len(t3):
        return False
    diffs = [(a, b) for a, b in zip(t2, t3) if a.lower() != b.lower()]
    if not diffs:
        return False
    for a, b in diffs:
        if tl not in b.lower() and tl not in a.lower():
            return False
    return True


@dataclass
class ABItem:
    voice_id: str
    part: str            # "pacing" | "math" | "terms"
    label: str           # z. B. V1_current / M2_neu_plain / M3_plain
    text_id: str
    original: str
    tts_text: str
    instruct: str
    post_speed: float    # 1.0 = keine Nachbearbeitung
    language: str = ""   # relevante Konfiguration
    speed: float = 1.0   # Generation-Speed (immer 1.0; Post nur bei V3)
    term: str = ""       # nur part="terms": getesteter Begriff
    form: str = ""       # nur part="terms": "single" | "sentence"
    dict_layer_bypassed: list = field(default_factory=list)  # gepoppte Builtins
    replacements: list = field(default_factory=list)  # Pronunciation-Regeln
    wav: str = ""
    wav_sha256: str = ""
    duration_s: float = 0.0
    elapsed_s: float = 0.0
    peak: float = 0.0
    rms: float = 0.0
    ok: bool = False
    error: str = ""


def _write_wav(path: Path, wav: np.ndarray, sr: int) -> None:
    try:
        import soundfile as sf
        sf.write(str(path), np.asarray(wav, dtype=np.float32), sr,
                 subtype="PCM_24")
    except Exception:
        import wave
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            pcm = np.clip(np.asarray(wav), -1.0, 1.0)
            pcm = (pcm * 32767).astype(np.int16)
            w.writeframes(pcm.tobytes())


def _stats(path: Path) -> tuple[float, float, float, str]:
    try:
        import soundfile as sf
        d, sr = sf.read(str(path))
        a = d if d.ndim == 1 else d.mean(axis=1)
        dur = len(a) / sr if sr else 0.0
        peak = float(np.max(np.abs(a))) if a.size else 0.0
        rms = float(np.sqrt(np.mean(a.astype(np.float64) ** 2))) if a.size else 0.0
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        return dur, peak, rms, sha
    except Exception:
        return 0.0, 0.0, 0.0, ""


def _synth(engine, text: str, language: str, instruct: str | None,
           speaker=None) -> tuple[np.ndarray, int, float]:
    req = SynthesisRequest(text=text, language=language, speaker=speaker,
                           max_seconds_hint=180.0, speed=1.0,
                           instruct=instruct or None)
    t0 = time.perf_counter()
    res = engine.synthesize(req)
    return (np.asarray(res.waveform, dtype=np.float32).reshape(-1),
            int(res.sample_rate), time.perf_counter() - t0)


def _record(items: list, engine, vdir: Path, *, voice_id: str, part: str,
            label: str, text_id: str, original: str, tts_text: str,
            language: str, instruct: str, post: float, term: str = "",
            form: str = "", dict_layer_bypassed: list | None = None,
            replacements: list | None = None,
            fname: str = "") -> None:
    item = ABItem(voice_id=voice_id, part=part, label=label, text_id=text_id,
                  original=original, tts_text=tts_text, instruct=instruct or "",
                  post_speed=post, language=language, speed=1.0, term=term,
                  form=form, dict_layer_bypassed=dict_layer_bypassed or [],
                  replacements=replacements or [])
    try:
        wav, sr, elapsed = _synth(engine, tts_text, language, instruct)
        if abs(post - 1.0) >= 0.02:
            wav, sr = apply_speed(wav, sr, post)
        wpath = vdir / fname
        _write_wav(wpath, wav, sr)
        dur, peak, rms, sha = _stats(wpath)
        item.wav = str(wpath)
        item.wav_sha256 = sha
        item.duration_s, item.peak, item.rms = dur, peak, rms
        item.elapsed_s = elapsed
        item.ok = dur > 1.0 and rms > 0.002
        print(f"  [{'OK' if item.ok else 'WEAK'}] {label:14s} {text_id}: "
              f"{dur:6.1f}s  peak={peak:.3f} rms={rms:.4f}")
        if part in ("math", "terms"):
            print(f"         TTS: {tts_text}")
    except Exception as e:
        item.error = f"{type(e).__name__}: {e}"
        print(f"  [FAIL] {label} {text_id}: {item.error}")
    items.append(item)


def main() -> int:
    hw = detect_hardware()
    if not getattr(hw, "cuda_available", False) and not getattr(hw, "gpu_name", ""):
        print("SKIP (keine CUDA-GPU): A/B-Hoertest nur auf dem GPU-Host "
              "ausfuehrbar.")
        return 0
    production = load_production()
    pron = PronunciationEngine()
    items: list[ABItem] = []
    checks: dict = {"math_only_diff": [], "term_only_diff": [],
                    "tech_terms_restore": None}
    hash_before = _tech_terms_hash()

    voices = [(v, "German") for v in DE_VOICES] + [(v, "English") for v in EN_VOICES]
    for voice_id, language in voices:
        print(f"\n=== {voice_id} ({language}) ===")
        spec = JobSpec(voice_id=voice_id, text=".", language=language,
                       speed=1.0, formats="wav", output_mode="full")
        try:
            engine, entry = build_engine(spec, production)
            engine.load()
        except Exception as e:
            print(f"  SKIP (build/load fehlgeschlagen): {e}")
            continue
        vdir = OUT_DIR / voice_id
        vdir.mkdir(parents=True, exist_ok=True)

        # ---------------- Part A: Pacing ----------------
        for text_id, text in PACING_TEXTS[language]:
            norm = normalize_text(text, language, NormalizationReport())
            pacing = pacing_hint(language)
            variants = [
                ("V1_current", None, 1.0),
                ("V2_pacing", pacing, 1.0),
                ("V3_speed09", speed_instruct(0.9), 0.9),
            ]
            for label, instr, post in variants:
                _record(items, engine, vdir, voice_id=voice_id, part="pacing",
                        label=label, text_id=text_id, original=text,
                        tts_text=norm, language=language, instruct=instr or "",
                        post=post, fname=f"{text_id}_{label}.wav")

        # ---------------- Part B: Mathematik (M1 vs M2) ----------------
        if language == "German":
            for i, sent in enumerate(MATH_SENTENCES, 1):
                norm = normalize_text(sent, "German", NormalizationReport())
                # M2 = Produktionspfad 9b026c6 (unveraendert)
                r_m2 = pron.process(norm, "German", suggest_unknown=False)
                # M1 = Produktionspfad-Emulation a0c79e6: ALLE Regeln
                # aktiv, NUR die 7 DE_MATH-Werte auf Alt-Stand (Restore
                # garantiert durch Kontextmanager).
                with _tech_terms_override(OLD_MATH_RESPARRY):
                    r_m1 = pron.process(norm, "German", suggest_unknown=False)
                ok_diff = _math_only_diff_check(r_m1.text, r_m2.text)
                checks["math_only_diff"].append(
                    {"sentence": i, "only_math_differs": ok_diff})
                print(f"  [CHECK] Satz {i}: M1/M2 unterscheiden sich "
                      f"ausschliesslich durch DE_MATH: "
                      f"{'JA' if ok_diff else 'NEIN (!!)'}")
                for label, res in (("M1_altrespell", r_m1),
                                   ("M2_neu_plain", r_m2)):
                    _record(items, engine, vdir, voice_id=voice_id, part="math",
                            label=label, text_id=f"math_{i:02d}",
                            original=sent, tts_text=res.text,
                            language="German", instruct="", post=1.0,
                            replacements=[{"from": x["from"], "to": x["to"],
                                           "rule": x.get("rule", "")}
                                          for x in res.replacements],
                            fname=f"math_{i:02d}_{label}.wav")

            # ------- Part C: Fachbegriffe (M2 vs M3, single+sentence) -------
            for k, (term, sentence) in enumerate(TRIAL_TERMS, 1):
                for form, text in (("single", term + "."), ("sentence", sentence)):
                    norm = normalize_text(text, "German", NormalizationReport())
                    r_m2 = pron.process(norm, "German", suggest_unknown=False)
                    bypassed: list = []
                    if term in pron.dictionary._builtin_de:
                        bypassed.append("builtin:" + term)
                    if term in pron.dictionary._user:
                        bypassed.append("user:" + term)
                    with _term_identity_override(term, pron.dictionary):
                        r_m3 = pron.process(norm, "German", suggest_unknown=False)
                    ok_diff = _term_only_diff_check(r_m2.text, r_m3.text, term)
                    checks["term_only_diff"].append(
                        {"term": term, "form": form, "only_term_differs": ok_diff,
                         "dict_layer_bypassed": bypassed})
                    if not ok_diff:
                        print(f"  [CHECK-FAIL] {term} ({form}): M2/M3-Unterschied "
                              f"betrifft mehr als den Zielbegriff!")
                    for label, res in (("M2_respelled", r_m2),
                                       ("M3_plain", r_m3)):
                        _record(items, engine, vdir, voice_id=voice_id,
                                part="terms", label=label,
                                text_id=f"{term}_{form}", original=text,
                                tts_text=res.text, language="German",
                                instruct="", post=1.0, term=term, form=form,
                                dict_layer_bypassed=bypassed,
                                replacements=[{"from": x["from"], "to": x["to"],
                                               "rule": x.get("rule", "")}
                                              for x in res.replacements],
                                fname=f"term_{k:02d}_{term}_{form}_{label}.wav")

        try:
            engine.unload()
        except Exception:
            pass

    # ---------------- Abschluss-Checks + Reports ----------------
    hash_after = _tech_terms_hash()
    checks["tech_terms_restore"] = {
        "hash_before": hash_before, "hash_after": hash_after,
        "unchanged": hash_before == hash_after}
    math_ok = all(c["only_math_differs"] for c in checks["math_only_diff"])
    term_ok = all(c["only_term_differs"] for c in checks["term_only_diff"])
    checks["summary"] = {
        "math_only_diff_ALL": math_ok,
        "term_only_diff_ALL": term_ok,
        "tech_terms_unchanged": hash_before == hash_after,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "audit.json").write_text(
        json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "checks": checks,
                    "items": [asdict(x) for x in items]},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")

    lines = ["# A/B Hoertest (R1): Pacing (V1/V2/V3) + Mathematik (M1/M2) "
             "+ Fachbegriffe (M2/M3)", "",
             "## Checks (Text-Ebene, automatisch)", "",
             f"- M1/M2 nur-DE_MATH-Unterschied (alle 4 Saetze): "
             f"{'PASS' if math_ok else 'FAIL'}",
             f"- M2/M3 nur-Zielbegriff-Unterschied (alle {len(checks['term_only_diff'])} "
             f"Messungen): {'PASS' if term_ok else 'FAIL'}",
             f"- TECH_TERMS_DE nach Lauf unveraendert: "
             f"{'PASS' if hash_before == hash_after else 'FAIL'}", "",
             "| Stimme | Teil | Label | Begriff/Form | Dauer | SHA256 (Kurz) | WAV |",
             "|---|---|---|---|---|---|---|"]
    for x in items:
        lines.append(
            f"| {x.voice_id} | {x.part} | {x.label} | "
            f"{x.term or x.text_id}{(':' + x.form) if x.form else ''} | "
            f"{x.duration_s:.1f}s | {x.wav_sha256[:12]} | "
            f"{Path(x.wav).name if x.wav else '-'} |")
    lines += ["", "Hinweis: V2_pacing = neuer Produktionspfad (speed=1.0, "
              "Erzeugung entspannter, KEIN Stretch). V3_speed09 nur als "
              "Referenz (alter 0.9-Stretch). M2/M3-Differenz pro Begriff "
              "ausschliesslich der getestete Fachbegriff.", ""]
    (OUT_DIR / "summary.md").write_text("\n".join(lines),
                                        encoding="utf-8")
    n_ok = sum(1 for x in items if x.ok)
    print(f"\nCHECKS: math_only_diff={'PASS' if math_ok else 'FAIL'} "
          f"term_only_diff={'PASS' if term_ok else 'FAIL'} "
          f"tech_terms_restore={'PASS' if hash_before == hash_after else 'FAIL'}")
    print(f"FERTIG: {n_ok}/{len(items)} Aufnahmen OK "
          f"({len(items)} WAVs erwartet)")
    print(f"Reports: {OUT_DIR / 'audit.json'} | {OUT_DIR / 'summary.md'}")
    return 0 if items else 1


if __name__ == "__main__":
    raise SystemExit(main())
