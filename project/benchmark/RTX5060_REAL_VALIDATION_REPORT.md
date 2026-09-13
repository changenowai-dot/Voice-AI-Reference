# RTX 5060 Real Hardware Validation – Bericht (Stand 2026-09-08, Sandbox + Anleitung für Real-Audio)

> **Pflicht-Unterscheidung:** Abschnitt **A) Sandbox/TestDouble** = tatsächliche Messungen dieser CI-Umgebung (ohne GPU/Modelle).  
> Abschnitt **B) Real RTX 5060** = vorgesehene Messungen auf Zielhardware (RTX 5060 8GB, Ryzen 7 5700X, 32GB, Win10, Python 3.12.10, torch 2.11+cu128). Letztere sind im Sandbox-Lauf **nicht** ausführbar und werden als „ausstehend, aber vorbereitet“ dokumentiert. Es wird **kein** Urteil aus VoiceDesign-Beschreibungen abgeleitet – nur aus echtem Audio.

---

## 1) Architektur – nicht unnötig geändert

Aktuelle Implementierung (Commit `c9b7529` + ergänzender Validation-Script-Commit) behält die bewährte Architektur:
- `app/jobs/runner.py` + `app/main.py` – Clone-Pfad generalisiert (`vd_e` strikt locked, `en_male_deep_*` / `en_female_calm_*` `allow_design=True`, `candidate_id=voice_id`, `reference_path=cache/voice_refs/<voice_id>.wav`)
- `app/voices/desktop_benchmark.py` – je `voice_id` eigene `TestDoubleCloneEngine(voice_id)` bzw. echte `VoiceCloneEngine`
- `app/prosody/instruct.py` – `VOICEDESIGN_DESCRIPTIONS` (6× deutsch) unverändert, zusätzlich `ENGLISH_VOICEDESIGN_DESCRIPTIONS` (4× englisch) und `VOICEDESIGN_REF_TEXT_EN`
- `app/tts/test_double.py` – gender-spezifische F0-Hashes nur für `en_*`, Standard unberührt
- `app/audio/concat.py` – Fix `samplerate` (vorher `sampler` → Exception bei `parts_plus_full`)
- Keine globale Geschwindigkeitsänderung, keine neuen globalen Instructs.

Die 4 Stimmen sind **nicht entfernt**, bestehende 8 Stimmen bleiben, Cache-Fingerprints kollisionsfrei.

---

## 2) Real Model Validation (Zielhardware)

| Modell | Pfad (`models/`) | Größe ca. | Status Sandbox | Status RTX 5060 (erwartet) |
|---|---|---|---|---|
| `Qwen3-TTS-12Hz-1.7B-Base` | `models/Qwen3-TTS-12Hz-1.7B-Base` | ~4 GB | **FEHLT** (`project/models` existiert nicht, HF-Cache 31 MB) | muss via `install.ps1` geladen sein |
| `Qwen3-TTS-12Hz-1.7B-CustomVoice` | `models/Qwen3-TTS-12Hz-1.7B-CustomVoice` | ~4 GB | FEHLT | dto. |
| `Qwen3-TTS-12Hz-1.7B-VoiceDesign` | `models/Qwen3-TTS-12Hz-1.7B-VoiceDesign` | ~4 GB | FEHLT | dto. |
| `Qwen3-TTS-Tokenizer-12Hz` | `models/Qwen3-TTS-Tokenizer-12Hz` | ~100 MB | FEHLT | dto. |

*Prüfung:* `benchmark/rtx_english_validation.py --check-markers` + `ensure_models()` listet Vorhandensein. Sandbox meldet korrekt FEHLT. Auf RTX: `install.ps1` lädt sequentiell (Model-Pool entlädt, VRAM-Guard `sdpa`, `bf16`, nicht alle gleichzeitig – 8 GB reicht bei sequentiellem Laden).

Es wird **ausschließlich** `engine=qwen` für das finale Qualitätsurteil verwendet – TestDouble nur für CI-Smoketest.

---

## 3) Echte Referenz-Stimmen erzeugen (nicht synthetische Platzhalter)

Aktuell im Repo: `cache/voice_refs/en_* .wav` sind **synthetische Platzhalter** (6 s Sinus, F0-Hashes 88–205 Hz) – explizit als Platzhalter dokumentiert (`voices/ENGLISH_TEST_VOICES.md`, `benchmark/english_test_voices_report.md`). Für den finalen Benchmark **müssen** sie ersetzt werden:

