# Voice Generation Architecture — VoiceDesign → Clone (Qwen3-TTS 1.7B) — Reproducible Pipeline

**Stand:** 2026-09-09 · **Branch:** `arena/01a082be-voice-ai-reference` · **Hardware-Ziel:** RTX 5060 8 GB (VRAM-Guard), CPU-Fallback
**Kern-Garantie:** Keine globale TTS-Änderung ohne Backup + Benchmark; VD-E `B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025` LOCKED

Dieser Leitfaden erklärt einem neuen AI-Agenten **exakt**, wie die guten English-/German-Voices dieser Repo entstanden sind — und wie sie reproduzierbar neu erzeugt werden — **ohne zu raten**. Unbekanntes wird als `unknown / not recorded` markiert und mit Code-Stelle belegt.

---

## A. VoiceDesign — Idee → Text-Prompt

**Zweck:** Aus natürlicher Beschreibung eine *hörbare* Referenz erzeugen, die später geclont wird.

- **Beschreibungstexte:** `project/app/prosody/instruct.py`
  - `VOICEDESIGN_DESCRIPTIONS` (`vd_a`…`vd_f`, z. B. `vd_e` *reifer, ruhiger, rauchiger Hörbuchsprecher …*)
  - `ENGLISH_VOICEDESIGN_DESCRIPTIONS` (`en_male_deep_01`, `en_male_deep_02`, …) — vollständige englische Prompts (siehe Instruct-Datei)
  - **Neue Premium-Voices dieser Session:** Beschreibungen liegen **direkt in** `project/voices/<voice_id>.json` → Feld `description` — z. B. `warm storytelling authoritative – superior version …` (voice-09) oder `deep authoritative scholar – clear, grounded …` (voice-22)
- **Referenztexte (kurz, stilprägend):**
  - Deutsch: `VOICEDESIGN_REF_TEXT_DE` in `instruct.py` → *„Es gibt ein Buch, das niemand geschrieben haben will. … Wer bestimmt, was wirklich ist?“*
  - Englisch: `VOICEDESIGN_REF_TEXT_EN` → *„There is a book no one claims to have written. … Who decides what is real?“*
  - **Fast-Audition-Hörtext (identisch, 15–25 s) ist davon getrennt:** Für English *„Every discovery begins with a question…“* (33 Worte), für German *„Jede Entdeckung beginnt mit einer Frage…“* — diese Texte sind **nicht** der VoiceDesign-Referenztext, sondern der **Audition-Render-Text** für den menschlichen Vergleich.
- **Parameter:** `project/app/tts/sampler.py` → `PARAM_SETS["balanced"]` = `{do_sample:true, temp 0.70, top_k 50, top_p 0.90, rep_pen 1.05}`; `CACHE_VERSION="q3p-v2-integrity"`; Seeds s. u.
- **Code:** `project/app/tts/voice_studio.py:QwenVoiceStudio.design_reference(candidate_id, description, language)`
  ```python
  model = pool.get("voicedesign")  # Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign via QwenModelPool
  for attempt in 1..3:
      torch.manual_seed(5100 + attempt*7)
      wavs, sr = model.generate_voice_design(text=ref_text, language=language, instruct=description, **params_for_set("balanced"))
  write_wav(VOICE_REFS_DIR / f"{candidate_id}.wav", wav, sr, 16bit)
  ```
  Log: `VoiceDesign-Referenz {candidate_id} -> {out} ({dur}s)`

### English Shortlist dieser Repo (konkret)

| voice_id | seed | language | gender | description (VoiceDesign-Prompt) |
|---|---|---|---|---|
| en_male_warm_storytelling_authoritative_02 (A, LOCKED, voice-09) | 52018 | English | male | warm storytelling authoritative – superior version of current favorite, deep warm authority clarity |
| en_male_velvet_baritone_01 (B, LOCKED, voice-12) | 52021 | English | male | velvet baritone – deep exceptionally smooth warm rich rounded |
| en_male_deep_authoritative_scholar_01 (C, SHORTLIST, voice-22) | 52031 | English | male | deep authoritative scholar – clear, grounded, knowledgeable, steady and reassuring |
| en_male_mature_documentary_natural_01 (D, SHORTLIST, voice-23) | 52032 | English | male | mature documentary natural – authentic, lived-in, calm, documentary-grade believability |
| en_male_deep_clear_insightful_01 (E, SHORTLIST, voice-24) | 52033 | English | male | deep clear insightful – intelligent, articulate, lucid, gentle authority |
| en_male_warm_grounded_humanist_01 (F, SHORTLIST, voice-25) | 52034 | English | male | warm grounded humanist – empathetic, sincere, mature, comforting and human |
| en_male_extremely_natural_deep_conversational_01 (G, SHORTLIST, voice-27) | 52036 | English | male | extremely natural deep conversationalist – hyper-natural, effortless, human rhythm, long-form fatigue-free |

