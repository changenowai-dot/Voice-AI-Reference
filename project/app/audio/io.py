"""Audio-I/O: WAV lesen/schreiben (float32/PCM16/PCM24)."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

try:
    import soundfile as sf
    _HAS_SF = True
except Exception:                                   # pragma: no cover
    _HAS_SF = False


def read_wav(path: Path | str) -> tuple[np.ndarray, int]:
    """Liest WAV als float32 mono (Stereo wird gemittelt)."""
    path = str(path)
    if _HAS_SF:
        data, sr = sf.read(path, dtype="float32", always_2d=False)
        arr = np.asarray(data, dtype=np.float32)
        if arr.ndim == 2:
            arr = arr.mean(axis=1)
        return arr, int(sr)
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        nch = w.getnchannels()
        sw = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if sw == 2:
        arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 4:
        arr = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    elif sw == 1:
        arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"Nicht unterstützte Wortbreite: {sw*8} bit")
    if nch > 1:
        arr = arr.reshape(-1, nch).mean(axis=1)
    return arr.astype(np.float32), int(sr)


def write_wav(path: Path | str, data: np.ndarray, sample_rate: int,
              bit_depth: int = 16) -> None:
    """Schreibt WAV; 24/32 Bit via soundfile, sonst stdlib (16 bit)."""
    path = str(path)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(data, dtype=np.float32).reshape(-1)
    if _HAS_SF:
        subtype = {16: "PCM_16", 24: "PCM_24", 32: "FLOAT"}.get(bit_depth, "PCM_24")
        sf.write(path, arr, sample_rate, subtype=subtype)
        return
    if bit_depth not in (16,):
        # stdlib-Fallback schreibt 16 bit
        pass
    pcm = np.clip(arr, -1.0, 1.0)
    ints = (pcm * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(ints.tobytes())


def resample(data: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """Hochwertiges Resampling (scipy polyphase, Fallback linear)."""
    if sr_in == sr_out or data.size == 0:
        return data
    try:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(sr_in, sr_out)
        return resample_poly(data, sr_out // g, sr_in // g).astype(np.float32)
    except Exception:                                # pragma: no cover
        n_out = int(len(data) * sr_out / sr_in)
        x = np.linspace(0, len(data) - 1, n_out)
        return np.interp(x, np.arange(len(data)), data).astype(np.float32)
