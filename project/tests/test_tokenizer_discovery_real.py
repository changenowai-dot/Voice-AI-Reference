"""
Regressionstests für Tokenizer-Discovery mit realen Strukturen.

Testet die Discovery-Logik für:
1. Verschachtelte VoiceOverApp-Struktur (VoiceOverApp_OLD/VoiceOverApp/models)
2. Direkte Tokenizer-Verzeichnisse
3. HF-Cache-Strukturen
4. speech_tokenizer in Base/CustomVoice
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Füge project/ zum Path hinzu
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.phase4_env_check import (
    _find_all_model_roots,
    _find_model_in_roots,
    check_models,
)


def test_nested_voiceoverapp_structure():
    """Test: Verschachtelte VoiceOverApp-Struktur wird gefunden."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Erstelle VoiceOverApp_OLD/VoiceOverApp/models Struktur
        nested_root = Path(tmpdir) / "VoiceOverApp_OLD" / "VoiceOverApp" / "models"
        nested_root.mkdir(parents=True)
        
        # Erstelle Tokenizer
        tokenizer_dir = nested_root / "Qwen3-TTS-Tokenizer-12Hz"
        tokenizer_dir.mkdir()
        (tokenizer_dir / "config.json").write_text("{}")
        
        # Simuliere Downloads-Verzeichnis
        downloads = Path(tmpdir) / "Downloads"
        downloads.mkdir()
        old_app = downloads / "VoiceOverApp_OLD"
        old_app.symlink_to(Path(tmpdir) / "VoiceOverApp_OLD")
        
        # Setze HOME auf tmpdir
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = tmpdir
        
        try:
            # Teste _find_all_model_roots
            roots = _find_all_model_roots()
            
            # Prüfe ob verschachtelter Root gefunden wurde
            root_strs = [str(r) for r in roots]
            nested_found = any("VoiceOverApp_OLD" in r and "VoiceOverApp" in r and "models" in r 
                              for r in root_strs)
            assert nested_found, f"Verschachtelter Root nicht gefunden. Gefunden: {root_strs}"
            
            # Teste Tokenizer-Discovery
            found, path = _find_model_in_roots(
                "Qwen3-TTS-Tokenizer-12Hz",
                ["models--Qwen--Qwen3-TTS-Tokenizer-12Hz", "models--Qwen3-TTS-Tokenizer-12Hz"],
                roots
            )
            assert found, "Tokenizer nicht in verschachtelter Struktur gefunden"
            assert "VoiceOverApp_OLD" in str(path), f"Falscher Pfad: {path}"
            
            print("✓ Test bestanden: Verschachtelte VoiceOverApp-Struktur")
        finally:
            if old_home:
                os.environ["HOME"] = old_home
            else:
                os.environ.pop("HOME", None)


def test_direct_tokenizer_directory():
    """Test: Direktes Tokenizer-Verzeichnis wird gefunden."""
    with tempfile.TemporaryDirectory() as tmpdir:
        models_root = Path(tmpdir) / "models"
        models_root.mkdir()
        
        # Erstelle direkten Tokenizer
        tokenizer_dir = models_root / "Qwen3-TTS-Tokenizer-12Hz"
        tokenizer_dir.mkdir()
        (tokenizer_dir / "config.json").write_text("{}")
        
        # Teste Discovery
        found, path = _find_model_in_roots(
            "Qwen3-TTS-Tokenizer-12Hz",
            ["models--Qwen--Qwen3-TTS-Tokenizer-12Hz"],
            [models_root]
        )
        
        assert found, "Direkter Tokenizer nicht gefunden"
        assert path == tokenizer_dir, f"Falscher Pfad: {path}"
        
        print("✓ Test bestanden: Direktes Tokenizer-Verzeichnis")


