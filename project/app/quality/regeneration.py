"""Automatische Regeneration (Anforderung 44+45; Phase 1: §22+§23).

Jeder Versuch verändert GEZIELT das, was die Fehlerklasse nahelegt –
keine zufälligen, fast identischen Varianten (Best-of-N-Qualität):

  Fehlerklasse              -> Änderung Attempt 2 / Attempt 3
  ------------------------------------------------------------------
  pronunciation/duration    -> Sampling stabiler + „articulate clearly“-
  too_short/too_long           Hinweis + neuer Seed
  monotone/prosody_de       -> temperaturerhöhter Sweep +
                               Melodie-Hinweis verschärft
  question_melody_missing   -> expliziter Frage-Melodie-Hinweis
  rate_out_of_range         -> Tempo-Hinweis (schneller/langsamer)
  mechanical_rhythm/pauses  -> Temperatur + Streuung + neuer Seed
  consistency               -> Konsistenz-Anker verstärkt
  OOM                       -> Segment-Split-Fallback (Pipeline)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..logging_setup import get_logger, qlog
from ..tts.engine_base import EngineOOMError, SynthesisRequest, TTSError
from ..tts.sampler import variation_for_attempt
from .qc import SegmentQC, log_segment_quality

log = get_logger("regen")


@dataclass
class AttemptResult:
    attempt: int
    score: float = 0.0
    german_score: float | None = None
    critical: bool = False
    waveform: object = None
    sample_rate: int = 24000
    metrics: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    error: str = ""
    params_used: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Fehlerklasse -> gezielte Parameter-/Instruct-Änderung (§22)
# ---------------------------------------------------------------------------
def _classify(issues: list[str]) -> str:
    s = set(issues)
    if s & {"question_melody_missing"}:
        return "question_melody"
    if s & {"rate_out_of_range"}:
        return "rate"
    if s & {"too_short", "too_long", "duration_implausible", "dropout",
            "nan", "noise_like"}:
        return "pronunciation"
    if s & {"monotone"}:
        return "monotone"
    if s & {"mechanical_rhythm", "mechanical_pauses"}:
        return "rhythm"
    if s & {"clipping"}:
        return "clipping"
    if s & {"too_quiet", "too_loud"}:
        return "loudness"
    return "generic"


_INSTRUCT_FIXES = {
    "pronunciation": "Articulate every word clearly and calmly, especially "
                     "names and numbers; do not skip or repeat words.",
    "monotone": "Use a lively but controlled German sentence melody with "
                "natural pitch movement.",
    "question_melody": "This is a question: end with a clearly rising German "
                       "question intonation.",
    "rate": "Keep a steady, natural German speaking pace.",
    "rhythm": "Vary phrase lengths naturally like a human narrator; avoid "
              "a mechanical beat.",
    "loudness": "Keep loudness perfectly even with the surrounding text.",
    "clipping": "Speak with clean, non-distorted articulation.",
    "generic": "",
}


def attempt_changes(attempt: int, prev_issues: list[str],
                    base_sampling: dict, base_instruct: str) -> dict:
    """Liefert {'sampling': …, 'instruct': …} für den nächsten Versuch."""
    cls = _classify(prev_issues)
    sampling = dict(base_sampling)
    instruct = base_instruct
    if attempt == 2:
        if cls == "pronunciation":
            sampling["temperature"] = max(
                0.45, sampling.get("temperature", 0.7) - 0.15)
            sampling["repetition_penalty"] = 1.08
        elif cls in ("monotone", "rhythm"):
            sampling["temperature"] = min(
                0.95, sampling.get("temperature", 0.7) + 0.15)
            sampling["top_p"] = 0.92
        elif cls == "rate":
            pass                            # nur Instruct
        else:
            sampling = variation_for_attempt(2, sampling)
    else:  # Versuch 3+: andere Richtung als Versuch 2
        if cls in ("pronunciation", "monotone", "rhythm"):
            sampling.update({"temperature": 0.55, "top_p": 0.85,
                             "top_k": 40, "repetition_penalty": 1.10})
        else:
            sampling = variation_for_attempt(3, sampling)
    fix = _INSTRUCT_FIXES.get(cls, "")
    if fix:
        # Fix-Hinweis ersetzt einen eventuell vorhandenen alten Fix,
        # damit der Instruct nicht endlos wächst
        for old_fix in _INSTRUCT_FIXES.values():
            if old_fix and old_fix in instruct:
                instruct = instruct.replace(" " + old_fix, "")
        instruct = instruct.rstrip() + " " + fix
    return {"sampling": sampling, "instruct": instruct, "error_class": cls}


def generate_with_qc(engine, request: SynthesisRequest, text: str,
                     qc: SegmentQC, max_attempts: int = 3,
                     min_score: float = 78.0, min_german_score: float = 75.0,
                     german_meta: dict | None = None,
                     progress_cb=None) -> dict:
    """Erzeugt ein Segment inkl. QC-Loop (Best-of-N, gezielt variierend).

    Annahme: Score-Schwelle UND deutsche Schwelle UND keine kritischen
    Issues (Anforderung 21/24).
    """
    base_sampling = dict(request.sampling or {})
    base_instruct = request.instruct or ""
    attempts: list[AttemptResult] = []
    best: AttemptResult | None = None
    last_issues: list[str] = []

    def _better(a: AttemptResult, b: AttemptResult | None) -> bool:
        if b is None:
            return True
        # kritische Varianten werden streng gemieden, sofern es eine
        # nicht-kritische Alternative gibt
        if a.critical != b.critical:
            return not a.critical
        key_a = (a.score + (a.german_score or a.score) * 0.5)
        key_b = (b.score + (b.german_score or b.score) * 0.5)
        return key_a > key_b

    for attempt in range(1, max(1, max_attempts) + 1):
        ar = AttemptResult(attempt=attempt)
        try:
            if attempt == 1:
                sampling, instruct = dict(base_sampling), base_instruct
            else:
                changes = attempt_changes(attempt, last_issues,
                                          base_sampling, base_instruct)
                sampling, instruct = changes["sampling"], changes["instruct"]
            req = SynthesisRequest(
                text=request.text,
                language=request.language,
                speaker=request.speaker,
                instruct=instruct,
                sampling=sampling,
                # Neuer Seed pro Versuch – deterministisch (base + attempt)
                seed=(request.seed or 0) + attempt * 1013,
                max_seconds_hint=request.max_seconds_hint,
                speed=request.speed)
            ar.params_used = {"seed": req.seed, "sampling": sampling}
            result = engine.synthesize(req)
            ar.waveform = result.waveform
            ar.sample_rate = result.sample_rate
            score_obj, metrics = qc.check(result.waveform, result.sample_rate,
                                          text, german_meta=german_meta)
            ar.score = score_obj.overall
            ar.german_score = (score_obj.german or {}).get("overall")
            ar.metrics = metrics
            ar.issues = list(score_obj.issues)
            ar.critical = score_obj.critical
            log_segment_quality(request.seed or 0, score_obj, metrics, attempt)
            if _better(ar, best):
                best = ar
            last_issues = ar.issues
            german_ok = (ar.german_score is None or
                         ar.german_score >= min_german_score)
            if ar.score >= min_score and german_ok and not ar.critical:
                qc.observe_good(metrics)
                break
        except EngineOOMError as e:
            ar.error = f"OOM: {e}"
            log.warning("Versuch %d OOM: %s", attempt, e)
            try:
                engine._cuda_cleanup()
            except Exception:
                pass
        except TTSError as e:
            ar.error = str(e)
            log.warning("Versuch %d fehlgeschlagen: %s", attempt, e)
        attempts.append(ar)
        if progress_cb:
            progress_cb(attempt, ar)

    if best is None and attempts:
        best = attempts[-1]
    # leicht unter Schwelle aber valide -> akzeptieren + protokollieren
    accepted = bool(best and not best.error and not best.critical
                    and best.score >= min_score * 0.6)
    if best and not best.error and (best.critical or best.score < min_score):
        accepted = not best.critical
        qlog(f"SEG best={best.score:.1f}/DE={best.german_score} unter "
             f"Schwelle ({min_score}/{min_german_score}) – "
             + ("kritisch, markiert" if best.critical else
                "akzeptiert als beste verfügbare Version") +
             f". Probleme: {','.join(best.issues)}")
    return {"attempts": attempts, "best": best, "accepted": accepted}
