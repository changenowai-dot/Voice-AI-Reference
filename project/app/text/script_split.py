"""Long-Script-Splitting (§8/§9) – NUR manueller Marker, nie Zeitbasis.

Einziger gültiger Abschnittsmarker: eine Zeile, die nach trimmen
EXAKT „+++++" ist. Alles andere (++++, ++++++, abc+++++, „+++++" im
Fließtext) ist KEIN Marker. Keine zeitbasierten Schnitte (§9) – die
Abschnittslänge ergibt sich ausschließlich aus dem Manuskript.

Explicit Audio Marker Mode:
  Der Marker „+++++" trennt Abschnitte, die als eigenständige Audio-Dateien
  ausgegeben werden sollen. Der Marker selbst wird NIEMALS an die TTS-Engine
  übergeben und NIEMALS gesprochen.

  Beispiel:
    Text A
    +++++
    Text B
    +++++
    Text C

  Ergibt 3 separate Audio-Dateien:
    001_Text_A.wav
    002_Text_B.wav
    003_Text_C.wav
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


# =============================================================================
# Explicit Audio Marker Mode – Neue Funktionen
# =============================================================================

def has_explicit_markers(text: str) -> bool:
    """Prüft ob der Text explizite Audio-Marker enthält.

    Gibt True zurück wenn mindestens eine Markerzeile vorhanden ist.
    Ein Marker ist eine Zeile die nach trimmen exakt ``+++++`` ist.

    Args:
        text: Eingabetext

    Returns:
        True wenn mindestens ein Marker vorhanden, False sonst

    Example:
        >>> has_explicit_markers("Text A\\n+++++\\nText B")
        True
        >>> has_explicit_markers("Normaler Text ohne Marker")
        False
    """
    if not text:
        return False
    return any(is_marker_line(line) for line in text.splitlines())


def split_explicit_audio_markers(text: str) -> list[str]:
    """Zerlegt Text an ``+++++``-Markern in separate Audio-Abschnitte.

    Dies ist die kanonische Funktion für den Explicit Audio Marker Mode.
    Jeder Abschnitt wird als eigenständige Audio-Datei ausgegeben.

    Verhalten:
      - Markerzeilen werden erkannt (exakt ``+++++`` nach trimmen)
      - Abschnitte zwischen Markern werden extrahiert
      - Leere/Whitespace-only Abschnitte werden verworfen
      - Führende/trailing Marker erzeugen keine leeren Abschnitte
      - Aufeinanderfolgende Marker werden wie ein einzelner behandelt
      - Ohne Marker wird der gesamte Text als ein Abschnitt zurückgegeben

    Args:
        text: Eingabetext mit optionalen ``+++++``-Markern

    Returns:
        Liste der nicht-leeren Textabschnitte (mindestens 1 wenn Text vorhanden)

    Example:
        >>> split_explicit_audio_markers("A\\n+++++\\nB\\n+++++\\nC")
        ['A', 'B', 'C']
        >>> split_explicit_audio_markers("+++++\\nA\\n+++++")
        ['A']
        >>> split_explicit_audio_markers("A\\n+++++\\n+++++\\nB")
        ['A', 'B']
        >>> split_explicit_audio_markers("Normaler Text")
        ['Normaler Text']

    WICHTIG:
      - Der Marker ``+++++`` wird NIEMALS in den zurückgegebenen Abschnitten sein
      - Die Funktion garantiert: ``assert MARKER not in section`` für alle sections
    """
    if not text or not text.strip():
        return []

    # Wenn keine Marker vorhanden, gesamten Text als einen Abschnitt
    if not has_explicit_markers(text):
        return [text.strip()] if text.strip() else []

    # Split an Markerzeilen
    raw_sections = split_manuscript(text)

    # Filtere leere/Whitespace-only Abschnitte
    # WICHTIG: split_manuscript hat einen Fallback der den Originaltext
    # zurückgibt wenn alle Abschnitte leer sind - das dürfen wir hier
    # NICHT verwenden, da der Originaltext noch Marker enthält!
    sections = [s.strip() for s in raw_sections
                if s and s.strip() and MARKER not in s]

    # Sicherheitscheck: Marker dürfen niemals in den Abschnitten sein
    for section in sections:
        if MARKER in section:
            raise ValueError(
                f"Interner Fehler: Marker '{MARKER}' in Abschnitt gefunden: "
                f"{section[:80]}..."
            )

    return sections


def assert_no_marker_in_tts_input(text: str, context: str = "") -> None:
    """Defensive Validierung: Stellt sicher dass kein Marker in TTS-Input ist.

    Diese Funktion MUSS unmittelbar vor der TTS-Synthese aufgerufen werden.
    Sie wirft eine ValueError wenn der Marker ``+++++`` im Text gefunden wird.

    Args:
        text: Der Text der an die TTS-Engine übergeben werden soll
        context: Optionaler Kontext für die Fehlermeldung (z.B. Dateiname)

    Raises:
        ValueError: Wenn der Marker im Text gefunden wird
    """
    if MARKER in text:
        ctx = f" ({context})" if context else ""
        raise ValueError(
            f"KRITISCHER FEHLER{ctx}: Marker '{MARKER}' in TTS-Input gefunden! "
            f"Der Marker darf NIEMALS an die TTS-Engine übergeben werden. "
            f"Text-Ausschnitt: {text[:100]}..."
        )


def assert_no_markers_in_sections(sections: list[str],
                                  context: str = "") -> None:
    """Validiert dass keine Marker in einer Liste von Abschnitten sind.

    Args:
        sections: Liste der zu validierenden Textabschnitte
        context: Optionaler Kontext für die Fehlermeldung

    Raises:
        ValueError: Wenn ein Marker in einem Abschnitt gefunden wird
    """
    for i, section in enumerate(sections):
        if MARKER in section:
            ctx = f" ({context})" if context else ""
            raise ValueError(
                f"KRITISCHER FEHLER{ctx}: Marker '{MARKER}' in Abschnitt "
                f"{i+1} gefunden! Text-Ausschnitt: {section[:100]}..."
            )


def generate_part_filename(base_name: str, part_index: int,
                           total_parts: int,
                           extension: str = ".wav") -> str:
    """Generiert deterministische Dateinamen für Explicit-Marker-Teile.

    Format: ``{NNN}_{base_name}{extension}``
    Beispiel: ``001_Delphi_Oracle.wav``, ``002_Delphi_Oracle.wav``

    Args:
        base_name: Basis-Dateiname (ohne Erweiterung)
        part_index: 1-basierter Index des Teils
        total_parts: Gesamtanzahl der Teile (für Validierung)
        extension: Dateiendung (default: ``.wav``)

    Returns:
        Formatierter Dateiname

    Example:
        >>> generate_part_filename("Delphi", 1, 3)
        '001_Delphi.wav'
        >>> generate_part_filename("Oracle", 2, 5, ".mp3")
        '002_Oracle.mp3'
    """
    if part_index < 1 or part_index > total_parts:
        raise ValueError(
            f"part_index {part_index} außerhalb des Bereichs "
            f"[1, {total_parts}]"
        )
    return f"{part_index:03d}_{base_name}{extension}"


def get_explicit_marker_plan(text: str) -> dict:
    """Erstellt einen Plan für die Explicit-Marker-Verarbeitung.

    Returns a dict mit allen relevanten Informationen:
      - ``has_markers``: bool ob Marker vorhanden sind
      - ``num_parts``: Anzahl der Teile (0 wenn keine Marker)
      - ``sections``: Liste der Textabschnitte (leer wenn keine Marker)
      - ``mode``: ``"explicit_split"`` oder ``"normal"``

    Args:
        text: Eingabetext

    Returns:
        Dictionary mit Verarbeitungsplan
    """
    if not has_explicit_markers(text):
        return {
            "has_markers": False,
            "num_parts": 0,
            "sections": [],
            "mode": "normal",
        }

    sections = split_explicit_audio_markers(text)
    return {
        "has_markers": True,
        "num_parts": len(sections),
        "sections": sections,
        "mode": "explicit_split",
    }
