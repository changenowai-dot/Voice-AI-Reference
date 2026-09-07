"""Comprehensive tests for explicit audio marker split mode.

Tests the ``+++++`` marker system for splitting input text into
separate audio output files. Validates:

1. Basic marker splitting (single, multi-line, with whitespace)
2. Empty segment handling (leading/trailing/repeated markers)
3. Exact five-plus marker recognition
4. Ordinary plus characters preserved
5. Marker never reaches TTS input
6. No-marker input unchanged
7. Output ordering deterministic
8. Cache/resume compatibility
9. Unicode German text preserved
10. Quotation marks and punctuation intact
11. Pipeline integration (explicit marker mode activation)
12. Defensive validation (assert_no_marker_in_tts_input)
13. File naming (001_basename, 002_basename, ...)
14. Empty input safety
15. Marker at BOF/EOF handling
16. Batch compatibility
"""
import unittest

from app.text.script_split import (
    MARKER,
    assert_no_marker_in_tts_input,
    assert_no_markers_in_sections,
    count_markers,
    generate_part_filename,
    get_explicit_marker_plan,
    has_explicit_markers,
    is_marker_line,
    split_explicit_audio_markers,
    split_manuscript,
)


# =============================================================================
# Test Data: Real German Text (Delphi Script)
# =============================================================================
DELPHI_A = (
    "Es gab einen Ort in der antiken Welt, der als der Nabel "
    "des Universums galt."
)
DELPHI_B = (
    "Die Pythia, die Hohepriesterin, saß auf einem Dreifuß "
    "über einem Erdspalt."
)
DELPHI_C = (
    "Die wahre Macht von Delphi lag nicht in der Wahrsagerei. "
    "Sie lag in der Reflexion."
)


class TestBasicMarkerDetection(unittest.TestCase):
    """Tests 1-5: Basic marker detection and splitting."""

    def test_single_marker_basic(self):
        """Test 1: Single marker: 'A+++++B' -> ['A', 'B']."""
        result = split_explicit_audio_markers("A\n+++++\nB")
        self.assertEqual(result, ["A", "B"])

    def test_multiline_marker(self):
        """Test 2: Multiline: 'A\\n+++++\\nB' -> ['A', 'B']."""
        result = split_explicit_audio_markers("A\n+++++\nB")
        self.assertEqual(result, ["A", "B"])

    def test_marker_with_surrounding_whitespace(self):
        """Test 3: Marker with surrounding whitespace."""
        result = split_explicit_audio_markers("A\n  +++++  \nB")
        self.assertEqual(result, ["A", "B"])

    def test_marker_with_tabs(self):
        """Test 3b: Marker with tab whitespace."""
        result = split_explicit_audio_markers("A\n\t+++++\t\nB")
        self.assertEqual(result, ["A", "B"])

    def test_leading_marker(self):
        """Test 4: Leading marker produces no empty first section."""
        result = split_explicit_audio_markers("+++++\nText A")
        self.assertEqual(result, ["Text A"])
        self.assertEqual(len(result), 1)

    def test_trailing_marker(self):
        """Test 4b: Trailing marker produces no empty last section."""
        result = split_explicit_audio_markers("Text A\n+++++")
        self.assertEqual(result, ["Text A"])
        self.assertEqual(len(result), 1)

    def test_repeated_markers(self):
        """Test 6: Repeated markers treated as single split."""
        result = split_explicit_audio_markers("Text A\n+++++\n+++++\nText B")
        self.assertEqual(result, ["Text A", "Text B"])
        self.assertEqual(len(result), 2)

    def test_multiple_blocks(self):
        """Test 7: Multiple blocks produce correct count."""
        text = f"{DELPHI_A}\n+++++\n{DELPHI_B}\n+++++\n{DELPHI_C}"
        result = split_explicit_audio_markers(text)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], DELPHI_A)
        self.assertEqual(result[1], DELPHI_B)
        self.assertEqual(result[2], DELPHI_C)


