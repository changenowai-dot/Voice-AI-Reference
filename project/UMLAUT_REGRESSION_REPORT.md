# REGRESSION REPORT — Deutsche Aussprache (Ä Ö Ü ß)

**Datum:** 2026-09-25 · **Zweig:** `arena/01a0ce4d-voice-ai-reference`
**Sync-Basis:** Remote-Stand `c96bb4e` (dein lokaler HEAD, verifiziert via
`git ls-remote`) + Pacing-Re-Apply `5d9ba1d` + dieser Fix `1237ff5`.

---

## A) ROOT_CAUSE

**Zentrale, historisch belegte Feststellung:** Eine allgemeine deutsche
Umlaut-/Orthografie-Schicht, die „früher da war und entfernt wurde",
**existierte in dieser Codebasis nie.** Der Log-Befund
`replacements=0 chars_in=641 chars_out=641` ist das korrekte Verhalten der
aktuellen Architektur — nicht die Folge eines Verlusts. Beweise:

- `TECH_TERMS_DE` in **allen 13 Historie-Versionen** (9a64fb4 → c96bb4e):
  **0** Alltags-Umlautwörter (Äpfel, größte, Straße, hören … nie enthalten).
- `builtins_de.json` (2 Versionen): einzige Änderung = Psychologie/
  Neurowissenschaft (Respell→Identity, host-verifiziert).
- `normalize.py` (3 Versionen): nur Zahlen/Symbole/Akronyme; **kein**
  `unicodedata`/Transliteration/NFK je im Repo (`git log -S unicodedata`: leer).
- `qwen_engine.py`: unverändert seit `2bc8438` — Engine/Prompt-Zusammenbau
  konstant über den ganzen Zeitraum.
- Reproduktion deines 641-Zeichen-Tests: Umlaute **codepunkt-identisch**
  GUI→TTS (Ä2/Ö1/Ü2/ä5/ö13/ü14/ß14 vor und nach normalize+Engine).

**Was die Regression stattdessen wirklich ist** — drei codebewiesene
Defekte, die genau die deutsche Orthografie-Kette betreffen, plus ein
Testinfrastruktur-Defekt, der Frees verursachte:

1. **`PACING_HINT_DE` war ASCII-entstellt** (`instruct.py`, seit `9b026c6`):
   der deutsche Prompt-Satz lautete „Atme **natuerlich** zwischen
   **Saetzen** … **gleichmaessigen** …" — anglo-Orthografie **im TTS-Prompt**
   selbst, bei jedem Lauf mit `pacing_hint`-Presets (deep_documentary!).