Rejected but retained: voice-18/19/20/21/26 (`rejected_human`, not production candidate).

### German Shortlist dieser Repo (konkret, fast_audition_de — 7er, davon 3 verifiziert)

| voice_id | seed | pos | gender | description | status |
|---|---|---|---|---|---|
| de_male_warm_storytelling_authoritative_01 (BEST MALE, voice-30) | 53003 | Pos3 | male | warm storytelling authority – tief, warm, menschlich, erzählerisch | saved_human_shortlist, current_best_male_german true, verifiziert |
| de_male_deep_natural_conversational_01 (BETTER male, voice-32) | 53005 | Pos5 | male | deep natural conversational – tief, natürlich, direkt, modern | saved_human_shortlist |
| de_female_deep_warm_documentary_01 (BEST FEMALE, voice-33) | 53011 | Pos6 | female | deep warm documentary – warm, tief, ruhig, reif | saved_human_shortlist, current_best_female_german true, verifiziert |
| de_female_deep_calm_intelligent_01 (Backup, voice-34) | 53012 | Pos4 (second) | female | deep calm intelligent – tief, ruhig, intelligent | good_archived (backup, nicht active, human_selected true, production_candidate false) |
Rejected German: voice-28/29/31 (`rejected_human`, pos1/2/4 der fast_audition_de).

### German Recovery Audition 2026-09-09 — 7 NEW CANDIDATES (identisch `Jede Entdeckung...`, 15-25 s, arena_placeholder, 1 Clip/Voice)

| voice_id | seed | pos | gender | concept |
|---|---|---|---|---|
| de_male_deep_gravitas_02 (voice-35) | 53013 | Pos1 | male | deep gravitas — sehr tief, wuchtig, seriös, dokumentarisch |
| de_male_warm_calm_authoritative_02 (voice-36) | 53014 | Pos2 | male | warm calm authoritative 02 — warm, ruhig, autoritativ |
| de_male_intellectual_precise_01 (voice-37) | 53015 | Pos3 | male | intellectual precise — intelligent, präzise, analytisch |
| de_male_natural_storyteller_01 (voice-38) | 53016 | Pos4 | male | natural storyteller — natürlich, erzählerisch, nahbar |
| de_male_cinematic_restrained_01 (voice-39) | 53017 | Pos5 | male | cinematic restrained — filmisch, zurückhaltend, tief |
| de_female_warm_empathetic_01 (voice-40) | 53018 | Pos6 | female | warm empathetic — warm, empathisch, nahbar |
| de_female_clear_natural_01 (voice-41) | 53019 | Pos7 | female | clear natural — klar, natürlich, hell |

Alle 7: `status new_candidate_german_recovery`, `arena_placeholder`, `reproduction_status prepared_not_runtime_verified`, **exhaustive Suche ergab 0 historische RECOVERED** (daher NEW). Human Rank bislang blank, pending intensiver Test. Letzter 9er-Lauf (Pos3/5/6) konnte nach vollständiger `benchmark/*`+git+JSON-Suche nicht zweifelsfrei rekonstruiert werden (kein Verzeichnis mit 9 deutschen MP3s) — daher kein Auto-Promote; bestehende verifizierte BEST (voice-30/32/33) bleiben unverändert (vgl. MANIFEST "Offene Rekonstruktion").

### English Female Calm 2 (preserved)

| voice_id | gender | provenance | note |
|---|---|---|---|
| en_female_calm_01 | female | preserved | ACTIVE female option, nicht Teil der 7-male Shortlist |
| en_female_calm_02 | female | preserved | s. o. |

---

## B. Reference Creation — VoiceDesign-WAV → `cache/voice_refs/`

**Pfad:** `project/app/paths.py:VOICE_REFS_DIR = Path(VOICEOVER_REFS_DIR or CACHE_DIR / "voice_refs")` → real: `cache/voice_refs/{candidate_id}.wav`
- **VD-E Spezialfall:** `cache/voice_refs/VD-E.wav` + goldene Kopie `project/VD-E_GOLDEN_REFERENCE/VD-E.wav` (998 484 Bytes, SHA256 `B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025` aus `project/VD-E_GOLDEN_REFERENCE/manifest.json` + `project/config/production.json` `reference_sha256`). **Niemals neu designen** (`allow_design=False` in `VoiceCloneEngine`, §12).
- **Format:** WAV 16-bit via `project/app/audio/io.py:write_wav` (im Cache-Manager alternativ 32-bit float für Segmente).
- **Provenance-Unterschied (ehrlich):**
  - **Production (RTX 5060):** echte Qwen-WAV via `generate_voice_design` (RTX 5060, bf16).
  - **Sandbox dieser Repo (Arena):** **kein Qwen-Modell geladen** (`nvidia-smi not found`, `torch not installed` bis Benchmark), daher wurden die **Benchmark-MP3s in `project/benchmark/fast_audition*/*.mp3` via Arena TTS `add_voice`/`generate_speech` als `arena_placeholder` erzeugt** — sie sind **Audition-Renders**, nicht `cache/voice_refs/*.wav`. Konzept, Seed und Beschreibung bleiben erhalten und werden später auf echter Qwen-Pipeline reproduziert (s. §G).

---

## C. Clone — Referenz → wiederverwendbarer Prompt

**Code:** `project/app/tts/voice_studio.py:QwenVoiceStudio.build_clone_prompt(ref: VoiceRef)` und `project/app/tts/qwen_engine.py:VoiceCloneEngine`
```python
key = f"{ref.candidate_id}:{ref.wav_path.stat().st_mtime}"
if key in _clone_prompts: return cached
prompt = model.create_voice_clone_prompt(ref_audio=str(ref.wav_path), ref_text=ref.ref_text, x_vector_only_mode=False)
# model = pool.get("base")  # Qwen/Qwen3-TTS-12Hz-1.7B-Base
```
- **Model-Pool:** `project/app/tts/model_pool.py:QwenModelPool` mit `MODEL_REPOS={"base": "Qwen/Qwen3-TTS-12Hz-1.7B-Base", "customvoice": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", "voicedesign": ...}` — Auflöslogik: zuerst `MODELS_DIR/<name>/model.safetensors`, dann `MODELS_DIR/hf/hub/...` (HF-Cache), sonst `FileNotFoundError`.
- **VD-E:** `allow_design=False` — Referenz MUSS existieren; kein Re-Design.
- **Parameter:** `x_vector_only_mode=False` (voller Prompt). Cache-Key: candidate_id + mtime.

---

## D. Generation — Text → Audio je Segment (Langform-konsistent)

**Zwei Engine-Pfade:**

1. **Produktion Clone:** `QwenVoiceStudio.synth_clone(prompt, request: SynthesisRequest)` → `model.generate_voice_clone(text, language, voice_clone_prompt=prompt, **gen_kwargs)`
2. **CustomVoice (Baseline):** `QwenTTSEngine.synthesize(request)` → `model.generate_custom_voice(text, language, speaker, instruct, **gen_kwargs)`

**Request:** `project/app/tts/engine_base.py:SynthesisRequest(text, language, speaker, instruct, sampling, seed, max_seconds_hint)`

**Sampling:** `project/app/tts/sampler.py`:
- `PARAM_SETS` — balanced / stable / expressive / conservative (s. A)
- `params_for_set(name, overrides)` — Basis + Overrides
- `variation_for_attempt(attempt, base)` — Versuch1 unverändert, Versuch2 temp-0.15, Versuch3+ konservativ
- `max_new_tokens_for(seconds, headroom=5.0)` → `(sec+5)*12.5+64` (12.5 Tokens/s bei 12 Hz-Tokenizer)
- `CACHE_VERSION="q3p-v2-integrity"` — alte Cache-Einträge werden stillschweigend invalidiert.

**Seed-Reproduzierbarkeit:** `torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)` vor jeder Synthese (`qwen_engine.py:79`, `voice_studio.py:79/167`).

**Globale Defaults (nicht ändern!):** `project/config/config.json` → `speed:1.0`, `german:{instruct_variant:de_doc_native, engine_mode:customvoice}`, `advanced:{temperature 0.7, top_k 50, top_p 0.9, rep_pen 1.05, qc_enabled true, ...}` — diese Aufgabe testet **Stimmen**, nicht globale TTS-Werte.

**Instruct-Aufbau (German Prosodie, Phase2):** `project/app/prosody/instruct.py:build_instruct()` + `project/app/prosody/german.py` — Varianten-Grundstil + Profil-Modifikator + AUTO-Emotion + Satzrollen-Hinweise (Budget) + rotierender Konsistenz-Anker. English nutzt direkte VoiceDesign-Beschreibung.

**Benchmark-Quelle dieser Repo:** In der Sandbox wurden alle **Hör-MP3s via `arena` `voice-0x` direkt mit dem Audition-Text synthetisiert** (`Every discovery…` bzw. `Jede Entdeckung…`). In Produktion würden stattdessen **Segmente** via `synth_clone` mit demselben Prompt je Stimme erzeugt, dann assembliert (s. E).

---

## E. Cache — Determinismus & Resume

**Datei:** `project/app/cache/manager.py` — `CACHE_VERSION="q3p-v2-integrity"`

- **Key:** `segment_cache_key(engine, engine_version, model_size, speaker, instruct, language, text, sampling, param_version)` → SHA256 aus `f"{CACHE_VERSION}|{engine}|...|{text}|{sampling_json}|{param_version}"`
- **Ablage:** `cache/audio/<key>.wav` (32-bit float WAV) + `cache/metadata/<key>.json` (`ok:true` = gültig)
- **Invalidierung:** Jede Änderung an Engine/Modell/Speaker/Instruct/Sprache/Text/Sampling/Param-Version erzeugt neuen Key — alter Eintrag wird nicht mehr gefunden.
- **Projekt-Pipeline nutzt Cache für Resume** (`project/app/project/pipeline.py` + `runner.py`).

**Sandbox-Hinweis:** `cache/voice_refs/` existiert in dieser Arena-Instanz nicht (`ls` → not found); echte Qwen-Caches entstehen erst mit lokalen Modellen unter `MODELS_DIR`.

---

## F. Audio Output — Vom Segment zum Master

1. **Segment-Synthese** → Float-WAV (SR aus Modell, typ. 24100–48000 Hz)
2. **Concat:** `project/app/audio/concat.py` / `assemble.py` — Aneinanderhängen mit Pausen (`project/app/prosody/pauses.py`)
3. **Mastering:** `project/app/audio/master.py` → EBU R128 `-14.0 LUFS`, `true_peak -1.5 dBTP` (aus `config.json:target_lufs/true_peak_dbtp`)
4. **WAV-Export:** `wav_bit_depth 24`, `wav_sample_rate 48000` (config) — für Benchmark-MP3s via Arena `mp3_bitrate 320k`
5. **Datei-Orte (diese Repo):**
   - Audition: `project/benchmark/fast_audition/`, `project/benchmark/fast_audition_round02/`, `project/benchmark/fast_audition_de/`, `project/benchmark/german_recovery_audition/` (2026-09-09, 7), `project/benchmark/german_second_audition/` (4), `project/benchmark/fast_audition_de_verification/` (3), `project/benchmark/male_deep_candidates/`
   - Referenzen: `cache/voice_refs/<candidate>.wav` (produktion) / `project/VD-E_GOLDEN_REFERENCE/VD-E.wav` (golden)

---

## G. Reproduction Procedure — Voice Recipe → VoiceDesign → Reference → Clone → Final

**Maschinenlesbar:** `project/voices/voice_generation_recipes.json` — enthält für jede gespeicherte Voice (7 English + VD-E + 7 German fast_audition + 7 German recovery + 2 EN female calm = 24) alle 30+ Felder aus der Aufgabenliste. Unbekanntes = `unknown / not recorded`.

**Schritte (bestehende Tools wiederverwenden, kein neues TTS-System):**

```bash
# 1) VoiceDesign-Referenz erzeugen (aus Recipe-Feld voice_design_prompt + language)
python -m project.app.tts.voice_studio  # oder via VoiceOverApp GUI: Voice Studio
# konkret in Code:
from project.app.hardware.detector import detect_hardware
from project.app.tts.model_pool import QwenModelPool
from project.app.tts.voice_studio import QwenVoiceStudio
hw = detect_hardware()
pool = QwenModelPool(hw)  # oder QwenModelPool(hw, models_dir=...)
studio = QwenVoiceStudio(pool)
ref = studio.design_reference(candidate_id="en_male_deep_authoritative_scholar_01",
                               description="deep authoritative scholar – clear, grounded …",
                               language="English")
# -> cache/voice_refs/en_male_deep_authoritative_scholar_01.wav

# 2) Clone-Prompt bauen
prompt = studio.build_clone_prompt(ref)

# 3) Synthese (Langform-Segmente)
from project.app.tts.engine_base import SynthesisRequest
from project.app.tts.sampler import params_for_set
req = SynthesisRequest(text="Every discovery begins with a question …",
                       language="English", seed=52031,
                       instruct=None,  # Clone braucht keine Instruct, nur Prompt
                       sampling=params_for_set("balanced"),
                       max_seconds_hint=25)
result = studio.synth_clone(prompt, req)
# -> result.waveform, sample_rate, duration_s

# Alternative: Produktions-Engine für bestehende Stimme
from project.app.tts.qwen_engine import VoiceCloneEngine
engine = VoiceCloneEngine(hw, candidate_id="vd_e", description="…", allow_design=False)
engine.load()  # prüft cache/voice_refs/VD-E.wav SHA
result = engine.synthesize(req)
```

**Helper:** `project/tools/reproduce_voice.py` + `project/tools/reproduce_voice.ps1` lesen `voice_generation_recipes.json` und führen obigen Ablauf aus (dry-run / --reproduce) und obigen Ablauf ausführen — kein paralleles System bauen.

**Seed-Behandlung:** Pro Segment deterministisch (`seed` aus Recipe, z. B. 52031). Für Variation via `variation_for_attempt` bei QC-Retry.

---

## H. Known Limitations / Placeholders — Ehrlichkeit vor Schönfärberei

- **Alle English-Test-MP3s dieser Session (`voice-06`…`voice-27`) und alle German Audition-MP3s (`fast_audition_de 7`, `german_recovery_audition 7`) sind `arena_placeholder`** (Arena TTS real speech, nicht `actual_qwen` RTX 5060 Qwen3-TTS-Base). Erkennbar an `model: "Arena TTS (real speech) – placeholder …"` + `reference_sha256: "ARENA_VOICE-xx"` + `provenance: arena_placeholder` in `voice_generation_recipes.json` und in `project/voices/*.json` Feld `reference_generated`. **Nie behaupten, sie seien Qwen-RTX-Renders.**
- **Nur VD-E ist `actual_qwen`** (golden reference Wave, SHA256 `B156C02A…`, `cache/voice_refs/VD-E.wav` mit `allow_design=False`).
- **Cache/Modelle in Arena:** `cache/voice_refs/` ist leer, `nvidia-smi` fehlt, `torch` nicht installiert im Sandbox-Benchmark — echte Qwen-Modelle werden erst nach `install.ps1` + Download von `Qwen/Qwen3-TTS-12Hz-1.7B-*` lokal vorhanden (`MODELS_DIR/hf` oder `MODELS_DIR/<model>`).
- **Unbekanntes präzise markiert:** In `voice_generation_recipes.json` stehen Felder wie `speed: unknown — global 1.0`, `audio_format.postprocessing: EBU R128 …` nur soweit aus `config.json`/`master.py` belegbar; sonst `not recorded`.
- **Nicht ändern (global):** German/English Speed, German Prosodie, Qwen-Settings, Cache-Logik, VD-E, Female-Favorites — diese Aufgabe ist **Stimmen-Test**, keine globale Optimierung.
- **Offene Rekonstruktion 9-way German:** Nach exhaustive Suche (counts, git log, JSON, Agent-Reports) kein 9-MP3-Verzeichnis gefunden — honest report in `VOICE_LIBRARY_MANIFEST.md`. Status der 7 recovery bleibt `new_candidate`, kein Raten. — 
- **Keine großen Binaries im Git:** Nur kleine Audition-MP3s (60–70 KB je Clip) + Metadaten werden versioniert; Modell-Binaries/caches bleiben lokal.

---

## Verweise

- `project/voices/voice_generation_recipes.json` — maschinenlesbare Recipes (30 Felder, reproduzierbar)
- `project/voices/*.json` — einzelne Voice-Profile (per_language, settings.seed/variant/arena_voice_id)
- `project/app/tts/voice_studio.py`, `qwen_engine.py`, `model_pool.py`, `sampler.py`
- `project/app/cache/manager.py` (`segment_cache_key`, `CACHE_VERSION`)
- `project/app/prosody/instruct.py` (`VOICEDESIGN_DESCRIPTIONS`, `ENGLISH_VOICEDESIGN_DESCRIPTIONS`, `VOICEDESIGN_REF_TEXT_DE/EN`)
- `project/app/paths.py` (`VOICE_REFS_DIR`, `MODELS_DIR`)
- `project/config/production.json` (`reference_sha256` VD-E), `project/versions.json` (python/torch/transformers/cuda), `project/requirements.txt` (`qwen-tts==0.1.1`)
- Audition-Audios: `project/benchmark/fast_audition*/*.mp3` — menschliche Hörbewertung via **sichtbare Position = Dateinummer** (1→`01_…`, 2→`02_…` …)

*Nach menschlicher Auswahl („Nummer X ist gut“) mappt der Agent Position → Voice-ID → sichert als `locked_human_favorite` / `saved_human_shortlist` (JSON `status`, `human_selected`, `production_candidate`) — nie globale Pipeline anpassen.*