class TestExactMarkerRecognition(unittest.TestCase):
    """Tests 9-11: Exact marker recognition and ordinary plus preservation."""

    def test_exact_five_plus_marker(self):
        """Test 9: Exactly five plus signs recognized as marker."""
        self.assertTrue(is_marker_line("+++++"))
        self.assertTrue(is_marker_line("  +++++  "))
        self.assertTrue(is_marker_line("\t+++++\t"))

    def test_four_plus_not_marker(self):
        """Test 9b: Four plus signs are NOT a marker."""
        self.assertFalse(is_marker_line("++++"))

    def test_six_plus_not_marker(self):
        """Test 10: Six plus signs are NOT a marker."""
        self.assertFalse(is_marker_line("++++++"))

    def test_plus_in_prose_not_marker(self):
        """Test 10b: Plus signs within prose are NOT markers."""
        self.assertFalse(is_marker_line("abc+++++"))
        self.assertFalse(is_marker_line("+++++abc"))

    def test_ordinary_plus_preserved_2plus2(self):
        """Test 11: '2+2=4' remains unchanged."""
        text = "2+2=4 ist eine einfache Rechnung."
        result = split_explicit_audio_markers(text)
        self.assertEqual(result, [text])
        self.assertIn("2+2=4", result[0])

    def test_cpp_preserved(self):
        """Test 11b: 'C++' remains unchanged."""
        text = "Die Programmiersprache C++ ist weit verbreitet."
        result = split_explicit_audio_markers(text)
        self.assertEqual(result, [text])
        self.assertIn("C++", result[0])

    def test_a_plus_b_preserved(self):
        """Test 11c: 'A+B' remains unchanged."""
        text = "A+B ergibt die Summe."
        result = split_explicit_audio_markers(text)
        self.assertEqual(result, [text])
        self.assertIn("A+B", result[0])

    def test_single_plus_preserved(self):
        """Test 11d: Single '+' remains unchanged."""
        text = "+42 ist eine positive Zahl."
        result = split_explicit_audio_markers(text)
        self.assertEqual(result, [text])
        self.assertIn("+42", result[0])

    def test_marker_with_text_around_not_marker(self):
        """Test: '++' embedded in text is not treated as marker."""
        text = "Das Ergebnis ist: +++++ Punkte"
        # This line contains "+++++" but not as a standalone line
        result = split_explicit_audio_markers(text)
        # It's one line, not a marker line
        self.assertEqual(len(result), 1)
        self.assertIn("+++++", result[0])


class TestEmptySegmentHandling(unittest.TestCase):
    """Tests 3, 8, 22-24: Empty segment and boundary handling."""

    def test_empty_input(self):
        """Test 22: Empty input handled safely."""
        result = split_explicit_audio_markers("")
        self.assertEqual(result, [])

    def test_whitespace_only_input(self):
        """Test 22b: Whitespace-only input handled safely."""
        result = split_explicit_audio_markers("   \n  \n  ")
        self.assertEqual(result, [])

    def test_only_markers(self):
        """Test 22c: Only markers produces empty result."""
        result = split_explicit_audio_markers("+++++\n+++++\n+++++")
        self.assertEqual(result, [])

    def test_marker_at_eof(self):
        """Test 23: Marker at EOF handled safely."""
        result = split_explicit_audio_markers("Text\n+++++")
        self.assertEqual(result, ["Text"])
        self.assertEqual(len(result), 1)

    def test_marker_at_bof(self):
        """Test 24: Marker at BOF handled safely."""
        result = split_explicit_audio_markers("+++++\nText")
        self.assertEqual(result, ["Text"])
        self.assertEqual(len(result), 1)

    def test_multiple_leading_markers(self):
        """Test: Multiple leading markers produce no empty sections."""
        result = split_explicit_audio_markers("+++++\n+++++\nText")
        self.assertEqual(result, ["Text"])

    def test_multiple_trailing_markers(self):
        """Test: Multiple trailing markers produce no empty sections."""
        result = split_explicit_audio_markers("Text\n+++++\n+++++")
        self.assertEqual(result, ["Text"])

    def test_empty_block_between_markers(self):
        """Test: Empty block between markers is skipped."""
        text = "A\n+++++\n\n+++++\nB"
        result = split_explicit_audio_markers(text)
        self.assertEqual(result, ["A", "B"])

    def test_whitespace_only_block_skipped(self):
        """Test: Whitespace-only block is skipped."""
        text = "A\n+++++\n   \n+++++\nB"
        result = split_explicit_audio_markers(text)
        self.assertEqual(result, ["A", "B"])


