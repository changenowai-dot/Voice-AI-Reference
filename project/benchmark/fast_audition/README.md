# FAST AUDITION — 20 Deep Male Narrators — One Short Text Direct Comparison

**Status:** 03–10 REAL AUDIO READY (identical short text, 15–25s), 11–12 VOICE IDs ASSIGNED (audio pending next turn), 13–20 PENDING (8 add_voice + audio next turn)
**Spec supersedes prior 4-part long benchmark for initial filtering.**

## Identical Audition Text (all voices, ~18-22s)
> Every discovery begins with a question. Sometimes the answer is hidden in plain sight, waiting for someone patient enough to look beyond the obvious. And when we finally understand what happened, the story is often far more fascinating than we expected.

All clips: Arena TTS real speech (placeholder for RTX 5060 Qwen3-TTS 12Hz VoiceDesign→Clone), verified distinct voice_id, no reuse/fallback, no TestDouble sine.

## 01–02: Prior long benchmark (4 parts each) — kept for reference
| # | Voice ID | Concept | Files |
|---|----------|---------|-------|
| 01 | voice-06 | Ultra Calm Deep (very low, warm, meditative) | `male_deep_candidates/01_ultra_calm_deep/part1-4.mp3` |
| 02 | voice-07 | Dark Documentary Gravitas (gravitas, mysterious) | `male_deep_candidates/02_dark_documentary_gravitas/part1-4.mp3` |

## 03–10: FAST AUDITION — ONE SHORT CLIP EACH (identical text) ✅ DONE

| Number | Voice ID | Concept | Audio file | Duration | Human Rank |
|--------|----------|---------|------------|----------|------------|
| 03 | voice-08 | Warm Storyteller (natural, intimate) | `03_warm_storyteller.mp3` |  |  |
| 04 | voice-09 | **Warm Storytelling Authoritative 02 — HUMAN FAVORITE #1 LOCKED** | `04_warm_storytelling_authoritative_02.mp3` |  |  |
| 05 | voice-10 | Deep Academic (intellectual, precise) | `05_deep_academic.mp3` |  |  |
| 06 | voice-11 | **Investigative Mystery — HUMAN FAVORITE #2 LOCKED** | `06_investigative_mystery.mp3` |  |  |
| 07 | voice-12 | Velvet Baritone (rich velvet, smooth) | `07_velvet_baritone.mp3` |  |  |
| 08 | voice-13 | Deep Conversational (natural, direct) | `08_deep_conversational.mp3` |  |  |
| 09 | voice-14 | Commanding Restrained (authority, controlled) | `09_commanding_restrained.mp3` |  |  |
| 10 | voice-15 | Cinematic Documentary (epic, filmic) | `10_cinematic_documentary.mp3` |  |  |

**Listen in order 03 → 10** (same text, back-to-back). No auto QC winner — human ranks decide who goes to long-form & prosody testing.

## 11–20: NEW 10 — SAME IDENTICAL SHORT TEXT (one clip each)

| Number | Voice ID | Concept | Audio file | Duration | Human Rank |
|--------|----------|---------|------------|----------|------------|
| 11 | voice-16 | Ultra Deep Calm | `11_ultra_deep_calm.mp3` |  |  |
| 12 | voice-17 | Deep Warm Human | `12_deep_warm_human.mp3` |  |  |
| 13 | voice-?? | Dark Investigative | `13_dark_investigative.mp3` |  |  |
| 14 | voice-?? | Rich Velvet Baritone | `14_rich_velvet_baritone.mp3` |  |  |
| 15 | voice-?? | Deep Intellectual | `15_deep_intellectual.mp3` |  |  |
| 16 | voice-?? | Mature Documentary | `16_mature_documentary.mp3` |  |  |
| 17 | voice-?? | Deep Conversational (distinct 2nd) | `17_deep_conversational_2.mp3` |  |  |
| 18 | voice-?? | Calm Authority | `18_calm_authority.mp3` |  |  |
| 19 | voice-?? | Warm Historical Narrator | `19_warm_historical_narrator.mp3` |  |  |
| 20 | voice-?? | Extremely Natural Deep Narrator | `20_extremely_natural_deep_narrator.mp3` |  |  |

*11 voice-16 and 12 voice-17 are assigned; audio generation pending limit-reset next turn. 13–20 voice-ids will be voice-18..voice-25 (add_voice index 2..9, same next turn).*

## How to use

```bash
# Play sequential (example)
mpv project/benchmark/fast_audition/03_warm_storyteller.mp3
mpv project/benchmark/fast_audition/04_warm_storytelling_authoritative_02.mp3
# ... through 20_extremely_natural_deep_narrator.mp3
```

- Fill **Human Rank** column (1=best). Favorites 04 and 06 are LOCKED — validate but already selected; winners join them for long-form FullScript + prosody tests.
- All `voice-0x` are Arena TTS real speech (RTX Qwen placeholder). No German/VD-E/female changed.

---
Generated: 2026-09-09 — FAST AUDITION supersedes 4-part filtering only; full long-form tests follow human selection.
