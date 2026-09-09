from pathlib import Path

app = Path(r"C:\Users\johan\OneDrive\Desktop\fertige projekte\Apps\VoiceoverAPPnew\VoiceOverApp_2.0.0_GUI")
g = app / "app" / "prosody" / "german.py"
i = app / "app" / "prosody" / "instruct.py"

gt = g.read_text(encoding="utf-8")
it = i.read_text(encoding="utf-8")

# --- german.py --------------------------------------------------------------
if "def has_comma_enumeration(" not in gt:
    anchor = 'def german_instruct_hints(profile_or_role, language: str = "German",'
    helper = '''def has_comma_enumeration(text: str) -> bool:
    """Erkennt kompakte Komma-Aufzählungen innerhalb eines einzelnen Satzes."""
    t = " ".join(str(text or "").split())
    if t.count(",") < 2:
        return False

    parts = [p.strip() for p in t.split(",")]
    if len(parts) < 3:
        return False

    tail = parts[-1]
    if not re.search(r"\\b(?:und|oder)\\b", tail, re.I):
        return False

    last = re.split(r"\\b(?:und|oder)\\b", tail, maxsplit=1, flags=re.I)[0].strip()
    items = [p for p in parts[:-1] if p] + ([last] if last else [])

    if not all(1 <= len(p.split()) <= 5 for p in items):
        return False

    if any(
        re.match(
            r"^(weil|obwohl|damit|während|wenn|falls|sobald|bevor|nachdem|indem|dass)\\b",
            p,
            re.I,
        )
        for p in items
    ):
        return False

    return True


'''
    if anchor not in gt:
        raise SystemExit("GERMAN_ANCHOR_NOT_FOUND")
    gt = gt.replace(anchor, helper + anchor, 1)

old_sig = 'def german_instruct_hints(profile_or_role, language: str = "German",\n'
new_sig = 'def german_instruct_hints(profile_or_role, language: str = "German",\n                          sentence_text: str | None = None,\n'
if old_sig in gt and "sentence_text: str | None = None" not in gt:
    gt = gt.replace(old_sig, new_sig, 1)

marker = '    hints: list[str] = []\n'
hint = '''    hints: list[str] = []
    if sentence_text and has_comma_enumeration(sentence_text) and language.lower().startswith("ger"):
        hints.append(
            "Use clear, natural micro-pauses between items in this compact comma-separated "
            "enumeration; do not run the items together, and keep the final item connected "
            "naturally with the closing und."
        )
'''
if 'Use clear, natural micro-pauses between items in this compact comma-separated enumeration' not in gt:
    pos = gt.find(marker, gt.find("def german_instruct_hints("))
    if pos < 0:
        raise SystemExit("HINT_MARKER_NOT_FOUND")
    gt = gt[:pos] + hint + gt[pos + len(marker):]

# --- instruct.py ------------------------------------------------------------
old_call = '''                long_sentence=long_sentence,
                in_short_run=(short_run_pos is not None),
'''
new_call = '''                long_sentence=long_sentence,
                sentence_text=text,
                in_short_run=(short_run_pos is not None),
'''
if "sentence_text=text" not in it:
    if old_call not in it:
        raise SystemExit("INSTRUCT_CALL_ANCHOR_NOT_FOUND")
    it = it.replace(old_call, new_call, 1)

g.write_text(gt, encoding="utf-8", newline="\n")
i.write_text(it, encoding="utf-8", newline="\n")
print("PATCH_WRITTEN")
