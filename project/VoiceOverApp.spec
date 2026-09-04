# -*- mode: python ; coding: utf-8 -*-
# ============================================================
#  VoiceOverApp 2.0 - PyInstaller-Spec (§7/§8)
#
#  Entry-Point: desktop.py  (GUI-Hauptdatei des Projekts)
#
#  Erzeugt EINE ONEDIR-Auslieferung mit ZWEI Executables:
#    VoiceOverApp.exe         = Desktop-GUI (windowed, kein Konsolen-
#                               fenster) - Normalstart per Doppelklick
#    VoiceOverAppBackend.exe  = Konsolen-Backend für --job (JSONL auf
#                               stdout; wird von der GUI als Subprocess
#                               gestartet, §16)
#
#  Alle Ressourcen (models/, config/, voices/, pronunciation/, cache/,
#  input/, output/) liegen NEBEN der EXE (relative Pfade, §9);
#  paths.py bestimmt den App-Root über das EXE-Verzeichnis.
#
#  Build:  .\.venv\Scripts\python.exe -m PyInstaller VoiceOverApp.spec
#  (wird von build_windows.ps1 aufgerufen)
# ============================================================

block_cipher = None

a = Analysis(
    ['desktop.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # App-Daten (Aussprache-Built-ins) mit einfrieren, damit sie
        # auch im _internal-Pfad auffindbar sind:
        ('app/pronunciation/builtins_de.json', 'app/pronunciation'),
        ('app/pronunciation/builtins_en.json', 'app/pronunciation'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# --- GUI-EXE (windowed: kein Konsolenfenster, Normalstart) -----------
gui_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VoiceOverApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                    # GUI ohne Konsole
)

# --- Backend-EXE (console: stdout=JSONL für die GUI) ------------------
backend_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VoiceOverAppBackend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,                     # Backend braucht stdout
)

coll = COLLECT(
    gui_exe,
    backend_exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='VoiceOverApp',
)
