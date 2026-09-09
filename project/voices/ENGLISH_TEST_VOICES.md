# Vier neue englische Teststimmen – VoiceOverApp v2.1 (2026-09)

**Ziel:** muttersprachliches Englisch, ruhig, professionell, erwachsen, dokumentarisch, long-form-tauglich (10 s – 120 min).  
**Status:** TESTSTIMMEN – VD-E bleibt locked production (Deutsch). Keine automatische Ersetzung.  
**Backend:** VoiceDesign → Clone (Qwen3-TTS-12Hz-1.7B-VoiceDesign für Referenz, Qwen3-TTS-12Hz-1.7B-Base für Clone-Synthese).  
**Hardware:** RTX 5060 8 GB VRAM (getestet: sequentielles Laden via QwenModelPool, bf16, attn=sdpa per Default).  
**Cache:** eindeutiger Fingerprint je Stimme (voice_id + model + language + reference_sha256 + sampling + instruct + param_version `q3p-v2-integrity`). Keine Kollision mit VD-E oder untereinander.

---

## Übersicht

| voice_id | display_name | gender | register | style | backend | engine | model | reference | seed | intended_use | status | language_support |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `en_male_deep_01` | EN Male Deep 01 | male | deep | investigative_documentary | clone | VoiceCloneEngine | Qwen3-TTS-12Hz-1.7B-Base (VoiceDesign->Clone) | `cache/voice_refs/en_male_deep_01.wav` | 52011 | long-form documentary, investigative, history, science | test_voice | German + English (EN native rank 11) |
| `en_male_deep_02` | EN Male Deep 02 | male | deep_warm | warm_storyteller | clone | VoiceCloneEngine | Qwen3-TTS-12Hz-1.7B-Base | `cache/voice_refs/en_male_deep_02.wav` | 52012 | storytelling, science, psychology | test_voice | German + English (EN native rank 12) |
| `en_female_calm_01` | EN Female Calm 01 | female | warm_low | calm_documentary | clone | VoiceCloneEngine | Qwen3-TTS-12Hz-1.7B-Base | `cache/voice_refs/en_female_calm_01.wav` | 52021 | documentary, psychology, philosophy | test_voice | German + English (EN native rank 21) |
| `en_female_calm_02` | EN Female Calm 02 | female | bright_calm | articulate_expressive | clone | VoiceCloneEngine | Qwen3-TTS-12Hz-1.7B-Base | `cache/voice_refs/en_female_calm_02.wav` | 52022 | science, technology, education | test_voice | German + English (EN native rank 22) |

**Native-Language-Einstufung:**
- Englisch: alle vier = `native` (VoiceDesign auf Englisch nativ trainiert, nicht Cross-Language Spezialfall). Ryan/Aiden bleiben ebenfalls native (Preset).
- Deutsch: alle vier = `cross_language` (rank 60–63, nicht empfohlen) – bewusst, damit deutsche Produktion bei VD-E bleibt.
- VD-E bleibt `recommended`/`default` für Deutsch, für Englisch `cross_language rank 35`.

---

## Voice-Design-Beschreibungen (voll, für Reproduktion)

### en_male_deep_01 – Deep Investigative (dunkler, autoritativer)
> A deep, authoritative English documentary narrator. Mature male voice in his early forties, resonant and grounded, supremely calm and credible. Measured pacing, flawless diction, natural neutral accent with subtle gravitas. Investigative, cinematic without drama, trustworthy over many minutes. Never trailer, never aggressive.

**Charakter:** tiefer, dunkler, autoritativer, investigativer als Ryan/Aiden. Maximale Glaubwürdigkeit für investigativen Deep Dive.

### en_male_deep_02 – Warm Storyteller (wärmer, conversationaler)
> A warm, deep English storyteller. Mature male voice in his late thirties, slightly warmer and more conversational than a pure documentary narrator, yet deeply professional and intelligent. Clear, inviting timbre with gentle narrative musicality, confident and articulate. Ideal for long-form history, science and psychology.

**Charakter:** wärmer, storyteller-orientiert, klar, einladend – trotzdem tief und ruhig. Mehr narrative Musikalität, weniger investigative Schwere.

### en_female_calm_01 – Warm Documentary (tiefer/wärmer Register)
> A calm, warm English female narrator. Mature woman in her late thirties, deeply warm and grounded in a lower register, documentary timbre. Highly professional, intelligent and emotionally present without theatricality. Velvet, trustworthy voice that remains pleasant over hours – never shrill, never childlike, never hype.

**Charakter:** wärmste, ruhigste, dokumentarischste weibliche Stimme – tiefe Lage, samtig, langfristig hörbar.

### en_female_calm_02 – Bright Articulate (heller, ausdrucksstark)
> A bright yet calm English female narrator. Articulate, expressive and intelligent, with a slightly higher but still mature register. Crisp diction, subtle emotional color, warm precision for science, psychology and philosophy. Naturally calm, never shrill, never overly emotional – long-form comfortable.

**Charakter:** leicht heller als 01, sehr artikuliert, stärker expressiv, aber weiterhin ruhig und erwachsen – präzise für Wissenschaft/Technik.

---

## Referenz-Generierung (Produktion)

