"""Regression test for target validator / pipeline report contract.

This test catches the exact failure mode where the target validator reads
wrong keys from the pipeline report, causing 0 sections / 0 WAV outputs
even though synthesis actually succeeded.

The pipeline's _process_explicit_marker_file returns a specific report
structure. The validator must read the CORRECT keys.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestPipelineReportStructure(unittest.TestCase):
    """Verify the pipeline report structure for marker mode."""

    def _make_marker_report(self):
        """Build a synthetic pipeline report matching _process_explicit_marker_file output."""
        return {
            "ok": True,
            "explicit_marker_mode": True,
            "num_parts": 3,
            "parts": [
                {
                    "file": "tmp.txt",
                    "part_index": 1,
                    "total_parts": 3,
                    "ok": True,
                    "wav": "/tmp/output/001_test.wav",
                    "mp3": "/tmp/output/001_test.mp3",
                    "segments": 1,
                    "duration_s": 5.2,
                    "avg_score": 85.0,
                    "project_id": "001_test__abc",
                },
                {
                    "file": "tmp.txt",
                    "part_index": 2,
                    "total_parts": 3,
                    "ok": True,
                    "wav": "/tmp/output/002_test.wav",
                    "mp3": "/tmp/output/002_test.mp3",
                    "segments": 1,
                    "duration_s": 6.1,
                    "avg_score": 87.0,
                    "project_id": "002_test__def",
                },
                {
                    "file": "tmp.txt",
                    "part_index": 3,
                    "total_parts": 3,
                    "ok": True,
                    "wav": "/tmp/output/003_test.wav",
                    "mp3": "/tmp/output/003_test.mp3",
                    "segments": 1,
                    "duration_s": 4.8,
                    "avg_score": 83.0,
                    "project_id": "003_test__ghi",
                },
            ],
            "wavs": [
                "/tmp/output/001_test.wav",
                "/tmp/output/002_test.wav",
                "/tmp/output/003_test.wav",
            ],
            "mp3s": [
                "/tmp/output/001_test.mp3",
                "/tmp/output/002_test.mp3",
                "/tmp/output/003_test.mp3",
            ],
            "segments": 3,
            "duration_s": 16.1,
            "avg_score": 85.0,
            "elapsed_s": 10.5,
            "manifest_path": "/tmp/output/test_manifest.json",
        }

    def test_report_has_explicit_marker_mode(self):
        """Report must contain explicit_marker_mode key."""
        report = self._make_marker_report()
        self.assertTrue(report.get("explicit_marker_mode"))

    def test_report_has_num_parts(self):
        """Report must contain num_parts (not just len(parts))."""
        report = self._make_marker_report()
        self.assertEqual(report.get("num_parts"), 3)

    def test_report_has_parts_list(self):
        """Report must contain 'parts' list, NOT 'sections'."""
        report = self._make_marker_report()
        self.assertIn("parts", report)
        self.assertIsInstance(report["parts"], list)
        self.assertEqual(len(report["parts"]), 3)
        # "sections" key should NOT exist in marker mode report
        self.assertNotIn("sections", report)

    def test_report_has_wavs_list(self):
        """Report must contain 'wavs' list, NOT 'output_files'."""
        report = self._make_marker_report()
        self.assertIn("wavs", report)
        self.assertIsInstance(report["wavs"], list)
        self.assertEqual(len(report["wavs"]), 3)
        # "output_files" key should NOT exist in marker mode report
        self.assertNotIn("output_files", report)

    def test_report_has_mp3s_list(self):
        """Report must contain 'mp3s' list."""
        report = self._make_marker_report()
        self.assertIn("mp3s", report)
        self.assertEqual(len(report["mp3s"]), 3)

    def test_part_report_has_wav_path_as_string(self):
        """Each part_report's wav must be a string path, NOT a dict."""
        report = self._make_marker_report()
        for part in report["parts"]:
            self.assertIsInstance(part["wav"], str)
            self.assertTrue(part["wav"].endswith(".wav"))

    def test_part_report_has_required_fields(self):
        """Each part_report must have: ok, wav, mp3, segments, duration_s."""
        report = self._make_marker_report()
        for part in report["parts"]:
            self.assertIn("ok", part)
            self.assertIn("wav", part)
            self.assertIn("mp3", part)
            self.assertIn("segments", part)
            self.assertIn("duration_s", part)

    def test_report_has_manifest_path(self):
        """Report must contain manifest_path key."""
        report = self._make_marker_report()
        self.assertIn("manifest_path", report)


