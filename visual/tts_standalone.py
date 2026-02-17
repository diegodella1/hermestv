"""Standalone TTS wrapper — synchronous interface over core TTS providers."""

import asyncio
import os
import uuid

from visual.ffmpeg_utils import probe_duration_ms


def synthesize_line(
    text: str,
    character: str,
    output_dir: str,
    provider: str = "piper",
    voice: str = "",
    model: str = "",
) -> tuple[str, int]:
    """Synthesize a single dialog line to audio.

    Args:
        text: Text to speak
        character: Character ID (used in filename)
        output_dir: Directory for audio files
        provider: "piper" or "openai"
        voice: Voice name/ID
        model: Piper model name or OpenAI model

    Returns:
        (audio_path, duration_ms)
    """
    os.makedirs(output_dir, exist_ok=True)
    output_id = f"{character}_{uuid.uuid4().hex[:8]}"

    loop = asyncio.new_event_loop()
    try:
        audio_path = loop.run_until_complete(
            _synthesize_async(text, output_id, provider, voice, model)
        )
    finally:
        loop.close()

    if not audio_path or not os.path.exists(audio_path):
        raise RuntimeError(f"TTS failed for: {text[:50]}")

    duration = probe_duration_ms(audio_path)
    print(f"[tts] {character}: {duration}ms — {text[:40]}...")
    return audio_path, duration


async def _synthesize_async(
    text: str,
    output_id: str,
    provider: str,
    voice: str,
    model: str,
) -> str | None:
    """Dispatch to the appropriate TTS provider."""
    if provider == "openai":
        from core.providers.tts_openai import synthesize
        return await synthesize(text, voice or "nova", output_id, model or "tts-1")
    else:
        from core.providers.tts_piper import synthesize
        model_name = model or "en_US-lessac-high"
        return await synthesize(text, model_name, output_id)