def test_hf_cache_tokenizer():
    """Test: Tokenizer im HF-Cache wird gefunden."""
    with tempfile.TemporaryDirectory() as tmpdir:
        models_root = Path(tmpdir) / "models"
        hf_hub = models_root / "hf" / "hub" / "models--Qwen--Qwen3-TTS-Tokenizer-12Hz" / "snapshots" / "abc123"
        hf_hub.mkdir(parents=True)
        
        # Erstelle config.json
        (hf_hub / "config.json").write_text("{}")
        
        # Teste Discovery
        found, path = _find_model_in_roots(
            "Qwen3-TTS-Tokenizer-12Hz",
            ["models--Qwen--Qwen3-TTS-Tokenizer-12Hz"],
            [models_root]
        )
        
        assert found, "HF-Cache Tokenizer nicht gefunden"
        assert "models--Qwen--Qwen3-TTS-Tokenizer-12Hz" in str(path), f"Falscher Pfad: {path}"
        
        print("✓ Test bestanden: HF-Cache Tokenizer")


def test_speech_tokenizer_in_base():
    """Test: speech_tokenizer in Base wird als Fallback gefunden."""
    with tempfile.TemporaryDirectory() as tmpdir:
        models_root = Path(tmpdir) / "models"
        
        # Erstelle Base mit speech_tokenizer
        base_dir = models_root / "Qwen3-TTS-12Hz-1.7B-Base"
        speech_tok = base_dir / "speech_tokenizer"
        speech_tok.mkdir(parents=True)
        (speech_tok / "config.json").write_text("{}")
        
        # Teste Discovery (nur für Tokenizer)
        found, path = _find_model_in_roots(
            "Qwen3-TTS-Tokenizer-12Hz",
            ["models--Qwen--Qwen3-TTS-Tokenizer-12Hz"],
            [models_root]
        )
        
        assert found, "speech_tokenizer in Base nicht gefunden"
        assert "speech_tokenizer" in str(path), f"Falscher Pfad: {path}"
        
        print("✓ Test bestanden: speech_tokenizer in Base")


def test_speech_tokenizer_in_customvoice():
    """Test: speech_tokenizer in CustomVoice wird als Fallback gefunden."""
    with tempfile.TemporaryDirectory() as tmpdir:
        models_root = Path(tmpdir) / "models"
        
        # Erstelle CustomVoice mit speech_tokenizer
        cv_dir = models_root / "Qwen3-TTS-12Hz-1.7B-CustomVoice"
        speech_tok = cv_dir / "speech_tokenizer"
        speech_tok.mkdir(parents=True)
        (speech_tok / "config.json").write_text("{}")
        
        # Teste Discovery (nur für Tokenizer)
        found, path = _find_model_in_roots(
            "Qwen3-TTS-Tokenizer-12Hz",
            ["models--Qwen--Qwen3-TTS-Tokenizer-12Hz"],
            [models_root]
        )
        
        assert found, "speech_tokenizer in CustomVoice nicht gefunden"
        assert "speech_tokenizer" in str(path), f"Falscher Pfad: {path}"
        
        print("✓ Test bestanden: speech_tokenizer in CustomVoice")


def test_speech_tokenizer_in_hf_cache():
    """Test: speech_tokenizer im HF-Cache wird gefunden."""
    with tempfile.TemporaryDirectory() as tmpdir:
        models_root = Path(tmpdir) / "models"
        
        # Erstelle Base im HF-Cache mit speech_tokenizer
        base_hf = models_root / "hf" / "hub" / "models--Qwen--Qwen3-TTS-12Hz-1.7B-Base" / "snapshots" / "abc123"
        speech_tok = base_hf / "speech_tokenizer"
        speech_tok.mkdir(parents=True)
        (speech_tok / "config.json").write_text("{}")
        
        # Teste Discovery (nur für Tokenizer)
        found, path = _find_model_in_roots(
            "Qwen3-TTS-Tokenizer-12Hz",
            ["models--Qwen--Qwen3-TTS-Tokenizer-12Hz"],
            [models_root]
        )
        
        assert found, "speech_tokenizer im HF-Cache nicht gefunden"
        assert "speech_tokenizer" in str(path), f"Falscher Pfad: {path}"
        
        print("✓ Test bestanden: speech_tokenizer im HF-Cache")


