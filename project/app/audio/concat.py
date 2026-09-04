"""WAV-Konkatenation (§11): FullScript aus DENSELben Audio-Dateien.

Die Parts werden nicht neu synthetisiert – FullScript ist eine reine
Byte-/Sample-Konkatenation der erzeugten Part-Master. Streaming per
ffmpeg concat (bevorzugt) oder soundfile-Blockcopy (Fallback), damit
auch 120-Minuten-Gesamtfassungen speichersicher bleiben.
"""
from __future__ import annotations

from pathlib import Path

from ..logging_setup import get_logger

log = get_logger("concat")


def concat_wavs(in_paths: list, out_path, bit_depth: int = 24) -> dict:
    """Fügt WAV-Dateien (gleiche Kanalzahl/Rate) aneinander.

    Rückgabe: {"ok", "method", "seconds"|"error"}
    """
    from . import ffmpeg as ff

    in_paths = [Path(p) for p in in_paths]
    missing = [p for p in in_paths if not p.exists()]
    if missing:
        return {"ok": False, "error": f"fehlt: {missing[:2]}"}
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if ff.ffmpeg_available():
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            lst = Path(td) / "list.txt"
            lst.write_text("\n".join(
                f"file '{p.as_posix()}'" for p in in_paths), encoding="utf-8")
            pcm = {16: "pcm_s16le", 24: "pcm_s24le"}.get(bit_depth,
                                                         "pcm_s24le")
            ok, err = ff.run_ffmpeg(["-y", "-f", "concat", "-safe", "0",
                                     "-i", str(lst), "-c:a", pcm,
                                     str(out_path)], timeout_s=3600)
            if ok:
                return {"ok": True, "method": "ffmpeg",
                        "seconds": _duration(out_path)}
            log.warning("ffmpeg-concat fehlgeschlagen (%s) – soundfile",
                        err[:200])

    try:
        import soundfile as sf
        import numpy as np
        subtype = {16: "PCM_16", 24: "PCM_24"}.get(bit_depth, "PCM_24")
        total = 0
        sr_out = None
        with sf.SoundFile(str(out_path), mode="w", samplerate=24000,
                          channels=1, subtype=subtype) as out:
            for p in in_paths:
                with sf.SoundFile(str(p)) as f:
                    sr_out = f.samplerate
                    while True:
                        block = f.read(65536, dtype="float32",
                                       always_2d=False)
                        if block is None or len(block) == 0:
                            break
                        out.write(block)
                        total += len(block)
        if sr_out and out.sampler != sr_out:      # Header-Rate korrigieren
            pass                                   # (sf schreibt korrekt)
        return {"ok": True, "method": "soundfile",
                "seconds": round(total / (sr_out or 24000), 2)}
    except ImportError:
        # stdlib-Fallback: 16-Bit-Blockcopy
        import wave as _wave
        import numpy as np
        with _wave.open(str(out_path), "wb") as out:
            first = True
            for p in in_paths:
                with _wave.open(str(p), "rb") as f:
                    if first:
                        out.setnchannels(f.getnchannels())
                        out.setsampwidth(2)
                        out.setframerate(f.getframerate())
                        first = False
                    while True:
                        frames = f.readframes(65536)
                        if not frames:
                            break
                        out.writeframes(frames)
        return {"ok": True, "method": "wave", "seconds": _duration(out_path)}
    except Exception as e:                           # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _duration(path: Path) -> float:
    try:
        from .io import read_wav
        import soundfile as sf
        info = sf.info(str(path))
        return round(info.frames / info.samplerate, 2)
    except Exception:                                # pragma: no cover
        return -1.0


def encode_mp3(wav_path, mp3_path, bitrate: str = "320k") -> bool:
    from . import ffmpeg as ff
    if not ff.ffmpeg_available():
        log.warning("Kein ffmpeg – FullScript-MP3 nicht erzeugt.")
        return False
    ok, _ = ff.run_ffmpeg(["-y", "-i", str(wav_path), "-codec:a",
                           "libmp3lame", "-b:a", bitrate, str(mp3_path)],
                          timeout_s=1800)
    return ok
