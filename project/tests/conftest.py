"""Schutz der Produktionsdaten vor Testläufen (Regressionsschutz).

HINTERGRUND (2026-09-24, während der Pacing-Analyse nachgewiesen)
-----------------------------------------------------------------
Mehrere Tests schreiben über ``app.config.save_config`` bzw. über
Benchmark-Module (``german_ab.run_ab``, ``phase2_ab.apply_pick_or_candidate``)
in die ECHTE Produktionskonfiguration. ``update_config()`` lädt, merged und
speichert – ein Test, der sie aufruft, persistiert also dauerhaft.

Von einem einzigen normalen Testlauf beobachtete Mutationen von
``config/config.json`` (Auslieferungszustand -> danach):

    speed                          1.0  -> 1.1      (tests/test_system.py:24
                                                     via update_config)
    german.tech_germanization      True -> False    (Fachwort-Aussprache AUS)
    german.engine_mode       customvoice -> voicedesign
    german.best_speaker            None -> 'Aiden'
    voices.speaker_map.male_1   <fehlt> -> 'Aiden'
    german.variation.enabled       None -> True
    advanced.segment_target_chars   130 -> 420/500  (Benchmark-"Winner")

Folgen für die Produktion: ``speed: 1.1`` wird als explizite Nutzerwahl
gewertet und beschleunigt jedes Segment um 10 % (apply_speed) plus
generationsseitigem "schneller sprechen"-Hinweis; ``tech_germanization:
False`` schaltet die gesamte DE-Fachwortschicht ab; ``speaker_map``/
``best_speaker`` ändern die Stimmenidentität.

Ebenfalls beobachtet: ``test_pronunciation.py`` und ``test_german_phase1.py``
rufen ``d.clear_all()`` auf dem echten Wörterbuch auf
(``pronunciation/pronunciation.json``), und ein Benchmark-Lauf überschrieb
``cache/voice_refs/VD-E.wav`` mit einer Platzhalterdatei (96.044 statt
1.021.484 Bytes, SHA abweichend vom geschützten
``B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025``).

WAS DIESES CONFTEST TUT
-----------------------
Es legt vor der Session ein Byte-Exakt aller geschützten Dateien an und
stellt am Ende jede veränderte Datei wieder her. Innerhalb der Session ändert
sich nichts – bestehende Erwartungen (auch solche, die Persistenz prüfen)
bleiben gültig; nur der Dauerzustand auf Platte wird geschützt. Veränderte
Dateien werden als Warnung gemeldet, damit sichtbar bleibt, WELCHER Test
in Produktionsdaten schreibt.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import pytest

_PROJECT = Path(__file__).resolve().parent.parent

# Geschützte Pfade/Globs – Aussprache, Identität, Golden Reference, Config.
_PROTECTED_GLOBS = (
    "config/config.json",
    "config/production.json",
    "pronunciation/pronunciation.json",
    "voices/*.json",
    "cache/voice_refs/VD-E.wav",
    "cache/voice_refs/vd_e.wav",
    "VD-E_GOLDEN_REFERENCE/VD-E.wav",
    "../reference/VD-E_GOLDEN_REFERENCE/VD-E.wav",
)


def _protected_files() -> list[Path]:
    files: list[Path] = []
    for pattern in _PROTECTED_GLOBS:
        files.extend(sorted(_PROJECT.glob(pattern)))
    return files


@pytest.fixture(scope="session", autouse=True)
def _protect_production_data():
    """Stellt geschützte Produktionsdaten nach der Test-Session wieder her.

    Selbstheilung (nachgetragen 2026-09-24): Für die beiden Live-Referenz-
    Pfade (``cache/voice_refs/VD-E.wav`` / ``vd_e.wav``) ist nicht der
    Session-Snapshot die Wahrheit, sondern die geschützte Golden Reference
    (``VD-E_GOLDEN_REFERENCE/VD-E.wav``, SHA B156C02A…). Beobachtete Lücke:
    Nach einem Verlust von ``cache/`` schrieb ein Benchmark eine
    Platzhalter-VD-E.wav; der Snapshot konnte das nicht heilen, weil beim
    Session-Start keine Baseline existierte. Jetzt zwingend: Live-Pfade
    werden am Session-Ende byte-exakt auf die Golden Reference gesetzt,
    wenn sie abweichen.
    """
    snapshot: dict[Path, bytes] = {}
    for path in _protected_files():
        try:
            snapshot[path] = path.read_bytes()
        except OSError:
            continue

    yield

    restored: list[str] = []

    # 1) Snapshot-Wiederherstellung (bestehende Dateien, verändert oder weg)
    for path, original in snapshot.items():
        try:
            current = path.read_bytes()
        except OSError:
            current = None
        if current != original:
            try:
                path.write_bytes(original)
                restored.append(str(path.relative_to(_PROJECT.parent)))
            except OSError:
                restored.append(f"{path} (Wiederherstellung FEHLGESCHLAGEN)")

    # 2) Golden-Referenz erzwingt den Zustand der Live-Voice-Referenz
    golden_path = _PROJECT / "VD-E_GOLDEN_REFERENCE" / "VD-E.wav"
    try:
        golden = golden_path.read_bytes()
    except OSError:
        golden = None
    if golden is not None:
        for rel in ("cache/voice_refs/VD-E.wav", "cache/voice_refs/vd_e.wav"):
            path = _PROJECT / rel
            try:
                if path.exists() and path.read_bytes() != golden:
                    path.write_bytes(golden)
                    restored.append(f"{rel} (auf Golden-Referenz gesetzt)")
            except OSError:
                restored.append(f"{rel} (Golden-Wiederherstellung FEHLGESCHLAGEN)")

    if restored:
        warnings.warn(
            "Testlauf hat Produktionsdaten verändert – wiederhergestellt: "
            + ", ".join(restored)
            + ". Ursache sind Tests/Benchmarks, die app.config.save_config "
              "bzw. clear_all() auf echten Dateien aufrufen.",
            stacklevel=1,
        )
