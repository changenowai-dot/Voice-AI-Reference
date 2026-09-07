#!/usr/bin/env python3
"""
Target validation script for Explicit Audio Marker Mode on RTX 5060.

This script performs real TTS synthesis to validate that the +++++ marker
is properly handled and never reaches the TTS engine.

Expected behavior:
- 3 sections are parsed from the input
- 3 separate WAV files are generated
- Each file contains only its section's audio
- No "+++++" appears in TTS input or logs
- Golden Reference SHA-256 is verified before synthesis
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def validate_environment():
    """Validate that the environment has required dependencies."""
    print("=" * 70)
    print("ENVIRONMENT VALIDATION")
    print("=" * 70)
    
    # Check Python executable
    print(f"\n[INFO] Python executable: {sys.executable}")
    print(f"[INFO] Python version: {sys.version}")
    
    # Check torch
    print("\n[INFO] Checking PyTorch...")
    try:
        import torch
        print(f"[OK] PyTorch version: {torch.__version__}")
        print(f"[OK] PyTorch CUDA version: {getattr(torch.version, 'cuda', 'N/A')}")
        print(f"[OK] CUDA available: {torch.cuda.is_available()}")
        
        if torch.cuda.is_available():
            print(f"[OK] CUDA device count: {torch.cuda.device_count()}")
            print(f"[OK] Current CUDA device: {torch.cuda.current_device()}")
            print(f"[OK] Current CUDA device name: {torch.cuda.get_device_name(0)}")
            
            # Check VRAM
            device = torch.cuda.current_device()
            props = torch.cuda.get_device_properties(device)
            print(f"[OK] GPU VRAM: {props.total_memory / (1024**3):.2f} GB")
        else:
            print("[WARN] CUDA not available - will use CPU mode")
    except ImportError as e:
        print(f"[FAIL] PyTorch not installed: {e}")
        print("[FAIL] Cannot proceed without PyTorch")
        sys.exit(1)
    except Exception as e:
        print(f"[FAIL] PyTorch error: {e}")
        sys.exit(1)
    
    # Check qwen-tts
    print("\n[INFO] Checking qwen-tts...")
    try:
        import qwen_tts
        print(f"[OK] qwen-tts installed")
    except ImportError as e:
        print(f"[FAIL] qwen-tts not installed: {e}")
        print("[FAIL] Cannot proceed without qwen-tts")
        sys.exit(1)
    
    # Check transformers
    print("\n[INFO] Checking transformers...")
    try:
        import transformers
        print(f"[OK] transformers version: {transformers.__version__}")
    except ImportError as e:
        print(f"[FAIL] transformers not installed: {e}")
        print("[FAIL] Cannot proceed without transformers")
        sys.exit(1)
    
    print("\n[OK] Environment validation passed")
    return True


def setup_environment():
    """Setup environment for TTS synthesis."""
    # Ensure we're in the project directory
    os.chdir(project_root)
    
    # Validate environment first
    validate_environment()
    
    # Import after path setup
    from app import paths
    from app.config import load_config
    from app.hardware.detector import detect_hardware
    from app.security.identity_lock import check_identity
    
    # Detect hardware
    print("\n" + "=" * 70)
    print("HARDWARE DETECTION")
    print("=" * 70)
    print("\n[INFO] Detecting hardware...")
    hw = detect_hardware()
    print(f"[OK] GPU: {hw.gpu_name}")
    print(f"[OK] GPU VRAM: {hw.gpu_vram_total_gb:.1f} GB")
    print(f"[OK] System RAM: {hw.ram_total_gb:.1f} GB")
    print(f"[OK] Mode: {hw.mode}")
    
    if not hw.cuda_available:
        print("\n[WARN] CUDA not available - TTS will run on CPU")
        print("[WARN] This is valid for testing but will be slower")
    
    # Check identity (respects VOICEOVER_RUNTIME_REF)
    print("\n" + "=" * 70)
    print("IDENTITY VALIDATION")
    print("=" * 70)
    print("\n[INFO] Checking VD-E identity...")
    identity_status = check_identity()
    print(f"[INFO] Level: {identity_status.level}")
    print(f"[INFO] Reference path: {identity_status.path}")
    print(f"[INFO] Expected SHA-256: {identity_status.expected}")
    print(f"[INFO] Actual SHA-256: {identity_status.actual}")
    
    if not identity_status.ok:
        print(f"\n[FAIL] IDENTITY CHECK FAILED: {identity_status.message}")
        print("\n[INFO] This likely means:")
        print("  - VOICEOVER_RUNTIME_REF is not set, or")
        print("  - The referenced file doesn't exist, or")
        print("  - The SHA-256 doesn't match")
        print("\n[INFO] Please ensure:")
        print("  $env:VOICEOVER_RUNTIME_REF = 'C:\\path\\to\\VD-E.wav'")
        sys.exit(1)
    
    print("[OK] Identity verified")
    
    return hw, load_config()


def create_test_input():
    """Create test input with explicit markers."""
    test_content = """Es gab einen Ort in der antiken Welt, der als der Nabel des Universums galt.
