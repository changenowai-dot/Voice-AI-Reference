"""v2-Feature-Tests (§16-Checkliste): Voice-Architektur, Native-Logik,
+++++-Splitting, Ausgabemodi, FullScript-Konkatenation, VD-E-Schutz.

Prüfstand: TestDouble(TestDoubleClone)-Engines. VD-E-Kern wird nicht
verändert; production.json/Identity-Lock bleiben unangetastet.
"""
from __future__ import annotations

import json
from pathlib import Path

from app import paths

VD_E_SHA = "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025"
APP_ROOT = Path(__file__).resolve().parent.parent


def _make_reference(root: Path) -> None:
    import hashlib
    import numpy as np
    from app.audio.io import write_wav
    ref_dir = root / "cache" / "voice_refs"
    ref_dir.mkdir(parents=True, exist_ok=True)
    ref = ref_dir / "VD-E.wav"
    if not ref.exists():
        t = np.linspace(0, 2.0, 48000, dtype=np.float32)
        write_wav(ref, (0.4 * np.sin(2 * np.pi * 110 * t)).astype(
            np.float32), 24000, bit_depth=16)
    digest = hashlib.sha256(ref.read_bytes()).hexdigest().upper()
    cfg_dir = root / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    prod = {"voice_id": "vd_e", "reference_path": "cache/voice_refs/VD-E.wav",
            "reference_sha256": digest, "seed": 52001,
            "cache_version": "q3p-v2-integrity",
            "max_token_headroom_s": 5.0, "expressive_sampling": True,
            "sampling_set": "expressive", "variant": "BASE"}
    (cfg_dir / "production.json").write_text(json.dumps(prod, indent=2),
                                             encoding="utf-8")


# ---------------------------------------------------------------------------
# §2–§5: Voice-Architektur & Native-Language-Logik
# ---------------------------------------------------------------------------
def test_registry_language_counts():
    """§5: pro Sprache mindestens 3 männlich + 3 weiblich."""
    from app.voices.registry import VoiceRegistry
    r = VoiceRegistry()
    for lang in ("German", "English"):
        entries = r.entries_for_language(lang)
        male = [e for e in entries if e.gender == "male"]
        female = [e for e in entries if e.gender == "female"]
        assert len(male) >= 3, (lang, male)
        assert len(female) >= 3, (lang, female)


def test_german_vd_e_top_recommended_default_locked():
    from app.voices.registry import VoiceRegistry
    r = VoiceRegistry()
    entries = r.entries_for_language("German")
    assert entries[0].voice_id == "vd_e"                       # §6 oben
    assert r.default_voice_id("German") == "vd_e"
    vd = r.get("vd_e")
    assert vd.production_locked and vd.recommended and vd.default
    assert vd.reference_path == "cache/voice_refs/VD-E.wav"
    raw = json.loads((APP_ROOT / "voices" / "vd_e.json").read_text(
        encoding="utf-8"))
    assert raw["production_locked"] is True
    assert raw["default"] is True and raw["recommended"] is True


def test_no_false_native_claims():
    """§2/§3/§4: niemals „nativ deutsch“ für Presets; niemals
    „nativ englisch weiblich“."""
    from app.gui.voice_view import voice_rows
    from app.voices.registry import VoiceRegistry, VoiceProfileEntry
    r = VoiceRegistry()
    for row in voice_rows("German", r):
        if row["voice_id"] != "vd_e":
            assert "nativ" not in row["label"].lower(), row
        e = next(x for x in r.entries_for_language("German")
                 if x.voice_id == row["voice_id"])
        if row["voice_id"] != "vd_e":
            assert e.native_status == "cross_language"
    for row in voice_rows("English", r):
        e = next(x for x in r.entries_for_language("English")
                 if x.voice_id == row["voice_id"])
        if e.gender == "female":
            assert e.native_status == "cross_language"          # §4
            assert "nativ" not in row["label"].lower(), row
    # native nur bei Ryan/Aiden (English)
    natives = [e.voice_id for e in r.entries_for_language("English")
               if e.native_status == "native"]
    assert set(natives) == {"ryan", "aiden"}
    # Uncle_Fu im Englischen = Cross-Language-Fallback
    uf = next(e for e in r.entries_for_language("English")
              if e.voice_id == "uncle_fu")
    assert uf.native_status == "fallback"


