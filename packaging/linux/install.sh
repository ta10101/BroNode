#!/usr/bin/env bash
# Install BroNode Linux binary (run from the extracted folder that contains BroNode + this script).
set -euo pipefail
PREFIX="${PREFIX:-/opt/BroNode}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HERE/BroNode"

echo "=== BroNode install ==="
echo "This will copy the app to $PREFIX, add the command 'bronode', and a menu shortcut."
echo "Docker must be installed separately (see https://docs.docker.com/engine/install/)."
echo "To remove only the GUI later: ./uninstall.sh"
echo "To remove Edge Node Docker data (container/image/volume): ./uninstall_docker_runtime.sh"
echo "Full guide: INSTALL_AND_UNINSTALL.md (in this folder)"
echo ""

if [[ ! -f "$BIN" ]]; then
  echo "ERROR: BroNode binary not found at $BIN"
  exit 1
fi

echo "[1/5] Creating install folder..."
sudo mkdir -p "$PREFIX"
echo "[2/5] Copying BroNode..."
sudo cp "$BIN" "$PREFIX/BroNode"
echo "[3/5] Setting permissions..."
sudo chmod 755 "$PREFIX/BroNode"
echo "[4/5] Adding bronode command (symlink)..."
sudo ln -sf "$PREFIX/BroNode" /usr/local/bin/bronode
echo "[5/5] Adding application menu entry..."
sudo install -Dm644 "$HERE/bronode.desktop" /usr/share/applications/bronode.desktop
echo ""
echo "Done. Start BroNode from your app menu or run: bronode"