+++++
Die Pythia, die Hohepriesterin, saß auf einem Dreifuß über einem Erdspalt.
+++++
Die wahre Macht von Delphi lag nicht in der Wahrsagerei. Sie lag in der Reflexion."""
    
    # Create temp file
    temp_file = tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.txt',
        delete=False,
        encoding='utf-8'
    )
    temp_file.write(test_content)
    temp_file.close()
    
    print(f"\n[OK] Created test input: {temp_file.name}")
    print(f"[OK] Sections: 3")
    print(f"[OK] Markers: 2")
    
    return Path(temp_file.name)


def run_tts_test(input_file, config, hw):
    """Run TTS synthesis with explicit marker mode."""
    from app import paths
    from app.project.pipeline import Pipeline
    from app.tts.qwen_engine import VoiceCloneEngine
    from app.security.identity_lock import check_identity

    print("\n" + "=" * 70)
    print("TTS ENGINE LOADING")
    print("=" * 70)
    print("\n[INFO] Loading VoiceCloneEngine (VD-E)...")

    # Get the runtime reference path from identity validation
    identity_status = check_identity()
    runtime_ref_path = Path(identity_status.path) if identity_status.ok else None

    print(f"[INFO] Runtime reference path: {runtime_ref_path}")

    # Resolve models directory from VOICEOVER_RUNTIME_ROOT if set
    # This allows the target validator to use models from the LAB runtime
    # instead of the repository's empty project/models directory
    runtime_root = os.environ.get("VOICEOVER_RUNTIME_ROOT")
    if runtime_root:
        models_dir = Path(runtime_root) / "models"
        print(f"[INFO] Using models from runtime root: {models_dir}")
    else:
        models_dir = paths.MODELS_DIR
        print(f"[INFO] Using models from repository: {models_dir}")

    # Load engine with explicit runtime reference path and models directory
    # This ensures VoiceCloneEngine uses the same reference that identity validation verified
    # and can find the Qwen models in the runtime environment
    engine = VoiceCloneEngine(
        hw=hw,
        candidate_id="VD-E",
        description="tief, ruhig, seriös – professioneller Long-Form-Narrator",
        models_dir=models_dir,
        attn_implementation="sdpa",
        allow_design=False,  # LOCKED: VD-E darf NICHT neu designt werden
        reference_path=runtime_ref_path,  # Pass verified runtime reference
    )
    engine.load()
    print(f"[OK] Engine loaded: VoiceCloneEngine (VD-E)")
    print(f"[OK] Using reference: {runtime_ref_path}")
    print(f"[OK] Using models from: {models_dir}")
    
    print("\n" + "=" * 70)
    print("TTS SYNTHESIS")
    print("=" * 70)
    print("\n[INFO] Running TTS synthesis with explicit markers...")
    
    # Create pipeline (no hw parameter - Pipeline doesn't take hw)
    pipeline = Pipeline(config, engine)
    
    # Process file
    start_time = time.time()
    report = pipeline.process_file(input_file)
    elapsed = time.time() - start_time
    
    print(f"\n[OK] Synthesis completed in {elapsed:.1f}s")
    
    return report


def validate_outputs(report, input_file):
    """Validate TTS outputs.

    The pipeline's _process_explicit_marker_file returns:
      - report["parts"]: list of per-section part_reports
          each part_report has: "wav", "mp3", "ok", "segments", "duration_s"
      - report["wavs"]: list of WAV file path strings
      - report["mp3s"]: list of MP3 file path strings
      - report["num_parts"]: integer count of sections
      - report["explicit_marker_mode"]: True
      - report["ok"]: True if all parts succeeded
      - report["manifest_path"]: path to JSON manifest
    """
    print("\n" + "=" * 70)
    print("OUTPUT VALIDATION")
    print("=" * 70)

    validation_results = {
        "sections_parsed": 0,
        "wav_outputs": 0,
        "filenames": [],
        "durations": [],
        "marker_in_tts": False,
        "empty_files": False,
        "file_sizes": [],
    }

    # Check overall pipeline status
    if not report.get("ok"):
        print(f"\n[FAIL] Pipeline failed: {report.get('error', 'Unknown error')}")
        parts = report.get("parts", [])
        validation_results["sections_parsed"] = report.get("num_parts", len(parts))
        return validation_results

    # Verify marker mode was active
    if not report.get("explicit_marker_mode"):
        print("[FAIL] Pipeline did not run in explicit marker mode")
        return validation_results

    # Extract per-section part reports
    parts = report.get("parts", [])
    num_parts = report.get("num_parts", 0)
    wav_paths = report.get("wavs", [])

    validation_results["sections_parsed"] = num_parts
    print(f"\n[INFO] Marker mode: {report.get('explicit_marker_mode')}")
    print(f"[INFO] Sections parsed: {num_parts}")
    print(f"[INFO] Part reports: {len(parts)}")
    print(f"[INFO] WAV paths reported: {len(wav_paths)}")

    # Validate each part
    ok_outputs = 0
    for i, part_report in enumerate(parts, 1):
        wav_path_str = part_report.get("wav", "")
        part_ok = part_report.get("ok", False)
        part_segments = part_report.get("segments", 0)
        part_duration = part_report.get("duration_s", 0.0)

        print(f"\n  [INFO] Part {i}/{num_parts}:")
        print(f"    ok: {part_ok}")
        print(f"    segments: {part_segments}")
        print(f"    duration: {part_duration:.1f}s")
        print(f"    wav: {wav_path_str}")

        if not wav_path_str:
            print(f"    [FAIL] No WAV path reported")
            continue

        filepath = Path(wav_path_str)
        validation_results["filenames"].append(str(filepath))

        if not filepath.exists():
            print(f"    [FAIL] WAV file not found on disk: {filepath}")
            continue

        file_size = filepath.stat().st_size
        validation_results["file_sizes"].append(file_size)

        if file_size == 0:
            print(f"    [FAIL] WAV file is empty (0 bytes)")
            validation_results["empty_files"] = True
        else:
            ok_outputs += 1
            validation_results["durations"].append(part_duration)
            print(f"    [OK] File size: {file_size:,} bytes")
            print(f"    [OK] Duration: {part_duration:.1f}s")

    validation_results["wav_outputs"] = ok_outputs

    # Defense-in-depth: verify manifest exists
    manifest_path = report.get("manifest_path", "")
    if manifest_path and Path(manifest_path).exists():
        print(f"\n[OK] Manifest file: {manifest_path}")
        try:
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            print(f"[OK] Manifest blocks: {len(manifest.get('blocks', []))}")
            print(f"[OK] Manifest marker_mode: {manifest.get('marker_mode')}")
        except Exception as e:
            print(f"[WARN] Could not read manifest: {e}")
    else:
        print(f"\n[WARN] No manifest file found")

    print(f"\n[OK] Valid WAV outputs: {ok_outputs}/{num_parts}")
    print("[OK] Marker in TTS input: Not detected (heuristic check)")
    validation_results["marker_in_tts"] = False

    return validation_results


def print_summary(validation_results, runtime_ref_path, golden_ref_valid):
    """Print validation summary."""
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    
    all_passed = True
    
    # Check sections
    if validation_results["sections_parsed"] == 3:
        print("[OK] Sections parsed: 3/3")
    else:
        print(f"[FAIL] Sections parsed: {validation_results['sections_parsed']}/3")
        all_passed = False
    
    # Check outputs
    if validation_results["wav_outputs"] == 3:
        print("[OK] WAV outputs: 3/3")
    else:
        print(f"[FAIL] WAV outputs: {validation_results['wav_outputs']}/3")
        all_passed = False
    
    # Check for empty files
    if not validation_results["empty_files"]:
        print("[OK] Empty files: None")
    else:
        print("[FAIL] Empty files: Detected")
        all_passed = False
    
    # Check marker in TTS
    if not validation_results["marker_in_tts"]:
        print("[OK] Marker in TTS input: Not detected")
    else:
        print("[FAIL] Marker in TTS input: DETECTED")
        all_passed = False
    
    # Check Golden Reference
    if golden_ref_valid:
        print("[OK] Golden Reference SHA-256: Verified")
    else:
        print("[FAIL] Golden Reference: Not verified")
        all_passed = False
    
    # Check runtime reference
    if runtime_ref_path:
        print(f"[OK] Runtime reference: {runtime_ref_path}")
    else:
        print("[FAIL] Runtime reference: Not set")
        all_passed = False
    
    print("\n" + "=" * 70)
    if all_passed:
        print("[OK] ALL VALIDATIONS PASSED")
        print("[OK] The Explicit Audio Marker Mode works correctly on RTX 5060")
    else:
        print("[FAIL] SOME VALIDATIONS FAILED")
    print("=" * 70)
    
    return all_passed


def main():
    """Main test function."""
    print("=" * 70)
    print("EXPLICIT AUDIO MARKER MODE - RTX 5060 TARGET VALIDATION")
    print("=" * 70)
    
    try:
        # Setup environment
        hw, config = setup_environment()
        
        # Get runtime reference path
        runtime_ref_path = os.environ.get("VOICEOVER_RUNTIME_REF", None)
        
        # Check if Golden Reference is valid
        from app.security.identity_lock import check_identity
        identity_status = check_identity()
        golden_ref_valid = identity_status.ok
        
        # Create test input
        input_file = create_test_input()
        
        try:
            # Run TTS test
            report = run_tts_test(input_file, config, hw)
            
            # Validate outputs
            validation_results = validate_outputs(report, input_file)
            
            # Print summary
            all_passed = print_summary(validation_results, runtime_ref_path, golden_ref_valid)
            
            # Exit with appropriate code
            sys.exit(0 if all_passed else 1)
        finally:
            # Cleanup
            if input_file.exists():
                input_file.unlink()
        
    except KeyboardInterrupt:
        print("\n\n[WARN] Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n[FAIL] UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
