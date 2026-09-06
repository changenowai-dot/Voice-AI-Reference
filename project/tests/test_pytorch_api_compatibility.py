"""Regression test: PyTorch API compatibility for CUDA device properties.

Catches issue where phase4 scripts used ``props.total_mem`` which does not
exist on ``torch._C._CudaDeviceProperties`` — the correct attribute is
``props.total_memory``.

This test does NOT require a real GPU.  It uses ``unittest.mock`` to
simulate ``torch.cuda`` and verifies the scripts reference the correct
attribute name via static source-code analysis.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parent.parent / "benchmark"


class PyTorchApiCompatibilityTest(unittest.TestCase):
    """Verify PyTorch CUDA API usage is compatible with PyTorch >= 2.0."""

    # Attributes that exist on torch._C._CudaDeviceProperties
    VALID_PROPERTIES = frozenset({
        "name",
        "major",
        "minor",
        "total_memory",     # bytes — the correct one
        "multi_processor_count",
        "is_integrated",
        "is_multi_gpu_board",
    })

    # Known INVALID attributes (these should NEVER appear in our code)
    INVALID_PROPERTIES = frozenset({
        "total_mem",        # AttributeError in PyTorch 2.x
    })

    def _find_py_source_files(self):
        """Return all .py files in the benchmark directory."""
        return list(BENCHMARK_DIR.glob("phase4_*.py"))

    def test_no_total_mem_in_benchmark_scripts(self):
        """phase4_*.py must not use the invalid attribute ``total_mem``."""
        files = self._find_py_source_files()
        self.assertTrue(files, "No phase4_*.py files found in benchmark/")

        bad_pattern = re.compile(r"\.total_mem\b(?!ory)")

        violations = []
        for f in files:
            for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if bad_pattern.search(line):
                    violations.append(f"  {f.name}:{lineno}: {line.strip()}")

        self.assertEqual(
            violations, [],
            "Found invalid PyTorch property 'total_mem' "
            "(should be 'total_memory'):\n" + "\n".join(violations),
        )

    def test_total_memory_is_used(self):
        """phase4_env_check.py must use ``total_memory`` for VRAM calculation."""
        env_check = BENCHMARK_DIR / "phase4_env_check.py"
        source = env_check.read_text(encoding="utf-8")
        self.assertIn(
            ".total_memory", source,
            "phase4_env_check.py does not reference .total_memory",
        )

    def test_benchmark_total_memory_is_used(self):
        """phase4_benchmark.py must use ``total_memory`` for GPU info."""
        benchmark = BENCHMARK_DIR / "phase4_benchmark.py"
        source = benchmark.read_text(encoding="utf-8")
        self.assertIn(
            ".total_memory", source,
            "phase4_benchmark.py does not reference .total_memory",
        )

    def test_mock_cuda_properties_with_total_memory(self):
        """Simulate torch.cuda.get_device_properties with total_memory."""
        from unittest.mock import MagicMock

        props = MagicMock()
        props.total_memory = 8 * 1024**3   # 8 GB in bytes
        props.name = "NVIDIA GeForce RTX 5060"
        props.major = 12
        props.minor = 0

        # This is the correct computation used in our scripts
        vram_gb = round(props.total_memory / (1024**3), 1)
        self.assertEqual(vram_gb, 8.0)
        self.assertEqual(props.name, "NVIDIA GeForce RTX 5060")

    def test_mock_cuda_properties_total_mem_raises(self):
        """Verify that total_mem is NOT a valid attribute — regression guard."""
        from unittest.mock import MagicMock

        props = MagicMock(spec=["name", "major", "minor", "total_memory",
                                 "multi_processor_count"])
        props.total_memory = 8 * 1024**3
        props.name = "NVIDIA GeForce RTX 5060"

        # total_mem should NOT exist when using spec
        with self.assertRaises(AttributeError):
            _ = props.total_mem


if __name__ == "__main__":
    unittest.main()