def test_english_default_is_native_ryan():
    from app.voices.registry import VoiceRegistry
    assert VoiceRegistry().default_voice_id("English") == "ryan"


def test_voice_metadata_complete():
    """§5: Metadaten vollständig (Beispiel-Felder)."""
    from app.voices.registry import VoiceRegistry
    r = VoiceRegistry()
    for e in r.entries():
        for f in ("voice_id", "display_name", "gender", "description",
                  "native_language", "native_status", "category"):
            assert getattr(e, f) not in ("", None), (e.voice_id, f)
    ryan = json.loads((APP_ROOT / "voices" / "ryan.json").read_text(
        encoding="utf-8"))
    assert ryan["native_language"] == "English"
    assert ryan["native_status"] == "native"
    assert ryan["category"] == "narrator"


def test_status_and_description_separate():
    """§7: Native-Status ist kein Teil der Charakterbeschreibung."""
    from app.gui.voice_view import voice_rows
    from app.voices.registry import VoiceRegistry
    for row in voice_rows("German", VoiceRegistry()):
        if row["voice_id"] != "vd_e":
            assert row["status"] == "CROSS-LANGUAGE"
            assert "(cross-language)" not in row["label"].lower()
            assert "nativ" not in row["label"].lower()


# ---------------------------------------------------------------------------
# §8/§9: Marker-Splitting (nur manueller Marker, nie zeitbasiert)
# ---------------------------------------------------------------------------
def test_marker_detection_exact():
    from app.text.script_split import count_markers, is_marker_line
    assert is_marker_line("+++++")
    assert is_marker_line("  +++++  ")
    assert is_marker_line("\t+++++")
    assert not is_marker_line("++++")            # 4
    assert not is_marker_line("++++++")          # 6
    assert not is_marker_line("abc+++++")
    assert not is_marker_line("+++++abc")
    assert not is_marker_line("Text +++++ Text")
    assert not is_marker_line("Ein Satz mit +++++ innerhalb.")
    assert not is_marker_line("++ ++++")
    assert count_markers("+++++\n+++++") == 2
    assert count_markers("++++\n++++++") == 0


def test_split_manuscript_sections():
    from app.text.script_split import split_manuscript
    text = ("Abschnitt 1 beginnt hier.\nZweite Zeile.\n\n+++++\n\n"
            "Abschnitt 2 beginnt hier.\n\n+++++\n\nAbschnitt 3.")
    parts = split_manuscript(text)
    assert parts == ["Abschnitt 1 beginnt hier.\nZweite Zeile.",
                     "Abschnitt 2 beginnt hier.", "Abschnitt 3."]
    # führender/she Absender Marker -> keine leeren Sections
    assert split_manuscript("+++++\nA") == ["A"]
    assert split_manuscript("A\n+++++") == ["A"]
    assert split_manuscript("A\n+++++\n+++++\nB") == ["A", "B"]
    # ohne Marker: unverändert
    assert split_manuscript("Nur ein Text.") == ["Nur ein Text."]
    # Marker im Fließtext bleibt Text (kein Split!)
    assert split_manuscript("Summe +++++ Rest im Satz") == \
        ["Summe +++++ Rest im Satz"]


def test_split_plan_disabled_behaves_like_before():
    from app.text.script_split import split_plan
    text = "A\n+++++\nB"
    plan_off = split_plan(text, enabled=False)
    assert plan_off["use_split"] is False
    assert plan_off["sections"] == [text]          # exakt bisheriges
    plan_on = split_plan(text, enabled=True)
    assert plan_on["use_split"] and plan_on["parts"] == 2
    plan_no_marker = split_plan("Kein Marker", enabled=True)
    assert plan_no_marker["use_split"] is False    # kein Marker -> Standard


def test_part_names_sortable():
    from app.text.script_split import part_name
    names = [part_name("x", i) for i in (1, 2, 10, 99, 100)]
    assert names == ["x_Part_001", "x_Part_002", "x_Part_010",
                     "x_Part_099", "x_Part_100"]
    assert names == sorted(names)


def test_no_time_based_splitting_anywhere():
    """§9: kein zeit-/längenbasierter Auto-Split im Codepfad."""
    src = (APP_ROOT / "app" / "text" / "script_split.py").read_text(
        encoding="utf-8")
    low = src.lower()
    for banned in ("30", "60", "seconds", "audio_len", "max_dur"):
        assert banned not in low, banned


