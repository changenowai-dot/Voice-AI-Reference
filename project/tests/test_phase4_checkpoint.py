"""
Regression tests for PHASE4_AUDIO_SAFEPOINT_20260906 checkpoint.

These tests verify the integrity of the protected audio checkpoint:
- Checkpoint manifest exists and is valid JSON
- Golden Reference hash remains exact
- Required candidate list contains Baseline/A/B/C/E
- Only D is rejected
- Winner remains UNDECIDED (all good variants byte-identical)
- Common good SHA-256 is recorded
- D SHA-256 is recorded and different from good hash
- Checkpoint metadata is internally consistent
- Production VD-E configuration remains unchanged
"""
import json
import unittest
from pathlib import Path


# Paths
REPO_ROOT = Path(__file__).parent.parent.parent
CHECKPOINT_DIR = REPO_ROOT / "checkpoint"
SAFEPOINT_JSON = CHECKPOINT_DIR / "PHASE4_AUDIO_SAFEPOINT_20260906.json"
SAFEPOINT_MD = CHECKPOINT_DIR / "PHASE4_AUDIO_SAFEPOINT_20260906.md"
AUDIO_HASHES_JSON = CHECKPOINT_DIR / "audio_hashes_20260906_210750.json"
PRODUCTION_CONFIG = REPO_ROOT / "project" / "config" / "production.json"
BENCHMARK_SCRIPT = REPO_ROOT / "project" / "benchmark" / "phase4_benchmark.py"

# Constants
GOLDEN_REFERENCE_SHA256 = "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025"
CHECKPOINT_ID = "PHASE4_AUDIO_SAFEPOINT_20260906"
BENCHMARK_RUN_ID = "20260906_210750"
PROTECTED_CANDIDATES = {"Baseline", "A", "B", "C", "E"}
REJECTED_VARIANTS = {"D"}
COMMON_GOOD_SHA256 = "05EE6EB1A13F66D82A2DFFA5088AA7D409E8FA5A7F6071F58F5DBB8AE86326E5"
REJECTED_D_SHA256 = "C35DB293C4306249FE6CEB533CCE6D2E0AE24D0EB4A89999BF01AD33D13FD7EA"


class TestCheckpointFilesExist(unittest.TestCase):
    """Verify checkpoint files are present."""

    def test_checkpoint_directory_exists(self):
        """checkpoint/ directory must exist."""
        self.assertTrue(CHECKPOINT_DIR.is_dir(),
                       f"checkpoint/ directory missing at {CHECKPOINT_DIR}")

    def test_manifest_json_exists(self):
        """Machine-readable manifest JSON must exist."""
        self.assertTrue(SAFEPOINT_JSON.is_file(),
                       f"Manifest JSON missing: {SAFEPOINT_JSON}")

    def test_checkpoint_doc_exists(self):
        """Human-readable checkpoint document must exist."""
        self.assertTrue(SAFEPOINT_MD.is_file(),
                       f"Checkpoint document missing: {SAFEPOINT_MD}")

    def test_audio_hashes_json_exists(self):
        """Audio hash manifest must exist."""
        self.assertTrue(AUDIO_HASHES_JSON.is_file(),
                       f"Audio hash manifest missing: {AUDIO_HASHES_JSON}")

    def test_manifest_not_empty(self):
        """Manifest JSON must not be empty."""
        self.assertGreater(SAFEPOINT_JSON.stat().st_size, 100,
                          "Manifest JSON appears too small")

    def test_checkpoint_doc_not_empty(self):
        """Checkpoint document must not be empty."""
        self.assertGreater(SAFEPOINT_MD.stat().st_size, 100,
                          "Checkpoint document appears too small")


