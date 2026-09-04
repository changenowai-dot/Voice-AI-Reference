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


def check_identity(production: dict | None = None) -> IdentityStatus:
    """Prüft die VD-E-Referenz. Gibt Status zurück; verändert NICHTS."""
    production = production or load_production()
    expected = str(production.get("reference_sha256", "") or "").upper()
    rel = str(production.get("reference_path",
                             "cache/voice_refs/VD-E.wav"))
    ref = (paths.ROOT / rel) if not Path(rel).is_absolute() else Path(rel)
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
