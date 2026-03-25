#!/usr/bin/env bash
# After build_macos.sh: zip BroNode.app for release (run from repo root).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -d dist/BroNode.app ]]; then
  echo "Run packaging/build_macos.sh first."
  exit 1
fi
VER="$(python3 -c "
import re
from pathlib import Path
t = Path('app.py').read_text(encoding='utf-8')
m = re.search(r'^APP_VERSION = \"([^\"]+)\"', t, re.M)
print(m.group(1) if m else '1.0.0')
")"
OUT="$ROOT/dist/bro-node-macos-${VER}.zip"
rm -f "$OUT"
( cd dist && zip -r -y "$OUT" BroNode.app )
echo "Created: $OUT"
