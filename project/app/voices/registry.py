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

# === 4-Tier Library (2026-09-09) — ACTIVE / BACKUPS / UNASSESSED / REJECTED ===
# ACTIVE: human-selected/confirmed shortlist/favorite/preserved — in Haupt-GUI, Favoriten, Standard-Auswahl (nur bestätigte)
# BACKUPS: good_archived + test_voice* als archivierter Backup-Bereich (z. B. voice-34) — nicht als Favorit
# UNASSESSED: new_candidate / recovered / unassessed — z. B. german_recovery 7 (voice-35..41) — NICHT als ACTIVE, nur Kandidaten-Pool, Human Rank blank
# REJECTED: rejected_human — niemals in ACTIVE-UI/Shortlist/Favoriten (nur Historie, Reproduktion)
ACTIVE_STATUSES = {"locked_human_favorite", "saved_human_shortlist", "preserved_female_calm", "test_voice_preserved", "active"}
BACKUP_STATUSES = {"good_archived", "test_voice", "test_voice_premium_10", "archived", "backup"}
REJECTED_STATUSES = {"rejected_human", "rejected"}
UNASSESSED_STATUSES = {"new_candidate_german_recovery", "new_candidate", "recovered", "unassessed", "candidate"}
# Any status containing these substrings also counts: we also inspect human_selected/production_candidate flags

