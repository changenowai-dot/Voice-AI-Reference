# Long-Form Segmentation & QC — Manual Listening Checklist

Use this after each long-form benchmark run. Listen to the FULL output
(and at least two segment boundaries) for every preset. Score 1–5 per
category; write notes about WHERE the failure happened (timestamp).

**File:** `project/benchmark/longform/<voice_id>/<preset>/<text>.wav`

## Per-preset evaluation

| Category | 1 (bad) .. 5 (excellent) | Notes / timestamp |
|---|---|---|
| Intelligibility (words understandable, no mumbling) |  |  |
| Speaker identity (voice stays the SAME person) |  |  |
| Pitch stability (no sudden jumps / drones / tones) |  |  |
| Loudness consistency (no abrupt volume changes at segment joins) |  |  |
| Pacing / rhythm (natural, not mechanical, no rushed endings) |  |  |
| Pronunciation (names/numbers/foreign words correct) |  |  |
| No reference-text leakage ("There is a book…" should NOT appear) |  |  |
| Boundary smoothness (listen to 3 joins; no clicks/double-starts/cuts) |  |  |
| Long-form degradation (last minute same quality as first minute) |  |  |
| Overall narration quality |  |  |

## Red flags (instant reject)

- Persistent tonal hum / siren / sine-wave at any point
- 0.16s / sub-second collapse into near-silence mid-text
- Voice audibly changes person/gender at a segment boundary
- Words cut off mid-sentence at a join
- Repeated words or stuttering across retries still audible
- Reference sentence ("There is a book…" / "Es gibt ein Buch…") spoken

## Preset comparison

For each voice/text, rank the presets by listening:

1.  ____________   (best)
2.  ____________
3.  ____________
4.  ____________
5.  ____________
6.  current       (baseline reference)

Best overall preset = ____________. Do NOT ship until at least one
preset scores ≥ 4 on Identity / Intelligibility / Boundaries /
Degradation for the full ~5+ minute test text.
