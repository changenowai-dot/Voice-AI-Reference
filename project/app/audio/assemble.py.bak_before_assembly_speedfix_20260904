"""Zusammenfügen der Segmente (Anforderung 40).

- Kantensilence der Segmente sauber kürzen (stapelt nicht mit Pausen)
- Lautheits-Voranpassung der Segmente an den Projektmedian (sanft, ±3 dB)
- kontextabhängige Pausen (app.prosody.pauses) einfügen
- Anti-Click-Randfades
Die natürliche Prosodie innerhalb der Segmente bleibt unangetastet.
"""
from __future__ import annotations

import numpy as np

from ..logging_setup import get_logger
from ..segmentation import Segment
from .ebu_r128 import integrated_lufs

log = get_logger("audio.assemble")

_EDGE_THRESH = 0.0015      # ~ -56 dBFS
_KEEP_HEAD_S = 0.06
_KEEP_TAIL_S = 0.10


def trim_edges(wav: np.ndarray, sr: int) -> np.ndarray:
    """Entfernt Stille am Anfang/Ende, behält kleine natürliche Ränder."""
    abs_w = np.abs(wav)
    n = len(wav)
    keep_head = int(_KEEP_HEAD_S * sr)
    keep_tail = int(_KEEP_TAIL_S * sr)
    idx = np.where(abs_w > _EDGE_THRESH)[0]
    if idx.size == 0:
        return wav
    start = max(0, int(idx[0]) - keep_head)
    end = min(n, int(idx[-1]) + keep_tail)
    return wav[start:end]


def _fade_edges(wav: np.ndarray, sr: int, ms: float = 6.0) -> np.ndarray:
    k = max(1, int(sr * ms / 1000.0))
    if len(wav) <= 2 * k:
        return wav
    ramp = np.linspace(0.0, 1.0, k, dtype=np.float32)
    out = wav.copy()
    out[:k] *= ramp
    out[-k:] *= ramp[::-1]
    return out


def loudness_match(wav: np.ndarray, sr: int, target_lufs: float,
                   max_gain_db: float = 3.0) -> np.ndarray:
    """Gleicht Segment-Lautheit sanft an Ziel-LUFS an (Konsistenz, Anf. 17)."""
    cur = integrated_lufs(wav, sr)
    return _match_to_lufs(wav, cur, target_lufs, max_gain_db)


def _match_to_lufs(wav: np.ndarray, current_lufs: float, target_lufs: float,
                   max_gain_db: float = 3.0) -> np.ndarray:
    if current_lufs <= -69.0:
        return wav
    gain_db = float(np.clip(target_lufs - current_lufs, -max_gain_db, max_gain_db))
    if abs(gain_db) < 0.25:
        return wav
    wav = wav * (10.0 ** (gain_db / 20.0))
    peak = float(np.max(np.abs(wav)))
    if peak > 0.985:
        wav = wav * (0.985 / peak)
    return wav.astype(np.float32)


def assemble(segments_audio: list[tuple[np.ndarray, int, Segment]],
             project_median_lufs: float | None = None,
             precomputed_lufs: list[float] | None = None) -> tuple[np.ndarray, int]:
    """Fügt [(wav, sr, segment)] zum Gesamt audio zusammen.

    project_median_lufs: Ziel für die Voranpassung (Median der Segment-
    LUFS-Werte). None = keine Anpassung. precomputed_lufs vermeidet
    doppelte Messung (Pipeline misst ohnehin).
    """
    if not segments_audio:
        raise ValueError("Keine Segmente zum Zusammenfügen")
    sr_out = segments_audio[0][1]
    processed: list[np.ndarray] = []
    for i, (wav, sr, seg) in enumerate(segments_audio):
        if sr != sr_out:
            from .io import resample
            wav = resample(wav, sr, sr_out)
        wav = trim_edges(np.asarray(wav, dtype=np.float32).copy(), sr_out)
        if project_median_lufs is not None:
            if precomputed_lufs is not None and i < len(precomputed_lufs) \
                    and precomputed_lufs[i] > -69:
                lufs_i = precomputed_lufs[i]
            else:
                lufs_i = integrated_lufs(wav, sr_out)
            wav = _match_to_lufs(wav, lufs_i, project_median_lufs)
        processed.append(_fade_edges(wav, sr_out))

    parts: list[np.ndarray] = []
    total = 0
    for i, wav in enumerate(processed):
        parts.append(wav)
        total += len(wav)
        seg = segments_audio[i][2]
        silence_s = seg.pause_after_s if seg.pause_after_s else 0.4
        ns = int(silence_s * sr_out)
        parts.append(np.zeros(ns, dtype=np.float32))
        total += ns
    out = np.concatenate(parts) if len(parts) > 1 else parts[0]
    log.info("Zusammenfügen: %d Segmente, %.1f s",
             len(processed), len(out) / sr_out)
    return out.astype(np.float32), sr_out


