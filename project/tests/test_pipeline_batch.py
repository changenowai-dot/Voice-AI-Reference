"""Integration: Pipeline + Batch + Cache + Resume + Fehlerisolierung
(Tests A, B, C, D, E, F, I, J, K + Anforderung 35)."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from app import paths
from app.batch.runner import BatchRunner
from app.config import DEFAULT_CONFIG
from app.project.pipeline import Pipeline
from app.tts.test_double import TestDoubleEngine

DE_SENTENCES = [
    "Im Herzen jeder Großstadt liegt eine verborgene Geschichte.",
    "Die Psychologie des Vergessens beginnt mit einem einzigen Moment.",
    "Nietzsche schrieb, dass der Mensch ein Seil sei zwischen Tier und Übermensch.",
    "1915 beschrieb Freud die Verdrängung erstmals systematisch.",
    "Warum wiederholen Menschen Muster, die sie längst durchschaut haben?",
    "CERN, Göbekli Tepe und die Tiefsee haben eines gemeinsam: Geheimnisse.",
    "Die Antwort liegt bei 3,7 Prozent der Proben.",
    "Und manchmal, in stillen Nächten, kehrt das Verdrängte zurück.",
    "Es gibt kein Zurück mehr hinter dieser Schwelle.",
    "Doch die Frage bleibt.",
]
EN_SENTENCES = [
    "Every city keeps a story that nobody has fully told.",
    "The psychology of forgetting begins with a single moment.",
    "In nineteen sixty-nine a quiet experiment changed everything.",
    "Why do people repeat the patterns they claim to understand?",
    "CERN, Göbekli Tepe and the deep sea share one trait: secrets.",
    "The reading was three point seven percent of all samples.",
    "And sometimes, in silent nights, the repressed returns.",
    "There is no way back beyond this threshold.",
    "Still, the question remains.",
]


def _de_text(n_chars: int, salt: str = "") -> str:
    out = []
    total = 0
    i = 0
    if salt:
        out.append(salt)
        total = len(salt) + 1
    while total < n_chars:
        s = DE_SENTENCES[i % len(DE_SENTENCES)]
        out.append(s)
        total += len(s) + 1
        i += 1
        if i % 10 == 0:
            out.append("\n")          # Absätze
    return " ".join(out)


def _cfg(**over):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    cfg["language"] = over.pop("language", "German")
    cfg.update(over)
    cfg["advanced"]["segment_target_chars"] = 260
    cfg["advanced"]["segment_max_chars"] = 400
    return cfg


def _pipeline(**over):
    return Pipeline(_cfg(**over), TestDoubleEngine())


def _write(name: str, text: str) -> Path:
    paths.INPUT_DIR.mkdir(parents=True, exist_ok=True)
    p = paths.INPUT_DIR / name
    p.write_text(text, encoding="utf-8")
    return p


def test_a_10_seconds_text():
    p = _write("test_10s.txt", _de_text(140))
    rep = _pipeline().process_file(p)
    assert rep["ok"], rep
    assert Path(rep["wav"]).exists()
    assert 4 <= rep["duration_s"] <= 25
    assert rep["segments"] >= 1


def test_b_1_minute_text():
    p = _write("test_1min.txt", _de_text(900))
    rep = _pipeline().process_file(p)
    assert rep["ok"]
    assert 30 <= rep["duration_s"] <= 110
    assert rep["segments"] >= 3


def test_c_10_minute_text():
    p = _write("test_10min.txt", _de_text(8400))
    rep = _pipeline().process_file(p)
    assert rep["ok"]
    assert rep["duration_s"] > 300
    assert rep["avg_score"] is not None and rep["avg_score"] > 50


def test_d_longform_with_chapters():
    text = ("# Kapitel eins: Der Anfang\n\n" + _de_text(1200) +
            "\n\n## Kapitel zwei: Die Wende\n\n" + _de_text(1200) +
            "\n\nKapitel drei: Das Ende\n\n" + _de_text(1200))
    p = _write("test_longform.txt", text)
    rep = _pipeline().process_file(p)
    assert rep["ok"] and rep["segments"] >= 10
    m = rep["master"]
    assert m["lufs_out"] is not None and abs(m["lufs_out"] + 14) < 1.5


def test_e_german():
    p = _write("test_de.txt", "Der Philosoph schrieb 1999 seine wichtigsten "
              "Zeilen. Göbekli Tepe liegt in der Türkei. 42 Prozent stimmten "
              "zu. Der Preis betrug 3,50 €.")
    rep = _pipeline(language="German").process_file(p)
    assert rep["ok"] and rep["normalizations"] >= 3, rep


def test_f_english():
    p = _write("test_en.txt", "The philosopher wrote his most important lines "
              "in 1999. Göbekli Tepe sits in Türkiye. 42 percent agreed.")
    rep = _pipeline(language="English").process_file(p)
    assert rep["ok"]


def test_i_multiple_files_batch():
    for i in range(5):
        _write(f"batch_{i:02d}.txt", _de_text(200 + i * 30))
    from app.ui.progress import ProgressReporter
    progress = ProgressReporter()
    engine = TestDoubleEngine()

    def factory():
        return Pipeline(_cfg(), engine)
    runner = BatchRunner(factory, progress=progress)
    files = sorted(paths.INPUT_DIR.glob("batch_*.txt"))
    summary = runner.run(files)
    assert summary["files_total"] == 5
    assert summary["completed"] == 5 and summary["failed"] == 0
    assert Path(summary["report"]).exists()


def test_j_cache_reuse():
    # vollständig eindeutiger Korpus (kein Cache-Overlap mit anderen Tests)
    unique = " ".join(
        f"Der Cache-Prüfsatz {i} enthält gänzlich eigenständige Wörter zum "
        f"Validieren der Wiederverwendung Nummer {i}." for i in range(14))
    p = _write("test_cache.txt", unique)
    rep1 = _pipeline().process_file(p)
    assert rep1["ok"] and rep1["reused"] == 0, rep1
    rep2 = _pipeline().process_file(p)
    assert rep2["ok"]
    assert rep2["reused"] == rep2["segments"], \
        f"Cache: reused={rep2['reused']} von {rep2['segments']}"
    assert rep2["regenerated"] == 0        # nichts neu erzeugt


def test_k_resume_after_partial_loss():
    p = _write("test_resume.txt", _de_text(1200, salt="Resumeprüfung Nummer sieben."))
    rep1 = _pipeline().process_file(p)
    assert rep1["ok"]
    # Simulierter Abbruch: Hälfte der Cachedateien löschen + State zurücksetzen
    from app.cache.manager import CacheManager
    cm = CacheManager(enabled=True)
    state_file = paths.CACHE_PROJECT_DIR / f"{rep1['project_id']}.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    segs = state["segments"]
    keep = len(segs) // 2
    for s in segs[keep:]:
        cm.clear_segment(s["cache_key"])
        s["status"] = "pending"
        s["cache_key"] = None
    # Cache-Keys neu berechnen lassen: State-Keys der ersten Hälfte behalten
    state_file.write_text(json.dumps(state), encoding="utf-8")
    rep2 = _pipeline().process_file(p)
    assert rep2["ok"]
    assert rep2["reused"] + 0 >= keep - 1, rep2   # mindestens die alte Hälfte
    assert rep2["reused"] < rep2["segments"]      # aber nicht alles


def test_error_isolation():
    """Anforderung 35: eine fehlerhafte Datei stoppt die anderen nicht."""
    files = [_write(f"iso_{i}.txt", _de_text(150)) for i in range(3)]

    class FailingPipeline(Pipeline):
        def process_file(self, input_path):
            if "iso_1" in Path(input_path).name:
                raise RuntimeError("simulierter Totalausfall")
            return super().process_file(input_path)

    engine = TestDoubleEngine()
    runner = BatchRunner(lambda: FailingPipeline(_cfg(), engine))
    summary = runner.run(files)
    assert summary["completed"] == 2 and summary["failed"] == 1
    failed = [r for r in summary["results"] if not r["ok"]][0]
    assert "Totalausfall" in failed["error"]


def test_pronunciation_report_and_suggestions():
    p = _write("test_pron.txt", "Xzqarius Broadhurst untersuchte die Wirkung "
               "von ChatGPT auf Studierende in Göteborg.")
    rep = _pipeline().process_file(p)
    assert rep["ok"]
    assert rep["pronunciation_replacements"] >= 1    # ChatGPT (Built-in)
    assert any("Xzqarius" in s for s in rep["pronunciation_suggestions"])


def test_output_formats():
    """N (WAV) + O (MP3)."""
    p = _write("test_fmt.txt", _de_text(300))
    rep = _pipeline().process_file(p)
    wav = Path(rep["wav"])
    mp3 = Path(rep["mp3"])
    assert wav.exists() and wav.stat().st_size > 40000
    # MP3 nur mit ffmpeg; im Test-Setup vorhanden
    from app.audio.ffmpeg import ffmpeg_available
    if ffmpeg_available():
        assert mp3.exists() and mp3.stat().st_size > 10000
        head = mp3.read_bytes()[:3]
        assert head == b"ID3" or head[0] == 0xFF
