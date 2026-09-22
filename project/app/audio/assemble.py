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


def _crossfade_pair(prev: np.ndarray, nxt: np.ndarray, sr: int,
                    overlap_ms: float = 35.0) -> tuple[np.ndarray, int]:
    """Cross-fade the tail of ``prev`` into the head of ``nxt`` to hide
    boundary clicks between independently synthesized segments. Uses
    equal-power ramps for a perceptually smooth join. Returns
    ``(merged_wav, trim_samples_removed_from_next)`` so pause logic can
    account for the overlap.
    """
    ol = max(1, int(sr * overlap_ms / 1000.0))
    if len(prev) < ol or len(nxt) < ol:
        ol = min(len(prev), len(nxt))
        if ol < 8:
            return np.concatenate([prev, nxt]).astype(np.float32), 0
    ramp = np.linspace(0.0, 1.0, ol, dtype=np.float32)
    eqp = np.sqrt(ramp)
    tail = prev[-ol:] * (1.0 - eqp)
    head = nxt[:ol] * eqp
    overlap = (tail + head).astype(np.float32)
    merged = np.concatenate([prev[:-ol], overlap, nxt[ol:]]).astype(np.float32)
    return merged, ol


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


def _do_crossfade(processed: list[np.ndarray], sr_out: int,
                  crossfade_ms: float) -> list[np.ndarray]:
    """Apply short equal-power crossfades at each segment boundary to
    suppress boundary clicks. The segment list stays INTACT (one entry
    per segment) so pauses are inserted AFTER crossfading and long
    natural pauses are preserved between the entries.

    INTEGRATIONS-FIX: Die fruehere Implementierung verschmolz
    (`out[-1] = merged`) alle Segmente zu EINEM Waveform – der
    Schreib-Loop in assemble/assemble_to_file lief danach nur noch
    ueber 1 Element und schrieb ausschliesslich die Pause des ersten
    Segments; alle weiteren pause_after_s gingen im Audio verloren
    (Plan im Log korrekt, Audio ohne innere Pausen). Der Crossfade
    selbst ist mathematisch identisch, wird aber nur noch an der
    Grenze der beiden jeweiligen Nachbarn angewendet.
    """
    if crossfade_ms <= 0 or len(processed) <= 1:
        return processed
    ol = max(1, int(sr_out * crossfade_ms / 1000.0))
    out: list[np.ndarray] = [processed[0]]
    for nxt in processed[1:]:
        prev = out[-1]
        if len(prev) < ol or len(nxt) < ol:
            ol_i = min(len(prev), len(nxt))
            if ol_i < 8:
                out.append(nxt)
                continue
        else:
            ol_i = ol
        ramp = np.linspace(0.0, 1.0, ol_i, dtype=np.float32)
        eqp = np.sqrt(ramp)
        overlap = (prev[-ol_i:] * (1.0 - eqp)
                   + nxt[:ol_i] * eqp).astype(np.float32)
        out[-1] = np.concatenate([prev[:-ol_i], overlap]).astype(np.float32)
        out.append(nxt[ol_i:])
    return out


