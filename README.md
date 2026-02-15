# Hermes Radio

AI-powered 24/7 internet radio station that runs on a Raspberry Pi 5. Plays music from a local library and inserts short radio breaks every few tracks with weather updates, news headlines, and two AI hosts with distinct personalities — all generated in real time.

## How It Works

```
MP3 Library ──> Liquidsoap ──> Named FIFO ──> FFmpeg ──> HLS Stream
                    ^                                        |
                    |                                        v
              Break Queue                              Web Player
                    ^                                   /hls/radio.m3u8
                    |
            FastAPI (Core)
           /     |      \
     Weather   News    GPT-4o-mini ──> Piper TTS
    (API)    (RSS)    (script gen)    (local voices)
```

**The cycle:**
1. Music plays in the order you set (loops back to track 1 after the last track)
2. At track N-1 (default: track 3), the system starts preparing the next break in the background
3. After track N (default: track 4), a 10-15 second break plays with weather + news
4. Two hosts alternate — **Luna** (warm, curious) and **Max** (sharp, direct)
5. Counter resets, repeat

If any external service fails, the system degrades gracefully through 4 levels — from template-only breaks down to just continuing the music.

## Features

- **AI Radio Hosts**: Two TTS voices (Piper, local, free) with unique personalities, alternating every break
- **Live Weather**: Real-time weather for configurable cities via WeatherAPI.com
- **News Headlines**: RSS feeds scored by GPT-4o-mini for relevance, top 1-3 headlines per break
- **Breaking News**: Manual trigger interrupts music immediately with urgent updates
- **Playlist Management**: Upload, reorder (drag-and-drop), enable/disable tracks from admin UI
- **Content Safety**: Post-LLM content filter blocks financial advice, URLs, political opinions
- **Graceful Degradation**: 5 levels — full break → template + weather → sting only → music continues
- **Admin Panel**: Full CRUD for cities, news sources, hosts, prompts, rules, music, logs
- **HLS Streaming**: Browser-compatible stream, playable with any HLS player
- **Single Container**: Docker image with supervisord managing playout + API server

## Quick Start

### Prerequisites

