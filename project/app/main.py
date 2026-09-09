"""VoiceOverApp â€“ Einstiegspunkt.

Standard: lokale Web-OberflÃ¤che (START.bat). ZusÃ¤tzlich:
  python app/main.py --headless            Input-Ordner ohne UI verarbeiten
  python app/main.py --benchmark system    System-Benchmark (Anforderung 50)
  python app/main.py --benchmark voices    Stimmen-Benchmark (Anforderung 51)
  python app/main.py --download-models     Modelle vorab laden (offline-fÃ¤hig)
  python app/main.py --info                Hardware/Umgebung anzeigen
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# HF-Cache & Offline-Verhalten zentral setzen, BEVOR torch/hf importieren
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import paths  # noqa: E402  (setzt HF_HOME beim Import)

os.environ.setdefault("HF_HOME", str(paths.MODELS_DIR / "hf"))
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

from app import __version__  # noqa: E402
from app import config as cfgmod  # noqa: E402
from app.logging_setup import get_logger, setup_logging  # noqa: E402


def _make_engine(engine_name: str, cfg: dict):
    """Engine-Auswahl nach production config und voice_id (§12/§13).
    
    Verwendet VoiceRegistry um die korrekte Engine basierend auf backend_mode zu erstellen:
    - clone (VD-E) → VoiceCloneEngine mit Base model
    - customvoice → QwenTTSEngine mit CustomVoice model
    """
    log = get_logger("main.engine")
    log.debug("[DIAG-A] _make_engine() entered")
    
    from app.hardware.detector import (detect_hardware, recommend_model_size,
                                       recommend_torch_dtype)
    from app.security.identity_lock import load_production
    from app.voices.registry import VoiceRegistry
    
    log.debug("[DIAG-A.1] Calling detect_hardware()")
    hw = detect_hardware()
    log.debug("[DIAG-A.2] detect_hardware() returned: mode=%s", hw.mode)
    
    adv = cfg.get("advanced", {})
    
    if engine_name == "test_double":
        from app.tts.test_double import TestDoubleEngine
        return TestDoubleEngine(), hw
    
    # Resolve models directory from VOICEOVER_RUNTIME_ROOT if set
    runtime_root = os.environ.get("VOICEOVER_RUNTIME_ROOT")
    if runtime_root:
        models_dir = Path(runtime_root) / "models"
        log.debug("[DIAG-E] Model root resolved from VOICEOVER_RUNTIME_ROOT: %s", models_dir)
    else:
        models_dir = None  # Let engine use default paths.MODELS_DIR
        log.debug("[DIAG-E] Model root: using default paths.MODELS_DIR")
    
    # Load production config to get voice_id
    log.debug("[DIAG-A.3] Calling load_production()")
    production = load_production()
    log.debug("[DIAG-A.4] load_production() returned: voice_id=%s", production.get("voice_id"))
    
    voice_id = production.get("voice_id", "vd_e")
    
    # Look up voice profile
    log.debug("[DIAG-C] Creating VoiceRegistry")
    registry = VoiceRegistry()
    entry = registry.get(voice_id)
    log.debug("[DIAG-C] VoiceRegistry resolved: voice_id=%s, backend_mode=%s", voice_id, entry.backend_mode if entry else None)
    if entry is None:
        raise RuntimeError(f"Unbekannte Stimme: {voice_id!r}")
    
    # Create engine based on backend_mode
    if entry.backend_mode == "clone":
        from app.tts.qwen_engine import VoiceCloneEngine
        # VD-E: strikter Identity-Lock (§12/§24)
        if entry.voice_id == "vd_e":
            from app.security.identity_lock import assert_vd_e_usable
            log.debug("[DIAG-B] Calling assert_vd_e_usable() for VD-E")
            assert_vd_e_usable(production)
            log.debug("[DIAG-B] assert_vd_e_usable() passed")
            log.debug("[DIAG-D] Creating VoiceCloneEngine (candidate_id=VD-E, allow_design=False)")
            eng = VoiceCloneEngine(
                hw=hw,
                candidate_id="VD-E",
                description="produktion",
                models_dir=models_dir,
                attn_implementation=adv.get("attn_implementation") or None,
                allow_design=False
            )
            log.debug("[DIAG-D] VoiceCloneEngine VD-E created")
            return eng, hw
        # Neue englische Teststimmen (en_male_deep_*, en_female_calm_*):
        # VoiceDesign->Clone, Referenz wird bei Bedarf erzeugt (allow_design=True
        # wenn Datei fehlt, danach wiederverwendet). Kein globaler VD-E-Lock.
        from app.prosody.instruct import ENGLISH_VOICEDESIGN_DESCRIPTIONS, VOICEDESIGN_DESCRIPTIONS
        desc_entry = (ENGLISH_VOICEDESIGN_DESCRIPTIONS.get(entry.voice_id)
                      or VOICEDESIGN_DESCRIPTIONS.get(entry.voice_id) or {})
        description = desc_entry.get("description") or entry.description or "English narrator"
        # Referenzpfad aus Registry (z. B. cache/voice_refs/en_male_deep_01.wav)
        ref_path = None
        if entry.reference_path:
            from app import paths as _p
            ref_path = _p.ROOT / entry.reference_path
            if not ref_path.exists():
                # File fehlt → Design erlauben, sonst sperren
                allow = True
                log.info("Clone-Stimme %s: Referenz fehlt, VoiceDesign wird erzeugt: %s",
                         entry.voice_id, ref_path)
            else:
                allow = False
        else:
            allow = True
        log.debug("[DIAG-D] Creating VoiceCloneEngine (candidate_id=%s, allow_design=%s)",
                  entry.voice_id, allow)
        # candidate_id für Dateinamen: en_male_deep_01 (lowercase) -> file en_male_deep_01.wav
        # VoiceCloneEngine erwartet candidate_id passend zum Dateinamen ohne Pfad
        candidate_id = entry.voice_id if entry.voice_id.startswith("en_") else "VD-E"
        eng = VoiceCloneEngine(
            hw=hw,
            candidate_id=candidate_id,
            description=description,
            models_dir=models_dir,
            attn_implementation=adv.get("attn_implementation") or None,
            allow_design=allow,
            reference_path=ref_path if ref_path and ref_path.exists() else None
        )
        log.debug("[DIAG-D] VoiceCloneEngine %s created", entry.voice_id)
        return eng, hw
    
    else:
        # CustomVoice backend (§13)
        from app.tts.qwen_engine import QwenTTSEngine
        size = recommend_model_size(hw, adv.get("prefer_model_size", "auto"))
        device = adv.get("device", "auto")
        
        eng = QwenTTSEngine(hw=hw,
                            model_size=size,
                            models_dir=models_dir,
                            dtype_hint=recommend_torch_dtype(hw),
                            device_hint=device if device != "auto" else None,
                            attn_implementation=adv.get("attn_implementation") or None)
        return eng, hw


def cmd_headless(args) -> int:
    from app.batch.runner import BatchRunner
    from app.project.pipeline import Pipeline
    from app.ui.progress import ProgressReporter

    cfg = cfgmod.load_config()
    progress = ProgressReporter()
    engine, hw = _make_engine(args.engine, cfg)
    print(f"Betriebsart: {hw.mode} | Engine: {engine.name} "
          f"(Modell: {engine.info().get('model_size', 'test')})")

    def factory():
        return Pipeline(cfg, engine, progress=progress)

    runner = BatchRunner(factory, progress=progress)
    files = [paths.INPUT_DIR / f for f in args.files] if args.files else None
    summary = runner.run(files)
    print(f"\nFertig: {summary['completed']} âœ“ / {summary['failed']} âœ—")
    print(f"Bericht: {summary['report']}")
    try:
        engine.unload()
    except Exception:
        pass
    return 0 if summary["failed"] == 0 else 1


def _phase1_engine(args):
    cfg = cfgmod.load_config()
    engine, hw = _make_engine(args.engine, cfg)
    return engine


def cmd_german_baseline(args) -> int:
    from app.benchmark.german_ab import ensure_baseline
    engine = _phase1_engine(args)
    rep = ensure_baseline(engine, force=args.german_baseline_force)
    print(f"Baseline DE-Score: {rep.get('german_overall')} "
          f"({rep.get('n')} Texte)")
    print("Bericht: benchmark/baseline/report_baseline.md")
    return 0


def cmd_german_ab(args) -> int:
    from app.benchmark.german_ab import run_ab
    engine = _phase1_engine(args)
    rep = run_ab(engine, quick=args.quick)
    print(f"Baseline {rep['baseline']['german_overall']} -> "
          f"Gewinner {rep['winner']['german_overall']}")
    print("Bericht: benchmark/comparisons/report_AB.md")
    print("Ãœbernommen:", ", ".join(rep["applied_changes"]) or "keine Ã„nderung")
    return 0


def cmd_german_speakers(args) -> int:
    from app.voices.benchmark import run_german_speaker_benchmark
    engine = _phase1_engine(args)
    rep = run_german_speaker_benchmark(engine, quick=args.quick)
    print(f"DEFAULT BEST GERMAN NARRATOR: {rep.get('best_german_narrator')}")
    print("Bericht: benchmark/german_speakers.md")
    return 0


def _phase2_studio(args):
    if args.engine == "test_double":
        from app.tts.voice_studio import TestDoubleVoiceStudio
        return TestDoubleVoiceStudio()
    from app.hardware.detector import detect_hardware
    from app.tts.model_pool import QwenModelPool
    from app.tts.voice_studio import QwenVoiceStudio
    hw = detect_hardware()
    adv = cfgmod.load_config().get("advanced", {})
    pool = QwenModelPool(hw, attn_implementation=adv.get(
        "attn_implementation") or None)
    return QwenVoiceStudio(pool)


def cmd_phase2_run(args) -> int:
    from app.benchmark.phase2_ab import run_phase2
    rep = run_phase2(_phase2_studio(args), quick=args.quick)
    ok = [c for c in rep["candidates"] if not c.get("error")]
    print(f"Phase-2-Vergleich: {len(ok)} Kandidaten OK")
    print("Blindproben: benchmark/phase2/blind/sample_*.wav")
    print("Bericht:     benchmark/phase2/comparisons/report_phase2.md")
    rec = rep["recommendation"]
    print(f"Empfehlung:  {rec['recommended'] or 'keine (Phase 1 bleibt)'}")
    print("Auswahl:     python app/main.py --phase2-pick B  (anhÃ¶ren zuerst!)")
    return 0


def cmd_phase2_pauses(args) -> int:
    from app.benchmark.phase2_ab import run_pause_probe
    out = run_pause_probe(_phase2_studio(args))
    for name, m in out.items():
        print(f"{name:9} Pause Ã˜ {m['pause_mean_s']}s (Â±{m['pause_std_s']}, "
              f"min {m['pause_min_s']}, max {m['pause_max_s']}), "
              f"Gesamt {m['total_s']}s")
    print("Bericht: benchmark/phase2/pause_probe/report.json")
    return 0


def cmd_phase2_pick(args) -> int:
    from app.benchmark.phase2_ab import save_blind_pick
    status = save_blind_pick(args.phase2_pick)
    print(f"Auswahl gespeichert: {status['pick']} -> "
          f"{status['mapping'][status['pick']]}")
    print("Ãœbernehmen: python app/main.py --phase2-apply")
    return 0


def cmd_phase2_apply(args) -> int:
    from app.benchmark.phase2_ab import apply_pick_or_candidate
    cand = None if args.phase2_apply == "USER" else args.phase2_apply
    res = apply_pick_or_candidate(cand)
    print("Ãœbernommen:", res["applied"])
    print("NÃ¤chster normalem Lauf nutzt die neue Stimme "
          "(Cache wird automatisch neu aufgebaut).")
    return 0


def cmd_phase3_run(args) -> int:
    from app.benchmark.phase3 import run_phase3
    rep = run_phase3(_phase2_studio(args), quick=args.quick)
    print("Phase-3-Vergleich fertig (VD-E-Referenz gesperrt).")
    print("Ranking:", ", ".join(rep["ranked"]))
    print("Empfehlung:", rep["recommended"] or "keine")
    print("Blindproben: benchmark/phase3/blind/sample_*.wav")
    print("Bericht:     benchmark/phase3/comparisons/report_phase3.md")
    print("Danach:      --phase3-pick X  und  --phase3-apply")
    return 0


def cmd_phase3_pick(args) -> int:
    from app.benchmark.phase3 import save_phase3_pick
    st = save_phase3_pick(args.phase3_pick)
    print(f"Auswahl gespeichert: {st['pick']} -> "
          f"{st['mapping'][st['pick']]}")
    return 0


def cmd_phase3_apply(args) -> int:
    from app.benchmark.phase3 import apply_phase3_pick
    res = apply_phase3_pick()
    print("Ãœbernommen:", res["applied"])
    print("Die Stimme bleibt VD-E; nur Fachwort-/Variations-Schalter "
          "wurden gesetzt. Cache baut sich bei Bedarf neu auf.")
    return 0


def cmd_desktop_voices(args) -> int:
    from app.voices.desktop_benchmark import run_desktop_voice_benchmark
    rep = run_desktop_voice_benchmark(_phase2_studio(args) if
                                      args.engine == "test_double" else None)
    print("Voice-Report: benchmark/desktop_voices/report.md")
    for v in rep.get("voices", []):
        print(f"  {v['voice_id']:8} DE={v.get('de_score', '-')} "
              f"EN={v.get('en_score', '-')} "
              f"Klasse={v.get('class', '-')} "
              f"{v.get('note', '')}")
    return 0


def cmd_benchmark(args) -> int:
    cfg = cfgmod.load_config()
    engine, hw = _make_engine(args.engine, cfg)
    if args.benchmark == "system":
        from app.benchmark.system import run_system_benchmark
        rep = run_system_benchmark(lambda size: engine, quick=args.quick,
                                   hw=hw)
        print("System-Benchmark:", "OK" if rep["ok"] else "FEHLER")
        print("Bericht: benchmark/report_SYSTEM.md")
        return 0 if rep["ok"] else 1
    if args.benchmark == "voices":
        from app.voices.benchmark import run_voice_benchmark
        rep = run_voice_benchmark(engine, quick=args.quick)
        print("Stimmen-Benchmark fertig: benchmark/voice_benchmark.md")
        return 0
    print("Unbekannter Benchmark:", args.benchmark)
    return 2


def cmd_download_models(args) -> int:
    from huggingface_hub import snapshot_download
    targets = ["Qwen/Qwen3-TTS-Tokenizer-12Hz",
               "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"]
    if args.all_models:
        targets += ["Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
                    "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                    "Qwen/Qwen3-TTS-12Hz-1.7B-Base"]
    for repo in targets:
        print(f"Lade {repo} â€¦")
        snapshot_download(repo_id=repo,
                          local_dir=str(paths.MODELS_DIR / repo.split("/")[-1]))
        print(f"  âœ“ {repo}")
    print("Modelle liegen in models/ â€“ die App lÃ¤uft danach offline.")
    return 0


def cmd_info() -> int:
    from app.audio.ffmpeg import ffmpeg_version
    from app.hardware.detector import detect_hardware
    hw = detect_hardware()
    print("=== VoiceOverApp", __version__, "===")
    for k, v in hw.to_dict().items():
        print(f"{k:26} {v}")
    print(f"{'ffmpeg':26} {ffmpeg_version() or 'nicht gefunden'}")
    print(f"{'Standard-Sprache':26} {cfgmod.load_config().get('language')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="VoiceOverApp")
    parser.add_argument("--ui", action="store_true",
                        help="(veraltet) siehe --webserver")
    parser.add_argument("--webserver", action="store_true",
                        help="Entwickler-Webserver â€“ nur EXPLIZIT; "
                             "Standard ist die Desktop-GUI")
    parser.add_argument("--headless", action="store_true",
                        help="ohne GUI: input/ verarbeiten (CLI-Pipeline)")
    parser.add_argument("--input", type=str,
                        help="Eingabedatei oder -ordner für headless-Modus")
    parser.add_argument("--output", type=str,
                        help="Ausgabeverzeichnis für headless-Modus")
    parser.add_argument("--files", nargs="*", help="bestimmte Dateien")
    parser.add_argument("--engine", default="qwen",
                        choices=["qwen", "test_double"],
                        help="test_double NUR fÃ¼r automatisierte Tests")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--benchmark", choices=["system", "voices"])
    parser.add_argument("--german-baseline", action="store_true",
                        help="deutsche Baseline erzeugen/prÃ¼fen (Â§5 Phase 1)")
    parser.add_argument("--german-baseline-force", action="store_true",
                        help="Baseline neu erzeugen (alte wird gesichert)")
    parser.add_argument("--german-ab", action="store_true",
                        help="deutschen A/B-Benchmark ausfÃ¼hren (Â§25)")
    parser.add_argument("--german-speakers", action="store_true",
                        help="deutschen Stimmen-Benchmark ausfÃ¼hren (Â§19)")
    parser.add_argument("--phase2-run", action="store_true",
                        help="Phase 2: Voice-Vergleich Kybalion (VoiceDesign "
                             "+ CustomVoice, Blindproben)")
    parser.add_argument("--phase2-pauses", action="store_true",
                        help="Phase 2: Pausenstrategien-Sonde")
    parser.add_argument("--phase2-pick", metavar="LETTER",
                        help="Phase 2: Blindauswahl speichern (z. B. B)")
    parser.add_argument("--phase2-apply", nargs="?", const="USER",
                        metavar="KANDIDAT",
                        help="Phase 2: Auswahl/Kandidat Ã¼bernehmen")
    parser.add_argument("--phase3-run", action="store_true",
                        help="Phase 3: referenz-erhaltende VD-E-"
                             "Optimierung (FachwÃ¶rter/Emotion/Variation)")
    parser.add_argument("--phase3-pick", metavar="LETTER",
                        help="Phase 3: Blindauswahl speichern (z. B. C)")
    parser.add_argument("--phase3-apply", action="store_true",
                        help="Phase 3: Auswahl Ã¼bernehmen (nur Schalter, "
                             "Stimme bleibt VD-E)")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--download-models", action="store_true")
    parser.add_argument("--all-models", action="store_true",
                        help="auch 0.6B herunterladen")
    parser.add_argument("--job", metavar="JOBSPEC",
                        help="GUI-Backend-Modus: Job-Spec (JSON) abarbeiten "
                             "und JSONL-Ereignisse ausgeben (Â§16)")
    parser.add_argument("--desktop-voices", action="store_true",
                        help="Voice-Benchmark der Desktop-App (Â§15): alle "
                             "Stimmen DE+EN testen und Report schreiben")
    parser.add_argument("--info", action="store_true")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()
    mode = route_mode(args)

    paths.ensure_directories()
    setup_logging(log_text_content=bool(
        cfgmod.load_config().get("advanced", {}).get("log_text_content", False)))
    cfgmod.write_default_config_if_missing()
    log = get_logger("main")
    log.info("VoiceOverApp %s startet (Python %s)", __version__,
             sys.version.split()[0])

    if args.version:
        print(__version__)
        return 0
    if mode == "gui":
        # Normaler Start OHNE Modus-Argumente = Desktop-GUI (Â§3).
        from app.gui.app import run
        run()
        return 0
    if args.info:
        return cmd_info()
    if args.download_models:
        return cmd_download_models(args)
    if args.german_baseline or args.german_baseline_force:
        return cmd_german_baseline(args)
    if args.german_ab:
        return cmd_german_ab(args)
    if args.german_speakers:
        return cmd_german_speakers(args)
    if args.phase2_run:
        return cmd_phase2_run(args)
    if args.phase2_pauses:
        return cmd_phase2_pauses(args)
    if args.phase2_pick:
        return cmd_phase2_pick(args)
    if args.phase2_apply is not None:
        return cmd_phase2_apply(args)
    if args.phase3_run:
        return cmd_phase3_run(args)
    if args.phase3_pick:
        return cmd_phase3_pick(args)
    if args.phase3_apply:
        return cmd_phase3_apply(args)
    if args.benchmark:
        return cmd_benchmark(args)
    if args.headless:
        return cmd_headless(args)
    if args.job:
        from app.jobs.runner import JobSpec, run_job
        spec = JobSpec.from_json_file(args.job)
        return run_job(spec)
    if args.desktop_voices:
        return cmd_desktop_voices(args)

    if mode == "webserver":
        from app.ui.server import run_server
        port = args.port or int(cfgmod.load_config().get("ui", {})
                                .get("port", 8750))
        run_server(port=port, open_browser=not args.no_browser,
                   engine_name=args.engine)
        return 0
    return 0


def route_mode(args) -> str:
    """Eindeutiges Entry-Point-Routing (Â§3, testbar):

    gui        - kein Modus-Argument  -> Desktop-GUI (desktop.py ruft
                seinerseits diese Funktion; Normalstart = GUI)
    cli        - Pipeline/Benchmark-/Job-Argumente
    webserver  - NUR mit explizitem --webserver (Entwicklermodus)
    """
    if getattr(args, "webserver", False) or getattr(args, "ui", False):
        return "webserver"
    cli_flags = ("headless", "input", "output", "files", "job", "benchmark", "download_models",
                 "info", "version", "german_baseline",
                 "german_baseline_force", "german_ab", "german_speakers",
                 "phase2_run", "phase2_pauses", "phase2_pick",
                 "phase2_apply", "phase3_run", "phase3_pick",
                 "phase3_apply", "desktop_voices", "quick")
    if getattr(args, "job", None):
        return "cli"
    for f in cli_flags:
        if f == "files":
            if getattr(args, "files", None):
                return "cli"
        elif f == "phase2_apply":
            if getattr(args, "phase2_apply", None) is not None:
                return "cli"
        elif getattr(args, f, False):
            return "cli"
    return "gui"


if __name__ == "__main__":
    raise SystemExit(main())

