"""Audio analysis — RMS-based lip-sync detection."""

import numpy as np

from visual.config import FPS, RMS_THRESHOLD, RMS_SMOOTHING_FRAMES
from visual.ffmpeg_utils import decode_audio_to_raw


def analyze_lipsync(audio_path: str, fps: int = FPS) -> list[bool]:
    """Analyze audio and return a bool per video frame: True = talking.

    Pipeline:
    1. Decode to raw PCM s16le mono 16kHz via FFmpeg
    2. Compute RMS per frame-aligned window
    3. Threshold → bool
    4. Smooth out isolated flips
    """
    raw_bytes = decode_audio_to_raw(audio_path)
    if not raw_bytes:
        return []

    samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
    sample_rate = 16000
    samples_per_frame = int(sample_rate / fps)

    if samples_per_frame == 0:
        return []

    total_frames = len(samples) // samples_per_frame
    if total_frames == 0:
        return []

    # Compute RMS per frame
    # Trim samples to exact multiple of samples_per_frame
    trimmed = samples[:total_frames * samples_per_frame]
    frames = trimmed.reshape(total_frames, samples_per_frame)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))

    # Normalize
    max_rms = rms.max()
    if max_rms > 0:
        rms_norm = rms / max_rms
    else:
        return [False] * total_frames

    # Threshold
    talking = (rms_norm > RMS_THRESHOLD).tolist()

    # Smooth: remove isolated flips shorter than N frames
    talking = _smooth(talking, RMS_SMOOTHING_FRAMES)

    return talking


def _smooth(frames: list[bool], min_run: int) -> list[bool]:
    """Remove runs shorter than min_run frames (flip them to match neighbors)."""
    if len(frames) < 3 or min_run < 1:
        return frames

    result = frames.copy()
    i = 0
    while i < len(result):
        # Find end of current run
        j = i + 1
        while j < len(result) and result[j] == result[i]:
            j += 1
        run_len = j - i
        if run_len < min_run and i > 0:
            # Flip this short run to match previous state
            for k in range(i, j):
                result[k] = result[i - 1]
        i = j

    return result
