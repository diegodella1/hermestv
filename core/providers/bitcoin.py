"""Bitcoin market data provider — Roxom API with SQLite cache."""

import json
import time
from datetime import datetime, timezone

import httpx

from core.database import get_db

API_URL = "https://rtvapi.roxom.com/btc/info"


async def get_bitcoin_data() -> dict | None:
    """Fetch Bitcoin market data if enabled, using cache when fresh."""
    db = await get_db()

    # Check settings
    cursor = await db.execute(
        "SELECT key, value FROM settings WHERE key IN "
        "('bitcoin_enabled', 'bitcoin_api_key', 'bitcoin_cache_ttl')"
    )
    settings = {r["key"]: r["value"] for r in await cursor.fetchall()}

    if settings.get("bitcoin_enabled") != "true":
        return None

    api_key = settings.get("bitcoin_api_key", "")
    if not api_key:
        return None

    cache_ttl = int(settings.get("bitcoin_cache_ttl", "300"))
    now = datetime.now(timezone.utc).isoformat()

    # Check cache
    cursor = await db.execute(
        "SELECT payload_json, expires_at FROM cache_bitcoin WHERE id = 'btc'"
    )
    row = await cursor.fetchone()

    if row and row["expires_at"] > now:
        return json.loads(row["payload_json"])

    # Fetch fresh
    fresh = await _fetch_bitcoin(api_key)
    if fresh:
        expires = datetime.fromtimestamp(
            time.time() + cache_ttl, tz=timezone.utc
        ).isoformat()
        await db.execute(
            """INSERT OR REPLACE INTO cache_bitcoin (id, payload_json, fetched_at, expires_at)
               VALUES ('btc', ?, ?, ?)""",
            (json.dumps(fresh), now, expires),
        )
        await db.commit()
        return fresh

    # Return stale cache if fetch failed
    if row:
        payload = json.loads(row["payload_json"])
        payload["stale"] = True
        return payload

    return None


async def _fetch_bitcoin(api_key: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(API_URL, params={"apiKey": api_key})
            resp.raise_for_status()
            data = resp.json()

        return _extract(data)
    except Exception as e:
        print(f"[bitcoin] Error fetching: {e}")
        return None


def _extract(data: dict) -> dict:
    """Extract the 4 relevant sections from the API response."""
    result = {}

    # Price
    price = data.get("price", {})
    result["price"] = {
        "live_price": price.get("live_price"),
        "change_24h": price.get("change_24h"),
        "change_pct_24h": price.get("change_percentage_24h"),
        "market_cap": price.get("market_cap"),
        "sats_per_dollar": price.get("sats_per_dollar"),
    }

    # ETF trading
    etf = data.get("etf_trading_24h", {})
    result["etf"] = {
        "spot_volume": etf.get("spot_volume"),
        "total_aum": etf.get("total_aum"),
        "btc_holdings": etf.get("btc_holdings"),
    }

    # Corporate treasuries
    corp = data.get("corporate_treasuries", {})
    result["corporate"] = {
        "total_btc": corp.get("total_btc"),
        "total_value": corp.get("total_value"),
        "public_companies": corp.get("public_companies"),
        "private_companies": corp.get("private_companies"),
    }

    # Government treasuries
    gov = data.get("government_treasuries", {})
    result["government"] = {
        "total_countries": gov.get("total_countries"),
        "total_btc": gov.get("total_btc"),
        "total_value": gov.get("total_value"),
    }

    return result
