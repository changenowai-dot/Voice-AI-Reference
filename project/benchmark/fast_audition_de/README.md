# FAST AUDITION DE — 7 neue deutsche Stimmen (5 männlich tief + 2 weiblich) — identischer Kurztext

**Datum:** 2026-09-09
**Status:** 7/7 REAL AUDIO READY — je EXAKT EIN Clip pro Stimme, identischer Text 15–25s
**Sichtbare Reihenfolge:** 1 → 01_..., 2 → 02_..., ... 7 → 07_... = exakt anklickbare Ausgaben von oben nach unten — **bewertet wird ausschließlich sichtbare Position**

## Identischer deutscher Testtext (alle 7 Stimmen exakt gleich)

> Jede Entdeckung beginnt mit einer Frage. Manchmal liegt die Antwort direkt vor uns, verborgen im Offensichtlichen. Doch erst wenn wir genauer hinschauen, erkennen wir, was wirklich geschehen ist. Und oft ist die Geschichte dahinter faszinierender, als wir zunächst erwartet haben.

Alle Clips: **Arena TTS real speech** (Placeholder für RTX 5060 `Qwen3-TTS-12Hz-1.7B-VoiceDesign→Clone`), verifizierte distinct `voice-28`–`voice-34`, kein Fallback, keine Wiederverwendung, kein TestDouble-Sine. Provenance in `project/voices/voice_generation_recipes.json` als `arena_placeholder` ehrlich dokumentiert.

## Sichtbare Hörliste — Position = Datei = Voice (KEIN verstecktes Sorting, KEIN Auto-Gewinner)

| Position | Voice ID | Voice Name | Concept | Audio File | Duration | Human Rank |
|----------|----------|------------|---------|------------|----------|------------|
| 1 | voice-28 | de_male_ultra_calm_deep_01 | Ultra Calm Deep — sehr tief, ruhig, warm, souverän, entspannte Langform | `01_de_male_ultra_calm_deep.mp3` |  |  |
| 2 | voice-29 | de_male_dark_documentary_01 | Dark Documentary — tief, ernst, glaubwürdig, dokumentarisch, kontrolliert | `02_de_male_dark_documentary.mp3` |  |  |
| 3 | voice-30 | de_male_warm_storytelling_authoritative_01 | Warm Storytelling Authority — tief, warm, menschlich, erzählerisch, subtil autoritativ | `03_de_male_warm_storytelling_authoritative.mp3` |  |  |
| 4 | voice-31 | de_male_deep_academic_01 | Deep Academic — tief, intelligent, präzise, kultiviert, wissenschaftlich | `04_de_male_deep_academic.mp3` |  |  |
| 5 | voice-32 | de_male_deep_natural_conversational_01 | Deep Natural Conversational — tief, natürlich, direkt, modern, sehr menschlich | `05_de_male_deep_natural_conversational.mp3` |  |  |
| 6 | voice-33 | de_female_deep_warm_documentary_01 | Deep Warm Documentary — warm, tief, ruhig, reif, glaubwürdig | `06_de_female_deep_warm_documentary.mp3` |  |  |
| 7 | voice-34 | de_female_deep_calm_intelligent_01 | Deep Calm Intelligent — ruhig, klar, intelligent, elegant, natürlich | `07_de_female_deep_calm_intelligent.mp3` |  |  |

**Human Rank:** leer lassen — du entscheidest z. B. „Nummer 4 und Nummer 6 sind gut“ → Agent mappt intern Position → Voice-ID und sichert diese dauerhaft.

## Dateien (exakt diese Reihenfolge abspielen)

```
project/benchmark/fast_audition_de/
01_de_male_ultra_calm_deep.mp3
02_de_male_dark_documentary.mp3
03_de_male_warm_storytelling_authoritative.mp3
04_de_male_deep_academic.mp3
05_de_male_deep_natural_conversational.mp3
06_de_female_deep_warm_documentary.mp3
07_de_female_deep_calm_intelligent.mp3
```

**Regeln:**
- 1 = erste anklickbare Ausgabe von oben, 2 = zweite, … 7 = siebte — **keine alphabetische Verschiebung, keine Registry-Sortierung**
- Wenn du sagst „Nummer 4 und 6“, mappt der Agent: 4→voice-31, 6→voice-33
- Kein QC/F0/Pitch/WER-Auto-Ranking — nur menschliches Hören
- Nur ein Sample pro Stimme (keine 4 Parts, kein FullScript) — schneller direkter Vergleich

