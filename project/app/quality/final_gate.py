"""Final-QC-Gate (§4, finale Änderung des Produktionsauftrags).

Ein kritisches „best“-Ergebnis der Regeneration darf NICHT einfach in
Cache oder Endaudio übernommen werden: Vor der endgültigen Übernahme
erfolgt eine UNABHÄNGIGE erneute QC-Prüfung. Auch ein Split-Fallback
wird vor der Übernahme erneut QC-geprüft.

Das Gate ergänzt die vorhandene QC-Schicht (wird nicht ersetzt).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..logging_setup import get_logger, qlog
from .qc import SegmentQC

log = get_logger("finalgate")


@dataclass
class GateResult:
    passed: bool
    score: float
    german_score: float | None
    critical: bool
    issues: list = field(default_factory=list)
    reason: str = ""


def final_qc_gate(wav, sr: int, text: str, qc: SegmentQC,
                  context: str = "segment",
                  german_meta: dict | None = None,
                  min_score: float = 60.0) -> GateResult:
    """Unabhängige Nachprüfung vor Cache-/Audio-Übernahme (§4, §23).

    Kriterien (bewusst streng gegenüber Integritätsfehlern):
    - harte Integrität: clipping/dropout/nan/noise_like/silence
    - kritische German-Score-Marker (duration_implausible,
      no_voiced_speech, rate_out_of_range)
    - Mindest-Gesamtscore (Default 60 – endgültig „schlecht, aber
      nutzbar“ bleibt der Regenerations-Entscheidung überlassen)
    """
    score_obj, metrics = qc.check(wav, sr, text, german_meta=german_meta)
    critical = score_obj.critical
    hard = {"clipping", "dropout", "nan", "noise_like", "silence"}
    integrity_bad = bool(hard & set(score_obj.issues))
    passed = (not integrity_bad
              and not critical
              and score_obj.overall >= min_score)
    reason = ""
    if integrity_bad:
        reason = (f"Integritätsfehler beim Final-Gate ({context}): "
                  f"{sorted(hard & set(score_obj.issues))}")
    elif critical:
        reason = (f"kritisches QC-Ergebnis beim Final-Gate ({context}): "
                  f"{score_obj.issues}")
    elif score_obj.overall < min_score:
        reason = (f"Score {score_obj.overall:.1f} unter Final-Gate-"
                  f"Minimum {min_score} ({context})")
    if not passed:
        qlog(f"FINAL-GATE BLOCKIERT ({context}): {reason} | "
             f"score={score_obj.overall:.1f} issues={score_obj.issues}")
    else:
        qlog(f"FINAL-GATE OK ({context}): score={score_obj.overall:.1f}")
    german = (score_obj.german or {}).get("overall")
    return GateResult(passed=passed, score=round(score_obj.overall, 1),
                      german_score=german, critical=critical,
                      issues=list(score_obj.issues), reason=reason)
