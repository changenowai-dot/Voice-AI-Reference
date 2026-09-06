"""
Regression tests for run_phase4_target.ps1 PowerShell stderr/exit-code handling.

Validates that the target runner correctly handles Python stderr output
without treating warnings as terminating errors, while still failing
on genuine non-zero exit codes.
"""
import unittest
import re
from pathlib import Path


class TestRunPhase4TargetStderrHandling(unittest.TestCase):
    """Test that run_phase4_target.ps1 handles stderr correctly."""

    @classmethod
    def setUpClass(cls):
        """Load the PowerShell script."""
        cls.ps1_path = Path(__file__).parent.parent.parent / "run_phase4_target.ps1"
        # Read as text (with universal newlines stripped to \n)
        cls.content = cls.ps1_path.read_text(encoding='utf-8-sig')
        cls.lines = cls.content.splitlines()
        # Also read raw bytes for binary checks (BOM, CRLF)
        cls.raw_bytes = cls.ps1_path.read_bytes()

    def test_bom_present(self):
        """PowerShell script must have UTF-8 BOM."""
        self.assertTrue(self.raw_bytes[:3] == b'\xef\xbb\xbf',
                       "UTF-8 BOM must be present")

    def test_crlf_line_endings(self):
        """PowerShell script must use CRLF line endings."""
        # Check raw bytes for CRLF
        self.assertIn(b'\r\n', self.raw_bytes, "CRLF line endings required in raw bytes")
        # Check no bare LF (LF not preceded by CR)
        content = self.raw_bytes
        # Remove BOM if present
        if content[:3] == b'\xef\xbb\xbf':
            content = content[3:]
        # Remove all \r\n
        no_crlf = content.replace(b'\r\n', b'')
        # Any remaining \n means bare LF
        bare_lf = no_crlf.count(b'\n')
        self.assertEqual(bare_lf, 0,
                        f"Found {bare_lf} bare LF characters (all lines must be CRLF)")

    def test_error_action_preference_stop_set(self):
        """Script must set $ErrorActionPreference = 'Stop' at the beginning."""
        pattern = r'\$ErrorActionPreference\s*=\s*"Stop"'
        self.assertRegex(self.content, pattern,
                        "$ErrorActionPreference = 'Stop' must be set")

    def test_benchmark_execution_uses_eap_switching(self):
        """Benchmark execution must use EAP switching pattern."""
        # Find the benchmark execution section
        benchmark_line_idx = None
        for i, line in enumerate(self.lines):
            if '$BenchmarkScript' in line and '& $PythonCmd' in line:
                benchmark_line_idx = i
                break

        self.assertIsNotNone(benchmark_line_idx,
                           "Benchmark execution line ($BenchmarkScript + & $PythonCmd) not found")

        # Look in surrounding context for EAP switching
        context_start = max(0, benchmark_line_idx - 20)
        context_end = min(len(self.lines), benchmark_line_idx + 20)
        context = '\n'.join(self.lines[context_start:context_end])

        # Check for EAP switching pattern
        self.assertIn('$prevEAP = $ErrorActionPreference', context,
                     "Must save $ErrorActionPreference before benchmark")
        self.assertIn("$ErrorActionPreference = 'Continue'", context,
                     "Must set $ErrorActionPreference = 'Continue' before benchmark")
        self.assertIn('$ErrorActionPreference = $prevEAP', context,
                     "Must restore $ErrorActionPreference after benchmark")

    def test_benchmark_captures_stderr(self):
        """Benchmark execution must capture both stdout and stderr."""
        # Find the benchmark execution line
        found = False
        for i, line in enumerate(self.lines):
            if '$BenchmarkScript' in line and '& $PythonCmd' in line:
                # Check that it uses 2>&1 to capture stderr
                self.assertIn('2>&1', line,
                            "Must use 2>&1 to capture both stdout and stderr")
                found = True
                break
        self.assertTrue(found, "Benchmark execution line not found")

    def test_benchmark_exit_code_checked(self):
        """Benchmark execution must check $LASTEXITCODE explicitly."""
        # Find the assignment line
        for i, line in enumerate(self.lines):
            if 'BenchmarkExitCode = $LASTEXITCODE' in line:
                # Check that it's compared to 0
                context = '\n'.join(self.lines[i:i+20])
                self.assertIn('$BenchmarkExitCode -ne 0', context,
                            "Must check if $BenchmarkExitCode -ne 0")
                self.assertIn('BENCHMARK FEHLGESCHLAGEN', context,
                            "Must report failure when exit code is non-zero")
                break
        else:
            self.fail("$BenchmarkExitCode = $LASTEXITCODE not found")

    def test_benchmark_output_written_to_file(self):
        """Benchmark output must be written to file."""
        # Find where output is written
        pattern = r'\$output\s*\|\s*Out-File\s+-FilePath\s+\$BenchmarkOutput'
        self.assertRegex(self.content, pattern,
                        "Must write $output to $BenchmarkOutput file")

    def test_env_check_uses_eap_switching(self):
        """Environment check must also use EAP switching for robustness."""
        # Find the environment check section
        env_line_idx = None
        for i, line in enumerate(self.lines):
            if '$EnvCheckScript' in line and '& $PythonCmd' in line:
                env_line_idx = i
                break

        self.assertIsNotNone(env_line_idx,
                           "Environment check execution line not found")

        # Look in surrounding context for EAP switching
        context_start = max(0, env_line_idx - 20)
        context_end = min(len(self.lines), env_line_idx + 20)
        context = '\n'.join(self.lines[context_start:context_end])

        # Check for EAP switching pattern
        self.assertIn('$prevEAP = $ErrorActionPreference', context,
                     "Must save $ErrorActionPreference before env check")
        self.assertIn("$ErrorActionPreference = 'Continue'", context,
                     "Must set $ErrorActionPreference = 'Continue' before env check")
        self.assertIn('$ErrorActionPreference = $prevEAP', context,
                     "Must restore $ErrorActionPreference after env check")

    def test_env_check_captures_stderr(self):
        """Environment check must capture both stdout and stderr."""
        found = False
        for i, line in enumerate(self.lines):
            if '$EnvCheckScript' in line and '& $PythonCmd' in line:
                self.assertIn('2>&1', line,
                            "Must use 2>&1 to capture both stdout and stderr")
                found = True
                break
        self.assertTrue(found, "Environment check execution line not found")

    def test_try_finally_for_benchmark(self):
        """Benchmark section must use try/finally to ensure EAP is restored."""
        # Find the benchmark line and look for surrounding try/finally
        benchmark_line_idx = None
        for i, line in enumerate(self.lines):
            if '$BenchmarkScript' in line and '& $PythonCmd' in line:
                benchmark_line_idx = i
                break

        self.assertIsNotNone(benchmark_line_idx, "Benchmark execution line not found")

        # Look for try/finally in context
        context_start = max(0, benchmark_line_idx - 10)
        context_end = min(len(self.lines), benchmark_line_idx + 15)
        context = '\n'.join(self.lines[context_start:context_end])

        self.assertIn('try {', context, "Must use try block around benchmark execution")
        self.assertIn('finally {', context, "Must use finally block to restore EAP")

    def test_try_finally_for_env_check(self):
        """Environment check section must use try/finally to ensure EAP is restored."""
        # Find the env check line and look for surrounding try/finally
        env_line_idx = None
        for i, line in enumerate(self.lines):
            if '$EnvCheckScript' in line and '& $PythonCmd' in line:
                env_line_idx = i
                break

        self.assertIsNotNone(env_line_idx, "Environment check execution line not found")

        # Look for try/finally in context
        context_start = max(0, env_line_idx - 10)
        context_end = min(len(self.lines), env_line_idx + 15)
        context = '\n'.join(self.lines[context_start:context_end])

        self.assertIn('try {', context, "Must use try block around env check execution")
        self.assertIn('finally {', context, "Must use finally block to restore EAP")

    def test_no_star_redirect_on_python_invocations(self):
        """Must not use *> operator for Python invocations (unreliable in PS 5.1 with Stop)."""
        for i, line in enumerate(self.lines, 1):
            if '& $PythonCmd' in line:
                self.assertNotIn('*>', line,
                    f"Line {i}: Must not use *> operator with & $PythonCmd")

    def test_hardware_info_fix_preserved(self):
        """HardwareInfo API fix must be preserved (no regression)."""
        benchmark_path = self.ps1_path.parent / "benchmark" / "phase4_benchmark.py"
        if benchmark_path.exists():
            benchmark_content = benchmark_path.read_text(encoding='utf-8')
            # Should use correct attribute names
            self.assertIn('hw.gpu_name', benchmark_content)
            self.assertIn('hw.gpu_vram_total_gb', benchmark_content)
            self.assertIn('hw.ram_total_gb', benchmark_content)
            # Should NOT use incorrect names
            self.assertNotIn('hw.vram_gb', benchmark_content)
            self.assertNotIn('hw.ram_gb', benchmark_content)
            self.assertNotIn('hw.device_name', benchmark_content)

    def test_identity_lock_runtime_ref_preserved(self):
        """Identity Lock runtime ref fix must be preserved (no regression)."""
        identity_lock_path = self.ps1_path.parent / "app" / "security" / "identity_lock.py"
        if identity_lock_path.exists():
            content = identity_lock_path.read_text(encoding='utf-8')
            # Should check for VOICEOVER_RUNTIME_REF
            self.assertIn('VOICEOVER_RUNTIME_REF', content,
                         "identity_lock.py must check VOICEOVER_RUNTIME_REF")
            # Should have _resolve_reference_path function
            self.assertIn('_resolve_reference_path', content,
                         "identity_lock.py must have _resolve_reference_path function")


class TestPowerShellSyntaxValidity(unittest.TestCase):
    """Test that the PowerShell script has valid syntax."""

    @classmethod
    def setUpClass(cls):
        """Load the PowerShell script."""
        cls.ps1_path = Path(__file__).parent.parent.parent / "run_phase4_target.ps1"
        cls.content = cls.ps1_path.read_text(encoding='utf-8-sig')

    def test_balanced_braces(self):
        """Braces must be balanced."""
        open_count = self.content.count('{')
        close_count = self.content.count('}')
        self.assertEqual(open_count, close_count,
                        f"Unbalanced braces: {open_count} open, {close_count} close")

    def test_balanced_parentheses(self):
        """Parentheses must be balanced."""
        open_count = self.content.count('(')
        close_count = self.content.count(')')
        self.assertEqual(open_count, close_count,
                        f"Unbalanced parentheses: {open_count} open, {close_count} close")

    def test_no_null_bytes(self):
        """Script must not contain null bytes."""
        self.assertNotIn('\x00', self.content,
                        "Script must not contain null bytes")


if __name__ == '__main__':
    unittest.main()
