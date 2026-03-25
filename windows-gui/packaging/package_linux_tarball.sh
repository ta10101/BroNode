#!/usr/bin/env bash
# Build one-file Linux binary and pack tarball for release (run from windows-gui/).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

bash "$ROOT/packaging/build_linux.sh"

VER="$(python3 -c "
import re
from pathlib import Path
t = Path('app.py').read_text(encoding='utf-8')
m = re.search(r'^APP_VERSION = \"([^\"]+)\"', t, re.M)
print(m.group(1) if m else '1.0.0')
")"
STAGE="$ROOT/packaging/_stage/bro-node-linux-x64"
rm -rf "$ROOT/packaging/_stage"
mkdir -p "$STAGE"
cp "$ROOT/dist/BroNode" "$STAGE/"
chmod +x "$STAGE/BroNode"
cp "$ROOT/packaging/linux/install.sh" "$ROOT/packaging/linux/uninstall.sh" "$ROOT/packaging/linux/uninstall_docker_runtime.sh" "$ROOT/packaging/linux/bronode.desktop" "$STAGE/"
cp "$ROOT/docs/INSTALL_AND_UNINSTALL.md" "$STAGE/INSTALL_AND_UNINSTALL.md"
chmod +x "$STAGE/install.sh" "$STAGE/uninstall.sh" "$STAGE/uninstall_docker_runtime.sh"
ARCHIVE="$ROOT/dist/bro-node-linux-x64-${VER}.tar.gz"
tar -czvf "$ARCHIVE" -C "$ROOT/packaging/_stage" bro-node-linux-x64
echo "Created: $ARCHIVE"
