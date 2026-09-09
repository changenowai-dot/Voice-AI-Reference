"""EBU R128 / ITU-R BS.1770 Lautheitsmessung in numpy/scipy (float32,
speicherschonend).

Für Quality-Control, Fallback-Mastering und Report-Werte. K-Filterung
(Shelf + RLB-Highpass, 48-kHz-Koeffizienten aus BS.1770-4) mit Gating
(absolut -70 LUFS, relativ -10 LU). True Peak via 4x-Oversampling.
"""
from __future__ import annotations

import numpy as np

from .io import resample

_SR = 48000
# BS.1770-4, 48 kHz
_SHELF_B = np.array([1.53512485958697, -2.69169618940638, 1.19839281085285],
                    dtype=np.float64)
_SHELF_A = np.array([1.0, -1.69065929318241, 0.73248077421585],
                    dtype=np.float64)
_HPF_B = np.array([1.0, -2.0, 1.0], dtype=np.float64)
_HPF_A = np.array([1.0, -1.99004745483398, 0.99007225036621], dtype=np.float64)


def k_weight(data: np.ndarray, sr: int) -> np.ndarray:
    """K-gewichtetes Signal (float32, blockweise gefiltert)."""
    data = np.asarray(data, dtype=np.float32)
    if sr != _SR:
        data = resample(data, sr, _SR)
    try:
        from scipy.signal import lfilter
        y = lfilter(_SHELF_B, _SHELF_A, data).astype(np.float32, copy=False)
        y = lfilter(_HPF_B, _HPF_A, y).astype(np.float32, copy=False)
        return y
    except Exception:                                # pragma: no cover
        return _k_weight_python(data)


def _k_weight_python(x: np.ndarray) -> np.ndarray:    # pragma: no cover
    y = np.empty_like(x)
    x1 = x2 = 0.0
    y1 = y2 = 0.0
    b0, b1, b2 = _SHELF_B
    a1, a2 = _SHELF_A[1], _SHELF_A[2]
    for i in range(x.size):
        xn = float(x[i])
        yn = b0 * xn + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, xn
        y2, y1 = y1, yn
        y[i] = yn
    z = np.empty_like(y)
    x1 = x2 = y1 = y2 = 0.0
    b0, b1, b2 = _HPF_B
    a1, a2 = _HPF_A[1], _HPF_A[2]
    for i in range(y.size):
        xn = float(y[i])
        zn = b0 * xn + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, xn
        y2, y1 = y1, zn
        z[i] = zn
    return z


def integrated_lufs(data: np.ndarray, sr: int) -> float:
    """Integrierte Programmlautheit (LUFS), mono."""
    data = np.asarray(data, dtype=np.float32)
    if data.size < sr // 10:
        return -70.0
    y = k_weight(data, sr)
    block = int(0.4 * _SR)
    hop = int(0.1 * _SR)
    n_blocks = max((len(y) - block) // hop + 1, 1)
    # Blockleistungen ohne zusätzliche Kopien (Views)
    powers = np.empty(n_blocks, dtype=np.float64)
    for i in range(n_blocks):
        seg = y[i * hop: i * hop + block]
        if seg.size < block:
            break
        d = seg.astype(np.float64, copy=False)
        powers[i] = float(np.dot(d, d) / block)
    z = powers[: i + 1] if i < n_blocks else powers
    if z.size == 0:
        return -70.0
    lufs_blocks = -0.691 + 10.0 * np.log10(np.maximum(z, 1e-12))
    keep = lufs_blocks > -70.0
    if not keep.any():
        return -70.0
    rel_threshold = 10.0 * np.log10(np.mean(z[keep])) - 0.691 - 10.0
    keep2 = keep & (lufs_blocks > rel_threshold)
    if not keep2.any():
        keep2 = keep
    return round(float(-0.691 + 10.0 * np.log10(np.mean(z[keep2]))), 2)


def shortterm_lufs_series(data: np.ndarray, sr: int,
                          window_s: float = 3.0) -> np.ndarray:
    """Kurzzeit-Lautheiten (3 s Fenster, 1 s Schritt)."""
    y = k_weight(np.asarray(data, dtype=np.float32), sr)
    win = int(window_s * _SR)
    hop = int(1.0 * _SR)
    vals = []
    for start in range(0, max(len(y) - win + 1, 1), hop):
        seg = y[start:start + win]
        if seg.size < win // 2:
            break
        vals.append(-0.691 + 10.0 * np.log10(
            max(float(np.mean(seg.astype(np.float64) ** 2)), 1e-12)))
    return np.array(vals, dtype=np.float32)


def true_peak_dbtp(data: np.ndarray, sr: int) -> float:
    """True-Peak-Näherung mittels 4x-Oversampling."""
    x = np.asarray(data, dtype=np.float32)
    if sr != _SR:
        x = resample(x, sr, _SR)
    try:
        from scipy.signal import resample_poly
        up = resample_poly(x, 4, 1)
    except Exception:                                # pragma: no cover
        up = x
    peak = float(np.max(np.abs(up))) if up.size else 0.0
    del up
    if peak <= 0:
        return -99.0
    return round(20.0 * np.log10(peak), 2)


def rms_db(data: np.ndarray) -> float:
    data = np.asarray(data, dtype=np.float32)
    if data.size == 0:
        return -99.0
    m = float(np.dot(data, data) / data.size)
    return round(10.0 * np.log10(max(m, 1e-12)), 2)
