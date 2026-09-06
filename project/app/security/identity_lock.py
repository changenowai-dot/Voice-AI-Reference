"""Identity-Lock für die VD-E-Produktionsreferenz (§24, §33).

Prüft SHA-256 von cache/voice_refs/VD-E.wav gegen den erwarteten
Produktions-Hash aus config/production.json. Bei Abweichung:
VD-E wird deaktiviert + Warnung. NIEMALS automatisches Überschreiben
oder „Reparatur“.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .. import paths
from ..logging_setup import get_logger
from ..utils import read_json

log = get_logger("identity")

PRODUCTION_FILE = paths.CONFIG_DIR / "production.json"


@dataclass
class IdentityStatus:
    ok: bool
    level: str            # "ok" | "missing_ref" | "missing_file" | "hash_mismatch" | "no_config"
    expected: str
    actual: str
    path: str
    message: str = ""

    @property
    def vd_e_available(self) -> bool:
        return self.ok


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def load_production() -> dict:
    data = read_json(PRODUCTION_FILE, {}) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _resolve_reference_path(production: dict) -> Path:
    """Ermittelt den Pfad zur VD-E-Referenz.
    
    Priorität:
    1. VOICEOVER_RUNTIME_REF Environment-Variable (explizit gesetzt vom Runner)
    2. reference_path aus production.json Config
    3. Default: cache/voice_refs/VD-E.wav
    """
    import os
    
    # 1. Environment Variable hat höchste Priorität
    env_ref = os.environ.get("VOICEOVER_RUNTIME_REF")
    if env_ref:
        env_path = Path(env_ref)
        if env_path.is_file():
            log.info(f"Verwende VD-E-Referenz aus VOICEOVER_RUNTIME_REF: {env_path}")
            return env_path
        else:
            log.warning(f"VOICEOVER_RUNTIME_REF gesetzt aber Datei nicht gefunden: {env_path}")
    
    # 2. Config-Pfad
    rel = str(production.get("reference_path", "cache/voice_refs/VD-E.wav"))
    if Path(rel).is_absolute():
        return Path(rel)
    return paths.ROOT / rel


def check_identity(production: dict | None = None) -> IdentityStatus:
    """Prüft die VD-E-Referenz. Gibt Status zurück; verändert NICHTS."""
    production = production or load_production()
    expected = str(production.get("reference_sha256", "") or "").upper()
    ref = _resolve_reference_path(production)
    
    if not expected:
        return IdentityStatus(False, "no_config", expected, "", str(ref),
                              "config/production.json enthält keinen "
                              "Referenz-Hash.")
    if not ref.exists():
        return IdentityStatus(False, "missing_ref", expected, "", str(ref),
                              f"VD-E-Referenz fehlt: {ref}. VD-E ist "
                              "deaktiviert. Keine Neuerzeugung (LOCKED).")
    actual = _sha256_file(ref)
    if actual != expected:
        return IdentityStatus(
            False, "hash_mismatch", expected, actual, str(ref),
            "Die geschützte VD-E-Referenz wurde verändert. "
            f"Erwartet {expected[:16]}…, gefunden {actual[:16]}…. "
            "VD-E ist deaktiviert. Kein automatisches Überschreiben.")
    return IdentityStatus(True, "ok", expected, actual, str(ref),
                          "VD-E-Referenz identitätsgesichert (SHA-256 OK).")


def assert_vd_e_usable(production: dict | None = None) -> IdentityStatus:
    """Wirft RuntimeError, wenn VD-E nicht verwendet werden darf (§12)."""
    status = check_identity(production)
    if not status.ok:
        raise RuntimeError(f"VD-E gesperrt: {status.message}")
    return status
