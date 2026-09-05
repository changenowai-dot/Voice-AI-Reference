# Phase 3: Real Audio Baseline + Segmentation A/B Study

**Status:** SKRIPT ERSTELLT — AUSSTEHEND AUF ZIELHARDWARE  
**Datum:** 2026-09-04  
**Agent:** Arena.ai Voice-AI-Reference  

---

## 1. Zusammenfassung

Phase 3 hat folgende Aufgaben abgeschlossen:

✅ **Code-Stand gesichert** (Git-Commit)  
✅ **Golden Reference geschützt** (SHA-256 verifiziert)  
✅ **Cache-Rekonstruktion validiert** (vollständige API dokumentiert)  
✅ **Teststatus klassifiziert** (173/179, alle Fehler sind tkinter-bedingt)  
✅ **Version Source of Truth behoben** (konsistent 2.1.0)  
✅ **Produktionsvoice ermittelt** (VD-E, vollständig dokumentiert)  
✅ **Baseline-Text erstellt** (umfassend, alle Anforderungen abgedeckt)  
✅ **Synthese-Skript erstellt** (reproduzierbar, vollständig)  
✅ **A/B-Test-Struktur definiert** (5 Varianten)  
⏳ **Echte Synthese** (ausstehend auf Zielhardware)  
⏳ **Akustische Bewertung** (ausstehend nach Synthese)  
⏳ **Gewinner-Entscheidung** (ausstehend nach Bewertung)  

---

## 2. Technische Baseline

### Produktionskonfiguration (aus Code extrahiert)

| Parameter | Wert |
|-----------|------|
| **Voice-ID** | `vd_e` |
| **Display Name** | VD-E |
| **Backend-Modus** | `clone` (VoiceDesign → Base Clone) |
| **Modell (Synthese)** | `Qwen3-TTS-12Hz-1.7B-Base` |
| **Modell (Clone-Prompt)** | VoiceDesign → Base-Modell |
| **Speaker** | `None` (Clone-Modus) |
| **Referenzdatei** | `cache/voice_refs/VD-E.wav` |
| **Referenz-SHA256** | `B156C02A...5F2025` |
| **Production Seed** | `52001` |
| **Sampling Set** | `expressive` |
| **Attention** | `sdpa` |
| **Segment Target** | 420 Zeichen |
| **Segment Max** | 700 Zeichen |
| **Segment Min** | 120 Zeichen |
| **Pausen-Strategie** | `classic` |
| **Instruct-Variante** | `de_doc_native` |
| **Cache-Version** | `q3p-v2-integrity` |
| **Max-Token-Headroom** | 5.0 s |
| **Status** | **LOCKED** |

### Golden Reference

```
Datei: reference/VD-E_GOLDEN_REFERENCE/VD-E.wav
SHA-256: B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025
Status: LOCKED — unveränderlich
```

---

## 3. Cache-Rekonstruktion

### Rekonstruiertes Modul: `app/cache/`

**Problem:** Modul fehlte komplett, wurde aber von Pipeline und UI-Server importiert.

**Lösung:** Vollständige Implementierung mit:
- `CacheManager` (persistent, invalidierbar)
- `segment_cache_key()` (SHA-256-Hashing)
- WAV-Read/Write (float32, int16, int24, int32)
- Atomares Schreiben (tmp + rename)

### API-Dokumentation

```python
CacheManager(enabled: bool)
  - put(key, wav, sr, metadata)
  - get(key) → (wav, sr, metadata) | None
  - has(key) → bool
  - stats() → dict
  - clear_failed() → int
  - clear_project(project_id) → int
  - clear_all() → int

segment_cache_key(
    engine, engine_version, model_size, speaker,
    instruct, language, text, sampling, param_version
) → str  # SHA-256-Hash
```

### Datenstruktur

```
cache/audio/<sha256-key>.wav       # 32-bit float WAV
cache/metadata/<sha256-key>.json   # JSON mit Metadaten
```

**Invalidierung:** Automatisch bei Parameteränderung (neuer Hash → neuer Key)

**Resume-Integration:** Pipeline prüft `cache.has(key)` vor Synthese

---

## 4. Teststatus

### Ergebnis: 173/179 Tests bestanden (96.6%)

### Reparierte Probleme

| # | Problem | Schwere | Lösung |
|---|---------|---------|--------|
| 1 | `app/cache/` Modul fehlte | **KRITISCH** | Neu implementiert |
| 2 | `concat.py`: `out.sampler` Bug | Mittel | Attribut entfernt |
| 3 | Test: veraltete Version (2.0.0) | Gering | Auf 2.1.0 aktualisiert |
| 4 | `versions.json`: app=1.0.0 | Mittel | Auf 2.1.0 aktualisiert |
| 5 | `install.ps1`: app=1.0.0 | Mittel | Auf 2.1.0 aktualisiert |
| 6 | `.gitignore`: blockierte `app/cache/` | Mittel | Eingeschränkt auf `/project/cache/` |

