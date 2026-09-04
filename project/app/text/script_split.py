"""Long-Script-Splitting (§8/§9) – NUR manueller Marker, nie Zeitbasis.

Einziger gültiger Abschnittsmarker: eine Zeile, die nach trimmen
EXAKT „+++++“ ist. Alles andere (++++, ++++++, abc+++++, „+++++“ im
Fließtext) ist KEIN Marker. Keine zeitbasierten Schnitte (§9) – die
Abschnittslänge ergibt sich ausschließlich aus dem Manuskript.
"""
from __future__ import annotations

import re

MARKER = "+++++"
_LINE_RE = re.compile(r"^[ \t]*\+\+\+\+\+[ \t]*$")   # exakt 5, allein


def is_marker_line(line: str) -> bool:
    """§8 Technik: trimmen + exakter Vergleich mit '+++++'."""
    return _LINE_RE.match(line) is not None


def count_markers(text: str) -> int:
    return sum(1 for line in text.splitlines() if is_marker_line(line))


def split_manuscript(text: str) -> list[str]:
    """Zerlegt das Manuskript an Markerzeilen in Abschnitte.

    Leerzeilen vor/nach Markern sind erlaubt; leere Abschnitte (z. B.
    Marker am Anfang/Ende oder doppelte Marker) werden verworfen.
    Ohne Marker → [text] (exakt bisheriges Verhalten).
    """
    sections: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if is_marker_line(line):
            sections.append("\n".join(current))
            current = []
        else:
            current.append(line)
    sections.append("\n".join(current))
    cleaned = [s.strip("\n").strip() for s in sections]
    return [s for s in cleaned if s] or ([text.strip()] if text.strip()
                                         else [])


def part_name(base: str, index_1based: int) -> str:
    """§12: stabile, sortierbare Part-Namen (Part_001…)."""
    return f"{base}_Part_{index_1based:03d}"


FULLSCRIPT_SUFFIX = "FullScript"


def split_plan(text: str, enabled: bool) -> dict:
    """Plan für den Job-Runner: {'use_split', 'sections', 'parts'}."""
    markers = count_markers(text)
    if not enabled or markers == 0:
        return {"use_split": False, "sections": [text], "parts": 1,
                "markers": markers}
    sections = split_manuscript(text)
    return {"use_split": True, "sections": sections,
            "parts": len(sections), "markers": markers}
