import sys
import time
import hashlib
from pathlib import Path

import numpy as np
import soundfile as sf

APP = Path(sys.argv[1]).resolve()
ATTN = sys.argv[2]
OUT = Path(sys.argv[3]).resolve()

sys.path.insert(0, str(APP))

from app.hardware.detector import detect_hardware
from app.tts.engine_base import SynthesisRequest
from app.tts.qwen_engine import VoiceCloneEngine

hw = detect_hardware()

# Der Engine-Test verwendet absichtlich exakt diese erwartete Datei.
ref_candidates = [
    APP / "cache" / "voice_refs" / "vd_e.wav",
    APP / "cache" / "voice_refs" / "VD-E.wav",
]

ref = next((p for p in ref_candidates if p.exists()), None)

print("ATTENTION=" + ATTN)
print("GPU=" + str(hw.gpu_name))
print("VRAM_GB=" + str(hw.gpu_vram_total_gb))
print("CUDA=" + str(hw.cuda_available))
print("CUDA_VERSION=" + str(hw.cuda_version))
print("TORCH_VERSION=" + str(hw.torch_version))
print("TORCH_CUDA=" + str(hw.torch_cuda_version))
print("TORCH_GPU_OK=" + str(hw.torch_gpu_ok))

if ref is None:
    raise SystemExit("VD-E reference missing")

print("REF_PATH=" + str(ref))
print("REF_EXISTS=True")

ref_hash = hashlib.sha256(ref.read_bytes()).hexdigest().upper()
print("REF_SHA256=" + ref_hash)
print("REF_BYTES=" + str(ref.stat().st_size))

text = (
    "Dies ist ein kontrollierter Vergleichstest der beiden "
    "Attention-Implementierungen. Die Stimme, der Text, der Seed "
    "und die Sampling-Parameter bleiben identisch."
)

sampling = {
    "temperature": 0.85,
    "top_k": 50,
    "top_p": 0.95,
}

engine = VoiceCloneEngine(
    hw=hw,
    candidate_id="vd_e",
    description="VD-E",
    models_dir=None,
    attn_implementation=ATTN,
    allow_design=False,
)

request = SynthesisRequest(
    text=text,
    language="German",
    speaker="",
    instruct="",
    sampling=sampling,
    seed=424242,
    max_seconds_hint=30.0,
    speed=1.0,
)

t0 = time.perf_counter()

try:
    result = engine.synthesize(request)
finally:
    # Unload auch bei Fehler möglichst sauber versuchen.
    try:
        engine.unload()
    except Exception:
        pass

elapsed = time.perf_counter() - t0

wave = np.asarray(result.waveform, dtype=np.float32).reshape(-1)
sample_rate = int(result.sample_rate)

OUT.parent.mkdir(parents=True, exist_ok=True)
sf.write(str(OUT), wave, sample_rate)

duration = float(result.duration_s)

print("RESULT_ENGINE=" + str(result.engine))
print("SAMPLE_RATE=" + str(sample_rate))
print("DURATION_S=" + str(duration))
print("ELAPSED_S=" + str(round(elapsed, 3)))
print("RTF=" + str(round(elapsed / max(duration, 1e-6), 3)))
print("WAV_BYTES=" + str(OUT.stat().st_size))
print("WAV_SHA256=" + hashlib.sha256(OUT.read_bytes()).hexdigest().upper())
print("OUTPUT=" + str(OUT))
print("RUN_COMPLETE")
