"""TTS router — dispatches synthesis to the right provider per host."""

from core.database import get_db
from core.providers import tts_piper, tts_elevenlabs, tts_openai


async def _get_setting(key: str) -> str:
    db = await get_db()
    cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = await cursor.fetchone()
    return row["value"] if row else ""


async def synthesize(text: str, host: dict, output_id: str) -> str | None:
    """
    Route TTS synthesis to the provider configured for this host.

    Args:
        text: The script to speak
        host: Full host dict from DB (must have tts_provider, tts_voice_id, piper_model)
        output_id: unique ID for the output file

    Returns:
        Path to the normalized MP3 file, or None on failure.
    """
    provider = host.get("tts_provider") or "piper"
    voice_id = host.get("tts_voice_id") or host.get("piper_model", "")

    print(f"[tts] Using provider={provider} voice={voice_id} for host={host.get('label', '?')}")

    if provider == "elevenlabs":
        api_key = await _get_setting("elevenlabs_api_key")
        if not api_key:
            print("[tts] ElevenLabs API key not set, falling back to piper")
            return await tts_piper.synthesize(text, host.get("piper_model", ""), output_id)
        return await tts_elevenlabs.synthesize(text, voice_id, output_id, api_key)

    elif provider == "openai":
        model = await _get_setting("openai_tts_model") or "tts-1"
        return await tts_openai.synthesize(text, voice_id, output_id, model)

    else:
        # Default: piper — use piper_model as the model name
        model_name = voice_id or host.get("piper_model", "")
        return await tts_piper.synthesize(text, model_name, output_id)