- Docker (tested on Docker 29+)
- An [OpenAI API key](https://platform.openai.com) (for news scoring + script generation)
- A [WeatherAPI.com key](https://www.weatherapi.com) (free tier, 1M calls/month)

### Run with Docker

```bash
docker build -t hermes-radio .

docker run -d \
  --name hermes \
  -p 8100:8100 \
  -e OPENAI_API_KEY=sk-your-key \
  -e WEATHER_API_KEY=your-key \
  -e HERMES_API_KEY=your-admin-password \
  -v hermes-music:/opt/hermes/music \
  -v hermes-data:/opt/hermes/data \
  hermes-radio
```

Then open:
- **Player**: `http://localhost:8100/`
- **Admin**: `http://localhost:8100/admin/`
- **Stream**: `http://localhost:8100/hls/radio.m3u8`

### Deploy with Coolify

1. Connect your GitHub repo in Coolify
2. Set environment variables: `OPENAI_API_KEY`, `WEATHER_API_KEY`, `HERMES_API_KEY`
3. Add persistent storage:
   - `/opt/hermes/music` (music library)
   - `/opt/hermes/data` (database + logs + generated breaks)
4. Set container port to `8100`
5. Deploy

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | - | OpenAI API key for GPT-4o-mini |
| `WEATHER_API_KEY` | Yes | - | WeatherAPI.com key |
| `HERMES_API_KEY` | No | `changeme` | Admin panel password |
| `HERMES_DATA_DIR` | No | `/opt/hermes/data` | Database, logs, generated audio |
| `HERMES_MUSIC_DIR` | No | `/opt/hermes/music` | MP3 music library |
| `HERMES_PORT` | No | `8100` | FastAPI server port |

See [`.env.example`](.env.example) for the full list.

### Admin Panel

Access at `/admin/` (password = `HERMES_API_KEY`).

| Page | What you can do |
|------|-----------------|
| **Dashboard** | View now playing, break stats, feed health |
| **Rules** | Set break frequency, quiet mode, score thresholds |
| **Cities** | Add/remove weather cities (lat/lon, timezone, units) |
| **Sources** | Manage RSS feeds, view feed health |
| **Hosts** | Edit host names, personality prompts, enable/disable |
| **Prompts** | Edit the master system prompt for all breaks |
| **Music** | Upload/delete MP3s, reorder playlist, enable/disable tracks |
| **Logs** | View event log (breaks, errors, track changes) |
| **Breaking** | Manually trigger a breaking news interrupt |

### Break Settings (via Rules page)

| Setting | Default | Description |
|---------|---------|-------------|
| `every_n_tracks` | 4 | Break after every N tracks |
| `prepare_at_track` | 3 | Start preparing break at this track count |
| `quiet_mode` | false | Disable all breaks |
| `breaking_score_threshold` | 8 | Headlines scoring 8+ trigger breaking news |
| `news_dedupe_window_minutes` | 60 | Don't repeat headlines within this window |

## Architecture

### Container Layout

A single Docker container runs two processes via supervisord:

```
supervisord
├── playout (Liquidsoap → FIFO → FFmpeg → HLS)
└── core    (FastAPI/uvicorn on :8100)
```

### Audio Pipeline

```
Liquidsoap (playlist + break queues)
    │
    ▼  WAV via named FIFO (/tmp/hermes_audio.fifo)
    │
  FFmpeg
    │
    ▼  HLS segments (AAC 128kbps, 4s segments)
    │
  /tmp/hls/radio.m3u8
    │
    ▼  Served by FastAPI static mount
    │
  Browser / HLS player
```

### Break Generation Pipeline

When the track counter reaches `prepare_at_track`:

```
1. Pick next host (Luna ↔ Max rotation)
2. Fetch weather for enabled cities (WeatherAPI, 10-min cache)
3. Fetch headlines from RSS feeds (6 default sources)
4. Score headlines with GPT-4o-mini (1-10 relevance)
5. Generate break script with GPT-4o-mini (host personality + context)
6. Validate script (content filter: word count, blocked terms)
7. Synthesize audio with Piper TTS (local ONNX models)
8. Normalize loudness with FFmpeg (-16 LUFS)
9. Push MP3 to Liquidsoap break queue
```

Total pipeline time: ~25-30 seconds, prepared while music still plays.

### Degradation Levels

| Level | Condition | What plays |
|-------|-----------|------------|
| 0 | Everything works | Full break: weather + news + host voice |
| 1 | LLM slow/partial | Cached template + fresh data + TTS |
| 2 | LLM down | Pre-written template with weather only |
| 3 | TTS down | Pre-recorded sting (station ID jingle) |
| 4 | Everything down | Music continues, no break |

## Project Structure

```
hermes/
├── Dockerfile
├── supervisord.conf
├── requirements.txt
├── schema.sql                    # Database schema + defaults
├── .env.example
│
├── core/                         # FastAPI application
│   ├── main.py                   # App setup, lifespan, router mounting
│   ├── config.py                 # Environment config
│   ├── database.py               # SQLite (aiosqlite) init + access
│   │
│   ├── routers/
│   │   ├── admin.py              # Admin UI + music management + auth
│   │   ├── playout.py            # Track event webhook from Liquidsoap
│   │   ├── status.py             # Health check, playout start/stop
│   │   ├── breaking.py           # Breaking news trigger
│   │   └── logs.py               # Event log viewer
│   │
│   ├── providers/
│   │   ├── llm.py                # OpenAI: headline scoring + script writing
│   │   ├── weather.py            # WeatherAPI.com with caching
│   │   ├── news.py               # RSS fetching + feed health
│   │   └── tts_piper.py          # Piper TTS synthesis + FFmpeg normalize
│   │
│   ├── services/
│   │   ├── break_builder.py      # Orchestrates the full break pipeline
│   │   ├── break_queue.py        # Break status tracking (PREPARING → PLAYED)
│   │   ├── content_filter.py     # Post-LLM validation
│   │   ├── degradation.py        # Fallback templates
│   │   ├── host_rotation.py      # Luna ↔ Max alternation
│   │   └── liquidsoap_client.py  # Unix socket control
│   │
│   ├── templates/                # Jinja2 (Admin UI, PicoCSS + HTMX)
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── music.html            # Playlist management (drag-and-drop)
│   │   ├── player.html           # Web player (HLS.js)
│   │   └── ...
│   │
│   └── static/
│       └── style.css
│
├── playout/
│   └── radio.liq                 # Liquidsoap script
│
├── scripts/
│   ├── entrypoint.sh             # Container startup (DB init, test tones, supervisord)
│   ├── start_playout.sh          # FIFO + FFmpeg + Liquidsoap startup
│   ├── init_db.py                # Database initialization
│   ├── deploy.sh                 # Deployment helper
│   ├── setup.sh                  # Native install (non-Docker)
│   └── watchdog.sh               # Process health monitor (for systemd deploy)
│
└── config/
    ├── caddy/Caddyfile            # For native/systemd deploy (not used in Docker)
    └── systemd/                   # Service files for native deploy
        ├── hermes-playout.service
        ├── hermes-core.service
        └── ...
```

## Database

SQLite with WAL mode. Auto-initialized on first run from `schema.sql`.

### Tables

| Table | Purpose |
|-------|---------|
| `settings` | Key-value config (break frequency, prompts, thresholds) |
| `hosts` | AI host definitions (name, voice model, personality prompt) |
| `cities` | Weather locations (lat/lon, timezone, units) |
| `news_sources` | RSS feed URLs with polling config |
| `feed_health` | Feed failure tracking (healthy/unhealthy/dead) |
| `cache_weather` | Weather response cache (10-min TTL) |
| `cache_news` | Fetched headlines with LLM scores |
| `break_queue` | Break lifecycle (PREPARING → READY → PLAYED/FAILED) |
| `fallback_templates` | 5 pre-written weather-only break templates |
| `events_log` | All events with timestamps and latencies |
| `host_rotation` | Tracks which host goes next |

## API Endpoints

### Public

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Web player page |
| GET | `/hls/radio.m3u8` | HLS stream manifest |
| GET | `/api/health` | System health check |

### Authenticated (X-API-Key header or session cookie)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/settings` | Get all settings |
| PUT | `/api/admin/settings` | Update settings |
| GET/POST/DELETE | `/api/admin/cities[/{id}]` | CRUD cities |
| POST | `/api/breaking/trigger` | Trigger breaking news |
| POST | `/api/playout/start` | Start playout |
| POST | `/api/playout/stop` | Stop playout |
| GET | `/api/status/now-playing` | Current track + break status |

### Internal (localhost only)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/playout/event` | Liquidsoap track-ended webhook |

## Hosts

| Host | Voice | Personality |
|------|-------|-------------|
| **Luna** | `en_US-lessac-high` (female) | Warm, curious, relaxed energy. Casual connectors. NPR meets indie radio. |
| **Max** | `en_US-ryan-high` (male) | Direct, dry wit, short sentences. Designated breaking news host. |

Both voices are [Piper TTS](https://github.com/rhasspy/piper) ONNX models baked into the Docker image. No cloud TTS needed.

## Default News Sources

| Source | Category |
|--------|----------|
| Reuters World | World |
| BBC News | General |
| AP News | General |
| Al Jazeera | World |
| TechCrunch | Tech |
| Ars Technica | Tech |

All configurable via admin panel. Feeds are health-tracked — after 5 consecutive failures a feed is marked as dead.

## Cost

| Service | Monthly Cost |
|---------|-------------|
| OpenAI GPT-4o-mini (~6k calls) | ~$3-5 |
| WeatherAPI.com | Free |
| Piper TTS (local) | Free |
| RSS feeds | Free |
| **Total** | **~$3-5/month** |

## Native Install (without Docker)

For running directly on a Raspberry Pi with systemd:

```bash
# Install dependencies
sudo apt install liquidsoap ffmpeg espeak-ng python3 python3-venv

# Install Piper TTS
# See Dockerfile for download URLs

# Setup
cd /opt/hermes
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys

# Initialize database
python3 scripts/init_db.py

# Install systemd services
sudo cp config/systemd/*.service /etc/systemd/system/
sudo cp config/systemd/hermes.target /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable hermes.target
sudo systemctl start hermes.target
```

Caddy config is included at `config/caddy/Caddyfile` for reverse proxying in native mode.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Playout Engine | [Liquidsoap](https://www.liquidsoap.info/) 2.1.3 |
| Backend | [FastAPI](https://fastapi.tiangolo.com/) + [aiosqlite](https://github.com/omnilib/aiosqlite) |
| Frontend | [Jinja2](https://jinja.palletsprojects.com/) + [PicoCSS](https://picocss.com/) + [HTMX](https://htmx.org/) |
| TTS | [Piper](https://github.com/rhasspy/piper) (local ONNX inference) |
| LLM | OpenAI GPT-4o-mini |
| Streaming | FFmpeg → HLS (mpegts, 4s segments) |
| Player | [HLS.js](https://github.com/video-dev/hls.js/) |
| Database | SQLite (WAL mode) |
| Process Manager | supervisord |

## License

MIT