def tier_for(data: dict) -> str:
    """Bestimme Tier aus status + flags (ehrlich, kein Raten)."""
    st = str(data.get("status","") or "")
    # VD-E golden locked is always ACTIVE regardless of status field
    if data.get("voice_id")=="vd_e" or data.get("production_locked") is True and data.get("voice_id")=="vd_e":
        return "ACTIVE"
    if data.get("production_locked") is True and "rejected" not in st:
        # Locked favorites (vd_e, voice-09, voice-12) are always ACTIVE
        return "ACTIVE"
    # explicit
    if st in REJECTED_STATUSES or "rejected" in st:
        return "REJECTED"
    # UNASSESSED: neue/recovered Kandidaten — NICHT ACTIVE, nicht BACKUP, nicht REJECTED (vgl. §5 FINAL CORRECTION)
    if st in UNASSESSED_STATUSES or st.startswith("new_candidate") or st.startswith("recovered") or st == "unassessed":
        return "UNASSESSED"
    if st in ACTIVE_STATUSES or st in ("saved_human_shortlist","locked_human_favorite"):
        return "ACTIVE"
    if st in BACKUP_STATUSES:
        return "BACKUPS"
    # fallback via flags: human_selected+production_candidate == ACTIVE shortlist, good_archived == BACKUPS even if human_selected
    if data.get("human_selected") is True and data.get("production_candidate") is True:
        return "ACTIVE"
    if str(data.get("status","")).endswith("_archived"):
        return "BACKUPS"
    # default: treat unknown as BACKUPS (safe, not ACTIVE)
    return "BACKUPS"


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
    # ================================================================
    # VIER NEUE ENGLISCHE TESTSTIMMEN – VoiceDesign->Clone (2026-09)
    # DESIGN: muttersprachliches Englisch, dokumentarisch, ruhig,
    #         erwachsen, langfristig angenehm – Long-Form narrators
    # STATUS: TEST voices – VD-E bleibt locked production
    # ================================================================
    "en_male_deep_01": {
        "voice_id": "en_male_deep_01",
        "display_name": "EN Male Deep 01",
        "gender": "male",
        "provider": "qwen3-tts",
        "model": "Qwen3-TTS-12Hz-1.7B-Base (VoiceDesign->Clone)",
        "language_support": [_DE, _EN],
        "native_language": "English",
        "native_status": "native",
        "category": "narrator",
        "description": "deep, authoritative, investigative documentary – English native",
        "backend_mode": "clone",
        "speaker_name": None,
        "reference_path": "cache/voice_refs/en_male_deep_01.wav",
        "production_locked": False,
        "recommended": False,
        "default": False,
        "intended_use": "long-form documentary, investigative, history, science",
        "status": "test_voice",
        "register": "deep",
        "style": "investigative_documentary",
        "per_language": {
            _EN: {"native_status": "native", "rank": 11,
                  "recommended": True, "default": False,
                  "description": "deep, authoritative, investigative – darkest, most weighty"},
            _DE: {"native_status": "cross_language", "rank": 60,
                  "recommended": False, "default": False,
                  "description": "deep, authoritative – English design (cross-language)"},
        },
        "settings": {"seed": 52011, "variant": "EN_DEEP_01", "cache_version": "q3p-v2-integrity",
                     "language": "English", "engine": "VoiceCloneEngine", "backend": "clone",
                     "model_pool": "base", "reference_text": "VOICEDESIGN_REF_TEXT_EN"},
    },
    "en_male_deep_02": {
        "voice_id": "en_male_deep_02",
        "display_name": "EN Male Deep 02",
        "gender": "male",
        "provider": "qwen3-tts",
        "model": "Qwen3-TTS-12Hz-1.7B-Base (VoiceDesign->Clone)",
        "language_support": [_DE, _EN],
        "native_language": "English",
        "native_status": "native",
        "category": "narrator",
        "description": "deep, warm, conversational storyteller – English native",
        "backend_mode": "clone",
        "speaker_name": None,
        "reference_path": "cache/voice_refs/en_male_deep_02.wav",
        "production_locked": False,
        "recommended": False,
        "default": False,
        "intended_use": "long-form storytelling, science, psychology, history",
        "status": "test_voice",
        "register": "deep_warm",
        "style": "warm_storyteller",
        "per_language": {
            _EN: {"native_status": "native", "rank": 12,
                  "recommended": True, "default": False,
                  "description": "deep, warm, conversational – storyteller, inviting clarity"},
            _DE: {"native_status": "cross_language", "rank": 61,
                  "recommended": False, "default": False,
                  "description": "deep, warm – English design (cross-language)"},
        },
        "settings": {"seed": 52012, "variant": "EN_DEEP_02", "cache_version": "q3p-v2-integrity",
                     "language": "English", "engine": "VoiceCloneEngine", "backend": "clone"},
    },
    "en_female_calm_01": {
        "voice_id": "en_female_calm_01",
        "display_name": "EN Female Calm 01",
        "gender": "female",
        "provider": "qwen3-tts",
        "model": "Qwen3-TTS-12Hz-1.7B-Base (VoiceDesign->Clone)",
        "language_support": [_DE, _EN],
        "native_language": "English",
        "native_status": "native",
        "category": "narrator",
        "description": "calm, warm, documentary – English native, low register",
        "backend_mode": "clone",
        "speaker_name": None,
        "reference_path": "cache/voice_refs/en_female_calm_01.wav",
        "production_locked": False,
        "recommended": False,
        "default": False,
        "intended_use": "long-form documentary, psychology, philosophy, science",
        "status": "test_voice",
        "register": "warm_low",
        "style": "calm_documentary",
        "per_language": {
            _EN: {"native_status": "native", "rank": 21,
                  "recommended": True, "default": False,
                  "description": "calm, warm, low register – velvet documentary, trustworthy"},
            _DE: {"native_status": "cross_language", "rank": 62,
                  "recommended": False, "default": False,
                  "description": "calm, warm – English design (cross-language)"},
        },
        "settings": {"seed": 52021, "variant": "EN_CALM_01", "cache_version": "q3p-v2-integrity",
                     "language": "English", "engine": "VoiceCloneEngine", "backend": "clone"},
    },
    "en_male_calm_deep_01": {
        "voice_id": "en_male_calm_deep_01",
        "display_name": "EN Male Calm Deep 01",
        "gender": "male",
        "provider": "qwen3-tts",
        "model": "Qwen3-TTS-12Hz-1.7B-Base (VoiceDesign->Clone)",
        "language_support": [_DE, _EN],
        "native_language": "English",
        "native_status": "native",
        "category": "narrator",
        "description": "calm deep – low, warm, controlled, mature, authoritative, highly intelligible",
        "backend_mode": "clone",
        "speaker_name": None,
        "reference_path": "cache/voice_refs/en_male_calm_deep_01.wav",
        "production_locked": False,
        "recommended": False,
        "default": False,
        "intended_use": "long-form documentary, history, science, philosophy – calm deep narration",
        "status": "test_voice",
        "register": "calm_deep",
        "style": "calm_deep_authoritative",
        "per_language": {
            _EN: {"native_status": "native", "rank": 13,
                  "recommended": True, "default": False,
                  "description": "calm deep – low, warm, controlled, mature, highly intelligible, long-form pleasant"},
            _DE: {"native_status": "cross_language", "rank": 64,
                  "recommended": False, "default": False,
                  "description": "calm deep – English design (cross-language)"},
        },
        "settings": {"seed": 52013, "variant": "EN_CALM_DEEP_01", "cache_version": "q3p-v2-integrity",
                     "language": "English", "engine": "VoiceCloneEngine", "backend": "clone"},
    },
    "en_male_warm_storytelling_authoritative_01": {
        "voice_id": "en_male_warm_storytelling_authoritative_01",
        "display_name": "EN Male Warm Storytelling Authoritative 01",
        "gender": "male",
        "provider": "qwen3-tts",
        "model": "Qwen3-TTS-12Hz-1.7B-Base (VoiceDesign->Clone)",
        "language_support": [_DE, _EN],
        "native_language": "English",
        "native_status": "native",
        "category": "narrator",
        "description": "warm storytelling authoritative – English native long-form",
        "backend_mode": "clone",
        "speaker_name": None,
        "reference_path": "cache/voice_refs/en_male_warm_storytelling_authoritative_01.wav",
        "production_locked": False,
        "recommended": False,
        "default": False,
        "intended_use": "long-form documentary, history, science, psychology – warm storytelling with authority",
        "status": "test_voice",
        "register": "warm_storytelling",
        "style": "warm_storytelling_authoritative",
        "per_language": {
            _EN: {"native_status": "native", "rank": 14,
                  "recommended": True, "default": False,
                  "description": "warm storytelling authoritative – natural phrasing, subtle warmth, human rhythm, professional"},
            _DE: {"native_status": "cross_language", "rank": 65,
                  "recommended": False, "default": False,
                  "description": "warm storytelling – English design (cross-language)"},
        },
        "settings": {"seed": 52014, "variant": "EN_WARM_STORY_01", "cache_version": "q3p-v2-integrity",
                     "language": "English", "engine": "VoiceCloneEngine", "backend": "clone"},
    },
    "en_female_calm_02": {
        "voice_id": "en_female_calm_02",
        "display_name": "EN Female Calm 02",
        "gender": "female",
        "provider": "qwen3-tts",
        "model": "Qwen3-TTS-12Hz-1.7B-Base (VoiceDesign->Clone)",
        "language_support": [_DE, _EN],
        "native_language": "English",
        "native_status": "native",
        "category": "narrator",
        "description": "calm, bright, articulate – English native, expressive",
        "backend_mode": "clone",
        "speaker_name": None,
        "reference_path": "cache/voice_refs/en_female_calm_02.wav",
        "production_locked": False,
        "recommended": False,
        "default": False,
        "intended_use": "long-form science, psychology, technology, education",
        "status": "test_voice",
        "register": "bright_calm",
        "style": "articulate_expressive",
        "per_language": {
            _EN: {"native_status": "native", "rank": 22,
                  "recommended": True, "default": False,
                  "description": "calm, bright, articulate – expressive, crisp precision"},
            _DE: {"native_status": "cross_language", "rank": 63,
                  "recommended": False, "default": False,
                  "description": "bright, calm – English design (cross-language)"},
        },
        "settings": {"seed": 52022, "variant": "EN_CALM_02", "cache_version": "q3p-v2-integrity",
                     "language": "English", "engine": "VoiceCloneEngine", "backend": "clone"},
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
                 "serena", "vivian", "sohee",
                 "en_male_deep_01", "en_male_deep_02",
                 "en_male_calm_deep_01", "en_male_warm_storytelling_authoritative_01",
                 "en_female_calm_01", "en_female_calm_02"]
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

    def entries_for_language(self, language: str, tier: str | None = None) -> list[VoiceProfileEntry]:
        """Stimmen einer Sprache, gruppenweise nach Rang sortiert
        (männlich zuerst; VD-E bei Deutsch immer ganz oben, §6).
        tier: None=alle (ohne REJECTED zu bevorzugen ist responsibility des Callers),
              "ACTIVE"/"BACKUPS"/"REJECTED"/"CANDIDATE" filtert strikt.
              Standard-GUI soll ausschließlich ACTIVE (confirmed) zeigen, UNASSESSED nie als Favorite, REJECTED nie
              in Favoriten/Shortlist. Backups séparat.
        """
        entries = [self.for_language(e, language)
                   for e in self.entries()
                   if language in e.language_support]
        if tier:
            t = tier.upper()
            filtered=[]
            for e in entries:
                d=self._profiles.get(e.voice_id,{})
                tt=tier_for(d)
                # CANDIDATE is subset of ACTIVE (new_candidate*)
                if t=="CANDIDATE":
                    if str(d.get("status","")).startswith("new_candidate"):
                        filtered.append(e)
                elif tt==t:
                    filtered.append(e)
            entries=filtered
        male = sorted([e for e in entries if e.gender == "male"],
                      key=lambda e: (e.rank, e.display_name))
        female = sorted([e for e in entries if e.gender == "female"],
                        key=lambda e: (e.rank, e.display_name))
        return male + female

    def entries_for_tier(self, tier: str) -> list[VoiceProfileEntry]:
        """Alle Stimmen eines Tiers, sprachunabhängig (für Manifest/Validator)."""
        out=[]
        for e in self.entries():
            d=self._profiles.get(e.voice_id,{})
            if tier_for(d).upper()==tier.upper():
                out.append(e)
        return sorted(out, key=lambda x: (x.display_name, x.voice_id))

    def tier_of(self, voice_id: str) -> str:
        d=self._profiles.get(voice_id,{})
        return tier_for(d) if d else "UNKNOWN"


    def default_voice_id(self, language: str = _DE) -> str:
        """VD-E bleibt bei Deutsch Standard; sonst beste empfohlene
        Stimme der Sprache (native bevorzugt). REJECTED wird nie zurückgegeben."""
        if language == _DE and self.get("vd_e") is not None:
            return "vd_e"
        # filter REJECTED out for default
        entries = [e for e in self.entries_for_language(language) if self.tier_of(e.voice_id)!="REJECTED"]
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
