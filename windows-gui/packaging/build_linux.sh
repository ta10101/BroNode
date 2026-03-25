#!/usr/bin/env bash
# Linux one-file GUI binary (from windows-gui/). Requires: python3, python3-tk, libcairo2 for mascot.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 -m pip install --user --upgrade pip
python3 -m pip install --user -r requirements-build.txt

python3 -m PyInstaller --clean --noconfirm BroNode.spec

echo "Built: $ROOT/dist/BroNode"
