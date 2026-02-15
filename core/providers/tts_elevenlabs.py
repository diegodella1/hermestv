"""ElevenLabs TTS provider — cloud text-to-speech via REST API."""

import asyncio
import os
import time

import httpx

from core.config import BREAKS_DIR


async def synthesize(
    text: str,
    voice_id: str,
    output_id: str,
    api_key: str,
) -> str | None:
    """
    Synthesize text to normalized MP3 using ElevenLabs API + FFmpeg loudnorm.

    Args:
        text: The script to speak
        voice_id: ElevenLabs voice ID
        output_id: unique ID for the output file
        api_key: ElevenLabs API key

    Returns:
        Path to the normalized MP3 file, or None on failure.
    """
    if not api_key:
        print("[tts:elevenlabs] No API key configured")
        return None

    if not voice_id:
        print("[tts:elevenlabs] No voice_id configured")
        return None

    os.makedirs(str(BREAKS_DIR), exist_ok=True)
    raw_path = os.path.join(str(BREAKS_DIR), f"{output_id}_raw.mp3")
    mp3_path = os.path.join(str(BREAKS_DIR), f"{output_id}.mp3")

    try:
        t0 = time.time()

        # Step 1: ElevenLabs API → raw MP3
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code != 200:
            print(f"[tts:elevenlabs] API error {resp.status_code}: {resp.text[:200]}")
            return None

        with open(raw_path, "wb") as f:
            f.write(resp.content)

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
            print(f"[tts:elevenlabs] FFmpeg normalize failed: {stderr.decode()}")
            return None

        elapsed = time.time() - t0
        print(f"[tts:elevenlabs] Generated {output_id} in {elapsed:.1f}s")

        # Clean up raw file
        try:
            os.remove(raw_path)
        except OSError:
            pass

        return mp3_path

    except asyncio.TimeoutError:
        print(f"[tts:elevenlabs] Timeout generating {output_id}")
        return None
    except Exception as e:
        print(f"[tts:elevenlabs] Error: {e}")
        return None
