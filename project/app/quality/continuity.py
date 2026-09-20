"""Inter-segment continuity tracking for long-form narration.

Tracks rolling F0 median, LUFS and RMS over accepted segments and
flags a segment when its characteristics drift outside a tolerable
envelope from the running baseline. This catches the common long-form
failure where speaker identity / loudness / pitch slowly drifts (or
suddenly jumps) across segment boundaries even though per-segment QC
passes each one individually.

This is a SOFT gate: it never rejects a segment outright, but it
bumps the retry priority and tags diagnostics. Hard rejection is left
to final_gate with a tightened threshold when drift persists.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np


@dataclass
class ContinuityState:
    # Running median over the last N accepted segments.
    window: int = 6
    f0_history: deque = field(default_factory=lambda: deque(maxlen=8))
    lufs_history: deque = field(default_factory=lambda: deque(maxlen=8))
    rms_history: deque = field(default_factory=lambda: deque(maxlen=8))

    # Allowable relative deviation from rolling median.
    f0_rel_tol: float = 0.22      # ±22 % F0 (≈ 3.5 semitones)
    lufs_abs_tol: float = 3.5     # ±3.5 LU
    rms_rel_tol: float = 0.40     # ±40 % RMS

    # Soft drift score in [0..100]; higher = more suspicious.
    last_drift_score: float = 0.0
    last_flags: list[str] = field(default_factory=list)

    def observe(self, metrics: dict) -> None:
        """Record an accepted segment's metrics for future comparison."""
        f0 = metrics.get("f0_median_hz")
        if f0 and f0 > 50:
            self.f0_history.append(float(f0))
        lufs = metrics.get("lufs")
        if lufs is not None and lufs > -60:
            self.lufs_history.append(float(lufs))
        rms = metrics.get("rms")
        if rms is not None and rms > 0:
            self.rms_history.append(float(rms))

    def _median(self, dq: deque) -> float | None:
        if not dq:
            return None
        return float(np.median(list(dq)))

    def score(self, metrics: dict) -> tuple[float, list[str]]:
        """Score a candidate segment; returns (drift_score 0..100, flags)."""
        flags: list[str] = []
        penalties: list[float] = []

        f0 = metrics.get("f0_median_hz") or 0.0
        lufs = metrics.get("lufs")
        rms = metrics.get("rms")

        m_f0 = self._median(self.f0_history)
        if m_f0 and f0 > 50:
            rel = abs(f0 - m_f0) / m_f0
            if rel > self.f0_rel_tol:
                penalties.append(min(60.0, (rel - self.f0_rel_tol) * 250.0))
                flags.append(f"f0_drift:{rel:.0%}")
        m_lufs = self._median(self.lufs_history)
        if m_lufs is not None and lufs is not None and lufs > -60:
            ad = abs(lufs - m_lufs)
            if ad > self.lufs_abs_tol:
                penalties.append(min(45.0, (ad - self.lufs_abs_tol) * 12.0))
                flags.append(f"lufs_drift:{ad:.1f}dB")
        m_rms = self._median(self.rms_history)
        if m_rms and rms and rms > 0:
            rel = abs(rms - m_rms) / m_rms
            if rel > self.rms_rel_tol:
                penalties.append(min(30.0, (rel - self.rms_rel_tol) * 80.0))
                flags.append(f"rms_drift:{rel:.0%}")
        score = float(min(100.0, sum(penalties)))
        self.last_drift_score = score
        self.last_flags = flags
        return score, flags


__all__ = ["ContinuityState"]
