#!/usr/bin/env bash
# macOS .app bundle (onedir inside .app). Run only on macOS from repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 -m pip install --user --upgrade pip
python3 -m pip install --user -r requirements-build.txt

python3 -m PyInstaller --clean --noconfirm BroNode-macos.spec

echo "Built: $ROOT/dist/BroNode.app"
echo "Tip: codesign/notarize before public distribution. Zip: cd dist && zip -r bro-node-macos.zip BroNode.app"
