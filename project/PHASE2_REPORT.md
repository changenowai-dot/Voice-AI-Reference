# PHASE 2 COMPLETE — Voice Design & Deutsche Prosodie-Optimierung

**VoiceOverApp 1.2.0** · Auftrag: deutlich natürlichere deutsche
Erzählerstimme über Qwen3-TTS, inkl. VoiceDesign-Testung und Blindvergleich.
Phase 1 bleibt als **unveränderlicher Referenzstand und Produktionsfallback**
erhalten (§2, §23).

---

## 1. Deine Rückmeldung → unmittelbare Konsequenzen

| Hörbefund (Nutzer) | Maßnahme in Phase 2 |
|---|---|
| „Ryan ist nicht der gewünschte Sprecher“ | VoiceDesign-Kandidaten A–F (designierte Stimme statt fester Timbre-Pool) + CustomVoice-Sweep; **Ryan/config wird nie als endgültige Wahrheit behandelt** |
| „Betonungen teilweise unpassend“ | Hinweis-Budget (§7): statement/calm/transition ohne Hinweis, Dramatik nie 2 Segmente hintereinander; Rollen-Hinweise nur noch gezielt |
| „Satzmelodie nicht immer natürlich“ | 3 neue Rollen (EXPLANATION/TRANSITION/CALM), rotierender Kontur-Anker (keine identische Instruct-Wiederholung), Langsatz-/Short-Run-Dramaturgie, Fragemelodie-Setup („Doch was passiert, wenn …?“) |
| „Noch nicht YouTube-fertig“ | Alles nur über A/B + Blindvergleich + deine Auswahl; keine ungeprüften Behauptungen (§22) |

## 2. Was gebaut wurde

### 2.1 VoiceDesign-Pipeline (§3)
- **QwenVoiceStudio** + **Modell-Pool** (max. EIN Modell gleichzeitig in
  8 GB VRAM; CustomVoice ↔ VoiceDesign ↔ Base werden getauscht, VRAM
  wird freigegeben).
- **Design→Clone-Workflow** (offizielle Qwen-Empfehlung für Langform):
  VoiceDesign erzeugt eine Referenz in der Ziel-Persona → Base-Modell
  baut einen wiederverwendbaren Clone-Prompt → **alle Segmente mit
  demselben Prompt** = maximale Konsistenz. Referenz wird persistent
  unter `cache/voice_refs/` gespeichert.
- **6 Beschreibungen**: A/B/C wörtlich aus dem Auftrag + D (glaubwürdiger
  Journalist), E (Hörbuch-Tiefe, rauchig), F (philosophisch-besonnen).
  Keine „German accent“-Formulierung — echte muttersprachliche Identität.
- Zusätzlich Kandidat **VD-B-DIRECT** (ohne Clone) im Volltest, um den
  Konsistenz-Nutzen der Clone-Strategie selbst zu messen.
- **VoiceCloneEngine**: Produktionstrieb für `engine_mode=voicedesign`
  (Pipeline läuft unverändert mit Cache/QC/Resume; neuer Cache-Namespace).

### 2.2 Prosodie (§5–§12)
- **Analyse der Unnatürlichkeit** (dokumentiert, prüfbar): (a) feste
  Wiederholung identischer Instructs lockt jede Kontur gleich,
  (b) zu viele Dramatik-Hinweise → „Ansager“-Rhythmus, (c) lange Sätze
  ohne Gliederung, (d) fehlende Frage-Melodie bei rhetorischem Setup.
- **Rollen**: STATEMENT, QUESTION, RHETORICAL_QUESTION, EMPHASIS, LIST
  (ex-enumeration), CONTRAST, **EXPLANATION, TRANSITION, DRAMATIC, CALM**;
  Mehrsatz-Segmente erhalten die *dominante* Rolle (Satzende doppelt
  gewichtet).
