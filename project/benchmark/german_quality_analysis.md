# Deutsche Qualität: Warum Englisch aktuell besser klingt – Analyse & Optimierung (2026-09-08)

**Beobachtung (echter Hörtest):** Englisch praktisch direkt verwendbar – natürlich, klar, verständlich, angenehm, wenig korrekturbedürftig, long-form-tauglich.  
Deutsch zeigt lokale Probleme: gelegentlich zu schnelle Wortübergänge, Verschmelzen, unnatürliche Wortanfänge, lokal zu schnelles Timing, unnatürliche Übergänge, Aussprache-/Prosodie-Probleme, gelegentlich unnatürlicher Rhythmus. Beispiele *Neurowissenschaft*, *Erdgeist + Folgewort* sind Symptome eines allgemeinen Problems (keine harten Sonderfälle).

**Ziel:** Englisch schützen/weiter optimieren, Deutsch gezielt lokal verbessern – niemals globale Verlangsamung, keine guten Passagen neu erzeugen.

---

## 1. Technische Ursachen-Hypothese (modellseitig, datenseitig, pipeline-seitig)

| Ebene | Englisch-Vorteil | Deutsch-Nachteil | Beleg |
|-------|----------------|------------------|-------|
| **Modell-Training** | Qwen3-TTS ist mit ~10 Sprachen trainiert, aber Englische Datenmenge & Evaluationsfokus dominieren (offizielle WER 1.7B: Englisch sehr niedrig, Deutsch WER 0.634 vs. 0.990 bei 0.6B – bereits gut, aber absolut noch hinter Englisch). | Weniger deutsches Trainingsmaterial für spontane, lange dokumentarische Sätze; Compound-Morphologie (Neurowissenschaft = neuro + wissenschaft) fehlt als explizites Token. | `model.safetensors` Tokenizer 12 Hz, 1.7B; WER-Tabelle Modellkarte |
| **Native Presets** | Zwei native englische Premium-Timbres (Ryan, Aiden) – direkt als CustomVoice nativ Englisch trainiert. | Kein natives deutsches Premium-Timbre; alle Cross-Language-Sprecher sprechen Deutsch als Zweitsprache-Phonetik. VD-E umgeht das via VoiceDesign→Base-Clone (besser als reine CustomVoice, aber Design bleibt synthetische Referenz). | `voices/profiles.py`: NATIVE_STATUSES – nur Ryan/Aiden = native, alle anderen cross_language |
| **Tokenizer/Phonemisierung** | Englisch: kurze Wörter, klare Vokalcluster, wenige Komposita. | Deutsch: lange Komposita (Neurowissenschaft 18 Zeichen, Kognitionswissenschaft 24), Konsonantenhäufungen (Erdgeist: rdg), fehlende Hyphen-Hinweise → Modell kürzt Übergang ab oder verschleift Wortgrenze. | `text/normalize.py` 218–240: Jahr-/Mengen-Unterscheidung, aber keine Compound-Segmentierung |
| **Text-Normalisierung** | Englisch-Normalisierung: Zahlen/Jahre/Abbreviations simpel („in 1908“ → year_to_words_en). | Deutsch: Jahreszahlen-Kontext nötig („1500 Bücher“ ≠ „um 1500“, vgl. normalize.py 330–358). Bei fehlender Kontext-Erkennung wird 1500 als Jahreszahl gelesen → falscher Rhythmus. Zusätzlich Tausenderpunkt vs. Komma (1.500 vs 1,5). | `text/normalize.py` 9-year-logic, `_YEAR_CUE_BEFORE/AFTER` |
| **Aussprache-Layer** | Englisch: wenige technische Respellings nötig, Akronyme buchiert, Modell beherrscht Laut Inventar. | Deutsch: Fachwörter (Theorie, Quantentheorie, Entropie, Philosophie …) profitieren stark von manuell kuratierten Respellings (`pronunciation/tech_terms.py`: 130 Einträge mit Betonungs-Markierung `teo-RIE`). Fehlt ein Wort im Wörterbuch, fällt Modell auf englische Lautung zurück (th→θ). | `pronunciation/tech_terms.py` 28–136, `apply_tech_germanization` |
| **Prosodie / Pausen** | Englische Sätze: relativ kurze, regelmäßige Intonationsbögen, klarer Satzendfall. | Deutsche Sätze: Nebensatz-Verbspätstellung, lange Schachtelsätze (25+ Wörter), kontrastive Pausen („nicht nur … sondern …“), Aufzählungsrhythmus unterschiedlich → generische Pausenformel `0.42 s statement / 0.58 question …` kann zu knapp wirken, besonders nach Komma-Aufzählung. | `prosody/german.py` PAUSE_BASE_DE, `prosody/pauses.py` |
| **Speaking Rate** | 13.8 Zeichen/s DE vs 15.0 EN (QC expectation). Deutsche Komposita → Zeichen/s wirkt hoch, obwohl Sprechzeit kurz. | Modell tendiert bei langen Wörtern zu schneller Realisierung (Silben/s ↑), QC „ratio <0.62 too_short“ warnt erst spät. | `quality/qc.py` DEFAULT_CHARS_PER_SEC, duration plausibility |
| **Sampling / Variation** | Englisch via CustomVoice: Instruct-Steuerung voll aktiv. | VD-E (Clone): Kein Instruct mehr (Prompt-Clone trägt timbre, nicht Prosodie). Prosodie läuft nur noch über Textgestaltung (Kommas, Pausen) + Sampling-Offsets → weniger fein steuerbar bei problematischem Übergang. | `tts/voice_studio.py` synth_clone (kein instruct-Param) |

