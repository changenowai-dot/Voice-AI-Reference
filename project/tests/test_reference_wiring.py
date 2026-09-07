#!/usr/bin/env python3
"""
Regression test for target validator runtime reference wiring fix.

This test validates that:
1. VoiceCloneEngine accepts a reference_path parameter
2. When reference_path is provided, it uses that path instead of the default
3. When reference_path is None, it falls back to the default behavior
4. The target validator correctly passes the runtime reference to the engine
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestVoiceCloneEngineReferenceWiring(unittest.TestCase):
    """Test that VoiceCloneEngine correctly handles reference_path parameter."""

    def test_engine_accepts_reference_path_parameter(self):
        """VoiceCloneEngine.__init__ should accept reference_path parameter."""
        from app.tts.qwen_engine import VoiceCloneEngine
        from app.hardware.detector import HardwareInfo

        # Create a mock hardware info
        hw = MagicMock(spec=HardwareInfo)
        hw.mode = "cpu"
        hw.gpu_name = "Test GPU"

        # Test that we can create engine with reference_path parameter
        with tempfile.TemporaryDirectory() as tmpdir:
            ref_path = Path(tmpdir) / "test_reference.wav"
            ref_path.write_bytes(b"fake wav data")

            # This should not raise an error
            engine = VoiceCloneEngine(
                hw=hw,
                candidate_id="TEST",
                description="test description",
                reference_path=ref_path,
            )

            # Verify the parameter was stored
            self.assertEqual(engine.reference_path, ref_path)

    def test_engine_reference_path_none_uses_default(self):
        """When reference_path is None, engine should use default path."""
        from app.tts.qwen_engine import VoiceCloneEngine
        from app.hardware.detector import HardwareInfo

        hw = MagicMock(spec=HardwareInfo)
        hw.mode = "cpu"
        hw.gpu_name = "Test GPU"

        engine = VoiceCloneEngine(
            hw=hw,
            candidate_id="TEST",
            description="test description",
            reference_path=None,
        )

        self.assertIsNone(engine.reference_path)

    def test_engine_reference_path_default_parameter(self):
        """reference_path should default to None for backward compatibility."""
        from app.tts.qwen_engine import VoiceCloneEngine
        from app.hardware.detector import HardwareInfo

        hw = MagicMock(spec=HardwareInfo)
        hw.mode = "cpu"
        hw.gpu_name = "Test GPU"

        # Create engine without reference_path parameter
        engine = VoiceCloneEngine(
            hw=hw,
            candidate_id="TEST",
            description="test description",
        )

        # Should default to None
        self.assertIsNone(engine.reference_path)

    def test_target_validator_passes_runtime_reference(self):
        """Target validator should pass runtime reference to engine."""
        # Read the target validator source code
        validator_path = project_root / "tests" / "target_validate_explicit_marker.py"
        source = validator_path.read_text(encoding="utf-8")

        # Verify the wiring is present
        self.assertIn("identity_status = check_identity()", source)
        self.assertIn("runtime_ref_path = Path(identity_status.path)", source)
        self.assertIn("reference_path=runtime_ref_path", source)

    def test_engine_ensure_prompt_uses_reference_path(self):
        """_ensure_prompt should use reference_path when provided."""
        from app.tts.qwen_engine import VoiceCloneEngine

        # Read the source code to verify the logic
        engine_path = project_root / "app" / "tts" / "qwen_engine.py"
        source = engine_path.read_text(encoding="utf-8")

        # Verify the conditional logic exists
        self.assertIn("if self.reference_path is not None:", source)
        self.assertIn("ref_path = Path(self.reference_path)", source)


class TestReferenceWiringIntegration(unittest.TestCase):
    """Integration test for the complete reference wiring flow."""

    def test_identity_lock_and_engine_use_same_path(self):
        """Both identity lock and engine should use VOICEOVER_RUNTIME_REF."""
        import os

        # Read both source files
        identity_lock_path = project_root / "app" / "security" / "identity_lock.py"
        identity_source = identity_lock_path.read_text(encoding="utf-8")

        engine_path = project_root / "app" / "tts" / "qwen_engine.py"
        engine_source = engine_path.read_text(encoding="utf-8")

        # Verify identity lock respects VOICEOVER_RUNTIME_REF
        self.assertIn("VOICEOVER_RUNTIME_REF", identity_source)
        self.assertIn("_resolve_reference_path", identity_source)

        # Verify engine accepts reference_path
        self.assertIn("reference_path", engine_source)

        # Verify target validator wires them together
        validator_path = project_root / "tests" / "target_validate_explicit_marker.py"
        validator_source = validator_path.read_text(encoding="utf-8")

        self.assertIn("check_identity()", validator_source)
        self.assertIn("reference_path=runtime_ref_path", validator_source)


if __name__ == "__main__":
    unittest.main()
