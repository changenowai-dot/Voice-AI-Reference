"""Regression tests for headless engine construction in main.py.

This test suite validates that the normal production headless path correctly
constructs the QwenTTSEngine with all required arguments, including the
critical hw (HardwareInfo) parameter.
"""
import inspect
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestHeadlessEngineConstruction(unittest.TestCase):
    """Test that _make_engine() correctly constructs engines."""

    def test_qwen_engine_signature_requires_hw(self):
        """QwenTTSEngine.__init__() must require hw as first parameter."""
        from app.tts.qwen_engine import QwenTTSEngine
        
        sig = inspect.signature(QwenTTSEngine.__init__)
        params = list(sig.parameters.keys())
        
        # First parameter after 'self' must be 'hw'
        self.assertGreater(len(params), 1,
                          "QwenTTSEngine.__init__ must have at least hw parameter")
        self.assertEqual(params[1], 'hw',
                        "First parameter of QwenTTSEngine.__init__ must be 'hw'")
        
        # hw must be required (no default value)
        hw_param = sig.parameters['hw']
        self.assertEqual(hw_param.default, inspect.Parameter.empty,
                        "hw parameter must be required (no default value)")

    def test_make_engine_passes_hw_to_qwen_engine(self):
        """_make_engine() must pass hw to QwenTTSEngine for customvoice backend."""
        from app.hardware.detector import HardwareInfo
        
        # Create a mock HardwareInfo
        mock_hw = MagicMock(spec=HardwareInfo)
        mock_hw.mode = "gpu"
        mock_hw.gpu_vram_total_gb = 8.0
        mock_hw.ram_total_gb = 16.0
        mock_hw.device_capability = (8, 6)
        mock_hw.gpu_name = "NVIDIA Test GPU"
        
        # Patch at the source location where it's imported
        # Use customvoice backend to test QwenTTSEngine path
        with patch('app.security.identity_lock.load_production', return_value={"voice_id": "uncle_fu"}):
            with patch('app.hardware.detector.detect_hardware', return_value=mock_hw):
                with patch('app.hardware.detector.recommend_model_size', return_value="1.7B"):
                    with patch('app.hardware.detector.recommend_torch_dtype', return_value="bfloat16"):
                        # Import after patching
                        from app.main import _make_engine
                        
                        # Mock QwenTTSEngine to capture constructor args
                        with patch('app.tts.qwen_engine.QwenTTSEngine') as MockEngine:
                            mock_engine_instance = MagicMock()
                            mock_engine_instance.name = "qwen3-tts-customvoice"
                            MockEngine.return_value = mock_engine_instance
                            
                            cfg = {"advanced": {}}
                            engine, hw = _make_engine("qwen", cfg)
                            
                            # Verify QwenTTSEngine was called
                            MockEngine.assert_called_once()
                            
                            # Get the actual call arguments
                            call_args = MockEngine.call_args
                            
                            # Verify hw was passed
                            # It should be passed as hw= keyword argument
                            self.assertIn('hw', call_args.kwargs,
                                        "hw must be passed to QwenTTSEngine")
                            self.assertEqual(call_args.kwargs['hw'], mock_hw,
                                           "hw must be passed correctly to QwenTTSEngine")

    def test_make_engine_with_realistic_hardware_info(self):
        """_make_engine() must work with realistic HardwareInfo object."""
        from app.hardware.detector import HardwareInfo
        
        # Create a realistic HardwareInfo similar to RTX 5060
        real_hw = HardwareInfo(
            mode="gpu",
            gpu_name="NVIDIA GeForce RTX 5060",
            gpu_vram_total_gb=7.96,
            ram_total_gb=34.3,
            cuda_available=True,
            device_capability=(8, 6),
            torch_version="2.11.0+cu128"
        )
        
        # Use customvoice backend to test QwenTTSEngine path
        with patch('app.security.identity_lock.load_production', return_value={"voice_id": "uncle_fu"}):
            with patch('app.hardware.detector.detect_hardware', return_value=real_hw):
                with patch('app.hardware.detector.recommend_model_size', return_value="1.7B"):
                    with patch('app.hardware.detector.recommend_torch_dtype', return_value="bfloat16"):
                        from app.main import _make_engine
                        
                        with patch('app.tts.qwen_engine.QwenTTSEngine') as MockEngine:
                            mock_engine_instance = MagicMock()
                            mock_engine_instance.name = "qwen3-tts-customvoice"
                            MockEngine.return_value = mock_engine_instance
                            
                            cfg = {"advanced": {}}
                            engine, hw = _make_engine("qwen", cfg)
                            
                            # Verify engine was created
                            self.assertIsNotNone(engine)
                            self.assertEqual(hw, real_hw)
                            
                            # Verify QwenTTSEngine was called with hw
                            MockEngine.assert_called_once()
                            call_kwargs = MockEngine.call_args.kwargs
                            self.assertIn('hw', call_kwargs)
                            self.assertEqual(call_kwargs['hw'], real_hw)

    def test_make_engine_respects_runtime_model_root(self):
        """_make_engine() must use VOICEOVER_RUNTIME_ROOT if set."""
        from app.hardware.detector import HardwareInfo
        
        mock_hw = MagicMock(spec=HardwareInfo)
        mock_hw.mode = "gpu"
        
        # Set VOICEOVER_RUNTIME_ROOT
        test_runtime_root = r"C:\Test\Runtime\Root"
        
        # Use customvoice backend to test QwenTTSEngine path
        with patch('app.security.identity_lock.load_production', return_value={"voice_id": "uncle_fu"}):
            with patch('app.hardware.detector.detect_hardware', return_value=mock_hw):
                with patch('app.hardware.detector.recommend_model_size', return_value="1.7B"):
                    with patch('app.hardware.detector.recommend_torch_dtype', return_value="bfloat16"):
                        from app.main import _make_engine
                        
                        with patch('app.tts.qwen_engine.QwenTTSEngine') as MockEngine:
                            mock_engine_instance = MagicMock()
                            MockEngine.return_value = mock_engine_instance
                            
                            # Set environment variable
                            old_env = os.environ.get('VOICEOVER_RUNTIME_ROOT')
                            try:
                                os.environ['VOICEOVER_RUNTIME_ROOT'] = test_runtime_root
                                
                                cfg = {"advanced": {}}
                                engine, hw = _make_engine("qwen", cfg)
                                
                                # Verify models_dir was passed correctly
                                call_kwargs = MockEngine.call_args.kwargs
                                self.assertIn('models_dir', call_kwargs)
                                
                                expected_models_dir = Path(test_runtime_root) / "models"
                                self.assertEqual(call_kwargs['models_dir'], expected_models_dir,
                                               "models_dir must be derived from VOICEOVER_RUNTIME_ROOT")
                            finally:
                                # Restore environment
                                if old_env is not None:
                                    os.environ['VOICEOVER_RUNTIME_ROOT'] = old_env
                                else:
                                    os.environ.pop('VOICEOVER_RUNTIME_ROOT', None)

    def test_make_engine_uses_default_models_dir_without_runtime_root(self):
        """_make_engine() must use None for models_dir when no runtime root is set."""
        from app.hardware.detector import HardwareInfo
        
        mock_hw = MagicMock(spec=HardwareInfo)
        mock_hw.mode = "gpu"
        
        # Use customvoice backend to test QwenTTSEngine path
        with patch('app.security.identity_lock.load_production', return_value={"voice_id": "uncle_fu"}):
            with patch('app.hardware.detector.detect_hardware', return_value=mock_hw):
                with patch('app.hardware.detector.recommend_model_size', return_value="1.7B"):
                    with patch('app.hardware.detector.recommend_torch_dtype', return_value="bfloat16"):
                        from app.main import _make_engine
                        
                        with patch('app.tts.qwen_engine.QwenTTSEngine') as MockEngine:
                            mock_engine_instance = MagicMock()
                            MockEngine.return_value = mock_engine_instance
                            
                            # Ensure no runtime root is set
                            old_env = os.environ.get('VOICEOVER_RUNTIME_ROOT')
                            try:
                                os.environ.pop('VOICEOVER_RUNTIME_ROOT', None)
                                
                                cfg = {"advanced": {}}
                                engine, hw = _make_engine("qwen", cfg)
                                
                                # Verify models_dir is None (use default)
                                call_kwargs = MockEngine.call_args.kwargs
                                self.assertIn('models_dir', call_kwargs)
                                self.assertIsNone(call_kwargs['models_dir'],
                                                "models_dir must be None when VOICEOVER_RUNTIME_ROOT is not set")
                            finally:
                                if old_env is not None:
                                    os.environ['VOICEOVER_RUNTIME_ROOT'] = old_env