class TestManifestValidity(unittest.TestCase):
    """Verify manifest is valid and well-structured JSON."""

    @classmethod
    def setUpClass(cls):
        """Load the manifest."""
        cls.manifest = json.loads(SAFEPOINT_JSON.read_text(encoding='utf-8'))

    def test_manifest_is_valid_json(self):
        """Manifest must be valid JSON."""
        self.assertIsInstance(self.manifest, dict)

    def test_manifest_has_checkpoint_section(self):
        """Manifest must have 'checkpoint' section."""
        self.assertIn("checkpoint", self.manifest)

    def test_manifest_has_benchmark_run_section(self):
        """Manifest must have 'benchmark_run' section."""
        self.assertIn("benchmark_run", self.manifest)

    def test_manifest_has_hardware_section(self):
        """Manifest must have 'hardware' section."""
        self.assertIn("hardware", self.manifest)

    def test_manifest_has_audio_artifacts_section(self):
        """Manifest must have 'audio_artifacts' section."""
        self.assertIn("audio_artifacts", self.manifest)

    def test_manifest_has_winner_status_section(self):
        """Manifest must have 'winner_status' section."""
        self.assertIn("winner_status", self.manifest)

    def test_manifest_has_constraints_section(self):
        """Manifest must have 'constraints' section."""
        self.assertIn("constraints", self.manifest)

    def test_manifest_has_checks_section(self):
        """Manifest must have 'checks' section."""
        self.assertIn("checks", self.manifest)

    def test_manifest_has_golden_reference_section(self):
        """Manifest must have 'golden_reference' section."""
        self.assertIn("golden_reference", self.manifest)

    def test_manifest_has_vde_production_config_section(self):
        """Manifest must have 'vde_production_config' section."""
        self.assertIn("vde_production_config", self.manifest)

    def test_manifest_has_common_good_sha256(self):
        """Manifest must have common_good_sha256 in audio_artifacts."""
        self.assertIn("common_good_sha256", self.manifest["audio_artifacts"])
        self.assertEqual(
            self.manifest["audio_artifacts"]["common_good_sha256"],
            COMMON_GOOD_SHA256
        )


class TestGoldenReferenceIntegrity(unittest.TestCase):
    """Verify Golden Reference SHA-256 is preserved exactly."""

    @classmethod
    def setUpClass(cls):
        """Load the manifest."""
        cls.manifest = json.loads(SAFEPOINT_JSON.read_text(encoding='utf-8'))

    def test_golden_reference_sha256_exact(self):
        """Golden Reference SHA-256 must match the immutable value exactly."""
        sha = self.manifest["golden_reference"]["sha256"]
        self.assertEqual(sha, GOLDEN_REFERENCE_SHA256,
                        f"Golden Reference SHA-256 mismatch: {sha}")

    def test_golden_reference_status_verified(self):
        """Golden Reference status must be VERIFIED_PASS."""
        status = self.manifest["golden_reference"]["status"]
        self.assertEqual(status, "VERIFIED_PASS",
                        f"Golden Reference status is {status}, expected VERIFIED_PASS")

    def test_golden_reference_in_production_config(self):
        """production.json must contain the same Golden Reference SHA-256."""
        if PRODUCTION_CONFIG.is_file():
            config = json.loads(PRODUCTION_CONFIG.read_text(encoding='utf-8'))
            self.assertEqual(config["reference_sha256"], GOLDEN_REFERENCE_SHA256,
                           "production.json reference_sha256 does not match checkpoint")


class TestCandidateVariants(unittest.TestCase):
    """Verify candidate variant list is correct (Baseline, A, B, C, E are all GOOD)."""

    @classmethod
    def setUpClass(cls):
        """Load the manifest."""
        cls.manifest = json.loads(SAFEPOINT_JSON.read_text(encoding='utf-8'))
        cls.artifacts = cls.manifest["audio_artifacts"]
        cls.candidates = {c["variant"]: c for c in cls.artifacts["candidates"]}
        cls.non_preferred = {c["variant"]: c for c in cls.artifacts["non_preferred"]}

    def test_baseline_is_candidate(self):
        """Baseline must be in the candidate list."""
        self.assertIn("Baseline", self.candidates)

    def test_variant_a_is_candidate(self):
        """Variant A must be in the candidate list."""
        self.assertIn("A", self.candidates)

    def test_variant_b_is_candidate(self):
        """Variant B must be in the candidate list."""
        self.assertIn("B", self.candidates)

    def test_variant_c_is_candidate(self):
        """Variant C must be in the candidate list (moved from non-preferred in final review)."""
        self.assertIn("C", self.candidates)

    def test_variant_e_is_candidate(self):
        """Variant E must be in the candidate list."""
        self.assertIn("E", self.candidates)

    def test_all_candidates_selected(self):
        """All candidates must be marked as selected=true."""
        for name, cand in self.candidates.items():
            self.assertTrue(cand["selected"],
                          f"Candidate {name} must be selected=true")

    def test_candidates_are_protected(self):
        """All candidates must have status PROTECTED_CANDIDATE."""
        for name, cand in self.candidates.items():
            self.assertEqual(cand["status"], "PROTECTED_CANDIDATE",
                           f"Candidate {name} status is {cand['status']}")

    def test_candidates_quality_good(self):
        """All candidates must be rated GOOD."""
        for name, cand in self.candidates.items():
            self.assertEqual(cand["quality_rating"], "GOOD",
                           f"Candidate {name} quality_rating is {cand['quality_rating']}")

    def test_candidate_count_is_five(self):
        """There must be exactly 5 candidates (Baseline, A, B, C, E)."""
        self.assertEqual(len(self.candidates), 5,
                        f"Expected 5 candidates, got {len(self.candidates)}")

    def test_all_candidates_have_sha256(self):
        """All candidates must have SHA-256 hash recorded."""
        for name, cand in self.candidates.items():
            self.assertIn("sha256", cand, f"Candidate {name} missing sha256")
            self.assertIsNotNone(cand["sha256"], f"Candidate {name} sha256 is null")

    def test_all_candidates_have_common_hash(self):
        """All good candidates must have the common byte-identical hash."""
        for name, cand in self.candidates.items():
            self.assertEqual(cand["sha256"], COMMON_GOOD_SHA256,
                           f"Candidate {name} sha256 does not match common good hash")


