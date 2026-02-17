"""FFmpeg helper functions — run commands, probe durations, detect HW encoder."""

import json
import subprocess
from pathlib import Path

from visual.config import DEFAULT_ENCODER, WIDTH, HEIGHT, FPS, PIXEL_FMT


def run_ffmpeg(args: list[str], desc: str = "") -> None:
    """Run an FFmpeg command, raising on failure."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning"] + args
    print(f"[ffmpeg] {desc or ' '.join(cmd[:8])}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed ({desc}): {result.stderr[-500:]}")


def probe_duration_ms(path: str | Path) -> int:
    """Get duration of an audio/video file in milliseconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {result.stderr}")
    info = json.loads(result.stdout)
    duration_s = float(info["format"]["duration"])
    return int(duration_s * 1000)


def detect_encoder() -> str:
    """Detect the best available H.264 encoder.

    Tries v4l2m2m (Pi 5 HW), then falls back to libx264.
    """
    # Try v4l2m2m with a quick test encode
    try:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=black:s=64x64:d=0.1:r={FPS}",
            "-c:v", "h264_v4l2m2m",
            "-f", "null", "-",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("[ffmpeg] Using HW encoder: h264_v4l2m2m")
            return "h264_v4l2m2m"
    except (subprocess.TimeoutExpired, Exception):
        pass

    print(f"[ffmpeg] Using software encoder: {DEFAULT_ENCODER}")
    return DEFAULT_ENCODER


def get_encoder_args(encoder: str) -> list[str]:
    """Return encoder-specific FFmpeg arguments."""
    if encoder == "h264_v4l2m2m":
        return [
            "-c:v", "h264_v4l2m2m",
            "-b:v", "4M",
            "-pix_fmt", PIXEL_FMT,
        ]
    # libx264 default
    return [
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", PIXEL_FMT,
    ]


def decode_audio_to_raw(audio_path: str | Path) -> bytes:
    """Decode any audio file to raw PCM s16le mono via FFmpeg pipe."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(audio_path),
        "-f", "s16le", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        "pipe:1",
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"Audio decode failed: {result.stderr.decode()[-300:]}")
    return result.stdout