def apply_speed(wav: np.ndarray, sr: int, speed: float) -> tuple[np.ndarray, int]:
    """Tempo-Änderung 0.8–1.2, pitch-erhaltend (ffmpeg atempo);
    Fallback: lineare Interpolation (leichte Tonhöhenänderung)."""
    if abs(speed - 1.0) < 0.02:
        return wav, sr
    from pathlib import Path
    import tempfile
    from . import ffmpeg as ff
    from .io import read_wav, write_wav
    if ff.ffmpeg_available():
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.wav"
            dst = Path(td) / "out.wav"
            write_wav(src, wav, sr, bit_depth=32)
            ok, err = ff.run_ffmpeg([
                "-y", "-i", str(src), "-filter:a",
                f"atempo={speed:.3f}", "-ar", str(sr),
                "-c:a", "pcm_f32le", str(dst),
            ])
            if ok and dst.exists():
                out, sr2 = read_wav(dst)
                return out.astype(np.float32), sr2
    return _speed_fallback(wav, sr, speed)


def _speed_fallback(wav: np.ndarray, sr: int, speed: float) -> tuple[np.ndarray, int]:
    """Einfacher Fallback: lineare Interpolation (ändert die Tonhöhe leicht).
    Für 0.8–1.2 akzeptabel; ffmpeg-Pfad wird bevorzugt."""
    n_out = int(len(wav) / speed)
    x = np.linspace(0, len(wav) - 1, n_out)
    out = np.interp(x, np.arange(len(wav)), wav).astype(np.float32)
    return out, sr


# ===========================================================================
# Phase Desktop (§18/§35): Streaming-Assembly direkt in Datei –
# speicherbefreit für sehr lange Texte (120 min+). Segmente werden
# nacheinander geschrieben (inkl. Vorverarbeitung + Pausen), das
# Mastering liest die Datei anschließend streaming (ffmpeg 2-Pass).
# ===========================================================================
def assemble_to_file(segments_audio, out_path, project_median_lufs=None,
                     precomputed_lufs=None, speed: float = 1.0,
                     bit_depth: int = 24) -> tuple:
    """Schreibt [(wav, sr, segment)] progressiv in eine WAV-Datei.

    Rückgabe: (sr, total_seconds, pause_total_s)
    """
    if not segments_audio:
        raise ValueError("Keine Segmente zum Zusammenfügen")
    import numpy as np
    from .io import write_wav, resample as _resample

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sr_out = segments_audio[0][1]

    # Vorverarbeitung (identisch zum In-Memory-Pfad)
    processed = []
    for i, (wav, sr, seg) in enumerate(segments_audio):
        if sr != sr_out:
            wav = _resample(np.asarray(wav, dtype=np.float32), sr, sr_out)
        wav = trim_edges(np.asarray(wav, dtype=np.float32).copy(), sr_out)
        if project_median_lufs is not None:
            if precomputed_lufs is not None and i < len(precomputed_lufs) \
                    and precomputed_lufs[i] > -69:
                lufs_i = precomputed_lufs[i]
            else:
                lufs_i = integrated_lufs(wav, sr_out)
            wav = _match_to_lufs(wav, lufs_i, project_median_lufs)
        processed.append(_fade_edges(wav, sr_out))

    # progressives Schreiben (16/24 Bit via soundfile-Blockwriter, sonst 16)
    total = 0
    pause_total = 0.0
    speed = max(0.5, float(speed or 1.0))
    try:
        import soundfile as sf
        subtype = {16: "PCM_16", 24: "PCM_24", 32: "FLOAT"}.get(
            bit_depth, "PCM_24")
        with sf.SoundFile(str(out_path), mode="w", samplerate=sr_out,
                          channels=1, subtype=subtype) as f:
            for i, wav in enumerate(processed):
                if abs(speed - 1.0) >= 0.02:
                    wav, _ = apply_speed(wav, sr_out, speed)
                f.write(wav)
                total += len(wav)
                seg = segments_audio[i][2]
                silence_s = (seg.pause_after_s or 0.4) / speed
                pause_total += silence_s
                ns = int(silence_s * sr_out)
                if ns > 0:
                    f.write(np.zeros(ns, dtype=np.float32))
                    total += ns
                processed[i] = None          # Speicher freigeben
    except ImportError:
        # stdlib-Fallback: 16 Bit blockweise
        import wave as _wave
        with _wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr_out)
            for i, wav in enumerate(processed):
                if abs(speed - 1.0) >= 0.02:
                    wav, _ = apply_speed(wav, sr_out, speed)
                pcm = (np.clip(wav, -1.0, 1.0) * 32767.0).astype("<i2")
                w.writeframes(pcm.tobytes())
                total += len(wav)
                seg = segments_audio[i][2]
                silence_s = (seg.pause_after_s or 0.4) / speed
                pause_total += silence_s
                ns = int(silence_s * sr_out)
                if ns > 0:
                    w.writeframes((np.zeros(ns, dtype=np.float32) * 32767)
                                  .astype("<i2").tobytes())
                    total += ns
                processed[i] = None
    log.info("Streaming-Assembly: %d Segmente -> %s (%.1f s)",
             len(segments_audio), out_path, total / sr_out)
    return sr_out, total / sr_out, pause_total


from pathlib import Path  # noqa: E402
