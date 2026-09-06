"""
Tests für identity_lock.py Runtime Reference Resolution

Testet, dass check_identity() die VOICEOVER_RUNTIME_REF Environment-Variable
korrekt respektiert und die richtige Priorisierung hat.
"""
import hashlib
import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch, MagicMock

# Import der zu testenden Module
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.security.identity_lock import check_identity, _resolve_reference_path, IdentityStatus


# Bekannter SHA-256 Hash der Golden Reference
EXPECTED_SHA256 = "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025"


def create_test_wav(path: Path, content: bytes = b"test audio content") -> Path:
    """Erstellt eine Test-WAV-Datei."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def compute_sha256(path: Path) -> str:
    """Berechnet SHA-256 Hash einer Datei."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


class TestIdentityLockRuntimeRef(TestCase):
    """Tests für VOICEOVER_RUNTIME_REF Environment-Variable Handling."""

    def setUp(self):
        """Erstellt temporäres Verzeichnis für Test-Dateien."""
        self.temp_dir = tempfile.mkdtemp(prefix="identity_lock_test_")
        self.temp_path = Path(self.temp_dir)
        
        # Erstelle Test-WAV mit bekanntem Hash
        self.test_wav = self.temp_path / "test_vd_e.wav"
        create_test_wav(self.test_wav, b"test audio content for vd-e")
        self.test_wav_hash = compute_sha256(self.test_wav)
        
        # Erstelle alternative Test-WAV mit anderem Hash
        self.alt_wav = self.temp_path / "alt_vd_e.wav"
        create_test_wav(self.alt_wav, b"different audio content")
        self.alt_wav_hash = compute_sha256(self.alt_wav)
        
        # Sicherstellen, dass die Hashes unterschiedlich sind
        self.assertNotEqual(self.test_wav_hash, self.alt_wav_hash)

    def tearDown(self):
        """Räumt temporäres Verzeichnis auf."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_explicit_runtime_ref_is_honored(self):
        """VOICEOVER_RUNTIME_REF hat höchste Priorität."""
        with patch.dict(os.environ, {"VOICEOVER_RUNTIME_REF": str(self.test_wav)}):
            # Mock production config mit dem Hash unserer Test-Datei
            production = {"reference_sha256": self.test_wav_hash}
            
            status = check_identity(production)
            
            self.assertTrue(status.ok)
            self.assertEqual(status.level, "ok")
            self.assertEqual(status.path, str(self.test_wav))
            self.assertIn("identitätsgesichert", status.message)

    def test_explicit_runtime_ref_overrides_config(self):
        """VOICEOVER_RUNTIME_REF überschreibt production.json Pfad."""
        # Erstelle eine weitere Test-Datei
        config_wav = self.temp_path / "config_vd_e.wav"
        create_test_wav(config_wav, b"config audio content")
        config_wav_hash = compute_sha256(config_wav)
        
        # Environment zeigt auf test_wav, Config zeigt auf config_wav
        with patch.dict(os.environ, {"VOICEOVER_RUNTIME_REF": str(self.test_wav)}):
            production = {
                "reference_sha256": self.test_wav_hash,
                "reference_path": str(config_wav)
            }
            
            status = check_identity(production)
            
            # Sollte test_wav verwenden (aus Environment), nicht config_wav
            self.assertTrue(status.ok)
            self.assertEqual(status.path, str(self.test_wav))

    def test_missing_explicit_runtime_ref_fails_clearly(self):
        """Fehlende VOICEOVER_RUNTIME_REF Datei schlägt klar fehl."""
        missing_path = self.temp_path / "missing.wav"
        
        with patch.dict(os.environ, {"VOICEOVER_RUNTIME_REF": str(missing_path)}):
            production = {"reference_sha256": self.test_wav_hash}
            
            status = check_identity(production)
            
            self.assertFalse(status.ok)
            self.assertEqual(status.level, "missing_ref")
            self.assertIn("fehlt", status.message.lower())

    def test_wrong_hash_runtime_ref_fails_clearly(self):
        """VOICEOVER_RUNTIME_REF mit falschem Hash schlägt klar fehl."""
        with patch.dict(os.environ, {"VOICEOVER_RUNTIME_REF": str(self.alt_wav)}):
            # Erwartet den Hash von test_wav, aber alt_wav hat anderen Hash
            production = {"reference_sha256": self.test_wav_hash}
            
            status = check_identity(production)
            
            self.assertFalse(status.ok)
            self.assertEqual(status.level, "hash_mismatch")
            self.assertIn("verändert", status.message)

    def test_no_regeneration_on_failure(self):
        """Bei Fehlern wird keine Datei regeneriert oder überschrieben."""
        missing_path = self.temp_path / "missing.wav"
        
        with patch.dict(os.environ, {"VOICEOVER_RUNTIME_REF": str(missing_path)}):
            production = {"reference_sha256": self.test_wav_hash}
            
            status = check_identity(production)
            
            # Stelle sicher, dass keine Datei erstellt wurde
            self.assertFalse(missing_path.exists())
            self.assertFalse(status.ok)

    def test_fallback_to_config_path(self):
        """Fallback auf production.json Pfad wenn keine Environment-Variable."""
        # Entferne Environment-Variable
        env_copy = os.environ.copy()
        env_copy.pop("VOICEOVER_RUNTIME_REF", None)
        
        with patch.dict(os.environ, env_copy, clear=True):
            production = {
                "reference_sha256": self.test_wav_hash,
                "reference_path": str(self.test_wav)
            }
            
            status = check_identity(production)
            
            self.assertTrue(status.ok)
            self.assertEqual(status.path, str(self.test_wav))

    def test_resolve_reference_path_priority(self):
        """_resolve_reference_path() respektiert Priorisierung."""
        # Test 1: Environment hat Priorität
        with patch.dict(os.environ, {"VOICEOVER_RUNTIME_REF": str(self.test_wav)}):
            production = {"reference_path": str(self.alt_wav)}
            resolved = _resolve_reference_path(production)
            self.assertEqual(resolved, self.test_wav)
        
        # Test 2: Fallback auf Config-Pfad
        env_copy = os.environ.copy()
        env_copy.pop("VOICEOVER_RUNTIME_REF", None)
        with patch.dict(os.environ, env_copy, clear=True):
            production = {"reference_path": str(self.test_wav)}
            resolved = _resolve_reference_path(production)
            self.assertEqual(resolved, self.test_wav)

    def test_nonexistent_env_path_logs_warning(self):
        """Nicht-existenter Environment-Pfad loggt Warnung."""
        missing_path = self.temp_path / "nonexistent.wav"
        
        with patch.dict(os.environ, {"VOICEOVER_RUNTIME_REF": str(missing_path)}):
            production = {"reference_sha256": self.test_wav_hash}
            
            # Sollte nicht crashen, sondern gracefully fehlschlagen
            status = check_identity(production)
            
            self.assertFalse(status.ok)
            self.assertEqual(status.level, "missing_ref")

    def test_absolute_path_in_config(self):
        """Absoluter Pfad in production.json wird korrekt behandelt."""
        env_copy = os.environ.copy()
        env_copy.pop("VOICEOVER_RUNTIME_REF", None)
        
        with patch.dict(os.environ, env_copy, clear=True):
            production = {
                "reference_sha256": self.test_wav_hash,
                "reference_path": str(self.test_wav.absolute())
            }
            
            status = check_identity(production)
            
            self.assertTrue(status.ok)
            self.assertEqual(status.path, str(self.test_wav.absolute()))


class TestIdentityLockIntegration(TestCase):
    """Integrationstests für den vollständigen Identity-Lock Flow."""

    def setUp(self):
        """Erstellt temporäres Verzeichnis mit vollständiger Struktur."""
        self.temp_dir = tempfile.mkdtemp(prefix="identity_integration_")
        self.temp_path = Path(self.temp_dir)
        
        # Erstelle project/cache/voice_refs/ Struktur
        self.cache_dir = self.temp_path / "project" / "cache" / "voice_refs"
        self.cache_dir.mkdir(parents=True)
        
        self.vd_e_wav = self.cache_dir / "VD-E.wav"
        create_test_wav(self.vd_e_wav, b"integration test audio")
        self.vd_e_hash = compute_sha256(self.vd_e_wav)

    def tearDown(self):
        """Räumt temporäres Verzeichnis auf."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_flow_with_external_reference(self):
        """Vollständiger Flow mit externer Reference (wie auf RTX 5060)."""
        # Simuliere die Situation auf dem Target-PC:
        # - Externe VoiceOverApp_LAB_NEXT mit VD-E.wav
        # - Frisch entpacktes Repository ohne lokale Kopie
        # - VOICEOVER_RUNTIME_REF zeigt auf externe Datei
        
        external_ref = self.temp_path / "VoiceOverApp_LAB_NEXT" / "cache" / "voice_refs" / "VD-E.wav"
        create_test_wav(external_ref, b"external lab next audio")
        external_hash = compute_sha256(external_ref)
        
        with patch.dict(os.environ, {"VOICEOVER_RUNTIME_REF": str(external_ref)}):
            production = {"reference_sha256": external_hash}
            
            status = check_identity(production)
            
            self.assertTrue(status.ok)
            self.assertEqual(status.path, str(external_ref))
            self.assertIn("identitätsgesichert", status.message)

    def test_full_flow_with_local_reference(self):
        """Vollständiger Flow mit lokaler Reference (legacy)."""
        # Legacy-Situation: Lokale Kopie in project/cache/voice_refs/
        env_copy = os.environ.copy()
        env_copy.pop("VOICEOVER_RUNTIME_REF", None)
        
        with patch.dict(os.environ, env_copy, clear=True):
            production = {
                "reference_sha256": self.vd_e_hash,
                "reference_path": str(self.vd_e_wav)
            }
            
            status = check_identity(production)
            
            self.assertTrue(status.ok)
            self.assertEqual(status.path, str(self.vd_e_wav))


if __name__ == "__main__":
    import unittest
    unittest.main()