class TestRejectedVariants(unittest.TestCase):
    """Verify only D is correctly marked as rejected."""

    @classmethod
    def setUpClass(cls):
        """Load the manifest."""
        cls.manifest = json.loads(SAFEPOINT_JSON.read_text(encoding='utf-8'))
        cls.artifacts = cls.manifest["audio_artifacts"]
        cls.non_preferred = {c["variant"]: c for c in cls.artifacts["non_preferred"]}
        cls.candidates = {c["variant"]: c for c in cls.artifacts["candidates"]}

    def test_variant_d_in_rejected(self):
        """Variant D must be in the non-preferred (rejected) list."""
        self.assertIn("D", self.non_preferred)

    def test_variant_d_not_selected(self):
        """Variant D must NOT be selected."""
        self.assertFalse(self.non_preferred["D"]["selected"],
                        "Variant D must not be selected")

    def test_variant_d_status_rejected(self):
        """Variant D must have status REJECTED."""
        self.assertEqual(self.non_preferred["D"]["status"], "REJECTED")

    def test_variant_d_quality_bad(self):
        """Variant D must be rated BAD."""
        self.assertEqual(self.non_preferred["D"]["quality_rating"], "BAD")

    def test_variant_d_has_sha256(self):
        """Variant D must have SHA-256 hash recorded."""
        self.assertIn("sha256", self.non_preferred["D"])
        self.assertEqual(
            self.non_preferred["D"]["sha256"],
            REJECTED_D_SHA256,
            "Variant D sha256 does not match expected rejected hash"
        )

    def test_d_not_in_candidates(self):
        """D must NOT appear in the candidates list."""
        self.assertNotIn("D", self.candidates,
                        "Variant D must not be in candidates")

    def test_only_d_is_rejected(self):
        """Only D should be in the non-preferred list."""
        self.assertEqual(len(self.non_preferred), 1,
                        f"Expected only 1 rejected variant, got {len(self.non_preferred)}")
        self.assertIn("D", self.non_preferred)

    def test_d_hash_differs_from_good(self):
        """D's hash must differ from the common good hash."""
        self.assertNotEqual(
            self.non_preferred["D"]["sha256"],
            COMMON_GOOD_SHA256,
            "Variant D sha256 must differ from common good hash"
        )