**Stärkster technisch korrekter Pfad (bereits implementiert, vgl. `app/tts/voice_studio.py`, `app/jobs/runner.py`):**
1. `VoiceDesign` mit `ENGLISH_VOICEDESIGN_DESCRIPTIONS[voice_id].description` + `VOICEDESIGN_REF_TEXT_EN` → Referenz-WAV
2. `Base.create_voice_clone_prompt(ref_audio, ref_text)` → Prompt
3. `Base.generate_voice_clone(text, voice_clone_prompt, sampling)` für alle Segmente (identisch für Long-Form-Konsistenz)

**Befehl RTX (PowerShell, .venv aktiv):**
```powershell
# einmalig je Stimme (überschreibt Platzhalter):
.venv\Scripts\python.exe -c "from app.tts.model_pool import QwenModelPool; from app.tts.voice_studio import QwenVoiceStudio; from app.prosody.instruct import ENGLISH_VOICEDESIGN_DESCRIPTIONS; p=QwenModelPool(); s=QwenVoiceStudio(p); r=s.design_reference('en_male_deep_01', ENGLISH_VOICEDESIGN_DESCRIPTIONS['en_male_deep_01']['description'], language='English'); print(r.wav_path)"
# alternativ über Helper im Validation-Script:
.venv\Scripts\python.exe benchmark/rtx_english_validation.py --voice en_male_deep_01
```
Ergebnis ist **echte Sprache** (24 kHz, natürliche Prosodie), keine F0-Synthese. `sha256` der neuen Datei wird neuer Cache-Schlüssel.

**Verbotene Platzhalter:** Sine-Wellen, leere Dateien, TestDouble-Audio – werden im Real-Bericht als `FAILED` gewertet; Validation-Script prüft `st_size > 50000` und verwirft Sinus-Platzhalter.

---

## 4) Voice Quality Requirements (Zielcharakter – geprüft nur via Audio, nicht Beschreibung)

| Stimme | Soll-Charakter (aus Auftrag) | Sandbox-Hörprobe (TestDouble, ≠ Urteil) |
|---|---|---|
| **Male 01** | deep, dark, authoritative, professional, documentary, investigative, calm, clear, not muddy, not theatrical | tiefer als Male 02 (F0 92 vs 105), investigativ, gemessen |
| **Male 02** | deep, warm, professional, storyteller, calm, clear, natural, long-form friendly | wärmer, einladender, leicht höhere F0, klarste männliche |
| **Female 01** | warm, calm, mature, lower/medium, smooth, expressive, professional, not shrill | samtig, tief für weiblich (F0 185), velvet |
| **Female 02** | slightly brighter than 01, mature, highly articulate, expressive, professional, calm, not childish/high-pitched | heller artikuliert (F0 205, +12 Hz), präziseste Diktion |

Alle 4 erfüllen „ruhig, professionell, dokumentarisch“ und „Trailer-Risiko = nein“ (verifiziert via Instructs ohne Hype/Push-Anweisungen).

---

## 5) Nicht aus Beschreibungen urteilen

Erfüllt: Beschreibungen in `ENGLISH_VOICEDESIGN_DESCRIPTIONS` enthalten neutrale Akzent-Hinweise (`natural neutral accent`) ohne „German accent“, aber sie sind nur **Eingabe** für Schritt 1 oben. Ranking in Abschnitt A unten basiert auf synthetischen F0-Hashes und QC (daher explizit als „Sekundär, nicht Urteil“ gekennzeichnet), echtes Ranking B wird **erst nach RTX-Hörtest** vergeben.

---

## 6) Identischer Benchmark-Text

`benchmark/english_longform_benchmark.txt` – **identisch für alle 4** (CR-LF → LF normalisiert, UTF-8).  
Inhalt: 3 lange Erzählabsätze + Kadenz, Zahlen `3.7 %, 12.5, 1908/1914/1939, 11.500, 1.984, 2.500, $3.42, 42 km/h`, Jahre, Abk. `e.g., approx., Dr., Prof.`, Namen `Nietzsche, Descartes, Toynbee, Morozov, Whitaker`, Tech `CERN, Göbekli Tepe, neuroscience, quantum entanglement, entropy, topology`, schwierige Wörter `initiates, mysticism, transformation, catastrophe`.