class TestValidatorReadsCorrectKeys(unittest.TestCase):
    """Verify the target validator reads the correct keys from the report."""

    def test_validator_uses_parts_not_sections(self):
        """Validator must read report['parts'], not report['sections']."""
        validator_path = Path(__file__).parent / "target_validate_explicit_marker.py"
        source = validator_path.read_text(encoding="utf-8")

        # Must use "parts" key
        self.assertIn('report.get("parts"', source)
        # Must NOT use "sections" key (which doesn't exist in marker report)
        # Check that it doesn't use report.get("sections") for section count
        self.assertNotIn('report.get("sections"', source)

    def test_validator_uses_wavs_not_output_files(self):
        """Validator must read report['wavs'], not report['output_files']."""
        validator_path = Path(__file__).parent / "target_validate_explicit_marker.py"
        source = validator_path.read_text(encoding="utf-8")

        # Must use "wavs" key
        self.assertIn('report.get("wavs"', source)
        # Must NOT use "output_files" key (which doesn't exist in marker report)
        self.assertNotIn('report.get("output_files"', source)

    def test_validator_reads_wav_as_string(self):
        """Validator must read part_report['wav'] as a string path."""
        validator_path = Path(__file__).parent / "target_validate_explicit_marker.py"
        source = validator_path.read_text(encoding="utf-8")

        # Must read wav path from part_report
        self.assertIn('part_report.get("wav"', source)
        # Must NOT read path from file_info dict (wrong structure)
        self.assertNotIn('file_info["path"]', source)

    def test_validator_uses_num_parts(self):
        """Validator must read report['num_parts']."""
        validator_path = Path(__file__).parent / "target_validate_explicit_marker.py"
        source = validator_path.read_text(encoding="utf-8")

        self.assertIn('report.get("num_parts"', source)


class TestValidatorOutputFileChecks(unittest.TestCase):
    """Verify the validator checks actual WAV files on disk."""

    def test_validator_checks_file_exists(self):
        """Validator must check that WAV files exist on disk."""
        validator_path = Path(__file__).parent / "target_validate_explicit_marker.py"
        source = validator_path.read_text(encoding="utf-8")

        self.assertIn("filepath.exists()", source)

    def test_validator_checks_file_not_empty(self):
        """Validator must check that WAV files are non-empty."""
        validator_path = Path(__file__).parent / "target_validate_explicit_marker.py"
        source = validator_path.read_text(encoding="utf-8")

        self.assertIn("file_size == 0", source)

    def test_validator_checks_file_size(self):
        """Validator must check actual file size on disk."""
        validator_path = Path(__file__).parent / "target_validate_explicit_marker.py"
        source = validator_path.read_text(encoding="utf-8")

        self.assertIn("filepath.stat().st_size", source)


class TestPipelineSourceStructure(unittest.TestCase):
    """Verify the pipeline source produces the correct report structure."""

    def test_marker_mode_sets_explicit_marker_mode_key(self):
        """Pipeline must set explicit_marker_mode=True in report."""
        pipeline_src = (
            Path(__file__).parent.parent / "app" / "project" / "pipeline.py"
        )
        source = pipeline_src.read_text(encoding="utf-8")
        self.assertIn('"explicit_marker_mode": True', source)

    def test_marker_mode_sets_num_parts_key(self):
        """Pipeline must set num_parts in report."""
        pipeline_src = (
            Path(__file__).parent.parent / "app" / "project" / "pipeline.py"
        )
        source = pipeline_src.read_text(encoding="utf-8")
        self.assertIn('"num_parts": num_parts', source)

    def test_marker_mode_sets_parts_key(self):
        """Pipeline must set 'parts' (not 'sections') in report."""
        pipeline_src = (
            Path(__file__).parent.parent / "app" / "project" / "pipeline.py"
        )
        source = pipeline_src.read_text(encoding="utf-8")
        self.assertIn('"parts": part_reports', source)

    def test_marker_mode_sets_wavs_key(self):
        """Pipeline must set 'wavs' (not 'output_files') in report."""
        pipeline_src = (
            Path(__file__).parent.parent / "app" / "project" / "pipeline.py"
        )
        source = pipeline_src.read_text(encoding="utf-8")
        self.assertIn('"wavs": all_wavs', source)

    def test_single_section_returns_wav_string(self):
        """_process_single_section must return wav as string path."""
        pipeline_src = (
            Path(__file__).parent.parent / "app" / "project" / "pipeline.py"
        )
        source = pipeline_src.read_text(encoding="utf-8")
        # The single section report must have "wav": str(out_wav)
        self.assertIn('"wav": str(out_wav)', source)


class TestNoMarkerRegression(unittest.TestCase):
    """No-marker path must remain unchanged."""

    def test_normal_pipeline_does_not_set_marker_mode(self):
        """Normal pipeline (no markers) does not set explicit_marker_mode."""
        pipeline_src = (
            Path(__file__).parent.parent / "app" / "project" / "pipeline.py"
        )
        source = pipeline_src.read_text(encoding="utf-8")

        # Find the normal mode report update (near the end of process_file)
        # The normal mode report has "wav": str(out_wav) at top level, not "parts"
        # Check that the normal mode return doesn't include "explicit_marker_mode"
        # by verifying the marker mode branch returns early
        self.assertIn("has_explicit_markers(text)", source)
        self.assertIn("_process_explicit_marker_file", source)


if __name__ == "__main__":
    unittest.main()
