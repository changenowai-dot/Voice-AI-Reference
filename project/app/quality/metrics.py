"""Audio-Metriken für Quality Control (Anforderung 42 + 43).

Rein signalbasierte Heuristiken (kein ASR, keine „Menschlichkeits-
Messung“ – siehe Anforderung 46: Vergleichsmaßstab, keine absolute
Wissenschaft). Alle Werte deterministisch und reproduzierbar.
"""
from __future__ import annotations

import numpy as np

from ..audio.ebu_r128 import integrated_lufs, true_peak_dbtp

SILENCE_THRESH = 0.004      # ~ -48 dBFS
FRAME_MS = 40


def _frames(x: np.ndarray, sr: int, frame_ms: int = FRAME_MS):
    n = max(1, int(sr * frame_ms / 1000.0))
    for start in range(0, max(len(x) - n + 1, 1), n):
        yield x[start:start + n]


def basic_stats(wav: np.ndarray, sr: int) -> dict:
    x = np.asarray(wav, dtype=np.float64)
    dur = len(x) / sr
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    clip_ratio = float(np.mean(np.abs(x) >= 0.995))
    dc = float(np.mean(x))
    has_nan = bool(np.any(~np.isfinite(x)))
    rms = float(np.sqrt(np.mean(x ** 2))) if x.size else 0.0
    return {
        "duration_s": round(dur, 3),
        "peak": round(peak, 4),
        "clip_ratio": round(clip_ratio, 6),
        "dc_offset": round(dc, 5),
        "rms": round(rms, 5),
        "has_nan": has_nan,
    }


def silence_stats(wav: np.ndarray, sr: int) -> dict:
    x = np.asarray(wav, dtype=np.float64)
    n = len(x)
    loud = np.abs(x) > SILENCE_THRESH
    # Randstille
    lead = 0
    while lead < n and not loud[lead]:
        lead += 1
    trail = 0
    while trail < n and not loud[n - 1 - trail]:
        trail += 1
    # interne Pausen (Serie von stillen Frames >= 250 ms)
    frame = max(1, int(sr * 0.05))
    n_frames = n // frame
    if n_frames:
        frames_loud = loud[:n_frames * frame].reshape(n_frames, frame).mean(axis=1) > 0.02
        pauses: list[float] = []
        run = 0
        for f in frames_loud:
            if not f:
                run += 1
            else:
                if run * 0.05 >= 0.25:
                    pauses.append(round(run * 0.05, 3))
                run = 0
        if run * 0.05 >= 0.25:
            pauses.append(round(run * 0.05, 3))
    else:
        pauses = []
    internal = [p for p in pauses]
    silence_ratio = float(1.0 - np.mean(loud)) if n else 0.0
    return {
        "leading_ms": round(lead / sr * 1000, 1),
        "trailing_ms": round(trail / sr * 1000, 1),
        "internal_pauses": internal,
        "longest_internal_pause_s": round(max(internal), 3) if internal else 0.0,
        "internal_pause_count": len(internal),
        "silence_ratio": round(silence_ratio, 4),
    }


def _autocorr_f0(frame: np.ndarray, sr: int, fmin=70.0, fmax=400.0) -> float:
    """Einfache, robuste F0-Schätzung via Autokorrelation."""
    x = frame - frame.mean()
    if np.sqrt(np.mean(x * x)) < 0.008:
        return 0.0
    corr = np.correlate(x, x, "full")[len(x) - 1:]
    if corr[0] <= 0:
        return 0.0
    lag_min = int(sr / fmax)
    lag_max = min(int(sr / fmin), len(corr) - 1)
    if lag_max <= lag_min:
        return 0.0
    seg = corr[lag_min:lag_max + 1]
    peak_idx = int(np.argmax(seg)) + lag_min
    if corr[peak_idx] < 0.35 * corr[0]:
        return 0.0
    return sr / peak_idx


def prosody_stats(wav: np.ndarray, sr: int) -> dict:
    """Prosodie-Proxys: F0-Verlauf, ZCR-Variation, Spektralschwerpunkt."""
    x = np.asarray(wav, dtype=np.float64)
    f0s: list[float] = []
    cents: list[float] = []
    for fr in _frames(x, sr):
        f0 = _autocorr_f0(fr, sr)
        f0s.append(f0)
        if fr.size:
            spec = np.abs(np.fft.rfft(fr * np.hanning(fr.size)))
            if spec.sum() > 1e-9:
                freqs = np.fft.rfftfreq(fr.size, 1.0 / sr)
                cents.append(float(np.sum(freqs * spec) / np.sum(spec)))
    voiced = [f for f in f0s if f > 0]
    if len(voiced) >= 3:
        v = np.array(voiced)
        v = v[(v >= 70) & (v <= 400)]
        f0_med = float(np.median(v)) if v.size else 0.0
        f0_std = float(np.std(v)) if v.size else 0.0
        f0_cv = float(f0_std / f0_med) if f0_med > 0 else 0.0
    else:
        f0_med, f0_std, f0_cv = 0.0, 0.0, 0.0
    if cents:
        c = np.array(cents)
        cent_mean, cent_std = float(np.mean(c)), float(np.std(c))
    else:
        cent_mean, cent_std = 0.0, 0.0
    # ZCR-Variation (Rhythmus)
    signs = np.sign(x)
    zc = np.where(np.diff(signs) != 0)[0]
    zcr_rate = len(zc) / max(len(x) / sr, 1e-6)
    return {
        "f0_median_hz": round(f0_med, 1),
        "f0_std_hz": round(f0_std, 2),
        "f0_cv": round(f0_cv, 4),                      # Intonationsbreite
        "spectral_centroid_mean": round(cent_mean, 1),
        "spectral_centroid_std": round(cent_std, 1),
        "zcr_per_s": round(zcr_rate, 1),
        "voiced_ratio": round(len(voiced) / max(len(f0s), 1), 3),
    }


def spectral_flatness(wav: np.ndarray, sr: int) -> float:
    """Spektrale Flachheit (0=tonal, 1=rauschend) – Artefakt-Indikator."""
    x = np.asarray(wav, dtype=np.float64)
    flats = []
    for fr in _frames(x, sr):
        if fr.size < 64:
            continue
        spec = np.abs(np.fft.rfft(fr * np.hanning(fr.size))) + 1e-12
        gm = float(np.exp(np.mean(np.log(spec))))
        am = float(np.mean(spec))
        if am > 1e-9:
            flats.append(gm / am)
    return round(float(np.mean(flats)), 4) if flats else 0.0


def dropouts(wav: np.ndarray, sr: int) -> int:
    """Anzahl auffälliger digitaler Aussetzer (exakte Null-Serien >= 60 ms)."""
    x = np.asarray(wav, dtype=np.float64)
    zeros = np.abs(x) < 1e-6
    run_min = int(0.06 * sr)
    count = 0
    run = 0
    for z in zeros:
        if z:
            run += 1
        else:
            if run >= run_min:
                count += 1
            run = 0
    if run >= run_min:
        count += 1
    return count


def analyze_segment_audio(wav: np.ndarray, sr: int) -> dict:
    out = basic_stats(wav, sr)
    out.update(silence_stats(wav, sr))
    out.update(prosody_stats(wav, sr))
    out["spectral_flatness"] = spectral_flatness(wav, sr)
    out["dropout_count"] = dropouts(wav, sr)
    out["lufs"] = integrated_lufs(wav, sr)
    out["true_peak_dbtp"] = true_peak_dbtp(wav, sr)
    return out