2. **Namens-Heuristik behandelte normale deutsche (Umlaut-)Wörter als
   riskante Unbekannt-Namen** (`names.py`): `_looks_german` hatte kein
   einzelnes `ä` in der Musterliste (nur äu/ü/ö/ß) und keine gängigen
   Nominalmuster → „Äpfel/Bäume/Türen/Bücher/Umlaute" wurden als
   `risk=True` geflaggt; der dokumentierte Satzanfang-Ausschluss („nicht
   Satzanfang") war **nie implementiert**. Das Diagnose-Signal, das
   Umlaut-Probleme sichtbar machen soll, war für genau diese Wörter blind/
   verrauscht (dein Log: `unknown_problem_terms=5` — 5 Fehlalarme).
3. **Keine Umlaut-Observability:** der Preprocess-Log wies nicht aus, ob
   Umlaute die Kette überhaupt überleben — eine Encoding-Regression wäre
   unsichtbar gewesen (QC `pron=97` misst Textabdeckung, nicht Akustik).
4. *(Infrastruktur, während der Analyse aufgedeckt)*
   `test_phase3_api_end2end` startete den Server mit **nie gelesener
   stdout-PIPE**; das phase3-Logvolumen (~62–65 KB) liegt an der
   64-KB-Puffergrenze → zufällige Freezes (reproduziert, bisektiert,
   behoben).

## B) FIX (Commit `1237ff5`)

| Datei | Änderung |
|---|---|
| `app/prosody/instruct.py` | `PACING_HINT_DE` mit echter Orthografie: „Atme **natürlich** zwischen **Sätzen** … **gleichmäßigen** Erzählrhythmus …" |
| `app/pronunciation/names.py` | (a) Wörter mit ä/ö/ü/ß ⇒ „deutsch wirkend" (kein risk-False-Positive mehr); (b) satzinitialer Großbuchstabe nach Satzende/Textanfang ⇒ kein Eigennamen-Signal (implementiert die dokumentierte Absicht) |
| `app/pronunciation/engine.py` | `umlaut_words=N` im `PRONUNCIATION_PREPROCESS_END`-Log (Observability; **ändert keinen Text**) |
| `tests/test_phase3.py` | e2e-Server-stdout in Temp-Datei statt ungelesener PIPE (Freeze-Klasse beseitigt; **alle Assertions unverändert**) |
| `tests/test_umlaut_regression.py` | **NEU**, 10 Gates (s. unten) |
| `tools/test_pronunciation_umlaut_ab.py` | **NEU**, frische TEST A/B/C-Fingerprints für den GPU-Host |

Keine globale ä→ae/ö→oe/ü→ue/ß→ss-Substitution, keine neue Wortlisten-
Ersetzungsschicht, Pronunciation-Engine-Pfad und Prioritäten unverändert.

## C) PREVIOUS_BEHAVIOR

- **Textpfad Umlautwörter:** in jeder Version identity → Qwen (nachweisbar).
  „Früher besser" kann daher aus dem Textpfad dieser Codebasis nicht
  stammen; plausibel ist der Unterschied durch **Fachwort-Respells-Zeiten**
  (Psyche/Physik/Theorie-Familie waren respellte Wörter mit hörbarem
  Unterschied), andere Voices/Texte in alten Tests sowie die zwischen
  `ba2b628` und `c96bb4e` bewusst geänderte Prosodie (relaxed/narrative,
  Pausen kommen seit `e2e740c` überhaupt ins Audio, pacing_hint).
- Die Intuition „früher funktionierte es" gilt historisch **für die
  Fachwörter** (dort gab es Regeln und Host-A/B-Nachweise) — für
  Alltags-Umlautwörter gab es nie eine Logik, die man hätte entfernen
  können. Diese Schicht wird jetzt erstmals sauber aufgebaut: als
  Observability + Gates + frische Host-A/B-Payloads, belegbasiert statt
  pauschal.

## D) REGRESSION_EVIDENCE

- `git log -S umlaut/Umlaute` → nur 3 Commits (9a64fb4-Dokumente,
  ba2b628-Kommentar, 9d67cef-Report-Zeile); **kein** Code je entfernt.
- `git log -S unicodedata` / `orthograf*` / `Ersatzschreibung`: **leer**.
- 13× `TECH_TERMS_DE`-Versionen: grep Alltags-Umlautwörter = 0 Treffer.
- `PACING_HINT_DE` ASCII-Fassung: eingeführt in `9b026c6` (vorher nicht
  vorhanden) — dein Lauf mit `deep_documentary` enthielt diesen Satz.
- `_looks_german`-Musterliste vor Fix: kein `ä`, kein `-el/-e/-te` →
  „Äpfel/Lampe/Nebel/Umlaute" = `risk=True` (Fehlalarme in deinem Log).
- Pipe-Freeze: mit Fixes an ungelesener PIPE gestoppt (60 s, `running:
  true`), ohne Fixes 17,2 s fertig; Logvolumen 62.376–64.596 B vs. 65.536
  B Pipe-Puffer.

## E) TEST_RESULTS (Vorher → Nachher, Tex ebene)

| Prüfung | Vorher | Nachher |
|---|---|---|
| 641-Z-Text: replacements / Codepunkte | 0 / identisch | 0 / identisch (Guard-Test) |
| `unknown_problem_terms` auf deinem Text | 5–6 (Äpfel, Lampe, Nebel, Bitte, Besonders, Umlaute) | **3** (nur noch nicht-Umlaut-Rest: Lampe, Nebel, Umlaute — dokumentierte Restlimitation der Diagnostik, kein Texteingriff) |
| `umlaut_words` im Log | fehlte | **47** (dein Text) |
| TEST A (40 Wörter): identity / keine ae-oe-ue-ss | ungeprüft | **40/40 identity**, Substitutions-Guard grün |
| TEST B (6 Sätze) | ungeprüft | identity, repl=0, fp frisch |
| TEST C (20 Fachwörter) | — | **20/20** auf eingefrorenen Produktionswerten (Psyche→Pü-che, Physik→FY-sik, Phänomen→Fä-NO-men, Energie→E-NER-gie, Philosophie→Fi-lo-zo-FIE, Transmutation, Kern-fy-SIK …; **Wissenschaft/Bewusstsein/Quantenphysik = Identity eingefroren**) |
| tests | — | umlaut 10/10 · phase3 **21/21 (endlich ohne Hang)** · cascade 27/27 · textstack 10/10 · segmentation 10/10 · pronunciation 6/6 |
| Frische Fingerprints (reused=0) | — | 3/3 verschieden, Arbeitsblatt `cache/umlaut_ab_payloads.json` |

**Akustisch:** Im Sandbox-Umfeld keine Synthese möglich (torch-Stub). Die
A/B/C-Payloads sind vorbereitet; das akustische Urteil fällt am GPU-Host
per Hörprüfung (Kriterien: Ä/Ö/Ü/ß je Wort, natürliche Sätze, Fachwörter,
kurze+lange Segmente — Punkte 1–10 des Auftrags).

## F) SAFETY

- ✅ VD-E.wav **4×** `b156c02a60a873ad…` (Golden, cache/VD-E, cache/vd_e,
  reference/) — unangetastet; GUI-Logs „Golden Reference direkt" +
  „identitätsgesichert" bleiben erhalten.
- ✅ Nur Teil A (`Voice-AI-Reference`); kein Stand B, kein Master-LIVE.
- ✅ `pronunciation/pronunciation.json` byte-identisch (SHA
  `03ac29aa…`), `config.json` BOM/speed 1.0/target 130 — von jedem
  Testlauf restauriert (e2e-Apply-Pollution erkannt und zurückgeschrieben).
- ✅ Fachwortregeln eingefroren und per Gate geschützt (Test 3 + 9):
  keine Verschlechterung durch die Umlaut-Fixes möglich.
- ✅ Keine bloß kosmetische Lösung: Prompt-Orthografie, Diagnostik-Signal,
  Observability, Freeze-Klasse und 10 permanente Gates sind
  verhaltensrelevante Reparaturen; nicht grün-gemacht, sondern gemessen.
- ✅ Zwischenstand gesichert & gepusht: `c96bb4e → 5d9ba1d → 1237ff5`.

## Nächster Schritt (Host)

`python tools/test_pronunciation_umlaut_ab.py` ausführen (funktioniert
ohne GPU, schreibt `cache/umlaut_ab_payloads.json`) und die drei
Payloads mit `de_male_cinematic_restrained_01`/`deep_documentary`
frisch synthetisieren (reused=0). Hörprüfung je Tabelle oben. Sollten
konkrete Wörter akustisch falsch klingen (z. B. „größte"), liefern die
Payloads + Gate-Struktur den belegbasierten Weg für gezielte, minimale
Einzel-Respells im dokumentierten Batch-Prozess — nicht pauschal.