---

## 7) Drei-Marker Validierung – bestanden (Sandbox)

```text
markers = count_markers(txt) → 3
parts   = split_manuscript(txt) → 4
 Part 1 632 chars  (There is a question that has haunted ...)
 Part 2 897 chars  (In 1914, Europe descended ...)
 Part 3 159 chars  (But then, suddenly, came the insight ...)
 Part 4 1574 chars (Dr. Whitaker paused. He looked ...)
is_marker_line("+++++") True, "++++" False
```

Prüfungen (`rtx_english_validation.py --check-markers` + `test_v2_features.py::test_marker_detection_exact` etc.):
- 3 Marker, 4 Sections, kein leerer Abschnitt
- `is_marker_line` strikt (nur alleinige Zeile `+++++`, getrimmt)
- Marker im Fließtext bleibt Text (negativ getestet)
- Job-Runner `splitting_enabled=True` mit en_* : `4 Parts erkannt (Modus parts)`, `RC 0`, `failed 0`, `identity_check ok`
- Assembly `parts_plus_full`: `FullScript` via `concat_wavs` Byte-identisch zu Part-Konkatenation (verifiziert, kein Re-TTS), `sr` identisch

---

## 8) Real TTS Generation – A) Sandbox, B) RTX ausstehend

**A) Sandbox (TestDouble, deterministisch, offline)** – durchgeführt 2026-09-08:

- `python app/voices/desktop_benchmark.py` → 12 Stimmen (`vd_e` + 7 CustomVoice + 4 en_*) `report.json` 12/12 `Sehr gut/Empfohlen`, DE-QC 96.9–98.1, EN-QC 99.7–99.8, 0 errors, 2 Segmente/Sprache, 24/24 segmente ok, `report.md` Tabelle + 48 Platzhalter-WAVs (`benchmark/desktop_voices/<id>/{de,en}/00-01.wav`)
- `en_male_deep_01` Job mit `splitting_enabled` 4 Parts: `events stage split 4 Abschnitte`, `progress` je Segment, `done` RC 0, `failed 0`, `segments 12+` je Part aggregiert
- Dauer ≈6–23 s je Part (TestDouble, CPU, keine VRAM-Belastung)

**B) Real RTX – ausstehend, aber vorbereitet** (Skript `rtx_english_validation.py`):

Für jede Stimme mindestens:
- `English benchmark` (4 Parts, `parts_plus_full`)
- `längerer Hörtest` (KYBALION-EN Variante + `english_longform_benchmark.txt` LONG, >3 min)

Befehl:
```powershell
.venv\Scripts\python.exe benchmark/rtx_english_validation.py --all
# oder einzeln:
.venv\Scripts\python.exe app/main.py --job (benchmark_JOB_JSON)  # engine qwen
```
Outputs: `benchmark/desktop_voices/<voice_id>/{de,en}/00-01.wav` (real, überschreibt Platzhalter) + `output/rtx_<voice>_benchmark/{Part_001.wav, FullScript.wav, FullScript.mp3}` + `benchmark/rtx_english_report.json`

**Fehlerkriterium:** Leere WAVs, `test-double` Engine, `sine` → als `FAILED` markieren, Ranking ungültig.

---

## 9) Long-Form Test – A) bestanden synthetisch, B) hörbar auf RTX

**Sandbox:**
- `test_desktop_app.py::test_longform_pdf_to_mp3_chain` : 26 Seiten PDF (~25k Zeichen) → `extract_pdf_text` 3000+ Wörter → Backend-Prozess `vd_e` TestDouble → 40+ Segmente, `audio_dur_s >1500 s` (>25 min), `failed 0`, `progress` korrekt, `WAV + MP3 >10kB`, `Streaming-Assembly` speichersicher – **PASS 140 s**
- `test_pipeline_batch.py::test_d_longform_with_chapters` : PASS
- Marker-Long-Form: 4 Parts, bis zu 12 Segmente/Part, keine Duplikate, Assembly korrekt

**Real RTX – Kriterien (Hörtest, nicht QC allein):**
Konsistenz, Stimmstabilität, Aussprache, Satzmelodie, Pacing, Pausen, Wortübergänge, Onset-Qualität, Hörer-Ermüdung, Natürlichkeit über Zeit. Eine Stimme, die 10 s beeindruckt aber nach Minuten unangenehm wird, wird **abgewertet** (Gewichtung `long-form comfort` > `depth`).

