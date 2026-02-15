#!/bin/bash
# Hermes Radio — Start playout pipeline (Liquidsoap → FIFO → FFmpeg → HLS)
# Uses a named pipe (FIFO) instead of stdout to avoid broken pipe issues in 2.1.x

set -eu

HLS_DIR="${HERMES_HLS_DIR:-/tmp/hls}"
FIFO="/tmp/hermes_audio.fifo"
LOGS="/opt/hermes/data/logs"

# Ensure directories exist
mkdir -p "$HLS_DIR" "$LOGS"

# Clean stale segments
rm -f "$HLS_DIR"/*.ts "$HLS_DIR"/*.m4s "$HLS_DIR"/*.m3u8 "$HLS_DIR"/*.mp4

# Create FIFO
rm -f "$FIFO"
mkfifo "$FIFO"

echo "[playout] Starting playout pipeline..."
echo "[playout] HLS output: $HLS_DIR/radio.m3u8"

# Generate playlist file from music directory
PLAYLIST="/opt/hermes/music/playlist.m3u"
echo "[playout] Generating playlist..."
find /opt/hermes/music/ -maxdepth 1 -iname '*.mp3' -type f | sort > "$PLAYLIST"
echo "[playout] Playlist: $(wc -l < "$PLAYLIST") tracks"
cat "$PLAYLIST"

# PIDs for cleanup
FFMPEG_PID=""

# Cleanup on exit
cleanup() {
    echo "[playout] Shutting down..."
    [ -n "$FFMPEG_PID" ] && kill "$FFMPEG_PID" 2>/dev/null || true
    rm -f "$FIFO"
    exit 0
}
trap cleanup EXIT TERM INT

# Start FFmpeg reading from FIFO (background)
ffmpeg -hide_banner -loglevel warning \
  -f wav -i "$FIFO" \
  -c:a aac -b:a 128k -ar 44100 -ac 2 \
  -f hls \
  -hls_time 4 \
  -hls_list_size 10 \
  -hls_flags delete_segments+append_list+program_date_time \
  -hls_segment_type mpegts \
  -hls_segment_filename "$HLS_DIR/radio_%03d.ts" \
  "$HLS_DIR/radio.m3u8" \
  2>>"$LOGS/ffmpeg_stderr.log" &
FFMPEG_PID=$!

# Start Liquidsoap writing to FIFO (foreground — supervisord monitors this)
# When liquidsoap exits, the script exits and cleanup kills FFmpeg
liquidsoap /opt/hermes/playout/radio.liq 2>>"$LOGS/liquidsoap_stderr.log"
