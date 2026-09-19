"""GUI-Stimmzeilen (§6/§7) – pur und damit headless testbar.

Liefert pro Sprache drei Stimmgruppen zurück (VD-E/Custom/Production-Clone),
so dass die GUI sie optisch trennen und Production-Clone-Stimmen nur dann
freischalten kann, wenn die kanonische WAV-Referenz vorhanden ist.
"""
from __future__ import annotations

from ..voices.registry import STATUS_LABELS, VoiceRegistry


def voice_groups(language: str, registry: VoiceRegistry) -> dict[str, list[dict]]:
    """Return ``{"locked": [...], "custom": [...], "clone": [...]}`` groups.

    - ``locked``: VD-E (production-locked German reference; shown with
      its own banner).
    - ``custom``: eingebaute CustomVoice-Sprecher (Ryan/Aiden/Serena/…).
    - ``clone``: Production-Clone-Stimmen (en_male_* / de_male_* /
      en_female_* / de_female_*); available=False wenn die kanonische WAV
      fehlt – GUI deaktiviert sie dann.
    """
    groups = {"locked": [], "custom": [], "clone": []}
    for e in registry.entries_for_language(language):
        status = STATUS_LABELS.get(e.native_status, "")
        if e.voice_id == "vd_e" and language == "German":
            status = "GESPERRTE PRODUKTIONSSTIMME"
        elif e.recommended_for_language and e.native_status == "native":
            status = "NATIV · EMPFOHLEN"
        if e.available is False and e.backend_mode == "clone":
            status = "NICHT VERFÜGBAR – Referenz fehlt"
        row = {
            "voice_id": e.voice_id,
            "label": f"{e.display_name} ({e.description_lang})",
            "status": status,
            "gender": e.gender,
            "default": e.default_for_language,
            "available": e.available,
            "availability_note": e.availability_note,
            "backend_mode": e.backend_mode,
        }
        if e.voice_id == "vd_e":
            groups["locked"].append(row)
        elif e.backend_mode == "clone":
            groups["clone"].append(row)
        else:
            groups["custom"].append(row)
    return groups


def voice_rows(language: str, registry: VoiceRegistry) -> list[dict]:
    """Flat list for backwards compatibility with existing GUI code."""
    g = voice_groups(language, registry)
    return g["locked"] + g["custom"] + g["clone"]


def default_voice(language: str, registry: VoiceRegistry) -> str:
    return registry.default_voice_id(language)