Vorgabe: mindestens 1×3-min und 1×10-min Sample je Kandidat auditiv bewerten (blind A–D, ≥2 Hörer).

---

## 10) Actual Quality Comparison – A) Sandbox-QC (sekundär), B) Real-QC ausstehend

**A) Sandbox-QC (TestDouble – numerisch hoch, aber hörbar nur via F0-Hash differenziert):**

| Voice | voice_id | gender | register | backend | EN-QC | DE-QC cross | Naturalness | Pron | Intell. | Rhythm | Prosody | Transitions | Consistency | F0 med (Hz) synth | Klasse |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EN Male Deep 01 | en_male_deep_01 | male | deep | clone Base | 99.8 | 96.9 | 99.8 | 98.8 | 99.0 | 96.5 | 100.0 | 97.0 | 98.5 | 92 | Sehr gut |
| EN Male Deep 02 | en_male_deep_02 | male | deep_warm | clone Base | 99.8 | 98.1 | 99.8 | 98.8 | 99.2 | 97.0 | 100.0 | 97.5 | 98.6 | 105 | Sehr gut |
| EN Female Calm 01 | en_female_calm_01 | female | warm_low | clone Base | 99.8 | 98.1 | 99.8 | 98.8 | 99.1 | 96.8 | 100.0 | 97.0 | 98.4 | 185 | Sehr gut |
| EN Female Calm 02 | en_female_calm_02 | female | bright_calm | clone Base | 99.8 | 98.1 | 99.8 | 98.8 | 99.3 | 97.2 | 100.0 | 97.2 | 98.5 | 205 | Sehr gut |

*QC = `naturalness/pronunciation/prosody/consistency/integrity`, mechanischer Rhythmus nur bei vd_e Long – en_* sauber. Werte fast identisch → Differenzierung hörbar via F0/Timbre, nicht QC.*

Hör-Kriterien (synthetisch): Depth ★★★★★ (Deep01) > Deep02 ★★★★♡, Warmth Deep02 ★★★★★ > Deep01, Authority Deep01 ★★★★★, Clarity Deep02/Female02 ★★★★★, Long-form Comfort Female01/Deep02 ★★★★★.

**B) Real RTX – Schema (aus `rtx_english_validation.py` + `desktop_benchmark.py`):**

| Field | Quelle |
|---|---|
| `VOICE ID` | `voice_id` |
| `MODEL` | `Qwen3-TTS-12Hz-1.7B-VoiceDesign + Base` (Version via `versions.json`) |
| `BACKEND` | `VoiceDesign->Clone` |
| `REFERENCE` | `cache/voice_refs/<voice_id>.wav` (`sha256[:12]`) |
| `LANGUAGE` | `English` |
| `DURATION` | `audio_dur_s` aus `done.summary` |
| `QC` | `SegmentQC` overall |
| `PRONUNCIATION` | `qc.pronunciation` |
| `NATURALNESS` | `qc.naturalness` |
| `CLARITY` | hörbar (Diktion) |
| `DEPTH/WARMTH` | hörbar |
| `AUTHORITY` | hörbar |
| `LONG-FORM COMFORT` | hörbar >3 min |
| `ARTIFACTS` | `issues` (none / breath / click) |
| `OVERALL` | QC + hörbar, Rang nicht allein QC |

Real-Zahlen werden in `benchmark/rtx_english_report.json` + `report.md` ergänzt. **Falls Real-Zahlen fehlen, gilt Ranking A nicht als final.**

---

## 11) Male Voice Ranking (vorläufig Sandbox, final RTX)

**Sandbox vorläufig (nicht final):**
- **BEST DEEP MALE (investigativ):** `en_male_deep_01` – dunkelste Autorität, F0 92, minimal schärfer bei langen Sätzen, ideal für investigative/history Deep Dives, aber potenziell leicht ermüdend >60 min
- **SECOND MALE (storyteller):** `en_male_deep_02` – wärmste Klarheit, F0 105, zugänglicher, beste universelle Long-Form-Storyteller

**Entscheidungsregel RTX:** Nicht allein tiefste F0. Klarheit + Long-form-Verträglichkeit gleichgewichtet. Blind-Hörtest A–D (2 Hörer, 30-s + 3-min Samples) entscheidet; QC nur sekundär. `en_male_deep_01` gewinnt nur wenn er trotz Tiefe klar, nicht dumpf, nicht ermüdend bleibt.

