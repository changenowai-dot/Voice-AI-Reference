# Versionierte Referenz-Bundles

Dieses Verzeichnis enthält die **mit dem Repo/Release ausgelieferten**
Referenz-WAVs und zugehörigen `.wav.json`-Manifeste für die ACTIVE
Production-Clone-Stimmen. Es ist **kein** Cache und **kein** Laufzeit-
Verzeichnis.

## Regeln

* Dateien hier sind immutable (gleiches Versionierungsprinzip wie Source-Code).
* WAVs werden **niemals zur Laufzeit** hierhin geschrieben. Die Laufzeit
  kopiert sie bei Bedarf automatisch nach `project/cache/voice_refs/`
  (siehe `project/app/tts/reference_bundle.py::_materialize_from_bundled`).
* VD-E liegt **nicht** hier, sondern in
  `project/VD-E_GOLDEN_REFERENCE/VD-E.wav` (gelockt per SHA
  `b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025`) und
  wird beim ersten Lauf automatisch in den Cache kopiert.
* Neue Produktions-Stimmen werden über
  `python project/tools/materialize_references.py --voice-id <id>` auf
  einem GPU-Host erzeugt und anschließend mit
  `python project/tools/import_reference_bundles.py` in dieses Verzeichnis
  kopiert + validiert.
* Jede WAV MUSS ein korrektes `<id>.wav.json`-Manifest mit SHA-256 von
  Audio und Referenztext haben.