def test_full_multiroot_with_nested():
    """Test: Vollständige Multi-Root-Discovery mit verschachtelter Struktur."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # VoiceOverApp_LAB_NEXT mit CustomVoice + Base
        lab_next = Path(tmpdir) / "VoiceOverApp_LAB_NEXT" / "models"
        lab_next.mkdir(parents=True)
        
        cv_dir = lab_next / "Qwen3-TTS-12Hz-1.7B-CustomVoice"
        cv_dir.mkdir()
        (cv_dir / "config.json").write_text("{}")
        
        base_dir = lab_next / "Qwen3-TTS-12Hz-1.7B-Base"
        base_dir.mkdir()
        (base_dir / "config.json").write_text("{}")
        
        # VoiceOverApp_OLD mit verschachtelter Struktur und Tokenizer
        old_root = Path(tmpdir) / "VoiceOverApp_OLD" / "VoiceOverApp" / "models"
        old_root.mkdir(parents=True)
        
        tokenizer_dir = old_root / "Qwen3-TTS-Tokenizer-12Hz"
        tokenizer_dir.mkdir()
        (tokenizer_dir / "config.json").write_text("{}")
        
        # Simuliere Downloads-Verzeichnis
        downloads = Path(tmpdir) / "Downloads"
        downloads.mkdir()
        
        # Erstelle Symlinks
        lab_next_link = downloads / "VoiceOverApp_LAB_NEXT"
        lab_next_link.symlink_to(Path(tmpdir) / "VoiceOverApp_LAB_NEXT")
        
        old_app_link = downloads / "VoiceOverApp_OLD"
        old_app_link.symlink_to(Path(tmpdir) / "VoiceOverApp_OLD")
        
        # Setze HOME auf tmpdir
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = tmpdir
        
        # Setze explizite Models-Roots
        os.environ["VOICEOVER_MODELS_ROOTS"] = str(lab_next) + os.pathsep + str(old_root)
        
        try:
            # Teste check_models
            result = check_models()
            
            assert result["ok"], f"check_models fehlgeschlagen: {result}"
            
            # Prüfe ob alle Modelle gefunden wurden
            actual = result["actual"]
            assert "Qwen3-TTS-12Hz-1.7B-CustomVoice" in actual
            assert "Qwen3-TTS-12Hz-1.7B-Base" in actual
            assert "Qwen3-TTS-Tokenizer-12Hz" in actual
            
            # Prüfe Pfade
            found_paths = result["models_found_paths"]
            assert "Qwen3-TTS-12Hz-1.7B-CustomVoice" in found_paths
            assert "Qwen3-TTS-12Hz-1.7B-Base" in found_paths
            assert "Qwen3-TTS-Tokenizer-12Hz" in found_paths
            
            # Tokenizer sollte aus VoiceOverApp_OLD kommen
            tokenizer_path = found_paths["Qwen3-TTS-Tokenizer-12Hz"]
            assert "VoiceOverApp_OLD" in tokenizer_path, f"Tokenizer aus falschem Root: {tokenizer_path}"
            
            print("✓ Test bestanden: Vollständige Multi-Root-Discovery mit verschachtelter Struktur")
        finally:
            if old_home:
                os.environ["HOME"] = old_home
            else:
                os.environ.pop("HOME", None)
            os.environ.pop("VOICEOVER_MODELS_ROOTS", None)


if __name__ == "__main__":
    print("Starte Tokenizer-Discovery Regressionstests...\n")
    
    try:
        test_direct_tokenizer_directory()
        test_hf_cache_tokenizer()
        test_speech_tokenizer_in_base()
        test_speech_tokenizer_in_customvoice()
        test_speech_tokenizer_in_hf_cache()
        test_nested_voiceoverapp_structure()
        test_full_multiroot_with_nested()
        
        print("\n" + "="*60)
        print("✓ Alle 7 Tests bestanden!")
        print("="*60)
    except AssertionError as e:
        print(f"\n✗ Test fehlgeschlagen: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unerwarteter Fehler: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
