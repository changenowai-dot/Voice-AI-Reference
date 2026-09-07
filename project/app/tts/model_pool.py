from pathlib import Path
from typing import Any

from app.config import paths


class QwenModelPool:
    """Deterministischer Qwen-Modellpool."""

    MODEL_REPOS = {
        "customvoice": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "customvoice_0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
        "base": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    }

    def __init__(self, hw: Any, models_dir: Path | None = None, dtype_hint: str | None = None, attn_implementation: str | None = None):
        self.hw = hw
        self.models_dir = Path(models_dir) if models_dir else paths.MODELS_DIR
        self.dtype_hint = dtype_hint
        self.attn_implementation = attn_implementation or "flash_attention_2"
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

        # Also check HF_HOME cache (standard HuggingFace cache location)
        import os
        hf_home = os.environ.get("HF_HOME")
        if hf_home:
            hf_hub = Path(hf_home) / "hub"
            hf_cache_root = hf_hub / ("models--" + repo.replace("/", "--"))
            hf_snapshots = hf_cache_root / "snapshots"
            if hf_snapshots.is_dir():
                hf_candidates = []
                for d in hf_snapshots.iterdir():
                    if d.is_dir() and (d / "model.safetensors").is_file():
                        hf_candidates.append(d)
                if hf_candidates:
                    hf_candidates.sort(
                        key=lambda p: (p / "model.safetensors").stat().st_size,
                        reverse=True
                    )
                    return str(hf_candidates[0])

        # Check default HF cache (~/.cache/huggingface/hub)
        default_hf_hub = Path.home() / ".cache" / "huggingface" / "hub"
        default_cache_root = default_hf_hub / ("models--" + repo.replace("/", "--"))
        default_snapshots = default_cache_root / "snapshots"
        if default_snapshots.is_dir():
            default_candidates = []
            for d in default_snapshots.iterdir():
                if d.is_dir() and (d / "model.safetensors").is_file():
                    default_candidates.append(d)
            if default_candidates:
                default_candidates.sort(
                    key=lambda p: (p / "model.safetensors").stat().st_size,
                    reverse=True
                )
                return str(default_candidates[0])

        raise FileNotFoundError(
            f"Qwen model not found for {repo}. "
            f"Checked direct path {direct}, local HF cache {snapshots}, "
            f"HF_HOME={os.environ.get('HF_HOME', 'not set')}, "
            f"and default HF cache {default_snapshots}"
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

        model = Qwen3TTSModel.from_pretrained(
            path,
            **kwargs
        )

        self._loaded[name] = model
        return model

    def clear(self):
        self._loaded.clear()




