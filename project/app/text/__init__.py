"""Text-Modul: Analyse, Normalisierung, Sprachprüfung."""
from .analyze import AnalysisResult, Block, TextStats, analyze_text, split_blocks, split_sentences  # noqa: F401
from .langdetect import check_language_plausibility, detect_language_scores  # noqa: F401
from .normalize import NormalizationReport, normalize_text  # noqa: F401
