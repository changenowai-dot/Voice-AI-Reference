"""Quality Control + Quality Score (Anforderung 42–46).

Bewertet jedes Segment anhand messbarer Kriterien. Der Score dient dem
VERGLEICH von Varianten und der Regenerierungs-Steuerung – er ist keine
absolute wissenschaftliche Messung von „Menschlichkeit“.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..logging_setup import get_logger, qlog
from .german_score import GermanScore, score_german
from .metrics import analyze_segment_audio

log = get_logger("quality")

# Erwartete Sprechrate (Zeichen/s) – wird aus guten Segmenten adaptiv gelernt
DEFAULT_CHARS_PER_SEC = {"de": 13.8, "en": 15.0}

ISSUE_LABELS = {
    "too_short": "Audio deutlich kürzer als Text erwarten lässt (Wörter verloren?)",
    "too_long": "Audio deutlich länger als erwartet (Wiederholung/Hänger?)",
    "clipping": "Übersteuerung (Clipping)",
    "nan": "Ungültige Samples (NaN/Inf)",
    "dropout": "Digitale Aussetzer",
    "long_pause": "Unnatürlich lange interne Pause",
    "too_quiet": "Segment auffällig leiser als Projektmedian",
    "too_loud": "Segment auffällig lauter als Projektmedian",
    "monotone": "Auffällig monotone Satzmelodie (F0-Varianz sehr gering)",
    "mechanical_rhythm": "Sehr gleichförmiger Rhythmus (KI-typisch)",
    "noise_like": "Rauschartiges Spektrum (Artefakt)",
    "tonal_artifact": "Tonales/Nicht-Sprach-Artefakt (Sinuston/Feedback/Sirene)",
    "low_voiced_content": "Zu wenig stimmhafte Sprache im Segment (Flüstern/Ton/Rauschen)",
    "dc_offset": "Gleichspannungsversatz",
    "edge_silence": "Überlange Randstille",
    "silence": "Segment besteht fast nur aus Stille",
}


@dataclass
class QualityScore:
    naturalness: float = 100.0
    pronunciation_plausibility: float = 100.0
    prosody: float = 100.0
    consistency: float = 100.0
    audio_integrity: float = 100.0
    overall: float = 100.0
    issues: list = field(default_factory=list)
    german: dict | None = None          # GermanNaturalnessScore (Phase 1)

    @property
    def critical(self) -> bool:
        """Katastrophale Fehler (Anforderung 21): Audio ist unbrauchbar
        (keine Stimme, Rauschen, NaN, Dropouts, Clipping, Stille) –
        MUSS regeneriert werden, auch bei Score 85+.

        Dauer-/Prosodieabweichungen (too_short/too_long/monotone/long_pause
        /duration_implausible/rate_out_of_range/question_melody_missing)
        sind QUALITÄTS-Probleme, keine Integritätsfehler: sie beeinflussen
        den Score/das Ranking, blockieren aber NICHT die Final-Gate,
        wenn die Sprachqualität ansonsten hoch ist und alle Retries
        keine bessere Alternative liefern. Andernfalls würden 90+-Score,
        klar stimmhafte Segmente wegen einer Dauerabweichung von wenigen
        Prozent verworfen – ein Fehlalarm, der im Host-Log massiv
        auftrat (z.B. score=93.1, dur=26.9s, f0=200Hz, LUFS=-19 als
        "kritisch" eingestuft und blockiert).

        0.16s-Stille/Kollaps wird weiterhin zuverlässig blockiert:
        qc.check() fügt in diesem Fall immer "silence" (hard-set) hinzu.

        Tonale/halbleere Artefakte (Sinustöne, Feedback-Pfeifen, Brumm-
        töne, fast-tonale Synthesizer-Fehler) werden über die
        Sprach-Integritätsprüfung erkannt ("tonal_artifact" /
        "low_voiced_content") und ebenfalls HARD geblockt. Das waren
        die im Human-Listen festgestellten falsch-positiven: sie haben
        eine plausible F0/LUFS und geringes Rauschen, sind aber keine
        verständliche Sprache.
        """
        # Nur wirklich unbrauchbare Audio-Integritätsfehler
        hard = {"clipping", "dropout", "nan", "noise_like", "silence",
                "tonal_artifact", "low_voiced_content"}
        if hard & set(self.issues):
            return True
        # German-seitig: nur "keine Sprache" ist katastrophal.
        # duration_implausible/rate_out_of_range/question_melody_missing
        # sind Qualitäts-Probleme (Prosodie/Aussprache), keine
        # Integritätsfehler – sie werden über den Score/Ranking
        # abgebildet, blockieren aber nicht die Final-Gate.
        g = self.german or {}
        if g.get("critical"):
            gi = set(g.get("issues") or [])
            if "no_voiced_speech" in gi:
                return True
        return False

    def to_dict(self) -> dict:
        return {
            "naturalness": round(self.naturalness, 1),
            "pronunciation": round(self.pronunciation_plausibility, 1),
            "prosody": round(self.prosody, 1),
            "consistency": round(self.consistency, 1),
            "audio_integrity": round(self.audio_integrity, 1),
            "overall": round(self.overall, 1),
            "issues": list(self.issues),
            "german": self.german,
        }


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


class SegmentQC:
    """Prüft ein Segment; kontextabhängig (Projektmedian, gelernte Rate).

    Phase 1: Zusätzlich wird für deutsche Segmente der separate
    GermanNaturalnessScore erhoben (Vergleichsmaßstab, keine
    Menschlichkeitsmessung) und in harte Kriterien eingebaut.
    """

    def __init__(self, language: str = "German"):
        self.lang_key = "de" if language.lower().startswith("ger") else "en"
        self.chars_per_sec = DEFAULT_CHARS_PER_SEC[self.lang_key]
        self.project_lufs: list[float] = []
        self.project_f0: list[float] = []

    def observe_good(self, metrics: dict) -> None:
        """Lernt aus als gut bewerteten Segmenten (adaptive Basislinie)."""
        self.project_lufs.append(metrics.get("lufs", -20.0))
        if metrics.get("f0_median_hz"):
            self.project_f0.append(metrics["f0_median_hz"])

    def german_baseline(self) -> dict:
        import numpy as np
        lufs = [v for v in self.project_lufs if v > -60]
        return {"lufs": float(np.median(lufs)) if lufs else None,
                "f0": float(np.median(self.project_f0))
                if self.project_f0 else None}

    # ---------------------------------------------------------------------
    def check(self, wav: np.ndarray, sr: int, text: str,
              german_meta: dict | None = None) -> tuple[QualityScore, dict]:
        m = analyze_segment_audio(wav, sr)
        score = QualityScore()
        issues: list[str] = []

        # Phase 1: separater deutscher Score (Vergleichsmaßstab)
        if self.lang_key == "de":
            g = score_german(wav, sr, text, meta=german_meta,
                             project_baseline=self.german_baseline())
            score.german = g.to_dict()
            for gi in g.issues:
                if gi not in ("mechanical_pauses",):     # doppelt unten
                    issues.append(gi)

        # ---- Dauer-Plausibilität (Wortverlust/Wiederholung) ----------------
        chars = max(len(text), 1)
        expected_s = chars / self.chars_per_sec
        dur = m["duration_s"]
        ratio = dur / expected_s if expected_s > 0 else 1.0
        if ratio < 0.40:
            # Extrem zu kurz: selbst bei sauberem Waveform ist der
            # Inhalt verloren → starke Herabsetzung. Unter 0.5s
            # zusätzlich low_voiced_content / unbrauchbar.
            score.pronunciation_plausibility = _clamp(
                10.0 + 40.0 * (ratio / 0.40))
            issues.append("too_short")
            if dur >= 0.5 and voiced_ratio < 0.35:
                issues.append("low_voiced_content")
        elif ratio < 0.62:
            score.pronunciation_plausibility = _clamp(
                45 + 50 * (ratio / 0.62))
            issues.append("too_short")
        elif ratio > 1.55:
            score.pronunciation_plausibility = _clamp(
                100 - (ratio - 1.55) * 80)
            issues.append("too_long")
        elif ratio > 1.35:
            score.pronunciation_plausibility = _clamp(100 - (ratio - 1.35) * 120)
        else:
            score.pronunciation_plausibility = 100.0 - abs(1.0 - ratio) * 25

        # ---- Audio-Integrität ----------------------------------------------
        integ = 100.0
        if m["has_nan"]:
            integ = 0.0
            issues.append("nan")
        if m["clip_ratio"] > 0.0005:
            integ -= min(40.0, m["clip_ratio"] * 20000)
            issues.append("clipping")
        if m["dropout_count"] > 0:
            integ -= 15.0 * m["dropout_count"]
            issues.append("dropout")
        if abs(m["dc_offset"]) > 0.02:
            integ -= 15.0
            issues.append("dc_offset")
        if m["spectral_flatness"] > 0.45:
            integ -= 25.0
            issues.append("noise_like")
        if m["leading_ms"] > 1200 or m["trailing_ms"] > 1500:
            integ -= 8.0
            issues.append("edge_silence")
        if m.get("silence_ratio", 0.0) > 0.9:
            integ -= 30.0
            issues.append("silence")

        # ---- Sprach-Integrität (keine ASR, aber robust gegen
        # tonale/halbleere Artefakte, die bei altem QC als "gute Stimme"
        # durchkamen) ----------------------------------------------------
        #
        # Menschliche Sprache hat einen breiten Frequenzgehalt
        # (Formanten F1-F3 + Zischlaute), hohe Momentan-Frequenz-
        # Variation und einen ZCR/Spectral-Centroid deutlich über
        # einem reinen Sinuston/Brummton. Diese Heuristiken ersetzen
        # KEINE ASR, trennen aber verlässlich:
        #   - reine Sinus-/Brummtöne          → tonal_artifact (BLOCK)
        #   - sehr schmalbandige Synthese     → tonal_artifact (BLOCK)
        #   - Flüstern/Rauschen ohne Stimme   → low_voiced_content (BLOCK)
        #   - normale stimmhafte Sprache      → keine Flag
        voiced_ratio = m.get("voiced_ratio", 0.0)
        cent_mean = m.get("spectral_centroid_mean", 0.0)
        cent_std = m.get("spectral_centroid_std", 0.0)
        zcr = m.get("zcr_per_s", 0.0)
        sf = m["spectral_flatness"]

        # Achtung: Starke Übersteuerung (clipping) erzeugt ebenfalls
        # Rechteck-ähnliche, sehr tonale Spektren – da clipping bereits
        # als katastrophal klassifiziert ist, blenden wir es hier aus,
        # damit "tonal_artifact" nur echte Nichttöne (Sinuston/Brumm/
        # Feedback-Pfeifen) meint.
        is_clipped = m["clip_ratio"] > 0.0005
        # (a) Fast-reiner Ton (niedrig-mittlere Frequenz): sehr flache
        #     Momentanfrequenz + schmaler Schwerpunkt + sehr geringes
        #     Spektralrauschen. Reiner Sinus/Zwei-Ton-Brumm hat
        #     cent_std nahe 0, sf≈0. Selbst monotone Vokale mit
        #     mehreren Harmonischen erreichen cent_std~25+ und
        #     cent_mean~900-1200, also trennen wir hier sauber.
        # cent_mean < 500 Hz: Sprache (selbst tiefe Männerstimmen)
        # hat durch F2/F3 und Zischlaute einen Spektral-Schwerpunkt
        # deutlich über 600–800 Hz. Nur Sinustöne/Brummtöne liegen
        # unter 500 Hz bei sehr kleinem cent_std und sehr niedrigem sf.
        if (m["duration_s"] >= 0.5 and not is_clipped
                and cent_std < 80.0
                and cent_mean < 500.0
                and sf < 0.10):
            integ -= 60.0
            issues.append("tonal_artifact")
        # (b) Schmalbandiger Pfeifton / Feedback bei höherer Frequenz:
        #     cent_mean kann auch über 800 Hz liegen (z.B. 1.2 kHz
        #     Feedback), aber cent_std ist nahe 0 und das Spektrum ist
        #     extrem tonal (sf < 0.05). Sprache hat cent_std ≫ 100 Hz
        #     durch Formantbewegung/Konsonanten/Zischlaute.
        elif (m["duration_s"] >= 0.5 and not is_clipped
                and cent_std < 30.0
                and sf < 0.05):
            integ -= 60.0
            issues.append("tonal_artifact")
        # (c) Zu wenig stimmhafter Anteil: trotz Dauer im plausiblen
        #     Bereich ist weniger als 40% der Frames "voiced"
        #     (F0 erkannt). Das fängt Flüstern/Rauschen/Atem/Ton-
        #     fragmente ein, die LUFS-technisch gut klingen aber
        #     keine nachweisbare stimmhafte Sprache enthalten.
        elif m["duration_s"] >= 0.5 and voiced_ratio < 0.35:
            integ -= 50.0
            issues.append("low_voiced_content")

        score.audio_integrity = _clamp(integ)

        # ---- Pausen natürlich? ----------------------------------------------
        pause_pen = 0.0
        if m["longest_internal_pause_s"] > 2.2:
            pause_pen += 30.0
            issues.append("long_pause")
        elif m["longest_internal_pause_s"] > 1.4:
            pause_pen += 12.0
        if m["internal_pause_count"] >= 1:
            pauses = m["internal_pauses"]
            pvar = float(np.std(pauses)) if len(pauses) > 1 else 0.0
            if len(pauses) >= 3 and pvar < 0.05:
                pause_pen += 10.0      # immer identische Pausen (Anf. 43)
                issues.append("mechanical_rhythm")

        # ---- Prosodie (F0-Variation) ---------------------------------------
        f0cv = m.get("f0_cv", 0.0)
        if m.get("f0_median_hz", 0) > 0:
            # Sehr sehr geringe F0-Variation KOMBINIERT mit hohem Stimm-
            # anteil und sehr tonalem Spektrum → praktisch ein
            # Sinus-Drohne (wird oben als tonal_artifact erkannt).
            # Die "monotone"-Flagge bleibt für flache menschliche
            # Prosodie reserviert (nicht blockierend), aber ein
            # buchstäblicher Ein-Ton f0cv<0.005 ist nie Sprache.
            if f0cv < 0.005 and voiced_ratio > 0.8 and cent_mean < 800.0:
                # Ist bereits über tonal_artifact abgedeckt, falls
                # nicht: zusätzlich als drone markieren.
                if "tonal_artifact" not in issues:
                    integ -= 60.0
                    issues.append("tonal_artifact")
                score.prosody = _clamp(30.0)
            elif f0cv < 0.015:
                score.prosody = _clamp(55.0)
                issues.append("monotone")
            elif f0cv < 0.03:
                score.prosody = _clamp(78.0)
            elif f0cv > 0.30:
                score.prosody = _clamp(84.0)   # übertrieben wackelig
            else:
                score.prosody = _clamp(92.0 + 26.0 * min(f0cv / 0.12, 1.0))
        else:
            score.prosody = 60.0                 # keine Stimme erkannt
            # Englisch: ohne German-Score gibt es keine no_voiced_speech-
            # Flag. Wenn gar keine F0 erkannt wird UND mehr als 0.5s lang
            # UND nicht bereits über silence erfasst → low_voiced_content.
            if m["duration_s"] >= 0.5 and "silence" not in issues:
                issues.append("low_voiced_content")
        score.audio_integrity = _clamp(integ)
        score.prosody = _clamp(score.prosody - pause_pen * 0.6)

        # ---- Konsistenz (Lautheit/Tonlage vs. Projekt) ----------------------
        cons = 100.0
        if self.project_lufs:
            median_lufs = float(np.median(self.project_lufs))
            dev = abs(m["lufs"] - median_lufs)
            if dev > 6.0:
                cons -= min(45.0, (dev - 6.0) * 7.0)
                issues.append("too_loud" if m["lufs"] > median_lufs else "too_quiet")
            else:
                cons -= dev * 2.0
        if self.project_f0:
            median_f0 = float(np.median(self.project_f0))
            if median_f0 > 0 and m.get("f0_median_hz", 0) > 0:
                f0dev = abs(m["f0_median_hz"] - median_f0) / median_f0
                cons -= min(35.0, max(0.0, f0dev - 0.06) * 200.0)
        score.consistency = _clamp(cons)

        # ---- Natürlichkeit (Kombination, Anforderung 43) --------------------
        nat = (0.45 * score.prosody + 0.25 * score.audio_integrity +
               0.20 * score.pronunciation_plausibility + 0.10 * score.consistency)
        if "mechanical_rhythm" in issues:
            nat -= 8.0
        score.naturalness = _clamp(nat)

        weights = {"naturalness": 0.30, "pronunciation": 0.15, "prosody": 0.25,
                   "consistency": 0.15, "audio_integrity": 0.15}
        score.overall = _clamp(
            weights["naturalness"] * score.naturalness +
            weights["pronunciation"] * score.pronunciation_plausibility +
            weights["prosody"] * score.prosody +
            weights["consistency"] * score.consistency +
            weights["audio_integrity"] * score.audio_integrity)

        score.issues = issues
        return score, m

    # ------------------------------------------------------------------
    @staticmethod
    def describe_issues(issues: list[str]) -> list[str]:
        return [ISSUE_LABELS.get(i, i) for i in issues]


def log_segment_quality(idx: int, score: QualityScore, metrics: dict,
                        attempt: int = 1) -> None:
    g = score.german or {}
    qlog(f"SEG {idx:04d} attempt {attempt} | overall {score.overall:.1f} | "
         f"nat {score.naturalness:.0f} pro {score.prosody:.0f} "
         f"pron {score.pronunciation_plausibility:.0f} "
         f"cons {score.consistency:.0f} int {score.audio_integrity:.0f} | "
         f"DE={g.get('overall', '-')} "
         f"(pron {g.get('pronunciation','-')}/mel {g.get('prosody_de','-')}/"
         f"rhy {g.get('rhythm','-')}) | "
         f"issues={','.join(score.issues) or 'none'} | "
         f"dur={metrics.get('duration_s')}s f0={metrics.get('f0_median_hz')}Hz "
         f"lufs={metrics.get('lufs')}")