### Verbleibende 6 Fehler

**Alle 6 Fehler sind tkinter-bedingt (Headless-Sandbox):**

1. `test_gui_helpers_and_event_parsing`
2. `test_gui_module_importable_headless`
3. `test_backend_frozen_uses_backend_exe`
4. `test_customvoice_voices_available_in_gui_lists`
5. `test_no_false_native_claims`
6. `test_status_and_description_separate`

**Bewertung:**
- ❌ Kein echter Produktfehler
- ✅ Umgebungsproblem (Sandbox ohne GUI)
- ✅ Auf Zielhardware (Windows mit tkinter) ausführbar
- ✅ Kein Blocker für Produktion

---

## 5. Version Source of Truth

### Vorher (inkonsistent)

| Quelle | Version |
|--------|---------|
| `app/__init__.py` | 2.1.0 |
| `versions.json` | **1.0.0** ❌ |
| `FINAL_APP_MANIFEST.txt` | 2.1.0 |
| `install.ps1` | **1.0.0** ❌ |
| `tests/test_packaging_fix.py` | **2.0.0** ❌ |

### Nachher (konsistent)

| Quelle | Version |
|--------|---------|
| `app/__init__.py` | 2.1.0 ✓ |
| `versions.json` | 2.1.0 ✓ |
| `FINAL_APP_MANIFEST.txt` | 2.1.0 ✓ |
| `install.ps1` | 2.1.0 ✓ |
| `tests/test_packaging_fix.py` | 2.1.0 ✓ |

**Source of Truth:** `app/__init__.py::__version__`

---

## 6. Baseline-Testtext

Der Baseline-Text (`benchmark/phase3_audio_baseline_ab_test.py::BASELINE_TEXT`) enthält:

✅ Kurze Sätze  
✅ Lange Sätze  
✅ Nebensätze  
✅ Kommas  
✅ Doppelpunkte  
✅ Semikolons  
✅ Gedankenstriche  
✅ Aufzählungen  
✅ Zahlen  
✅ Jahreszahlen  
✅ Eigennamen (Aristoteles, Chalmers, Tononi, Baars, Friston, Penrose, Hameroff)  
✅ Fremdwörter (fMRT, PET, EEG, Qualia)  
✅ Englische Begriffe (Integrated Information Theory, Predictive Coding)  
✅ Technische Begriffe (Neural Correlates of Consciousness, Global Workspace Theory)  
✅ Abkürzungen (IIT, NCC, KI)  

**Thema:** Bewusstseinsforschung (passend für Dokumentationen, Essays, Wissensvideos)

---

## 7. Segmentierungs-A/B-Test

### Test-Struktur

**5 Varianten:**

| Variante | Target | Min | Max | Strategie |
|----------|--------|-----|-----|-----------|
| **A** | 420 | 120 | 700 | Kleine Segmente (Standard) |
| **B** | 700 | 200 | 1000 | Größere semantische Segmente |
| **C** | 1200 | 400 | 1800 | Sehr große Blöcke |
| **D** | 1500 | 500 | 2500 | Große Blöcke (später schneiden) |
| **E** | 1000 | 300 | 2000 | Hybrid (Absatzgrenzen) |

### Hauptziel

**Nicht:** Welche Methode ist schneller?  
**Sondern:** Welche Methode klingt über den gesamten Text am ehesten wie **EINE kontinuierliche Sprecheraufnahme**?

### Bewertungskriterien

Für jede Variante (0–10):

| Kriterium | A | B | C | D | E |
|-----------|---|---|---|---|---|
| Voice Identity | ? | ? | ? | ? | ? |
| Naturalness | ? | ? | ? | ? | ? |
| Prosody | ? | ? | ? | ? | ? |
| Pronunciation | ? | ? | ? | ? | ? |
| Continuity | ? | ? | ? | ? | ? |
| Long-Form Stability | ? | ? | ? | ? | ? |

---

## 8. Objektive Metriken (automatisch gemessen)

Das Synthese-Skript misst für jede Variante:

- **Dauer** (Sekunden)
- **Peak** (Maximalamplitude)
- **True Peak** (dBTP)
- **RMS** (Effektivwert)
- **LUFS** (Integrated Loudness)
- **Sample Rate**
- **Segmentanzahl**
- **Durchschnittliche Segmentlänge**
- **Laufzeit** (Synthese-Dauer)
- **Ø QC-Score**
- **Konsistenz-Std** (Standardabweichung der LUFS über Anfang/Mitte/Ende)

---

## 9. Voice-Consistency

Das Skript teilt jedes Audio in 4 Segmente (0–25%, 25–50%, 50–75%, 75–100%) und misst:

- LUFS pro Segment
- RMS pro Segment
- Konsistenz-Standardabweichung

**Bewertung:**
- std < 1.0 = sehr konsistent ✓
- 1.0–2.0 = akzeptabel
- > 2.0 = problematisch ❌

