"""Text-Modul: Analyse, Normalisierung, Sprachprüfung, Script-Splitting."""
from .analyze import AnalysisResult, Block, TextStats, analyze_text, split_blocks, split_sentences  # noqa: F401
from .langdetect import check_language_plausibility, detect_language_scores  # noqa: F401
from .normalize import NormalizationReport, normalize_text  # noqa: F401
from .script_split import (  # noqa: F401
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
