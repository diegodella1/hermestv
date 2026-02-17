"""Break builder — orchestrates the full break generation pipeline."""

import json
import time
from datetime import datetime, timezone

from core.database import get_db
from core.providers import weather, news, llm, tts_router, bitcoin
from core.services import (
    break_queue,
    content_filter,
    host_rotation,
    degradation,
    liquidsoap_client,
)


async def prepare_break(is_breaking: bool = False, breaking_note: str = "", recent_tracks: list[dict] | None = None):
    """
    Full break generation pipeline:
    1. Fetch weather
    2. Fetch + score news
    3. Select host
    4. Generate script (LLM)
    5. Validate (content filter)
    6. TTS → MP3
    7. Push to queue
    8. Inject into Liquidsoap
    """
    t0 = time.time()
    now = datetime.now(timezone.utc)
    break_id = f"brk_{now.strftime('%Y%m%d_%H%M%S')}_{now.strftime('%f')[:4]}"
    deg_level = 0

    db = await get_db()

    # Get settings
    settings = {}
    cursor = await db.execute("SELECT key, value FROM settings")
    for row in await cursor.fetchall():
        settings[row["key"]] = row["value"]

    # Check if already preparing
    existing = await break_queue.get_preparing_break()
    if existing and not is_breaking:
        print(f"[builder] Already preparing {existing['id']}, skipping")
        return

    try:
        # Pick host
        host = await host_rotation.get_next_host(is_breaking)
        if not host:
            print("[builder] No host available")
            return

        await break_queue.create_break(
            break_id,
            break_type="breaking" if is_breaking else "scheduled",
            priority=10 if is_breaking else 0,
            host_id=host["id"],
        )

        # 1. Weather + Bitcoin (parallel)
        import asyncio
        weather_result, bitcoin_result = await asyncio.gather(
            weather.get_weather_for_cities(),
            bitcoin.get_bitcoin_data(),
            return_exceptions=True,
        )
        weather_data = weather_result if isinstance(weather_result, list) else []
        bitcoin_data = bitcoin_result if isinstance(bitcoin_result, dict) else None
        if isinstance(weather_result, Exception):
            print(f"[builder] Weather error: {weather_result}")
        if isinstance(bitcoin_result, Exception):
            print(f"[builder] Bitcoin error: {bitcoin_result}")

        # 2. News — fetch, score, select
        headlines = []
        try:
            await news.fetch_all_feeds()
            unscored = await news.get_recent_unscored(limit=20)

            if unscored:
                scores = await llm.score_headlines(
                    [{"title": h["title"], "source": h.get("source_id", "")} for h in unscored]
                )

                for s in scores:
                    idx = s.get("index", -1)
                    if 0 <= idx < len(unscored):
                        await news.mark_scored(
                            unscored[idx]["id"],
                            s.get("score", 0),
                            s.get("category"),
                        )

            recently_used_ids = await break_queue.get_recent_headline_ids(lookback=2)
            # Wider lookback for "previously reported" tagging
            all_used_ids = set(await break_queue.get_recent_headline_ids(lookback=10))
            dedupe_window = int(settings.get("news_dedupe_window_minutes", "60"))
            headlines = await news.get_top_headlines(
                limit=3,
                dedupe_window_minutes=dedupe_window,
                exclude_ids=recently_used_ids or None,
            )
            # Tag headlines the audience already heard
            for h in headlines:
                h["previously_reported"] = h["id"] in all_used_ids
        except Exception as e:
            print(f"[builder] News pipeline error: {e}")

        # 3. Generate script
        master_prompt = settings.get("master_prompt", "You are a radio host.")
        if is_breaking:
            s_min_w = int(settings.get("breaking_min_words", "10"))
            s_max_w = int(settings.get("breaking_max_words", "50"))
        else:
            s_min_w = int(settings.get("break_min_words", "15"))
            s_max_w = int(settings.get("break_max_words", "100"))
            # More room for bitcoin market segment
            if bitcoin_data:
                s_max_w = max(s_max_w, 180)
        s_max_c = int(settings.get("break_max_chars", "1200" if bitcoin_data else "600"))

        script = await llm.generate_break_script(
            weather_data, headlines, host, master_prompt, is_breaking,
            recent_tracks=recent_tracks,
            max_words=s_max_w,
            bitcoin_data=bitcoin_data,
        )

        # 4. Fallback if LLM failed
        if not script:
            print("[builder] LLM failed, trying fallback")
            script, deg_level = await degradation.get_fallback_script(weather_data)

            if script is None and deg_level == 3:
                # Sting-only fallback
                sting_path = degradation.get_sting_path("station_id")
                if sting_path:
                    await break_queue.mark_ready(
                        break_id, "", sting_path, degradation_level=3
                    )
                    await liquidsoap_client.push_break(sting_path)
                    await _log_break(break_id, t0, 3)
                    return

            if script is None:
                # Level 4: skip entirely
                await break_queue.mark_failed(break_id, "all fallbacks exhausted")
                await _log_break(break_id, t0, 4, error="all_fallbacks_failed")
                return

        # 5. Content filter
        valid, reason = content_filter.validate(
            script, is_breaking,
            min_words=s_min_w, max_words=s_max_w, max_chars=s_max_c,
        )
        if not valid:
            print(f"[builder] Content filter rejected: {reason}")
            # Try fallback
            script, deg_level = await degradation.get_fallback_script(weather_data)
            if script is None:
                await break_queue.mark_failed(break_id, f"filter: {reason}")
                await _log_break(break_id, t0, deg_level, error=reason)
                return

        # 6. TTS + optional dialog mode
        dialog_mode = settings.get("dialog_mode", "monologue")
        audio_path = None
        dialog_script = None

        if dialog_mode == "dialog" and not is_breaking:
            # Dialog mode: generate multi-character script, synthesize per-line, combine
            dialog_chars = settings.get("dialog_characters", "alex,maya").split(",")
            dialog_script = await llm.generate_dialog_script(
                characters=[c.strip() for c in dialog_chars],
                topic=script,  # use the monologue script as topic context
                bitcoin_data=bitcoin_data,
                headlines=headlines,
            )
            if dialog_script:
                audio_path = await _synthesize_dialog(dialog_script, break_id)

        # Fallback to monologue TTS if dialog failed or not in dialog mode
        if not audio_path:
            audio_path = await tts_router.synthesize(script, host, break_id)

        if not audio_path:
            print("[builder] TTS failed, trying sting fallback")
            sting_path = degradation.get_sting_path("station_id")
            if sting_path:
                await break_queue.mark_ready(
                    break_id, script, sting_path, degradation_level=3
                )
                await liquidsoap_client.push_break(sting_path)
                await _log_break(break_id, t0, 3)
                return
            else:
                await break_queue.mark_failed(break_id, "TTS failed, no sting")
                await _log_break(break_id, t0, 4, error="tts_failed")
                return

        # 6b. Video render (optional, non-blocking)
        video_path = None
        if settings.get("video_enabled") == "true":
            if dialog_script:
                video_path = await _render_dialog_video(dialog_script, break_id)
            else:
                video_path = await _render_video(script, audio_path, host["id"], break_id)

        # 7. Mark ready + inject
        elapsed_ms = int((time.time() - t0) * 1000)
        await break_queue.mark_ready(
            break_id,
            script,
            audio_path,
            degradation_level=deg_level,
            duration_ms=elapsed_ms,
            meta={
                "host": host["id"],
                "headlines": len(headlines),
                "headline_ids": [h["id"] for h in headlines],
                "weather_cities": len(weather_data),
                "bitcoin": bitcoin_data is not None,
                "video_path": video_path,
            },
        )

        # Push to Liquidsoap
        pushed = await liquidsoap_client.push_break(audio_path)
        # Always reset counter to prevent accumulation, even if push failed
        await liquidsoap_client.reset_counter()

        # Mark as PLAYED once pushed (Liquidsoap has no play-complete callback)
        if pushed:
            await break_queue.mark_played(break_id)

        await _log_break(break_id, t0, deg_level)
        print(f"[builder] Break {break_id} {'played' if pushed else 'ready (push failed)'} in {elapsed_ms}ms (deg={deg_level})")

    except Exception as e:
        print(f"[builder] Pipeline error: {e}")
        await break_queue.mark_failed(break_id, str(e))
        await _log_break(break_id, t0, 4, error=str(e))


