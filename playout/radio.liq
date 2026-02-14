#!/usr/bin/liquidsoap

# ============================================================
# Hermes Radio — Liquidsoap Playout Script
# Compatible with Liquidsoap 2.1.x (Debian apt)
# ============================================================

# --- Logging ---
set("log.file.path", "/opt/hermes/data/logs/liquidsoap.log")
set("log.stdout", true)
set("log.level", 3)

# --- Server (Unix socket for FastAPI control) ---
set("server.socket", true)
set("server.socket.path", "/tmp/liquidsoap.sock")
set("server.socket.permissions", 0o660)
set("server.telnet", false)

# --- Sources ---

# Music: shuffle playlist from local directory
music = playlist(
  id="music",
  mode="randomize",
  reload=600,
  reload_mode="rounds",
  "/opt/hermes/music/"
)

# Break queue (regular breaks — waits for track end)
breaks = request.queue(id="breaks")

# Stings queue (breaking — interrupts immediately)
stings = request.queue(id="stings")

# Safety fallback — silence if nothing else plays
security = blank(id="security")

# --- Track counter + webhook to FastAPI ---
track_count = ref(0)

def on_track_change(m) =
  track_count := !track_count + 1

  artist = m["artist"]
  title = m["title"]
  filename = m["filename"]

  payload = '{"event":"TRACK_ENDED","track":{"artist":"' ^ artist ^ '","title":"' ^ title ^ '","filename":"' ^ filename ^ '"},"tracks_since_last_break":' ^ string_of(!track_count) ^ '}'

  ignore(
    http.post(
      headers=[("Content-Type", "application/json")],
      data=payload,
      timeout=5.0,
      "http://127.0.0.1:8100/api/playout/event"
    )
  )
end

music = on_track(on_track_change, music)

# --- Crossfade ---
music = crossfade(
  duration=3.0,
  fade_out=2.5,
  fade_in=0.5,
  music
)

# --- Composition ---
# Breaks: track-sensitive (wait for current track to end)
radio = fallback(
  id="radio",
  track_sensitive=true,
  [breaks, music]
)

# Stings: not track-sensitive (interrupt immediately)
radio = fallback(
  id="with_stings",
  track_sensitive=false,
  [stings, radio]
)

# Safety net
radio = mksafe(fallback([radio, security]))

# --- Server commands (callable via Unix socket) ---
server.register(
  namespace="hermes",
  description="Reset track counter",
  usage="reset_counter",
  "reset_counter",
  fun(_) -> begin
    track_count := 0
    "Counter reset to 0"
  end
)

server.register(
  namespace="hermes",
  description="Get current track count",
  usage="track_count",
  "track_count",
  fun(_) -> begin
    string_of(!track_count)
  end
)

server.register(
  namespace="hermes",
  description="Skip current track",
  usage="skip",
  "skip",
  fun(_) -> begin
    source.skip(radio)
    "Skipped"
  end
)

# --- Output: WAV to stdout (piped to FFmpeg) ---
output.file(
  %wav(
    stereo=true,
    channels=2,
    samplesize=16,
    header=true
  ),
  fallible=false,
  reopen_on_metadata=false,
  "/dev/stdout",
  radio
)