def assemble(segments_audio: list[tuple[np.ndarray, int, Segment]],
             project_median_lufs: float | None = None,
             precomputed_lufs: list[float] | None = None,
             crossfade_ms: float = 25.0) -> tuple[np.ndarray, int]:
    """Fügt [(wav, sr, segment)] zum Gesamt audio zusammen.

    project_median_lufs: Ziel für die Voranpassung (Median der Segment-
    LUFS-Werte). None = keine Anpassung. precomputed_lufs vermeidet
    doppelte Messung (Pipeline misst ohnehin). Ein kurzer Crossfade
    zwischen Segmenten verhindert Klick-Artefakte an Segmentgrenzen.
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

    processed = _do_crossfade(processed, sr_out, crossfade_ms)

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
    """Tempo-Änderung 0.8–1.2, immer pitch-erhaltend.

    B-Kette: TTS (speed=1.0) → Segment-Assembly → explizite Pausen →
    gesamtes Audio → pitch-erhaltendes apply_speed() → Final Audio.
    Hauptpfad: ffmpeg atempo (Pitch unverändert). Fallback ohne ffmpeg:
    deterministische WSOLA-Zeitdehnung (Pitch ebenfalls unverändert;
    ersetzt die frueher tonhoeenaendernde Linear-Interpolation).
    Pausen werden gekoppelt behandelt (assemble/assemble_to_file skalieren
    die expliziten Pausen mit 1/speed), damit die Pausenproportionen bei
    Geschwindigkeitsaenderungen natuerlich bleiben.
    """
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
    return _speed_wsola(wav, sr, speed)


def _speed_wsola(wav: np.ndarray, sr: int, speed: float) -> np.ndarray:
    """Deterministische WSOLA-Zeitdehnung (pitch-erhaltend, ohne ffmpeg).

    Overlap-Add mit Hann-Fenster; die Frame-Position im Eingang wird je
    Schritt per Kreuzkorrelation mit der natuerlichen Fortsetzung im
    +/-12-ms-Fenster gesucht (WSOLA-Similarity). Kein Zufall: identische
    Eingaben liefern bit-identische Ausgaben. Gueltig fuer 0.8–1.2.
    """
    wav = np.asarray(wav, dtype=np.float32)
    n = len(wav)
    if n < 8 * sr // 50:                      # sehr kurze Eingaben: unveraendert
        return wav
    frame = max(256, int(0.040 * sr))         # 40 ms Rahmen
    hop_out = frame // 2
    tol = max(64, int(0.012 * sr))            # +/-12 ms Suchfenster
    step = max(1, tol // 32)                  # feines Suchraster (Determinismus)
    win = np.hanning(frame).astype(np.float32)
    hop_in = hop_out * float(speed)
    out_len = int(n / speed) + 2 * frame
    out = np.zeros(out_len, dtype=np.float32)
    norm = np.zeros(out_len, dtype=np.float32)
    pos_out = 0
    k = 0
    ref = None                                # natuerliche Fortsetzung (Tail)
    from numpy.lib.stride_tricks import sliding_window_view
    while True:
        ideal = int(round(k * hop_in))
        lo = max(0, ideal - tol)
        hi = min(n - frame, ideal + tol)
        if hi < lo:
            break
        if ref is None or hi == lo:
            s = min(max(ideal, 0), hi)
        else:
            ol = min(hop_out, n - lo)
            cand = np.arange(lo, hi + 1, step)
            cand = cand[cand + ol <= n]
            if cand.size == 0:
                s = min(max(ideal, 0), hi)
            else:
                # vektorisierte Kreuzkorrelation: Kandidaten-Anfaenge gegen
                # die natuerliche Fortsetzung (Output-Tail)
                windows = sliding_window_view(wav, ol)[cand]
                scores = windows @ ref[:ol]
                s = int(cand[int(np.argmax(scores))])
        seg = wav[s:s + frame]
        if len(seg) < frame:
            seg = np.pad(seg, (0, frame - len(seg)))
        end = pos_out + frame
        if end > out_len:
            break
        out[pos_out:end] += seg * win
        norm[pos_out:end] += win
        nxt = pos_out + hop_out
        if nxt + hop_out > out_len:
            break
        ref = out[nxt:nxt + hop_out]
        pos_out = nxt
        k += 1
    good = norm > 1e-6
    out[good] /= norm[good]
    return out[:int(n / speed) + hop_out]


# ===========================================================================
# Phase Desktop (§18/§35): Streaming-Assembly direkt in Datei –
# speicherbefreit für sehr lange Texte (120 min+). Segmente werden
# nacheinander geschrieben (inkl. Vorverarbeitung + Pausen), das
# Mastering liest die Datei anschließend streaming (ffmpeg 2-Pass).
# ===========================================================================
def assemble_to_file(segments_audio, out_path, project_median_lufs=None,
                     precomputed_lufs=None, speed: float = 1.0,
                     bit_depth: int = 24,
                     crossfade_ms: float = 25.0) -> tuple:
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

    # Crossfades VOR dem Schreiben, damit keine Klicks an Grenzen.
    processed = _do_crossfade(processed, sr_out, crossfade_ms)

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
    # Speed-Nachweis: bei |speed-1| < 0.02 (inkl. 1.00) ist apply_speed
    # BY DESIGN inaktiv (keine kuenstliche Verlangsamung/Beschleunigung);
    # die geplanten Pausen wurden mit 1/speed gekoppelt uebernommen.
    log.info("ASSEMBLY_SPEED speed=%.2f apply_speed_aktiv=%s "
             "pausen_gesamt=%.2fs",
             float(speed), abs(float(speed) - 1.0) >= 0.02, pause_total)
    return sr_out, total / sr_out, pause_total


from pathlib import Path  # noqa: E402
