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

# Use existing playlist (admin-managed order) or generate a default one
PLAYLIST="/opt/hermes/music/playlist.m3u"
if [ -s "$PLAYLIST" ]; then
    echo "[playout] Using existing playlist (admin-managed)"
else
    echo "[playout] No playlist found, generating default from disk..."
    find /opt/hermes/music/ -maxdepth 1 -iname '*.mp3' -type f | sort > "$PLAYLIST"
fi
echo "[playout] Playlist: $(wc -l < "$PLAYLIST") tracks"

# PIDs for cleanup
FFMPEG_PID=""

# Cleanup on exit — also purge HLS so player doesn't get stale segments
cleanup() {
    echo "[playout] Shutting down..."
    [ -n "$FFMPEG_PID" ] && kill "$FFMPEG_PID" 2>/dev/null || true
    rm -f "$FIFO"
    rm -f "$HLS_DIR"/*.ts "$HLS_DIR"/*.m4s "$HLS_DIR"/*.m3u8 "$HLS_DIR"/*.mp4
    echo "[playout] HLS segments purged"
    exit 0
}
trap cleanup EXIT TERM INT

# Epoch-based start number avoids segment name collisions with browser cache
START_NUM=$(( $(date +%s) % 100000 ))

# Start FFmpeg reading from FIFO (background)
# - thread_queue_size: larger input buffer to absorb Liquidsoap track-transition gaps
# - hls_time 6: longer segments = more stable playback (tradeoff: 6s extra latency)
# - hls_list_size 20: ~120s window so slow clients don't get 404 on deleted segments
# - independent_segments: tells player each segment decodes standalone → faster seek/start
# - removed discont_start (caused unnecessary rebuffering on playlist load)
ffmpeg -hide_banner -loglevel warning \
  -thread_queue_size 1024 \
  -f wav -i "$FIFO" \
  -c:a aac -b:a 128k -ar 44100 -ac 2 \
  -f hls \
  -hls_time 6 \
  -hls_list_size 20 \
  -hls_flags delete_segments+program_date_time+independent_segments \
  -hls_segment_type mpegts \
  -start_number "$START_NUM" \
  -hls_segment_filename "$HLS_DIR/radio_%05d.ts" \
  "$HLS_DIR/radio.m3u8" \
  2>>"$LOGS/ffmpeg_stderr.log" &
FFMPEG_PID=$!

# Start Liquidsoap writing to FIFO (foreground — supervisord monitors this)
# When liquidsoap exits, the script exits and cleanup kills FFmpeg
liquidsoap /opt/hermes/playout/radio.liq 2>>"$LOGS/liquidsoap_stderr.log"
