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
    tier = _tier_for(registry._profiles.get(e.voice_id, {})) if \
        e.voice_id != "vd_e" else "ACTIVE"
    tier_label = _TIER_LABEL.get(tier, tier)
    avail_note = ""
    # VD-E hat IMMER den "GESPERRTE PRODUKTIONSSTIMME"-Status, unabhängig
    # davon, ob der kanonische WAV-Link in cache/voice_refs/ gerade
    # existiert (die Produktion benutzt VD-E_GOLDEN_REFERENCE direkt).
    if e.voice_id == "vd_e":
        status = "GESPERRTE PRODUKTIONSSTIMME"
        avail_note = ("Identitätsgesichert durch SHA-256-Prüfung gegen "
                      "VD-E_GOLDEN_REFERENCE/VD-E.wav.")
    elif e.recommended_for_language and e.native_status == "native":
        status = "NATIV · EMPFOHLEN"
    else:
        if e.backend_mode == "clone":
            if e.available is False:
                status = "NICHT VERFÜGBAR – Referenz fehlt"
                avail_note = (e.availability_note or
                              "Kanonische WAV-Referenz in cache/voice_refs/ "
                              "fehlt; Stimme zuerst mit tools/"
                              "materialize_references.py materialisieren.")
            elif tier in ("UNASSESSED", "REJECTED"):
                status = f"{tier_label} – Referenz vorhanden, Stimme nicht freigegeben"
                avail_note = (
                    "Die Referenz ist vorhanden, aber die Stimme wurde "
                    "noch nicht in den ACTIVE-Bestand übernommen. Wählen "
                    "Sie sie gezielt über die voice_id in Aufrufskripten an, "
                    "bis eine menschliche Freigabe erfolgt ist.")
            elif tier == "BACKUPS":
                status = f"{tier_label} – vorhanden"
    return {
        "voice_id": e.voice_id,
        "label": f"{e.display_name} ({e.description_lang})",
        "status": status,
        "gender": e.gender,
        "default": e.default_for_language,
        # VD-E: immer als "verfügbar" anzeigen (wird über den
        # Golden-Reference-Pfad geladen, nicht über cache/voice_refs/).
        # Sonst: verfügbar, wenn die Registry available=True sagt UND
        # der Tier die Stimme nicht zurückgewiesen hat.
        "available": (True if e.voice_id == "vd_e"
                      else (e.available if tier not in ("REJECTED", "UNASSESSED")
                            else (e.available if e.available else False))),
        # REJECTED/UNASSESSED mit vorhandener Referenz werden als
        # NICHT im GUI auswählbar markiert (keine versehentliche Nutzung),
        # aber sichtbar gelassen mit der Statuszeile.
        # VD-E ist IMMER auswählbar (geschützte Produktionsstimme).
        "selectable": (True if e.voice_id == "vd_e"
                       else bool(e.available and tier not in ("REJECTED",
                                                              "UNASSESSED"))),
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
    # VD-E ist die deutsche GESPERRTE PRODUKTIONSSTIMME. Sie wird in
    # BEIDEN Sprachansichten als "locked" oben angezeigt, ist aber nur
    # in German AUSWÄHLBAR – in English bleibt die Radio deaktiviert,
    # damit der Benutzer nicht versehentlich eine deutsche Stimme für
    # englischen Text auswählt.
    vd_e_entry = registry.get("vd_e")
    if vd_e_entry is not None:
        vd_row = _build_row(vd_e_entry, registry, language)
        if language != "German":
            vd_row["selectable"] = False
            vd_row["status"] = "GESPERRTE PRODUKTIONSSTIMME (nur Deutsch)"
            vd_row["availability_note"] = (
                "VD-E ist eine deutsche Referenzstimme und steht für "
                "englischen Text nicht zur Verfügung.")
        groups["locked"].append(vd_row)
    for e in registry.entries_for_language(language):
        if e.voice_id == "vd_e":
            continue                     # haben wir schon als locked
        row = _build_row(e, registry, language)
        if e.backend_mode == "customvoice":
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

