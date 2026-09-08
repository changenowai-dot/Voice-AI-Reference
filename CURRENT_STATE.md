# VoiceOverApp – Current State v2.2.0 (2026-09-08)

**Branch:** `arena/01a082be-voice-ai-reference` (ab 761d258 feat: add --input and --output parameters)  
**Ausgangscommit:** `761d2583e877a5692f92ea7f8184cf49f0c38076`  
**Status:** 12 Stimmen (VD-E locked + 7 CustomVoice + 4 englische Design->Clone Teststimmen), Englisch-Benchmark via drei `+++++` Marker (4 Abschnitte), deutsche Qualität lokal optimiert (generische Komposita-Suffixe, sprachsensitiv), Cache-Fingerprint je Stimme, VD-E Hash locked, Tests prototypisch (TestDouble) bestanden (desktop_voices 12/12).

**Voices:**
- vd_e (male, clone, DE recommended/default, seed 52001, ref cache/voice_refs/VD-E.wav, SHA B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025)
- en_male_deep_01 (male deep investigative, clone, EN native rank11, seed 52011, ref en_male_deep_01.wav F0 92Hz)
- en_male_deep_02 (male warm storyteller, clone, EN native rank12, seed 52012)
- en_female_calm_01 (female warm doc, clone, EN native rank21, seed 52021)
- en_female_calm_02 (female bright articulate, clone, EN native rank22, seed 52022)
- plus uncle_fu, dylan, ryan, aiden, serena, vivian, sohee (CustomVoice)

**Änderungen (Kurz):**
- app/prosody/instruct.py: VOICEDESIGN_REF_TEXT_EN + ENGLISH_VOICEDESIGN_DESCRIPTIONS
- app/voices/registry.py: 4 Profile + order
- voices/*.json: 4 neue JSON
- cache/voice_refs/*.wav: 4 Platzhalter-Refs
- app/tts/test_double.py: voice_id-spezifische F0/Logik
- app/jobs/runner.py + app/main.py: clone-Engine generalisiert (VD-E Lock nur für vd_e, neue Stimmen design->clone)
- app/voices/desktop_benchmark.py: clone-Handling je Stimme
- tests/*: Sprache/Native-Logik angepasst (12 Stimmen)
- benchmark/english_longform_benchmark.txt: 3 Marker, 4 Abschnitte, vollständige Abdeckung
- benchmark/german_quality_analysis.md: Analyse + Empfehlungen
- voices/ENGLISH_TEST_VOICES.md: Metadaten
- README + manifest: v2.2.0

**Benchmarks:**
- Desktop-Voice (TestDouble): 12/12 Sehr gut/Empfohlen, DE-QC 96.9–98.1, EN-QC 99.7–99.8 (simuliert; Hörtest auf RTX 5060 ausstehend)
- Marker-Splitting: 3 Marker → 4 Parts, parts+full via concat, identity_check ok
- Long-Form: PDF 26 Seiten via streaming ok (vorige Phase)

**Hardware:** RTX 5060 8GB vorgesehen (bf16, sdpa, model_pool sequentiell, TQDM nicht benötigt). Tests liefen auf Linux Sandbox mit TestDouble (kein Modell).

**Nächste Schritte auf Zielmaschine:**
- Modelle laden (`install.ps1` – Qwen3-TTS-12Hz-1.7B-VoiceDesign + Base + CustomVoice + Tokenizer)
- Echte VoiceDesign-Referenzen generieren (ersetzt Platzhalter)
- RTX-5060-Benchmark: `python app/main.py --desktop-voices` + Hörtest blind (en_* vs Ryan/Aiden)
- German A/B: compound-hilfe + semantic pause vs baseline