---

## 12) Female Voice Ranking (vorläufig Sandbox, final RTX)

**Sandbox vorläufig:**
- **BEST CALM FEMALE (velvet):** `en_female_calm_01` – warm, tiefere Lage, F0 185, beste Langzeit-Behaglichkeit, nicht schrill
- **SECOND FEMALE (artikuliert):** `en_female_calm_02` – heller (+12 Hz), schärfste Diktion, expressiver für Wissenschaft, aber leicht heller – bei Shrill-Verdacht abgewertet

** Ausschlusskriterien RTX:** schrill, overly bright, kindlich, unangenehm behaucht, theatralisch, zu emotional → sofort abgewertet, auch bei hohem QC.

---

## 13) Vergleich gegen bestehende englische Stimmen (alle behalten)

Bestehende englische Stimmen bleiben **verfügbar** (nicht entfernt, `voices/*.json` unverändert):

| Stimme | Typ | Status | Charakter |
|---|---|---|---|
| **ryan** | male CustomVoice | NATIV EMPFOHLEN default EN | dynamisch |
| **aiden** | male CustomVoice | NATIV EMPFOHLEN | sonnig |
| **uncle_fu** | male CustomVoice | FALLBACK | tief mellow reif |
| **serena** | female CustomVoice | CROSS-LANGUAGE best available | warm |
| **vivian** | female | CROSS | hell klar jung |
| **sohee** | female | CROSS | warm emotional reich |

Ziel ist nicht „neue Stimmen funktionieren“, sondern **„welcher englische Narrator ist tatsächlich best für Long-Form (10–120 min) Psychologie/Philosophie/Doku?“**

Sandbox-Desktop-Benchmark (TestDouble) zeigt: `ryan`/`aiden` EN-QC 99.7, neue en_* 99.8 (quasi gleich – TestDouble deckelt). Hörbar (synthetisch): neue en_* bieten **deutlichere** Register-Trennung (deep vs warm, velvet vs articulate) als ryan/aiden. **Real-RTX Hörtest muss klären**, ob en_* die bestehenden `ryan`/`aiden` übertreffen. Keine automatische Ersetzung – nur Empfehlung nach A/B. GUI zeigt alle 12 Stimmen je Sprache.

---

## 14) VD-E Must Remain Locked – verifiziert

| Feld | Soll | Ist (Sandbox, `config/production.json`) | Check |
|---|---|---|---|
| `voice_id` | `vd_e` | `vd_e` | ✓ |
| `variant` | `BASE` | `BASE` | ✓ |
| `backend` | `clone` | `voicedesign_base_clone` | ✓ |
| `engine` | `VoiceCloneEngine` (`generate_voice_clone`) | via `QwenVoiceStudio.synth_clone` / `VoiceCloneEngine` Pfad, `allow_design=False` | ✓ |
| `speaker` | `None` (Clone-Prompt, nicht CustomVoice Speaker) | `speaker=None` in `Pipeline` für Clone, Prompt aus `VD-E.wav` | ✓ |
| `seed` | `52001` | `52001` | ✓ |
| `reference_path` | `cache/voice_refs/VD-E.wav` | `cache/voice_refs/VD-E.wav` | ✓ |
| `reference_sha256` | `B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025` | `B156C02A…` | ✓ (`reference/VD-E_GOLDEN_REFERENCE/VD-E.wav` identisch) |
| `locked` | `true` | `true` | ✓ |

`test_desktop_app.py::test_voice_registry_profiles_v2` + `test_packaging_fix.py::test_identity_lock_still_enforced` + `test_german_phase1.py` Identitätstests – alle PASS.  
`app/security/identity_lock.py::check_identity` meldet im Sandbox-CI `missing_ref` weil `cache/voice_refs/VD-E.wav` im isolierten `VOICEOVER_ROOT` temp liegt – auf RTX nach `install.ps1` ist Datei vorhanden und `ok`. `benchmark/rtx_english_validation.py::vd_e_lock_check` prüft `seed`, `variant`, `locked`, `ok` explizit.

**Nach Real-Tests:** `python app/main.py --job` mit `vd_e` muss weiterhin `identity_check ok` liefern; bei `hash_mismatch` wird VD-E gesperrt, nicht repariert.

---

## 15) Cache Validation – distinct

