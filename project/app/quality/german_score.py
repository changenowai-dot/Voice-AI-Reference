"""GermanNaturalnessScore (Phase 1, Anforderung 6 + 24).

SEPARATER Vergleichs-Score für deutsche Qualität – bewusst nicht
identisch mit dem allgemeinen QualityScore und ausdrücklich keine
objektive Messung menschlicher Wahrnehmung (Anforderung 46).

Teilbereiche:
  pronunciation   – Aussprache-Plausibilität (Silben-basierte
                    Dauererwartung für Deutsch, ~4,2 Silben/s)
  prosody_de      – deutsche Satzmelodie: Deklination über den Satz,
                    Fragemelodie wenn der Text eine Frage ist,
                    Intonationsbreite (F0-Variation in Halbtönen)
  rhythm          – Sprechrhythmus: Variabilität stimmhafter Abschnitte
                    und Pausen (zu gleichförmig = mechanisch,
                    zu unruhig = gestört)
  naturalness     – Kombination der oberen drei
  pauses          – Pausenbild im Segment (Anteil, Längenspread)
  consistency     – Abweichung von Projektmedian (LUFS, F0)
  foreign_words   – Anteil entschieden behandelter Fremdwörter (Metadaten)
  names           – Abdeckung riskanter Eigennamen (Metadaten)
  numbers         – sind nach Normalisierung keine Rohtext-Ziffern
                    übrig geblieben? (Metadaten)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from ..audio.ebu_r128 import integrated_lufs
from .metrics import basic_stats

# Deutsche Sprechgeschwindigkeit (Dokumentation): ~4,2 Silben/s
SYLLABLES_PER_SECOND_DE = 4.2
RATE_RANGE = (3.1, 5.6)            # akzeptables Band
_QUESTION_END_EXPECT_RISE_ST = 1.0  # minimale Anhebung am Satzende (Halbtöne)
_STATEMENT_EXPECT_FALL_ST = -0.5

_VOWEL_GROUPS = re.compile(r"[aeiouäöüy]+", re.I)


def count_syllables_de(text: str) -> int:
    """Nähert deutsche Silben über Vokalgruppen an."""
    words = re.findall(r"[A-Za-zÄÖÜäöüß]+", text)
    n = 0
    for w in words:
        groups = len(_VOWEL_GROUPS.findall(w))
        n += max(1, groups)
    return n


def f0_series(wav: np.ndarray, sr: int, frame_ms: int = 60):
    """F0-Verlauf (t, f0) via Autokorrelation (ausgelagert aus metrics)."""
    from .metrics import _autocorr_f0
    n = max(1, int(sr * frame_ms / 1000.0))
    series = []
    for i in range(0, max(len(wav) - n + 1, 1), n):
        frame = np.asarray(wav[i:i + n], dtype=np.float64)
        f0 = _autocorr_f0(frame, sr)
        series.append((i / sr, f0))
    return series


def _semitones(f_lo: float, f_hi: float) -> float:
    if f_lo <= 0 or f_hi <= 0:
        return 0.0
    return 12.0 * np.log2(f_hi / f_lo)


@dataclass
class GermanScore:
    pronunciation: float = 100.0
    prosody_de: float = 100.0
    rhythm: float = 100.0
    naturalness: float = 100.0
    pauses: float = 100.0
    consistency: float = 100.0
    foreign_words: float = 100.0
    names: float = 100.0
    numbers: float = 100.0
    overall: float = 100.0
    issues: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: (round(v, 1) if isinstance(v, float) else v)
                for k, v in self.__dict__.items()}

    @property
    def critical(self) -> bool:
        """Harte Kriterien (Anforderung 21):>=1 kritisches Issue ->
        Segment gilt NICHT als gut genug, unabhängig vom Score."""
        return any(i in ("rate_out_of_range", "question_melody_missing",
                         "no_voiced_speech", "duration_implausible")
                   for i in self.issues)


def _voiced_runs(wav: np.ndarray, sr: int) -> tuple[list[float], list[float]]:
    """Längen stimmhafter Abschnitte und interner Pausen (Sekunden)."""
    frame = max(1, int(sr * 0.02))
    n = len(wav) // frame
    if n == 0:
        return [], []
    abs_w = np.abs(np.asarray(wav[:n * frame]).reshape(n, frame)).mean(axis=1)
    loud = abs_w > 0.004
    voiced: list[float] = []
    pauses: list[float] = []
    run_v = 0
    run_p = 0
    started = False
    for l in loud:
        if l:
            if run_v == 0 and started:
                if run_p * 0.02 >= 0.12:
                    pauses.append(run_p * 0.02)
                run_p = 0
            run_v += 1
            started = True
        else:
            if run_v:
                voiced.append(run_v * 0.02)
                run_v = 0
            if started:
                run_p += 1
    if run_v:
        voiced.append(run_v * 0.02)
    return voiced, pauses


def score_german(wav: np.ndarray, sr: int, tts_text: str,
                 meta: dict | None = None,
                 project_baseline: dict | None = None) -> GermanScore:
    """Berechnet den deutschen Vergleichs-Score für ein Segment.

    meta: Pipeline-Metadaten (names/foreign/numbers-Info).
    project_baseline: {"lufs": x, "f0": y} gelernter Projektmedian.
    """
    meta = meta or {}
    s = GermanScore()
    wav = np.asarray(wav, dtype=np.float32)

    # ---- Aussprache: Dauer-Plausibilität über Silben --------------------
    syllables = max(1, count_syllables_de(tts_text))
    dur = len(wav) / sr
    expected = syllables / SYLLABLES_PER_SECOND_DE
    rate = syllables / max(dur, 1e-6)
    if dur < 0.35:
        s.pronunciation = 10.0
        s.issues.append("duration_implausible")
        s.notes.append(f"dur={dur:.2f}s bei {syllables} Silben")
    else:
        ratio = dur / expected
        if ratio < 0.6:
            s.pronunciation = 45.0
            s.issues.append("duration_implausible")
        elif ratio > 1.7:
            s.pronunciation = 40.0
            s.issues.append("duration_implausible")
        else:
            s.pronunciation = float(np.clip(100 - abs(1 - ratio) * 70, 0, 100))
    if not (RATE_RANGE[0] <= rate <= RATE_RANGE[1]) and dur >= 0.35:
        s.issues.append("rate_out_of_range")
        s.notes.append(f"rate={rate:.1f} Silben/s")

    # ---- Prosodie: F0-Verlauf, Fragemelodie, Spannweite ------------------
    series = [(t, f) for t, f in f0_series(wav, sr) if f > 0]
    voiced_ratio = len(series) / max(1, len(f0_series(wav, sr)))
    if not series:
        s.prosody_de = 40.0
        s.issues.append("no_voiced_speech")
    else:
        f0s = np.array([f for _, f in series], dtype=np.float64)
        f0_med = float(np.median(f0s))
        # Intonationsbreite (Halbtöne zwischen 10.- und 90.-Perzentil)
        p10, p90 = np.percentile(f0s, 10), np.percentile(f0s, 90)
        span_st = _semitones(p10, p90)
        if span_st < 1.0:
            s.prosody_de = 55.0
            s.issues.append("monotone")
        elif span_st > 12.0:
            s.prosody_de = 75.0      # übertrieben wackelig
        else:
            s.prosody_de = float(np.clip(60 + span_st * 6.0, 0, 100))
        # Satzend-Melodie
        tail = series[-max(3, len(series) // 4):]
        head = series[:max(3, len(series) // 4)]
        if len(tail) >= 2 and len(head) >= 2:
            tail_f = float(np.median([f for _, f in tail]))
            head_f = float(np.median([f for _, f in head]))
            end_change = _semitones(min(head_f, tail_f), max(head_f, tail_f)) \
                * (1 if tail_f >= head_f else -1)
            is_question = tts_text.rstrip().endswith("?")
            if is_question and end_change < _QUESTION_END_EXPECT_RISE_ST:
                s.prosody_de -= 25.0
                s.issues.append("question_melody_missing")
                s.notes.append(f"Frage ohne steigende Endmelodie "
                               f"({end_change:.1f} st)")
            elif not is_question and end_change > 2.5:
                s.prosody_de -= 10.0      # Aussage mit Frage-Melodie
                s.notes.append("Aussage steigt am Ende (englisch anmutend)")
        # Deklination: leichte Abnahme über die Zeit ist natürlich
        if len(series) >= 6:
            half = len(series) // 2
            first_f = np.median([f for _, f in series[:half]])
            second_f = np.median([f for _, f in series[half:]])
            decl = _semitones(second_f, first_f)      # >0 = fallend
            if decl < -1.5:                            # stark steigend
                s.prosody_de -= 12.0
                s.notes.append("keine natürliche Deklination")
        s.prosody_de = float(np.clip(s.prosody_de, 0, 100))

    # ---- Rhythmus: Variabilität stimmhafter Abschnitte -------------------
    voiced, pauses = _voiced_runs(wav, sr)
    if len(voiced) >= 3:
        v = np.array(voiced)
        cv = float(np.std(v) / max(np.mean(v), 1e-6))
        # mechanisch: cv ~ 0; natürlich deutscher Fluss: 0.25-0.8
        if cv < 0.12:
            s.rhythm = 55.0
            s.issues.append("mechanical_rhythm")
        elif cv > 1.4:
            s.rhythm = 65.0
            s.issues.append("erratic_rhythm")
        else:
            s.rhythm = float(np.clip(75 + 50 * min(cv / 0.5, 1.0), 0, 100))
    else:
        s.rhythm = 80.0

    # ---- Pausen im Segment ------------------------------------------------
    if pauses:
        longest = max(pauses)
        if longest > 2.2:
            s.pauses = 55.0
            s.issues.append("long_pause")
        elif longest > 1.4:
            s.pauses = 78.0
        else:
            s.pauses = 95.0
        if len(pauses) >= 3:
            pcv = float(np.std(pauses) / max(np.mean(pauses), 1e-6))
            if pcv < 0.05:
                s.pauses -= 15.0
                s.issues.append("mechanical_pauses")
    else:
        s.pauses = 92.0

    # ---- Konsistenz gegen Projektmedian ------------------------------------
    if project_baseline:
        base_lufs = project_baseline.get("lufs")
        base_f0 = project_baseline.get("f0")
        cons = 100.0
        if base_lufs is not None:
            lufs = integrated_lufs(wav, sr)
            dev = abs(lufs - base_lufs)
            cons -= min(45.0, max(0.0, dev - 4.0) * 8.0)
        if base_f0 is not None and series:
            f0_med = float(np.median([f for _, f in series]))
            f0dev = abs(f0_med - base_f0) / max(base_f0, 1.0)
            cons -= min(35.0, max(0.0, f0dev - 0.05) * 220.0)
        s.consistency = float(np.clip(cons, 0, 100))

    # ---- Metadaten-basierte Bereiche ---------------------------------------
    fw = meta.get("foreign_words")
    if fw:
        decided = fw.get("decided", fw.get("total", 0))
        total = fw.get("total", decided)
        s.foreign_words = float(np.clip(
            100.0 * (decided / total) if total else 100.0, 40, 100))
    names_info = meta.get("names")
    if names_info:
        risky = names_info.get("risky_total", 0)
        covered = names_info.get("risky_covered", 0)
        s.names = float(np.clip(
            100.0 if risky == 0 else 100.0 * covered / risky, 30, 100))
        if risky and covered == 0:
            s.notes.append(f"{risky} riskante Eigennamen ohne Aussprache")
    numbers_left = len(re.findall(r"\d", tts_text))
    s.numbers = 100.0 if numbers_left == 0 else \
        max(40.0, 100.0 - numbers_left * 4)

    # ---- Gewichtetes Gesamt -------------------------------------------------
    s.naturalness = float(np.clip(
        0.40 * s.prosody_de + 0.30 * s.rhythm + 0.30 * s.pronunciation, 0, 100))
    s.overall = float(np.clip(
        0.28 * s.naturalness +
        0.18 * s.prosody_de +
        0.12 * s.rhythm +
        0.10 * s.pauses +
        0.10 * s.consistency +
        0.08 * s.pronunciation +
        0.06 * s.foreign_words +
        0.05 * s.names +
        0.03 * s.numbers, 0, 100))
    return s


def baseline_from(scores: list[dict]) -> dict:
    """Lernt Projektmedian (LUFS/F0) aus als gut bewerteten Segmenten."""
    lufs = [m["lufs"] for m in scores if m.get("lufs", -99) > -60]
    f0s = [m["f0_median_hz"] for m in scores if m.get("f0_median_hz")]
    return {"lufs": float(np.median(lufs)) if lufs else None,
            "f0": float(np.median(f0s)) if f0s else None}
