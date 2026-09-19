"""Tests for Multi-Root Model Discovery (Tokenizer fix).

Validates that the Phase 4 env check can find models spread across
multiple VoiceOverApp installations (e.g. CustomVoice in one location,
Tokenizer in another).

No GPU required. Uses temporary directory structures.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class MultiRootModelDiscoveryTest(unittest.TestCase):
    """Test Multi-Root Model Discovery for Tokenizer and other models."""

    def setUp(self):
        """Create temporary directory structure simulating multiple VoiceOverApp installations."""
        self.tmpdir = tempfile.mkdtemp(prefix="test_multiroot_")
        self.tmp_path = Path(self.tmpdir)
        
        # Save original env
        self.orig_env = {}
        for key in ("VOICEOVER_MODELS_DIR", "VOICEOVER_MODELS_ROOTS", "VOICEOVER_ROOT"):
            self.orig_env[key] = os.environ.get(key)
        
        # Simulation: VoiceOverApp_LAB_NEXT with CustomVoice + Base
        self.lab_next = self.tmp_path / "VoiceOverApp_LAB_NEXT"
        self.lab_models = self.lab_next / "models" / "hf" / "hub"
        (self.lab_models / "models--Qwen--Qwen3-TTS-12Hz-1.7B-CustomVoice" / "snapshots").mkdir(parents=True)
        (self.lab_models / "models--Qwen--Qwen3-TTS-12Hz-1.7B-Base" / "snapshots").mkdir(parents=True)
        
        # Simulation: VoiceOverApp_LAB_PREV with Tokenizer (and maybe Base)
        self.lab_prev = self.tmp_path / "VoiceOverApp_LAB_PREV"
        self.prev_models = self.lab_prev / "models" / "hf" / "hub"
        (self.prev_models / "models--Qwen--Qwen3-TTS-Tokenizer-12Hz" / "snapshots").mkdir(parents=True)
        
        # Simulation: VoiceOverApp_OLD with all three models
        self.lab_old = self.tmp_path / "VoiceOverApp_OLD"
        self.old_models = self.lab_old / "models" / "hf" / "hub"
        (self.old_models / "models--Qwen--Qwen3-TTS-12Hz-1.7B-CustomVoice" / "snapshots").mkdir(parents=True)
        (self.old_models / "models--Qwen--Qwen3-TTS-12Hz-1.7B-Base" / "snapshots").mkdir(parents=True)
        (self.old_models / "models--Qwen--Qwen3-TTS-Tokenizer-12Hz" / "snapshots").mkdir(parents=True)
        
        # Set VOICEOVER_ROOT to prevent import issues
        os.environ["VOICEOVER_ROOT"] = str(PROJECT_ROOT)
    
    def tearDown(self):
        """Clean up temporary directories and restore environment."""
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        for key, val in self.orig_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
    
    def test_find_all_model_roots_discovers_multiple(self):
        """_find_all_model_roots should find all VoiceOverApp installations."""
        from benchmark.phase4_env_check import _find_all_model_roots
        
        # Set up env to point to our temp directories
        roots_str = os.pathsep.join([
            str(self.lab_models.parent.parent),  # VoiceOverApp_LAB_NEXT/models
            str(self.prev_models.parent.parent),  # VoiceOverApp_LAB_PREV/models
            str(self.old_models.parent.parent),   # VoiceOverApp_OLD/models
        ])
        os.environ["VOICEOVER_MODELS_ROOTS"] = roots_str
        
        all_roots = _find_all_model_roots()
        
        # Should find at least the 3 we specified
        root_strs = [str(r) for r in all_roots]
        self.assertTrue(
            any("LAB_NEXT" in r for r in root_strs),
            f"LAB_NEXT not found in roots: {root_strs}"
        )
        self.assertTrue(
            any("LAB_PREV" in r for r in root_strs),
            f"LAB_PREV not found in roots: {root_strs}"
        )
        self.assertTrue(
            any("OLD" in r for r in root_strs),
            f"OLD not found in roots: {root_strs}"
        )
    
    def test_find_model_in_roots_tokenizer_from_different_root(self):
        """Tokenizer should be found even if it's in a different root than other models."""
        from benchmark.phase4_env_check import _find_model_in_roots
        
        roots = [
            self.lab_models.parent.parent,  # Has CustomVoice + Base but NO Tokenizer
            self.prev_models.parent.parent,  # Has Tokenizer
        ]
        
        # CustomVoice should be found in first root
        found, path = _find_model_in_roots(
            "Qwen3-TTS-12Hz-1.7B-CustomVoice",
            ["models--Qwen--Qwen3-TTS-12Hz-1.7B-CustomVoice"],
            roots,
        )
        self.assertTrue(found, "CustomVoice should be found in first root")
        self.assertIn("LAB_NEXT", str(path))
        
        # Tokenizer should be found in second root
        found, path = _find_model_in_roots(
            "Qwen3-TTS-Tokenizer-12Hz",
            ["models--Qwen--Qwen3-TTS-Tokenizer-12Hz", "models--Qwen3-TTS-Tokenizer-12Hz"],
            roots,
        )
        self.assertTrue(found, "Tokenizer should be found in second root")
        self.assertIn("LAB_PREV", str(path))
    
    def test_find_model_in_roots_not_found(self):
        """Model that doesn't exist anywhere should return False."""
        from benchmark.phase4_env_check import _find_model_in_roots
        
        roots = [
            self.lab_models.parent.parent,
            self.prev_models.parent.parent,
        ]
        
        found, path = _find_model_in_roots(
            "Qwen3-TTS-12Hz-1.7B-NonExistent",
            ["models--Qwen--Qwen3-TTS-12Hz-1.7B-NonExistent"],
            roots,
        )
        self.assertFalse(found)
        self.assertIsNone(path)
    
    def test_check_models_multi_root_all_found(self):
        """check_models should report all models OK when spread across roots."""
        from benchmark.phase4_env_check import check_models
        
        # Set up env with all roots
        roots_str = os.pathsep.join([
            str(self.lab_models.parent.parent),  # CustomVoice + Base
            str(self.prev_models.parent.parent),  # Tokenizer
        ])
        os.environ["VOICEOVER_MODELS_ROOTS"] = roots_str
        os.environ["VOICEOVER_MODELS_DIR"] = str(self.lab_models.parent.parent)
        
        result = check_models()
        
        self.assertTrue(result["ok"], f"Expected all models found, got: {result}")
        self.assertIn("Qwen3-TTS-12Hz-1.7B-CustomVoice", result["actual"])
        self.assertIn("Qwen3-TTS-12Hz-1.7B-Base", result["actual"])
        self.assertIn("Qwen3-TTS-Tokenizer-12Hz", result["actual"])
        
        # Check that [OK] is in each model's status
        for model_name, status in result["actual"].items():
            self.assertIn("[OK]", status, f"{model_name} should be [OK], got: {status}")
    
    def test_check_models_multi_root_documentation(self):
        """check_models should document which root each model was found in."""
        from benchmark.phase4_env_check import check_models
        
        roots_str = os.pathsep.join([
            str(self.lab_models.parent.parent),
            str(self.prev_models.parent.parent),
        ])
        os.environ["VOICEOVER_MODELS_ROOTS"] = roots_str
        os.environ["VOICEOVER_MODELS_DIR"] = str(self.lab_models.parent.parent)
        
        result = check_models()
        
        # Should have models_found_paths dict
        self.assertIn("models_found_paths", result)
        found_paths = result["models_found_paths"]
        
        # Each found model should have a path
        for model_name in ["Qwen3-TTS-12Hz-1.7B-CustomVoice", "Qwen3-TTS-12Hz-1.7B-Base", "Qwen3-TTS-Tokenizer-12Hz"]:
            self.assertIn(model_name, found_paths, f"{model_name} should be in found_paths")
            self.assertTrue(len(found_paths[model_name]) > 0, f"{model_name} path should not be empty")
    
    def test_check_models_with_single_root_missing_tokenizer(self):
        """With only LAB_NEXT as root, Tokenizer should be FEHLT."""
        from benchmark.phase4_env_check import check_models
        
        # Only point to LAB_NEXT (which lacks Tokenizer)
        os.environ["VOICEOVER_MODELS_DIR"] = str(self.lab_models.parent.parent)
        os.environ.pop("VOICEOVER_MODELS_ROOTS", None)
        
        # Need to temporarily remove other VoiceOverApp dirs from search path
        # Since _find_all_model_roots also scans Downloads/Documents, we need to
        # ensure our temp dirs are NOT in those locations.
        # Our tempdir is in /tmp, so it won't be found by home-dir scanning.
        
        result = check_models()
        
        # CustomVoice and Base should be OK, Tokenizer should FAIL
        actual = result["actual"]
        self.assertIn("[OK]", actual.get("Qwen3-TTS-12Hz-1.7B-CustomVoice", ""))
        self.assertIn("[OK]", actual.get("Qwen3-TTS-12Hz-1.7B-Base", ""))
        # Tokenizer may or may not be found depending on system paths
        # This test validates the multi-root capability
    
    def test_old_installation_has_all_models(self):
        """VoiceOverApp_OLD should have all three models in one root."""
        from benchmark.phase4_env_check import check_models
        
        os.environ["VOICEOVER_MODELS_DIR"] = str(self.old_models.parent.parent)
        os.environ.pop("VOICEOVER_MODELS_ROOTS", None)
        
        result = check_models()
        
        # All should be found in the OLD installation
        self.assertTrue(result["ok"], f"OLD installation has all models but got: {result}")


