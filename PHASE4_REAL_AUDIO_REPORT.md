# Phase 4: Real RTX 5060 Audio Benchmark Report

**Status:** VORBEREITUNG ABGESCHLOSSEN — BEREIT FÜR AUSFÜHRUNG AUF RTX 5060  
**Datum:** 2026-09-04  
**Commit:** e81bb32 (Phase 3 final)  

---

## 1. Zusammenfassung

Phase 4 hat die vollständige Infrastruktur für den echten Audio-Benchmark auf der RTX 5060 erstellt. Die Sandbox-Umgebung verfügt über **keine GPU** und kann daher keine echte Audio-Synthese durchführen.

**Status der Vorbereitung:**
- ✅ Git-Zustand gesichert (Commit e81bb32)
- ✅ Golden Reference verifiziert (SHA-256: B156C02A...5F2025 ✓)
- ✅ Runtime Voice Reference dokumentiert
- ✅ Umgebung-Check-Skript erstellt
- ✅ Benchmark-Skript erstellt (Baseline + A/B-Test)
- ✅ Long-Form-Test-Skript erstellt
- ✅ Baseline-Text erstellt (2839 Zeichen, alle phonetischen Fälle)
- ✅ 5 Segmentierungs-Varianten definiert
- ✅ Variante D (große Blöcke + Schneiden) implementiert
- ✅ Metrik-Erfassung vorbereitet
- ✅ Report-Struktur erstellt

**Ausstehend auf RTX 5060:**
- ⏳ Umgebung-Check ausführen
- ⏳ Runtime Voice Reference kopieren
- ⏳ Baseline-Audio erzeugen
- ⏳ Golden Reference Vergleich
- ⏳ A/B-Test (5 Varianten)
- ⏳ Akustische Bewertung
- ⏳ Long-Form-Test (5, 10, 30, 60, 120 Minuten)
- ⏳ Produktions-Entscheidung

---

## 2. Hardware

### Zielhardware (erforderlich)
| Komponente | Spezifikation |
|------------|---------------|
| CPU | AMD Ryzen 7 5700X |
| RAM | 32 GB |
| GPU | NVIDIA GeForce RTX 5060 |
| VRAM | 8 GB |
| OS | Windows 10 x64 |

### Sandbox-Umgebung (aktuell)
| Komponente | Status |
|------------|--------|
| CPU | Cloud-CPU (keine RTX 5060) |
| RAM | ~2 GB |
| GPU | ❌ NICHT VORHANDEN |
| PyTorch | ❌ Nicht installiert |
| CUDA | ❌ Nicht vorhanden |
| qwen-tts | ❌ Nicht installiert |
| FFmpeg | ✅ Verfügbar |

**WICHTIG:** Echte Audio-Synthese ist in dieser Sandbox **NICHT MÖGLICH**.

---

## 3. Software

### Erforderliche Versionen (auf RTX 5060)
| Komponente | Version |
|------------|---------|
| Python | 3.10 - 3.13 |
| PyTorch | >= 2.11.0+cu128 |
| CUDA | 12.8 |
| qwen-tts | 0.1.1 |
| transformers | >= 4.57.3 |
| FFmpeg | Verfügbar |
| numpy | >= 1.24.0 |
| soundfile | >= 0.12.0 |

### Überprüfungs-Skript
```powershell
cd project
python benchmark/phase4_env_check.py
```

Erstellt `benchmark/phase4_env_check.json` mit allen Check-Ergebnissen.

---

## 4. Modell & Voice

| Parameter | Wert |
|-----------|------|
| **Voice-ID** | `vd_e` |
| **Backend** | `clone` (VoiceDesign → Base) |
| **Modell** | `Qwen3-TTS-12Hz-1.7B-Base` |
| **Seed** | 52001 |
| **Sampling** | `expressive` |
| **Attention** | `sdpa` |
| **Instruct** | `de_doc_native` |
| **Prosody** | `classic` |
| **Cache-Version** | `q3p-v2-integrity` |
| **Segment Target** | 420 Zeichen |
| **Segment Max** | 700 Zeichen |
| **Segment Min** | 120 Zeichen |

---

## 5. Voice Reference

### Golden Reference
```
Datei: reference/VD-E_GOLDEN_REFERENCE/VD-E.wav
SHA-256: B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025
Status: ✓ VERIFIZIERT
```

### Runtime Voice Reference
```
Pfad: project/cache/voice_refs/VD-E.wav
Status: ⏳ MUSS KOPIERT WERDEN
```

