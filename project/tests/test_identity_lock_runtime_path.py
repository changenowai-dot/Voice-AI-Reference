"""
Regressionstests für identity_lock.py Runtime-Pfad-Auflösung.

Testet dass identity_lock.py VOICEOVER_REFS_DIR korrekt respektiert
und die VD-E Referenz über den Runtime-Pfad findet.
"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.security.identity_lock import (
    _resolve_reference_path,
    check_identity,
    assert_vd_e_usable,
    IdentityStatus
)


class TestIdentityLockRuntimePath(unittest.TestCase):
    """Testet dass identity_lock Runtime-Pfade korrekt auflöst."""
    
    def setUp(self):
        """Erstelle temporäres Verzeichnis für Tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.refs_dir = Path(self.temp_dir) / "voice_refs"
        self.refs_dir.mkdir()
        
        # Erstelle eine Test-VD-E.wav Datei
        self.test_wav = self.refs_dir / "VD-E.wav"
        self.test_wav.write_bytes(b"fake wav content for testing")
        
    def tearDown(self):
        """Bereinige temporäres Verzeichnis."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_resolve_uses_voiceover_refs_dir(self):
        """identity_lock muss VOICEOVER_REFS_DIR verwenden wenn gesetzt."""
        # Setze VOICEOVER_REFS_DIR
        with patch.dict(os.environ, {'VOICEOVER_REFS_DIR': str(self.refs_dir)}):
            # Mock paths.VOICE_REFS_DIR
            with patch('app.security.identity_lock.paths.VOICE_REFS_DIR', self.refs_dir):
                production = {'reference_path': 'cache/voice_refs/VD-E.wav'}
                resolved = _resolve_reference_path(production)
                
                # Muss die Datei aus VOICEOVER_REFS_DIR finden
                self.assertTrue(resolved.exists())
                self.assertEqual(resolved, self.test_wav)
    
    def test_resolve_prefers_voiceover_runtime_ref(self):
        """VOICEOVER_RUNTIME_REF hat höchste Priorität."""
        # Erstelle explizite Referenz-Datei
        explicit_ref = Path(self.temp_dir) / "explicit_vd_e.wav"
        explicit_ref.write_bytes(b"explicit reference content")
        
        with patch.dict(os.environ, {
            'VOICEOVER_RUNTIME_REF': str(explicit_ref),
            'VOICEOVER_REFS_DIR': str(self.refs_dir)
        }):
            production = {'reference_path': 'cache/voice_refs/VD-E.wav'}
            resolved = _resolve_reference_path(production)
            
            # Muss die explizite Referenz verwenden
            self.assertEqual(resolved, explicit_ref)
    
    def test_resolve_falls_back_to_config_path(self):
        """Wenn keine Env-Vars gesetzt, verwende Config-Pfad relativ zu ROOT."""
        with patch.dict(os.environ, {}, clear=True):
            # Stelle sicher dass VOICEOVER_REFS_DIR nicht existiert
            with patch('app.security.identity_lock.paths.VOICE_REFS_DIR', Path('/nonexistent')):
                production = {'reference_path': 'cache/voice_refs/VD-E.wav'}
                resolved = _resolve_reference_path(production)
                
                # Muss relativ zu ROOT aufgelöst werden
                self.assertIn('cache', str(resolved))
                self.assertIn('voice_refs', str(resolved))
                self.assertIn('VD-E.wav', str(resolved))
    
    def test_hash_mismatch_blocks_vd_e(self):
        """VD-E muss blockiert werden wenn Hash nicht übereinstimmt."""
        # Erstelle Datei mit falschem Inhalt
        wrong_wav = self.refs_dir / "VD-E.wav"
        wrong_wav.write_bytes(b"wrong content - hash will not match")
        
        production = {
            'reference_path': 'cache/voice_refs/VD-E.wav',
            'reference_sha256': 'B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025'
        }
        
        with patch.dict(os.environ, {'VOICEOVER_REFS_DIR': str(self.refs_dir)}):
            with patch('app.security.identity_lock.paths.VOICE_REFS_DIR', self.refs_dir):
                status = check_identity(production)
                
                # Muss fehlschlagen wegen Hash-Mismatch
                self.assertFalse(status.ok)
                self.assertEqual(status.level, 'hash_mismatch')
                self.assertIn('verändert', status.message)
    
    def test_missing_reference_blocks_vd_e(self):
        """VD-E muss blockiert werden wenn Referenz fehlt."""
        # Lösche die Test-Datei
        self.test_wav.unlink()
        
        production = {
            'reference_path': 'cache/voice_refs/VD-E.wav',
            'reference_sha256': 'B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025'
        }
        
        with patch.dict(os.environ, {'VOICEOVER_REFS_DIR': str(self.refs_dir)}):
            with patch('app.security.identity_lock.paths.VOICE_REFS_DIR', self.refs_dir):
                status = check_identity(production)
                
                # Muss fehlschlagen weil Datei fehlt
                self.assertFalse(status.ok)
                self.assertEqual(status.level, 'missing_ref')
                self.assertIn('fehlt', status.message)
    
    def test_assert_vd_e_usable_raises_on_missing(self):
        """assert_vd_e_usable muss RuntimeError werfen wenn Referenz fehlt."""
        # Lösche die Test-Datei
        self.test_wav.unlink()
        
        production = {
            'reference_path': 'cache/voice_refs/VD-E.wav',
            'reference_sha256': 'B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025'
        }
        
        with patch.dict(os.environ, {'VOICEOVER_REFS_DIR': str(self.refs_dir)}):
            with patch('app.security.identity_lock.paths.VOICE_REFS_DIR', self.refs_dir):
                with self.assertRaises(RuntimeError) as ctx:
                    assert_vd_e_usable(production)
                
                self.assertIn('VD-E gesperrt', str(ctx.exception))
    
    def test_correct_hash_passes(self):
        """VD-E muss akzeptiert werden wenn Hash übereinstimmt."""
        import hashlib
        
        # Berechne echten SHA-256 der Test-Datei
        actual_hash = hashlib.sha256(self.test_wav.read_bytes()).hexdigest().upper()
        
        production = {
            'reference_path': 'cache/voice_refs/VD-E.wav',
            'reference_sha256': actual_hash
        }
        
        with patch.dict(os.environ, {'VOICEOVER_REFS_DIR': str(self.refs_dir)}):
            with patch('app.security.identity_lock.paths.VOICE_REFS_DIR', self.refs_dir):
                status = check_identity(production)
                
                # Muss erfolgreich sein
                self.assertTrue(status.ok)
                self.assertEqual(status.level, 'ok')
                self.assertEqual(status.expected, actual_hash)
                self.assertEqual(status.actual, actual_hash)


class TestIdentityLockBackwardCompatibility(unittest.TestCase):
    """Testet dass bestehende lokale/default Referenzlogik kompatibel bleibt."""
    
    def test_absolute_path_in_config(self):
        """Absoluter Pfad in Config muss direkt verwendet werden."""
        temp_file = Path(tempfile.mktemp(suffix='.wav'))
        temp_file.write_bytes(b"absolute path test")
        
        try:
            production = {'reference_path': str(temp_file)}
            resolved = _resolve_reference_path(production)
            
            self.assertEqual(resolved, temp_file)
        finally:
            temp_file.unlink(missing_ok=True)
    
    def test_relative_path_in_config(self):
        """Relativer Pfad in Config muss relativ zu ROOT aufgelöst werden."""
        with patch.dict(os.environ, {}, clear=True):
            with patch('app.security.identity_lock.paths.VOICE_REFS_DIR', Path('/nonexistent')):
                production = {'reference_path': 'cache/voice_refs/VD-E.wav'}
                resolved = _resolve_reference_path(production)
                
                # Muss relativ zu ROOT sein
                self.assertFalse(resolved.is_absolute() and 'voice_refs' not in str(resolved))


if __name__ == '__main__':
    unittest.main()
