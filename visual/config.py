"""Visual module constants and configuration."""

import os
from pathlib import Path

# Video
WIDTH = 1920
HEIGHT = 1080
FPS = 24
PIXEL_FMT = "yuv420p"

# Audio
AUDIO_SAMPLE_RATE = 44100
AUDIO_CHANNELS = 2

# Codec — overridden at runtime by detect_encoder()
DEFAULT_ENCODER = "libx264"
ENCODER_PRESET = "fast"  # x264 preset (ignored by HW encoders)
CRF = "23"

# RMS lip-sync
RMS_THRESHOLD = 0.02  # fraction of max amplitude
RMS_SMOOTHING_FRAMES = 2  # ignore flips shorter than this

# Director defaults (Phase 1 — kept for backward compat)
WIDE_SHOT_DURATION_S = 2.0  # wide shot at scene start
MIN_CLOSEUP_DURATION_S = 1.0

# Director Phase 2 — reaction shots, twoshots, timing
REACTION_PROBABILITY = 0.20
REACTION_MIN_MS = 1500
REACTION_MAX_MS = 3000
TWOSHOT_MIN_MS = 3000
TWOSHOT_MAX_MS = 6000
WIDE_SHOT_MIN_MS = 2000
WIDE_SHOT_MAX_MS = 4000
MIN_SHOT_DURATION_MS = 2000
MAX_SHOT_DURATION_MS = 8000
NO_CUT_FIRST_MS = 1500  # don't cut away in the first N ms of a line
WIDE_SHOT_INTERVAL = 4  # insert wide every N lines without one
RAPID_EXCHANGE_MS = 2000  # if gap between speakers < this → twoshot

# Transition probabilities
TRANSITION_CUT = 0.85
TRANSITION_DISSOLVE = 0.10
TRANSITION_FADE_BLACK = 0.05
DISSOLVE_DURATION_S = 0.5  # dissolve transition duration
FADE_BLACK_DURATION_S = 0.5  # fade to black duration

# Transitions
CROSSFADE_DURATION_S = 0.5  # crossfade between segments (0 = hard cut)

# Paths (relative to project root, overridable via env)
PROJECT_ROOT = Path(os.environ.get(
    "HERMES_ROOT", Path(__file__).resolve().parent.parent
))
DEFAULT_ASSETS_DIR = Path(os.environ.get(
    "HERMES_VISUAL_ASSETS", PROJECT_ROOT / "assets"
))
DEFAULT_OUTPUT_DIR = Path(os.environ.get(
    "HERMES_VISUAL_OUTPUT", PROJECT_ROOT / "output"
))
