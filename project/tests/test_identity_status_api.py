"""
Regression test for IdentityStatus API usage in target validator.

This test ensures that target_validate_explicit_marker.py uses the correct
IdentityStatus field names and doesn't reference non-existent fields.

Related to the fix: "fix explicit marker identity status api"
"""
import ast
import unittest
from pathlib import Path


class TestTargetValidatorIdentityStatusAPI(unittest.TestCase):
    """Test that target validator uses correct IdentityStatus API."""

    def setUp(self):
        """Load the target validator script."""
        self.validator_path = Path(__file__).parent / "target_validate_explicit_marker.py"
        self.assertTrue(self.validator_path.exists(), 
                       f"Target validator not found: {self.validator_path}")
        
        with open(self.validator_path, 'r', encoding='utf-8') as f:
            self.source = f.read()
        
        # Parse the AST
        self.tree = ast.parse(self.source)

    def test_no_status_field(self):
        """Target validator must not use identity_status.status (non-existent field)."""
        # Check for identity_status.status specifically
        self.assertNotIn('identity_status.status', self.source,
                        "Target validator uses 'identity_status.status' which doesn't exist. "
                        "Use 'identity_status.level' instead.")

    def test_no_valid_field(self):
        """Target validator must not use identity_status.valid (non-existent field)."""
        # Check for identity_status.valid specifically
        self.assertNotIn('identity_status.valid', self.source,
                        "Target validator uses 'identity_status.valid' which doesn't exist. "
                        "Use 'identity_status.ok' instead.")

    def test_no_reference_path_field(self):
        """Target validator must not use identity_status.reference_path (non-existent field)."""
        # Check for identity_status.reference_path specifically
        self.assertNotIn('identity_status.reference_path', self.source,
                        "Target validator uses 'identity_status.reference_path' which doesn't exist. "
                        "Use 'identity_status.path' instead.")

    def test_no_expected_sha256_field(self):
        """Target validator must not use identity_status.expected_sha256 (non-existent field)."""
        # Check for identity_status.expected_sha256 specifically
        self.assertNotIn('identity_status.expected_sha256', self.source,
                        "Target validator uses 'identity_status.expected_sha256' which doesn't exist. "
                        "Use 'identity_status.expected' instead.")

    def test_no_actual_sha256_field(self):
        """Target validator must not use identity_status.actual_sha256 (non-existent field)."""
        # Check for identity_status.actual_sha256 specifically
        self.assertNotIn('identity_status.actual_sha256', self.source,
                        "Target validator uses 'identity_status.actual_sha256' which doesn't exist. "
                        "Use 'identity_status.actual' instead.")

    def test_uses_ok_field(self):
        """Target validator should use identity_status.ok."""
        self.assertIn('identity_status.ok', self.source,
                     "Target validator should use 'identity_status.ok' for validity check")

    def test_uses_level_field(self):
        """Target validator should use identity_status.level."""
        self.assertIn('identity_status.level', self.source,
                     "Target validator should use 'identity_status.level' for status level")

    def test_uses_path_field(self):
        """Target validator should use identity_status.path."""
        self.assertIn('identity_status.path', self.source,
                     "Target validator should use 'identity_status.path' for reference path")

    def test_uses_expected_field(self):
        """Target validator should use identity_status.expected."""
        self.assertIn('identity_status.expected', self.source,
                     "Target validator should use 'identity_status.expected' for expected SHA-256")

    def test_uses_actual_field(self):
        """Target validator should use identity_status.actual."""
        self.assertIn('identity_status.actual', self.source,
                     "Target validator should use 'identity_status.actual' for actual SHA-256")

    def test_uses_message_field(self):
        """Target validator should use identity_status.message."""
        self.assertIn('identity_status.message', self.source,
                     "Target validator should use 'identity_status.message' for error messages")

    def test_identity_status_import(self):
        """Target validator should import from identity_lock module."""
        # Validator imports check_identity, not necessarily IdentityStatus class
        self.assertIn('from app.security.identity_lock import check_identity', self.source,
                     "Target validator should import check_identity from app.security.identity_lock")

    def test_check_identity_call(self):
        """Target validator should call check_identity()."""
        self.assertIn('check_identity()', self.source,
                     "Target validator should call check_identity()")


class TestIdentityStatusDefinition(unittest.TestCase):
    """Test that IdentityStatus has the expected fields."""

    def test_identity_status_has_correct_fields(self):
        """IdentityStatus should have the correct fields as defined in identity_lock.py."""
        from app.security.identity_lock import IdentityStatus
        
        # Create a sample IdentityStatus
        status = IdentityStatus(
            ok=True,
            level="ok",
            expected="B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025",
            actual="B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025",
            path="/path/to/VD-E.wav",
            message="VD-E identity verified"
        )
        
        # Verify all expected fields exist
        self.assertTrue(hasattr(status, 'ok'))
        self.assertTrue(hasattr(status, 'level'))
        self.assertTrue(hasattr(status, 'expected'))
        self.assertTrue(hasattr(status, 'actual'))
        self.assertTrue(hasattr(status, 'path'))
        self.assertTrue(hasattr(status, 'message'))
        self.assertTrue(hasattr(status, 'vd_e_available'))
        
        # Verify values
        self.assertEqual(status.ok, True)
        self.assertEqual(status.level, "ok")
        self.assertEqual(status.expected, "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025")
        self.assertEqual(status.actual, "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025")
        self.assertEqual(status.path, "/path/to/VD-E.wav")
        self.assertEqual(status.message, "VD-E identity verified")
        self.assertEqual(status.vd_e_available, True)

    def test_identity_status_no_nonexistent_fields(self):
        """IdentityStatus should NOT have the fields that were incorrectly used."""
        from app.security.identity_lock import IdentityStatus
        
        status = IdentityStatus(
            ok=True,
            level="ok",
            expected="TEST",
            actual="TEST",
            path="/test"
        )
        
        # These fields should NOT exist
        self.assertFalse(hasattr(status, 'status'),
                        "IdentityStatus should not have 'status' field")
        self.assertFalse(hasattr(status, 'valid'),
                        "IdentityStatus should not have 'valid' field")
        self.assertFalse(hasattr(status, 'reference_path'),
                        "IdentityStatus should not have 'reference_path' field")
        self.assertFalse(hasattr(status, 'expected_sha256'),
                        "IdentityStatus should not have 'expected_sha256' field")
        self.assertFalse(hasattr(status, 'actual_sha256'),
                        "IdentityStatus should not have 'actual_sha256' field")


if __name__ == '__main__':
    unittest.main()