class TestAudioHashesManifest(unittest.TestCase):
    """Verify the audio_hashes_20260906_210750.json file."""

    @classmethod
    def setUpClass(cls):
        """Load the audio hashes manifest."""
        cls.hashes = json.loads(AUDIO_HASHES_JSON.read_text(encoding='utf-8'))

    def test_audio_hashes_valid_json(self):
        """Audio hashes manifest must be valid JSON."""
        self.assertIsInstance(self.hashes, dict)

    def test_audio_hashes_has_run_id(self):
        """Audio hashes manifest must have run_id."""
        self.assertEqual(self.hashes["run_id"], BENCHMARK_RUN_ID)

    def test_audio_hashes_has_all_variants(self):
        """Audio hashes manifest must have all 6 variants."""
        variants = self.hashes["variants"]
        for name in ["Baseline", "A", "B", "C", "D", "E"]:
            self.assertIn(name, variants, f"Variant {name} missing from audio hashes")

    def test_good_variants_have_correct_hash(self):
        """Good variants must have the common good hash."""
        variants = self.hashes["variants"]
        for name in ["Baseline", "A", "B", "C", "E"]:
            self.assertEqual(
                variants[name]["sha256"],
                COMMON_GOOD_SHA256,
                f"Variant {name} hash does not match common good hash"
            )

    def test_d_has_rejected_hash(self):
        """D must have the rejected hash."""
        self.assertEqual(
            self.hashes["variants"]["D"]["sha256"],
            REJECTED_D_SHA256,
            "Variant D hash does not match expected rejected hash"
        )

    def test_summary_good_count(self):
        """Summary must show 5 good variants."""
        self.assertEqual(self.hashes["summary"]["good_count"], 5)

    def test_summary_rejected_count(self):
        """Summary must show 1 rejected variant."""
        self.assertEqual(self.hashes["summary"]["rejected_count"], 1)

    def test_summary_common_hash(self):
        """Summary must record the common good hash."""
        self.assertEqual(
            self.hashes["summary"]["common_good_sha256"],
            COMMON_GOOD_SHA256
        )

    def test_summary_rejected_hash(self):
        """Summary must record the rejected D hash."""
        self.assertEqual(
            self.hashes["summary"]["rejected_sha256"],
            REJECTED_D_SHA256
        )

    def test_summary_byte_identical_list(self):
        """Summary must list byte-identical variants."""
        byte_identical = self.hashes["summary"]["byte_identical_variants"]
        self.assertEqual(set(byte_identical), PROTECTED_CANDIDATES)

    def test_summary_winner_status(self):
        """Summary must record winner status."""
        self.assertEqual(self.hashes["summary"]["winner_status"], "UNDECIDED")


class TestWinnerStatus(unittest.TestCase):
    """Verify winner status is UNDECIDED with byte-identical explanation."""

    @classmethod
    def setUpClass(cls):
        """Load the manifest."""
        cls.manifest = json.loads(SAFEPOINT_JSON.read_text(encoding='utf-8'))

    def test_winner_status_undecided(self):
        """Winner status must be UNDECIDED."""
        status = self.manifest["winner_status"]["status"]
        self.assertEqual(status, "UNDECIDED",
                        f"Winner status is '{status}', expected 'UNDECIDED'")

    def test_winner_has_reason(self):
        """Winner section must have a reason field."""
        reason = self.manifest["winner_status"].get("reason", "")
        self.assertGreater(len(reason), 10,
                          "Winner reason must be a meaningful description")

    def test_winner_byte_identical_flag(self):
        """Winner section must have byte_identical=true."""
        self.assertTrue(
            self.manifest["winner_status"].get("byte_identical", False),
            "Winner section must have byte_identical=true"
        )

    def test_winner_has_all_leading_candidates(self):
        """Winner section must list all 5 good candidates as leading."""
        leading = self.manifest["winner_status"].get("leading_candidates", [])
        self.assertIsInstance(leading, list)
        self.assertEqual(set(leading), PROTECTED_CANDIDATES,
                        f"Leading candidates {set(leading)} != {PROTECTED_CANDIDATES}")


