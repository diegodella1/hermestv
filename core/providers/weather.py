"""Weather provider — WeatherAPI.com with SQLite cache."""

import json
import time
from datetime import datetime, timezone

import httpx

from core.config import WEATHER_API_KEY
from core.database import get_db

CACHE_TTL_SECONDS = 600  # 10 minutes
API_BASE = "https://api.weatherapi.com/v1/current.json"


async def get_weather_for_cities() -> list[dict]:
    """Fetch weather for all enabled cities (in parallel), using cache when fresh."""
    import asyncio

    db = await get_db()
    cursor = await db.execute(
        "SELECT id, label, lat, lon, units FROM cities WHERE enabled = 1 ORDER BY priority"
    )
    cities = await cursor.fetchall()

    fetched = await asyncio.gather(
        *[_get_cached_or_fetch(dict(city)) for city in cities],
        return_exceptions=True,
    )
    return [data for data in fetched if isinstance(data, dict)]


async def _get_cached_or_fetch(city: dict) -> dict | None:
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()

    cursor = await db.execute(
        "SELECT payload_json, expires_at FROM cache_weather WHERE city_id = ?",
        (city["id"],),
    )
    row = await cursor.fetchone()

    if row and row["expires_at"] > now:
        payload = json.loads(row["payload_json"])
        payload["city_label"] = city["label"]
        return payload

    # Fetch fresh
    fresh = await _fetch_weather(city)
    if fresh:
        expires = datetime.fromtimestamp(
            time.time() + CACHE_TTL_SECONDS, tz=timezone.utc
        ).isoformat()
        await db.execute(
            """INSERT OR REPLACE INTO cache_weather (city_id, payload_json, fetched_at, expires_at)
               VALUES (?, ?, ?, ?)""",
            (city["id"], json.dumps(fresh), now, expires),
        )
        await db.commit()
        fresh["city_label"] = city["label"]
        return fresh

    # Return stale cache if fetch failed
    if row:
        payload = json.loads(row["payload_json"])
        payload["city_label"] = city["label"]
        payload["stale"] = True
        return payload

    return None


async def _fetch_weather(city: dict) -> dict | None:
    if not WEATHER_API_KEY:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                API_BASE,
                params={
                    "key": WEATHER_API_KEY,
                    "q": f"{city['lat']},{city['lon']}",
                    "aqi": "no",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        current = data.get("current", {})
        is_imperial = city.get("units", "metric") == "imperial"

        return {
            "city_id": city["id"],
            "temp": current.get("temp_f" if is_imperial else "temp_c"),
            "feelslike": current.get("feelslike_f" if is_imperial else "feelslike_c"),
            "condition": current.get("condition", {}).get("text", ""),
            "wind": current.get("wind_mph" if is_imperial else "wind_kph"),
            "humidity": current.get("humidity"),
            "units": "F" if is_imperial else "C",
            "wind_units": "mph" if is_imperial else "kph",
        }
    except Exception as e:
        print(f"[weather] Error fetching {city['label']}: {e}")
        return None