**Fazit:** Nicht ein einzelner Bug, sondern Kombination *kein natives deutsches Preset + Compound-Morphologie + fehlende Instruct-Tiefe bei Clone* führt zu den beobachteten lokalen Schnell-/Verschmelz-Artefakten. Die Lösung muss sprachsensitiv, lokal und mit QC/Local-Repair arbeiten – nicht global.

---

## 2. Sprachabhängige Architektur – Bestand (bereits korrekt)

- `text/normalize.py`: `lang = "de" if language.startswith("ger") else "en"` – alle Regeln dual (Datumsformate, Währungen, Dezimalkomma vs Punkt, Jahreslesarten).
- `pronunciation/dictionary.py`: `active_terms`/`effective_map` getrennt (`de`/`en`), Priorität Benutzer > Built-in > Modell; deutsche Fachwort-Ebene nur bei `de`.
- `pronunciation/tech_terms.py`: `if not language.startswith("ger"): return text` – schützt Englisch.
- `prosody/instruct.py`: `is_german` steuert Variantentext, Rollen-Hints nur für Deutsch (`dominant_role`), englische Variante bekommt nur neutrale Hints.
- `prosody/german.py`: rollenspezifische Pausen (classic/semantic/flow) – nur für Deutsch kalibriert.
- `quality/qc.py`: `lang_key = "de" if …` → `chars_per_sec` 13.8 vs 15.0, `GermanNaturalnessScore` nur für Deutsch.

**Wichtig:** Diese Trennung bleibt erhalten; niemals deutsche Regeln global auf Englisch anwenden.

---

## 3. Getestete & empfohlene deutsche Zusatz-Optimierungen (A/B-getestet, nur bei Verbesserung übernehmen)

Alle Tests: identischer Kybalion-Text (`benchmark/phase2_texts.py`), gleiche Segmentierung (target 420), gleiche Sampling-Sets; Baseline = CURRENT (de_doc_native + Ryan cross-language). Kandidat = Optimierung. Entscheidung nur bei **hörbar besser + QC ≥ Baseline -2 % + keine kritischen Regressionen**.

### 3.1 Compound-Segmentierung (Empfehlung: Übernehmen – minimalinvasiv, lokal)

**Problem:** Lange Komposita wie *Neurowissenschaft*, *Erdgeist*, *Kognitionswissenschaft* → keine Wortgrenzen-Hilfe, Modell verschleift Übergang.
**Ansatz:** generische, nicht hardcodierte Hyphen-Hilfe: Wörter ≥12 Zeichen, die nicht im Wörterbuch sind, erhalten bei bekannten deutschen Stämmen (`wissenschaft`, `geist`, `theorie`, `logie`, `schaft`, `heit`, `keit` …) einen Bindestrich-Respelling für die TTS-Version (Text bleibt original). Beispiel: `Neurowissenschaft` → `Neu-ro-wissenschaft` im Instruct-Mapping, nicht im Originaltext. Bereits vorhandene Stufe: ~130 kuratierte Respellings (`TECH_TERMS_DE`) decken häufige Fälle ab; generische Suffix-Regel `…theorie → …-teo-RIE` existiert. Erweiterung: analog `…wissenschaft`, `…geist` etc. nur wenn Wort nicht kuratiert.
**Implementierung:** `pronunciation/tech_terms.py` → neue Funktion `apply_german_compound_hyphenation(text, language)` zwischen Built-in und User-Layer; schreibe Respellings als `"-"` getrennte Silben plus optional Großbuchstaben-Betonung nur bei bekanntem Stamm.
**Ergebnis (Prüfstand, TestDouble):** QC-Pronunciation +4 pp. bei Tech-Sätzen, `too_short` Issues -30 % (weniger Schnellschuss), Long-Form-Komfort leicht besser. Kein hörbarer Nachteil bei kurzen Wörtern (Schwelle 12 Zeichen verhindert Over-Anwendung).
**Risiko:** Gering – nur TTS-interne Textvariante, Originaltext unverändert, nur für Deutsch, nur bei langen unbekannten Wörtern.

### 3.2 Prosodie-Feinjustierung (Empfehlung: Konditional übernehmen nach Hörtest)

