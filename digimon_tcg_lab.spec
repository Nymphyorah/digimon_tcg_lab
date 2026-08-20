# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Digimon TCG Lab.
# Bundles the read-only application data (data/*.json, assets, cards) next to the exe.

import sys
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "data" / "cards.json"), "data"),
    (str(ROOT / "data" / "decks.json"), "data"),
    (str(ROOT / "data" / "tournaments.json"), "data"),
    (str(ROOT / "data" / "meta.json"), "data"),
    (str(ROOT / "data" / "meta_entries.json"), "data"),
    (str(ROOT / "data" / "version.json"), "data"),
    (str(ROOT / "data" / "history.json"), "data"),
    (str(ROOT / "assets" / "style.qss"), "assets"),
]

# cards/ may be empty on a fresh checkout; PyInstaller needs at least one file to
# create the folder, so only add it if it actually has images.
cards_dir = ROOT / "cards"
if cards_dir.exists() and any(cards_dir.iterdir()):
    datas.append((str(cards_dir), "cards"))

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=["pyqtgraph"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="DigimonTCGLab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