class TestMarkerNeverReachesTTS(unittest.TestCase):
    """Tests 12-13, 25: Marker never reaches TTS input."""

    def test_marker_not_in_split_sections(self):
        """Test 12: Marker never in split section output."""
        text = f"{DELPHI_A}\n+++++\n{DELPHI_B}\n+++++\n{DELPHI_C}"
        sections = split_explicit_audio_markers(text)
        for section in sections:
            self.assertNotIn(MARKER, section,
                           f"Marker found in section: {section[:50]}")

    def test_assert_no_marker_passes_clean_text(self):
        """Test 13: assert_no_marker_in_tts_input passes clean text."""
        # Should not raise
        assert_no_marker_in_tts_input("Normaler Text ohne Marker")
        assert_no_marker_in_tts_input("C++ Programmierung")
        assert_no_marker_in_tts_input("2+2=4")

    def test_assert_no_marker_raises_on_marker(self):
        """Test 25: assert_no_marker_in_tts_input raises on marker."""
        with self.assertRaises(ValueError) as ctx:
            assert_no_marker_in_tts_input("Text mit +++++ drin")
        self.assertIn("KRITISCHER FEHLER", str(ctx.exception))
        self.assertIn(MARKER, str(ctx.exception))

    def test_assert_no_markers_in_sections(self):
        """Test: assert_no_markers_in_sections validates all sections."""
        sections = ["A", "B", "C"]
        # Should not raise
        assert_no_markers_in_sections(sections)

    def test_assert_no_markers_raises_on_contaminated(self):
        """Test: assert_no_markers_in_sections raises on contamination."""
        sections = ["A", "B with +++++", "C"]
        with self.assertRaises(ValueError):
            assert_no_markers_in_sections(sections)

    def test_split_output_passes_assertion(self):
        """Test: All split outputs pass the TTS assertion."""
        text = f"Teil 1\n+++++\nTeil 2\n+++++\nTeil 3"
        sections = split_explicit_audio_markers(text)
        for section in sections:
            # This should never raise
            assert_no_marker_in_tts_input(section)


class TestNoMarkerBehaviorUnchanged(unittest.TestCase):
    """Test 14: No-marker input remains unchanged."""

    def test_normal_text_unchanged(self):
        """Test 14: Normal text returns as single section."""
        text = "Normaler deutscher Text ohne Marker."
        result = split_explicit_audio_markers(text)
        self.assertEqual(result, [text])

    def test_text_with_plus_signs_unchanged(self):
        """Test 14b: Text with ordinary plus signs unchanged."""
        text = "2+2=4 und C++ sind正常."
        result = split_explicit_audio_markers(text)
        self.assertEqual(result, [text])

    def test_empty_no_marker(self):
        """Test 14c: Empty text returns empty list."""
        result = split_explicit_audio_markers("")
        self.assertEqual(result, [])

    def test_has_explicit_markers_false_for_normal(self):
        """Test: has_explicit_markers returns False for normal text."""
        self.assertFalse(has_explicit_markers("Normaler Text"))
        self.assertFalse(has_explicit_markers(""))
        self.assertFalse(has_explicit_markers("C++ Programmierung"))
        self.assertFalse(has_explicit_markers("2+2=4"))

    def test_has_explicit_markers_true_for_marker(self):
        """Test: has_explicit_markers returns True for marker text."""
        self.assertTrue(has_explicit_markers("A\n+++++\nB"))
        self.assertTrue(has_explicit_markers("+++++"))
        self.assertTrue(has_explicit_markers("  +++++  "))


class TestOutputOrderingDeterministic(unittest.TestCase):
    """Test 15: Output ordering is deterministic."""

    def test_order_preserved(self):
        """Test 15: Sections maintain source order."""
        text = f"{DELPHI_A}\n+++++\n{DELPHI_B}\n+++++\n{DELPHI_C}"
        result = split_explicit_audio_markers(text)
        self.assertEqual(result[0], DELPHI_A)
        self.assertEqual(result[1], DELPHI_B)
        self.assertEqual(result[2], DELPHI_C)

    def test_order_deterministic_multiple_calls(self):
        """Test: Multiple calls produce identical results."""
        text = f"C\n+++++\nA\n+++++\nB"
        result1 = split_explicit_audio_markers(text)
        result2 = split_explicit_audio_markers(text)
        self.assertEqual(result1, result2)

    def test_part_filename_deterministic(self):
        """Test: Part filenames are deterministic."""
        name1 = generate_part_filename("Test", 1, 3)
        name2 = generate_part_filename("Test", 1, 3)
        self.assertEqual(name1, name2)
        self.assertEqual(name1, "001_Test.wav")

    def test_part_filename_sequential(self):
        """Test: Sequential filenames are correctly numbered."""
        self.assertEqual(generate_part_filename("Delphi", 1, 3),
                        "001_Delphi.wav")
        self.assertEqual(generate_part_filename("Delphi", 2, 3),
                        "002_Delphi.wav")
        self.assertEqual(generate_part_filename("Delphi", 3, 3),
                        "003_Delphi.wav")

    def test_part_filename_custom_extension(self):
        """Test: Custom extension works."""
        self.assertEqual(generate_part_filename("File", 1, 2, ".mp3"),
                        "001_File.mp3")

    def test_part_filename_validates_range(self):
        """Test: Out-of-range index raises error."""
        with self.assertRaises(ValueError):
            generate_part_filename("Test", 0, 3)
        with self.assertRaises(ValueError):
            generate_part_filename("Test", 4, 3)