async def _render_video(
    script_text: str, audio_path: str, host_id: str, break_id: str
) -> str | None:
    """Render video for a break in a thread (FFmpeg is blocking)."""
    try:
        import asyncio
        from functools import partial
        from visual.bridge import render_break_video

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            partial(
                render_break_video,
                script_text=script_text,
                audio_path=audio_path,
                host_id=host_id,
                break_id=break_id,
            ),
        )
        return result
    except Exception as e:
        print(f"[builder] Video render failed (non-fatal): {e}")
        return None


async def _synthesize_dialog(dialog_script: dict, break_id: str) -> str | None:
    """Synthesize TTS for each dialog line and combine into one MP3."""
    try:
        import asyncio
        import tempfile
        from functools import partial
        from visual.bridge import synthesize_dialog
        from visual.ffmpeg_utils import run_ffmpeg

        loop = asyncio.get_running_loop()

        # Create temp dir for per-line audio
        audio_dir = tempfile.mkdtemp(prefix=f"hermes_dialog_{break_id}_")

        # Synthesize each line (blocking Piper calls, run in executor)
        updated = await loop.run_in_executor(
            None, partial(synthesize_dialog, dialog_script, audio_dir)
        )

        # Combine all line audio files into one MP3
        from pathlib import Path
        audio_files = []
        for scene in updated.get("scenes", []):
            for line in scene.get("lines", []):
                if line.get("audio_path"):
                    audio_files.append(line["audio_path"])

        if not audio_files:
            return None

        combined_path = str(Path(audio_dir) / f"{break_id}_combined.mp3")
        concat_file = Path(audio_dir) / "concat.txt"
        concat_file.write_text("\n".join(f"file '{f}'" for f in audio_files))

        run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c", "copy",
            str(combined_path),
        ], desc=f"combine dialog audio ({len(audio_files)} files)")

        return combined_path
    except Exception as e:
        print(f"[builder] Dialog TTS failed (non-fatal): {e}")
        return None


async def _render_dialog_video(dialog_script: dict, break_id: str) -> str | None:
    """Render video for a dialog script in a thread."""
    try:
        import asyncio
        from functools import partial
        from visual.bridge import render_dialog_video

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            partial(
                render_dialog_video,
                dialog_script=dialog_script,
                break_id=break_id,
                output_dir="output/",
            ),
        )
        return result
    except Exception as e:
        print(f"[builder] Dialog video render failed (non-fatal): {e}")
        return None


async def _log_break(break_id: str, t0: float, deg_level: int, error: str = ""):
    elapsed_ms = int((time.time() - t0) * 1000)
    db = await get_db()
    event_type = "break_failed" if error else "break_ready"
    payload = {"break_id": break_id, "degradation_level": deg_level}
    if error:
        payload["error"] = error
    await db.execute(
        "INSERT INTO events_log (event_type, payload_json, latency_ms) VALUES (?, ?, ?)",
        (event_type, json.dumps(payload), elapsed_ms),
    )
    await db.commit()
