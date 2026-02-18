#!/bin/bash
set -e

echo "[entrypoint] Hermes TV starting..."

# Create data dirs
mkdir -p /opt/hermes/data/{logs,breaks,stings}
mkdir -p /tmp/hls_video

# Initialize DB if not exists
if [ ! -f "${HERMES_DB_PATH:-/opt/hermes/data/hermes.db}" ]; then
    echo "[entrypoint] Initializing database..."
    python3 /opt/hermes/scripts/init_db.py
fi

exec "$@"