# ---------------------------------------------------------------------------
# §10–§12: Ausgabemodi + FullScript aus Part-Material (E2E, Prüfstand)
# ---------------------------------------------------------------------------
def _run_job(spec: dict, timeout=900):
    import os
    import subprocess
    import sys
    job_file = paths.STATE_DIR / "job_v2.json"
    job_file.parent.mkdir(parents=True, exist_ok=True)
    job_file.write_text(json.dumps(spec, ensure_ascii=False),
                        encoding="utf-8")
    env = dict(os.environ)
    env["VOICEOVER_ROOT"] = str(paths.ROOT)
    proc = subprocess.Popen(
        [sys.executable, str(APP_ROOT / "app" / "main.py"),
         "--job", str(job_file)],
        env=env, cwd=str(APP_ROOT), stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8",
        errors="replace")
    out, _err = proc.communicate(timeout=timeout)
    events = []
    for line in out.splitlines():
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return proc.returncode, events


MANUSCRIPT = ("Abschnitt eins beginnt mit einem Satz. Noch ein Satz "
              "mit 1908 Zahlen.\n+++++\nAbschnitt zwei stellt eine "
              "Frage? Und antwortet.\n+++++\nAbschnitt drei endet.")


def test_mode_b_parts_only():
    _make_reference(paths.ROOT)
    rc, events = _run_job({
        "text": MANUSCRIPT, "language": "German", "voice_id": "vd_e",
        "engine": "test_double", "output_name": "mb",
        "splitting_enabled": True, "output_mode": "parts"})
    assert rc == 0, [e for e in events if e["event"] == "error"]
    done = next(e for e in events if e["event"] == "done")
    parts = done["summary"]["parts"]
    assert len(parts) == 3
    for i, p in enumerate(parts, 1):
        assert f"mb_Part_{i:03d}" in p["wav"]
        assert Path(p["wav"]).exists() and Path(p["mp3"]).exists()
    # MODE B: KEINE FullScript-Datei
    assert done["summary"]["fullscript_wav"] is None
    assert not list(Path(done["summary"]["wav"]).parent.glob(
        "mb_FullScript*"))
    # Part-Stages gemeldet (§17)
    part_stages = [e for e in events if e.get("stage") == "part"]
    assert [p["part"] for p in part_stages] == [1, 2, 3]


def test_mode_c_parts_plus_fullscript_same_material():
    _make_reference(paths.ROOT)
    rc, events = _run_job({
        "text": MANUSCRIPT, "language": "German", "voice_id": "vd_e",
        "engine": "test_double", "output_name": "mc",
        "splitting_enabled": True, "output_mode": "parts_plus_full"})
    assert rc == 0, [e for e in events if e["event"] == "error"]
    done = next(e for e in events if e["event"] == "done")
    s = done["summary"]
    full = Path(s["fullscript_wav"])
    assert full.exists() and full.name == "mc_FullScript.wav"
    assert Path(s["fullscript_mp3"]).exists()
    # §11: FullScript == exakte Konkatenation der Part-Dateien
    import numpy as np
    from app.audio.io import read_wav
    from app.audio.concat import concat_wavs
    part_wavs = [Path(p["wav"]) for p in s["parts"]]
    control = paths.CACHE_DIR / "assembly" / "control_full.wav"
    res = concat_wavs(part_wavs, control)
    assert res["ok"]
    a, sr_a = read_wav(full)
    b, sr_b = read_wav(control)
    assert sr_a == sr_b and a.shape == b.shape
    assert np.array_equal(a, b), "FullScript != Part-Konkatenation"
    # keine erneute TTS: Segment-Summe der Parts == Gesamt-Segmente
    assert s["segments"] == sum(p["segments"] for p in s["parts"])


def test_mode_a_splitting_disabled_exact_previous_behavior():
    _make_reference(paths.ROOT)
    rc, events = _run_job({
        "text": MANUSCRIPT, "language": "German", "voice_id": "vd_e",
        "engine": "test_double", "output_name": "ma"})
    assert rc == 0
    done = next(e for e in events if e["event"] == "done")
    s = done["summary"]
    assert s["output_mode"] == "full" and s["parts"] is None
    assert "_Part_" not in s["wav"] and "FullScript" not in s["wav"]
    # Standard-GUI-Benennung bleibt gui_/name (keine Part-Dateien)
    assert not list(Path(s["wav"]).parent.glob("ma_Part_*"))


