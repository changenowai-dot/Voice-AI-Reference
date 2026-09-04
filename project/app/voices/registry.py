"""Voice-Profile-System v2 (§2–§5): Native-Language-Logik.

Klassen: native | cross_language | recommended | fallback.

Faktenlage (offizielle Qwen3-TTS-CustomVoice-Presets):
  Vivian/Serena/Uncle_Fu = Chinese, Dylan = Chinese (Beijing),
  Eric = Chinese (Sichuan), Ryan/Aiden = English, Ono_Anna = Japanese,
  Sohee = Korean. Es gibt KEIN natives deutsches Preset — daher darf
  keine dieser Stimmen je als „nativ deutsch“ bezeichnet werden.
  VD-E ist der gesicherte deutsche Produktions-Clone (LOCKED).

Pro Sprache stehen mindestens 3 männliche und 3 weibliche Stimmen
bereit (§5 Zielarchitektur); neue Stimmen sind einfach zusätzliche
voices/*.json mit per_language-Metadaten.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from .. import paths
from ..logging_setup import get_logger
from ..utils import read_json, write_json

log = get_logger("voices")

PROFILES_DIR = paths.ROOT / "voices"

NATIVE_STATUSES = ("native", "cross_language", "recommended", "fallback")

STATUS_LABELS = {
    "native": "NATIV",
    "cross_language": "CROSS-LANGUAGE",
    "recommended": "EMPFOHLEN",
    "fallback": "CROSS-LANGUAGE FALLBACK",
}

_DE = "German"
_EN = "English"

DEFAULT_PROFILES: dict[str, dict] = {
    # ---------------------------------------------------------------- VD-E
    "vd_e": {
        "voice_id": "vd_e",
        "display_name": "VD-E",
        "gender": "male",
        "provider": "qwen3-tts",
        "model": "Qwen3-TTS-12Hz-1.7B-Base (VoiceDesign->Clone)",
        "language_support": [_DE, _EN],
        "native_language": "German (Produktion)",
        "native_status": "recommended",        # gesicherte Hauptstimme
        "category": "narrator",
        "description": "tief, ruhig, seriös – professioneller "
                       "Long-Form-Narrator",
        "backend_mode": "clone",
        "speaker_name": None,
        "reference_path": "cache/voice_refs/VD-E.wav",
        "production_locked": True,
        "recommended": True,
        "default": True,
        "per_language": {
            _DE: {"native_status": "recommended", "rank": 0,
                  "recommended": True, "default": True,
                  "description": "tief, ruhig, seriös"},
            _EN: {"native_status": "cross_language", "rank": 35,
                  "recommended": False, "default": False,
                  "description": "tief, ruhig, seriós"},
        },
        "settings": {"seed": 52001, "variant": "BASE",
                     "cache_version": "q3p-v2-integrity"},
    },
    # ------------------------------------------------------------- Uncle_Fu
    "uncle_fu": {
        "voice_id": "uncle_fu",
        "display_name": "Uncle_Fu",
        "gender": "male",
        "provider": "qwen3-tts",
        "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "language_support": [_DE, _EN],
        "native_language": "Chinese",
        "native_status": "cross_language",
        "category": "narrator",
        "description": "tief, warm, mellow, reif, klassischer Erzähler",
        "backend_mode": "customvoice",
        "speaker_name": "Uncle_Fu",
        "reference_path": None,
        "production_locked": False,
        "recommended": False,
        "default": False,
        "per_language": {
            _DE: {"native_status": "cross_language", "rank": 20,
                  "recommended": False, "default": False,
                  "description": "tief, warm, mellow, reif"},
            _EN: {"native_status": "fallback", "rank": 45,
                  "recommended": False, "default": False,
                  "description": "tief, mellow, reif"},
        },
        "settings": {},
    },
    # ----------------------------------------------------------------- Dylan
    "dylan": {
        "voice_id": "dylan",
        "display_name": "Dylan",
        "gender": "male",
        "provider": "qwen3-tts",
        "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "language_support": [_DE, _EN],
        "native_language": "Chinese (Beijing)",
        "native_status": "cross_language",
        "category": "narrator",
        "description": "klar, natürlich, jünger, ruhiger Erzähler",
        "backend_mode": "customvoice",
        "speaker_name": "Dylan",
        "reference_path": None,
        "production_locked": False,
        "recommended": False,
        "default": False,
        "per_language": {
            _DE: {"native_status": "cross_language", "rank": 30,
                  "recommended": False, "default": False,
                  "description": "klar, natürlich, jünger"},
            _EN: {"native_status": "cross_language", "rank": 40,
                  "recommended": False, "default": False,
                  "description": "klar, natürlich"},
        },
        "settings": {},
    },
    # ------------------------------------------------------------------ Ryan
    "ryan": {
        "voice_id": "ryan",
        "display_name": "Ryan",
        "gender": "male",
        "provider": "qwen3-tts",
        "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "language_support": [_DE, _EN],
        "native_language": "English",
        "native_status": "native",
        "category": "narrator",
        "description": "native English, dynamisch, rhythmisch, klarer "
                       "Long-Form-Narrator",
        "backend_mode": "customvoice",
        "speaker_name": "Ryan",
        "reference_path": None,
        "production_locked": False,
        "recommended": True,
        "default": False,
        "per_language": {
            _EN: {"native_status": "native", "rank": 10,
                  "recommended": True, "default": True,
                  "description": "nativ Englisch, dynamisch, rhythmisch"},
            _DE: {"native_status": "cross_language", "rank": 40,
                  "recommended": False, "default": False,
                  "description": "dynamisch, klar"},
        },
        "settings": {},
    },
    # ----------------------------------------------------------------- Aiden
    "aiden": {
        "voice_id": "aiden",
        "display_name": "Aiden",
        "gender": "male",
        "provider": "qwen3-tts",
        "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "language_support": [_DE, _EN],
        "native_language": "English",
        "native_status": "native",
        "category": "narrator",
        "description": "native English, sonnig, klar, amerikanischer "
                       "Midrange",
        "backend_mode": "customvoice",
        "speaker_name": "Aiden",
        "reference_path": None,
        "production_locked": False,
        "recommended": True,
        "default": False,
        "per_language": {
            _EN: {"native_status": "native", "rank": 20,
                  "recommended": True, "default": False,
                  "description": "nativ Englisch, sonnig, amerikanisch"},
            _DE: {"native_status": "cross_language", "rank": 50,
                  "recommended": False, "default": False,
                  "description": "sonnig, klar"},
        },
        "settings": {},
    },
    # ---------------------------------------------------------------- Serena
    "serena": {
        "voice_id": "serena",
        "display_name": "Serena",
        "gender": "female",
        "provider": "qwen3-tts",
        "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "language_support": [_DE, _EN],
        "native_language": "Chinese",
        "native_status": "cross_language",
        "category": "narrator",
        "description": "warm, sanft, ruhig – Storytelling",
        "backend_mode": "customvoice",
        "speaker_name": "Serena",
        "reference_path": None,
        "production_locked": False,
        "recommended": False,
        "default": False,
        "per_language": {
            _DE: {"native_status": "cross_language", "rank": 20,
                  "recommended": False, "default": False,
                  "description": "warm, sanft, ruhig"},
            _EN: {"native_status": "cross_language", "rank": 20,
                  "recommended": False, "default": False,
                  "note": "best available (kein natives englisch-"
                            "weibliches Preset)",
                  "description": "warm, sanft, ruhig"},
        },
        "settings": {},
    },
    # ---------------------------------------------------------------- Vivian
    "vivian": {
        "voice_id": "vivian",
        "display_name": "Vivian",
        "gender": "female",
        "provider": "qwen3-tts",
        "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "language_support": [_DE, _EN],
        "native_language": "Chinese",
        "native_status": "cross_language",
        "category": "narrator",
        "description": "hell, klar, jung, leicht edgy",
        "backend_mode": "customvoice",
        "speaker_name": "Vivian",
        "reference_path": None,
        "production_locked": False,
        "recommended": False,
        "default": False,
        "per_language": {
            _DE: {"native_status": "cross_language", "rank": 30,
                  "recommended": False, "default": False,
                  "description": "hell, klar, jung, leicht edgy"},
            _EN: {"native_status": "cross_language", "rank": 30,
                  "recommended": False, "default": False,
                  "note": "best available (kein natives englisch-"
                            "weibliches Preset)",
                  "description": "hell, klar, jung"},
        },
        "settings": {},
    },
    # ----------------------------------------------------------------- Sohee
    "sohee": {
        "voice_id": "sohee",
        "display_name": "Sohee",
        "gender": "female",
        "provider": "qwen3-tts",
        "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "language_support": [_DE, _EN],
        "native_language": "Korean",
        "native_status": "cross_language",
        "category": "narrator",
        "description": "warm, emotional, reich, weich",
        "backend_mode": "customvoice",
        "speaker_name": "Sohee",
        "reference_path": None,
        "production_locked": False,
        "recommended": False,
        "default": False,
        "per_language": {
            _DE: {"native_status": "cross_language", "rank": 40,
                  "recommended": False, "default": False,
                  "description": "warm, emotional, reich, weich"},
            _EN: {"native_status": "cross_language", "rank": 40,
                  "recommended": False, "default": False,
                  "note": "best available (kein natives englisch-"
                            "weibliches Preset)",
                  "description": "warm, emotional, reich"},
        },
        "settings": {},
    },
}


@dataclass
class VoiceProfileEntry:
    voice_id: str
    display_name: str
    gender: str
    backend_mode: str                 # clone | customvoice
    speaker_name: str | None
    reference_path: str | None
    production_locked: bool
    recommended: bool
    default: bool
    available: bool | None = None
    availability_note: str = ""
    description: str = ""
    model: str = ""
    language_support: list = field(default_factory=list)
    # v2 (§5 Metadaten)
    native_language: str = ""
    native_status: str = "cross_language"
    category: str = "narrator"
    # sprachspezifische Sicht (via for_language):
    language: str = ""
    description_lang: str = ""
    rank: int = 99
    status_note: str = ""
    recommended_for_language: bool = False
    default_for_language: bool = False

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def ensure_profile_files() -> None:
    """Schreibt fehlende voices/*.json (bestehende bleiben unverändert)."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    for vid, profile in DEFAULT_PROFILES.items():
        f = PROFILES_DIR / f"{vid}.json"
        if not f.exists():
            write_json(f, profile)


class VoiceRegistry:
    def __init__(self):
        ensure_profile_files()
        self._profiles: dict[str, dict] = {}
        for f in sorted(PROFILES_DIR.glob("*.json")):
            data = read_json(f, {}) or {}
            if isinstance(data, dict) and data.get("voice_id"):
                self._profiles[str(data["voice_id"])] = data

    # -- Roh-Zugriff (alle Stimmen, sprachunabhängig) ---------------------
    def entries(self) -> list[VoiceProfileEntry]:
        order = ["vd_e", "uncle_fu", "dylan", "ryan", "aiden",
                 "serena", "vivian", "sohee"]
        ids = [i for i in order if i in self._profiles] + \
              [i for i in self._profiles if i not in order]
        out = []
        for vid in ids:
            d = self._profiles[vid]
            out.append(VoiceProfileEntry(
                voice_id=vid,
                display_name=str(d.get("display_name", vid)),
                gender=str(d.get("gender", "male")),
                backend_mode=str(d.get("backend_mode", "customvoice")),
                speaker_name=d.get("speaker_name"),
                reference_path=d.get("reference_path"),
                production_locked=bool(d.get("production_locked", False)),
                recommended=bool(d.get("recommended", False)),
                default=bool(d.get("default", False)),
                available=d.get("available"),
                availability_note=str(d.get("availability_note", "")),
                description=str(d.get("description", "")),
                model=str(d.get("model", "")),
                language_support=list(d.get("language_support",
                                            [_DE, _EN])),
                native_language=str(d.get("native_language", "")),
                native_status=str(d.get("native_status",
                                        "cross_language")),
                category=str(d.get("category", "narrator")),
            ))
        return out

    def get(self, voice_id: str) -> VoiceProfileEntry | None:
        for e in self.entries():
            if e.voice_id == voice_id:
                return e
        return None

    # -- sprachspezifische Sicht (§2/§6) -----------------------------------
    def for_language(self, entry: VoiceProfileEntry,
                     language: str) -> VoiceProfileEntry:
        """Sprachspezifische Kopie mit native_status/rank/description."""
        d = self._profiles.get(entry.voice_id, {})
        per = (d.get("per_language", {}) or {}).get(language, {}) or {}
        lang_status = str(per.get("native_status",
                                  d.get("native_status",
                                        "cross_language")))
        if lang_status not in NATIVE_STATUSES:
            lang_status = "cross_language"
        return replace(
            entry,
            language=language,
            native_status=lang_status,
            description_lang=str(per.get("description",
                                         d.get("description", ""))),
            rank=int(per.get("rank", 99)),
            status_note=str(per.get("note", "")),
            recommended_for_language=bool(per.get("recommended", False)),
            default_for_language=bool(
                per.get("default", False) or
                (entry.voice_id == "vd_e" and language == _DE)),
        )

    def entries_for_language(self, language: str) -> list[VoiceProfileEntry]:
        """Stimmen einer Sprache, gruppenweise nach Rang sortiert
        (männlich zuerst; VD-E bei Deutsch immer ganz oben, §6)."""
        entries = [self.for_language(e, language)
                   for e in self.entries()
                   if language in e.language_support]
        male = sorted([e for e in entries if e.gender == "male"],
                      key=lambda e: (e.rank, e.display_name))
        female = sorted([e for e in entries if e.gender == "female"],
                        key=lambda e: (e.rank, e.display_name))
        return male + female

    def default_voice_id(self, language: str = _DE) -> str:
        """VD-E bleibt bei Deutsch Standard; sonst beste empfohlene
        Stimme der Sprache (native bevorzugt)."""
        if language == _DE and self.get("vd_e") is not None:
            return "vd_e"
        entries = self.entries_for_language(language)
        for e in entries:
            if e.default_for_language:
                return e.voice_id
        for e in entries:
            if e.recommended_for_language or e.native_status == "native":
                return e.voice_id
        return entries[0].voice_id if entries else "vd_e"

    # -- Verfügbarkeit (§13 des Desktop-Auftrags; kein Fallback) ----------
    def mark_availability(self, voice_id: str, available: bool,
                          note: str = "") -> None:
        f = PROFILES_DIR / f"{voice_id}.json"
        data = read_json(f, {}) or {}
        data["available"] = available
        data["availability_note"] = note if not available else ""
        write_json(f, data)
        if voice_id in self._profiles:
            self._profiles[voice_id].update(
                {"available": available, "availability_note": note})

    def check_customvoice_availability(self, engine) -> dict:
        """Prüft die Sprecherliste des GELADENEN CustomVoice-Modells."""
        supported = None
        try:
            supported = {s.lower() for s in
                         (engine.model.get_supported_speakers() or [])}
        except Exception as e:                        # noqa: BLE001
            log.warning("Sprecherliste nicht abrufbar: %s", e)
        result = {}
        for e in self.entries():
            if e.backend_mode != "customvoice":
                result[e.voice_id] = (True, "")
                continue
            if supported is None:
                result[e.voice_id] = (None, "unbekannt (Modell nicht "
                                            "geladen)")
                continue
            if e.speaker_name and e.speaker_name.lower() in supported:
                result[e.voice_id] = (True, "")
                self.mark_availability(e.voice_id, True)
            else:
                note = (f"Stimme nicht verfügbar: Sprecher "
                        f"\u201e{e.speaker_name}\u201c fehlt im lokalen "
                        f"Modell.")
                self.mark_availability(e.voice_id, False, note)
                result[e.voice_id] = (False, note)
        return result