1. **VoiceDesign** (Qwen3-TTS-12Hz-1.7B-VoiceDesign) erzeugt je Beschreibung eine kurze Referenzdatei (~6 s) mit `VOICEDESIGN_REF_TEXT_EN`:
   > There is a book no one claims to have written. And yet it has moved generations. Perhaps because it asks a question no one dares to speak aloud: Who decides what is real?
2. **Base-Clone** (`Qwen3-TTS-12Hz-1.7B-Base`, `create_voice_clone_prompt`) baut daraus den wiederverwendbaren Prompt (`cache/voice_refs/en_*.wav`).
3. Alle Segmente laufen über `generate_voice_clone` mit demselben Prompt → maximale Long-Form-Konsistenz (identisches Verfahren wie VD-E).

Sandbox-Platzhalter (TestDouble-ähnliche synthetische Wavs, F0 92/105/185/205 Hz) liegen bereits unter `cache/voice_refs/` für Offline-Tests. Auf RTX 5060 einmalig durch echte VoiceDesign-Referenzen ersetzen (`docs: Referenz via `python app/main.py --voice-design-reference en_male_deep_01` oder manuell über VoiceStudio).

**Seeds:** 52011–52022 garantieren deterministische, aber je Stimme unterschiedliche Intonationsvariation (Segment-Seed = production_seed pro Stimme, falls gesetzt, sonst cache-key-Hash + 52011-Hash).

---

## Integration – geänderte Dateien

- `app/prosody/instruct.py`: `VOICEDESIGN_REF_TEXT_EN` + `ENGLISH_VOICEDESIGN_DESCRIPTIONS` (+ Rückwärts-Alias in `VOICEDESIGN_DESCRIPTIONS`).
- `app/prosody/__init__.py`: Export der neuen Konstanten.
- `app/voices/registry.py`: 4 neue Profile + `order` ergänzt.
- `voices/*.json`: 4 neue Profile (auto-generiert via `ensure_profile_files`, Referenz-Hashes eingetragen).
- `app/tts/test_double.py`: `TestDoubleCloneEngine` generalisiert (voice_id-spezifischer F0-Key, VD-E-Lock nur für VD-E).
- `app/jobs/runner.py`: `build_engine` + `run_job` generalisiert (VD-E-Lock nur für vd_e, neue Stimmen via Design->Clone, Speaker-Cache-Key = voice_id).
- `app/main.py`: `_make_engine` analog generalisiert.

Kein Breaking Change für bestehende Stimmen; VD-E unverändert.

---

## Benchmark – Englisch (identischer Text, drei +++++ Marker)

Text: `benchmark/english_longform_benchmark.txt` (Abschnitt 1: Anonymes Buch + Physik/Neurowissenschaft; `+++++`; Abschnitt 2: 1914/1939, CERN 12.5 °C, Zahlen, Abkürzungen; `+++++`; Abschnitt 3: Long-Form-Melodie, philosophisch, Listen, dramatische Kurzsätze).

Kriterien: naturalness, intelligibility, pronunciation, rhythm, pauses, sentence melody, transition quality, onset quality, consistency, depth, warmth, professionalism, long-form comfort, artifacts, QC.

Ausführen (Prüfstand, offline):
```
.venv\Scripts\python.exe app/main.py --desktop-voices --engine test_double
python app/main.py --job job_en_benchmark.json  # mit language English, je voice_id
```

Echte RTX-5060-Bewertung (empfohlen):
```
# je Stimme getrennt, identischer Text
python app/main.py --job bench_en_male_deep_01.json
# Ergebnis: benchmark/desktop_voices/report.md + report.json
# HÖRTEST: blind sample_A-D.wav vergleichen (wie Phase 2/3)
```

Ranking wird nach Hörtest vergeben (numerischer QC nur sekundär).

---

## GUI – Sichtbarkeit

- Sprache **Deutsch** → oberste Position VD-E (EMPFOHLEN · Standard), darunter Uncle_Fu/Ryan … neue englische Teststimmen erscheinen nur ganz unten (rank 60+, CROSS-LANGUAGE) – kennzeichnen „English design (cross-language)“.
- Sprache **English** → männlich sortiert Ryan (10), EN Male Deep 01 (11), EN Male Deep 02 (12), Aiden (20) … weiblich Serena (20), EN Female Calm 01 (21), EN Female Calm 02 (22), Vivian (30) … VD-E erscheint unten (rank 35, CROSS-LANGUAGE).
- Status-Spalte: `NATIV` für alle vier neuen + Ryan/Aiden; `NATIV · EMPFOHLEN` für Ryan (default English), neue Stimmen `NATIV` + per_language recommended true aber nicht default.

---

## Schutzregeln

- VD-E-Referenz `cache/voice_refs/VD-E.wav` SHA-256 `B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025` – niemals überschreiben, nie neu designen (`allow_design=False`). Blockiert automatisch bei Hash-Abweichung.
- Neue Stimmen: SHA-256 je Referenz in `voices/en_*.json` dokumentiert; Cache-Key enthält reference-haltigen Speaker-Key, daher keine Kollision.
- Englische Qualität schützen: keine deutsche Aussprache-Overrides auf Englisch (`apply_tech_germanization` prüft `language.startswith("ger")`), keine globale Speed-Änderung, keine deutsche Prosodie auf Englisch.

---

*Erstellt 2026-09-08, Agent-Branch arena/01a082be-voice-ai-reference*
