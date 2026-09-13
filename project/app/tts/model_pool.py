from pathlib import Path
from typing import Any

from app.config import paths


class QwenModelPool:
    """Deterministischer Qwen-Modellpool."""

    MODEL_REPOS = {
        "customvoice": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "customvoice_0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
        "base": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        "voicedesign": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    }

    def __init__(self, hw: Any, models_dir: Path | None = None, dtype_hint: str | None = None, attn_implementation: str | None = None):
        self.hw = hw
        self.models_dir = Path(models_dir) if models_dir else paths.MODELS_DIR
        self.dtype_hint = dtype_hint
        # SDPA is built into PyTorch and works reliably on RTX 5060 (Blackwell)
        # without requiring the flash-attn wheel (which is not available on
        # Windows for all torch/CUDA combinations). Use sdpa as default;
        # caller can override via attn_implementation="flash_attention_2" if
        # flash-attn is confirmed installed.
        self.attn_implementation = attn_implementation or "sdpa"
        self._loaded = {}

    def _resolve_model_path(self, repo: str) -> str:
        direct = self.models_dir / repo.split("/")[-1]

        if (direct / "model.safetensors").is_file():
            return str(direct)

        hub = self.models_dir / "hf" / "hub"
        cache_root = hub / ("models--" + repo.replace("/", "--"))
        snapshots = cache_root / "snapshots"

        if snapshots.is_dir():
            candidates = []

            for d in snapshots.iterdir():
                if d.is_dir() and (d / "model.safetensors").is_file():
                    candidates.append(d)

            if candidates:
                candidates.sort(
                    key=lambda p: (p / "model.safetensors").stat().st_size,
                    reverse=True
                )
                resolved = candidates[0]
                return str(resolved)

        raise FileNotFoundError(
            f"Qwen model not found for {repo}. "
            f"Checked direct path {direct} and HuggingFace cache {snapshots}"
        )

    def get(self, name: str):
        if name in self._loaded:
            return self._loaded[name]

        repo = self.MODEL_REPOS.get(name)

        if repo is None:
            raise KeyError(f"Unknown Qwen model pool entry: {name}")

        path = self._resolve_model_path(repo)

        import torch
        from qwen_tts import Qwen3TTSModel

        device = "cuda" if torch.cuda.is_available() else "cpu"

        kwargs = {}

        if device == "cuda":
            kwargs["dtype"] = torch.bfloat16
            kwargs["device_map"] = "cuda"
        else:
            kwargs["dtype"] = torch.float32

        # Pass attn_implementation (sdpa by default for Win/RTX 5060 compat)
        if self.attn_implementation:
            kwargs["attn_implementation"] = self.attn_implementation

        # Allow dtype override (fp16 fallback etc.)
        if self.dtype_hint == "float16":
            kwargs["dtype"] = torch.float16
        elif self.dtype_hint == "float32":
            kwargs["dtype"] = torch.float32

        model = Qwen3TTSModel.from_pretrained(
            path,
            **kwargs
        )
        # Immer eval()-Modus: Deaktiviert Dropout und andere Trainings-RNGs
        # die Retry-Nichtdeterminismus auch bei gleichem Seed verursachen.
        try:
            model.eval()
        except Exception:
            pass

        self._loaded[name] = model
        return model

    def clear(self):
        self._loaded.clear()

    def unload(self):
        """Alias for clear() — unload all loaded models and free VRAM."""
        import gc
        import torch
        self._loaded.clear()
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            try:
                torch.cuda.synchronize()
            except Exception:
                pass