- **Überbetonung verhindert** (§7): Budget — ruhige Rollen ohne Hinweis,
  Dramatik mit Abstand ≥ 2 Segmente; AUTO-Emotion neutral = kein
  Emotionszusatz.
- **Satzenden** (§9): 3 rotierende Konsistenz-Formulierungen.
- **Rhetorische Fragen** (§8): Setup-Muster „Doch was/wer/wenn/warum …?“
  explizit erkannt → Melodie-Hinweis + verlängerter Antwortraum.
- **Pausen** (§10): Strategien `classic | semantic | flow` (semantisch:
  +Raum nach Fragen/Dramatik, Atmung bei Transitionen; flow: knapper im
  Absatz) — Sonde `--phase2-pauses`, aktivierbar via
  `advanced.pause_strategy`.
- **Lange Sätze** (§11): Struktur-Hinweis („breathe at commas, land
  clearly“) ab 25 Wörtern; **kurze Satzfolgen** (§12): Build-Dramaturgie
  first→middle→last („Sieben Prinzipien. / Sieben Regeln. / Eine einzige
  Ordnung.“) mit Auflöse-Pause am Ende.

### 2.3 Aussprache (§13, §14)
- +70 Einträge: Kybalion (→ Kü-ba-li-on), Hermes Trismegistos
  (→ Tris-me-gis-tos), Thoth, Gnosis, Kabbala, Smaragdtafel,
  Mentaltransmutation, a priori/a posteriori/ad infinitum, Systemtheorie,
  Neurowissenschaft, Autopoiesis, Homöostase, Luhmann, Bateson, von
  Foerster, Prigogine, Blavatsky, Atkinson, Ramacharaka …
  (insg. 249 Built-in-DE-Eintrräge; keine blinden Phonetik-Ratespiele —
  nur belegte deutsche Lesarten).
- Gazetteer um Hermetik + Systemwissenschaft erweitert (riskante Namen
  werden gekennzeichnet, nicht geraten).
- Kontextbewusstsein (§14) aktiv wie in Phase 1 (Gesamtsprache + Wort +
  Wörterbuch; echte englische Phrasen bleiben englisch).

### 2.4 Sprecher-Auswahl nicht nach F0 (§4, §25)
- Phase-2-Vergleichsschlüssel: **0,45·DE-Score + 0,25·Natürlichkeit +
  0,20·Konsistenz + 0,10·Aussprache — F0-frei.**
- Phase-1-Stimmenbenchmark nachgeschärft: F0 nur noch als
  Plausibilitätsband (m 92–150 Hz, w 150–230 Hz) statt „tiefer=besser“.

### 2.5 Blindvergleich & Nutzer-Vorrang (§18–§20)
- Alle Kandidaten → neutrale `benchmark/phase2/blind/sample_A.wav…`,
  Schlüssel `blind_key.json` wird in der UI **erst nach deiner Auswahl
  enthüllt**.
- UI-Karte „Phase 2 – Voice Studio“: Start (Voll/Schnell), Audio-Player
  je Buchstabe, Auswahl-Dropdown, Speichern, Übernahme-Button,
  Score-Tabelle + automatische Empfehlung (nur Information).
- CLI: `--phase2-run [--quick]`, `--phase2-pauses`, `--phase2-pick B`,
  `--phase2-apply`.

### 2.6 Phase-1-Schutz (§2, §23)
- Harte Pfad-Prüfung (`assert_no_phase1_write`) + Sentinels in Tests.
- Automatische Empfehlung **ersetzt nichts**: übernommen wird nur bei
  klarer Verbesserung (DE ≥ +2,0, Konsistenz nicht schlechter, keine
  kritischen Segmente) **und** deiner Blindauswahl (§20/§23).
  Sonst bleibt Phase 1 Produktionsfallback.

## 3. Vergleichsdesign (§16, §17)
- Text: **Kybalion, wörtlich** (10 Sätze, ~1,5 min, enthält: Jahr 1908,
  Namen, Gedankenstrich-Parenthese, Short-Run, rhetorische Struktur,
  Fachbegriffe).