def test_splitting_on_full_mode_upgrades_to_c():
    _make_reference(paths.ROOT)
    rc, events = _run_job({
        "text": MANUSCRIPT, "language": "German", "voice_id": "vd_e",
        "engine": "test_double", "output_name": "upg",
        "splitting_enabled": True, "output_mode": "full"})
    assert rc == 0
    done = next(e for e in events if e["event"] == "done")
    assert done["summary"]["output_mode"] == "parts_plus_full"
    assert any(e.get("stage") == "split" and "A -> C" in str(
        e.get("detail", "")) for e in events)


def test_invalid_output_mode_rejected():
    import os
    import subprocess
    import sys
    job_file = paths.STATE_DIR / "job_bad.json"
    job_file.parent.mkdir(parents=True, exist_ok=True)
    job_file.write_text(json.dumps({
        "text": "x", "output_mode": "kaputt"}), encoding="utf-8")
    env = dict(os.environ)
    env["VOICEOVER_ROOT"] = str(paths.ROOT)
    proc = subprocess.run(
        [sys.executable, str(APP_ROOT / "app" / "main.py"),
         "--job", str(job_file)],
        env=env, cwd=str(APP_ROOT), capture_output=True, text=True,
        timeout=120)
    assert proc.returncode != 0
    assert "Ausgabemodus" in (proc.stderr or proc.stdout)


# ---------------------------------------------------------------------------
# §16: VD-E-Schutz & Basis-Regressionen
# ---------------------------------------------------------------------------
def test_vd_e_core_untouched():
    prod = json.loads((APP_ROOT / "config" / "production.json").read_text(
        encoding="utf-8"))
    assert prod["reference_sha256"] == VD_E_SHA
    assert prod["seed"] == 52001 and prod["locked"] is True
    from app.tts.sampler import PARAM_SET_VERSION
    assert PARAM_SET_VERSION == "q3p-v2-integrity"   # Cache unverändert
    from app.security.identity_lock import check_identity
    prod_check = dict(prod, reference_path="cache/voice_refs/NICHT_DA.wav")
    status = check_identity(prod_check)
    assert status.level == "missing_ref" and not status.ok


def test_vd_e_job_still_works_with_splitting_disabled():
    _make_reference(paths.ROOT)
    rc, events = _run_job({
        "text": "Dies ist ein natürlicher deutscher Testsatz für die "
                "VoiceOver-Anwendung. Zweiter Satz. Dritter Satz.",
        "language": "German", "voice_id": "vd_e", "engine": "test_double",
        "output_name": "vde_reg"})
    assert rc == 0
    done = next(e for e in events if e["event"] == "done")
    assert done["summary"]["voice"] == "VD-E"
    ident = [e for e in events if e["event"] == "identity_check"]
    assert ident and ident[-1]["ok"] is True           # §17-Checkliste


def test_pronunciation_identical_for_parts_and_full():
    """§14: Aussprachelogik identisch – gleicher Text ergibt gleiche
    TTS-Eingabe in Part- und Gesamtfassung."""
    from app.pronunciation import PronunciationEngine
    from app.text.script_split import split_manuscript
    from app.text.normalize import NormalizationReport, normalize_text
    eng = PronunciationEngine()

    def tts(t):
        return eng.process(normalize_text(t, "German", NormalizationReport()
                                          ), "German").text
    whole = tts(MANUSCRIPT.replace("+++++", "").replace("\n\n", "\n"))
    parts = [tts(p) for p in split_manuscript(MANUSCRIPT)]
    joined = "\n".join(parts)
    # Kerninhalt (Namen/Zahlen/Respellings) identisch verteilt:
    for probe in ("neunzehnhundertacht", "Frage"):
        assert probe in whole
        assert any(probe in p for p in parts)
    assert len(parts) == 3


def test_customvoice_voices_available_in_gui_lists():
    """§16: männliche und weibliche Stimmen sichtbar (beide Sprachen)."""
    from app.gui.voice_view import voice_rows
    from app.voices.registry import VoiceRegistry
    r = VoiceRegistry()
    for lang in ("German", "English"):
        rows = voice_rows(lang, r)
        assert any(x["gender"] == "male" for x in rows)
        assert any(x["gender"] == "female" for x in rows)
        for x in rows:
            assert "(" in x["label"] and ")" in x["label"]   # Beschreibung