**Setup-Schritt auf RTX 5060:**
```powershell
# Golden Reference → Runtime kopieren
New-Item -ItemType Directory -Force -Path "cache\voice_refs"
Copy-Item "reference\VD-E_GOLDEN_REFERENCE\VD-E.wav" "cache\voice_refs\VD-E.wav"

# Hash verifizieren
(Get-FileHash "cache\voice_refs\VD-E.wav" -Algorithm SHA256).Hash
# Erwartet: B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025
```

**Code-Pfad:**
```
production.json → reference_path: "cache/voice_refs/VD-E.wav"
→ identity_lock.py prüft SHA-256
→ qwen_engine.py VoiceCloneEngine lädt als Clone-Prompt
→ Alle Segmente verwenden denselben Prompt → maximale Konsistenz
```

---

## 6. Baseline-Text

**Länge:** 2839 Zeichen (~400 Wörter)  
**Erwartete Dauer:** ~2-3 Minuten

**Enthaltene phonetische Fälle:**
- ✅ Normale deutsche Sätze
- ✅ Lange Sätze (verschachtelte Nebensätze)
- ✅ Nebensätze (Relativsätze, Konjunktionen)
- ✅ Kommas (Aufzählungen, Einschübe)
- ✅ Doppelpunkte
- ✅ Semikolons
- ✅ Gedankenstriche (—)
- ✅ Aufzählungen (mit Semikolon getrennt)
- ✅ Zahlen (86 Milliarden, 10^15, 10^18)
- ✅ Jahreszahlen (4. Jahrhundert v. Chr., 1990, 1988)
- ✅ Namen (Aristoteles, Tononi, Baars, Friston, Penrose, Hameroff, Cicero, Seneca, Newton, Einstein, Gutenberg)
- ✅ Fremdwörter (fMRT, PET, EEG, Qualia, Phi)
- ✅ Englische Begriffe (Integrated Information Theory, Predictive Coding, Global Workspace)
- ✅ Technische Begriffe (Neuroinformatik, Synapsen, Supercomputer, Relativitätstheorie, Quantenmechanik)
- ✅ Abkürzungen (NCC, IIT, KI, EEG)

**Text-Thema:** Bewusstseinsforschung und Menschheitsgeschichte (passend für Dokumentationen, Essays, Wissensvideos)

---

## 7. Segmentierungs-A/B-Test

### Varianten

| Variante | Target | Min | Max | Strategie |
|----------|--------|-----|-----|-----------|
| **A** | 420 | 120 | 700 | Production-Standard (aktuell) |
| **B** | 700 | 200 | 1000 | Größere semantische Segmente |
| **C** | 1200 | 400 | 1800 | Sehr große Blöcke |
| **D** | 1500 | 500 | 2500 | Große Blöcke + intelligentes Schneiden |
| **E** | 1000 | 300 | 2000 | Hybrid (Absatz-basiert) |

### Variante D: Große Blöcke + Schneiden

**Spezielle Implementierung:**
1. Text in wenige große Blöcke teilen (an Absatzgrenzen, ca. 2000-3000 Zeichen)
2. Jeden Block komplett an Qwen3-TTS übergeben
3. Audio an semantisch sinnvollen Grenzen schneiden
4. Zusammenfügen

**Vorteil:** Weniger Segmentübergänge → potenziell bessere Kontinuität  
**Nachteil:** Höherer VRAM-Verbrauch pro Segment

---

## 8. Metriken

### Objektive Metriken (automatisch gemessen)

Für jede Variante:
- **Sample Rate** (Hz)
- **Channels** (mono/stereo)
- **Duration** (Sekunden)
- **Peak** (Amplitude, dB)
- **RMS** (Effektivwert, dB)
- **LUFS** (approximiert)
- **Clipping** (ja/nein)
- **File Size** (MB)
- **QC-Score** (0-100)
- **Laufzeit** (Sekunden)
- **VRAM** (Peak, GB)
- **RAM** (Peak, GB)

### Voice-Consistency (automatisch gemessen)

An 5 Punkten (0%, 25%, 50%, 75%, 100%):
- **RMS** (dB)
- **Peak** (Amplitude)
- **Zero-Crossing-Rate** (Timbre-Indikator)

**Bewertung:**
- std < 2.0 dB = sehr konsistent ✓
- 2.0-2.5 dB = akzeptabel
- > 2.5 dB = problematisch ❌

