#!/usr/bin/env python3
"""Voice inventory + short-test matrix for Voice-AI-Reference.

Produces:
  project/benchmark/voice_inventory/inventory.json     machine-readable
  project/benchmark/voice_inventory/INVENTORY.md       human-readable
  project/benchmark/voice_inventory/short/<voice>/     per-voice short WAVs

Two modes:

  --static    Inspect registry/profile/bundle only (no model load; runs
              anywhere, produces pass/needs_fix/blocked for everything
              that can be decided without synthesis).
  --short     Run a ~5-10 second synthesis for every selectable voice
              and record waveform metrics (RMS/peak/NaN/QC). Requires
              GPU + installed Qwen3-TTS models.
  --spot N    Run a ~N-second long-form spot check (segmentation +
              assembly) for every voice that passes --short. Expensive.

Standard short-test texts (per language): roughly 6-10 s, semantically
rich, exercise punctuation and different consonants. These are held
constant so results are comparable across voices.

Usage:
  # Static inventory (always, no GPU needed):
  python project/tools/voice_inventory.py --static

  # Full matrix on GPU host:
  python project/tools/voice_inventory.py --static --short --spot 60
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import time
import traceback
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "project"
sys.path.insert(0, str(PROJECT))

OUT_DIR = PROJECT / "benchmark" / "voice_inventory"
SHORT_DIR = OUT_DIR / "short"
SPOT_DIR = OUT_DIR / "spot"

# Standard short test texts (≈6-10s of speech at natural pace).
# Same text for all voices in a language so metrics are comparable.
SHORT_TEXT_EN = (
    "Every discovery begins with a question. Sometimes the answer is "
    "hidden in plain sight, waiting for someone patient enough to look "
    "beyond the obvious."
)
SHORT_TEXT_DE = (
    "Jede Entdeckung beginnt mit einer Frage. Manchmal liegt die Antwort "
    "direkt vor uns, verborgen im Offensichtlichen. Erst wenn wir genau "
    "hinschauen, erkennen wir, was wirklich geschah."
)

# Long-form spot-check text (~60 s of content) per language.
SPOT_TEXT_EN = (
    "There is a quiet pleasure in returning to a story we thought we knew. "
    "Each time we read it, something new surfaces: a word we had skipped, "
    "a rhythm we had missed, a question we had not been ready to ask. "
    "That is the mark of serious writing, and of serious listening as well. "
    "A voice does not merely recount events. It frames silence, shapes "
    "attention, and invites the listener to slow down. In long-form "
    "narration, consistency matters more than momentary drama: the same "
    "timbre, the same patience, the same respect for every sentence. "
    "When a narrator holds that balance across minutes, the story stops "
    "feeling performed and begins to feel inevitable."
)
SPOT_TEXT_DE = (
    "Es liegt eine stille Freude darin, zu einer Geschichte zurückzukehren, "
    "die wir zu kennen glaubten. Jedes Mal, wenn wir sie lesen, taucht etwas "
    "Neues auf: ein Wort, das wir überlasen, ein Rhythmus, der uns entging, "
    "eine Frage, die zu stellen wir noch nicht bereit waren. Das ist das "
    "Zeichen ernsthaften Schreibens, und auch ernsthaften Zuhörens. Eine "
    "Stimme erzählt nicht nur Ereignisse. Sie rahmt die Stille, lenkt die "
    "Aufmerksamkeit und lädt den Zuhörer ein, langsamer zu werden. In der "
    "langen Form zählt Beständigkeit mehr als augenblickliche Dramatik: die "
    "gleiche Klangfarbe, die gleiche Geduld, der gleiche Respekt vor jedem "
    "Satz. Wenn ein Sprecher dieses Gleichgewicht über Minuten hält, wirkt "
    "die Geschichte nicht mehr vorgespielt, sondern selbstverständlich."
)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


@dataclass
class VoiceResult:
    voice_id: str
    display_name: str
    gender: str
    backend: str           # customvoice | clone
    language_native: str
    production_locked: bool
    recommended: bool
    speaker_name: str | None
    ref_path: str | None
    # Static checks
    profile_status: str = "OK"           # OK | MISSING
    bundle_status: str = "N/A"           # VALID | INVALID | MISSING | N/A | BOOTSTRAPPED
    bundle_detail: str = ""
    audio_sha256: str | None = None
    text_sha256: str | None = None
    seed: int | None = None
    ref_text_key: str | None = None
    selectable_in_gui: bool = True
    available_in_registry: bool = False
    static_notes: list[str] = field(default_factory=list)
    # Short synthesis
    short_status: str = "NOT_RUN"        # NOT_RUN | PASS | FAIL | SKIPPED
    short_detail: str = ""
    short_duration_s: float | None = None
    short_rms: float | None = None
    short_peak: float | None = None
    short_nan: bool | None = None
    short_retry_count: int | None = None
    short_qc_score: float | None = None
    short_final_gate: str | None = None
    short_output: str | None = None
    short_elapsed_s: float | None = None
    # Long-form spot
    spot_status: str = "NOT_RUN"
    spot_detail: str = ""
    spot_duration_s: float | None = None
    spot_regen_count: int | None = None
    spot_failed_segments: int | None = None
    spot_avg_score: float | None = None
    spot_output: str | None = None
    # Final classification
    classification: str = "PENDING"      # PASS | NEEDS_FIX | BLOCKED | PENDING
    classification_reason: str = ""
    human_listening_required: bool = True


def inspect_static(voices: list[VoiceResult]) -> None:
    """Populate all static fields by inspecting registry, bundles, GUI groups."""
    from app import paths
    from app.voices.registry import VoiceRegistry
    from app.tts.reference_bundle import (BundleResolutionError,
                                          default_ref_text_for,
                                          load_bundle, resolve_bundle)

    reg = VoiceRegistry()
    entries = {e.voice_id: e for e in reg.entries()}

    # GUI grouping
    try:
        from app.gui.voice_view import voice_groups
        groups = voice_groups()
        gui_ids: set[str] = set()
        for g in groups:
            for v in g.get("voices", []):
                gui_ids.add(v.get("voice_id"))
    except Exception as e:                         # noqa: BLE001
        gui_ids = set(entries.keys())
        # If GUI can't be inspected we assume all registered are selectable.

    for v in voices:
        e = entries.get(v.voice_id)
        if e is None:
            v.profile_status = "MISSING"
            v.classification = "BLOCKED"
            v.classification_reason = "voice_id not in registry"
            continue
        v.available_in_registry = True
        v.display_name = e.display_name
        v.vselectable_in_gui = e.voice_id in gui_ids
        # settings seed
        try:
            jf = PROJECT / "voices" / f"{v.voice_id}.json"
            if jf.exists():
                data = json.loads(jf.read_text(encoding="utf-8"))
                s = (data.get("settings") or {}).get("seed")
                if s is not None:
                    v.seed = int(s)
        except Exception:
            pass
        v.ref_text_key = e.reference_text_key
        if v.backend == "customvoice":
            v.bundle_status = "N/A"
            v.classification = "PENDING_SHORT"
            v.static_notes.append("customvoice (no reference bundle)")
            continue
        # Clone: resolve canonical wav + bundle
        wav = paths.VOICE_REFS_DIR / f"{v.voice_id}.wav"
        if not wav.exists():
            v.bundle_status = "MISSING"
            v.bundle_detail = f"canonical WAV not found: {wav}"
            v.classification = "NEEDS_FIX"
            v.classification_reason = "reference WAV missing (not materialized)"
            v.static_notes.append("materialize with tools/materialize_references.py")
            continue
        # Try resolve_bundle
        try:
            lang = "English" if v.voice_id.startswith("en_") else \
                   "German" if v.voice_id.startswith("de_") or v.voice_id == "vd_e" \
                   else "English"
            require = (v.voice_id != "vd_e")
            bundle = resolve_bundle(v.voice_id, language=lang,
                                    require_manifest=require)
            v.bundle_status = "VALID"
            v.bundle_detail = f"bundle_id={bundle.bundle_id()}"
            v.audio_sha256 = bundle.audio_sha256
            v.text_sha256 = bundle.reference_text_sha256
            if bundle.generation.get("seed") is not None:
                v.seed = bundle.generation.get("seed")
            v.classification = "PENDING_SHORT"
        except BundleResolutionError as ex:
            msg = str(ex)
            if "MANIFEST_MISSING" in msg:
                v.bundle_status = "MISSING"
                v.classification = "NEEDS_FIX"
                v.classification_reason = "sidecar manifest missing (run bootstrap_reference_bundles.py)"
            elif "AUDIO_SHA256" in msg or "TEXT_SHA256" in msg:
                v.bundle_status = "INVALID"
                v.classification = "BLOCKED"
                v.classification_reason = "hash mismatch in manifest; provenance broken"
            elif "AMBIGUOUS" in msg:
                v.bundle_status = "INVALID"
                v.classification = "NEEDS_FIX"
                v.classification_reason = "duplicate/ambiguous reference files"
            elif "AUDIO_MISSING" in msg:
                v.bundle_status = "MISSING"
                v.classification = "NEEDS_FIX"
                v.classification_reason = "WAV not found"
            else:
                v.bundle_status = "INVALID"
                v.classification = "NEEDS_FIX"
                v.classification_reason = msg.split("\n")[0][:160]
            v.bundle_detail = msg


def _build_engine(v: VoiceResult):
    from app.hardware.detector import detect_hardware
    if v.backend == "customvoice":
        from app.tts.qwen_engine import QwenTTSEngine
        from app.hardware.detector import recommend_model_size, recommend_torch_dtype
        hw = detect_hardware()
        adv = {}
        try:
            from app import config as cfgmod
            adv = cfgmod.load_config().get("advanced", {})
        except Exception:
            pass
        return QwenTTSEngine(
            hw=hw,
            model_size=recommend_model_size(hw,
                adv.get("prefer_model_size", "auto")),
            dtype_hint=recommend_torch_dtype(hw),
            attn_implementation=adv.get("attn_implementation") or None)
    # Clone: use VoiceCloneEngine with canonical bundle resolution.
    from app.jobs.runner import _resolve_voice_native_language, _resolve_voice_seed
    from app.tts.qwen_engine import VoiceCloneEngine
    from app.voices.registry import VoiceRegistry
    reg = VoiceRegistry()
    entry = reg.get(v.voice_id)
    lang = _resolve_voice_native_language(reg, entry)
    seed = v.seed if v.seed is not None else _resolve_voice_seed(reg, entry)
    hw = detect_hardware()
    adv = {}
    try:
        from app import config as cfgmod
        adv = cfgmod.load_config().get("advanced", {})
    except Exception:
        pass
    desc = entry.description or ""
    return VoiceCloneEngine(
        hw=hw, candidate_id=v.voice_id, description=desc,
        language=lang, ref_text=None, seed=seed,
        attn_implementation=adv.get("attn_implementation") or None,
        allow_design=False, reference_path=None)


def run_short(voices: list[VoiceResult]) -> None:
    """Run a single ~5-10 s synthesis per voice that is PENDING_SHORT."""
    import numpy as np
    from app.tts.engine_base import SynthesisRequest
    from app.project.pipeline import Pipeline
    from app import config as cfgmod, paths
    for v in voices:
        if v.classification not in ("PENDING_SHORT", "PENDING_SPOT"):
            v.short_status = "SKIPPED"
            v.short_detail = v.classification_reason or v.bundle_detail
            continue
        out_v = SHORT_DIR / v.voice_id
        out_v.mkdir(parents=True, exist_ok=True)
        lang = "English" if v.voice_id.startswith("en_") else (
            "German" if v.voice_id.startswith("de_") or v.voice_id == "vd_e"
            else "English")
        text = SHORT_TEXT_EN if lang == "English" else SHORT_TEXT_DE
        try:
            engine = _build_engine(v)
            t0 = time.perf_counter()
            engine.load()
            seed = v.seed if v.seed is not None else 52000
            req = SynthesisRequest(text=text, language=lang,
                                   speaker=(v.speaker_name or v.voice_id),
                                   seed=seed, max_seconds_hint=15.0)
            res = engine.synthesize(req)
            wav = res.waveform if hasattr(res, "waveform") else res.wave
            wav_np = np.asarray(wav, dtype=np.float32).reshape(-1)
            sr = int(res.sample_rate)
            dur = float(len(wav_np) / sr)
            rms = float(np.sqrt(np.mean(wav_np.astype("float64") ** 2)))
            peak = float(np.max(np.abs(wav_np.astype("float64"))))
            nan = bool(np.isnan(wav_np).any() or np.isinf(wav_np).any())
            out_wav = out_v / "short.wav"
            from app.audio.io import write_wav
            write_wav(out_wav, wav_np, sr, bit_depth=24)
            v.short_status = "PASS" if (not nan and dur > 2.0 and peak > 0.01
                                        and peak <= 1.0 and rms > 0.005) else "FAIL"
            v.short_detail = "ok" if v.short_status == "PASS" else \
                f"nan={nan} dur={dur:.2f} rms={rms:.4f} peak={peak:.4f}"
            v.short_duration_s = round(dur, 3)
            v.short_rms = round(rms, 5)
            v.short_peak = round(peak, 5)
            v.short_nan = nan
            v.short_elapsed_s = round(time.perf_counter() - t0, 3)
            v.short_output = str(out_wav.relative_to(ROOT))
            if v.short_status == "PASS":
                v.classification = "PENDING_SPOT"
            else:
                v.classification = "NEEDS_FIX"
                v.classification_reason = f"short synthesis anomaly: {v.short_detail}"
            try:
                engine.unload()
            except Exception:
                pass
        except Exception as e:                                # noqa: BLE001
            v.short_status = "FAIL"
            v.short_detail = f"{type(e).__name__}: {e}"
            v.classification = "NEEDS_FIX"
            v.classification_reason = v.short_detail


def run_spot(voices: list[VoiceResult], seconds_hint: int = 60) -> None:
    """Run a small long-form pipeline per PENDING_SPOT voice."""
    from app.project.pipeline import Pipeline
    from app import config as cfgmod, paths
    import numpy as np
    for v in voices:
        if v.classification != "PENDING_SPOT":
            v.spot_status = "SKIPPED"
            v.spot_detail = v.classification_reason or v.short_detail
            continue
        out_v = SPOT_DIR / v.voice_id
        out_v.mkdir(parents=True, exist_ok=True)
        lang = "English" if v.voice_id.startswith("en_") else (
            "German" if v.voice_id.startswith("de_") or v.voice_id == "vd_e"
            else "English")
        text = SPOT_TEXT_EN if lang == "English" else SPOT_TEXT_DE
        in_txt = out_v / "input.txt"
        in_txt.write_text(text, encoding="utf-8")
        try:
            engine = _build_engine(v)
            engine.load()
            seed = v.seed if v.seed is not None else 52000
            cfg = {
                "language": lang,
                "voice": {"id": v.voice_id, "speaker": v.voice_id,
                          "production_seed": seed},
                "output_dir": str(out_v),
                "output_format": "wav",
                "advanced": {
                    "qc_enabled": True,
                    "qc_max_attempts": 3,
                    "qc_min_score": 78,
                    "final_gate_ratio": 0.88,
                    "wav_sample_rate": 24000,
                    "wav_bit_depth": 24,
                    "target_lufs": -16.0,
                    "true_peak_dbtp": -1.0,
                    "attn_implementation": "sdpa",
                    "segment_seed_mode": "per_segment",
                    "segment_target_chars": 350,
                    "segment_min_chars": 120,
                    "segment_max_chars": 600,
                },
                "german": {"cache_version": "q3p-v2-integrity",
                           "tech_germanization": False,
                           "variation": {"enabled": False}},
                "preset": "deep_documentary",
            }
            t0 = time.perf_counter()
            pipe = Pipeline(cfg, engine)
            report = pipe.process_file(str(in_txt))
            v.spot_elapsed_s = round(time.perf_counter() - t0, 3)
            if not report.get("ok"):
                v.spot_status = "FAIL"
                v.spot_detail = f"pipeline error: {report.get('error')}"
                v.classification = "NEEDS_FIX"
                v.classification_reason = v.spot_detail
            else:
                v.spot_status = "PASS"
                v.spot_duration_s = report.get("duration_s")
                v.spot_regen_count = report.get("regenerated")
                v.spot_failed_segments = report.get("failed_segments")
                v.spot_avg_score = report.get("avg_score")
                v.spot_output = report.get("wav")
                # Acceptable: no failed segments, regeneration <= 1
                if (v.spot_failed_segments or 0) == 0 and (v.spot_regen_count or 0) <= 2:
                    v.classification = "PASS"
                    v.classification_reason = "short+spot pipeline OK; human listening required"
                else:
                    v.classification = "NEEDS_FIX"
                    v.classification_reason = (
                        f"spot regen={v.spot_regen_count} failed={v.spot_failed_segments}")
            try:
                engine.unload()
            except Exception:
                pass
        except Exception as e:                                # noqa: BLE001
            v.spot_status = "FAIL"
            v.spot_detail = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            v.classification = "NEEDS_FIX"
            v.classification_reason = v.spot_detail[:200]


def write_outputs(voices: list[VoiceResult]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SHORT_DIR.mkdir(parents=True, exist_ok=True)
    SPOT_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "head_commit": _git_commit(),
        "voices": [asdict(v) for v in voices],
        "short_text_en": SHORT_TEXT_EN,
        "short_text_de": SHORT_TEXT_DE,
        "spot_text_en": SPOT_TEXT_EN,
        "spot_text_de": SPOT_TEXT_DE,
    }
    (OUT_DIR / "inventory.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    _write_markdown(data)


def _git_commit() -> str:
    import subprocess
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                           capture_output=True, timeout=5, check=False)
        if r.returncode == 0:
            return r.stdout.decode().strip()
    except Exception:
        pass
    return "unknown"


def _write_markdown(data: dict) -> None:
    lines = []
    lines.append("# Voice Inventory & Quality Matrix\n")
    lines.append(f"Generated: {data['generated_at']}  ")
    lines.append(f"HEAD: `{data['head_commit']}`\n")
    by_class = {"PASS": [], "NEEDS_FIX": [], "BLOCKED": [],
                "PENDING_SHORT": [], "PENDING_SPOT": [], "PENDING": []}
    for v in data["voices"]:
        by_class.setdefault(v["classification"], []).append(v)
    lines.append("## Summary\n")
    lines.append(f"Total voices registered: **{len(data['voices'])}**  ")
    lines.append(f"- PASS: **{len(by_class['PASS'])}**  ")
    lines.append(f"- NEEDS_FIX: **{len(by_class['NEEDS_FIX'])}**  ")
    lines.append(f"- BLOCKED: **{len(by_class['BLOCKED'])}**  ")
    lines.append(f"- PENDING short/spot: **{len(by_class['PENDING_SHORT']) + len(by_class['PENDING_SPOT'])}**\n")

    def section(title: str, vs: list[dict]):
        lines.append(f"## {title} ({len(vs)})\n")
        if not vs:
            lines.append("_(none)_\n")
            return
        lines.append("| voice_id | lang | backend | bundle | short | spot | reason/notes |")
        lines.append("|---|---|---|---|---|---|---|")
        for v in sorted(vs, key=lambda x: x["voice_id"]):
            lines.append(
                f"| `{v['voice_id']}` | {v['language_native'][:3]} | "
                f"{v['backend']} | {v['bundle_status']} | "
                f"{v['short_status']} | {v['spot_status']} | "
                f"{(v['classification_reason'] or ', '.join(v['static_notes']) or '—')[:80]} |")
        lines.append("")
    section("PASS (short + spot clean, human listening pending)", by_class["PASS"])
    section("NEEDS FIX", by_class["NEEDS_FIX"])
    section("BLOCKED", by_class["BLOCKED"])
    section("Pending short synthesis", by_class["PENDING_SHORT"])
    section("Pending long-form spot check", by_class["PENDING_SPOT"])

    lines.append("## Short-test texts\n")
    lines.append("**English:** ")
    lines.append("> " + SHORT_TEXT_EN + "\n")
    lines.append("**German:** ")
    lines.append("> " + SHORT_TEXT_DE + "\n")
    lines.append("## Protected / reference voices\n")
    for v in data["voices"]:
        if v["production_locked"]:
            lines.append(f"- `{v['voice_id']}` — {v['display_name']} "
                         f"({v['language_native']}, {v['backend']})")
    lines.append("")
    lines.append("## Per-voice machine-readable data\n")
    lines.append("See `inventory.json` for full waveforms metrics and output paths.\n")
    (OUT_DIR / "INVENTORY.md").write_text("\n".join(lines), encoding="utf-8")


def build_voice_list() -> list[VoiceResult]:
    from app.voices.registry import VoiceRegistry
    reg = VoiceRegistry()
    out = []
    for e in reg.entries():
        out.append(VoiceResult(
            voice_id=e.voice_id,
            display_name=e.display_name,
            gender=e.gender,
            backend=e.backend_mode,
            language_native=e.native_language,
            production_locked=e.production_locked,
            recommended=e.recommended,
            speaker_name=e.speaker_name,
            ref_path=e.reference_path,
            ref_text_key=e.reference_text_key,
        ))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--static", action="store_true",
                    help="Run static inventory only (no synthesis).")
    ap.add_argument("--short", action="store_true",
                    help="Run short synthesis matrix after static checks.")
    ap.add_argument("--spot", type=int, default=0, metavar="SECONDS",
                    help="Run N-second spot long-form check for voices "
                         "that pass short (use 60 for the standard spot).")
    args = ap.parse_args()

    if not (args.static or args.short or args.spot):
        args.static = True   # default: static only

    voices = build_voice_list()
    inspect_static(voices)
    if args.short or args.spot:
        run_short(voices)
    if args.spot:
        run_spot(voices, seconds_hint=args.spot)
    write_outputs(voices)
    # Console summary
    n_pass = sum(1 for v in voices if v.classification == "PASS")
    n_fix = sum(1 for v in voices if v.classification == "NEEDS_FIX")
    n_blk = sum(1 for v in voices if v.classification == "BLOCKED")
    n_pen = len(voices) - n_pass - n_fix - n_blk
    print(f"\nInventory: {len(voices)} voices  PASS={n_pass}  "
          f"NEEDS_FIX={n_fix}  BLOCKED={n_blk}  PENDING={n_pen}")
    print(f"Report:  {OUT_DIR/'INVENTORY.md'}")
    print(f"JSON:    {OUT_DIR/'inventory.json'}")


if __name__ == "__main__":
    main()
