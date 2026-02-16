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
            dedupe_window = int(settings.get("news_dedupe_window_minutes", "60"))
            headlines = await news.get_top_headlines(
                limit=3,
                dedupe_window_minutes=dedupe_window,
                exclude_ids=recently_used_ids or None,
            )
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
        s_max_c = int(settings.get("break_max_chars", "600"))

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

        # 6. TTS
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
