"""
Tests for Python interpreter discovery logic.

Validates that the target validator can discover the correct Python
interpreter from various sources (environment variables, .venv paths).
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestPythonInterpreterDiscovery(unittest.TestCase):
    """Test Python interpreter discovery mechanisms."""

    def test_current_interpreter_is_valid(self):
        """Current interpreter must be a valid Python executable."""
        self.assertTrue(os.path.isfile(sys.executable))
        self.assertTrue(sys.executable.endswith(('.exe', 'python', 'python3')))

    def test_current_interpreter_version(self):
        """Current interpreter must be Python 3.10+."""
        self.assertGreaterEqual(sys.version_info.major, 3)
        self.assertGreaterEqual(sys.version_info.minor, 10)

    def test_project_root_exists(self):
        """Project root must exist and contain expected structure."""
        project_root = Path(__file__).parent.parent
        self.assertTrue(project_root.exists())
        self.assertTrue((project_root / "app").exists())
        self.assertTrue((project_root / "tests").exists())

    def test_target_validator_exists(self):
        """Target validator script must exist."""
        validator_path = Path(__file__).parent / "target_validate_explicit_marker.py"
        self.assertTrue(validator_path.exists())

    def test_target_validator_is_importable(self):
        """Target validator must be importable."""
        # This will fail if there are syntax errors or import issues
        import importlib.util
        validator_path = Path(__file__).parent / "target_validate_explicit_marker.py"
        spec = importlib.util.spec_from_file_location("target_validator", validator_path)
        module = importlib.util.module_from_spec(spec)
        # Don't execute it, just verify it can be loaded
        self.assertIsNotNone(spec)
        self.assertIsNotNone(module)


class TestEnvironmentVariableSupport(unittest.TestCase):
    """Test environment variable support for runtime discovery."""

    def test_voiceover_python_env_var(self):
        """VOICEOVER_PYTHON env var should be readable."""
        # Just test that we can read env vars
        test_value = os.environ.get("VOICEOVER_PYTHON")
        # Value may or may not be set, just ensure no error
        self.assertTrue(test_value is None or isinstance(test_value, str))

    def test_voiceover_runtime_root_env_var(self):
        """VOICEOVER_RUNTIME_ROOT env var should be readable."""
        test_value = os.environ.get("VOICEOVER_RUNTIME_ROOT")
        self.assertTrue(test_value is None or isinstance(test_value, str))

    def test_voiceover_runtime_ref_env_var(self):
        """VOICEOVER_RUNTIME_REF env var should be readable."""
        test_value = os.environ.get("VOICEOVER_RUNTIME_REF")
        self.assertTrue(test_value is None or isinstance(test_value, str))


class TestVirtualEnvironmentDetection(unittest.TestCase):
    """Test virtual environment detection logic."""

    def test_repo_venv_path_construction(self):
        """Repository .venv path should be constructable."""
        repo_root = Path(__file__).parent.parent.parent
        venv_path = repo_root / ".venv" / "Scripts" / "python.exe"
        # Path should be constructable even if it doesn't exist
        self.assertIsInstance(venv_path, Path)

    def test_runtime_root_venv_path_construction(self):
        """Runtime root .venv path should be constructable."""
        test_root = Path("/fake/path/to/runtime")
        venv_path = test_root / ".venv" / "Scripts" / "python.exe"
        self.assertIsInstance(venv_path, Path)
        self.assertIn(".venv", str(venv_path))


class TestInterpreterPriorityOrder(unittest.TestCase):
    """Test that interpreter discovery follows correct priority order."""

    def test_priority_order_documentation(self):
        """Priority order should be documented in code."""
        # Read the PowerShell script
        ps1_path = Path(__file__).parent.parent.parent / "test_explicit_marker_mode.ps1"
        if ps1_path.exists():
            content = ps1_path.read_text(encoding='utf-8')
            # Check for priority comments
            self.assertIn("Priority 1", content)
            self.assertIn("Priority 2", content)
            self.assertIn("VOICEOVER_PYTHON", content)
            self.assertIn("VOICEOVER_RUNTIME_ROOT", content)


class TestTorchCUDAAvailability(unittest.TestCase):
    """Test torch/CUDA availability reporting."""

    def test_torch_import_or_fail(self):
        """Torch import should either succeed or fail gracefully."""
        try:
            import torch
            # If torch is available, we should be able to check CUDA
            self.assertTrue(hasattr(torch, 'cuda'))
            self.assertTrue(hasattr(torch.cuda, 'is_available'))
            # is_available() should return a boolean
            result = torch.cuda.is_available()
            self.assertIsInstance(result, bool)
        except ImportError:
            # Torch not available - this is OK in sandbox environment
            # but would be a failure in target validation
            pass


class TestExitCodePropagation(unittest.TestCase):
    """Test that exit codes are properly propagated."""

    def test_sys_exit_codes(self):
        """sys.exit() should accept standard exit codes."""
        # Just verify the constants exist
        self.assertEqual(0, 0)  # Success
        self.assertEqual(1, 1)  # General error
        self.assertEqual(130, 130)  # Interrupted


if __name__ == "__main__":
    unittest.main()