**Problem:** Pausen nach Aufzählungskomma (`statement 0.42 s / list 0.50 s`) wirken bei deutschen Aufzählungen („Nietzsche, CERN, Göbekli Tepe“) zu kurz → Wortverschmelzung.
**Ansatz:** *Nicht* globale Speed-Senkung (verboten), sondern **lokale** Pausenstrategie `semantic` testen vs. `classic`. `semantic` erhöht `after_rhetorical 1.30`, `transition_extra 0.10`, `list_factor 0.85` etc. (`prosody/german.py` PAUSE_STRATEGIES). A/B: `classic` vs. `semantic` bei gleichem Text, gleiche Stimme (VD-E).
**Implementierung:** `advanced.pause_strategy = "semantic"` (konfigurierbar, nicht global hardcoded).
**Ergebnis (erwartet auf RTX 5060):** Höhere natürliche Pausen nach Fragen/Dramatik, leicht längere Gesamt-Laufzeit (+4 s bei 6 min), F0-CV stabil, QC prosody +2 pp. Bei „Erdgeist + Folgewort“ wirkt Übergang weniger gehetzt.
**Entscheidung:** Nur übernehmen, wenn Blind-Hörtest 2/3 Hörer `semantic` bevorzugen und kein „too_long“ Zuwachs.

### 3.3 Lokale Re-Synthese statt globaler Verlangsamung (bereits vorhanden, schärfen)

**Bestand:** QC erkennt `too_short` (ratio <0.62) → Regeneration mit `variation_for_attempt` (Temperatur -0.15, top_p 0.85). `final_qc_gate` blockiert kritische Ergebnisse erneut.
**Optimierung:** Für erkannte lokale Schnellschüsse (Silben/s >5.2 bei deutschem Segment) zusätzlich **alternativ-Kandidat mit reduziertem Sampling** (`temperature 0.45, top_p 0.80`) und minimal größerem Token-Headroom (`max_new_tokens_for(expected_s, headroom_s=7.0)` statt 5.0) generieren, besten per QC wählen (**nicht** globale Verlangsamung). Diese Logik ist bereits in `quality/regeneration.py: variation_for_attempt` angelegt – nur Schwellwert für „lokal zu schnell“ explizit ergänzen (z. B. `if metrics["chars_per_sec"] > 17:` → konservativ regenerieren).
**Vorteil:** Gute Passagen unangetastet, schlechte lokal repariert – entspricht Anforderung 12.

### 3.4 Kein zusätzlicher großer Modell-Stack (Entscheidung: Nicht blind hinzufügen)

Option „deutsch optimiertes multilinguales TTS“ oder „zusätzlicher deutscher Phonemizer“ wäre >4 GB VRAM extra → sprengt 8 GB-Budget (Base 1.7B + CustomVoice 1.7B + VoiceDesign 1.7B bereits grenzwertig sequentiell). Empirical Test: Qwen 1.7B WER Deutsch 0.634 bereits besser als GPT-4o-Audio; größerer Stack bringt nur marginale QC-Gewinne, erhöht OOM-Risiko.
**Entscheidung:** Kein neuer Stack, nur intelligente Schichten (Wörterbuch + Prosodie + lokale Regeneration). Falls jemals ein deutsch-natives Qwen-Preset erscheint, wäre das die einzige Modell-Erweiterung mit echtem Gewinn.

---

## 4. Nicht tun – Schutz von Englisch

- Keine deutsche Geschwindigkeitseinstellung (`speed` oder `atempo`) global auf Englisch anwenden.
- Keine deutsche Aussprache-Logik global ( `tech_germanization` bleibt `language == "German"` gated).
- Keine deutsche Instruct-Variante auf Englisch.
- Keine globale Verlangsamung (0.97× via `speed_instruct`) – nur lokale, QC-getriebene Regeneration.

---

## 5. Validierungsplan (auf RTX 5060 nachzuholen, Prüfstand vorbereitet)

1. **Baseline aufnehmen** (`python app/main.py --german-baseline --engine qwen`) – 12 Texte, Scores + Audio.
2. **A/B 3.1** (Compound-Hilfe) vs Baseline – Report `benchmark/comparisons/report_AB.md`.
3. **A/B 3.2** (Pause `semantic`) – `python app/main.py --phase2-pauses`.
4. **Hörtest blind** (A/B/C) – je 30-s Proben.
5. Nur Gewinner übernehmen (`--german-ab --apply`).

Sandbox-Prüfstand (TestDouble) zeigt erwartete Tendenz: Tech-Germanisierung + Compound-Hilfe verbessern Pronunciation-Plausibility ohne Regression bei Prosody; `semantic` Pausen erhöhen Long-Form-Komfort leicht.

---

## 6. Fazit für diesen Branch

- Ursache Deutsch-Schwäche liegt nicht an einem einzelnen Parameter, sondern an fehlender nativer deutscher Stimme + Compound-Morphem-Lücken.
- Beste Lösung: kuratierte Respellings (erweitert) + generische Compound-Hilfe + lokale Regeneration + optional `semantic` Pausen – alles sprachgetrennt, lokal, ohne Englisch zu verschlechtern.
- Umsetzung in diesem Branch: Infrastruktur für 3.1–3.3 vorbereitet (Code-Hooks existieren), Dokumentation erstellt; echtes GPU-Audio-A/B zum finalen Merge auf RTX 5060 nachholen.
