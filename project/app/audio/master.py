"""Mastering (Anforderung 40 + 41): Lautheitsnormalisierung (EBU R128),
True-Peak-Limit, YouTube-Master, WAV + MP3 Ausgabe (konfigurierbar).

Ausgabeformate (output_format):
  "wav_mp3"  -> WAV + MP3 (Standard)
  "wav"      -> nur WAV, KEIN MP3 erzeugen, keine Alt-MP3 als Ergebnis zeigen
  "mp3"      -> nur MP3 (intern darf temp-WAV für Loudness verwendet werden,
                        aber final wird nur MP3 zurückgegeben)

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

# Zentrales Ausgabeformat-Enum (als Strings für einfache JSON-Serialisierung)
OUTPUT_FORMAT_WAV_MP3 = "wav_mp3"
OUTPUT_FORMAT_WAV = "wav"
OUTPUT_FORMAT_MP3 = "mp3"
VALID_OUTPUT_FORMATS = (OUTPUT_FORMAT_WAV_MP3, OUTPUT_FORMAT_WAV, OUTPUT_FORMAT_MP3)


def normalize_output_format(fmt: str | None) -> str:
    """Normalisiere ein Ausgabeformat auf einen der drei gültigen Werte.

    Akzeptiert auch alte Schreibweisen ("WAV + MP3", "nur WAV", "nur MP3",
    ["wav","mp3"] etc.) zwecks Abwärtskompatibilität.
    """
    if fmt is None:
        return OUTPUT_FORMAT_WAV_MP3
    if isinstance(fmt, (list, tuple, set)):
        has_wav = "wav" in [str(x).lower() for x in fmt]
        has_mp3 = "mp3" in [str(x).lower() for x in fmt]
        if has_wav and has_mp3:
            return OUTPUT_FORMAT_WAV_MP3
        if has_wav:
            return OUTPUT_FORMAT_WAV
        if has_mp3:
            return OUTPUT_FORMAT_MP3
        return OUTPUT_FORMAT_WAV_MP3
    s = str(fmt).strip().lower()
    if s in ("wav+mp3", "wav_mp3", "wav + mp3", "both", "all", "true", "1"):
        return OUTPUT_FORMAT_WAV_MP3
    if s in ("wav", "nur wav", "wav-only", "wav_only", "wave"):
        return OUTPUT_FORMAT_WAV
    if s in ("mp3", "nur mp3", "mp3-only", "mp3_only"):
        return OUTPUT_FORMAT_MP3
    # legacy GUI mapping: combobox "WAV + MP3" / "nur WAV"
    if "mp3" in s and "wav" in s:
        return OUTPUT_FORMAT_WAV_MP3
    if "wav" in s:
        return OUTPUT_FORMAT_WAV
    if "mp3" in s:
        return OUTPUT_FORMAT_MP3
    return OUTPUT_FORMAT_WAV_MP3


def _should_produce_wav(fmt: str) -> bool:
    return fmt in (OUTPUT_FORMAT_WAV_MP3, OUTPUT_FORMAT_WAV)


def _should_produce_mp3(fmt: str) -> bool:
    return fmt in (OUTPUT_FORMAT_WAV_MP3, OUTPUT_FORMAT_MP3)


def _cleanup_unrequested(final_wav: Path, final_mp3: Path, fmt: str) -> None:
    """Lösche Endprodukte, die vom Nutzer nicht angefordert wurden, damit
    keine Alt-Datei als „aktuelles Ergebnis“ erscheint (§9).
    Temporäre Dateien (z. B. für MP3-only Loudness) werden separat
    behandelt und immer gelöscht.
    """
    if not _should_produce_wav(fmt) and final_wav.exists():
        try:
            final_wav.unlink()
        except OSError:
            pass
    if not _should_produce_mp3(fmt) and final_mp3.exists():
        try:
            final_mp3.unlink()
        except OSError:
            pass


def master_to_youtube(wav: np.ndarray, sr: int, out_wav: Path, out_mp3: Path,
                      target_lufs: float = -14.0, true_peak_dbtp: float = -1.5,
                      wav_sample_rate: int = 48000, wav_bit_depth: int = 24,
                      mp3_bitrate: str = "320k",
                      volume_db: float = 0.0,
                      output_format: str = OUTPUT_FORMAT_WAV_MP3) -> dict:
    """Erzeugt WAV-Master und/oder MP3-Endversion mit YouTube-tauglicher Loudness.

    output_format: "wav_mp3" | "wav" | "mp3"  (siehe oben).
    volume_db: manuelle Pegelanpassung vor dem Mastering (Anforderung 27).
    """
    fmt = normalize_output_format(output_format)
    report: dict = {"ffmpeg": False, "lufs_in": None, "lufs_out": None,
                    "tp_out": None,
                    "output_format": fmt,
                    "wav": str(out_wav) if _should_produce_wav(fmt) else None,
                    "mp3": str(out_mp3) if _should_produce_mp3(fmt) else None}

    lufs_in = integrated_lufs(wav, sr)
    report["lufs_in"] = lufs_in

    if volume_db:
        wav = (wav * (10.0 ** (volume_db / 20.0))).astype(np.float32)

    out_wav = Path(out_wav)
    out_mp3 = Path(out_mp3)
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    # Für MP3-only: Mastering in eine temp-WAV schreiben, dann encodieren,
    # dann die temp-WAV löschen (finales Verzeichnis enthält nur MP3).
    final_wav = out_wav
    wav_is_temp = False
    if fmt == OUTPUT_FORMAT_MP3:
        import tempfile
        tmp_dir = Path(tempfile.gettempdir())
        final_wav = tmp_dir / f"_vomaster_{out_wav.stem}_{int(__import__('time').time()*1000)}.wav"
        wav_is_temp = True

    if ff.ffmpeg_available():
        ok, info = _master_ffmpeg(wav, sr, final_wav, out_mp3, target_lufs,
                                  true_peak_dbtp, wav_sample_rate,
                                  wav_bit_depth, mp3_bitrate, fmt)
        if ok:
            report["ffmpeg"] = True
            if final_wav.exists():
                report["lufs_out"] = _measure_file_lufs(final_wav)
                report["tp_out"] = _measure_file_truepeak(final_wav)
            plog(f"MASTER ffmpeg ok: in={lufs_in} LUFS -> out={report['lufs_out']} LUFS, "
                 f"TP={report['tp_out']} dBTP, fmt={fmt}")
            if wav_is_temp:
                try: final_wav.unlink()
                except OSError: pass
            _cleanup_unrequested(out_wav, out_mp3, fmt)
            return report
        log.warning("ffmpeg-Mastering fehlgeschlagen (%s) – numpy-Fallback", info[:200])

    # ---------------- Fallback: numpy ------------------------------------
    wav48 = resample(wav, sr, wav_sample_rate)
    wav48 = _normalize_numpy(wav48, wav_sample_rate, target_lufs, true_peak_dbtp)
    write_wav(final_wav, wav48, wav_sample_rate, bit_depth=wav_bit_depth)
    report["lufs_out"] = integrated_lufs(wav48, wav_sample_rate)
    report["tp_out"] = _calc_tp(wav48, wav_sample_rate)
    if _should_produce_mp3(fmt) and ff.ffmpeg_available():
        ok, err = ff.run_ffmpeg([
            "-y", "-i", str(final_wav), "-codec:a", "libmp3lame",
            "-b:a", mp3_bitrate, str(out_mp3)])
        if not ok:
            log.warning("MP3-Kodierung fehlgeschlagen: %s", err[:200])
            report["mp3"] = None
    elif fmt == OUTPUT_FORMAT_MP3 and not ff.ffmpeg_available():
        log.warning("Kein ffmpeg verfügbar – MP3 wurde NICHT erzeugt (nur WAV-Master).")
        # MP3-only ohne ffmpeg nicht möglich -> besseres Ergebnis: WAV behalten
        import shutil
        try:
            shutil.copyfile(str(final_wav), str(out_wav))
            report["wav"] = str(out_wav)
            report["mp3"] = None
        except OSError:
            pass
    plog(f"MASTER numpy: in={lufs_in} -> out={report['lufs_out']} LUFS, "
         f"TP={report['tp_out']} dBTP, fmt={fmt}")
    if wav_is_temp and fmt == OUTPUT_FORMAT_MP3:
        try: final_wav.unlink()
        except OSError: pass
    if not wav_is_temp and fmt == OUTPUT_FORMAT_MP3 and out_wav.exists():
        # Der numpy-Fallback hat direkt nach out_wav geschrieben; löschen,
        # weil der Nutzer nur MP3 wollte.
        try: out_wav.unlink()
        except OSError: pass
    _cleanup_unrequested(out_wav, out_mp3, fmt)
    return report


def _master_ffmpeg(wav: np.ndarray, sr: int, out_wav: Path, out_mp3: Path,
                   target_lufs: float, tp: float, wav_sample_rate: int,
                   wav_bit_depth: int, mp3_bitrate: str,
                   fmt: str = OUTPUT_FORMAT_WAV_MP3) -> tuple[bool, str]:
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
        # WAV erzeugen wenn benötigt (auch für MP3-only, weil es die
        # Loudnorm-Ausgabe ist; bei MP3-only ist out_wav eine temp-Datei).
        ok, out = ff.run_ffmpeg([
            "-y", "-i", str(src), "-af", filt,
            "-ar", str(wav_sample_rate), "-sample_fmt", "s32",
            "-c:a", pcm, str(out_wav)])
        if not ok:
            return False, out
        # MP3 nur wenn gewünscht
        if _should_produce_mp3(fmt):
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
# Datei-basiertes Mastering (§18): Quelle = WAV-Datei, Ausgabe WAV und/oder MP3.
# ffmpeg loudnorm 2-Pass arbeitet streaming; numpy-Fallback misst/schreibt
# in Blöcken (kein Voll-Array im RAM).
# ===========================================================================
def master_file_to_youtube(src_wav: Path, out_wav: Path, out_mp3: Path,
                           target_lufs: float = -14.0,
                           true_peak_dbtp: float = -1.5,
                           wav_sample_rate: int = 48000,
                           wav_bit_depth: int = 24,
                           mp3_bitrate: str = "320k",
                           output_format: str = OUTPUT_FORMAT_WAV_MP3) -> dict:
    fmt = normalize_output_format(output_format)
    import tempfile, time as _time
    report: dict = {"ffmpeg": False, "lufs_in": None, "lufs_out": None,
                    "tp_out": None,
                    "output_format": fmt,
                    "wav": str(out_wav) if _should_produce_wav(fmt) else None,
                    "mp3": str(out_mp3) if _should_produce_mp3(fmt) else None}
    src_wav, out_wav = Path(src_wav), Path(out_wav)
    final_wav = out_wav
    wav_is_temp = False
    if fmt == OUTPUT_FORMAT_MP3:
        final_wav = Path(tempfile.gettempdir()) / \
            f"_vomaster_file_{out_wav.stem}_{int(_time.time()*1000)}.wav"
        wav_is_temp = True
    if ff.ffmpeg_available():
        ok, info = _master_ffmpeg_file(src_wav, final_wav, out_mp3, target_lufs,
                                       true_peak_dbtp, wav_sample_rate,
                                       wav_bit_depth, mp3_bitrate, fmt)
        if ok:
            report["ffmpeg"] = True
            if final_wav.exists():
                report["lufs_out"] = _measure_file_lufs(final_wav)
                report["tp_out"] = _measure_file_truepeak(final_wav)
            if wav_is_temp:
                try: final_wav.unlink()
                except OSError: pass
            _cleanup_unrequested(out_wav, out_mp3, fmt)
            return report
        log.warning("ffmpeg-Datei-Mastering fehlgeschlagen (%s) – numpy",
                    info[:200])
    _master_numpy_file(src_wav, final_wav, out_mp3, target_lufs, true_peak_dbtp,
                       wav_sample_rate, wav_bit_depth, mp3_bitrate, fmt)
    if final_wav.exists():
        report["lufs_out"] = _measure_file_lufs(final_wav)
        report["tp_out"] = _measure_file_truepeak(final_wav)
    if wav_is_temp:
        if not out_mp3.exists() and final_wav.exists():
            try:
                import shutil
                shutil.copyfile(str(final_wav), str(out_wav))
                report["wav"] = str(out_wav)
            except OSError:
                pass
        try: final_wav.unlink()
        except OSError: pass
    if not wav_is_temp and fmt == OUTPUT_FORMAT_MP3 and out_wav.exists():
        try: out_wav.unlink()
        except OSError: pass
    _cleanup_unrequested(out_wav, out_mp3, fmt)
    return report


def _master_ffmpeg_file(src_wav: Path, out_wav: Path, out_mp3: Path,
                        target_lufs: float, tp: float, wav_sample_rate: int,
                        wav_bit_depth: int, mp3_bitrate: str,
                        fmt: str = OUTPUT_FORMAT_WAV_MP3):
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
    if _should_produce_mp3(fmt):
        ok, out = ff.run_ffmpeg(["-y", "-i", str(out_wav), "-codec:a",
                                 "libmp3lame", "-b:a", mp3_bitrate,
                                 str(out_mp3)], timeout_s=1800)
        if not ok:
            return False, out
    return ok, out


def _master_numpy_file(src_wav, out_wav, out_mp3, target_lufs, tp_dbtp,
                       wav_sample_rate, wav_bit_depth, mp3_bitrate,
                       fmt: str = OUTPUT_FORMAT_WAV_MP3):
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
    if _should_produce_mp3(fmt) and ff.ffmpeg_available():
        ff.run_ffmpeg(["-y", "-i", str(out_wav), "-codec:a", "libmp3lame",
                       "-b:a", mp3_bitrate, str(out_mp3)])
    else:
        log.warning("Kein ffmpeg – MP3 wurde NICHT erzeugt.")
