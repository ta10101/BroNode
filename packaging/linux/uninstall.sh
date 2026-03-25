#!/usr/bin/env bash
# Remove BroNode GUI (does not remove Docker containers/images/volumes).
set -euo pipefail
PREFIX="${PREFIX:-/opt/BroNode}"
echo "=== BroNode uninstall ==="
echo "Removing app files from $PREFIX (your Docker data is not touched)."
sudo rm -f /usr/local/bin/bronode
sudo rm -f /usr/share/applications/bronode.desktop
sudo rm -rf "$PREFIX"
echo "Done. BroNode GUI removed."