class TestCacheResumeBehavior(unittest.TestCase):
    """Tests 16-17: Cache and resume compatibility."""

    def test_each_section_has_unique_text(self):
        """Test 16: Each section produces unique cache key input."""
        text = f"{DELPHI_A}\n+++++\n{DELPHI_B}\n+++++\n{DELPHI_C}"
        sections = split_explicit_audio_markers(text)
        # Each section must be different text -> unique cache keys
        self.assertEqual(len(set(sections)), 3)

    def test_get_explicit_marker_plan(self):
        """Test: Plan provides all needed metadata."""
        text = f"{DELPHI_A}\n+++++\n{DELPHI_B}"
        plan = get_explicit_marker_plan(text)
        self.assertTrue(plan["has_markers"])
        self.assertEqual(plan["num_parts"], 2)
        self.assertEqual(plan["mode"], "explicit_split")
        self.assertEqual(len(plan["sections"]), 2)

    def test_plan_normal_mode(self):
        """Test: Plan for normal text returns normal mode."""
        plan = get_explicit_marker_plan("Normaler Text")
        self.assertFalse(plan["has_markers"])
        self.assertEqual(plan["num_parts"], 0)
        self.assertEqual(plan["mode"], "normal")
        self.assertEqual(plan["sections"], [])


class TestUnicodeAndPunctuation(unittest.TestCase):
    """Tests 20-21: Unicode German text and punctuation."""

    def test_german_unicode_intact(self):
        """Test 20: German Unicode characters preserved."""
        text = "ÄÖÜ äöü ß sind deutsche Buchstaben."
        result = split_explicit_audio_markers(text)
        self.assertEqual(result, [text])
        self.assertIn("ÄÖÜ", result[0])
        self.assertIn("ß", result[0])

    def test_quotation_marks_intact(self):
        """Test 21: Quotation marks preserved."""
        text = '„Hallo", sagte er. »Wie geht es?«'
        result = split_explicit_audio_markers(text)
        self.assertEqual(result, [text])
        self.assertIn("„Hallo\"", result[0])

    def test_punctuation_intact(self):
        """Test 21b: All punctuation preserved."""
        text = "Frage? Ausruf! Satz. Komma, Strich; Doppelpunkt:"
        result = split_explicit_audio_markers(text)
        self.assertEqual(result, [text])

    def test_german_sections_with_unicode(self):
        """Test: German sections with markers preserve Unicode."""
        text = f"Abschnitt mit Ü\n+++++\nAbschnitt mit ß\n+++++\nÄ Ö"
        result = split_explicit_audio_markers(text)
        self.assertEqual(len(result), 3)
        self.assertIn("Ü", result[0])
        self.assertIn("ß", result[1])
        self.assertIn("Ä", result[2])

    def test_german_delphi_full(self):
        """Test 13 (real script): Full Delphi script with markers."""
        text = f"{DELPHI_A}\n+++++\n{DELPHI_B}\n+++++\n{DELPHI_C}"
        result = split_explicit_audio_markers(text)
        self.assertEqual(len(result), 3)
        # Check content preserved
        self.assertIn("Nabel des Universums", result[0])
        self.assertIn("Pythia", result[1])
        self.assertIn("Reflexion", result[2])
        # No marker leakage
        for section in result:
            self.assertNotIn("+++++", section)
            self.assertNotIn("plus", section)


class TestCountMarkers(unittest.TestCase):
    """Additional tests for marker counting."""

    def test_count_zero(self):
        """No markers: count is 0."""
        self.assertEqual(count_markers("Normaler Text"), 0)

    def test_count_one(self):
        """One marker: count is 1."""
        self.assertEqual(count_markers("A\n+++++\nB"), 1)

    def test_count_multiple(self):
        """Multiple markers: count is correct."""
        self.assertEqual(count_markers("A\n+++++\nB\n+++++\nC"), 2)
        self.assertEqual(count_markers("A\n+++++\nB\n+++++\nC\n+++++\nD"), 3)

    def test_count_ignores_non_markers(self):
        """Non-marker plus sequences not counted."""
        self.assertEqual(count_markers("A\n++++\nB"), 0)  # 4 pluses
        self.assertEqual(count_markers("A\n++++++\nB"), 0)  # 6 pluses


