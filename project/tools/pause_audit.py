#!/usr/bin/env python3
"""Offline pause-audit + prosody baseline tool.

Works WITHOUT torch/GPU/models. It walks the segmentation + pause logic
on a given text and reports, per pause strategy:

  - segment count
  - per-segment pause (type + s)
  - average / median / min / max pause
  - estimated total pause time
  - estimated total duration (chars / 15 + pauses)
  - distribution of pause types

This lets us measure pause structure BEFORE/AFTER the narrative
strategy change without needing real synthesis. For real audio we can
later compare with an RMS-based silence scan on the produced WAV.

Usage:
  python project/tools/pause_audit.py path/to/text.txt
  python project/tools/pause_audit.py path/to/text.txt --language English
  python project/tools/pause_audit.py --text "Hello. World, foo — bar."
"""
from __future__ import annotations
import argparse, sys, statistics, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "project"))

from app.text.analyze import analyze_text, Block             # noqa: E402
from app.text.normalize import normalize_text, NormalizationReport  # noqa: E402
from app.pronunciation import PronunciationEngine             # noqa: E402
from app.segmentation import SegmentationConfig, segment_text  # noqa: E402
from app.prosody.pauses import assign_pauses                  # noqa: E402


def build_segments(text: str, language: str, seg_cfg):
    analysis = analyze_text(text, language)
    norm = NormalizationReport()
    pr = PronunciationEngine(tech_germanization=False)

    def provider(block: Block) -> str:
        n = normalize_text(block.text, language, norm)
        p = pr.process(n, language, suggest_unknown=False)
        return p.text

    segs = segment_text(analysis.blocks, provider, seg_cfg)
    return segs


def audit(text: str, language: str, strat: str, style: str, speed: float,
          seg_cfg: SegmentationConfig, chars_per_sec: float):
    segs = build_segments(text, language, seg_cfg)
    assign_pauses(segs, style=style, speed=speed, strategy=strat)
    pauses = [s.pause_after_s for s in segs]
    roles = {}
    for s in segs:
        roles[s.pause_type] = roles.get(s.pause_type, 0) + 1
    total_chars = sum(len(s.text) for s in segs)
    est_spoken = total_chars / chars_per_sec
    est_pause = sum(pauses)
    near_zero = sum(1 for p in pauses if p < 0.25)
    return {
        "strategy": strat, "style": style, "speed": speed,
        "segments": len(segs),
        "total_chars": total_chars,
        "chars_per_sec": chars_per_sec,
        "est_spoken_s": round(est_spoken, 2),
        "est_pause_s": round(est_pause, 2),
        "est_total_s": round(est_spoken + est_pause, 2),
        "pause_avg_s": round(statistics.mean(pauses), 3) if pauses else 0,
        "pause_median_s": round(statistics.median(pauses), 3) if pauses else 0,
        "pause_min_s": round(min(pauses), 3) if pauses else 0,
        "pause_max_s": round(max(pauses), 3) if pauses else 0,
        "near_zero_count": near_zero,
        "pause_type_counts": roles,
        "per_segment": [
            {"idx": s.index, "chars": len(s.text), "type": s.pause_type,
             "pause_s": s.pause_after_s, "preview": s.text[:80]}
            for s in segs],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="Text file to audit")
    ap.add_argument("--text", help="Inline text instead of file")
    ap.add_argument("--language", default="English")
    ap.add_argument("--target-chars", type=int, default=420)
    ap.add_argument("--min-chars", type=int, default=120)
    ap.add_argument("--max-chars", type=int, default=700)
    ap.add_argument("--strategies", default="classic,semantic,flow,narrative")
    ap.add_argument("--style", default="auto")
    ap.add_argument("--speed", type=float, default=1.0)
    args = ap.parse_args()

    if args.text:
        text = args.text
    elif args.file:
        for enc in ("utf-8-sig", "utf-8", "utf-16", "cp1252", "latin-1"):
            try:
                text = Path(args.file).read_text(encoding=enc); break
            except Exception:
                continue
        else:
            text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    else:
        ap.error("provide --text or a file path")

    seg_cfg = SegmentationConfig(
        target_chars=args.target_chars, min_chars=args.min_chars,
        max_chars=args.max_chars, close_slack=0.45,
        hard_start_min_chars=200, respect_paragraph_boundary=True)
    cps = 15.0 if args.language.lower().startswith("en") else 13.8

    out = {"language": args.language, "text_chars": len(text)}
    for strat in [s.strip() for s in args.strategies.split(",") if s.strip()]:
        out[strat] = audit(text, args.language, strat, args.style, args.speed,
                           seg_cfg, cps)
    # Compact table
    print(f"{'strategy':<10} {'segs':>4} {'spoken_s':>8} {'pause_s':>8} "
          f"{'total_s':>8} {'avg':>5} {'med':>5} {'min':>5} {'max':>5} "
          f"{'near0':>5}  types")
    for strat in out:
        if strat in ("language", "text_chars"): continue
        r = out[strat]
        print(f"{strat:<10} {r['segments']:>4} {r['est_spoken_s']:>8.2f} "
              f"{r['est_pause_s']:>8.2f} {r['est_total_s']:>8.2f} "
              f"{r['pause_avg_s']:>5.2f} {r['pause_median_s']:>5.2f} "
              f"{r['pause_min_s']:>5.2f} {r['pause_max_s']:>5.2f} "
              f"{r['near_zero_count']:>5}  "
              f"{','.join(f'{k}={v}' for k,v in sorted(r['pause_type_counts'].items()))}")
    print()
    # Show narrative breakdown
    narr = out.get("narrative")
    if narr:
        print(f"Narrative per-segment pauses ({narr['segments']} segments):")
        for s in narr["per_segment"]:
            print(f"  [{s['idx']:03d}] {s['type']:<20} pause={s['pause_s']:.3f}s  "
                  f"chars={s['chars']:>3d}  {s['preview'][:70]}")


if __name__ == "__main__":
    main()
