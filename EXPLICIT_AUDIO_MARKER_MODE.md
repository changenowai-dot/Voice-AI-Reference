# Explicit Audio Marker Mode

## Overview

The Explicit Audio Marker Mode allows you to split a single input text file into multiple separate audio output files using the `+++++` marker. Each section between markers becomes an independent audio file with deterministic naming.

## Key Features

- **Opt-in**: Only activates when `+++++` markers are present in the input
- **No marker speech**: The `+++++` marker is never sent to TTS and never spoken
- **Backward compatible**: Input without markers uses the normal processing pipeline unchanged
- **Deterministic output**: Files named `001_basename.wav`, `002_basename.wav`, etc.
- **Resume capable**: Each section has independent cache/resume
- **Production-safe**: Defensive validation prevents marker leakage to TTS

## Usage

### Input File Example

```text
Es gab einen Ort in der antiken Welt, der als der Nabel des Universums galt.
+++++
Die Pythia, die Hohepriesterin, saß auf einem Dreifuß über einem Erdspalt.
+++++
Die wahre Macht von Delphi lag nicht in der Wahrsagerei. Sie lag in der Reflexion.
```

### Output Files

```
001_Delphi_Oracle.wav
002_Delphi_Oracle.wav
003_Delphi_Oracle.wav
```

Each file contains the audio for its corresponding section.

## Marker Rules

### What IS a Marker

A line containing **exactly** five plus signs (`+++++`), with optional whitespace:

```text
+++++          ✓ Valid marker
  +++++        ✓ Valid marker (whitespace allowed)
	+++++	    ✓ Valid marker (tabs allowed)
```

### What is NOT a Marker

```text
++++           ✗ Only 4 plus signs
++++++         ✗ 6 plus signs
abc+++++       ✗ Text before marker
+++++abc       ✗ Text after marker
```

### Ordinary Plus Signs Preserved

Plus signs in normal text are **not** treated as markers:

```text
2+2=4          ✓ Preserved as-is
C++            ✓ Preserved as-is
A+B            ✓ Preserved as-is
```

## Empty Sections

Empty sections (caused by leading, trailing, or repeated markers) are automatically skipped:

```text
+++++              ← Leading marker (ignored)
Text A
+++++
+++++              ← Repeated marker (treated as one)
Text B
+++++              ← Trailing marker (ignored)
```

Result: 2 files (Text A, Text B)

## Technical Details

### Implementation Location

- **Parser**: `project/app/text/script_split.py`
- **Integration**: `project/app/project/pipeline.py` (method `_process_explicit_marker_file`)
- **Validation**: `assert_no_marker_in_tts_input()` called before every TTS synthesis

### Defensive Validation

The system includes multiple safety checks to ensure the marker never reaches TTS:

1. **Parser level**: `split_explicit_audio_markers()` filters out markers
2. **Pipeline level**: `assert_no_marker_in_tts_input()` validates before synthesis
3. **Normalization level**: Even if marker leaked, `normalize_text()` converts `+` to `plus`

### Cache and Resume

Each section has:
- Independent cache keys (based on section text + parameters)
- Independent resume state
- Unique project ID: `{output_stem}__{text_hash}`

If section 1 and 2 complete but section 3 fails, rerunning will:
- Reuse cached audio for sections 1 and 2
- Regenerate only section 3

### Output Naming

Format: `{NNN}_{base_name}.{ext}`

Examples:
- `001_Delphi.wav`
- `002_Delphi.wav`
- `003_Delphi.mp3`

The base name is derived from the input filename.

## Integration with Existing Features

### Normalization

Each section goes through the full normalization pipeline:
- Number conversion (2024 → "zweitausendvierundzwanzig")
- Abbreviation expansion (z.B. → "zum Beispiel")
- Pronunciation optimization
- Plus sign handling (`+` → "plus" in speech)

### Segmentation

Each section is independently segmented according to the configured parameters:
- `segment_target_chars`
- `segment_min_chars`
- `segment_max_chars`

### Audio Post-Processing

Each output file undergoes the full production pipeline:
- Quality control (QC)
- Regeneration if needed
- Assembly
- Mastering (EBU R128 loudness normalization)

### No Impact on Normal Mode

Input files **without** `+++++` markers:
- Use the normal processing pipeline
- Produce a single output file
- No change in behavior from before this feature

## Testing

### Test Coverage

67 comprehensive tests in `project/tests/test_explicit_audio_markers.py`:

- Basic marker splitting (single, multi-line, with whitespace)
- Empty segment handling (leading/trailing/repeated markers)
- Exact five-plus marker recognition
- Ordinary plus characters preserved
- Marker never reaches TTS input
- No-marker input unchanged
- Output ordering deterministic
- Cache/resume compatibility
- Unicode German text preserved
- Quotation marks and punctuation intact
- Edge cases (empty input, only markers, etc.)

### Running Tests

```bash
cd project
python3 -m unittest tests/test_explicit_audio_markers.py -v
```

## Target Hardware Validation (RTX 5060)

To validate on your RTX 5060 system:

```powershell
# 1. Create test input file
@"
Es gab einen Ort in der antiken Welt.
+++++
Die Pythia saß auf einem Dreifuß.
+++++
Die wahre Macht von Delphi lag in der Reflexion.
"@ | Out-File -Encoding UTF8 input\Delphi_Test.txt

# 2. Run benchmark
python benchmark\phase4_benchmark.py

# 3. Check output
Get-ChildItem output\00*.wav | Select-Object Name, Length

# 4. Verify no marker in logs
Select-String -Path logs\*.log -Pattern "\+\+\+\+\+" -SimpleMatch
```

Expected results:
- 3 separate WAV files: `001_Delphi_Test.wav`, `002_Delphi_Test.wav`, `003_Delphi_Test.wav`
- No `+++++` in any log output
- Each file plays the corresponding section
- Golden Reference SHA-256 unchanged

## Limitations and Known Behavior

1. **No nested markers**: `+++++` inside a section is not supported
2. **No marker escaping**: Cannot include literal `+++++` in output text
3. **File-per-section**: Cannot concatenate sections into a single output
4. **No marker metadata**: Markers don't carry additional information (chapter titles, etc.)

## Future Enhancements (Not Implemented)

Potential future additions:
- Marker with metadata: `+++++ Chapter 1: Introduction`
- Nested markers for hierarchical structure
- Marker-based pause/duration control
- Export marker positions as chapter markers in output

## Compatibility

- ✅ Backward compatible with existing input files
- ✅ No changes to production configuration
- ✅ No impact on Phase 4 safepoint
- ✅ Works with all existing TTS engines
- ✅ Compatible with cache/resume system
- ✅ Supports batch processing

## Security

The marker system is designed to be **fail-safe**:
- Marker is stripped before any TTS processing
- Multiple validation layers prevent leakage
- Even if marker leaks, normalization converts it to speech-safe form
- Clear error messages if validation fails

## References

- Implementation: `project/app/text/script_split.py`
- Pipeline integration: `project/app/project/pipeline.py:165-195`
- Test suite: `project/tests/test_explicit_audio_markers.py`
- Phase 4 Safepoint: `PHASE4_AUDIO_SAFEPOINT_20260906` (unchanged)