## Stimmcharakter — sieben wirklich unterschiedliche Identitäten

- **Männlich tief (5):** jeweils unterschiedliche Register/Beschreibung (sehr tief souverän vs. dunkel dokumentarisch vs. warm erzählerisch vs. akademisch präzise vs. natürlich direkt) — nicht nur Pitch-Varianten
- **Weiblich (2):** zwei getrennte Identities (tief-warm dokumentarisch vs. ruhig-klar intelligent) — beide reif, glaubwürdig, long-form geeignet

Alle: deutsch muttersprachlich/native-level, professionell, natürlich, erwachsen, warm/intelligent, long-form suitable, interesting, clear, believable. Nicht: Trailer, Werbung, aggressive announcer, Overacting, künstliche Dramatik, monotone Roboterstimme.

## Mapping-Garantie (interne Doku)

| Visible Pos | Datei | Voice ID (Arena) | Voice Name | Concept |
|-------------|-------|------------------|------------|---------|
| 1 | 01_de_male_ultra_calm_deep.mp3 | voice-28 | de_male_ultra_calm_deep_01 | Ultra Calm Deep |
| 2 | 02_de_male_dark_documentary.mp3 | voice-29 | de_male_dark_documentary_01 | Dark Documentary |
| 3 | 03_de_male_warm_storytelling_authoritative.mp3 | voice-30 | de_male_warm_storytelling_authoritative_01 | Warm Storytelling Authority |
| 4 | 04_de_male_deep_academic.mp3 | voice-31 | de_male_deep_academic_01 | Deep Academic |
| 5 | 05_de_male_deep_natural_conversational.mp3 | voice-32 | de_male_deep_natural_conversational_01 | Deep Natural Conversational |
| 6 | 06_de_female_deep_warm_documentary.mp3 | voice-33 | de_female_deep_warm_documentary_01 | Deep Warm Documentary |
| 7 | 07_de_female_deep_calm_intelligent.mp3 | voice-34 | de_female_deep_calm_intelligent_01 | Deep Calm Intelligent |

Jede Ausgabe stammt tatsächlich von dieser Stimme — verifiziert via `arena_voice_id`, kein Fallback.

## Provenance (ehrlich)

- **generation_provenance = `arena_placeholder`** für alle 7: echte Qwen-RTX-5060 Pipeline (`VoiceDesign→Clone` mit `Qwen/Qwen3-TTS-12Hz-1.7B-Base`) ist in dieser Sandbox nicht gelaufen (`nvidia-smi not found`, keine Modelle geladen). Stattdessen Arena TTS real speech, aber **VoiceDesign-Konzept, Seed, Beschreibung sind vollständig gesichert** und in `project/voices/voice_generation_recipes.json` dokumentiert → reproduzierbar via `QwenVoiceStudio.design_reference()` + `build_clone_prompt()` + `synth_clone()` auf RTX 5060 (s. `project/voices/VOICE_GENERATION_ARCHITECTURE.md` §G).
- **VD-E bleibt `actual_qwen`** (golden reference Wave, SHA `B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025`).

## Was danach passiert

1. Du hörst 1–7 und nennst z. B. „Nummer 4 und 6“.
2. Agent sichert diese Positionen → Voice-IDs dauerhaft (z. B. `status: saved_human_shortlist`, `human_selected:true` oder `locked_human_favorite` nach deiner Festlegung).
3. Nur Gewinner gehen in vertiefte Tests: längere Texte, Long-Form, Prosodie, Natürlichkeit, Konsistenz, Ermüdungsfreiheit — **ohne globale TTS-Änderungen** in dieser Phase.

## English Shortlist bleibt unverändert (geschützt)

Aktuelle 7 englische Arbeitsstimmen bleiben erhalten und wurden nicht beeinflusst:
- LOCKED: voice-09 (A), voice-12 (B)
- SHORTLIST: voice-22 (C), voice-23 (D), voice-24 (E), voice-25 (F), voice-27 (G)
Alle dokumentiert in `project/voices/voice_generation_recipes.json` + `VOICE_GENERATION_ARCHITECTURE.md`.

---
Generated: 2026-09-09 — German fast audition (5+2) — kein Auto-Gewinner, nur schneller Hörvergleich, danach Vertiefung der besten.