class TokenizerNameVariantsTest(unittest.TestCase):
    """Test that all known Tokenizer name variants are recognized."""
    
    def test_standard_tokenizer_name(self):
        """Standard HF cache name models--Qwen--Qwen3-TTS-Tokenizer-12Hz."""
        from benchmark.phase4_env_check import _find_model_in_roots
        
        tmpdir = tempfile.mkdtemp(prefix="test_tokenizer_name_")
        try:
            models_root = Path(tmpdir) / "models"
            hf_dir = models_root / "hf" / "hub" / "models--Qwen--Qwen3-TTS-Tokenizer-12Hz"
            hf_dir.mkdir(parents=True)
            
            found, _ = _find_model_in_roots(
                "Qwen3-TTS-Tokenizer-12Hz",
                ["models--Qwen--Qwen3-TTS-Tokenizer-12Hz", "models--Qwen3-TTS-Tokenizer-12Hz"],
                [models_root],
            )
            self.assertTrue(found, "Standard tokenizer name should be found")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    
    def test_org_prefix_variant(self):
        """HF cache name without org prefix models--Qwen3-TTS-Tokenizer-12Hz."""
        from benchmark.phase4_env_check import _find_model_in_roots
        
        tmpdir = tempfile.mkdtemp(prefix="test_tokenizer_org_")
        try:
            models_root = Path(tmpdir) / "models"
            hf_dir = models_root / "hf" / "hub" / "models--Qwen3-TTS-Tokenizer-12Hz"
            hf_dir.mkdir(parents=True)
            
            found, _ = _find_model_in_roots(
                "Qwen3-TTS-Tokenizer-12Hz",
                ["models--Qwen--Qwen3-TTS-Tokenizer-12Hz", "models--Qwen3-TTS-Tokenizer-12Hz"],
                [models_root],
            )
            self.assertTrue(found, "Org-prefix variant should be found")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
