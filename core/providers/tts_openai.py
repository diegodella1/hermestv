"""OpenAI TTS provider — cloud text-to-speech via OpenAI SDK."""

import asyncio
import os
import time

from core.config import BREAKS_DIR, OPENAI_API_KEY


async def synthesize(
    text: str,
    voice: str,
    output_id: str,
    model: str = "tts-1",
) -> str | None:
    """
    Synthesize text to normalized MP3 using OpenAI TTS + FFmpeg loudnorm.

    Args:
        text: The script to speak
        voice: OpenAI voice name (alloy, echo, fable, onyx, nova, shimmer)
        output_id: unique ID for the output file
        model: OpenAI TTS model (tts-1 or tts-1-hd)

    Returns:
        Path to the normalized MP3 file, or None on failure.
    """
    if not OPENAI_API_KEY:
        print("[tts:openai] No OPENAI_API_KEY configured")
        return None

    if not voice:
        voice = "nova"

    if model not in ("tts-1", "tts-1-hd"):
        model = "tts-1"

    os.makedirs(str(BREAKS_DIR), exist_ok=True)
    raw_path = os.path.join(str(BREAKS_DIR), f"{output_id}_raw.mp3")
    mp3_path = os.path.join(str(BREAKS_DIR), f"{output_id}.mp3")

    try:
        t0 = time.time()

        # Step 1: OpenAI TTS → raw MP3
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)

        response = await asyncio.wait_for(
            client.audio.speech.create(
                model=model,
                voice=voice,
                input=text,
                response_format="mp3",
            ),
            timeout=30.0,
        )

        with open(raw_path, "wb") as f:
            f.write(response.content)

        # Step 2: FFmpeg loudnorm → normalized MP3
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y",
            "-i", raw_path,
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "44100", "-ac", "2",
            "-c:a", "libmp3lame", "-b:a", "192k",
            mp3_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)

        if proc.returncode != 0:
            print(f"[tts:openai] FFmpeg normalize failed: {stderr.decode()}")
            return None

        elapsed = time.time() - t0
        print(f"[tts:openai] Generated {output_id} in {elapsed:.1f}s")

        # Clean up raw file
        try:
            os.remove(raw_path)
        except OSError:
            pass

        return mp3_path

    except asyncio.TimeoutError:
        print(f"[tts:openai] Timeout generating {output_id}")
        return None
    except Exception as e:
        print(f"[tts:openai] Error: {e}")
        return None
