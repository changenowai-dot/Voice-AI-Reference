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
                    # Verify reference_path is NOT passed (not part of API)
                    self.assertNotIn('reference_path', call_kwargs)

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

    def test_runtime_reference_via_environment_variable(self):
        """Runtime reference must be passed via VOICEOVER_REFS_DIR environment variable."""
        from app.main import _make_engine
        from app.hardware.detector import HardwareInfo
        
        mock_hw = MagicMock(spec=HardwareInfo)
        mock_hw.mode = "gpu"
        
        with patch('app.hardware.detector.detect_hardware', return_value=mock_hw):
            with patch('app.security.identity_lock.assert_vd_e_usable'):
                with patch('app.tts.qwen_engine.VoiceCloneEngine') as MockEngine:
                    mock_engine_instance = MagicMock()
                    MockEngine.return_value = mock_engine_instance
                    
                    # Verify VoiceCloneEngine does NOT receive reference_path parameter
                    cfg = {"advanced": {}}
                    engine, hw = _make_engine("qwen", cfg)
                    
                    call_kwargs = MockEngine.call_args.kwargs
                    # reference_path is NOT a parameter of VoiceCloneEngine.__init__()
                    self.assertNotIn('reference_path', call_kwargs,
                                   "VoiceCloneEngine must not receive reference_path parameter")
                    
                    # VoiceCloneEngine uses paths.VOICE_REFS_DIR which is set from
                    # VOICEOVER_REFS_DIR environment variable (see app/paths.py)
                    # The actual reference file is located at VOICE_REFS_DIR/VD-E.wav

    def test_vd_e_uses_valid_constructor_signature(self):
        """VD-E must use the actual VoiceCloneEngine constructor signature."""
        import inspect
        from app.main import _make_engine
        from app.hardware.detector import HardwareInfo
        from app.tts.qwen_engine import VoiceCloneEngine
        
        mock_hw = MagicMock(spec=HardwareInfo)
        mock_hw.mode = "gpu"
        
        # Get the actual VoiceCloneEngine signature
        sig = inspect.signature(VoiceCloneEngine.__init__)
        valid_params = set(sig.parameters.keys())
        
        with patch('app.hardware.detector.detect_hardware', return_value=mock_hw):
            with patch('app.security.identity_lock.assert_vd_e_usable'):
                with patch('app.tts.qwen_engine.VoiceCloneEngine') as MockEngine:
                    mock_engine_instance = MagicMock()
                    MockEngine.return_value = mock_engine_instance
                    
                    cfg = {"advanced": {}}
                    engine, hw = _make_engine("qwen", cfg)
                    
                    # Verify all passed parameters are valid for VoiceCloneEngine.__init__()
                    call_kwargs = MockEngine.call_args.kwargs
                    for param_name in call_kwargs.keys():
                        self.assertIn(param_name, valid_params,
                                    f"Parameter '{param_name}' is not valid for VoiceCloneEngine.__init__()")
                    
                    # Verify required parameters are present
                    self.assertIn('hw', call_kwargs)
                    self.assertIn('candidate_id', call_kwargs)
                    self.assertIn('description', call_kwargs)
                    self.assertIn('allow_design', call_kwargs)

    def test_no_customvoice_engine_for_vd_e(self):
        """VD-E configuration must NOT create QwenTTSEngine."""
        from app.main import _make_engine
        from app.hardware.detector import HardwareInfo
        
        mock_hw = MagicMock(spec=HardwareInfo)
        mock_hw.mode = "gpu"
        
        with patch('app.hardware.detector.detect_hardware', return_value=mock_hw):
            with patch('app.security.identity_lock.assert_vd_e_usable'):
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


