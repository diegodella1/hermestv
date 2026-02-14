#!/bin/bash
# Hermes Radio — Deploy from dev to /opt/hermes/
# Usage: sudo bash scripts/deploy.sh

set -euo pipefail

SRC="/home/diego/Documents/hermes"
DST="/opt/hermes"

echo "=== Deploying Hermes Radio ==="
echo "Source: $SRC"
echo "Target: $DST"

# Sync code (exclude dev-only files)
rsync -av --delete \
    --exclude='.git' \
    --exclude='.claude' \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='.env' \
    --exclude='*.pyc' \
    --exclude='prdhermes.md' \
    --exclude='models/*.onnx' \
    --exclude='models/*.json' \
    "$SRC/" "$DST/"

# Create .env if it doesn't exist
if [ ! -f "$DST/.env" ]; then
    cp "$DST/.env.example" "$DST/.env"
    echo "[!] Created .env from .env.example — fill in API keys!"
fi

# Ensure data dirs exist
mkdir -p "$DST/data/"{logs,breaks,stings}
mkdir -p "$DST/music"
mkdir -p /tmp/hls

# Install/update Python deps
if [ -d "$DST/venv" ]; then
    "$DST/venv/bin/pip" install -q -r "$DST/requirements.txt"
fi

# Init DB
"$DST/venv/bin/python" "$DST/scripts/init_db.py"

# Set ownership
chown -R hermes:hermes "$DST"
chown -R hermes:hermes /tmp/hls

# Install systemd services
for svc in "$DST/config/systemd/"*; do
    cp "$svc" /etc/systemd/system/
done
systemctl daemon-reload

echo ""
echo "=== Deploy Complete ==="
echo "Run: sudo systemctl start hermes.target"
