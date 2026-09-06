"""
Regression test for project/install.ps1 PowerShell command construction.

Validates that the installer does NOT construct broken commands like:
    & ".venv\\Scripts\\python.exe -m pip"
    & $Pip -m pip ...   (where $Pip is a string with embedded args)

The robust pattern is:
    $Vpy = Join-Path $Root ".venv\\Scripts\\python.exe"
    & $Vpy -m pip install ...

This test parses install.ps1 textually (no PS engine needed) and
checks for the known-broken patterns.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INSTALL_PS1 = REPO_ROOT / "project" / "install.ps1"


class InstallPs1CommandConstructionTest(unittest.TestCase):
    """Ensure install.ps1 constructs commands correctly for PowerShell 5.1."""

    @classmethod
    def setUpClass(cls):
        cls.source = INSTALL_PS1.read_text(encoding="utf-8")
        cls.lines = cls.source.splitlines()

    # ------------------------------------------------------------------ #
    # 1. No $Pip variable should be used (it was the root cause variable)
    # ------------------------------------------------------------------ #
    def test_no_pip_variable_assignment(self):
        """$Pip should not be assigned as a combined string or array."""
        # Match: $Pip = "..." or $Pip = "@(..."
        pattern = re.compile(r'^\s*\$Pip\s*=', re.IGNORECASE)
        violations = []
        for i, line in enumerate(self.lines, 1):
            if pattern.match(line):
                violations.append(f"  line {i}: {line.strip()}")
        self.assertEqual(
            violations, [],
            "install.ps1 must not define a $Pip variable "
            "(exec+args embedded in one var):\n" + "\n".join(violations),
        )

    def test_no_pip_variable_invocation(self):
        """No invocation should use & $Pip (the broken pattern)."""
        pattern = re.compile(r'&\s+\$Pip\b')
        violations = []
        for i, line in enumerate(self.lines, 1):
            if pattern.search(line):
                violations.append(f"  line {i}: {line.strip()}")
        self.assertEqual(
            violations, [],
            "install.ps1 must not invoke & $Pip:\n" + "\n".join(violations),
        )

    # ------------------------------------------------------------------ #
    # 2. Executable path must be separate from arguments
    # ------------------------------------------------------------------ #
    def test_vpy_is_join_path_absolute(self):
        """$Vpy must be built via Join-Path (absolute), not a bare relative string."""
        # Look for: $Vpy = Join-Path $Root ".venv\Scripts\python.exe"
        pattern = re.compile(
            r'\$Vpy\s*=\s*Join-Path\s+\$Root\s+["\']\.venv\\Scripts\\python\.exe["\']'
        )
        self.assertTrue(
            pattern.search(self.source),
            "$Vpy must be assigned via Join-Path $Root \".venv\\Scripts\\python.exe\" "
            "to produce an absolute path",
        )

    def test_no_bare_relative_vpy_assignment(self):
        """$Vpy must not be a bare relative path like '.venv\\Scripts\\python.exe'."""
        pattern = re.compile(
            r'^\s*\$Vpy\s*=\s*["\']\.venv\\Scripts\\python\.exe["\']',
            re.MULTILINE,
        )
        matches = pattern.findall(self.source)
        self.assertEqual(
            matches, [],
            "$Vpy must not be assigned a bare relative path",
        )

    # ------------------------------------------------------------------ #
    # 3. No invocation should try to execute a combined string
    # ------------------------------------------------------------------ #
    def test_no_compound_executable_string(self):
        """No & invocation should contain a compound 'python.exe -m pip' string."""
        # Match: & "something.exe -m pip"  or  & 'something.exe -m pip'
        pattern = re.compile(
            r'&\s*["\'][^"\']*\.exe\s+(-m|install|--)[^"\']*["\']'
        )
        violations = []
        for i, line in enumerate(self.lines, 1):
            if pattern.search(line):
                violations.append(f"  line {i}: {line.strip()}")
        self.assertEqual(
            violations, [],
            "install.ps1 must not invoke a compound executable string "
            "(exe path + args as one quoted value):\n" + "\n".join(violations),
        )

    # ------------------------------------------------------------------ #
    # 4. All & $Vpy invocations must pass arguments as separate tokens
    # ------------------------------------------------------------------ #
    def test_all_vpy_invocations_separate_args(self):
        """Every & $Vpy ... line must have args as separate tokens after $Vpy."""
        pattern = re.compile(r'&\s+\$Vpy\b(.*)')
        violations = []
        for i, line in enumerate(self.lines, 1):
            m = pattern.search(line)
            if not m:
                continue
            rest = m.group(1).strip()
            # After $Vpy, arguments should be separate tokens.
            # Red flag: a quoted string containing spaces AND executable-like content
            # e.g., & $Vpy ".venv\Scripts\python.exe -m pip"
            bad = re.search(r'["\'][^"\']*\.exe\s+-[^"\']*["\']', rest)
            if bad:
                violations.append(f"  line {i}: {line.strip()}")
        self.assertEqual(
            violations, [],
            "install.ps1 has compound args after & $Vpy:\n" + "\n".join(violations),
        )

    # ------------------------------------------------------------------ #
    # 5. ErrorActionPreference should be "Stop"
    # ------------------------------------------------------------------ #
    def test_error_action_preference_is_stop(self):
        """Script should stop immediately on errors."""
        pattern = re.compile(r'\$ErrorActionPreference\s*=\s*"Stop"')
        self.assertTrue(
            pattern.search(self.source),
            "$ErrorActionPreference must be 'Stop' for fail-fast behavior",
        )

    # ------------------------------------------------------------------ #
    # 6. Every pip invocation uses the canonical pattern
    # ------------------------------------------------------------------ #
    def test_pip_invocations_use_canonical_pattern(self):
        """All pip install invocations must use: & $Vpy -m pip install ..."""
        # Find all lines that call pip install
        pip_install_pattern = re.compile(r'pip\s+install')
        canonical_pattern = re.compile(r'&\s+\$Vpy\s+-m\s+pip\s+install')
        violations = []
        for i, line in enumerate(self.lines, 1):
            if pip_install_pattern.search(line) and not line.strip().startswith("#"):
                if not canonical_pattern.search(line):
                    violations.append(f"  line {i}: {line.strip()}")
        self.assertEqual(
            violations, [],
            "All pip install calls must use '& $Vpy -m pip install ...':\n"
            + "\n".join(violations),
        )

    # ------------------------------------------------------------------ #
    # 7. venv creation uses proper command splitting
    # ------------------------------------------------------------------ #
    def test_venv_creation_uses_proper_split(self):
        """venv creation must not use a compound executable string."""
        # The py launcher case must split args
        venv_pattern = re.compile(r'&\s+\$Python\s+-m\s+venv\s+\.venv')
        self.assertTrue(
            venv_pattern.search(self.source),
            "Standard venv creation should use: & $Python -m venv .venv",
        )


class InstallPs1SyntaxTest(unittest.TestCase):
    """Basic PowerShell syntax sanity checks (textual, no PS engine)."""

    @classmethod
    def setUpClass(cls):
        cls.source = INSTALL_PS1.read_text(encoding="utf-8")
        cls.lines = cls.source.splitlines()

    def test_balanced_braces(self):
        """Braces must be balanced (basic syntax check)."""
        opens = self.source.count("{")
        closes = self.source.count("}")
        self.assertEqual(opens, closes, f"Unbalanced braces: {opens} {{ vs {closes} }}")

    def test_balanced_parens_in_code(self):
        """Non-comment parentheses should be reasonably balanced."""
        # Strip comment portions and strings, then count
        code_lines = []
        for line in self.lines:
            # Strip everything after # that is not inside a string
            stripped = line.split("#")[0] if "#" in line else line
            code_lines.append(stripped)
        code = "\n".join(code_lines)
        opens = code.count("(")
        closes = code.count(")")
        # Allow some tolerance for multi-line expressions and string contents
        self.assertAlmostEqual(
            opens, closes, delta=5,
            msg=f"Too many unbalanced parens in code: {opens} ( vs {closes} )",
        )

    def test_no_null_byte(self):
        """Script must not contain null bytes (corruption indicator)."""
        self.assertNotIn("\x00", self.source)

    def test_preserves_cuda_intent(self):
        """Script must retain cu128 installation intent."""
        self.assertIn("cu128", self.source)
        self.assertIn("download.pytorch.org/whl/cu128", self.source)

    def test_preserves_python_version_range(self):
        """Script must still target Python 3.10-3.13."""
        self.assertIn("3.12", self.source)
        self.assertIn("3.11", self.source)
        self.assertIn("3.13", self.source)
        self.assertIn("3.10", self.source)

    def test_preserves_requirements_txt(self):
        """Script must still install from requirements.txt."""
        self.assertIn("requirements.txt", self.source)


if __name__ == "__main__":
    unittest.main()
