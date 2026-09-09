"""Konfiguration: Laden, Zusammenführen, Abspeichern.

Standardwerte sind so gewählt, dass sie ohne manuelle Einstellung die bestmögliche
Qualität für den Hauptanwendungsfall (tiefe, ruhige Dokumentation, Deutsch)
liefern (Anforderung 29).
"""
from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from typing import Any, Dict

from . import paths

_LOCK = threading.RLock()

# ---------------------------------------------------------------------------
# Standardkonfiguration
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: Dict[str, Any] = {
    "ui": {
        "language": "de",                 # Oberflächensprache der App
        "port": 8750,
        "open_browser": True,
    },
    # Sprache des zu erzeugenden Voice-Overs (vom Nutzer gewählt, wird nie
    # automatisch überschrieben – Anforderung 8)
    "language": "German",                 # "German" | "English"
    "voice_profile": "default_best_narrator",
    "preset": "deep_documentary",
    # Phase 1 – deutsche Qualitätsoptimierung
    "german": {
        # gewählte Instruct-Variante (A/B-Benchmark auf Zielhardware)
        "instruct_variant": "de_doc_native",
        "min_german_score": 75.0,
        "best_speaker": None,            # vom Deutsch-Stimmen-Benchmark gesetzt
        # Phase 2: "customvoice" (Standard) | "voicedesign" (Clone-Stimme
        # aus Phase-2-Blindauswahl; setzt voicedesign.candidate_id)
        "engine_mode": "customvoice",
        "voicedesign": None,             # {"candidate_id": "VD-B", "description": …}
        # Phase 3 (§20): Fachwort-Germanisierung (Theorie, Quantentheorie,
        # Kybalion …) – TTS-intern, Originaltext bleibt unverändert
        "tech_germanization": True,
        # Phase 3 (§22): semantisch motivierte Sampling-Variation.
        # enabled=None -> automatisch für Clone-Stimmen (kein Instruct
        # verfügbar), aus für CustomVoice (Instruct übernimmt die Variation)
        "variation": {"enabled": None, "strength": "subtle"},
    },
    "voices": {
        # Profil -> Qwen-Speaker (vom Deutsch-Stimmen-Benchmark gesetzt;
        # leer = Standardzuordnung aus app/voices/profiles.py)
        "speaker_map": {},
    },
    "speed": 1.0,                         # 0.80 – 1.20 (Anforderung 24)
    "emotion": "AUTO",                    # AUTO | neutral | calm | warm | serious |
                                          #   somber | mysterious | tense | hopeful
    "intensity": "AUTO",                  # AUTO | 1..5
    "volume_db": 0.0,                     # manuelle Pegelanpassung vor dem Mastering
    "pause_style": "auto",                # auto | tight | relaxed
    # Phase 2 (§10): Pausenstrategie – classic | semantic | flow
    "pause_strategy": "classic",
    "advanced": {
        # Engine
        "prefer_model_size": "auto",      # auto | 1.7B | 0.6B
        "device": "auto",                 # auto | cuda | cpu
        "batch_size": "auto",             # auto | 1..4
        "max_workers": 1,                 # TTS-Aufrufe standardmäßig sequenziell
        # Segmentierung
        "segment_target_chars": 420,      # vom System-Benchmark optimierbar
        "segment_max_chars": 700,
        "segment_min_chars": 120,
        # Attention-Implementierung: sdpa = stabil (Default).
        # flash_attention_2 optional experimentell (§33: nicht automatisch
        # installiert – Windows-Build-Risiko dokumentiert)
        "attn_implementation": "sdpa",
        # Sampling (Anforderung 49; vom Benchmark verfeinerbar)
        "do_sample": True,
        "temperature": 0.7,
        "top_k": 50,
        "top_p": 0.90,
        "repetition_penalty": 1.05,
        # Quality Control
        "qc_enabled": True,
        "qc_min_score": 78,               # darunter: Regeneration
        "qc_max_attempts": 3,             # Anforderung 45
        # Audio
        "target_lufs": -14.0,             # YouTube-Master (Anforderung 41)
        "true_peak_dbtp": -1.5,
        "wav_bit_depth": 24,
        "wav_sample_rate": 48000,
        "mp3_bitrate": "320k",
        # Cache
        "cache_enabled": True,
        # Logging-Privatsphäre: Texte niemals vollständig loggen (Anf. 68)
        "log_text_content": False,
    },
}

# Zielparameter für YouTube zentral konfigurierbar (Anforderung 41)
YOUTUBE_MASTER_DEFAULTS = {
    "target_lufs": -14.0,
    "true_peak_dbtp": -1.5,
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config() -> Dict[str, Any]:
    """Lädt config/config.json, ergänzt fehlende Schlüssel aus den Defaults."""
    with _LOCK:
        data: Dict[str, Any] = {}
        if paths.CONFIG_FILE.exists():
            try:
                data = json.loads(paths.CONFIG_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
        cfg = _deep_merge(DEFAULT_CONFIG, data)
        return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    with _LOCK:
        paths.ensure_directories()
        paths.CONFIG_FILE.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def update_config(partial: Dict[str, Any]) -> Dict[str, Any]:
    cfg = load_config()
    cfg = _deep_merge(cfg, partial)
    save_config(cfg)
    return cfg


def reset_config() -> Dict[str, Any]:
    save_config(copy.deepcopy(DEFAULT_CONFIG))
    return copy.deepcopy(DEFAULT_CONFIG)


def write_default_config_if_missing() -> None:
    if not paths.CONFIG_FILE.exists():
        save_config(copy.deepcopy(DEFAULT_CONFIG))


def get(cfg: Dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    node: Any = cfg
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def ensure_file_from_template(path: Path, template: Dict[str, Any]) -> Dict[str, Any]:
    """Schreibt eine JSON-Datei, falls sie fehlt; gibt Inhalt zurück."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(template, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return copy.deepcopy(template)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return copy.deepcopy(template)
