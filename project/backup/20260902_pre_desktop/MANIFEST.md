# Backup vor Desktop-App-Phase (2026-09-02)
Cache-Version vorher: q3p-v1 (nachher: q3p-v2-integrity, Produktion)
VD-E erwarteter SHA256 (Produktion, Benutzermaschine): B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025
Gesicherte Dateien: pipeline.py, sampler.py, qwen_engine.py, regeneration.py, paths.py, main.py, config.py
Geändert in der Desktop-Phase: pipeline.py (Final-Gate, voice_id/seed, Streaming-Assembly),
  sampler.py (Cache-Version, Headroom), qwen_engine.py (allow_design),
  paths.py (Frozen-EXE-Root), main.py (--job, --desktop-voices), config.py (production-Sektion).
Neu: app/security/, app/jobs/, app/gui/, app/text/pdf_import.py,
  app/voices/registry.py + desktop_benchmark.py, app/quality/final_gate.py,
  desktop.py, VoiceOverApp.bat, build_windows.ps1, config/production.json,
  voices/*.json, tests/test_desktop_app.py.
VD-E-Hash-Prüfungen: vor Umbau (produktion.json angelegt), nach jedem Backend-Test
  (identity_check-Event), nach GUI-Integration (Test test_identity_lock_*).