- Kandidaten mind.: `P1-CURRENT` (deine Konfiguration, Legacy-Instruct =
  genau das, was du gehört hast), `P1-…` Sweep (Speaker × Varianten),
  `VD-A…F` (Clone), `VD-B-DIRECT`.
- Messwerte je Kandidat: DE-Score, Natürlichkeit, Melodie, Aussprache,
  Rhythmus, Pausen, **Konsistenz über alle Segmente** (F0-/LUFS-/Tempo-
  Streuung), kritische Segmente, Dauer + Hördatei.

## 4. Testergebnis (technisch, §22/§24)
**103/103 bestanden** (17 neue Phase-2-Tests, u. a. Kybalion-Wörtlichkeit,
Rollen, Budget, Rotation, Short-Run, Strategien, Studio-Konsistenz,
Phase-1-Schutz, Blindvergleich Ende-zu-Ende über HTTP inkl. Auswahl +
Übernahme; komplette alte Suite weiterhin grün → keine Regressionen in
Batch/Cache/Resume/WAV/MP3/QC/Fortschritt/Wörterbuch/Long-Form).

**Ehrliche Grenze:** Diese Sandbox hat keine GPU — die akustische
Entscheidung (Welche Stimme gewinnt wirklich?) kann hier nicht getroffen
werden und wurde bewusst **nicht** behauptet. Sie ist als Ihr
Blindvergleich auf der RTX 5060 angelegt; die automatisch Empfehlung ist
vorab `null`-sicher (Phase 1 bleibt, bis ein Kandidat klar gewinnt UND
Sie ihn wählen).

## 5. Ausführung auf dem Zielsystem (RTX 5060)
```
START.bat  →  Erweitert → Phase 2 – Voice Studio
   [▶ Phase-2-Vergleich starten]      # lädt VoiceDesign+Base bei Bedarf (~4 GB)
   Blindproben anhören → Sample wählen → [Auswahl speichern]
   [Auswahl als Produktionsstimme übernehmen]
```
oder CLI: `python app/main.py --phase2-run` → `--phase2-pick B` →
`--phase2-apply`. Danach optional `--phase2-pauses` und
`advanced.pause_strategy` auf `semantic`/`flow`, falls es beim Hören
besser wirkt. Der erste Produktionslauf mit Clone-Stimme baut den Cache
neu auf (erwartet, da neue Engine-Keys).

## 6. Gewinner / Parameter (Stand Sandkasten-Prüfung)
- Technischer Gewinner muss auf Zielsystem gemessen werden —
  `benchmark/phase2/comparisons/report_phase2.{md,json}` enthält die
  Rangliste, `recommendation.json` die begründete Empfehlung.
- Konfiguriert bleibt bis dahin: Phase 1 (`de_restrained`/Ryan auf
  deinem Rechner) als Fallback (§23).

## 7. Bekannte Probleme / Empfehlungen
1. Clone-Stimme trägt keinen Stil-Instruct (API-Limit des Base-Modells):
  Prosodie läuft über Text-/Pausen-Ebene; genau deshalb misst VD-B-DIRECT,
  ob der Clone-Pfad überhaupt nötig ist.
2. VoiceDesign-Modelle (~2 GB) werden beim ersten Phase-2-Lauf geladen —
  einmalig einige Minuten; VRAM-Pool sorgt für Stabilität.
3. Falls alle VoiceDesign-Kandidaten die Phase-1-Stimme nicht schlagen:
  vollständig dokumentierter Verbleib auf Phase 1 ist ein legitimes,
  gewolltes Ergebnis (§23).
4. **Phase 3 nicht gestartet** (Auftrag §24): bereite u. a. ASR-basierte
  Aussprache-Verifikation, feinere Emotionssteuerung über den Kybalion-
  Blindvergleich-Datensatz vor — wartet auf deinen Hörbefund.
