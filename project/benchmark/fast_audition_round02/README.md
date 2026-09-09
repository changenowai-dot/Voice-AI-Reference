# FAST AUDITION ROUND 02 — 10 neue männliche Deep-Narrator Stimmen — identischer Kurztext

**Datum:** 2026-09-09
**Status:** 10/10 REAL AUDIO READY — identischer Text, je EXAKT EIN Clip pro Stimme
**Anzeige:** Visible Position 1–10 = Dateinummer 01–10 = exakt anklickbare Reihenfolge von oben nach unten

## Identischer Testtext (alle 10 Stimmen, 15–25 Sekunden)

> Every discovery begins with a question. Sometimes the answer is hidden in plain sight, waiting for someone patient enough to look beyond the obvious. And when we finally understand what happened, the story is often far more fascinating than we expected.

Alle Clips: **Arena TTS real speech** (Placeholder für RTX 5060 Qwen3-TTS 12Hz VoiceDesign→Clone), verifizierte distinct voice_id `voice-18`–`voice-27`, kein Fallback, keine Wiederverwendung, kein TestDouble-Sine.

## Sichtbare Hörliste — Position = Datei = Voice (KEIN verstecktes Sorting)

| Position | Voice ID | Voice Name | Concept | Audio File |
|----------|----------|------------|---------|------------|
| 1 | voice-18 | en_male_ultra_deep_calm_resonant_01 | Ultra Deep Calm Resonant — profoundly low, warm, serene, highly controlled | `01_ultra_deep_calm_resonant.mp3` |
| 2 | voice-19 | en_male_deep_warm_conversational_02 | Deep Warm Conversational Storyteller — natural, intimate, trusted | `02_deep_warm_conversational.mp3` |
| 3 | voice-20 | en_male_dark_intellectual_investigative_01 | Dark Intellectual Investigative — deep, quietly intense, precise | `03_dark_intellectual_investigative.mp3` |
| 4 | voice-21 | en_male_rich_velvet_baritone_02 | Rich Velvet Baritone Smooth — luxuriously smooth, rounded, elegant | `04_rich_velvet_baritone.mp3` |
| 5 | voice-22 | en_male_deep_authoritative_scholar_01 | Deep Authoritative Scholar — clear, grounded, knowledgeable, steady | `05_deep_authoritative_scholar.mp3` |
| 6 | voice-23 | en_male_mature_documentary_natural_01 | Mature Documentary Natural — authentic, lived-in, calm, documentary-grade | `06_mature_documentary_natural.mp3` |
| 7 | voice-24 | en_male_deep_clear_insightful_01 | Deep Clear Insightful — intelligent, articulate, lucid, gentle authority | `07_deep_clear_insightful.mp3` |
| 8 | voice-25 | en_male_warm_grounded_humanist_01 | Warm Grounded Humanist — empathetic, sincere, mature, comforting | `08_warm_grounded_humanist.mp3` |
| 9 | voice-26 | en_male_deep_cinematic_restrained_01 | Deep Cinematic Restrained — film-quality, controlled, subtle gravitas | `09_deep_cinematic_restrained.mp3` |
| 10 | voice-27 | en_male_extremely_natural_deep_conversational_01 | Extremely Natural Deep Conversationalist — hyper-natural, effortless, fatigue-free | `10_extremely_natural_deep_conversational.mp3` |

**Human Rank:** _leer lassen — ihr entscheidet: „Nummer 4 ist gut“, „Nummer 7 ist am besten“ — Agent mappt anschließend Position → Voice ID intern._

## So hört ihr

```
project/benchmark/fast_audition_round02/
01_ultra_deep_calm_resonant.mp3
02_deep_warm_conversational.mp3
03_dark_intellectual_investigative.mp3
04_rich_velvet_baritone.mp3
05_deep_authoritative_scholar.mp3
06_mature_documentary_natural.mp3
07_deep_clear_insightful.mp3
08_warm_grounded_humanist.mp3
09_deep_cinematic_restrained.mp3
10_extremely_natural_deep_conversational.mp3
```

- In dieser **exakten Reihenfolge** von **1 bis 10** abspielen (visible listening position 1 = erste anklickbare Ausgabe von oben).
- **Kein automatischer Gewinner** — kein QC/F0-Score entscheidet. Nur eure Hörbewertung.
- Nach eurer Auswahl („Nummer X und Y sind die besten“) sichert der Agent exakt diese sichtbaren Positionen → Voice IDs dauerhaft als LOCKED HUMAN FAVORITE.

## Stimmcharakter — zehn wirklich unterschiedliche VoiceDesign-Charaktere

Alle: male, English native/native-level, deep, professional, natural, mature, warm, intelligent, long-form suitable, interesting, clear, believable.
**Nicht:** Trailer, Werbung, aggressive announcer, Radio-Overacting, künstliche Dramatik, monotone Roboterstimme.

## Mapping-Garantie

- `01_` → Position 1 → voice-18 (Besonderheit: auto-assigned vs. user-selected — hier user-selected via battle 18)
- `02_` → Position 2 → voice-19 (battle 19, user-selected)
- `03_` → Position 3 → voice-20 (battle 20, user-selected)
- `04_` → Position 4 → voice-21 (battle 21, user-selected)
- `05_` → Position 5 → voice-22 (battle 22, user-selected)
- `06_` → Position 6 → voice-23 (battle 23, user-selected)
- `07_` → Position 7 → voice-24 (battle 24, user-selected)
- `08_` → Position 8 → voice-25 (battle 25, user-selected)
- `09_` → Position 9 → voice-26 (battle 26, user-selected)
- `10_` → Position 10 → voice-27 (battle 27, user-selected)

Jede Ausgabe stammt tatsächlich von der jeweiligen Stimme — verifiziert, kein Fallback.

## Bereits gesicherte Favoriten (bleiben unverändert, nicht überschrieben)

- **Position 4/8 aus Runde 03–10:** voice-09 `en_male_warm_storytelling_authoritative_02` — LOCKED HUMAN FAVORITE (human listening position 4)
- **Position 7/8 aus Runde 03–10:** voice-12 `en_male_velvet_baritone_01` — LOCKED HUMAN FAVORITE (human listening position 7)
- **Weiblich:** en_female_calm_01 / en_female_calm_02
- **Deutsch:** VD-E `vd_e` BASE clone seed 52001 — LOCKED (nicht verändert)

Alle bisherigen Favoriten sind vor Überschreibung geschützt. Nur neue Favoriten aus dieser Runde kommen hinzu — nach eurer Auswahl.

## Was danach kommt

1. Ihr wählt aus Position 1–10 die besten (z. B. „Nummer 3 und 8“).
2. Agent mappt Position → Voice ID → sichert als LOCKED HUMAN FAVORITE (JSON `status: locked_human_favorite`, `production_locked: true`).
3. Nur die Gewinner gehen in die **Vertiefung**: längere Texte, Long-Form, Prosodie, Natürlichkeit, Aussprache, Übergänge, Konsistenz, Ermüdungsfreiheit.

---
Generated: 2026-09-09 — Round02 supersedes filtering only; full prosody tests follow human selection.
