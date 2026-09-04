from pathlib import Path

from app.config import paths


class QwenTTSEngine:
    ENGINE_NAME = "qwen3-tts-customvoice"

    def __init__(
        self,
        model_size: str = "1.7B",
        models_dir: Path | None = None,
        dtype_hint: str | None = None,
    ):
        self.model_size = model_size
        self.models_dir = Path(models_dir) if models_dir else paths.MODELS_DIR
        self.dtype_hint = dtype_hint

        self.repo_ids = {
            "1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
            "0.6B": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
        }

        self.repo_id = self.repo_ids.get(
            model_size,
            self.repo_ids["1.7B"]
        )

        self._model = None
        self._model_path = None

    def _resolve_model_path(self) -> str:
        direct = self.models_dir / self.repo_id.split("/")[-1]

        if (direct / "model.safetensors").is_file():
            return str(direct)

        hub = self.models_dir / "hf" / "hub"

        cache_root = hub / (
            "models--" + self.repo_id.replace("/", "--")
        )

        snapshots = cache_root / "snapshots"

        if snapshots.is_dir():

            candidates = [
                d for d in snapshots.iterdir()
                if d.is_dir()
                and (d / "model.safetensors").is_file()
            ]

            if candidates:

                candidates.sort(
                    key=lambda p: (
                        p / "model.safetensors"
                    ).stat().st_size,
                    reverse=True
                )

                resolved = candidates[0]

                return str(resolved)

        raise FileNotFoundError(
            f"Qwen model not found: {self.repo_id}"
        )

    def load(self):

        if self._model is not None:
            return self._model

        import torch
        from qwen_tts import Qwen3TTSModel

        path = self._resolve_model_path()

        self._model_path = path

        device = (
            "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )

        kwargs = {}

        if device == "cuda":

            kwargs["dtype"] = torch.bfloat16

            kwargs["device_map"] = "cuda"

        self._model = Qwen3TTSModel.from_pretrained(
            path,
            **kwargs
        )

        return self._model
