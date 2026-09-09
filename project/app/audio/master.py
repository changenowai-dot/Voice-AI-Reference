"""Mastering (Anforderung 40 + 41): Lautheitsnormalisierung (EBU R128),
True-Peak-Limit, YouTube-Master, WAV + MP3 Ausgabe.

Pfad A (bevorzugt): ffmpeg 2-Pass loudnorm (exakt, branchenüblich)
Pfad B (Fallback ohne ffmpeg): eigene R128-Messung + Gain + Peak-Limiter
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..logging_setup import get_logger, plog
from . import ffmpeg as ff
from .ebu_r128 import integrated_lufs
from .ebu_r128 import true_peak_dbtp as _calc_tp
from .io import read_wav, resample, write_wav

log = get_logger("audio.master")


def master_to_youtube(wav: np.ndarray, sr: int, out_wav: Path, out_mp3: Path,
                      target_lufs: float = -14.0, true_peak_dbtp: float = -1.5,
                      wav_sample_rate: int = 48000, wav_bit_depth: int = 24,
                      mp3_bitrate: str = "320k",
                      volume_db: float = 0.0) -> dict:
    """Erzeugt WAV-Master + MP3-Endversion mit YouTube-tauglicher Loudness.

    volume_db: manuelle Pegelanpassung vor dem Mastering (Anforderung 27).
    """
    report: dict = {"ffmpeg": False, "lufs_in": None, "lufs_out": None,
                    "tp_out": None, "wav": str(out_wav), "mp3": str(out_mp3)}

    lufs_in = integrated_lufs(wav, sr)
    report["lufs_in"] = lufs_in

    if volume_db:
        wav = (wav * (10.0 ** (volume_db / 20.0))).astype(np.float32)

    out_wav = Path(out_wav)
    out_mp3 = Path(out_mp3)
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    if ff.ffmpeg_available():
        ok, info = _master_ffmpeg(wav, sr, out_wav, out_mp3, target_lufs,
                                  true_peak_dbtp, wav_sample_rate,
                                  wav_bit_depth, mp3_bitrate)
        if ok:
            report["ffmpeg"] = True
            # Streaming-Messung des Ergebnisses (speicherschonend)
            report["lufs_out"] = _measure_file_lufs(out_wav)
            report["tp_out"] = _measure_file_truepeak(out_wav)
            plog(f"MASTER ffmpeg ok: in={lufs_in} LUFS -> out={report['lufs_out']} LUFS, "
                 f"TP={report['tp_out']} dBTP")
            return report
        log.warning("ffmpeg-Mastering fehlgeschlagen (%s) – numpy-Fallback", info[:200])

    # ---------------- Fallback: numpy ------------------------------------
    wav48 = resample(wav, sr, wav_sample_rate)
    wav48 = _normalize_numpy(wav48, wav_sample_rate, target_lufs, true_peak_dbtp)
    write_wav(out_wav, wav48, wav_sample_rate, bit_depth=wav_bit_depth)
    report["lufs_out"] = integrated_lufs(wav48, wav_sample_rate)
    report["tp_out"] = _calc_tp(wav48, wav_sample_rate)
    if ff.ffmpeg_available():
        ok, err = ff.run_ffmpeg([
            "-y", "-i", str(out_wav), "-codec:a", "libmp3lame",
            "-b:a", mp3_bitrate, str(out_mp3)])
        if not ok:
            log.warning("MP3-Kodierung fehlgeschlagen: %s", err[:200])
    else:
        log.warning("Kein ffmpeg verfügbar – MP3 wurde NICHT erzeugt "
                    "(nur WAV-Master).")
    plog(f"MASTER numpy: in={lufs_in} -> out={report['lufs_out']} LUFS, "
         f"TP={report['tp_out']} dBTP")
    return report


def _master_ffmpeg(wav: np.ndarray, sr: int, out_wav: Path, out_mp3: Path,
                   target_lufs: float, tp: float, wav_sample_rate: int,
                   wav_bit_depth: int, mp3_bitrate: str) -> tuple[bool, str]:
    import json as _json
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "src.wav"
        write_wav(src, wav, sr, bit_depth=32)
        # Pass 1: messen
        ok, out = ff.run_ffmpeg([
            "-i", str(src), "-af",
            f"loudnorm=I={target_lufs}:TP={tp}:LRA=11:print_format=json",
            "-f", "null", "-"])
        if not ok:
            return False, out
        measured = {}
        try:
            json_start = out.rfind("{")
            measured = _json.loads(out[json_start:out.rfind("}") + 1])
        except Exception:
            measured = {}
        inp_i = measured.get("input_i", str(target_lufs))
        inp_tp = measured.get("input_tp", "-1.0")
        inp_lra = measured.get("input_lra", "11")
        inp_thr = measured.get("input_thresh", "-70")
        filt = (f"loudnorm=I={target_lufs}:TP={tp}:LRA=11:"
                f"measured_I={inp_i}:measured_TP={inp_tp}:"
                f"measured_LRA={inp_lra}:measured_thresh={inp_thr}:offset="
                f"{measured.get('target_offset', '0')}:linear=true")
        pcm = "pcm_s24le" if wav_bit_depth == 24 else (
            "pcm_s16le" if wav_bit_depth == 16 else "pcm_s32le")
        ok, out = ff.run_ffmpeg([
            "-y", "-i", str(src), "-af", filt,
            "-ar", str(wav_sample_rate), "-sample_fmt", "s32",
            "-c:a", pcm, str(out_wav)])
        if not ok:
            return False, out
        ok, out = ff.run_ffmpeg([
            "-y", "-i", str(out_wav), "-codec:a", "libmp3lame",
            "-b:a", mp3_bitrate, str(out_mp3)])
        if not ok:
            return False, out
    return True, "ok"


def _normalize_numpy(wav: np.ndarray, sr: int, target_lufs: float,
                     tp_dbtp: float) -> np.ndarray:
    cur = integrated_lufs(wav, sr)
    if cur > -69.0:
        gain = 10.0 ** ((target_lufs - cur) / 20.0)
        wav = wav * gain
    # True-Peak-Limiter (weich)
    tp_lin = 10.0 ** (tp_dbtp / 20.0)
    peak = float(np.max(np.abs(wav))) if wav.size else 0.0
    if peak > tp_lin:
        # sanfte Soft-Knee-Kompression nur im Übersteuerungsbereich
        ratio = 3.0
        over = np.abs(wav) > tp_lin
        excess = np.abs(wav[over]) - tp_lin
        compressed = tp_lin + excess / ratio
        sign = np.sign(wav[over])
        wav = wav.copy()
        wav[over] = sign * np.minimum(compressed, tp_lin * 1.02)
        peak2 = float(np.max(np.abs(wav)))
        if peak2 > tp_lin * 1.02:
            wav = wav * (tp_lin / peak2)
    return wav.astype(np.float32)


def _measure_file_lufs(path) -> float | None:
    """Misst integrierte LUFS einer Datei via ffmpeg ebur128 (streaming)."""
    ok, out = ff.run_ffmpeg(["-i", str(path), "-filter_complex",
                             "ebur128=peak=none", "-f", "null", "-"],
                            timeout_s=300)
    if not ok:
        return None
    import re as _re
    vals = _re.findall(r"I:\s+(-?\d+\.\d+)\s*LUFS", out)
    return round(float(vals[-1]), 2) if vals else None


def _measure_file_truepeak(path) -> float | None:
    """True Peak via ffmpeg (streaming)."""
    ok, out = ff.run_ffmpeg(["-i", str(path), "-filter_complex",
                             "ebur128=peak=true", "-f", "null", "-"],
                            timeout_s=300)
    if not ok:
        return None
    import re as _re
    vals = _re.findall(r"True frame peak:\s+Peak:\s*(-?\d+\.\d+)\s*dBFS", out)
    if not vals:
        vals = _re.findall(r"Peak:\s*(-?\d+\.\d+)\s*dBFS", out)
    return round(float(vals[-1]), 2) if vals else None


# ===========================================================================
# Datei-basiertes Mastering (§18): Quelle = WAV-Datei, Ausgabe WAV+MP3.
# ffmpeg loudnorm 2-Pass arbeitet streaming; numpy-Fallback misst/streibt
# in Blöcken (kein Voll-Array im RAM).
# ===========================================================================
def master_file_to_youtube(src_wav: Path, out_wav: Path, out_mp3: Path,
                           target_lufs: float = -14.0,
                           true_peak_dbtp: float = -1.5,
                           wav_sample_rate: int = 48000,
                           wav_bit_depth: int = 24,
                           mp3_bitrate: str = "320k") -> dict:
    report: dict = {"ffmpeg": False, "lufs_in": None, "lufs_out": None,
                    "tp_out": None, "wav": str(out_wav), "mp3": str(out_mp3)}
    src_wav, out_wav = Path(src_wav), Path(out_wav)
    if ff.ffmpeg_available():
        ok, info = _master_ffmpeg_file(src_wav, out_wav, out_mp3, target_lufs,
                                       true_peak_dbtp, wav_sample_rate,
                                       wav_bit_depth, mp3_bitrate)
        if ok:
            report["ffmpeg"] = True
            report["lufs_out"] = _measure_file_lufs(out_wav)
            report["tp_out"] = _measure_file_truepeak(out_wav)
            return report
        log.warning("ffmpeg-Datei-Mastering fehlgeschlagen (%s) – numpy",
                    info[:200])
    _master_numpy_file(src_wav, out_wav, out_mp3, target_lufs, true_peak_dbtp,
                       wav_sample_rate, wav_bit_depth, mp3_bitrate)
    report["lufs_out"] = _measure_file_lufs(out_wav)
    report["tp_out"] = _measure_file_truepeak(out_wav)
    return report


def _master_ffmpeg_file(src_wav: Path, out_wav: Path, out_mp3: Path,
                        target_lufs: float, tp: float, wav_sample_rate: int,
                        wav_bit_depth: int, mp3_bitrate: str):
    import json as _json
    ok, out = ff.run_ffmpeg([
        "-i", str(src_wav), "-af",
        f"loudnorm=I={target_lufs}:TP={tp}:LRA=11:print_format=json",
        "-f", "null", "-"], timeout_s=1800)
    if not ok:
        return False, out
    try:
        measured = _json.loads(out[out.rfind("{"):out.rfind("}") + 1])
    except Exception:
        measured = {}
    filt = (f"loudnorm=I={target_lufs}:TP={tp}:LRA=11:"
            f"measured_I={measured.get('input_i', target_lufs)}:"
            f"measured_TP={measured.get('input_tp', '-1.0')}:"
            f"measured_LRA={measured.get('input_lra', '11')}:"
            f"measured_thresh={measured.get('input_thresh', '-70')}:"
            f"offset={measured.get('target_offset', '0')}:linear=true")
    pcm = "pcm_s24le" if wav_bit_depth == 24 else (
        "pcm_s16le" if wav_bit_depth == 16 else "pcm_s32le")
    ok, out = ff.run_ffmpeg(["-y", "-i", str(src_wav), "-af", filt,
                             "-ar", str(wav_sample_rate),
                             "-c:a", pcm, str(out_wav)], timeout_s=1800)
    if not ok:
        return False, out
    ok, out = ff.run_ffmpeg(["-y", "-i", str(out_wav), "-codec:a",
                             "libmp3lame", "-b:a", mp3_bitrate,
                             str(out_mp3)], timeout_s=1800)
    return ok, out


def _master_numpy_file(src_wav, out_wav, out_mp3, target_lufs, tp_dbtp,
                       wav_sample_rate, wav_bit_depth, mp3_bitrate):
    """Blockweiser numpy-Fallback (nur falls kein ffmpeg vorhanden)."""
    import numpy as np
    from .io import read_wav, resample, write_wav
    wav, sr = read_wav(src_wav)
    cur = integrated_lufs(wav, sr)
    gain = 10.0 ** ((target_lufs - cur) / 20.0) if cur > -69 else 1.0
    tp_lin = 10.0 ** (tp_dbtp / 20.0)
    # Gain begrenzen, damit True-Peak nicht massiv überschritten wird
    peak = float(np.max(np.abs(wav))) if wav.size else 0.0
    if peak * gain > tp_lin * 1.05:
        gain = min(gain, tp_lin * 1.05 / max(peak, 1e-9))
    wav = (wav * gain).astype(np.float32)
    wav = resample(wav, sr, wav_sample_rate)
    write_wav(out_wav, wav, wav_sample_rate, bit_depth=wav_bit_depth)
    del wav
    if ff.ffmpeg_available():
        ff.run_ffmpeg(["-y", "-i", str(out_wav), "-codec:a", "libmp3lame",
                       "-b:a", mp3_bitrate, str(out_mp3)])
    else:
        log.warning("Kein ffmpeg – MP3 wurde NICHT erzeugt.")