class TestHeadlessEngineIntegration(unittest.TestCase):
    """Integration tests for headless engine construction."""

    def test_target_validator_and_headless_use_same_pattern(self):
        """Target validator and headless path must use same hw passing pattern."""
        # Read target validator
        validator_path = project_root / "tests" / "target_validate_explicit_marker.py"
        validator_source = validator_path.read_text(encoding="utf-8")
        
        # Read main.py
        main_path = project_root / "app" / "main.py"
        main_source = main_path.read_text(encoding="utf-8")
        
        # Both must pass hw to engine constructors
        # Target validator passes hw to VoiceCloneEngine
        self.assertIn("hw=hw", validator_source,
                     "Target validator must pass hw to engine")
        
        # main.py must pass hw to QwenTTSEngine
        self.assertIn("hw=hw", main_source,
                     "main.py must pass hw to engine")

    def test_headless_path_does_not_hardcode_lab_paths(self):
        """Headless path must not hardcode personal LAB paths."""
        main_path = project_root / "app" / "main.py"
        main_source = main_path.read_text(encoding="utf-8")
        
        # Should not contain hardcoded user paths
        self.assertNotIn(r"C:\Users\johan", main_source,
                        "main.py must not contain hardcoded user paths")
        self.assertNotIn(r"C:\Users\YourName", main_source,
                        "main.py must not contain hardcoded user paths")
        
        # Should use environment variables instead
        self.assertIn("os.environ", main_source,
                     "main.py should use environment variables")


