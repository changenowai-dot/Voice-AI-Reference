"""
Regression test for HardwareInfo API usage in target validator.

This test ensures that target_validate_explicit_marker.py uses the correct
HardwareInfo field names and doesn't reference removed fields.

Related to commit f3762cb which fixed HardwareInfo API mismatches.
"""
import ast
import unittest
from pathlib import Path


class TestTargetValidatorHardwareAPI(unittest.TestCase):
    """Test that target validator uses correct HardwareInfo API."""

    def setUp(self):
        """Load the target validator script."""
        self.validator_path = Path(__file__).parent / "target_validate_explicit_marker.py"
        self.assertTrue(self.validator_path.exists(), 
                       f"Target validator not found: {self.validator_path}")
        
        with open(self.validator_path, 'r', encoding='utf-8') as f:
            self.source = f.read()
        
        # Parse the AST
        self.tree = ast.parse(self.source)

    def test_no_vram_gb_field(self):
        """Target validator must not use hw.vram_gb (removed field)."""
        # Check for attribute access patterns
        self.assertNotIn('vram_gb', self.source,
                        "Target validator uses 'vram_gb' which doesn't exist in HardwareInfo. "
                        "Use 'gpu_vram_total_gb' instead.")

    def test_no_ram_gb_field(self):
        """Target validator must not use hw.ram_gb (removed field)."""
        self.assertNotIn('ram_gb', self.source,
                        "Target validator uses 'ram_gb' which doesn't exist in HardwareInfo. "
                        "Use 'ram_total_gb' instead.")

    def test_no_device_name_field(self):
        """Target validator must not use hw.device_name (removed field)."""
        # Check for hw.device_name specifically (not torch.cuda.get_device_name)
        self.assertNotIn('hw.device_name', self.source,
                        "Target validator uses 'hw.device_name' which doesn't exist in HardwareInfo. "
                        "Use 'hw.gpu_name' instead.")

    def test_uses_gpu_vram_total_gb(self):
        """Target validator should use hw.gpu_vram_total_gb."""
        # Check that the correct field is used
        self.assertIn('gpu_vram_total_gb', self.source,
                     "Target validator should use 'gpu_vram_total_gb' for VRAM")

    def test_uses_ram_total_gb(self):
        """Target validator should use hw.ram_total_gb."""
        self.assertIn('ram_total_gb', self.source,
                     "Target validator should use 'ram_total_gb' for system RAM")

    def test_uses_gpu_name(self):
        """Target validator should use hw.gpu_name."""
        self.assertIn('gpu_name', self.source,
                     "Target validator should use 'gpu_name' for GPU name")

    def test_no_emoji_characters(self):
        """Target validator must not use emoji (causes Windows encoding errors)."""
        # Check for common emoji that cause cp1252 encoding errors
        forbidden_emoji = ['❌', '✅', '⚠️', '✓', '🔥', '🎉', '💥', '🚀']
        
        for emoji in forbidden_emoji:
            self.assertNotIn(emoji, self.source,
                           f"Target validator contains emoji '{emoji}' which causes "
                           "UnicodeEncodeError on Windows cp1252. Use ASCII equivalents "
                           "like [OK], [FAIL], [WARN] instead.")

    def test_uses_ascii_status_markers(self):
        """Target validator should use ASCII status markers."""
        # Check that ASCII markers are used
        ascii_markers = ['[OK]', '[FAIL]', '[WARN]', '[INFO]']
        
        found_markers = [marker for marker in ascii_markers if marker in self.source]
        self.assertGreater(len(found_markers), 0,
                         "Target validator should use ASCII status markers like [OK], [FAIL], [WARN]")

    def test_detect_hardware_call(self):
        """Target validator should call detect_hardware()."""
        self.assertIn('detect_hardware()', self.source,
                     "Target validator should call detect_hardware()")

    def test_imports_detect_hardware(self):
        """Target validator should import detect_hardware."""
        self.assertIn('from app.hardware.detector import detect_hardware', self.source,
                     "Target validator should import detect_hardware from app.hardware.detector")

    def test_imports_check_identity(self):
        """Target validator should import check_identity."""
        self.assertIn('from app.security.identity_lock import check_identity', self.source,
                     "Target validator should import check_identity from app.security.identity_lock")

    def test_validates_environment(self):
        """Target validator should validate environment (torch, CUDA, etc.)."""
        self.assertIn('validate_environment', self.source,
                     "Target validator should have a validate_environment function")
        
        # Check that it validates torch
        self.assertIn('import torch', self.source,
                     "Target validator should import torch for environment validation")

    def test_checks_cuda_availability(self):
        """Target validator should check CUDA availability."""
        self.assertIn('torch.cuda.is_available()', self.source,
                     "Target validator should check torch.cuda.is_available()")

    def test_checks_qwen_tts(self):
        """Target validator should check qwen-tts availability."""
        self.assertIn('import qwen_tts', self.source,
                     "Target validator should import qwen_tts")

    def test_handles_missing_torch_gracefully(self):
        """Target validator should handle missing torch gracefully."""
        # Check for try-except around torch import
        self.assertIn('try:', self.source)
        self.assertIn('except ImportError', self.source,
                     "Target validator should catch ImportError for missing dependencies")

    def test_prints_python_info(self):
        """Target validator should print Python executable and version."""
        self.assertIn('sys.executable', self.source,
                     "Target validator should print Python executable path")
        self.assertIn('sys.version', self.source,
                     "Target validator should print Python version")


class TestPowerShellScriptConsistency(unittest.TestCase):
    """Test that PowerShell script has consistent step numbering."""

    def setUp(self):
        """Load the PowerShell script."""
        self.ps1_path = Path(__file__).parent.parent.parent / "test_explicit_marker_mode.ps1"
        self.assertTrue(self.ps1_path.exists(),
                       f"PowerShell script not found: {self.ps1_path}")
        
        with open(self.ps1_path, 'r', encoding='utf-8') as f:
            self.lines = f.readlines()

    def test_consistent_step_numbering(self):
        """PowerShell script should have consistent step numbering."""
        # Find all step markers
        step_pattern = r'\[(\d+)/(\d+)\]'
        steps = []
        
        for i, line in enumerate(self.lines, 1):
            import re
            match = re.search(step_pattern, line)
            if match:
                current = int(match.group(1))
                total = int(match.group(2))
                steps.append((current, total, i))
        
        # Check that all steps have the same total
        if steps:
            totals = set(total for _, total, _ in steps)
            self.assertEqual(len(totals), 1,
                           f"Inconsistent step numbering: found totals {totals}. "
                           f"All steps should use the same total (e.g., all /6 or all /7).")
            
            # Check that steps are sequential
            expected_total = totals.pop()
            for i, (current, total, line_num) in enumerate(steps, 1):
                self.assertEqual(current, i,
                               f"Step numbering error at line {line_num}: "
                               f"expected step {i}, found step {current}")
                self.assertEqual(total, expected_total,
                               f"Step total mismatch at line {line_num}")

    def test_no_emoji_in_output(self):
        """PowerShell script should not use emoji in output."""
        # Join all lines for checking
        content = ''.join(self.lines)
        
        # Check for emoji
        forbidden_emoji = ['❌', '✅', '⚠️', '✓', '🔥', '🎉', '💥', '🚀']
        
        for emoji in forbidden_emoji:
            self.assertNotIn(emoji, content,
                           f"PowerShell script contains emoji '{emoji}' which may cause "
                           "encoding issues. Use ASCII text instead.")


if __name__ == '__main__':
    unittest.main()