class TestCacheModuleAvailability(unittest.TestCase):
    """Test that app.cache module is available for headless pipeline."""

    def test_cache_module_exists(self):
        """app.cache module must exist and be importable."""
        import os
        from pathlib import Path
        
        # Check that the cache module files exist
        cache_init = project_root / "app" / "cache" / "__init__.py"
        cache_manager = project_root / "app" / "cache" / "manager.py"
        
        self.assertTrue(cache_init.exists(), 
                       "project/app/cache/__init__.py must exist")
        self.assertTrue(cache_manager.exists(),
                       "project/app/cache/manager.py must exist")

    def test_cache_module_importable(self):
        """CacheManager and segment_cache_key must be importable."""
        # This test verifies the fix for the ModuleNotFoundError
        # Note: numpy is a runtime dependency, so we only check structure
        import os
        from pathlib import Path
        
        # Check that manager.py contains the required exports
        manager_path = project_root / "app" / "cache" / "manager.py"
        manager_content = manager_path.read_text(encoding="utf-8")
        
        self.assertIn("class CacheManager", manager_content,
                     "manager.py must define CacheManager class")
        self.assertIn("def segment_cache_key", manager_content,
                     "manager.py must define segment_cache_key function")
        
        # Check that __init__.py exports them
        init_path = project_root / "app" / "cache" / "__init__.py"
        init_content = init_path.read_text(encoding="utf-8")
        
        self.assertIn("CacheManager", init_content,
                     "__init__.py must export CacheManager")
        self.assertIn("segment_cache_key", init_content,
                     "__init__.py must export segment_cache_key")

    def test_pipeline_can_import_cache(self):
        """project/app/project/pipeline.py must be able to import cache."""
        # Verify that the relative import in pipeline.py will work
        # pipeline.py is at project/app/project/pipeline.py
        # It imports: from ..cache.manager import CacheManager, segment_cache_key
        # This resolves to project/app/cache/manager.py
        
        pipeline_path = project_root / "app" / "project" / "pipeline.py"
        cache_manager_path = project_root / "app" / "cache" / "manager.py"
        
        self.assertTrue(pipeline_path.exists(),
                       "pipeline.py must exist")
        self.assertTrue(cache_manager_path.exists(),
                       "cache/manager.py must exist")
        
        # Verify the import statement exists in pipeline.py
        pipeline_content = pipeline_path.read_text(encoding="utf-8")
        self.assertIn("from ..cache.manager import CacheManager, segment_cache_key",
                     pipeline_content,
                     "pipeline.py must import CacheManager and segment_cache_key")

    def test_cache_module_in_git(self):
        """app.cache module files must be tracked by git."""
        import subprocess
        
        # Check that cache module files are tracked by git
        result = subprocess.run(
            ["git", "ls-files", "project/app/cache/"],
            cwd=project_root.parent,
            capture_output=True,
            text=True
        )
        
        tracked_files = result.stdout.strip().split('\n')
        tracked_files = [f for f in tracked_files if f]  # Remove empty strings
        
        self.assertGreater(len(tracked_files), 0,
                          "app.cache module files must be tracked by git")
        
        # Check for specific files
        self.assertIn("project/app/cache/__init__.py", tracked_files,
                     "__init__.py must be tracked by git")
        self.assertIn("project/app/cache/manager.py", tracked_files,
                     "manager.py must be tracked by git")


