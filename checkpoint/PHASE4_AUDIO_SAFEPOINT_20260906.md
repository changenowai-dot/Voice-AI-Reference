# PHASE4_AUDIO_SAFEPOINT_20260906

## Protected Known-Good Audio Baseline

**Checkpoint ID:** `PHASE4_AUDIO_SAFEPOINT_20260906`
**Git Tag:** `PHASE4_AUDIO_SAFEPOINT_20260906`
**Branch:** `arena/01a06e55-voice-ai-reference`
**Created:** 2026-09-06

---

## Purpose

This checkpoint captures the **first successful Phase 4 audio benchmark run** on the real RTX 5060 target hardware. It serves as the **protected rollback point** for all future audio optimization work.

**This is a SNAPSHOT/FREEZE. No synthesis behavior is changed in this commit.**

| Rule | Enforced |
|------|----------|
| Golden Reference unchanged | ✅ |
| VD-E production config unchanged | ✅ |
| Model configuration unchanged | ✅ |
| Benchmark experiment definitions unchanged | ✅ |
| Candidate audio artifacts preserved | ✅ |
| Winner status = UNDECIDED | ✅ |

---

## Benchmark Run

| Field | Value |
|-------|-------|
| **Run ID** | `20260906_210750` |
| **Runner** | `run_phase4_target.ps1` |
| **Local results path** | `results\phase4\20260906_210750\` |

### Verification Results

| Check | Status |
|-------|--------|
| Environment | ✅ PASS |
| Golden Reference SHA-256 | ✅ PASS |
| Identity Lock | ✅ PASS |
| Model Discovery | ✅ PASS |
| FFmpeg | ✅ PASS |
| Benchmark Execution | ✅ PASS |

---

## Hardware

| Component | Specification |
|-----------|---------------|
| CPU | AMD Ryzen 7 5700X |
| RAM | 34.3 GB |
| GPU | NVIDIA GeForce RTX 5060 |
| VRAM | 8.6 GB |
| OS | Windows 10 x64 |

## Software

| Component | Version |
|-----------|---------|
| Python | 3.12.10 |
| PyTorch | 2.11.0+cu128 |
| CUDA | 12.8 |
| Transformers | 4.57.3 |
| App | 2.1.0 |

---

## Golden Reference

| Field | Value |
|-------|-------|
| **SHA-256** | `B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025` |
| **Path** | `cache/voice_refs/VD-E.wav` |
| **Status** | VERIFIED PASS |

**⚠️ This hash must NEVER change. It is the immutable identity anchor for VD-E.**

---

## VD-E Production Configuration

| Parameter | Value |
|-----------|-------|
| Voice-ID | `vd_e` |
| Mode | `voicedesign_base_clone` |
| Variant | `BASE` |
| Seed | `52001` |
| Model | `Qwen3-TTS-12Hz-1.7B-Base` |
| Sampling | `expressive` |
| Locked | `true` |

**⚠️ This configuration is LOCKED. No changes allowed in this checkpoint.**

---

## Audio Candidate Evaluation

### Manual Listening Test Results

The user listened to all generated Phase 4 variants on the RTX 5060 and provided qualitative ratings:

### ✅ PROTECTED CANDIDATES (GOOD / Production-Capable)

| Variant | Output Directory | Strategy | Rating |
|---------|-----------------|----------|--------|
| **Baseline** | `project/output/phase4_baseline/` | Default production pipeline | ✅ GOOD |
| **A** | `project/output/phase4_A/` | Production standard (seg_target=420s) | ✅ GOOD |
| **B** | `project/output/phase4_B/` | Larger segments (seg_target=700s) | ✅ GOOD |
| **E** | `project/output/phase4_E/` | Hybrid paragraph (seg_target=1000s) | ✅ GOOD |

### ❌ NON-PREFERRED (BAD / Not Selected)

| Variant | Output Directory | Strategy | Rating | Note |
|---------|-----------------|----------|--------|------|
| **C** | `project/output/phase4_C/` | Very large blocks (seg_target=1200s) | ❌ BAD | Preserved for historical reference only |
| **D** | `project/output/phase4_variant_D/` | Large blocks + cutting | ❌ BAD | Preserved for historical reference only |

---

## Winner Status

### 🟡 UNDECIDED

**No single winner has been declared.**

All four candidates (Baseline, A, B, E) are considered production-capable. The user currently cannot choose among them.

**Leading candidates:** Baseline and E are noted as especially promising.

**Next steps:** Further optimization will be performed from this checkpoint. The winner will be selected after optimization is complete.

---

## Audio Artifact Integrity

Audio files reside on the local RTX 5060 machine and are **not stored in Git** (too large).

### Required: Compute SHA-256 Hashes Locally

Run the helper script on the RTX 5060:

```powershell
.\checkpoint\compute_audio_hashes.ps1
```

Or manually compute hashes:

```powershell
Get-FileHash -Algorithm SHA256 project\output\phase4_baseline\*.wav
Get-FileHash -Algorithm SHA256 project\output\phase4_A\*.wav
Get-FileHash -Algorithm SHA256 project\output\phase4_B\*.wav
Get-FileHash -Algorithm SHA256 project\output\phase4_E\*.wav
```

**⚠️ These hashes must be recorded in the manifest after computation. They serve as the integrity anchor — any future regeneration must produce matching hashes to prove no silent substitution occurred.**

---

## Constraints for Future Work

### 🔒 IMMUTABLE (Do Not Modify)

1. **Golden Reference** — SHA-256 must remain `B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025`
2. **VD-E production config** — `project/config/production.json` voice_id/mode/seed locked
3. **Model configuration** — Current working model setup unchanged
4. **Benchmark experiment definitions** — Variant parameters in `phase4_benchmark.py`
5. **Candidate audio artifacts** — Baseline, A, B, E files must not be regenerated or deleted

### 📋 OPTIMIZATION RULES

1. **All future optimization must build FROM this checkpoint, never overwrite it**
2. Each optimization attempt must be a **separate branch/commit**
3. This safepoint serves as the **rollback target** if optimization fails
4. Winner selection is **deferred** until optimization is complete
5. Non-preferred variants (C, D) must remain in historical benchmark results

### 🚫 NOT YET (Deferred)

- Long-Form optimization — not started
- Segmentation logic changes — not yet applied
- Winner declaration — pending further optimization

---

## Regression Tests

Safety tests in `project/tests/test_phase4_checkpoint.py` verify:

- [ ] Checkpoint manifest exists and is valid JSON
- [ ] Golden Reference hash remains exact
- [ ] Required candidate list contains Baseline/A/B/E
- [ ] C/D are not selected as candidates
- [ ] Winner remains UNDECIDED
- [ ] Checkpoint metadata is internally consistent
- [ ] Production VD-E configuration remains unchanged

Run: `python -m unittest project/tests/test_phase4_checkpoint.py -v`

---

## How to Rollback to This Checkpoint

```bash
git checkout PHASE4_AUDIO_SAFEPOINT_20260906
```

This restores the exact code state of the successful Phase 4 benchmark.

---

*This checkpoint was created automatically from the successful benchmark run `20260906_210750` on RTX 5060.*
*It represents the first verified production-capable audio output from the VoiceOverApp Phase 4 pipeline.*