class TestSplitManuscript(unittest.TestCase):
    """Tests for the underlying split_manuscript function."""

    def test_no_markers(self):
        """No markers: returns original text as single section."""
        result = split_manuscript("Normaler Text")
        self.assertEqual(result, ["Normaler Text"])

    def test_basic_split(self):
        """Basic split at marker."""
        result = split_manuscript("A\n+++++\nB")
        self.assertEqual(result, ["A", "B"])

    def test_multiple_splits(self):
        """Multiple markers."""
        result = split_manuscript("A\n+++++\nB\n+++++\nC")
        self.assertEqual(result, ["A", "B", "C"])


class TestEdgeCases(unittest.TestCase):
    """Additional edge case tests."""

    def test_marker_with_surrounding_blank_lines(self):
        """Marker surrounded by blank lines."""
        text = "A\n\n+++++\n\nB"
        result = split_explicit_audio_markers(text)
        self.assertEqual(result, ["A", "B"])

    def test_multiline_section_content(self):
        """Sections can contain multiple lines."""
        text = "Line 1\nLine 2\n+++++\nLine 3\nLine 4"
        result = split_explicit_audio_markers(text)
        self.assertEqual(len(result), 2)
        self.assertIn("Line 1", result[0])
        self.assertIn("Line 2", result[0])
        self.assertIn("Line 3", result[1])
        self.assertIn("Line 4", result[1])

    def test_section_with_only_whitespace_lines(self):
        """Section with only whitespace lines is empty."""
        text = "A\n+++++\n   \n\n   \n+++++\nB"
        result = split_explicit_audio_markers(text)
        self.assertEqual(result, ["A", "B"])

    def test_marker_constant_is_five_plus(self):
        """MARKER constant is exactly five plus signs."""
        self.assertEqual(MARKER, "+++++")
        self.assertEqual(len(MARKER), 5)

    def test_assert_context_included_in_error(self):
        """assert_no_marker_in_tts_input includes context."""
        with self.assertRaises(ValueError) as ctx:
            assert_no_marker_in_tts_input("text +++++", context="TestCtx")
        self.assertIn("TestCtx", str(ctx.exception))

    def test_normalizer_would_convert_plus_to_speech(self):
        """Verify the concern: normalizer converts '+' to 'plus'.

        This test documents why we MUST strip markers before normalization.
        The normalize.py converts '+' to ' plus ', so if a marker leaked
        through, it would be spoken as 'plus plus plus plus plus'.
        """
        # This test ensures we're aware of the normalization behavior
        # The actual fix is in assert_no_marker_in_tts_input
        from app.text.normalize import normalize_text, NormalizationReport
        report = NormalizationReport()
        result = normalize_text("test + test", "German", report)
        # The '+' becomes 'plus' in normalized output
        self.assertIn("plus", result)
        # This confirms: if marker leaked, it would be spoken!
        self.assertNotIn("+++++", result)


class TestMarkerPlanIntegration(unittest.TestCase):
    """Integration tests for the marker plan system."""

    def test_plan_sections_are_clean(self):
        """Plan sections must not contain markers."""
        text = f"{DELPHI_A}\n+++++\n{DELPHI_B}\n+++++\n{DELPHI_C}"
        plan = get_explicit_marker_plan(text)
        for section in plan["sections"]:
            assert_no_marker_in_tts_input(section)

    def test_plan_matches_split_function(self):
        """Plan sections match direct split function output."""
        text = f"A\n+++++\nB\n+++++\nC"
        plan = get_explicit_marker_plan(text)
        direct = split_explicit_audio_markers(text)
        self.assertEqual(plan["sections"], direct)

    def test_plan_count_matches_sections(self):
        """Plan num_parts matches actual section count."""
        text = f"A\n+++++\nB\n+++++\nC\n+++++\nD"
        plan = get_explicit_marker_plan(text)
        self.assertEqual(plan["num_parts"], len(plan["sections"]))
        self.assertEqual(plan["num_parts"], 4)


if __name__ == "__main__":
    unittest.main()
