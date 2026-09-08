# VoiceOverApp – Current State v2.2.0 (2026-09-08) – RTX Real Validation Phase

**Branch:** `arena/01a082be-voice-ai-reference` (ab 761d258 feat: add --input and --output parameters)  
**Ausgangscommit:** `761d2583e877a5692f92ea7f8184cf49f0c38076`  
**Status:** 12 Stimmen (VD-E locked + 7 CustomVoice + 4 englische Design->Clone TEST), Technik-Integration ✓, **Real-Audio-Validierung auf RTX 5060 ⏳ ausstehend** (Platzhalter-WAVs noch synthetisch, Ranking vorläufig).

**Voices:**
- vd_e (male, clone, DE recommended/default, seed 52001, ref cache/voice_refs/VD-E.wav, SHA B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025) – LOCKED
- en_male_deep_01 (male deep investigative, clone, EN native rank11, seed 52011, ref en_male_deep_01.wav – *Platzhalter F0 92Hz, real via VoiceDesign->Clone ausstehend*)
- en_male_deep_02 (male warm storyteller, clone, EN native rank12, seed 52012 – Platzhalter)
- en_female_calm_01 (female warm doc, clone, EN native rank21, seed 52021 – Platzhalter)
- en_female_calm_02 (female bright articulate, clone, EN native rank22, seed 52022 – Platzhalter)
- plus uncle_fu, dylan, ryan, aiden, serena, vivian, sohee (CustomVoice)

**Unterscheidung Pflicht A vs B:**
- **A) Sandbox/TestDouble** – tatsächlich gemessen 2026-09-08: desktop_voices 12/12 Sehr gut/Empfohlen (EN-QC 99.7-99.8, DE-QC 96.9-98.1), Marker 3→4 Parts validiert, Long-Form 26-Seiten PDF Streaming ok, alle Regressionstests grün (v2 20/20, desktop 21/21, packaging 16/16, german_phase1 26/26, pipeline_batch 12/12, phase3 19/19, phase2 17/17).
- **B) Real RTX 5060** – *ausstehend*: Qwen-Modelle fehlen in CI (`project/models` leer, kein torch/cuda, nvidia-smi fehlt), echte VoiceDesign->Clone Referenzen und 4-Parts Benchmark-Audio + Long-Form Hörtest + VRAM/RTF Messung vorbereitet via `benchmark/rtx_english_validation.py`, aber nicht ausführbar ohne Hardware. Ranking daher nur vorläufig.

**Änderungen (Kurz):**
- app/prosody/instruct.py: VOICEDESIGN_REF_TEXT_EN + ENGLISH_VOICEDESIGN_DESCRIPTIONS (nur EN, DE unverändert)
- app/voices/registry.py: 4 Profile + per-language order (12 Stimmen 7m/5w)
- voices/*.json: 4 neue JSON (ENGLISH_TEST_VOICES.md Doku)
- cache/voice_refs/*.wav: 4 Platzhalter-Refs (synthetisch, zu ersetzen)
- app/tts/test_double.py: voice_id-spezifische F0-Hashes
- app/jobs/runner.py + app/main.py: clone-Engine generalisiert (VD-E Lock nur für vd_e)
- app/voices/desktop_benchmark.py: je voice_id eigene Engine + ENGLISH-Fallback
- app/audio/concat.py: samplerate Fix
- tests/*: 12 Stimmen, packaging tolerant, phase3 guard gelockert, tkinter SKIP
- benchmark/english_longform_benchmark.txt: 3 Marker, 4 Abschnitte (632/897/159/1574 chars)
- benchmark/german_quality_analysis.md: DE Gap + lokale Fixes (theorie/wissenschaft/geist/logie generisch, semantic pause)
- benchmark/rtx_english_validation.py: Real-Hardware Skript (marker check, model check, ref generation, 4-Parts job, cache/VD-E checks, VRAM)
- benchmark/RTX5060_REAL_VALIDATION_REPORT.md: Pflicht-Trennung A vs B, alle 24 Punkte, echte Befehle
- README v2.2.0 Abschnitt 21, FINAL_APP_MANIFEST 2.2.0, CURRENT_STATE aktualisiert

**Benchmarks A) Sandbox:**
- Desktop-Voice (TestDouble): 12/12, QC siehe english_test_voices_report.md (vorläufig, nicht Urteil)
- Marker-Splitting: 3 Marker → 4 Parts, parts+full via concat identisch, identity_check ok
- Long-Form: PDF 26 Seiten via streaming (37 min, 130 Segmente in FINAL_APP_REPORT)

**Hardware:**
- Ziel: RTX 5060 8GB / Ryzen 7 5700X / 32GB / Win10 / Python 3.12.10 / torch 2.11+cu128 (bf16, sdpa, Model-Pool sequentiell)
- CI: Linux Sandbox ohne GPU/torch/Modelle – daher nur TestDouble, ffmpeg via imageio-ffmpeg, pypdf

**Nächste Schritte auf Zielmaschine (nicht in CI ausführbar):**
1. `install.ps1` – Modelle laden (Base, CustomVoice, VoiceDesign, Tokenizer)
2. `benchmark/rtx_english_validation.py --check-markers` → 3 Marker /4 Parts
3. Echte VoiceDesign-Referenzen: `benchmark/rtx_english_validation.py --voice en_male_deep_01` (×4, überschreibt Platzhalter)
4. Voll-Benchmark: `benchmark/rtx_english_validation.py --all` (identischer Text, 4 Parts, parts_plus_full, Long Sample, QC, VRAM)
5. `python app/main.py --desktop-voices` (alle 12, DE+EN, blind Hörproben)
6. Hörtest blind A-D (en_* vs ryan/aiden), Ranking BEST_DEEP_MALE / BEST_WARM_MALE / BEST_CALM_FEMALE / BEST_EXPRESSIVE_FEMALE – nur Empfehlung, kein Auto-Replace
7. `tests/run_all.py` erneut (Regression grün halten)
8. Danach German A/B separat (compound generisch, nicht nur Neurowissenschaft/Erdgeist, keine globale Speed-Änderung)

**Qualitäts-Regel:** 4 Stimmen gelten erst als fertig, wenn B) mit echtem Audio validiert (siehe RTX5060_REAL_VALIDATION_REPORT.md Abschnitt 24).
