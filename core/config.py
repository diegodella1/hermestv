"""Hermes TV — Centralized configuration from .env"""

import os
from pathlib import Path

# Base paths
BASE_DIR = Path(os.environ.get("HERMES_BASE_DIR", "/opt/hermes"))
DATA_DIR = Path(os.environ.get("HERMES_DATA_DIR", "/opt/hermes/data"))
MODELS_DIR = Path(os.environ.get("HERMES_MODELS_DIR", "/opt/hermes/models"))
DB_PATH = os.environ.get("HERMES_DB_PATH", str(DATA_DIR / "hermes.db"))

# API keys
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "")
HERMES_API_KEY = os.environ.get("HERMES_API_KEY", "changeme")

# FastAPI
HERMES_HOST = os.environ.get("HERMES_HOST", "127.0.0.1")
HERMES_PORT = int(os.environ.get("HERMES_PORT", "8100"))

# Base path for reverse proxy (e.g. "/hermestv" when behind Traefik)
BASE_PATH = os.environ.get("HERMES_BASE_PATH", "").rstrip("/")

# Piper TTS
PIPER_BIN = os.environ.get("PIPER_BIN", "/usr/local/bin/piper")

# Assets (characters, backgrounds)
ASSETS_DIR = Path(os.environ.get("HERMES_ASSETS_DIR", str(BASE_DIR / "assets")))

# Breaks directory
BREAKS_DIR = DATA_DIR / "breaks"
STINGS_DIR = DATA_DIR / "stings"
LOGS_DIR = DATA_DIR / "logs"
HLS_VIDEO_DIR = Path(os.environ.get("HERMES_HLS_VIDEO_DIR", "/tmp/hls_video"))

# Scheduler default
BREAK_INTERVAL_MINUTES = int(os.environ.get("HERMES_BREAK_INTERVAL_MINUTES", "15"))
