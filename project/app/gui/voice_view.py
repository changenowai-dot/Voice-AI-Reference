"""GUI-Stimmzeilen — technische Verfügbarkeit vs. Tier-Status sauber
getrennt.

Jede Stimme in der GUI erhält:

- ``technically_available``: ``True`` wenn die Runtime die Stimme laden
  kann (CustomVoice immer, Clone wenn ein gültiges Bundle vorhanden
  ist, VD-E immer).
- ``selectable``: ``technically_available AND tier != REJECTED``
  (REJECTED bleibt dauerhaft nicht auswählbar; ARCHIV/KANDIDAT sind
  auswählbar sobald ein gültiges Bundle da ist).
- ``status_label``: Klarer Hinweis wie "[VERFÜGBAR] PRODUKTION" /
  "[VERFÜGBAR] ARCHIV" / "[VERFÜGBAR] KANDIDAT" / "[NICHT VERFÜGBAR]
  Referenz fehlt" / "GESPERRTE PRODUKTIONSSTIMME".

Gruppen:
- ``locked``       : VD-E (production-locked German reference).
- ``custom``       : eingebaute CustomVoice-Sprecher (Ryan/Aiden/…).
- ``clone``        : ACTIVE + BACKUPS + UNASSESSED mit validem Bundle
                     (auswählbar) oder ohne (deaktiviert).
- ``candidates``   : REJECTED und ACTIVE/BACKUPS/UNASSESSED ohne
                     Bundle – sichtbar, aber nicht auswählbar, mit
                     eindeutiger Ursache.

Stimmen verschwinden niemals stillschweigend.
"""
from __future__ import annotations

from ..voices.registry import (STATUS_LABELS, VoiceRegistry,
                               tier_for as _tier_for)

# Tier-Label (Deutsch, GUI-Anzeige)
_TIER_LABEL = {
    "ACTIVE":     "PRODUKTION",
    "BACKUPS":    "ARCHIV",
    "UNASSESSED": "KANDIDAT",
    "REJECTED":   "ZURÜCKGEWIESEN",
}

_AVAIL_PREFIX = "VERFÜGBAR"
_UNAVAIL_PREFIX = "NICHT VERFÜGBAR"


def _build_row(e, registry, language):
    tier = _tier_for(registry._profiles.get(e.voice_id, {})) if \
        e.voice_id != "vd_e" else "ACTIVE"
    tier_label = _TIER_LABEL.get(tier, tier)

    # --- 1. Technische Verfügbarkeit ----------------------------------
    if e.voice_id == "vd_e":
        technically_available = True
        locked = True
        reason_missing = ""
    elif e.backend_mode == "customvoice":
        technically_available = True
        locked = False
        reason_missing = ""
    else:  # clone
        locked = False
        if e.available:
            technically_available = True
            reason_missing = ""
        else:
            technically_available = False
            reason_missing = (e.availability_note
                              or "Kanonisches Referenz-Bundle "
                                 "(WAV + Manifest) fehlt oder ist "
                                 "ungültig.")

    # --- 2. Selektierbarkeit (P4) -------------------------------------
    # VD-E in German selektierbar, sonst nur locked; Custom und alle
    # verfügbaren Clone (auch ARCHIV/KANDIDAT) sind auswählbar.
    # REJECTED bleibt dauerhaft nicht auswählbar (menschlich abgelehnt).
    if e.voice_id == "vd_e":
        selectable = (language == "German")
    elif tier == "REJECTED":
        selectable = False
    else:
        selectable = technically_available

    # --- 3. Status-Text ------------------------------------------------
    if e.voice_id == "vd_e":
        if language == "German":
            status = "GESPERRTE PRODUKTIONSSTIMME"
        else:
            status = "GESPERRTE PRODUKTIONSSTIMME (nur Deutsch)"
        avail_note = ("Identitätsgesichert durch SHA-256-Prüfung gegen "
                      "VD-E_GOLDEN_REFERENCE/VD-E.wav.")
    elif e.backend_mode == "customvoice":
        status = f"[{_AVAIL_PREFIX}] {tier_label} – eingebauter Qwen-Sprecher"
        avail_note = ""
        if e.recommended_for_language and e.native_status == "native":
            status = f"[{_AVAIL_PREFIX}] NATIV · EMPFOHLEN · {tier_label}"
    else:  # clone
        if technically_available:
            # Nativer Favorit extra markieren
            if e.recommended_for_language and e.native_status == "native" \
                    and tier == "ACTIVE":
                status = f"[{_AVAIL_PREFIX}] NATIV · EMPFOHLEN · {tier_label}"
            else:
                status = f"[{_AVAIL_PREFIX}] {tier_label}"
            avail_note = ""
        else:
            status = f"[{_UNAVAIL_PREFIX}] {tier_label} – Referenz fehlt oder ungültig"
            avail_note = reason_missing

    return {
        "voice_id": e.voice_id,
        "label": f"{e.display_name} ({e.description_lang})",
        "status": status,
        "gender": e.gender,
        "default": e.default_for_language,
        "available": technically_available,
        "selectable": bool(selectable),
        "tier": tier,
        "availability_note": avail_note,
        "backend_mode": e.backend_mode,
        "locked": bool(locked),
    }


def voice_groups(language: str, registry: VoiceRegistry) -> dict[str, list[dict]]:
    """Return ``{"locked", "custom", "clone", "candidates"}``."""
    groups = {"locked": [], "custom": [], "clone": [], "candidates": []}

    # VD-E (locked)
    vd_e_entry = registry.get("vd_e")
    if vd_e_entry is not None:
        groups["locked"].append(_build_row(vd_e_entry, registry, language))

    for e in registry.entries_for_language(language):
        if e.voice_id == "vd_e":
            continue
        row = _build_row(e, registry, language)
        if e.backend_mode == "customvoice":
            groups["custom"].append(row)
            continue
        # Clone-Stimmen:
        #  - REJECTED -> immer candidates (nie auswählbar).
        #  - ohne gültiges Bundle -> candidates (nicht auswählbar,
        #    mit Grund).
        #  - mit gültigem Bundle (egal ob ACTIVE/BACKUPS/UNASSESSED) ->
        #    clone (auswählbar), das Label zeigt den Tier-Status.
        if row["tier"] == "REJECTED":
            groups["candidates"].append(row)
        elif not row["available"]:
            groups["candidates"].append(row)
        else:
            groups["clone"].append(row)
    return groups


def voice_rows(language: str, registry: VoiceRegistry) -> list[dict]:
    """Flat list für Kompatibilität."""
    g = voice_groups(language, registry)
    return g["locked"] + g["custom"] + g["clone"] + g["candidates"]


def default_voice(language: str, registry: VoiceRegistry) -> str:
    return registry.default_voice_id(language)