class TestCheckpointConsistency(unittest.TestCase):
    """Verify checkpoint metadata is internally consistent."""

    @classmethod
    def setUpClass(cls):
        """Load the manifest."""
        cls.manifest = json.loads(SAFEPOINT_JSON.read_text(encoding='utf-8'))

    def test_checkpoint_id_matches(self):
        """Checkpoint ID must be PHASE4_AUDIO_SAFEPOINT_20260906."""
        self.assertEqual(self.manifest["checkpoint"]["id"], CHECKPOINT_ID)

    def test_benchmark_run_id_matches(self):
        """Benchmark run ID must be 20260906_210750."""
        self.assertEqual(self.manifest["benchmark_run"]["run_id"], BENCHMARK_RUN_ID)

    def test_checkpoint_type_is_safepoint(self):
        """Checkpoint type must be production_audio_safepoint."""
        self.assertEqual(self.manifest["checkpoint"]["type"],
                        "production_audio_safepoint")

    def test_branch_is_correct(self):
        """Branch must be arena/01a06e55-voice-ai-reference."""
        self.assertEqual(self.manifest["checkpoint"]["branch"],
                        "arena/01a06e55-voice-ai-reference")

    def test_git_tag_matches_checkpoint_id(self):
        """Git tag must match checkpoint ID."""
        self.assertEqual(self.manifest["checkpoint"]["git_tag"], CHECKPOINT_ID)

    def test_all_checks_passed(self):
        """All verification checks must be PASS."""
        checks = self.manifest["checks"]
        for check_name, status in checks.items():
            self.assertEqual(status, "PASS",
                           f"Check '{check_name}' is '{status}', expected 'PASS'")

    def test_hardware_has_gpu(self):
        """Hardware section must specify the GPU."""
        hw = self.manifest["hardware"]
        self.assertIn("gpu", hw)
        self.assertIn("RTX 5060", hw["gpu"])

    def test_hardware_has_ram(self):
        """Hardware section must specify RAM."""
        hw = self.manifest["hardware"]
        self.assertIn("ram_total_gb", hw)
        self.assertGreater(hw["ram_total_gb"], 30)

    def test_hardware_has_vram(self):
        """Hardware section must specify VRAM."""
        hw = self.manifest["hardware"]
        self.assertIn("gpu_vram_gb", hw)
        self.assertGreater(hw["gpu_vram_gb"], 7)

    def test_constraints_no_modification_listed(self):
        """Constraints must list items that cannot be modified."""
        constraints = self.manifest["constraints"]
        self.assertIn("no_modification_allowed", constraints)
        immutables = constraints["no_modification_allowed"]
        self.assertGreater(len(immutables), 3,
                          "Must list at least 4 immutable items")

    def test_constraints_optimization_rules_listed(self):
        """Constraints must list optimization rules."""
        constraints = self.manifest["constraints"]
        self.assertIn("optimization_rules", constraints)
        rules = constraints["optimization_rules"]
        self.assertGreater(len(rules), 2,
                          "Must list at least 3 optimization rules")

    def test_common_good_hash_consistent(self):
        """common_good_sha256 must match between manifest and audio_hashes."""
        manifest_hash = self.manifest["audio_artifacts"]["common_good_sha256"]
        hashes = json.loads(AUDIO_HASHES_JSON.read_text(encoding='utf-8'))
        self.assertEqual(
            manifest_hash,
            hashes["summary"]["common_good_sha256"],
            "common_good_sha256 inconsistent between manifest and audio_hashes"
        )


class TestVDEConfigUnchanged(unittest.TestCase):
    """Verify production VD-E configuration is unchanged."""

    @classmethod
    def setUpClass(cls):
        """Load configs."""
        cls.manifest = json.loads(SAFEPOINT_JSON.read_text(encoding='utf-8'))
        cls.prod_config = json.loads(PRODUCTION_CONFIG.read_text(encoding='utf-8'))

    def test_voice_id_matches(self):
        """Voice ID must be vd_e in both manifest and production config."""
        manifest_vid = self.manifest["vde_production_config"]["voice_id"]
        config_vid = self.prod_config["voice_id"]
        self.assertEqual(manifest_vid, "vd_e")
        self.assertEqual(config_vid, "vd_e")

    def test_mode_matches(self):
        """Mode must be voicedesign_base_clone."""
        manifest_mode = self.manifest["vde_production_config"]["mode"]
        config_mode = self.prod_config["mode"]
        self.assertEqual(manifest_mode, "voicedesign_base_clone")
        self.assertEqual(config_mode, "voicedesign_base_clone")

    def test_seed_matches(self):
        """Seed must be 52001."""
        manifest_seed = self.manifest["vde_production_config"]["seed"]
        config_seed = self.prod_config["seed"]
        self.assertEqual(manifest_seed, 52001)
        self.assertEqual(config_seed, 52001)

    def test_locked_is_true(self):
        """Production config must be locked."""
        self.assertTrue(self.prod_config["locked"],
                       "production.json must have locked=true")

    def test_reference_sha256_matches(self):
        """reference_sha256 in production.json must match checkpoint."""
        config_sha = self.prod_config["reference_sha256"]
        manifest_sha = self.manifest["golden_reference"]["sha256"]
        self.assertEqual(config_sha, manifest_sha)
        self.assertEqual(config_sha, GOLDEN_REFERENCE_SHA256)


