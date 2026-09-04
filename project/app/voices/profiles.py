"""Die sechs Hauptstimmen (Anforderung 18) + DEFAULT BEST NARRATOR (Anf. 19).

Zuordnung zu den 9 Qwen3-TTS-Premium-Timbres (CustomVoice-Modelle):

| Speaker   | Beschreibung (offiziell)                  | Nativ      |
|-----------|-------------------------------------------|------------|
| Vivian    | bright, slightly edgy young female        | Chinesisch |
| Serena    | warm, gentle young female                 | Chinesisch |
| Uncle_Fu  | seasoned male, low mellow timbre          | Chinesisch |
| Dylan     | youthful Beijing male                     | Chinesisch |
| Eric      | lively Chengdu male, husky brightness     | Chinesisch |
| Ryan      | dynamic male, strong rhythmic drive       | Englisch   |
| Aiden     | sunny American male, clear midrange       | Englisch   |
| Ono_Anna  | playful Japanese female                    | Japanisch  |
| Sohee     | warm Korean female, rich emotion          | Koreanisch |

Alle Speaker können alle 10 Sprachen sprechen (inkl. Deutsch); die
endgültige Zuordnung liefert der Stimmen-Benchmark auf der Zielhardware
(Anforderung 19+20: Auswahl durch Test, nicht willkürlich – siehe
app/voices/benchmark.py und benchmark/report_*.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Qwen3-TTS Modell-/Speaker-Konstanten
SUPPORTED_SPEAKERS = ["Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric",
                      "Ryan", "Aiden", "Ono_Anna", "Sohee"]

MODEL_REPO_BY_SIZE = {
    "1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "0.6B": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
}
TOKENIZER_REPO = "Qwen/Qwen3-TTS-Tokenizer-12Hz"


@dataclass
class VoiceProfile:
    id: str
    label: str
    gender: str                    # male | female
    speaker: str                   # Qwen3-TTS Premium-Timbre (Default)
    base_style_de: str             # Grundhaltung (in Instruct, DE-Inhalte)
    base_style_en: str
    description: str               # deutsche Beschreibung für die UI
    tags: list = field(default_factory=list)
    de_modifier: str = ""          # Zusatzzeile im DE-Instruct (Phase 1)


PROFILES: dict[str, VoiceProfile] = {
    "male_1": VoiceProfile(
        id="male_1", label="Male 1 – Der Dokumentar",
        gender="male", speaker="Ryan",
        base_style_de=("Speak as a professional male documentary narrator in "
                       "German: calm, warm, highly credible, even pacing, "
                       "natural intonation."),
        base_style_en=("Speak as a professional male documentary narrator: "
                       "calm, warm, highly credible, even pacing."),
        description="Professionell, dokumentarisch, ruhig, glaubwürdig, warm, seriös.",
        tags=["doku", "standard"],
    ),
    "male_2": VoiceProfile(
        id="male_2", label="Male 2 – Der Erzähler",
        gender="male", speaker="Uncle_Fu",
        base_style_de=("Speak as a deep, intelligent, warm male voice in "
                       "German, audiobook style: unhurried, emotionally "
                       "controlled, immersive."),
        base_style_en=("Speak as a deep, intelligent, warm male voice, "
                       "audiobook style: unhurried, emotionally controlled."),
        description="Tief, intelligent, warm, ruhig, hörbuchartig.",
        tags=["hörbuch"],
    ),
    "male_3": VoiceProfile(
        id="male_3", label="Male 3 – Die Tiefe (Deep Dive)",
        gender="male", speaker="Ryan",
        base_style_de=("Speak as a very deep, serious, cinematic male voice "
                       "in German: powerful but calm, psychological, weighty, "
                       "never theatrical."),
        base_style_en=("Speak as a very deep, serious, cinematic male voice: "
                       "powerful but calm, weighty, never theatrical."),
        description="Sehr seriös, kraftvoll, cinematic, tief – für Deep Dives.",
        tags=["deep", "cinematic"],
        de_modifier=("Extra deep and weighty timbre, exceptionally steady "
                     "delivery, quiet cinematic gravity."),
    ),
    "female_1": VoiceProfile(
        id="female_1", label="Female 1 – Die Warme",
        gender="female", speaker="Serena",
        base_style_de=("Speak as a warm, calm, naturally deep female voice in "
                       "German: trustworthy, gentle, present."),
        base_style_en=("Speak as a warm, calm, naturally deep female voice: "
                       "trustworthy, gentle."),
        description="Warm, ruhig, tief, natürlich, vertrauenswürdig.",
        tags=["warm"],
    ),
    "female_2": VoiceProfile(
        id="female_2", label="Female 2 – Die Intellektuelle",
        gender="female", speaker="Sohee",
        base_style_de=("Speak as an intelligent, elegant female documentary "
                       "voice in German: composed, precise, high-quality "
                       "delivery."),
        base_style_en=("Speak as an intelligent, elegant female documentary "
                       "voice: composed, precise."),
        description="Intelligent, elegant, dokumentarisch, hochwertig.",
        tags=["doku"],
    ),
    "female_3": VoiceProfile(
        id="female_3", label="Female 3 – Die Erzählerin",
        gender="female", speaker="Vivian",
        base_style_de=("Speak as a professional, emotionally present female "
                       "narrator in German: natural, calm, storytelling "
                       "warmth."),
        base_style_en=("Speak as a professional, emotionally present female "
                       "narrator: natural, calm storytelling."),
        description="Professionell, emotional, ruhig, natürlich, erzählerisch.",
        tags=["story"],
    ),
}

# DEFAULT BEST NARRATOR (Anforderung 19): Kandidat mit stärkster erwarteter
# Deutsch-Qualität; finale Bestätigung durch Stimmen-Benchmark auf der
# Zielhardware (Benchmark überschreibt diese Zuweisung wenn besser).
# Phase 1 (§19): DEFAULT BEST GERMAN NARRATOR wird durch den DEUTSCHEN
# Stimmen-Benchmark ermittelt (app/voices/benchmark.py,
# run_german_speaker_benchmark) – nicht durch englische Tests.
DEFAULT_BEST_NARRATOR_ID = "male_1"
DEFAULT_BEST_NARRATOR_LABEL = "DEFAULT BEST NARRATOR"
GERMAN_BEST_LABEL = "DEFAULT BEST GERMAN NARRATOR"


def get_profile(profile_id: str) -> VoiceProfile:
    if profile_id in (None, "", "default_best_narrator"):
        return PROFILES[DEFAULT_BEST_NARRATOR_ID]
    return PROFILES.get(profile_id, PROFILES[DEFAULT_BEST_NARRATOR_ID])


def list_profiles() -> list[VoiceProfile]:
    return list(PROFILES.values())


def profile_for_language(profile: VoiceProfile, language: str) -> str:
    return (profile.base_style_de if language.lower().startswith("ger")
            else profile.base_style_en)
