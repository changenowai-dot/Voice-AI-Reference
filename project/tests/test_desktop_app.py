"""Desktop-App-Tests (§32 Phasen 2–10): PDF, Identity-Lock, Registry,
Final-Gate, Job-Runner (JSONL), GUI-Helfer, Regressionen (§34),
Long-Form-Kette PDF→WAV/MP3 (§35).

Der Produktionskern wird nicht verändert; VD-E-Hash wird in jeder
relevanten Testumgebung synthetisch gesichert (der echte Produktions-
Hash steht in config/production.json der Auslieferung).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app import paths

APP_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# PDF-Fixture: minimales gültiges PDF bauen (ohne Fremdpakete)
# ---------------------------------------------------------------------------
def build_pdf(path: Path, pages: list[list[str]]) -> None:
    objs: list[bytes] = []

    def esc(s: str) -> str:
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    n_pages = len(pages)
    # 1=Catalog 2=Pages 3=Font 4..=Pages+Contents
    page_ids = list(range(4, 4 + n_pages * 2, 2))
    objs.append(b"")  # Platzhalter für 1-basierte Indizes
    objs.append(f"<< /Type /Catalog /Pages 2 0 R >>".encode())
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>"
                .encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, lines in enumerate(pages):
        pid = page_ids[i]
        cid = pid + 1
        stream = ["BT", "/F1 10 Tf", "72 720 Td"]
        for ln in lines:
            stream.append(f"({esc(ln)}) Tj")
            stream.append("0 -14 Td")
        stream.append("ET")
        s = "\n".join(stream).encode("latin-1", "replace")
        objs.append(f"<< /Type /Page /Parent 2 0 R "
                    f"/MediaBox [0 0 612 792] /Contents {cid} 0 R "
                    f"/Resources << /Font << /F1 3 0 R >> >> >>".encode())
        objs.append(f"<< /Length {len(s)} >>\nstream\n".encode() + s +
                    b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objs):
        if i == 0:
            continue
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    n = len(objs)
    out += f"xref\n0 {n}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_pos}\n"
            f"%%EOF").encode()
    path.write_bytes(bytes(out))


def test_pdf_import_basic_and_cleanup():
    from app.text.pdf_import import extract_pdf_text
    p = paths.CACHE_DIR / "t_pdf1.pdf"
    build_pdf(p, [
        ["Dies ist ein natürlicher deut-",
         "scher Testsatz für die Voice-",
         "Over-Anwendung mit 1999 Zahlen.",
         "12"],
        ["Zweite Seite: Nietzsche, CERN und",
         "die Quantentheorie  bleiben.",
         "3"],
    ])
    res = extract_pdf_text(p)
    assert res.pages == 2 and res.words > 15
    # Trennstriche korrekt zusammengefügt (§7)
    assert "deutscher" in res.text and "natürlicher" in res.text
    # Seitennummern-Zeilen entfernt, Zahlen im Satz bleiben
    assert "\n12\n" not in res.text and "1999" in res.text
    # Inhalte bleiben (Namen, Zahlen)
    assert "Nietzsche" in res.text and "CERN" in res.text


def test_pdf_import_invalid_and_empty():
    from app.text.pdf_import import PdfImportError, extract_pdf_text
    bad = paths.CACHE_DIR / "t_bad.pdf"
    bad.write_bytes(b"kein pdf, nur text")
    try:
        extract_pdf_text(bad)
        raised = False
    except PdfImportError as e:
        raised = True
        assert "Ungültige" in str(e) or "unlesbare" in str(e)
    assert raised
    empty = paths.CACHE_DIR / "t_empty.pdf"
    build_pdf(empty, [[""]])
    try:
        extract_pdf_text(empty)
        raised = False
    except PdfImportError as e:
        raised = True
        assert "keine extrahierbaren Wörter" in str(e)
    assert raised


def test_pdf_import_big_multipage():
    """§7: große, mehrseitige PDFs stabil (40 Seiten)."""
    from app.text.pdf_import import extract_pdf_text
    p = paths.CACHE_DIR / "t_big.pdf"
    pages = [[f"Seite {i} Absatz {j}: Der Text fliesst weiter und weiter."
              for j in range(8)] for i in range(40)]
    build_pdf(p, pages)
    res = extract_pdf_text(p)
    assert res.pages == 40 and res.chars > 3000


# ---------------------------------------------------------------------------
# Identity-Lock (§24/§33)
# ---------------------------------------------------------------------------
def _make_reference(root: Path) -> str:
    """Erzeugt deterministische VD-E-Test-Referenz + production.json."""
    import hashlib
    import numpy as np
    ref_dir = root / "cache" / "voice_refs"
    ref_dir.mkdir(parents=True, exist_ok=True)
    ref = ref_dir / "VD-E.wav"
    t = np.linspace(0, 2.0, 48000, dtype=np.float32)
    wav = (0.4 * np.sin(2 * np.pi * 110 * t)).astype(np.float32)
    from app.audio.io import write_wav
    write_wav(ref, wav, 24000, bit_depth=16)
    digest = hashlib.sha256(ref.read_bytes()).hexdigest().upper()
    cfg_dir = root / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    prod = {"voice_id": "vd_e", "reference_path": "cache/voice_refs/VD-E.wav",
            "reference_sha256": digest, "seed": 52001,
            "cache_version": "q3p-v2-integrity",
            "max_token_headroom_s": 5.0, "expressive_sampling": True,
            "sampling_set": "expressive", "variant": "BASE"}
    (cfg_dir / "production.json").write_text(
        json.dumps(prod, indent=2), encoding="utf-8")
    return digest


def test_identity_lock_ok_mismatch_missing():
    from app.security.identity_lock import (check_identity, load_production,
                                            assert_vd_e_usable)
    _make_reference(paths.ROOT)
    prod = load_production()
    status = check_identity(prod)
    assert status.ok and status.level == "ok"
    assert_vd_e_usable(prod)                     # wirft nicht

    # Manipulation -> Sperre, keine Reparatur
    ref = paths.ROOT / "cache" / "voice_refs" / "VD-E.wav"
    original = ref.read_bytes()
    ref.write_bytes(original[:-8] + b"XXXXXXXX")
    bad = check_identity(prod)
    assert not bad.ok and bad.level == "hash_mismatch"
    assert "verändert" in bad.message
    try:
        assert_vd_e_usable(prod)
        raised = False
    except RuntimeError:
        raised = True
    assert raised
    assert ref.read_bytes() != original          # keine „Reparatur“ zurück

    # fehlend -> gesperrt, wird NICHT neu erzeugt
    ref.unlink()
    miss = check_identity(prod)
    assert not miss.ok and miss.level == "missing_ref"
    assert not ref.exists()

    _make_reference(paths.ROOT)                  # für Folgetests wiederher


def test_production_settings_applied():
    """§3: expressive Sampling, BASE-Variante, Cache-Version dokumentiert."""
    from app.jobs.runner import apply_production
    cfg = {"advanced": {"temperature": 0.7}, "german": {}}
    prod = {"expressive_sampling": True, "sampling_set": "expressive",
            "cache_version": "q3p-v2-integrity", "variant": "BASE"}
    out = apply_production(cfg, prod)
    adv = out["advanced"]
    assert adv["temperature"] == 0.85            # expressive-Set
    assert adv["top_k"] == 60 and adv["top_p"] == 0.92
    assert adv["do_sample"] is True
    assert out["german"]["tech_germanization"] is False       # BASE
    assert out["german"]["variation"]["enabled"] is False     # BASE
    assert out["german"]["cache_version"] == "q3p-v2-integrity"


def test_sampler_cache_version_and_headroom():
    from app.tts.sampler import PARAM_SET_VERSION, max_new_tokens_for
    assert PARAM_SET_VERSION == "q3p-v2-integrity"            # §5
    assert max_new_tokens_for(20.0) == int((20.0 + 5.0) * 12.5 + 64)
    assert max_new_tokens_for(20.0, headroom_s=12.0) == int(32.0 * 12.5 + 64)


# ---------------------------------------------------------------------------
# Voice-Registry (§10–§13)
# ---------------------------------------------------------------------------
def test_voice_registry_profiles_v2():
    """v2: 8 Stimmen (VD-E + 7 CustomVoice), VD-E gesperrt/Standard."""
    from app.voices.registry import VoiceRegistry
    reg = VoiceRegistry()
    entries = reg.entries()
    assert len(entries) == 8                     # v2: + uncle_fu, dylan
    male = [e for e in entries if e.gender == "male"]
    female = [e for e in entries if e.gender == "female"]
    assert len(male) == 5 and len(female) == 3
    vd = reg.get("vd_e")
    assert vd.production_locked and vd.default and vd.backend_mode == "clone"
    assert vd.reference_path == "cache/voice_refs/VD-E.wav"
    ids = {e.voice_id for e in entries}
    assert ids == {"vd_e", "uncle_fu", "dylan", "ryan", "aiden",
                   "vivian", "serena", "sohee"}
    assert reg.default_voice_id() == "vd_e"      # Deutsch-Standard bleibt
    assert reg.default_voice_id("German") == "vd_e"


def test_voice_availability_no_fallback():
    """§13: fehlender Sprecher -> deaktiviert + Meldung, kein Ersatz."""
    from app.voices.registry import VoiceRegistry

    class FakeModel:
        def get_supported_speakers(self):
            return ["Ryan", "Serena"]            # 4 fehlen

    class FakeEngine:
        model = FakeModel()

    reg = VoiceRegistry()
    result = reg.check_customvoice_availability(FakeEngine())
    assert result["ryan"][0] is True
    assert result["serena"][0] is True
    assert result["aiden"][0] is False
    assert "Stimme nicht verfügbar" in result["vivian"][1]
    assert "Sohee" in result["sohee"][1] or "sohee" in result["sohee"][1]
    assert result["vd_e"][0] is True             # Clone unangetastet


# ---------------------------------------------------------------------------
# Final-QC-Gate (§4)
# ---------------------------------------------------------------------------
def test_final_gate_blocks_critical():
    import numpy as np
    from app.quality import SegmentQC
    from app.quality.final_gate import final_qc_gate
    qc = SegmentQC("German")
    text = "Ein ausreichend langer Testsatz mit mehreren Wörtern darin."
    # NaN-Audio
    bad = np.full(int(2.5 * 24000), np.nan, dtype=np.float32)
    g1 = final_qc_gate(bad, 24000, text, qc, context="test")
    assert not g1.passed and g1.critical
    # Stille
    silent = np.zeros(int(2.5 * 24000), dtype=np.float32)
    g2 = final_qc_gate(silent, 24000, text, qc, context="test")
    assert not g2.passed
    # gesund (Prüfstand)
    from app.tts.test_double import TestDoubleEngine
    from app.tts.engine_base import SynthesisRequest
    res = TestDoubleEngine().synthesize(SynthesisRequest(
        text=text * 4, language="German", speaker="Ryan"))
    g3 = final_qc_gate(res.waveform, res.sample_rate, text * 4, qc,
                       context="test")
    assert g3.passed and g3.score >= 60


def test_pipeline_final_gate_rejects_defect():
    """§4: defektes Segment wird NICHT in Cache/Endaudio übernommen."""
    import json as _json
    from app.project.pipeline import Pipeline
    from app.tts.test_double import TestDoubleEngine
    from app.config import DEFAULT_CONFIG
    paths.INPUT_DIR.mkdir(parents=True, exist_ok=True)
    p = paths.INPUT_DIR / "gate_test.txt"
    p.write_text("Erster Satz bleibt gesund erhalten. " * 3, encoding="utf-8")

    class BrokenAlways(TestDoubleEngine):
        """ALLE Versuche defekt (NaN) – Final-Gate muss blockieren."""
        def synthesize(self, request):
            import numpy as np
            from app.tts.engine_base import SynthesisResult
            return SynthesisResult(
                waveform=np.full(int(2.0 * 24000), np.nan, dtype=np.float32),
                sample_rate=24000, duration_s=2.0, elapsed_s=0.01,
                engine="broken", params_used={})

    cfg = _json.loads(_json.dumps(DEFAULT_CONFIG))
    cfg["advanced"]["segment_target_chars"] = 400
    rep = Pipeline(cfg, BrokenAlways()).process_file(p)
    # §22: Job scheitert sauber; KEINE beschädigte Datei als „fertig“
    assert not rep.get("ok")
    assert "Keine Segmente erfolgreich" in rep.get("error", "")
    from app import paths as _p
    assert not (_p.OUTPUT_DIR / "gate_test.wav").exists()
    # KEIN Cache-Eintrag mit NaN
    for mf in paths.CACHE_META_DIR.glob("*.json"):
        meta = _json.loads(mf.read_text(encoding="utf-8"))
        m = meta.get("metrics", {})
        assert not m.get("has_nan", False), mf


def test_pipeline_production_seed_locked():
    """§3: VD-E-Produktion nutzt festen Seed 52001 (kein Zufalls-Seed)."""
    from app.project.pipeline import _voice_cfg
    # nur Konfigurationsmechanik: Seed wird aus voice.production_seed gelesen
    cfg = {"voice": {"id": "vd_e", "production_seed": 52001}}
    v = _voice_cfg(cfg)
    assert v["production_seed"] == 52001


# ---------------------------------------------------------------------------
# Job-Runner Ende-zu-Ende (JSONL-Protokoll, §16/§17)
# ---------------------------------------------------------------------------
def _run_job_subprocess(spec: dict, timeout=600) -> tuple[int, list[dict]]:
    job_file = paths.STATE_DIR / "job_test.json"
    job_file.parent.mkdir(parents=True, exist_ok=True)
    job_file.write_text(json.dumps(spec, ensure_ascii=False),
                        encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(APP_ROOT / "app" / "main.py"),
         "--job", str(job_file)],
        env=_test_env(), cwd=str(APP_ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace")
    out, err = proc.communicate(timeout=timeout)
    events = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return proc.returncode, events


def _test_env() -> dict:
    import os
    env = dict(os.environ)
    env["VOICEOVER_ROOT"] = str(paths.ROOT)
    return env


def test_job_runner_vd_e_success_events():
    _make_reference(paths.ROOT)
    spec = {"text": "Dies ist ein natürlicher deutscher Testsatz für die "
                    "VoiceOver-Anwendung. Zweiter Satz mit 1999 Zahlen. "
                    "Dritter Satz schließt ab.",
            "language": "German", "voice_id": "vd_e", "speed": 1.0,
            "engine": "test_double"}
    rc, events = _run_job_subprocess(spec)
    kinds = [e["event"] for e in events]
    assert rc == 0, events
    assert "done" in kinds and "progress" in kinds
    done = next(e for e in events if e["event"] == "done")
    s = done["summary"]
    assert s["status"] == "Erfolgreich" and s["voice"] == "VD-E"
    assert s["failed"] == 0 and Path(done["wav"]).exists()
    # §33: Identity-Check nach Lauf gemeldet
    ident = [e for e in events if e["event"] == "identity_check"]
    assert ident and ident[-1]["ok"] is True


def test_job_runner_vd_e_blocked_when_tampered():
    _make_reference(paths.ROOT)
    ref = paths.ROOT / "cache" / "voice_refs" / "VD-E.wav"
    data = ref.read_bytes()
    ref.write_bytes(data[:-4] + b"XXXX")
    try:
        spec = {"text": "Test", "language": "German", "voice_id": "vd_e",
                "engine": "test_double"}
        rc, events = _run_job_subprocess(spec)
        assert rc != 0
        err = next(e for e in events if e["event"] == "error")
        assert "VD-E" in err["message"] or "gesperrt" in err["message"]
        # Referenz nicht überschrieben/„repariert“
        assert ref.read_bytes()[-4:] == b"XXXX"
    finally:
        _make_reference(paths.ROOT)


def test_job_runner_unknown_voice_and_empty_text():
    spec = {"text": "Hallo", "voice_id": "unbekannt",
            "engine": "test_double"}
    rc, events = _run_job_subprocess(spec)
    assert rc != 0
    assert any(e["event"] == "error" and "Unbekannte Stimme" in e["message"]
               for e in events)
    spec2 = {"text": "   ", "voice_id": "vd_e", "engine": "test_double"}
    rc2, events2 = _run_job_subprocess(spec2)
    assert rc2 != 0
    assert any("leer" in e.get("message", "") for e in events2
               if e["event"] == "error")


def test_job_runner_missing_speaker_no_fallback():
    """§13: fehlender CustomVoice-Sprecher -> Fehler, kein Ersatzsprecher."""
    _make_reference(paths.ROOT)

    class _NoSpeaker:
        pass
    # direkter Funktionstest (Subprocess hätte echtes Modell nötig)
    from app.jobs.runner import JobSpec, ensure_speaker_available
    from app.voices.registry import VoiceRegistry
    entry = VoiceRegistry().get("vivian")
    fake = _NoSpeaker()
    fake.load = lambda: None

    class _M:
        def get_supported_speakers(self):
            return ["Ryan"]
    fake.model = _M()
    try:
        ensure_speaker_available(fake, entry)
        raised = False
    except RuntimeError as e:
        raised = True
        assert "Stimme nicht verfügbar" in str(e)
    assert raised


def test_job_runner_single_process_lock():
    """§16: zweite Backend-Instanz wird abgewiesen."""
    import subprocess
    import sys as _sys
    import time as _time
    from app.jobs.runner import _acquire_lock, _release_lock, LOCK_FILE
    sleeper = subprocess.Popen(
        [_sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        _time.sleep(0.4)                       # PID sicher lebend
        _acquire_lock()
        assert LOCK_FILE.exists()
        _acquire_lock()                        # eigene PID: idempotent
        # fremde, lebende PID -> Abweisung
        LOCK_FILE.write_text(str(sleeper.pid))
        try:
            _acquire_lock()
            raised = False
        except RuntimeError as e:
            raised = True
            assert "bereits" in str(e)
        assert raised
    finally:
        _release_lock()
        assert not LOCK_FILE.exists()
        sleeper.terminate()
        try:
            sleeper.wait(timeout=5)
        except subprocess.TimeoutExpired:
            sleeper.kill()


# ---------------------------------------------------------------------------
# GUI-Helfer + Backend-Parsing (headless, ohne Tk-Instanz)
# ---------------------------------------------------------------------------
def test_gui_helpers_and_event_parsing():
    from app.gui.helpers import (format_duration, format_eta, stage_label,
                                 text_stats)
    st = text_stats("Dies ist ein Test mit genau zehn Wörtern hier jetzt.",
                    "German")
    assert st["words"] == 10 and st["est_segments"] >= 1
    assert st["est_seconds"] > 0
    assert format_duration(3725) == "1:02:05"
    assert format_eta(100, 50) == format_duration(100)
    assert format_eta(10, 0) == ""                       # zu früh
    assert stage_label("mastering") == "Mastering (YouTube-Lautheit)"
    assert stage_label("unbekannt_x") == "unbekannt_x"
    from app.gui.backend import parse_progress_event
    p = parse_progress_event({"event": "progress", "stage": "tts",
                              "segment": 14, "segments_total": 128,
                              "percent": 72})
    assert p["segment"] == 14 and p["segments_total"] == 128
    assert p["percent"] == 72
    s = parse_progress_event({"event": "stage", "stage": "model_load"})
    assert s["stage"] == "model_load"


def test_gui_module_importable_headless():
    """GUI-Code importierbar ohne Fenster (Tk erst bei run())."""
    import app.gui.app as gui_app
    assert hasattr(gui_app, "run")
    assert hasattr(gui_app, "VoiceOverApp")


def test_desktop_entry_cli_routing():
    """desktop.py ohne Argumente = GUI; mit --job = CLI (§37/§38)."""
    src = (APP_ROOT / "desktop.py").read_text(encoding="utf-8")
    assert "from app.gui.app import run" in src
    assert "--job" in src
    # CLI-Routing im Subprocess: --info muss über app.main laufen
    proc = subprocess.run(
        [sys.executable, str(APP_ROOT / "desktop.py"), "--info"],
        env=_test_env(), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0
    assert "VoiceOverApp" in proc.stdout


# ---------------------------------------------------------------------------
# §34 Regressionstest-Matrix (Prüfstand-Mechanik; Audio auf Zielsystem)
# ---------------------------------------------------------------------------
def test_regression_matrix_voices_languages():
    """3-Satz-Test: DE/EN × alle 6 Stimmen (VD-E über Clone-Pfad)."""
    import json as _json
    from app.config import DEFAULT_CONFIG
    from app.project.pipeline import Pipeline
    from app.tts.test_double import TestDoubleCloneEngine, TestDoubleEngine
    from app.voices.registry import VoiceRegistry
    _make_reference(paths.ROOT)
    de = ("Dies ist ein natürlicher deutscher Testsatz für die VoiceOver-"
          "Anwendung. Im Jahr 1989 geschah Unerwartetes. Doch die Frage "
          "bleibt offen?")
    en = ("This is a natural English test sentence for the VoiceOver "
          "application. In 1989 something unexpected happened. Yet the "
          "question remains open?")
    reg = VoiceRegistry()
    for entry in reg.entries():
        for lang, text in (("German", de), ("English", en)):
            cfg = _json.loads(_json.dumps(DEFAULT_CONFIG))
            cfg["language"] = lang
            cfg["voice"] = {"id": entry.voice_id,
                            "speaker": entry.speaker_name,
                            "production_seed":
                                52001 if entry.voice_id == "vd_e" else None}
            cfg["advanced"]["segment_target_chars"] = 400
            engine = (TestDoubleCloneEngine(allow_design=False)
                      if entry.backend_mode == "clone"
                      else TestDoubleEngine())
            p = paths.INPUT_DIR / f"reg_{entry.voice_id}_{lang}.txt"
            p.write_text(text, encoding="utf-8")
            rep = Pipeline(cfg, engine).process_file(p)
            assert rep["ok"], (entry.voice_id, lang, rep.get("error"))
            assert Path(rep["wav"]).exists()


# ---------------------------------------------------------------------------
# §35 Long-Form-Kette: PDF → Text → TTS → QC → Assembly → Master → WAV/MP3
# ---------------------------------------------------------------------------
def test_longform_pdf_to_mp3_chain():
    """Vollkette mit ~30 Minuten Text (Prüfstand), ohne manuelles Eingreifen."""
    _make_reference(paths.ROOT)
    # 1) PDF mit ~30 min Sprache bauen (~25 000 Zeichen)
    para = ("Im Jahr 1989 fielen Mauern, während 1914 die alte Ordnung "
            "zerbrach. Nietzsche, CERN und die Quantentheorie zeigen: "
            "U.a. bleiben 3,7 % aller Muster unverstanden. Warum nur? "
            "Doch dann kam die Erkenntnis, die alles veränderte. ")
    pages = [[para] * 6 for _ in range(26)]
    pdf = paths.INPUT_DIR / "longform.pdf"
    build_pdf(pdf, pages)
    from app.text.pdf_import import extract_pdf_text
    res = extract_pdf_text(pdf)
    assert res.words > 3000

    # 2) Kompletter Job über den Backend-Prozess (§35: „nicht nur GUI-Test“)
    spec = {"text": res.text, "language": "German", "voice_id": "vd_e",
            "speed": 1.0, "engine": "test_double",
            "output_name": "longform_chain"}
    rc, events = _run_job_subprocess(spec, timeout=1200)
    assert rc == 0, [e for e in events if e["event"] == "error"]
    done = next(e for e in events if e["event"] == "done")
    wav, mp3 = Path(done["wav"]), Path(done["mp3"])
    assert wav.exists() and mp3.exists() and mp3.stat().st_size > 10000
    summary = done["summary"]
    assert summary["segments"] > 40                     # Long-Form-Segmentierung
    assert summary["audio_dur_s"] > 1500                # > 25 min Audio
    assert summary["failed"] == 0
    # Fortschrittsereignisse vorhanden (§17)
    prog = [e for e in events if e["event"] == "progress"
            and e.get("segment")]
    assert prog and prog[-1].get("segments_total") == summary["segments"]
    # Testumgebung entlasten: große Artefakte wieder freigeben
    for f in list(wav.parent.glob("longform_chain*")) + \
            list(paths.CACHE_AUDIO_DIR.glob("*.wav")):
        try:
            f.unlink()
        except OSError:
            pass