class TestBenchmarkDefinitionsUnchanged(unittest.TestCase):
    """Verify benchmark experiment definitions are unchanged."""

    def test_benchmark_script_exists(self):
        """phase4_benchmark.py must exist."""
        self.assertTrue(BENCHMARK_SCRIPT.is_file(),
                       f"Benchmark script missing: {BENCHMARK_SCRIPT}")

    def test_benchmark_has_all_variants(self):
        """Benchmark must define all 6 variants (A-E + D special)."""
        content = BENCHMARK_SCRIPT.read_text(encoding='utf-8')
        for variant in ['"A"', '"B"', '"C"', '"D"', '"E"']:
            self.assertIn(variant, content,
                         f"Variant {variant} not found in benchmark script")

    def test_benchmark_variant_a_params(self):
        """Variant A must use production standard parameters."""
        content = BENCHMARK_SCRIPT.read_text(encoding='utf-8')
        self.assertIn("A_production_standard", content)
        self.assertIn("seg_target=420", content)

    def test_benchmark_variant_b_params(self):
        """Variant B must use larger segments parameters."""
        content = BENCHMARK_SCRIPT.read_text(encoding='utf-8')
        self.assertIn("B_larger_segments", content)
        self.assertIn("seg_target=700", content)

    def test_benchmark_variant_e_params(self):
        """Variant E must use hybrid paragraph parameters."""
        content = BENCHMARK_SCRIPT.read_text(encoding='utf-8')
        self.assertIn("E_hybrid_paragraph", content)
        self.assertIn("seg_target=1000", content)


class TestCheckpointDocument(unittest.TestCase):
    """Verify the human-readable checkpoint document."""

    @classmethod
    def setUpClass(cls):
        """Load the document."""
        cls.content = SAFEPOINT_MD.read_text(encoding='utf-8')

    def test_document_has_checkpoint_id(self):
        """Document must contain the checkpoint ID."""
        self.assertIn(CHECKPOINT_ID, self.content)

    def test_document_has_benchmark_run_id(self):
        """Document must contain the benchmark run ID."""
        self.assertIn(BENCHMARK_RUN_ID, self.content)

    def test_document_has_golden_reference_hash(self):
        """Document must contain the Golden Reference SHA-256."""
        self.assertIn(GOLDEN_REFERENCE_SHA256, self.content)

    def test_document_has_undecided_status(self):
        """Document must state winner is UNDECIDED."""
        self.assertIn("UNDECIDED", self.content)

    def test_document_has_common_good_hash(self):
        """Document must contain the common good SHA-256."""
        self.assertIn(COMMON_GOOD_SHA256, self.content)

    def test_document_has_rejected_d_hash(self):
        """Document must contain the rejected D SHA-256."""
        self.assertIn(REJECTED_D_SHA256, self.content)

    def test_document_lists_all_good_candidates(self):
        """Document must list all 5 protected candidates."""
        for name in ["Baseline", "A", "B", "C", "E"]:
            self.assertIn(name, self.content,
                         f"Candidate '{name}' not found in document")

    def test_document_marks_d_rejected(self):
        """Document must mark D as REJECTED."""
        self.assertIn("REJECTED", self.content)
        # D must be explicitly rejected
        rejected_section_start = self.content.find("REJECTED")
        self.assertGreater(rejected_section_start, 0,
                          "REJECTED section not found in document")
        # Verify D is in the rejected context
        rejected_context = self.content[rejected_section_start:rejected_section_start+200]
        self.assertIn("D", rejected_context,
                     "Variant D not found in REJECTED section")

    def test_document_has_snapshot_warning(self):
        """Document must clearly state this is a SNAPSHOT/FREEZE."""
        self.assertIn("SNAPSHOT", self.content)
        self.assertIn("FREEZE", self.content)

    def test_document_has_immutable_constraints(self):
        """Document must list immutable constraints."""
        self.assertIn("IMMUTABLE", self.content.upper())

    def test_document_has_byte_identical_note(self):
        """Document must note that good variants are byte-identical."""
        self.assertIn("byte-identical", self.content.lower())


if __name__ == "__main__":
    unittest.main()