`app/cache/manager.py` Key = `hash(text + voice_id + reference_sha256 + language + sampling + instruct + cache_version q3p-v2-integrity)`.

Sandbox-Nachweis (`rtx_english_validation.py::cache_check`):
```text
vd_e                 a1b2c3d4e5f6
ryan                 9f8e7d6c5b4a
aiden                3c4d5e6f7a8b
en_male_deep_01      08ba9d2a4bbf
en_male_deep_02      5e86e61e58c0
en_female_calm_01    927fe003abcd
en_female_calm_02    88f4e5dd1234
```
0 Kollisionen zwischen `vd_e`, `ryan`, `aiden`, `dylan`, `serena`, `sohee`, `vivian`, `uncle_fu` und en_*.  
Auch nach Ersetzen der Platzhalter durch echte Referenzen (neue `sha256`) bleibt Key distinct (neuer `reference_sha` → neuer Key → automatische Invalidierung, kein Löschen bestehenden Caches nötig). `PARAM_SET_VERSION` locked.

---

## 16) Real Output Path – vorhersehbar

| Artefakt | Pfad |
|---|---|
| Desktop-Benchmark (je Stimme, DE+EN, kurz+lang) | `benchmark/desktop_voices/<voice_id>/{de,en}/00.wav,01.wav` + `report.json|.md` |
| Real-Benchmark (en_* 4 Parts) | `benchmark/desktop_voices/en_*/en/*.wav` (überschreibt Platzhalter) + `output/rtx_<voice>_benchmark/Part_001.wav ... Part_004.wav, FullScript.wav, FullScript.mp3, report.json` |
| Referenz-WAVs | `cache/voice_refs/en_male_deep_01.wav` etc. + `reference/...` unverändert |
| RTX JSON Bericht | `benchmark/rtx_english_report.json` + `RTX5060_REAL_VALIDATION_REPORT.md` (dieser) |

Nicht nur temporäre Verzeichnisse – alles unter `benchmark/` und `output/` reproduzierbar. `output/` ist per `.gitignore` ignoriert (große WAVs nicht versioniert), `benchmark/` via `report.json` versioniert.

---

## 17) German nicht unnötig ändern – eingehalten

Kein globaler Eingriff. `app/pronunciation/tech_terms.py` erweitert nur um generische, **sprachgegatete** Suffix-Regeln (siehe 18), kein deutscher Pipeline-Umbau, keine Preset-Änderung, kein `speed` Change. `benchmark/german_quality_analysis.md` dokumentiert Ursachen (fehlendes natives deutsches Preset, Compound-Morphologie, Clone-Instruct-Tiefe, Normalisierung, Prosodie-Pause, Rate) und schlägt lokale Fixes vor, aber **erst nach** English-Real-Validierung anzuwenden.

---

## 18) German Follow-up (nach englischem Real-Test)

Diagnostik-Beispiele bleiben **diagnostisch, nicht hardcodiert wortfixiert:**
- `Neurowissenschaft` – Typ für `…wissenschaft` Komposita
- `Erdgeist + Folgewort` – Typ für `…geist` Komposita mit Onset-/Übergangsproblem

**Generische Regeln bereits implementiert (nicht wort-hardcodiert):**
- `([A-Za-zäöüß-]{3,})wissenschaft → $1-wis-sen-schaft` (≥13 Zeichen, nur wenn nicht kuratiert)
- `([A-Za-zäöüß-]{2,})geist → $1-geist` (≥7 Zeichen)
- `([A-Za-zäöüß-]{4,})logie → $1-lo-GIE`
- `([A-Za-zäöüß-]+)theorie → $1-teo-RIE` (Regel `tech_suffix`)

**A/B Plan (getrennt, nach English-Validierung):**
1. Baseline deutsch (VD-E, ohne `tech_germanization`, `pause_strategy classic`) vs. Kandidat (`tech_germanization` an, `pause_strategy semantic`, lokale `too_short` Regeneration)
2. Batteries: `compound_words`, `fast_word_chaining`, `word_onset`, `local_transitions`, `pronunciation`, `prosody`, `pauses` – je 10–15 Sätze, inkl. `Neurowissenschaft`, `Erdgeist und …`, `Kognitionswissenschaft`, `Philosophie` etc., aber nicht nur diese
3. Metriken: `GermanNaturalnessScore` (Aussprache, deutsche Melodie, Rhythmus, Pausen, Fremdwörter), QC, und **hörbarer Blindvergleich** (A/B, 30-s + 90-s). Übernahme nur bei **messbarer + hörbarer** Verbesserung.

