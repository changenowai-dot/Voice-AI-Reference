"""GUI-Stimmzeilen (§6/§7) – pur und damit headless testbar.

Liefert pro Sprache die anzuzeigenden Stimmenzeilen:
Gruppierung nach Geschlecht, Sortierung nach Rang (VD-E bei Deutsch
ganz oben), Inline-Beschreibung „Name (Charakter)“ und ein separates
Status-Label (Native-Status ≠ Klangcharakter).
"""
from __future__ import annotations

from ..voices.registry import STATUS_LABELS, VoiceRegistry


def voice_rows(language: str, registry: VoiceRegistry) -> list[dict]:
    """Zeilen für die GUI: [{voice_id, label, status, gender, group}…].

    label   = "VD-E (tief, ruhig, seriós)"  (§7-Format)
    status  = "EMPFOHLEN · Standard" | "NATIV" | "CROSS-LANGUAGE" | …
    """
    rows = []
    for e in registry.entries_for_language(language):
        status = STATUS_LABELS.get(e.native_status, "")
        if e.voice_id == "vd_e" and language == "German":
            status = "EMPFOHLEN · Standard"
        elif e.recommended_for_language and e.native_status == "native":
            status = "NATIV · EMPFOHLEN"
        rows.append({
            "voice_id": e.voice_id,
            "label": f"{e.display_name} ({e.description_lang})",
            "status": status,
            "gender": e.gender,
            "default": e.default_for_language,
            "available": e.available,
        })
    return rows


def default_voice(language: str, registry: VoiceRegistry) -> str:
    return registry.default_voice_id(language)
