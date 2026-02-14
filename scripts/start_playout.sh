#!/bin/bash
# Hermes Radio — Start playout pipeline (Liquidsoap | FFmpeg → HLS)

set -euo pipefail

HLS_DIR="${HERMES_HLS_DIR:-/tmp/hls}"

# Ensure HLS directory exists
mkdir -p "$HLS_DIR"

# Clean stale segments
rm -f "$HLS_DIR"/*.ts "$HLS_DIR"/*.m4s "$HLS_DIR"/*.m3u8 "$HLS_DIR"/*.mp4

echo "[playout] Starting Liquidsoap | FFmpeg pipeline..."
echo "[playout] HLS output: $HLS_DIR/radio.m3u8"

liquidsoap /opt/hermes/playout/radio.liq 2>>/opt/hermes/data/logs/liquidsoap_stderr.log | \
ffmpeg -hide_banner -loglevel warning \
  -f wav -i pipe:0 \
  -c:a aac -b:a 128k -ar 44100 -ac 2 \
  -f hls \
  -hls_time 4 \
  -hls_list_size 10 \
  -hls_flags delete_segments+append_list+program_date_time \
  -hls_segment_type mpegts \
  -hls_segment_filename "$HLS_DIR/radio_%03d.ts" \
  "$HLS_DIR/radio.m3u8" \
  2>>/opt/hermes/data/logs/ffmpeg_stderr.log
