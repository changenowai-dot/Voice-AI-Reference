# Release Architecture: Voice Reference Bundles

Vier getrennte Schichten mit eigenem Speicherort und eigenem Distributionsmechanismus:

## 1. Source Code (versioniert)
- Pfad: `project/app/`
- Distribution: `git` + `git archive` (ZIP-Release)
- Nie Binary-Blobs außer kleinen Testdaten.

## 2. Runtime-Modelldaten (NICHT versioniert)
- Pfad: `models/` (Qwen3-TTS 1.7B-Base/CustomVoice/VoiceDesign + HF-Cache)
- Distribution: Download via `install.ps1` / `SETUP.ps1`
- Größe: ~8–15 GB; nie committen.

## 3. Runtime-Cache (NICHT versioniert)
- Pfad: `project/cache/` (audio, metadata, segments, voice_output,
  **voice_refs/**, state)
- Erzeugt zur Laufzeit. Wird bei Setup nicht befüllt.
- Darf im Release leer/nicht vorhanden sein.

## 4. Versionierte Referenz-Bundles (versioniert, Source of Truth für Distribution)
- Pfad: `project/app/voices/bundles/<voice_id>.wav`
        + `<voice_id>.wav.json`
- Distribution: `git` + `git archive` (ZIP-Release)
- Werden beim ersten Lauf automatisch nach `project/cache/voice_refs/`
  kopiert (idempotent, bitgenau, SHA-verifiziert) von:
  `project/app/tts/reference_bundle.py::_materialize_from_bundled()`
- Nie zur Laufzeit geschrieben.
- Import-Tool für den GPU-Host:
  `python project/tools/import_voice_bundles.py --from-cache --all`

## 5. VD-E Golden Reference (versioniert, unveränderlich)
- Pfad: `project/VD-E_GOLDEN_REFERENCE/VD-E.wav`
- SHA-256 (LOCKED): `b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025`
- Wird beim ersten Lauf automatisch nach `cache/voice_refs/VD-E.wav`
  kopiert (SHA-geprüft). Kein Resampling, kein Re-Encoding, keine
  Neusynthese. Weicht der SHA ab, wird die Kopie gelöscht und VD-E ist
  gesperrt (Identity-Lock).

## Auflöse-Reihenfolge zur Laufzeit
Für jede Clone-Voice sucht `resolve_bundle()`:
1. VD-E: Golden Reference → SHA-Prüfung → Cache-Kopie.
2. Release-Bundle in `project/app/voices/bundles/<id>.wav` (valides Manifest).
3. Runtime-Cache in `project/cache/voice_refs/<id>.wav` (lokaler Override
   bei GPU-Host-Entwicklung; hat Vorrang bei abweichendem SHA mit Warnung).
4. Nichts gefunden → BundleResolutionError → Stimme ist im GUI als
   "NICHT VERFÜGBAR" markiert.

## Import-Workflow (auf dem GPU-/Arbeits-Host, nach Materialisierung)
```powershell
python project/tools/import_voice_bundles.py --from-cache --all
python project/tools/validate_reference_bundles.py
git add project/app/voices/bundles/
git commit -m "feat(voices): import production reference bundles"
git push
```

## Release-Gates
- Jede ACTIVE Production-Clone-Stimme hat ein Bundle in `bundles/`,
  valide, SHA-konsistent.
- VD-E Golden Reference SHA ist `b156c02a…`.
- `python project/tools/validate_reference_bundles.py` Exit 0.
- Frischer Checkout: `python project/tools/audit_all_voices.py` zeigt
  0 "auswählbar aber defekt".
- Auf dem GPU-Host: `python project/tools/audit_all_voices.py --smoke`
  → alle selektierbaren Stimmen haben `tts_pass=pass` und eine
  abspielbare Output-WAV.