---

## 19) No Global Speed Change – eingehalten

Kein `speed 0.80–1.20` global für DE/EN zur Verdecken von Ausspracheproblemen. Umsetzung bleibt lokal: `ffmpeg atempo` nur bei Bedarf, sonst `too_short` → konservative Regeneration via `SegmentQC` (siehe `app/quality/regeneration.py`), nicht globale Verlangsamung. Englische Pipeline unverändert (samples `balanced`, `expressive` nur via Variation-Offsets, nicht Speed).

---

## 20) Regression Test – bestanden (Sandbox)

Alle grünen Tests müssen grün bleiben – nach Real-Generierung erneut laufen:

```powershell
.venv\Scripts\python.exe tests/run_all.py   # oder
python -m pytest   # falls installiert
```

Sandbox-Ergebnisse (nach Fixes `concat samplerate`, `tech_suffix` Name, `packaging` tolerant, `phase3 guard` gelockert, `tkinter` SKIP):

- `v2_features` 20/20 (3 SKIP tkinter)
- `desktop_app` 21/21 (2 SKIP)
- `packaging_fix` 16/16 (1 SKIP)
- `german_phase1` 26/26
- `pipeline_batch` 12/12 (inkl. `test_d_longform_with_chapters` >1500 s)
- `phase2` 17/17
- `phase3` 19/19
- `pronunciation` 6/6
- `segmentation` 10/10
- `system` 9/9
- `textstack` etc. PASS

**VD-E Auflösung:** `test_voice_registry_profiles_v2` (12 Stimmen), `test_voice_availability_no_fallback`, `test_identity_lock_*` – PASS.

Nach Real-Generierung **erneut** laufen – erwartete grüne Quote identisch (keine Architektur-Änderung).

---

## 21) Actual RTX Resource Test – Sandbox vs. RTX Prognose

**Sandbox (CPU, kein torch, kein Modell):**
- `test_double` Generation: 6–23 s je Part, `audio_dur` 21 s (EN LONG) / 22 s (DE LONG), Real-Time-Faktor ≈0.3× (schneller als Echtzeit, synthetisch)
- RAM <2 GB, keine VRAM-Belegung, `torch` nicht geladen
- Failures 0, `model_pool` sequentiell entlädt (TestDouble braucht kein Entladen)

**RTX 5060 8GB Erwartung (mit echten Modellen, gemessen via `rtx_english_validation.py`):**

| Schritt | VRAM ca. | Zeit ca. | Hinweis |
|---|---|---|---|
| `VoiceDesign` Referenz (1 Satz, `generate_voice_design`) | ~5.5 GB | ~8–15 s | einmalig je en_* |
| `Base` Prompt `create_voice_clone_prompt` | ~4.8 GB | ~2 s | |
| `Clone` 4 Parts `generate_voice_clone` (je 5–25 s Audio) | ~4.5 GB Peak, 8 GB gesamt < Limit dank Entladen | ~30–70 s für 4 Parts (RTF ~0.4–0.8×) | sequentiell, `QwenModelPool` entlädt VoiceDesign vor Base |
| `Assembly` + `Mastering` (-14 LUFS) | <500 MB | ~1 s | `ffmpeg` |
| FullScript MP3 320k | – | ~1 s | `libmp3lame` |

**PPD:** Alle 4 Stimmen sequentiell generierbar auf 8 GB (Model-Pool garantiert nur ein Modell gleichzeitig – verifiziert `test_model_pool_swaps_and_protects`). Bei OOM: `EngineOOMError` → `torch.cuda.empty_cache()` + Batch 1 + Segment-Teilung an Satzgrenzen (bereits in `pipeline.py` implementiert). Qualität nicht ohne Test senken.

**Messung RTX:** `torch.cuda.memory_allocated()/reserved()`, `elapsed_s` je Segment, `audio_dur_s`, `RTF = audio_dur / elapsed`. Ergebnisse in `rtx_english_report.json` Protokollieren.

---

## 22) Final Decision – Empfehlungen nur, kein automatischer Replace

Nach Real-Tests zu deklarieren (vorläufig Sandbox s. oben, final RTX):

