"""Piper TTS provider — local text-to-speech via subprocess."""

import asyncio
import os
import time

from core.config import PIPER_BIN, MODELS_DIR, BREAKS_DIR


async def synthesize(
    text: str,
    model_name: str,
    output_id: str,
) -> str | None:
    """
    Synthesize text to normalized MP3 using Piper + FFmpeg loudnorm.

    Args:
        text: The script to speak
        model_name: e.g. "en_US-lessac-high"
        output_id: unique ID for the output file

    Returns:
        Path to the normalized MP3 file, or None on failure.
    """
    model_path = os.path.join(str(MODELS_DIR), f"{model_name}.onnx")
    if not os.path.exists(model_path):
        print(f"[tts] Model not found: {model_path}")
        return None

    os.makedirs(str(BREAKS_DIR), exist_ok=True)
    wav_path = os.path.join(str(BREAKS_DIR), f"{output_id}.wav")
    mp3_path = os.path.join(str(BREAKS_DIR), f"{output_id}.mp3")

    try:
        t0 = time.time()

        # Step 1: Piper → WAV
        proc = await asyncio.create_subprocess_exec(
            PIPER_BIN,
            "--model", model_path,
            "--output_file", wav_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(
            proc.communicate(input=text.encode("utf-8")),
            timeout=60.0,
        )

        if proc.returncode != 0:
            print(f"[tts] Piper failed: {stderr.decode()}")
            return None

        if not os.path.exists(wav_path):
            print("[tts] WAV file not created")
            return None

        # Step 2: FFmpeg loudnorm → MP3
        proc2 = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y",
            "-i", wav_path,
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "44100", "-ac", "2",
            "-c:a", "libmp3lame", "-b:a", "192k",
            mp3_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr2 = await asyncio.wait_for(
            proc2.communicate(),
            timeout=30.0,
        )

        if proc2.returncode != 0:
            print(f"[tts] FFmpeg normalize failed: {stderr2.decode()}")
            return None

        elapsed = time.time() - t0
        print(f"[tts] Generated {output_id} in {elapsed:.1f}s")

        # Clean up WAV
        try:
            os.remove(wav_path)
        except OSError:
            pass

        return mp3_path

    except asyncio.TimeoutError:
        print(f"[tts] Timeout generating {output_id}")
        _cleanup_temp(wav_path)
        return None
    except Exception as e:
        print(f"[tts] Error: {e}")
        _cleanup_temp(wav_path)
        return None


def _cleanup_temp(*paths):
    """Remove temp files on failure."""
    for p in paths:
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass
