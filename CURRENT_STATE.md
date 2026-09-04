# CURRENT STATE — VoiceOverApp Voice-AI-Reference

**Datum:** 2026-09-04  
**Version:** 2.1.0  
**Commit-Basis:** `0ef7279` (Initial VoiceOverApp project and Golden Reference)  
**Branch:** `arena/01a06e55-voice-ai-reference`

---

## 1. Projektüberblick

VoiceOverApp ist ein lokales Long-Form-Voice-Over-System auf Basis von
Qwen3-TTS (1.7B-CustomVoice + Base für VD-E-Clone). Ziel: professionelle
deutsche Voice-Overs für YouTube (Dokumentationen, Essays, Wissensvideos,
Hörbuch-Erzählungen) — vollständig lokal, ohne API-Keys.

**Komplette Pipeline:**
```
Text → Analyse → Normalisierung → Aussprache → Segmentierung →
Qwen3-TTS → QC → Regeneration → Assembly → Mastering → WAV+MP3
```

---

## 2. Architektur-Überblick

### Einstiegspunkte
| Startpunkt | Zweck |
|---|---|
| `VoiceOverApp.bat` / `desktop.py` | Desktop-GUI (Tkinter) |
| `START.ps1` | Desktop-GUI + Install-Fallback |
| `app/main.py --headless` | CLI Pipeline |
| `app/main.py --webserver` | Web-UI (dev only) |

### Kernmodule (`project/app/`)
| Modul | Funktion |
|---|---|
| `config.py` | Konfiguration (Defaults, Merge, YAML/JSON) |
| `paths.py` | Zentrale Pfadverwaltung |
| `main.py` | CLI-Einstiegspunkt |
| `project/pipeline.py` | **Haupt-Pipeline** (Analyse→Mastering) |
| `project/state.py` | Projekt-State für Resume |
| `tts/qwen_engine.py` | Qwen3-TTS CustomVoice-Engine |
| `tts/voice_studio.py` | VoiceDesign + Clone-Pipeline |
| `tts/model_pool.py` | Modell-Pool (CustomVoice/Base/0.6B) |
| `tts/sampler.py` | Sampling-Parameter-Sets |
| `tts/engine_base.py` | Engine-Basisklasse + SynthesisRequest/Result |
| `tts/test_double.py` | Deterministischer Test-Double (keine GPU) |
| `segmentation/__init__.py` | Intelligente Long-Form-Segmentierung |
| `prosody/german.py` | Deutsche Satzrollen, Pausen-Basen, Hinweise |
| `prosody/instruct.py` | Instruct-Builder (Varianten, Emotion) |
| `prosody/pauses.py` | Kontextabhängige Pausen (classic/semantic/flow) |
| `prosody/presets.py` | Presets (Deep Documentary, etc.) |
| `prosody/variation.py` | Sampling-Variation, Emotion, Betonung |
| `pronunciation/` | Wörterbuch + Regeln (DE/EN, Namen, Fremdwörter) |
| `quality/qc.py` | Segment-QC (Score, Issues) |
| `quality/final_gate.py` | Final-QC-Gate (harte Integritätsprüfung) |
| `quality/regeneration.py` | Best-of-N Regeneration |
| `quality/german_score.py` | GermanNaturalnessScore |
| `quality/metrics.py` | Audio-Metriken |
| `audio/assemble.py` | Segment-Zusammenfügung (Streaming) |
| `audio/concat.py` | FullScript-Konkatenation aus Parts |
| `audio/master.py` | YouTube-Mastering (LUFS, TruePeak) |
| `audio/ebu_r128.py` | EBU R128 Lautheitsmessung |
| `audio/ffmpeg.py` | FFmpeg-Wrapper |
| `audio/io.py` | WAV Read/Write/Resample |
| `cache/manager.py` | **Segment-Cache** (persistent, invalidierbar) |
| `batch/runner.py` | Batch-Verarbeitung |
| `jobs/runner.py` | Job-Runner (JSONL, PID-Sperre) |
| `hardware/detector.py` | Hardware-Erkennung (GPU/CPU/VRAM/RAM) |
| `hardware/monitor.py` | VRAM-Guard |
| `gui/app.py` | Desktop-GUI (Tkinter) |
| `gui/backend.py` | Backend-Subprocess |
| `ui/server.py` | Web-UI-Server |
| `voices/registry.py` | Voice-Registry (Native-Language-Logik) |
| `voices/profiles.py` | Voice-Profile |
| `security/identity_lock.py` | VD-E-Identitäts-Lock (SHA-256) |
| `text/normalize.py` | Text-Normalisierung (Zahlen, Datum, etc.) |
| `text/analyze.py` | Text-Analyse (Blöcke, Sätze) |
| `text/numbers.py` | Zahlen-Konvertierung |
| `text/langdetect.py` | Sprach-Plausibilität |
| `text/pdf_import.py` | PDF-Import |

---

## 3. TTS-Engine & Modelle

### Produktiv-Engine
- **Qwen3-TTS-12Hz-1.7B-CustomVoice** (Hauptmodell)
- **Qwen3-TTS-12Hz-1.7B-Base** (für VD-E-Clone)
- **Qwen3-TTS-Tokenizer-12Hz** (gemeinsam)
- 0.6B als CPU-/Notfallvariante

### Attention-Implementierung
- **SDPA** (Standard, stabil)
- Flash Attention 2 (experimentell, Windows-Risiko dokumentiert)
- Benchmark-Ergebnisse in `benchmark/ATTENTION_AB_20260903/`

### Sampling-Parameter (Produktion)
- Set: "balanced" (default), "expressive" (VD-E-Produktion)
- temperature=0.7, top_k=50, top_p=0.90, repetition_penalty=1.05
- PARAM_SET_VERSION = "q3p-v2-integrity"

---

## 4. VD-E Golden Reference

| Eigenschaft | Wert |
|---|---|
| Datei | `reference/VD-E_GOLDEN_REFERENCE/VD-E.wav` |
| SHA-256 | `B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025` |
| Status | LOCKED — unveränderlich |
| Verfahren | VoiceDesign → Base Clone |
| Seed | 52001 |
| Identitätsschutz | Identity-Lock prüft Hash bei Start/Lauf/Nach-Lauf |

**Zweitere Golden Reference Kopien:**
- `project/VD-E_GOLDEN_REFERENCE/` (Arbeitskopie)
- `project/benchmark/APPROVED_STATE_ATTENTION_20260903/VD-E.wav`
- `project/benchmark/PROTECT_VD_E_20260903_181533/VD-E.wav`

---

## 5. Stimmen-Architektur

### Deutsch (DE)
| Stimme | Status | Beschreibung |
|---|---|---|
| **VD-E** | **EMPFOHLEN · DEFAULT · LOCKED** | tief, ruhig, seriös |
| Uncle_Fu | CROSS-LANGUAGE | tief, warm, mellow, reif |
| Dylan | CROSS-LANGUAGE | klar, natürlich, jünger |
| Serena | CROSS-LANGUAGE | warm, sanft, ruhig |
| Vivian | CROSS-LANGUAGE | hell, klar, jung |
| Sohee | CROSS-LANGUAGE | warm, emotional, reich |

### Englisch (EN)
| Stimme | Status |
|---|---|
| **Ryan** | NATIV · EMPFOHLEN |
| Aiden | NATIV · EMPFOHLEN |
| Uncle_Fu | FALLBACK |
| Serena/Vivian/Sohee | CROSS-LANGUAGE |

---

## 6. Segmentierung

- Ziel: 420 Zeichen pro Segment
- Max: 700 Zeichen
- Min: 120 Zeichen
- Grenzen: Satz → Absatz → Kapitel → Nebensatz (Komma/Semikolon/Gedankenstrich)
- Niemals mitten im Wort
- Niemals zeitbasiert (nur Marker `+++++` für manuellen Split)

---

## 7. Audio-Ausgabe

| Format | Spezifikation |
|---|---|
| WAV Master | 48 kHz / 24 Bit, -14 LUFS / -1.5 dBTP |
| MP3 | 320 kbps (YouTube-tauglich) |

### Mastering-Pfad
1. ffmpeg 2-Pass loudnorm (bevorzugt)
2. numpy-Fallback (R128-Messung + Gain + Peak-Limiter)

---

## 8. Quality Control

- **SegmentQC**: Score aus Naturalness, Pronunciation, Prosody, Consistency, Integrity
- **GermanNaturalnessScore**: Separater DE-spezifischer Score
- **Final-QC-Gate**: Harte Integritätsprüfung vor Cache-Übernahme
- **Regeneration**: Bis zu 3 Versuche mit klassifizierter Parameter-Strategie
- **Min-Score**: 78 (QC) / 60 (Final-Gate)

---

## 9. Cache & Resume

- **Cache-Version**: `q3p-v2-integrity`
- **Cache-Struktur**: `cache/audio/<key>.wav` + `cache/metadata/<key>.json`
- **Cache-Key**: SHA-256 aus (Version, Engine, Modell, Speaker, Instruct, Sprache, Text, Sampling, Param-Version)
- **Invalidierung**: Automatisch bei Parameteränderung (neuer Key)
- **Resume**: Projekt-State in `cache/projects`, abgebrochene Jobs setzen nur fehlende Segmente fort

---

## 10. Teststand (Sandbox, 2026-09-04)

### Reparierte kritische Probleme
1. **`app/cache/` Modul fehlte komplett** → neu erstellt (cache/__init__.py, cache/manager.py)
   - CacheManager mit put/get/has/clear_segment/clear_failed/clear_all/stats
   - segment_cache_key mit SHA-256-Hashing
   - WAV-Read/Write (float32, int16, int24, int32)
   - Atomares Schreiben (tmp + rename)
2. **`concat.py` Bug**: `out.sampler` (nicht-existentes Attribut) → entfernt
3. **`test_packaging_fix.py`**: Veraltete Version-Assertion (2.0.0 → 2.1.0, 6 → 8 Stimmen)

### Testergebnis
```
172/179 bestanden (96.1%)
```

### Verbleibende 7 Fehler (alle Sandbox-bedingt)
- 6× `No module named 'tkinter'` — Headless-Umgebung ohne GUI-Bibliothek
- 0× Code-Bugs

### Auf Zielhardware ausstehend
- Echte Qwen3-TTS-Synthese (GPU, RTX 5060)
- Akustische Bewertung gegen Golden Reference
- Long-Form-Stabilität (30-120 min)
- VRAM-/RAM-Verifikation

---

## 11. Hardware-Ziel

| Komponente | Wert |
|---|---|
| CPU | AMD Ryzen 7 5700X |
| RAM | 32 GB |
| GPU | NVIDIA GeForce RTX 5060 |
| VRAM | 8 GB |
| OS | Windows 10 Home / x64 |

---

## 12. Bekannte Einschränkungen

1. **Keine echte Audioqualität in der Sandbox verifiziert** — GPU-Tests ausstehend
2. **tkinter-Tests** laufen nur auf dem Zielsystem mit GUI
3. **Quality Score ist Vergleichsmaßstab**, keine absolute Natürlichkeitsmessung
4. **Spracherkennung (ASR)** bewusst nicht eingebaut (QC nutzt Dauerplausibilität als Proxy)

---

## 13. Nächste Prioritäten (Optimierungsplan)

### A. Segmentierungs-Strategie evaluieren (§40)
- Variante A: vollständige lange Generierung
- Variante B: große semantische Segmente
- Variante C: kleine Segmente
- Variante D: Hybrid
- Variante E: Generierung mit Kontextfenster/Overlap
- **Bewertung**: Voice consistency, Prosody, Übergänge, VRAM, Stabilität

### B. Long-Form-Konsistenz (§70)
- Voice consistency über 30-120 Minuten
- Tonalität, Lautheit, Geschwindigkeit, Artikulation

### C. Quality Gate erweitern
- Mehr Varianten pro Segment
- Bessere akustische Metriken

### D. Performance-Optimierung (wenn Qualität gleich bleibt)
- Model Pool effizienter nutzen
- Besseres Caching
- Parallelisierung wo sinnvoll

### E. Dokumentation aktualisieren
- CURRENT_STATE.md (dieses Dokument)
- REPOSITORY_INVENTORY.txt nach Änderungen
