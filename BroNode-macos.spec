# -*- mode: python ; coding: utf-8 -*-
# macOS only: dist/BroNode.app (onedir bundle). Build on a Mac:
#   python -m PyInstaller --noconfirm BroNode-macos.spec

import os
import sys
from pathlib import Path

assert sys.platform == "darwin", "BroNode-macos.spec must be built on macOS"

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
    [],
    exclude_binaries=True,
    name="BroNode",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BroNode",
)

app = BUNDLE(
    coll,
    name="BroNode.app",
    bundle_identifier="com.bronode.gui",
    info_plist={
        "NSPrincipalClass": "NSApplication",
        "NSHighResolutionCapable": True,
        "CFBundleDisplayName": "BroNode",
        "CFBundleName": "BroNode",
        "CFBundleShortVersionString": "1.0.2",
        "CFBundleVersion": "1.0.2",
    },
)
