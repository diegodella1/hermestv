"""Hermes Radio — Centralized configuration from .env"""

import os
from pathlib import Path

# Base paths
BASE_DIR = Path(os.environ.get("HERMES_BASE_DIR", "/opt/hermes"))
DATA_DIR = Path(os.environ.get("HERMES_DATA_DIR", "/opt/hermes/data"))
MUSIC_DIR = Path(os.environ.get("HERMES_MUSIC_DIR", "/opt/hermes/music"))
MODELS_DIR = Path(os.environ.get("HERMES_MODELS_DIR", "/opt/hermes/models"))
HLS_DIR = Path(os.environ.get("HERMES_HLS_DIR", "/tmp/hls"))
DB_PATH = os.environ.get("HERMES_DB_PATH", str(DATA_DIR / "hermes.db"))

# API keys
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "")
HERMES_API_KEY = os.environ.get("HERMES_API_KEY", "changeme")

# Liquidsoap
LIQUIDSOAP_SOCKET = os.environ.get("LIQUIDSOAP_SOCKET", "/tmp/liquidsoap.sock")

# FastAPI
HERMES_HOST = os.environ.get("HERMES_HOST", "127.0.0.1")
HERMES_PORT = int(os.environ.get("HERMES_PORT", "8100"))

# Base path for reverse proxy (e.g. "/hermestv" when behind Traefik)
BASE_PATH = os.environ.get("HERMES_BASE_PATH", "").rstrip("/")

# Piper TTS
PIPER_BIN = os.environ.get("PIPER_BIN", "/usr/local/bin/piper")

# Breaks directory
BREAKS_DIR = DATA_DIR / "breaks"
STINGS_DIR = DATA_DIR / "stings"
LOGS_DIR = DATA_DIR / "logs"
