# RECOVERY MATRIX — Premium English Voices

**Datum:** 2026-09-10 (Recovery-Zyklus)  
**Arbeitsbranch:** `arena/01a08d48-voice-ai-reference` (ausgehend von `agent-ready` @ `801c0f4`)  
**Suchraum:** alle Branches (6 Remote-Branches fetched), alle Tags, komplette Git-History (30+ Commits), Reflog, fsck --full --unreachable, lokales Dateisystem, /tmp, /var/tmp, Pack-Dateien  
**Golden Reference VD-E:** INTACT — SHA256 `B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025` ✓

## Status-Legende

- **ORIGINAL_RECOVERED** — Original-Datei aus dem früheren Agent-Lauf unverändert im Git-Repositorium oder lokal gefunden.
- **ARENA_PLACEHOLDER** — Vorhandene Datei ist ein Arena-TTS-Platzhalter (Sandbox-Add-Voice), KEIN Qwen-VoiceDesign-Output.
- **MISSING** — Nicht auffindbar in Branches/History/Dateisystem; vermutlich nie erzeugt (Qwen-GPU-Lauf auf RTX 5060 steht noch aus).
- **TEST_OUTPUT** — Vorhanden, aber es handelt sich um ein älteres/anderes Test-Audio (nicht diese Stimme).

## Kern-Fund

**Ehrliche Diagnose:** Die 7 Premium-Stimmen wurden im Sandbox-Kontext **nie auf Qwen GPU generiert**. Alle im Repository vorhandenen Audiodateien sind Arena-TTS-Platzhalter-MP3s (60–85 KB, erzeugt via `add_voice`/`generate_speech` in Arena). Die vom Menschen bewerteten Hörproben selbst sind aber als **originale MP3s erhalten geblieben**. Echte Qwen VoiceDesign WAVs (`cache/voice_refs/<id>.wav`) oder Qwen-Clones existieren für keine der 7 Premium-Stimmen in der Git-Historie — dies erfordert den RTX-5060-Lauf, der vom vorigen Agenten architektonisch vollständig vorbereitet wurde (`project/tools/reproduce_voice.py`).

Rezepte/Seeds/Prompts/Referenztexte/Sampling-Parameter sind **vollständig original erhalten** (24 Rezepte, Validator `OK 24 recipes ExitCode 0`).

## Matrix