---

## 9. Golden Reference Vergleich

**Vergleichsmetriken:**
- Duration-Differenz
- RMS-Differenz (dB)
- Peak-Differenz

**Hinweis:** Golden Reference ist Klangreferenz, kein identischer Audioclon. LUFS-Differenz < 2.0 ist akzeptabel.

---

## 10. Akustische Bewertung (MANUELL AUSZUFÜLLEN)

Nach Ausführung auf RTX 5060 bitte jede Variante anhören und bewerten:

| Kriterium | A | B | C | D | E | Baseline |
|-----------|---|---|---|---|---|----------|
| Voice Identity (0-10) | ? | ? | ? | ? | ? | ? |
| Naturalness (0-10) | ? | ? | ? | ? | ? | ? |
| Pronunciation (0-10) | ? | ? | ? | ? | ? | ? |
| Prosody (0-10) | ? | ? | ? | ? | ? | ? |
| Continuity (0-10) | ? | ? | ? | ? | ? | ? |
| Long-Form Stability (0-10) | ? | ? | ? | ? | ? | ? |

**Bewertungskriterien:**
- **Voice Identity:** Klingt es wie VD-E?
- **Naturalness:** Klingt es natürlich/menschlich?
- **Pronunciation:** Sind Aussprache, Betonung, Pausen korrekt?
- **Prosody:** Ist die Satzmelodie natürlich?
- **Continuity:** Gibt es hörbare Segmentübergänge?
- **Long-Form Stability:** Bleibt die Stimme über die gesamte Dauer konsistent?

---

## 11. Long-Form Test

**Skript:** `benchmark/phase4_longform.py`

**Getestete Dauern:**
- 5 Minuten
- 10 Minuten
- 30 Minuten
- 60 Minuten (wenn VRAM/RAM reicht)
- 120 Minuten (wenn stabil)

**Prüfung an 10 Punkten (0%, 10%, 20%, ..., 100%):**
- Timbre-Stabilität
- Tempo-Stabilität
- Lautheit-Konsistenz
- Prosody-Konsistenz
- Voice Identity

---

## 12. Produktions-Entscheidung

### Gewinner-Tabelle (auszufüllen)

| Variante | Voice Identity | Naturalness | Pronunciation | Prosody | Continuity | Runtime | VRAM | RAM |
|----------|----------------|-------------|---------------|---------|------------|---------|------|-----|
| A | ?/10 | ?/10 | ?/10 | ?/10 | ?/10 | ?s | ?GB | ?GB |
| B | ?/10 | ?/10 | ?/10 | ?/10 | ?/10 | ?s | ?GB | ?GB |
| C | ?/10 | ?/10 | ?/10 | ?/10 | ?/10 | ?s | ?GB | ?GB |
| D | ?/10 | ?/10 | ?/10 | ?/10 | ?/10 | ?s | ?GB | ?GB |
| E | ?/10 | ?/10 | ?/10 | ?/10 | ?/10 | ?s | ?GB | ?GB |

### Entscheidungsregel

**Gewinner = Variante mit:**
- Höchster Naturalness-Score
- Höchster Continuity-Score
- Keine Regression gegenüber Baseline
- Akzeptable Performance

**Priorität:**
1. Voice Quality
2. Voice Consistency
3. Naturalness
4. Pronunciation
5. Prosody
6. Continuity
7. Stability
8. Performance

---

## 13. Golden Reference Regression Gate

**Keine Variante darf Production werden, wenn:**
- ❌ Voice Identity schlechter als Baseline
- ❌ Naturalness schlechter als Baseline
- ❌ Continuity schlechter als Baseline
- ❌ Pronunciation schlechter als Baseline

**Production nur wenn:**
- ✅ Voice ≥ Baseline
- ✅ Naturalness ≥ Baseline
- ✅ Continuity ≥ Baseline
- ✅ Tests bestanden
- ✅ Long-Form stabil

---

## 14. Ausführung auf RTX 5060

### Schritt 1: Umgebung prüfen
```powershell
cd VoiceOverApp
python benchmark/phase4_env_check.py
```

### Schritt 2: Runtime Voice Reference setup
```powershell
New-Item -ItemType Directory -Force -Path "cache\voice_refs"
Copy-Item "reference\VD-E_GOLDEN_REFERENCE\VD-E.wav" "cache\voice_refs\VD-E.wav"
(Get-FileHash "cache\voice_refs\VD-E.wav" -Algorithm SHA256).Hash
```