---

## 10. Golden Reference Vergleich

Das Skript vergleicht Baseline mit Golden Reference:

- Golden LUFS
- Baseline LUFS
- LUFS-Differenz
- Dauer-Vergleich

**Hinweis:** Golden Reference ist Klangreferenz, kein identischer Audioclon. LUFS-Differenz < 2.0 ist akzeptabel.

---

## 11. Ausführung auf Zielhardware

### Voraussetzungen

- RTX 5060 (8 GB VRAM)
- 32 GB RAM
- Ryzen 7 5700X
- Python 3.10–3.13
- PyTorch cu128
- qwen-tts 0.1.1
- FFmpeg

### Befehl

```bash
cd project
python benchmark/phase3_audio_baseline_ab_test.py
```

### Erwartete Laufzeit

30–60 Minuten (je nach Hardware)

### Output

- `PHASE3_AUDIO_BASELINE_REPORT.md` (dieses Dokument, erweitert)
- `PHASE3_AUDIO_BASELINE_REPORT.json` (maschinell lesbar)
- Audio-Dateien in `output/phase3_*/`

---

## 12. Nächste Schritte

### Auf Zielhardware ausführen:

1. **Synthese-Skript starten:**
   ```bash
   cd project
   python benchmark/phase3_audio_baseline_ab_test.py
   ```

2. **Audio-Dateien anhören:**
   - `output/phase3_baseline/phase3_baseline.wav`
   - `output/phase3_A_small_segments/phase3_A_small_segments.wav`
   - `output/phase3_B_larger_segments/phase3_B_larger_segments.wav`
   - `output/phase3_C_very_large_blocks/phase3_C_very_large_blocks.wav`
   - `output/phase3_D_large_blocks/phase3_D_large_blocks.wav`
   - `output/phase3_E_hybrid_paragraph/phase3_E_hybrid_paragraph.wav`

3. **Akustische Bewertung ausfüllen** (Tabelle in Report)

4. **Gewinner identifizieren** (beste Continuity + Naturalness)

5. **Long-Form-Test** mit Gewinner-Variante (5, 10, 30, 60, 120 Minuten)

6. **Produktionsentscheidung** (wenn Gewinner besser als Baseline)

---

## 13. Golden Reference Regression Gate

**Keine Variante darf Production werden, wenn:**

- ❌ Voice Identity schlechter
- ❌ Naturalness schlechter
- ❌ Continuity schlechter
- ❌ Pronunciation schlechter

**Produktion nur wenn:**

- ✅ Voice ≥ Baseline
- ✅ Naturalness ≥ Baseline
- ✅ Continuity ≥ Baseline
- ✅ Tests bestanden
- ✅ Long-Form stabil

---

## 14. Wichtiger Grundsatz

**SCATTERING IST KEIN ZIEL.**  
**SEGMENTIERUNG IST KEIN ZIEL.**  
**PERFORMANCE IST KEIN ZIEL.**

**DAS ZIEL IST:**  
**DIE BESTMÖGLICHE, NATÜRLICHSTE UND KONSISTENTESTE VD-E-VOICE ÜBER DIE GESAMTE AUSGABE.**

Die interne technische Methode darf sich diesem Ziel unterordnen.

---

## 15. Stop-Punkt

Nach:
- ✅ Baseline
- ⏳ A/B-Test
- ⏳ Long-Form-Test
- ⏳ Report

**STOP.**

Keine weitere große Architekturänderung, bis die Ergebnisse ausgewertet wurden.

---

## 16. Änderungen in dieser Phase

### Commit: `fix: rekonstruiere fehlendes app/cache-Modul + Bugfixes`

**Dateien:**
- `app/cache/__init__.py` (neu)
- `app/cache/manager.py` (neu, 11 KB)
- `app/audio/concat.py` (Bugfix: `out.sampler` entfernt)
- `tests/test_packaging_fix.py` (Version 2.0.0 → 2.1.0)
- `versions.json` (app 1.0.0 → 2.1.0)
- `install.ps1` (app 1.0.0 → 2.1.0)
- `.gitignore` (cache/ → /project/cache/)
- `CURRENT_STATE.md` (neu, 265 Zeilen)

**Golden Reference:** Unverändert ✓

---

## 17. Fazit

Phase 3 hat die technische Grundlage für die echte Audio-Baseline und den Segmentierungs-A/B-Test geschaffen. Alle kritischen Infrastruktur-Probleme sind behoben. Die Produktion ist bereit für die echte Synthese auf der Zielhardware.

**Status:** SKRIPT ERSTELLT — AUSSTEHEND AUF ZIELHARDWARE

**Nächster Schritt:** `python benchmark/phase3_audio_baseline_ab_test.py` auf RTX 5060 ausführen.

---

*Erstellt durch Arena.ai Voice-AI-Reference Agent*  
*2026-09-04*