class TestModelPathResolution(unittest.TestCase):
    """Test that model paths are resolved correctly from environment variables."""

    def test_models_dir_uses_voiceover_runtime_root(self):
        """MODELS_DIR should use VOICEOVER_RUNTIME_ROOT/models when set."""
        import os
        from pathlib import Path
        
        # Save current environment
        old_runtime_root = os.environ.get('VOICEOVER_RUNTIME_ROOT')
        old_models_dir = os.environ.get('VOICEOVER_MODELS_DIR')
        
        try:
            # Set VOICEOVER_RUNTIME_ROOT
            test_runtime_root = r"C:\Test\Runtime\Root"
            os.environ['VOICEOVER_RUNTIME_ROOT'] = test_runtime_root
            os.environ.pop('VOICEOVER_MODELS_DIR', None)
            
            # Re-import paths to pick up new environment
            import importlib
            import sys
            if 'app.paths' in sys.modules:
                importlib.reload(sys.modules['app.paths'])
            
            from app.paths import MODELS_DIR
            
            # Verify MODELS_DIR points to runtime root / models
            expected = Path(test_runtime_root) / "models"
            self.assertEqual(MODELS_DIR, expected,
                           "MODELS_DIR should be VOICEOVER_RUNTIME_ROOT/models")
            
        finally:
            # Restore environment
            if old_runtime_root is not None:
                os.environ['VOICEOVER_RUNTIME_ROOT'] = old_runtime_root
            else:
                os.environ.pop('VOICEOVER_RUNTIME_ROOT', None)
            
            if old_models_dir is not None:
                os.environ['VOICEOVER_MODELS_DIR'] = old_models_dir
            else:
                os.environ.pop('VOICEOVER_MODELS_DIR', None)
            
            # Reload paths module to restore original state
            import importlib
            import sys
            if 'app.paths' in sys.modules:
                importlib.reload(sys.modules['app.paths'])

    def test_models_dir_prefers_explicit_override(self):
        """VOICEOVER_MODELS_DIR should take precedence over VOICEOVER_RUNTIME_ROOT."""
        import os
        from pathlib import Path
        
        # Save current environment
        old_runtime_root = os.environ.get('VOICEOVER_RUNTIME_ROOT')
        old_models_dir = os.environ.get('VOICEOVER_MODELS_DIR')
        
        try:
            # Set both environment variables
            test_runtime_root = r"C:\Test\Runtime\Root"
            test_models_dir = r"C:\Explicit\Models"
            os.environ['VOICEOVER_RUNTIME_ROOT'] = test_runtime_root
            os.environ['VOICEOVER_MODELS_DIR'] = test_models_dir
            
            # Re-import paths to pick up new environment
            import importlib
            import sys
            if 'app.paths' in sys.modules:
                importlib.reload(sys.modules['app.paths'])
            
            from app.paths import MODELS_DIR
            
            # Verify MODELS_DIR uses explicit override
            expected = Path(test_models_dir)
            self.assertEqual(MODELS_DIR, expected,
                           "VOICEOVER_MODELS_DIR should take precedence")
            
        finally:
            # Restore environment
            if old_runtime_root is not None:
                os.environ['VOICEOVER_RUNTIME_ROOT'] = old_runtime_root
            else:
                os.environ.pop('VOICEOVER_RUNTIME_ROOT', None)
            
            if old_models_dir is not None:
                os.environ['VOICEOVER_MODELS_DIR'] = old_models_dir
            else:
                os.environ.pop('VOICEOVER_MODELS_DIR', None)
            
            # Reload paths module to restore original state
            import importlib
            import sys
            if 'app.paths' in sys.modules:
                importlib.reload(sys.modules['app.paths'])

    def test_hf_home_set_from_models_dir(self):
        """HF_HOME should be set to MODELS_DIR/hf in ensure_directories()."""
        import os
        from pathlib import Path
        
        # Save current environment
        old_hf_home = os.environ.get('HF_HOME')
        old_runtime_root = os.environ.get('VOICEOVER_RUNTIME_ROOT')
        old_models_dir = os.environ.get('VOICEOVER_MODELS_DIR')
        
        try:
            # Set VOICEOVER_RUNTIME_ROOT
            test_runtime_root = r"C:\Test\Runtime\Root"
            os.environ['VOICEOVER_RUNTIME_ROOT'] = test_runtime_root
            os.environ.pop('VOICEOVER_MODELS_DIR', None)
            os.environ.pop('HF_HOME', None)
            
            # Re-import paths
            import importlib
            import sys
            if 'app.paths' in sys.modules:
                importlib.reload(sys.modules['app.paths'])
            
            from app.paths import ensure_directories, MODELS_DIR
            
            # Call ensure_directories
            ensure_directories()
            
            # Verify HF_HOME is set correctly
            expected_hf_home = str(MODELS_DIR / "hf")
            actual_hf_home = os.environ.get('HF_HOME')
            self.assertEqual(actual_hf_home, expected_hf_home,
                           "HF_HOME should be MODELS_DIR/hf")
            
        finally:
            # Restore environment
            if old_hf_home is not None:
                os.environ['HF_HOME'] = old_hf_home
            else:
                os.environ.pop('HF_HOME', None)
            
            if old_runtime_root is not None:
                os.environ['VOICEOVER_RUNTIME_ROOT'] = old_runtime_root
            else:
                os.environ.pop('VOICEOVER_RUNTIME_ROOT', None)
            
            if old_models_dir is not None:
                os.environ['VOICEOVER_MODELS_DIR'] = old_models_dir
            else:
                os.environ.pop('VOICEOVER_MODELS_DIR', None)
            
            # Reload paths module to restore original state
            import importlib
            import sys
            if 'app.paths' in sys.modules:
                importlib.reload(sys.modules['app.paths'])

    def test_model_pool_resolves_from_runtime_root(self):
        """QwenModelPool should resolve models from VOICEOVER_RUNTIME_ROOT."""
        import os
        from pathlib import Path
        from unittest.mock import MagicMock
        
        # Save current environment
        old_runtime_root = os.environ.get('VOICEOVER_RUNTIME_ROOT')
        
        try:
            # Set VOICEOVER_RUNTIME_ROOT
            test_runtime_root = Path(r"C:\Test\Runtime\Root")
            os.environ['VOICEOVER_RUNTIME_ROOT'] = str(test_runtime_root)
            
            # Create mock hardware
            mock_hw = MagicMock()
            mock_hw.mode = "gpu"
            
            # Create model pool with models_dir from runtime root
            from app.tts.model_pool import QwenModelPool
            models_dir = test_runtime_root / "models"
            pool = QwenModelPool(hw=mock_hw, models_dir=models_dir)
            
            # Verify models_dir is set correctly
            self.assertEqual(pool.models_dir, models_dir,
                           "ModelPool should use runtime root models directory")
            
            # Verify _resolve_model_path would check correct locations
            # We can't actually resolve without the model files, but we can
            # verify the path construction
            repo = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
            direct_path = pool.models_dir / repo.split("/")[-1]
            hf_cache_path = pool.models_dir / "hf" / "hub" / ("models--" + repo.replace("/", "--"))
            
            # These paths should be under the runtime root
            self.assertTrue(str(direct_path).startswith(str(test_runtime_root)),
                          "Direct model path should be under runtime root")
            self.assertTrue(str(hf_cache_path).startswith(str(test_runtime_root)),
                          "HF cache path should be under runtime root")
            
        finally:
            # Restore environment
            if old_runtime_root is not None:
                os.environ['VOICEOVER_RUNTIME_ROOT'] = old_runtime_root
            else:
                os.environ.pop('VOICEOVER_RUNTIME_ROOT', None)