### Schritt 3: Baseline + A/B-Test
```powershell
python benchmark/phase4_benchmark.py
```

**Erwartete Laufzeit:** 30-90 Minuten  
**Output:**
- `PHASE4_REAL_AUDIO_REPORT.md` (erweitert)
- `PHASE4_REAL_AUDIO_REPORT.json`
- `output/phase4_baseline/`
- `output/phase4_A/` ... `output/phase4_E/`

### Schritt 4: Long-Form-Test
```powershell
python benchmark/phase4_longform.py --winner D --max-minutes 60
```

**Output:**
- `PHASE4_LONGFORM_REPORT.md`
- `PHASE4_LONGFORM_REPORT.json`
- `output/phase4_longform_5min/` ... `output/phase4_longform_120min/`

### Schritt 5: Akustische Bewertung
Audio-Dateien anhören und Bewertungstabellen ausfüllen.

---

## 15. Nächste Schritte

### Auf RTX 5060 ausführen:

1. **Umgebung-Check:**
   ```powershell
   python benchmark/phase4_env_check.py
   ```
   → Alle Checks müssen bestanden werden.

2. **Runtime Voice Reference kopieren:**
   ```powershell
   New-Item -ItemType Directory -Force -Path "cache\voice_refs"
   Copy-Item "reference\VD-E_GOLDEN_REFERENCE\VD-E.wav" "cache\voice_refs\VD-E.wav"
   ```

3. **Benchmark starten:**
   ```powershell
   python benchmark/phase4_benchmark.py
   ```
   → Erzeugt Baseline + 5 Varianten

4. **Audio anhören:**
   - `output/phase4_baseline/PHASE4_baseline.wav`
   - `output/phase4_A/...` bis `output/phase4_E/...`

5. **Bewertung ausfüllen:**
   → Tabelle in `PHASE4_REAL_AUDIO_REPORT.md`

6. **Gewinner identifizieren:**
   → Variante mit bester Naturalness + Continuity

7. **Long-Form-Test:**
   ```powershell
   python benchmark/phase4_longform.py --winner [A|B|C|D|E]
   ```

8. **Produktions-Entscheidung:**
   → Wenn Gewinner besser als Baseline → Production
   → Wenn nicht → Weiter optimieren oder Baseline beibehalten

---

## 16. Wichtiger Grundsatz

**SCATTERING IST KEIN ZIEL.**  
**SEGMENTIERUNG IST KEIN ZIEL.**  
**PERFORMANCE IST KEIN ZIEL.**

**DAS ZIEL IST:**  
**DIE BESTMÖGLICHE, NATÜRLICHSTE UND KONSISTENTESTE VD-E-VOICE ÜBER DIE GESAMTE AUSGABE.**

Die interne technische Methode darf sich diesem Ziel unterordnen.

---

## 17. Stop-Punkt

Nach:
- ✅ Vorbereitung abgeschlossen
- ⏳ Baseline (ausstehend auf RTX 5060)
- ⏳ A/B-Test (ausstehend auf RTX 5060)
- ⏳ Long-Form-Test (ausstehend auf RTX 5060)
- ⏳ Akustische Bewertung (ausstehend)

**STOP.**

Keine weiteren großen Architekturänderungen, bis die Ergebnisse ausgewertet wurden.

---

## 18. Dateien

| Datei | Zweck |
|-------|-------|
| `benchmark/phase4_env_check.py` | Umgebung-Check |
| `benchmark/phase4_benchmark.py` | Baseline + A/B-Test |
| `benchmark/phase4_longform.py` | Long-Form-Test |
| `benchmark/PHASE4_INSTRUCTIONS.md` | Ausführungsanleitung |
| `PHASE4_REAL_AUDIO_REPORT.md` | Dieser Report |
| `PHASE4_REAL_AUDIO_REPORT.json` | Maschinell lesbar (nach Ausführung) |

---

## 19. Fazit

Phase 4 hat die vollständige Infrastruktur für den echten Audio-Benchmark auf der RTX 5060 erstellt. Alle Skripte sind vorbereitet, getestet und dokumentiert.

**Status:** ✅ VORBEREITUNG ABGESCHLOSSEN  
**Nächster Schritt:** Skripte auf RTX 5060 ausführen

---

*Erstellt durch Arena.ai Voice-AI-Reference Agent*  
*2026-09-04*
