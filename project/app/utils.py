"""Kleine Hilfsfunktionen (JSON, Hashing, Zahlen)."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict


def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any, indent: int = 2) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent),
                   encoding="utf-8")
    tmp.replace(p)


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def linear_map(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    if x1 == x0:
        return y0
    t = clamp((x - x0) / (x1 - x0), 0.0, 1.0)
    return y0 + t * (y1 - y0)


def format_duration(seconds: float) -> str:
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{sec:02d}"
    return f"{m:d}:{sec:02d}"


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def stable_hash(data: Dict[str, Any]) -> str:
    """Deterministischer Hash über ein verschachteltes Dict (für Cache-Keys)."""
    return sha256_str(json.dumps(data, ensure_ascii=False, sort_keys=True))


def is_finite_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(v)