class TestProtectedStateUnchanged(unittest.TestCase):
    """Verify protected state remains unchanged."""

    def test_golden_reference_sha_unchanged(self):
        """Golden Reference SHA must remain unchanged."""
        from app.security.identity_lock import load_production
        
        config = load_production()
        expected_sha = "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025"
        
        self.assertEqual(config["reference_sha256"], expected_sha,
                        "Golden Reference SHA must not be changed")

    def test_identity_lock_unchanged(self):
        """identity_lock.py must contain expected functions."""
        # Verify identity_lock.py exists and contains expected functions
        identity_lock_path = project_root / "app" / "security" / "identity_lock.py"
        
        # Just verify the file exists and contains expected functions
        self.assertTrue(identity_lock_path.exists())
        
        source = identity_lock_path.read_text(encoding="utf-8")
        self.assertIn("def check_identity", source)
        self.assertIn("def load_production", source)

    def test_production_json_unchanged(self):
        """production.json must not be modified."""
        # Verify production.json exists and has expected structure
        config_path = project_root / "config" / "production.json"
        self.assertTrue(config_path.exists())
        
        from app.security.identity_lock import load_production
        config = load_production()
        
        # Must have reference_sha256
        self.assertIn("reference_sha256", config)


class TestEngineSelectionByBackendMode(unittest.TestCase):
    """Test that _make_engine() creates the correct engine based on backend_mode."""

    def test_vd_e_creates_voice_clone_engine(self):
        """voice_id=vd_e must create VoiceCloneEngine, not QwenTTSEngine."""
        from app.main import _make_engine
        from app.hardware.detector import HardwareInfo
        
        mock_hw = MagicMock(spec=HardwareInfo)
        mock_hw.mode = "gpu"
        
        with patch('app.hardware.detector.detect_hardware', return_value=mock_hw):
            with patch('app.security.identity_lock.assert_vd_e_usable'):
                with patch('app.security.identity_lock.check_identity') as mock_check:
                    mock_check.return_value = MagicMock(ok=True, path="/fake/path/VD-E.wav")
                    with patch('app.tts.qwen_engine.VoiceCloneEngine') as MockEngine:
                        mock_engine_instance = MagicMock()
                        mock_engine_instance.name = "qwen3-tts-clone"
                        MockEngine.return_value = mock_engine_instance
                        
                        cfg = {"advanced": {}}
                        engine, hw = _make_engine("qwen", cfg)
                        
                        # Verify VoiceCloneEngine was created
                        MockEngine.assert_called_once()
                        
                        # Verify correct parameters
                        call_kwargs = MockEngine.call_args.kwargs
                        self.assertEqual(call_kwargs['candidate_id'], "VD-E")
                        self.assertEqual(call_kwargs['allow_design'], False)
                        self.assertEqual(call_kwargs['hw'], mock_hw)

    def test_customvoice_creates_qwen_tts_engine(self):
        """voice_id=uncle_fu (customvoice) must create QwenTTSEngine."""
        from app.main import _make_engine
        from app.hardware.detector import HardwareInfo
        
        mock_hw = MagicMock(spec=HardwareInfo)
        mock_hw.mode = "gpu"
        
        # Temporarily change production config to use uncle_fu
        with patch('app.security.identity_lock.load_production', return_value={"voice_id": "uncle_fu"}):
            with patch('app.hardware.detector.detect_hardware', return_value=mock_hw):
                with patch('app.hardware.detector.recommend_model_size', return_value="1.7B"):
                    with patch('app.hardware.detector.recommend_torch_dtype', return_value="bfloat16"):
                        with patch('app.tts.qwen_engine.QwenTTSEngine') as MockEngine:
                            mock_engine_instance = MagicMock()
                            mock_engine_instance.name = "qwen3-tts-customvoice"
                            MockEngine.return_value = mock_engine_instance
                            
                            cfg = {"advanced": {}}
                            engine, hw = _make_engine("qwen", cfg)
                            
                            # Verify QwenTTSEngine was created
                            MockEngine.assert_called_once()

    def test_vd_e_uses_base_model_not_customvoice(self):
        """VD-E must use Base model, not CustomVoice model."""
        from app.main import _make_engine
        from app.hardware.detector import HardwareInfo
        
        mock_hw = MagicMock(spec=HardwareInfo)
        mock_hw.mode = "gpu"
        
        with patch('app.hardware.detector.detect_hardware', return_value=mock_hw):
            with patch('app.security.identity_lock.assert_vd_e_usable'):
                with patch('app.security.identity_lock.check_identity') as mock_check:
                    mock_check.return_value = MagicMock(ok=True, path="/fake/path/VD-E.wav")
                    with patch('app.tts.qwen_engine.VoiceCloneEngine') as MockEngine:
                        mock_engine_instance = MagicMock()
                        MockEngine.return_value = mock_engine_instance
                        
                        cfg = {"advanced": {}}
                        engine, hw = _make_engine("qwen", cfg)
                        
                        # Verify candidate_id is VD-E (uses Base model)
                        call_kwargs = MockEngine.call_args.kwargs
                        self.assertEqual(call_kwargs['candidate_id'], "VD-E")
                        
                        # Verify it's NOT using CustomVoice parameters
                        self.assertNotIn('model_size', call_kwargs)

    def test_runtime_reference_passed_to_voice_clone_engine(self):
        """VOICEOVER_RUNTIME_REF must be passed to VoiceCloneEngine."""
        from app.main import _make_engine
        from app.hardware.detector import HardwareInfo
        
        mock_hw = MagicMock(spec=HardwareInfo)
        mock_hw.mode = "gpu"
        
        test_ref_path = r"C:\Test\Runtime\VD-E.wav"
        
        with patch('app.hardware.detector.detect_hardware', return_value=mock_hw):
            with patch('app.security.identity_lock.assert_vd_e_usable'):
                with patch('app.security.identity_lock.check_identity') as mock_check:
                    mock_check.return_value = MagicMock(ok=True, path="/fallback/path")
                    with patch('app.tts.qwen_engine.VoiceCloneEngine') as MockEngine:
                        mock_engine_instance = MagicMock()
                        MockEngine.return_value = mock_engine_instance
                        
                        old_env = os.environ.get('VOICEOVER_RUNTIME_REF')
                        try:
                            os.environ['VOICEOVER_RUNTIME_REF'] = test_ref_path
                            
                            cfg = {"advanced": {}}
                            engine, hw = _make_engine("qwen", cfg)
                            
                            call_kwargs = MockEngine.call_args.kwargs
                            self.assertEqual(call_kwargs['reference_path'], Path(test_ref_path))
                        finally:
                            if old_env is not None:
                                os.environ['VOICEOVER_RUNTIME_REF'] = old_env
                            else:
                                os.environ.pop('VOICEOVER_RUNTIME_REF', None)

    def test_no_customvoice_engine_for_vd_e(self):
        """VD-E configuration must NOT create QwenTTSEngine."""
        from app.main import _make_engine
        from app.hardware.detector import HardwareInfo
        
        mock_hw = MagicMock(spec=HardwareInfo)
        mock_hw.mode = "gpu"
        
        with patch('app.hardware.detector.detect_hardware', return_value=mock_hw):
            with patch('app.security.identity_lock.assert_vd_e_usable'):
                with patch('app.security.identity_lock.check_identity') as mock_check:
                    mock_check.return_value = MagicMock(ok=True, path="/fake/path")
                    with patch('app.tts.qwen_engine.VoiceCloneEngine') as MockClone:
                        with patch('app.tts.qwen_engine.QwenTTSEngine') as MockCustom:
                            mock_engine_instance = MagicMock()
                            MockClone.return_value = mock_engine_instance
                            
                            cfg = {"advanced": {}}
                            engine, hw = _make_engine("qwen", cfg)
                            
                            # VoiceCloneEngine should be called
                            MockClone.assert_called_once()
                            # QwenTTSEngine should NOT be called for VD-E
                            MockCustom.assert_not_called()


if __name__ == "__main__":
    unittest.main()
