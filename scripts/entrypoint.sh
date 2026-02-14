#!/bin/bash
set -e

echo "[entrypoint] Hermes Radio starting..."

# Create data dirs
mkdir -p /opt/hermes/data/{logs,breaks,stings}
mkdir -p /opt/hermes/music
mkdir -p /tmp/hls

# Initialize DB if not exists
if [ ! -f "${HERMES_DB_PATH:-/opt/hermes/data/hermes.db}" ]; then
    echo "[entrypoint] Initializing database..."
    python3 /opt/hermes/scripts/init_db.py
fi

# Generate test music if directory is empty
if [ -z "$(ls -A /opt/hermes/music/*.mp3 2>/dev/null)" ]; then
    echo "[entrypoint] No music found, generating test tones..."
    ffmpeg -y -f lavfi -i "sine=frequency=440:duration=60" -c:a libmp3lame -b:a 128k \
        /opt/hermes/music/test_tone_A4_60s.mp3 2>/dev/null
    ffmpeg -y -f lavfi -i "sine=frequency=523:duration=45" -c:a libmp3lame -b:a 128k \
        /opt/hermes/music/test_tone_C5_45s.mp3 2>/dev/null
    ffmpeg -y -f lavfi -i "sine=frequency=659:duration=30" -c:a libmp3lame -b:a 128k \
        /opt/hermes/music/test_tone_E5_30s.mp3 2>/dev/null
    echo "[entrypoint] Generated 3 test tones"
fi

exec "$@"