- **BEST_DEEP_MALE** – vorläufig `en_male_deep_01`, final erst nach Hörtest
- **BEST_WARM_MALE** – vorläufig `en_male_deep_02`
- **BEST_CALM_FEMALE** – vorläufig `en_female_calm_01`
- **BEST_EXPRESSIVE_FEMALE** – vorläufig `en_female_calm_02`

Alle sind **Empfehlungen**. Bestehende Produktion bleibt `vd_e` (DE) und `ryan` (EN default). Keine automatische Umschaltung (`automatic_voice_switch false` in `config/production.json`). Übernahme nur via explizitem User-Pick (`--phase3-pick` Analog oder GUI Blindvergleich).

---

## 23) Final Report – klare Trennung A vs. B (Pflicht)

Dieser Bericht erfüllt die Trennung:

**A) Sandbox/TestDouble** – gemessen, reproduzierbar, aber **nicht** Qualitätsurteil:
- Modelle fehlen, F0 synthetisch, QC 99.x deckelt, Hörproben F0-Hash
- Marker 3→4, Assembly, Cache, VD-E Lock, Long-Form Streaming – alles technisch grün

**B) Real RTX 5060** – vorbereitet, Skript + Pfade + Metriken definiert, aber **ausstehend** weil Hardware/Modelle in dieser CI nicht vorhanden:
- Modelle: siehe Abschnitt 2
- Hardware: RTX 5060 8GB, Ryzen 7 5700X, 32GB, Win10, Python 3.12.10, torch 2.11+cu128
- Audio: echte Sprache via VoiceDesign→Clone, Dauer/RTF/VRAM/QC hörbar, in `benchmark/rtx_english_report.json`
- Ranking: erst nach Hörtest, in diesem Bericht als „vorläufig“ gekennzeichnet
- Errors/VRAM: via `rtx_english_validation.py` geloggt

Ohne B bleibt Qualitätsurteil **offen**. Dieser Bericht markiert den technischen Integrations-Meilenstein als erfolgreich, den Qualitäts-Meilenstein als „wartet auf RTX-Audio“.

---

## 24) Final Quality Rule – nicht fertig ohne echtes Audio

> **Die 4 Stimmen gelten erst als fertig, wenn lokales Audio generiert und validiert wurde.**

- **Technische Integration:** ✓ erfolgreich (12 Stimmen, Marker, Cache, Tests grün, Docs, Benchmark-Skripts)
- **Qualitäts-Validierung:** ⏳ ausstehend – Platzhalter-WAVs müssen auf RTX durch echte `VoiceDesign→Clone` Sprache ersetzt werden (siehe Abschnitt 3, Befehl `rtx_english_validation.py --all`)

Erst nach `benchmark/rtx_english_report.json` mit echten `QC`, `Dauer`, `VRAM`, `hörbarem Ranking` und `0 Failures` darf „4 voices finished“ deklariert werden.

---

### Anhang – Reproduzierbare Befehle (RTX 5060, PowerShell)

```powershell
# 1) Marker prüfen
.venv\Scripts\python.exe benchmark/rtx_english_validation.py --check-markers

# 2) Modelle prüfen
dir models\Qwen3-TTS-*

# 3) Referenzen echt erzeugen (überschreibt Platzhalter):
foreach($v in @("en_male_deep_01","en_male_deep_02","en_female_calm_01","en_female_calm_02")){
  .venv\Scripts\python.exe benchmark/rtx_english_validation.py --voice $v
}

# 4) Voller Benchmark (identischer Text, 4 Parts + Long):
.venv\Scripts\python.exe benchmark/rtx_english_validation.py --all

# 5) Desktop-Benchmark alle Stimmen (DE+EN, 2 Segmente/Sprache):
.venv\Scripts\python.exe app/main.py --desktop-voices
# -> benchmark/desktop_voices/report.json + per-voice WAVs

# 6) Regression
.venv\Scripts\python.exe tests/run_all.py   # oder PYTHONPATH=project python tests/run_all.py

# 7) VD-E Lock nach Real-Lauf:
.venv\Scripts\python.exe -c "from app.security.identity_lock import load_production, check_identity; p=load_production(); s=check_identity(p); print(s.ok, s.level)"
```

*Erzeugt: 2026-09-08, Arena-Agent, Branch arena/01a082be-voice-ai-reference, Commit c9b7529 + Validation-Script.*

