"""
Regression test for HardwareInfo API usage in benchmark scripts.
Validates that phase4_benchmark.py and phase3_audio_baseline_ab_test.py
use the correct HardwareInfo attribute names.
"""
import ast
import unittest
from pathlib import Path


class TestHardwareInfoAPI(unittest.TestCase):
    """Test that benchmark scripts use correct HardwareInfo API."""

    def test_phase4_benchmark_uses_correct_attributes(self):
        """phase4_benchmark.py must use correct HardwareInfo attributes."""
        benchmark_path = Path(__file__).parent.parent / "benchmark" / "phase4_benchmark.py"
        content = benchmark_path.read_text(encoding='utf-8')
        
        # Should use these correct attributes
        self.assertIn('hw.gpu_name', content)
        self.assertIn('hw.gpu_vram_total_gb', content)
        self.assertIn('hw.ram_total_gb', content)
        
        # Should NOT use these incorrect attributes
        self.assertNotIn('hw.vram_gb', content)
        self.assertNotIn('hw.ram_gb', content)
        self.assertNotIn('hw.device_name', content)

    def test_phase3_benchmark_uses_correct_attributes(self):
        """phase3_audio_baseline_ab_test.py must use correct HardwareInfo attributes."""
        benchmark_path = Path(__file__).parent.parent / "benchmark" / "phase3_audio_baseline_ab_test.py"
        content = benchmark_path.read_text(encoding='utf-8')
        
        # Should use these correct attributes
        self.assertIn('hw.gpu_vram_total_gb', content)
        self.assertIn('hw.ram_total_gb', content)
        
        # Should NOT use these incorrect attributes
        self.assertNotIn('hw.vram_gb', content)
        self.assertNotIn('hw.ram_gb', content)

    def test_hardware_info_class_has_correct_attributes(self):
        """HardwareInfo class must define the correct attributes."""
        detector_path = Path(__file__).parent.parent / "app" / "hardware" / "detector.py"
        content = detector_path.read_text(encoding='utf-8')
        
        # Parse the AST to find the HardwareInfo class
        tree = ast.parse(content)
        
        hardware_info_class = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == 'HardwareInfo':
                hardware_info_class = node
                break
        
        self.assertIsNotNone(hardware_info_class, "HardwareInfo class not found")
        
        # Get all attribute names from the class
        attribute_names = set()
        for item in hardware_info_class.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                attribute_names.add(item.target.id)
        
        # Verify correct attributes exist
        self.assertIn('gpu_name', attribute_names)
        self.assertIn('gpu_vram_total_gb', attribute_names)
        self.assertIn('ram_total_gb', attribute_names)
        
        # Verify incorrect attributes don't exist
        self.assertNotIn('vram_gb', attribute_names)
        self.assertNotIn('ram_gb', attribute_names)
        self.assertNotIn('device_name', attribute_names)


if __name__ == '__main__':
    unittest.main()
