"""GUI-Stimmzeilen (§6/§7) – pur und damit headless testbar.

Liefert pro Sprache vier Stimmgruppen zurück (VD-E / Custom /
Production-Clone / Weitere Archiv-Kandidaten), so dass die GUI sie
optisch trennen und Production-Clone-Stimmen nur dann freischalten
kann, wenn die kanonische WAV-Referenz vorhanden ist.

WICHTIG: auch Stimmen, deren Referenz noch nicht materialisiert ist
oder deren Tier REJECTED/UNASSESSED ist, werden in der GUI gezeigt
– allerdings mit klarer Status-Kennzeichnung und (bei fehlender
Referenz) deaktiviert. Dadurch sieht der Benutzer, welche Stimmen im
Projekt vorhanden sind; Stimmen verschwinden nicht stillschweigend.
"""
from __future__ import annotations

from ..voices.registry import (STATUS_LABELS, VoiceRegistry,
                               tier_for as _tier_for)

# Tier-Label (Deutsch, GUI-Anzeige)
_TIER_LABEL = {
    "ACTIVE": "PRODUKTION",
    "BACKUPS": "ARCHIV",
    "UNASSESSED": "KANDIDAT (unbewertet)",
    "REJECTED": "ZURÜCKGEWIESEN",
}


def _build_row(e, registry, language):
    status = STATUS_LABELS.get(e.native_status, "")
    if e.voice_id == "vd_e" and language == "German":
        status = "GESPERRTE PRODUKTIONSSTIMME"
    elif e.recommended_for_language and e.native_status == "native":
        status = "NATIV · EMPFOHLEN"
    # Tier-Kennzeichnung (außer VD-E)
    tier = _tier_for(registry._profiles.get(e.voice_id, {})) if \
        e.voice_id != "vd_e" else "ACTIVE"
    tier_label = _TIER_LABEL.get(tier, tier)
    avail_note = ""
    if e.backend_mode == "clone":
        if e.available is False:
            status = "NICHT VERFÜGBAR – Referenz fehlt"
            avail_note = (e.availability_note or
                          "Kanonische WAV-Referenz in cache/voice_refs/ "
                          "fehlt; Stimme zuerst mit tools/"
                          "materialize_references.py materialisieren.")
        elif tier in ("UNASSESSED", "REJECTED"):
            # Referenz da, aber menschlich noch nicht freigegeben
            status = f"{tier_label} – Referenz vorhanden, Stimme nicht freigegeben"
            avail_note = (
                "Die Referenz ist vorhanden, aber die Stimme wurde "
                "noch nicht in den ACTIVE-Bestand übernommen. Wählen "
                "Sie sie gezielt über die voice_id in Aufrufskripten an, "
                "bis eine menschliche Freigabe erfolgt ist.")
        elif tier == "BACKUPS":
            status = f"{tier_label} – vorhanden"
    # VD-E: keep its own label
    if e.voice_id == "vd_e":
        pass
    return {
        "voice_id": e.voice_id,
        "label": f"{e.display_name} ({e.description_lang})",
        "status": status,
        "gender": e.gender,
        "default": e.default_for_language,
        "available": e.available if tier not in ("REJECTED", "UNASSESSED")
                        else (e.available if e.available else False),
        # REJECTED/UNASSESSED mit vorhandener Referenz werden als
        # NICHT im GUI auswählbar markiert (keine versehentliche Nutzung),
        # aber sichtbar gelassen mit der Statuszeile.
        "selectable": bool(e.available and tier not in ("REJECTED",
                                                        "UNASSESSED"))
                      or e.voice_id == "vd_e",
        "tier": tier,
        "availability_note": avail_note or e.availability_note,
        "backend_mode": e.backend_mode,
    }


def voice_groups(language: str, registry: VoiceRegistry) -> dict[str, list[dict]]:
    """Return ``{"locked": [...], "custom": [...], "clone": [...], "candidates": [...]}``.

    - ``locked``     : VD-E (production-locked German reference).
    - ``custom``     : eingebaute CustomVoice-Sprecher (Ryan/Aiden/…).
    - ``clone``      : ACTIVE + BACKUPS Production-Clone-Stimmen;
                       nicht verfügbare sind deaktiviert.
    - ``candidates``: UNASSESSED- und REJECTED-Stimmen (Referenz
                       vorhanden oder nicht) – sichtbar, aber nicht
                       auswählbar. Die GUI kann sie in einer separaten
                       Gruppe mit Warnhinweis anzeigen.
    """
    groups = {"locked": [], "custom": [], "clone": [], "candidates": []}
    for e in registry.entries_for_language(language):
        row = _build_row(e, registry, language)
        if e.voice_id == "vd_e":
            groups["locked"].append(row)
        elif e.backend_mode == "customvoice":
            groups["custom"].append(row)
        elif row["tier"] in ("ACTIVE", "BACKUPS"):
            groups["clone"].append(row)
        else:
            groups["candidates"].append(row)
    return groups


def voice_rows(language: str, registry: VoiceRegistry) -> list[dict]:
    """Flat list for backwards compatibility with existing GUI code."""
    g = voice_groups(language, registry)
    return g["locked"] + g["custom"] + g["clone"] + g["candidates"]


def default_voice(language: str, registry: VoiceRegistry) -> str:
    return registry.default_voice_id(language)

