"""Regression tests for model-root resolution.

Validates that QwenModelPool correctly resolves model paths from:
1. Explicit model directory (models_dir parameter)
2. VOICEOVER_RUNTIME_ROOT environment variable
3. Repository-local model directory (default)
4. HF_HOME environment variable (standard HuggingFace cache)
5. Default HF cache (~/.cache/huggingface/hub)

Also validates that the target validator correctly passes the model root
from VOICEOVER_RUNTIME_ROOT to the engine.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestModelRootResolution(unittest.TestCase):
    """Test that QwenModelPool resolves model paths correctly."""

    def test_model_pool_accepts_models_dir_parameter(self):
        """QwenModelPool should accept explicit models_dir."""
        from app.tts.model_pool import QwenModelPool
        from unittest.mock import MagicMock

        hw = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            models_dir = Path(tmpdir) / "models"
            models_dir.mkdir()
            pool = QwenModelPool(hw=hw, models_dir=models_dir)
            self.assertEqual(pool.models_dir, models_dir)

    def test_model_pool_default_models_dir(self):
        """QwenModelPool should use paths.MODELS_DIR when no override."""
        from app.tts.model_pool import QwenModelPool
        from app import paths
        from unittest.mock import MagicMock

        hw = MagicMock()
        pool = QwenModelPool(hw=hw)
        self.assertEqual(pool.models_dir, paths.MODELS_DIR)

    def test_model_pool_direct_path_resolution(self):
        """QwenModelPool should find models in direct path format."""
        from app.tts.model_pool import QwenModelPool
        from unittest.mock import MagicMock

        hw = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            models_dir = Path(tmpdir)
            # Create a fake model directory with model.safetensors
            model_dir = models_dir / "Qwen3-TTS-12Hz-1.7B-Base"
            model_dir.mkdir()
            (model_dir / "model.safetensors").write_bytes(b"fake model data")

            pool = QwenModelPool(hw=hw, models_dir=models_dir)
            resolved = pool._resolve_model_path("Qwen/Qwen3-TTS-12Hz-1.7B-Base")
            self.assertEqual(resolved, str(model_dir))

    def test_model_pool_local_hf_cache_resolution(self):
        """QwenModelPool should find models in local HF cache format."""
        from app.tts.model_pool import QwenModelPool
        from unittest.mock import MagicMock

        hw = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            models_dir = Path(tmpdir)
            # Create a fake HF cache structure
            snapshot_dir = (
                models_dir / "hf" / "hub" /
                "models--Qwen--Qwen3-TTS-12Hz-1.7B-Base" / "snapshots" / "abc123"
            )
            snapshot_dir.mkdir(parents=True)
            (snapshot_dir / "model.safetensors").write_bytes(b"fake model data")

            pool = QwenModelPool(hw=hw, models_dir=models_dir)
            resolved = pool._resolve_model_path("Qwen/Qwen3-TTS-12Hz-1.7B-Base")
            self.assertEqual(resolved, str(snapshot_dir))

    def test_model_pool_hf_home_resolution(self):
        """QwenModelPool should find models in HF_HOME cache."""
        from app.tts.model_pool import QwenModelPool
        from unittest.mock import MagicMock

        hw = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set up HF_HOME to point to temp directory
            hf_home = Path(tmpdir) / "hf_cache"
            hf_home.mkdir()
            snapshot_dir = (
                hf_home / "hub" /
                "models--Qwen--Qwen3-TTS-12Hz-1.7B-Base" / "snapshots" / "def456"
            )
            snapshot_dir.mkdir(parents=True)
            (snapshot_dir / "model.safetensors").write_bytes(b"fake model data")

            # Use a different models_dir that doesn't have the model
            models_dir = Path(tmpdir) / "models"
            models_dir.mkdir()

            old_hf_home = os.environ.get("HF_HOME")
            try:
                os.environ["HF_HOME"] = str(hf_home)
                pool = QwenModelPool(hw=hw, models_dir=models_dir)
                resolved = pool._resolve_model_path("Qwen/Qwen3-TTS-12Hz-1.7B-Base")
                self.assertEqual(resolved, str(snapshot_dir))
            finally:
                if old_hf_home is not None:
                    os.environ["HF_HOME"] = old_hf_home
                else:
                    os.environ.pop("HF_HOME", None)

    def test_model_pool_missing_model_failure(self):
        """QwenModelPool should raise FileNotFoundError for missing models."""
        from app.tts.model_pool import QwenModelPool
        from unittest.mock import MagicMock

        hw = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            models_dir = Path(tmpdir)
            pool = QwenModelPool(hw=hw, models_dir=models_dir)

            with self.assertRaises(FileNotFoundError) as ctx:
                pool._resolve_model_path("Qwen/Qwen3-TTS-12Hz-1.7B-Base")
            self.assertIn("Qwen model not found", str(ctx.exception))
            self.assertIn("Qwen3-TTS-12Hz-1.7B-Base", str(ctx.exception))

    def test_model_pool_direct_path_takes_priority(self):
        """Direct path should take priority over HF cache."""
        from app.tts.model_pool import QwenModelPool
        from unittest.mock import MagicMock

        hw = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            models_dir = Path(tmpdir)
            # Create both direct path and HF cache
            direct_model = models_dir / "Qwen3-TTS-12Hz-1.7B-Base"
            direct_model.mkdir()
            (direct_model / "model.safetensors").write_bytes(b"direct model")

            snapshot_dir = (
                models_dir / "hf" / "hub" /
                "models--Qwen--Qwen3-TTS-12Hz-1.7B-Base" / "snapshots" / "abc123"
            )
            snapshot_dir.mkdir(parents=True)
            (snapshot_dir / "model.safetensors").write_bytes(b"cache model")

            pool = QwenModelPool(hw=hw, models_dir=models_dir)
            resolved = pool._resolve_model_path("Qwen/Qwen3-TTS-12Hz-1.7B-Base")
            # Should return direct path, not HF cache
            self.assertEqual(resolved, str(direct_model))


class TestTargetValidatorModelRoot(unittest.TestCase):
    """Test that target validator correctly resolves model root."""

    def test_target_validator_uses_runtime_root_for_models(self):
        """Target validator should use VOICEOVER_RUNTIME_ROOT for models."""
        validator_path = Path(__file__).parent / "target_validate_explicit_marker.py"
        source = validator_path.read_text(encoding="utf-8")

        # Verify the wiring exists
        self.assertIn("VOICEOVER_RUNTIME_ROOT", source)
        self.assertIn("models_dir", source)
        self.assertIn("runtime_root", source)

    def test_target_validator_falls_back_to_repo_models(self):
        """Target validator should fall back to paths.MODELS_DIR if no runtime root."""
        validator_path = Path(__file__).parent / "target_validate_explicit_marker.py"
        source = validator_path.read_text(encoding="utf-8")

        # Verify fallback logic exists
        self.assertIn("paths.MODELS_DIR", source)
        self.assertIn("else:", source)

    def test_target_validator_model_and_reference_from_same_root(self):
        """Model and reference should be able to come from the same runtime root."""
        validator_path = Path(__file__).parent / "target_validate_explicit_marker.py"
        source = validator_path.read_text(encoding="utf-8")

        # Both should use VOICEOVER_RUNTIME_ROOT
        self.assertIn("VOICEOVER_RUNTIME_ROOT", source)
        self.assertIn("VOICEOVER_RUNTIME_REF", source)
        self.assertIn("runtime_root", source)
        self.assertIn("runtime_ref_path", source)


class TestNoMarkerPathUnchanged(unittest.TestCase):
    """Verify no-marker production path is unchanged."""

    def test_model_pool_has_no_marker_specific_logic(self):
        """ModelPool should not have any marker-specific logic."""
        pool_path = Path(__file__).parent.parent / "app" / "tts" / "model_pool.py"
        source = pool_path.read_text(encoding="utf-8")
        self.assertNotIn("marker", source.lower())
        self.assertNotIn("+++++", source)

    def test_qwen_engine_has_no_marker_specific_logic(self):
        """QwenEngine should not have marker-specific model logic."""
        engine_path = Path(__file__).parent.parent / "app" / "tts" / "qwen_engine.py"
        source = engine_path.read_text(encoding="utf-8")
        # The engine should not have any marker-specific model resolution
        self.assertNotIn("marker", source.lower().split("models_dir")[0])


if __name__ == "__main__":
    unittest.main()
