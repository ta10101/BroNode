# -*- mode: python ; coding: utf-8 -*-
# Build on each target OS from windows-gui/:  python -m PyInstaller --noconfirm BroNode.spec
# Linux: install libcairo2 (Debian/Ubuntu: apt install libcairo2) for cairosvg at runtime.

import os
import sys
from pathlib import Path

block_cipher = None
root = Path(os.path.dirname(os.path.abspath(SPEC)))

datas = []
binaries = []
hiddenimports = []

assets = root / "assets"
if assets.is_dir():
    datas.append((str(assets), "assets"))

try:
    from PyInstaller.utils.hooks import collect_all

    for pkg in (
        "cairosvg",
        "cairocffi",
        "tinycss2",
        "cssselect2",
        "defusedxml",
    ):
        try:
            d, b, h = collect_all(pkg)
            datas += d
            binaries += b
            hiddenimports += h
        except Exception:
            pass
except ImportError:
    hiddenimports += [
        "cairosvg",
        "cairocffi",
        "cffi",
        "tinycss2",
        "cssselect2",
        "defusedxml",
    ]

a = Analysis(
    [str(root / "app.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="BroNode",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=(sys.platform == "darwin"),
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
