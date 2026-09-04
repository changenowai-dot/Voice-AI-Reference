"""PDF-Import (§7) – lokal, stabil, inhaltsgetreu.

Extraktion via pypdf + behutsame Bereinigung von PDF-Artefakten:
Seitenumbrüche, Doppel-Leerzeichen, Trennstriche aus Zeilenumbrüchen,
Einzel-Ziffern-Zeilen (Seitennummern). Wörter, Zahlen und Namen werden
NICHT verändert (§7/§15-Geist).
"""
from __future__ import annotations

import re
from dataclasses import dataclass


class PdfImportError(RuntimeError):
    pass


@dataclass
class PdfImportResult:
    text: str
    pages: int
    chars: int
    words: int


def _cleanup(raw: str) -> str:
    # Zeilenenden vereinheitlichen
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    # Trennstrich am Zeilenende (PDF-Umbruch-Hyphen) zusammenfügen –
    # nur wenn danach ein Kleinbuchstabe folgt (typische Silbentrennung)
    raw = re.sub(r"([a-zäöüß])-\n([a-zäöüß])", r"\1\2", raw)
    # Zeilenumbrüche innerhalb eines Absatzes zu Leerzeichen
    raw = re.sub(r"(?<=[^\n])\n(?=[^\n])", " ", raw)
    # Seitennummern-/Artefakt-Zeilen: isolierte kurze Zahlen/Glyphen
    lines = [ln.strip() for ln in raw.split("\n")]
    keep = []
    for ln in lines:
        if re.fullmatch(r"\d{1,4}", ln):            # Seitenzahl allein
            continue
        if re.fullmatch(r"[^\wÄÖÜäöüß]{1,3}", ln):  # Glyphen-Müll
            continue
        keep.append(ln)
    raw = "\n".join(keep)
    # Whitespace normalisieren
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def extract_pdf_text(path) -> PdfImportResult:
    """Liest ein PDF und gibt bereinigten Text zurück (§7)."""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise PdfImportError(
            "PDF-Unterstützung fehlt (pypdf nicht installiert). "
            "Bitte install.ps1 erneut ausführen.") from e
    try:
        reader = PdfReader(str(path))
    except Exception as e:                           # noqa: BLE001
        raise PdfImportError(f"Ungültige oder unlesbare PDF-Datei: "
                             f"{e}") from e
    try:
        n_pages = len(reader.pages)
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:                        # noqa: BLE001
                parts.append("")
    except Exception as e:                           # noqa: BLE001
        raise PdfImportError(f"PDF konnte nicht gelesen werden: {e}") from e
    raw = "\n".join(parts)
    text = _cleanup(raw)
    words = re.findall(r"[^\s]+", text)
    if not words:
        raise PdfImportError(
            "Die PDF-Datei enthält keine extrahierbaren Wörter "
            "(möglicherweise ein reines Scan/Bild-PDF).")
    return PdfImportResult(text=text, pages=n_pages, chars=len(text),
                           words=len(words))
