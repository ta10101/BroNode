#!/usr/bin/env bash
# Remove Holo Edge Node Docker resources (container, image, volume). DATA LOSS on volume.
# Does NOT remove BroNode GUI. Works on Linux and macOS (Docker on PATH).
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-edgenode}"
IMAGE_NAME="${IMAGE_NAME:-ghcr.io/holo-host/edgenode}"
VOLUME_NAME="${VOLUME_NAME:-holo-data}"

echo "=== Edge Node Docker cleanup ==="
echo "This will remove:"
echo "  Container: $CONTAINER_NAME"
echo "  Image:     $IMAGE_NAME"
echo "  Volume:    $VOLUME_NAME  (all persisted node data in this volume)"
echo ""
read -r -p "Type YES to continue: " confirm
if [[ "$confirm" != "YES" ]]; then
  echo "Cancelled."
  exit 0
fi

echo "[1/3] Removing container..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
echo "[2/3] Removing image..."
docker rmi "$IMAGE_NAME" 2>/dev/null || true
echo "[3/3] Removing volume..."
docker volume rm "$VOLUME_NAME" 2>/dev/null || true
echo "Done. BroNode app was not removed."