| Voice | Seed | Recipe JSON | VoiceDesign Desc/Prompt | Ref Text | Qwen VD Reference WAV | Ref WAV SHA256 | Clone Conditioning | Arena Audition MP3 (original) | Audition MP3 SHA256 | Generated Qwen Audio | Benchmarks | Fundort | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **voice-09**<br>`en_male_warm_storytelling_authoritative_02`<br>_locked_human_favorite_ | 52018 | ORIGINAL_RECOVERED<br>`project/voices/en_male_warm_storytelling_authoritative_02.json` | ORIGINAL_RECOVERED | ORIGINAL_RECOVERED (identischer Text: "Every discovery begins...") | **MISSING** — nie auf Qwen erzeugt (Sandbox ohne GPU) | MISSING | MISSING (würde in cache/metadata/ liegen — gitignored; Rezept dokumentiert) | ORIGINAL_RECOVERED<br>`project/benchmark/fast_audition/04_warm_storytelling_authoritative_02.mp3`<br>(60429 bytes) | `AB9C78D32E7A3631EC9336E8D8C8F11A6D9AFFB6C787493C31CF9D460DB9B697` | **MISSING** — nur Arena-Placeholder; echter Qwen-Clone steht aus | MISSING (nur Arena-Audition; keine Qwen-Benchmarks) | Git: agent-ready + arena/01a082be @ 801c0f4/8340c5a (MP3s) / Rezepte in voice_generation_recipes.json + voices/*.json; KEINE WAVs in irgendeinem Branch | ARENA_PLACEHOLDER (Audition MP3 ORIGINAL_RECOVERED; Qwen-Output MISSING) |
| **voice-12**<br>`en_male_velvet_baritone_01`<br>_locked_human_favorite_ | 52021 | ORIGINAL_RECOVERED<br>`project/voices/en_male_velvet_baritone_01.json` | ORIGINAL_RECOVERED | ORIGINAL_RECOVERED (identischer Text: "Every discovery begins...") | **MISSING** — nie auf Qwen erzeugt (Sandbox ohne GPU) | MISSING | MISSING (würde in cache/metadata/ liegen — gitignored; Rezept dokumentiert) | ORIGINAL_RECOVERED<br>`project/benchmark/fast_audition/07_velvet_baritone.mp3`<br>(61389 bytes) | `3B238F1F95B158D647991E0B27F127256A4F882E01C280EEA8ADF24EB69D7003` | **MISSING** — nur Arena-Placeholder; echter Qwen-Clone steht aus | MISSING (nur Arena-Audition; keine Qwen-Benchmarks) | Git: agent-ready + arena/01a082be @ 801c0f4/8340c5a (MP3s) / Rezepte in voice_generation_recipes.json + voices/*.json; KEINE WAVs in irgendeinem Branch | ARENA_PLACEHOLDER (Audition MP3 ORIGINAL_RECOVERED; Qwen-Output MISSING) |
| **voice-22**<br>`en_male_deep_authoritative_scholar_01`<br>_saved_human_shortlist_ | 52031 | ORIGINAL_RECOVERED<br>`project/voices/en_male_deep_authoritative_scholar_01.json` | ORIGINAL_RECOVERED | ORIGINAL_RECOVERED (identischer Text: "Every discovery begins...") | **MISSING** — nie auf Qwen erzeugt (Sandbox ohne GPU) | MISSING | MISSING (würde in cache/metadata/ liegen — gitignored; Rezept dokumentiert) | ORIGINAL_RECOVERED<br>`project/benchmark/fast_audition_round02/05_deep_authoritative_scholar.mp3`<br>(69261 bytes) | `243389F0AA3144AA078E32C035236C259E93FA27B1FD7294337E7BC75B6DAA99` | **MISSING** — nur Arena-Placeholder; echter Qwen-Clone steht aus | MISSING (nur Arena-Audition; keine Qwen-Benchmarks) | Git: agent-ready + arena/01a082be @ 801c0f4/8340c5a (MP3s) / Rezepte in voice_generation_recipes.json + voices/*.json; KEINE WAVs in irgendeinem Branch | ARENA_PLACEHOLDER (Audition MP3 ORIGINAL_RECOVERED; Qwen-Output MISSING) |
| **voice-23**<br>`en_male_mature_documentary_natural_01`<br>_saved_human_shortlist_ | 52032 | ORIGINAL_RECOVERED<br>`project/voices/en_male_mature_documentary_natural_01.json` | ORIGINAL_RECOVERED | ORIGINAL_RECOVERED (identischer Text: "Every discovery begins...") | **MISSING** — nie auf Qwen erzeugt (Sandbox ohne GPU) | MISSING | MISSING (würde in cache/metadata/ liegen — gitignored; Rezept dokumentiert) | ORIGINAL_RECOVERED<br>`project/benchmark/fast_audition_round02/06_mature_documentary_natural.mp3`<br>(63501 bytes) | `3C0A63C649C22A60D0A3BE6533B832459EB698E11F7AD7920E67F125F959450C` | **MISSING** — nur Arena-Placeholder; echter Qwen-Clone steht aus | MISSING (nur Arena-Audition; keine Qwen-Benchmarks) | Git: agent-ready + arena/01a082be @ 801c0f4/8340c5a (MP3s) / Rezepte in voice_generation_recipes.json + voices/*.json; KEINE WAVs in irgendeinem Branch | ARENA_PLACEHOLDER (Audition MP3 ORIGINAL_RECOVERED; Qwen-Output MISSING) |
| **voice-24**<br>`en_male_deep_clear_insightful_01`<br>_saved_human_shortlist_ | 52033 | ORIGINAL_RECOVERED<br>`project/voices/en_male_deep_clear_insightful_01.json` | ORIGINAL_RECOVERED | ORIGINAL_RECOVERED (identischer Text: "Every discovery begins...") | **MISSING** — nie auf Qwen erzeugt (Sandbox ohne GPU) | MISSING | MISSING (würde in cache/metadata/ liegen — gitignored; Rezept dokumentiert) | ORIGINAL_RECOVERED<br>`project/benchmark/fast_audition_round02/07_deep_clear_insightful.mp3`<br>(69069 bytes) | `5ABB841EDF0E9B29F260FB1ECA8CC5DE8E18E52CF924D537F36D84CFF8C0522D` | **MISSING** — nur Arena-Placeholder; echter Qwen-Clone steht aus | MISSING (nur Arena-Audition; keine Qwen-Benchmarks) | Git: agent-ready + arena/01a082be @ 801c0f4/8340c5a (MP3s) / Rezepte in voice_generation_recipes.json + voices/*.json; KEINE WAVs in irgendeinem Branch | ARENA_PLACEHOLDER (Audition MP3 ORIGINAL_RECOVERED; Qwen-Output MISSING) |
| **voice-25**<br>`en_male_warm_grounded_humanist_01`<br>_saved_human_shortlist_ | 52034 | ORIGINAL_RECOVERED<br>`project/voices/en_male_warm_grounded_humanist_01.json` | ORIGINAL_RECOVERED | ORIGINAL_RECOVERED (identischer Text: "Every discovery begins...") | **MISSING** — nie auf Qwen erzeugt (Sandbox ohne GPU) | MISSING | MISSING (würde in cache/metadata/ liegen — gitignored; Rezept dokumentiert) | ORIGINAL_RECOVERED<br>`project/benchmark/fast_audition_round02/08_warm_grounded_humanist.mp3`<br>(70029 bytes) | `3ED77F8E868044E4B27B79F872A7D1C1CED6F1987B4FB83E8A0E80CEEA110A31` | **MISSING** — nur Arena-Placeholder; echter Qwen-Clone steht aus | MISSING (nur Arena-Audition; keine Qwen-Benchmarks) | Git: agent-ready + arena/01a082be @ 801c0f4/8340c5a (MP3s) / Rezepte in voice_generation_recipes.json + voices/*.json; KEINE WAVs in irgendeinem Branch | ARENA_PLACEHOLDER (Audition MP3 ORIGINAL_RECOVERED; Qwen-Output MISSING) |
| **voice-27**<br>`en_male_extremely_natural_deep_conversational_01`<br>_saved_human_shortlist_ | 52036 | ORIGINAL_RECOVERED<br>`project/voices/en_male_extremely_natural_deep_conversational_01.json` | ORIGINAL_RECOVERED | ORIGINAL_RECOVERED (identischer Text: "Every discovery begins...") | **MISSING** — nie auf Qwen erzeugt (Sandbox ohne GPU) | MISSING | MISSING (würde in cache/metadata/ liegen — gitignored; Rezept dokumentiert) | ORIGINAL_RECOVERED<br>`project/benchmark/fast_audition_round02/10_extremely_natural_deep_conversational.mp3`<br>(68109 bytes) | `454EF422E6838D3715CED93607ADFD1CAE8DF24C6DD0FF6E4C1D81BD415EDE77` | **MISSING** — nur Arena-Placeholder; echter Qwen-Clone steht aus | MISSING (nur Arena-Audition; keine Qwen-Benchmarks) | Git: agent-ready + arena/01a082be @ 801c0f4/8340c5a (MP3s) / Rezepte in voice_generation_recipes.json + voices/*.json; KEINE WAVs in irgendeinem Branch | ARENA_PLACEHOLDER (Audition MP3 ORIGINAL_RECOVERED; Qwen-Output MISSING) |

## Golden Reference VD-E — Geschützt

| Asset | Pfad | SHA256 | Status |
|---|---|---|---|
| Golden Reference WAV | `project/VD-E_GOLDEN_REFERENCE/VD-E.wav` | `B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025` | ORIGINAL_RECOVERED — UNVERÄNDERT |
| Redundante Kopie | `reference/VD-E_GOLDEN_REFERENCE/VD-E.wav` | `B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025` | ORIGINAL_RECOVERED — identisch |
| Runtime-Kopie `cache/voice_refs/VD-E.wav` | `project/cache/voice_refs/VD-E.wav` | — | MISSING (wird zur Laufzeit aus Golden Reference abgeleitet, NIE überschrieben) |
| Recipe/Production | `project/config/production.json` + `project/voices/vd_e.json` | seed=52001 mode=voicedesign_base_clone variant=BASE sampling_set=expressive | ORIGINAL_RECOVERED |
| Identity-Lock | `project/app/security/identity_lock.py` | prüft SHA256, verbietet Überschreibung | ORIGINAL_RECOVERED |
| VD-E Test-Outputs (Sep 2026) | `project/test_output_vde_*.wav/.mp3` (nur in älteren Branches/im Pack) | diverse RIFF/ID3 | TEST_OUTPUT (Vergleichsausgaben, keine neue Referenz) |

## Weitere historische Audio-Funde (keine der 7 Premium-Stimmen)

| Fund | In Branch | Commit | Bedeutung |
|---|---|---|---|
| `project/benchmark/rtx_real_audio/en_male_deep_0{1,2}_part*.mp3` | arena/01a082be @ 8340c5a | 8340c5a | Ältere EN-Teststimmen (Phase vor den 7 Premium), NICHT voice-09/12/22-27 |
| `project/benchmark/rtx_real_audio/en_male_calm_deep_01_part*.mp3` | arena/01a082be @ 8340c5a | 8340c5a | Vorgängerstimme, nicht in den 7 Premium |
| `project/benchmark/rtx_real_audio/en_male_warm_storytelling_authoritative_01_part*.mp3` | arena/01a082be @ 8340c5a | 8340c5a | Vorgänger von voice-09 (01 vs. 02), **NICHT** voice-09 |
| `project/benchmark/rtx_real_audio/en_female_calm_{01,02}_part*.mp3` | arena/01a082be @ 8340c5a | 8340c5a | Female Backup-Stimmen (preserved) |
| `project/benchmark/male_deep_candidates/01_ultra_calm_deep/part[1-4].mp3` | arena/01a082be @ 8340c5a | 8340c5a | voice-06 (rejected) |
| `project/benchmark/male_deep_candidates/02_dark_documentary_gravitas/part[1-4].mp3` | arena/01a082be @ 8340c5a | 8340c5a | voice-07 (rejected) |
| `project/test_output_vde_*.wav/.mp3` | Anfangscommit 0ef7279 | 0ef7279 | VD-E-Testausgaben (listpause/tempo/plus_split/comma_enum) — nicht Golden |
| `project/benchmark/ATTENTION_AB_20260903/*.wav` | Anfangscommit 0ef7279 | 0ef7279 | SDPA vs Flash Attention A/B-Vergleiche VD-E |

## Explizit NICHT gefunden

- `project/test_output_vde_qwen_real_clone.wav` (in Dokumentation erwähnt, aber nie in Git committed)
- `cache/voice_refs/en_male_*.wav` für eine der 7 Premium-Stimmen
- Qwen VoiceDesign WAV-Referenzen für eine der 7 Premium-Stimmen
- Serialized Clone-Prompts (liegen in `cache/metadata/`, gitignored)
- Segment-Cache (`cache/audio/`)
- Qwen-Modelle unter `models/` (ca. 4 GB/Modell, nicht in Git)
- HuggingFace-Cache auf dem Sandbox-System
- Dangling-Blobs mit RIFF/ID3-Magic in Git
- Audiomaterial in /tmp, /var/tmp oder anderen Workspace-Verzeichnissen

## Reproduktionspfad (echt Qwen, RTX 5060 — vorbereitet, nicht ausgeführt)

Pfad ist im vorigen Agent-Lauf vollständig vorbereitet worden:

```powershell
# Einmalig auf RTX 5060:
powershell -ExecutionPolicy Bypass -File project/SETUP.ps1

# Pro Stimme (Beispiel voice-09):
.venv\Scripts\python.exe project/tools/reproduce_voice.py --reproduce `
  --voice-id en_male_warm_storytelling_authoritative_02 --language English `
  --text "Every discovery begins with a question..."
```

Rezepte sind 100%% vollständig: seed, VoiceDesign-Prompt, Referenztext, Sampling-Parameter, Clone-Anweisungen sind dokumentiert. Das Ergebnis ist reproduzierbar aber **nicht bit-identisch** zu den Audio-Merkmalen, die der Benutzer in der Sandbox-Arena-Hörprobe bewertet hat — Arena-TTS und Qwen3-TTS sind unterschiedliche Backends.

## Unmittelbar nächste Schritte (ohne Zerstörung vorhandener Assets)

1. Runtime-Kopie von VD-E kontrolliert aus der Golden Reference ablegen (Read-Only-Copy, SHA256-Check vor jedem Lauf).
2. Keine der 7 Premium-Stimmen überschreiben, keine Seeds ändern, keine MP3s durch neue Placeholder ersetzen.
3. Qwen-Modelle via `install.ps1` laden.
4. Für jede der 7 Stimmen auf RTX 5060 echte VoiceDesign→Clone-Pipeline ausführen (seed beibehalten).
5. Neue Outputs als `REPRODUCED` markieren — niemals als `ORIGINAL_RECOVERED`.
6. Deutsche Prosodie/Aussprache verbessern; 4 weitere professionelle English-Narrator-Stimmen entwickeln.
7. Vollständige Regressionstests.
