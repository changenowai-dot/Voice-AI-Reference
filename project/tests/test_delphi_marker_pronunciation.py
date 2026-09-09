"""Tests: Delphi marker pipeline and pronunciation system.

Verifies:
- 16 markers create exactly 17 blocks
- Each block creates ONE final output (not per-segment)
- Pronunciation overrides (Psychologie etc.) are applied correctly
- Internal segmentation doesn't affect final output count
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pronunciation import PronunciationDictionary, PronunciationEngine
from app.text.script_split import split_manuscript, MARKER


class TestDelphiMarkerCount(unittest.TestCase):
    """Test: 16 markers create exactly 17 blocks."""
    
    def test_16_markers_17_blocks(self):
        """16 +++++ markers must create exactly 17 blocks."""
        # Build text with exactly 16 markers
        blocks = [f"Block {i} content" for i in range(1, 18)]
        text = f"\n{MARKER}\n".join(blocks)
        
        # Verify we have 16 markers
        marker_count = text.count(MARKER)
        self.assertEqual(marker_count, 16, "Must have exactly 16 markers")
        
        # Split and verify 17 blocks
        sections = split_manuscript(text)
        self.assertEqual(len(sections), 17, 
                        "16 markers must create exactly 17 blocks")
    
    def test_marker_never_in_output(self):
        """Marker must never appear in any output section."""
        blocks = [f"Block {i}" for i in range(1, 18)]
        text = f"\n{MARKER}\n".join(blocks)
        sections = split_manuscript(text)
        
        for i, section in enumerate(sections, 1):
            self.assertNotIn(MARKER, section,
                           f"Marker found in section {i}")


class TestLongBlockSingleOutput(unittest.TestCase):
    """Test: Long blocks (>420 chars) create ONE output."""
    
    def test_long_block_creates_one_section(self):
        """A block with >1000 chars is still ONE section."""
        # Create a very long block
        long_text = "Dies ist ein sehr langer Text. " * 50
        text = f"Block 1\n{MARKER}\n{long_text}\n{MARKER}\nBlock 3"
        
        sections = split_manuscript(text)
        
        # Should have 3 sections
        self.assertEqual(len(sections), 3)
        
        # The middle section should be the full long text
        self.assertEqual(sections[1].strip(), long_text.strip())
        
        # Verify it's really long (>700 chars)
        self.assertGreater(len(sections[1]), 700,
                          "Middle section should be >700 chars")


class TestPronunciationPsychologie(unittest.TestCase):
    """Test: 'Psychologie' pronunciation override."""
    
    def test_psychologie_in_builtins(self):
        """'Psychologie' must be in built-in dictionary."""
        d = PronunciationDictionary()
        builtins = d.builtin_entries()
        self.assertIn("Psychologie", builtins,
                     "'Psychologie' must be in German builtins")
    
    def test_psychologie_pronunciation_applied(self):
        """'Psychologie' must be replaced with respelled version."""
        d = PronunciationDictionary()
        engine = PronunciationEngine(d, tech_germanization=True)
        
        text = "Die Psychologie untersucht das Verhalten."
        result = engine.process(text, "German")
        
        # The tech layer provides "Psy-cho-LO-gie" (with stress markers)
        self.assertIn("Psy-cho-LO-gie", result.text,
                     "Psychologie must be replaced with Psy-cho-LO-gie")
        
        # Verify the replacement was recorded
        psych_replacements = [r for r in result.replacements 
                             if "Psychologie" in r["from"]]
        self.assertGreater(len(psych_replacements), 0,
                          "Must have at least one replacement for Psychologie")
    
    def test_psychologie_case_insensitive(self):
        """Pronunciation must work for different cases."""
        d = PronunciationDictionary()
        engine = PronunciationEngine(d, tech_germanization=True)
        
        # Test uppercase (sentence start)
        text1 = "Psychologie ist wichtig."
        result1 = engine.process(text1, "German")
        self.assertGreater(len(result1.replacements), 0)
        
        # Test lowercase
        text2 = "Die psychologie ist wichtig."
        result2 = engine.process(text2, "German")
        self.assertGreater(len(result2.replacements), 0)
    
    def test_psychologie_in_long_text(self):
        """Pronunciation must work in long texts with multiple occurrences."""
        d = PronunciationDictionary()
        engine = PronunciationEngine(d, tech_germanization=True)
        
        # Create long text with multiple "Psychologie" occurrences
        text = ("Die Psychologie ist faszinierend. "
                "In der Psychologie gibt es viele Bereiche. "
                "Die moderne Psychologie nutzt verschiedene Methoden.")
        
        result = engine.process(text, "German")
        
        # Should have multiple replacements
        psych_replacements = [r for r in result.replacements 
                             if "Psy-cho-LO-gie" in r["to"]]
        self.assertGreaterEqual(len(psych_replacements), 3,
                               "Should have at least 3 replacements")


class TestPronunciationOtherTerms(unittest.TestCase):
    """Test: Other problematic German terms."""
    
    def test_epistemologie(self):
        """'Epistemologie' must be in builtins and applied."""
        d = PronunciationDictionary()
        engine = PronunciationEngine(d, tech_germanization=True)
        
        # Check builtin
        builtins = d.builtin_entries()
        self.assertIn("Epistemologie", builtins)
        
        # Test application
        text = "Die Epistemologie ist ein Teil der Philosophie."
        result = engine.process(text, "German")
        
        # The actual output uses detailed syllable separation with hyphens
        self.assertIn("E-pis-te", result.text)
        self.assertIn("mo-LO-gie", result.text)
    
    def test_chatgpt(self):
        """'ChatGPT' must be pronounced as 'Tschät G P T'."""
        d = PronunciationDictionary()
        engine = PronunciationEngine(d, tech_germanization=True)
        
        text = "ChatGPT ist ein Sprachmodell."
        result = engine.process(text, "German")
        
        self.assertIn("Tschät", result.text)
        self.assertIn("G P T", result.text)


class TestPronunciationPersistent(unittest.TestCase):
    """Test: Pronunciation overrides are persistent."""
    
    def test_user_override_persists(self):
        """User pronunciation overrides must persist across instances."""
        d1 = PronunciationDictionary()
        d1.clear_all()
        
        # Add custom override
        d1.add_entry("Testwort", "Test-wort")
        
        # Create new instance (should load from file)
        d2 = PronunciationDictionary()
        
        # Override should persist
        self.assertIn("Testwort", d2.user_entries())
        
        # Cleanup
        d2.clear_all()
    
    def test_user_override_applied_to_segments(self):
        """User overrides must be applied to all segments."""
        d = PronunciationDictionary()
        d.clear_all()
        d.add_entry("Spezialbegriff", "Spe-zial-begriff")
        
        engine = PronunciationEngine(d, tech_germanization=True)
        
        # Test in multiple "segments"
        for i in range(3):
            text = f"Segment {i}: Der Spezialbegriff ist wichtig."
            result = engine.process(text, "German")
            self.assertIn("Spe-zial-begriff", result.text,
                         f"Override not applied in segment {i}")
        
        # Cleanup
        d.clear_all()


class TestPipelineIntegration(unittest.TestCase):
    """Integration tests for the full pipeline."""
    
    def test_marker_split_preserves_order(self):
        """Marker splitting must preserve original order."""
        blocks = [f"Block {i}" for i in range(1, 18)]
        text = f"\n{MARKER}\n".join(blocks)
        
        sections = split_manuscript(text)
        
        # Verify order
        for i, section in enumerate(sections, 1):
            self.assertEqual(section.strip(), f"Block {i}",
                           f"Block {i} is not in correct position")
    
    def test_marker_never_reaches_tts_simulation(self):
        """Simulate that marker never reaches TTS input."""
        text = f"Block 1\n{MARKER}\nBlock 2\n{MARKER}\nBlock 3"
        sections = split_manuscript(text)
        
        # Each section would be sent to TTS
        for section in sections:
            # Verify no marker in any section
            self.assertNotIn(MARKER, section,
                           "Marker would reach TTS - CRITICAL BUG!")
            
            # Simulate pronunciation processing
            d = PronunciationDictionary()
            engine = PronunciationEngine(d, tech_germanization=True)
            result = engine.process(section, "German")
            
            # Still no marker after pronunciation
            self.assertNotIn(MARKER, result.text,
                           "Marker appeared after pronunciation processing")


if __name__ == '__main__':
    unittest.main()
