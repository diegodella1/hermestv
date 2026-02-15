"""News provider — RSS fetch via feedparser with cache + dedup + health tracking."""

import hashlib
import json
import re
import time
from datetime import datetime, timezone

import feedparser
import httpx

from core.database import get_db

# Strip HTML tags and control chars for LLM safety
_TAG_RE = re.compile(r"<[^>]+>")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize(text: str, max_len: int = 200) -> str:
    text = _TAG_RE.sub("", text)
    text = _CTRL_RE.sub("", text)
    return text.strip()[:max_len]


def _title_hash(title: str) -> str:
    return hashlib.sha256(title.lower().strip().encode()).hexdigest()[:16]


async def fetch_all_feeds() -> list[dict]:
    """Fetch headlines from all enabled + healthy feeds."""
    db = await get_db()
    cursor = await db.execute(
        """SELECT ns.id, ns.label, ns.url, ns.category, ns.weight
           FROM news_sources ns
           JOIN feed_health fh ON fh.source_id = ns.id
           WHERE ns.enabled = 1 AND fh.status != 'dead'
           ORDER BY ns.weight DESC"""
    )
    sources = [dict(r) for r in await cursor.fetchall()]

    all_headlines = []
    for source in sources:
        headlines = await _fetch_feed(source)
        all_headlines.extend(headlines)

    return all_headlines


async def _fetch_feed(source: dict) -> list[dict]:
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(source["url"])
            resp.raise_for_status()
            content = resp.text

        feed = feedparser.parse(content)
        entries = feed.entries[:20]  # limit per feed

        headlines = []
        for entry in entries:
            title = _sanitize(entry.get("title", ""), 200)
            if not title:
                continue

            th = _title_hash(title)
            news_id = f"{source['id']}_{th}"

            # Dedup check
            cursor = await db.execute(
                "SELECT id FROM cache_news WHERE id = ?", (news_id,)
            )
            if await cursor.fetchone():
                continue

            desc = _sanitize(entry.get("summary", entry.get("description", "")), 300)
            pub = entry.get("published_parsed")
            pub_dt = (
                datetime(*pub[:6], tzinfo=timezone.utc).isoformat()
                if pub
                else now
            )

            await db.execute(
                """INSERT OR IGNORE INTO cache_news
                   (id, source_id, title, description, url, published_at, fetched_at, title_hash, category)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    news_id,
                    source["id"],
                    title,
                    desc,
                    entry.get("link", ""),
                    pub_dt,
                    now,
                    th,
                    source.get("category", "general"),
                ),
            )

            headlines.append(
                {
                    "id": news_id,
                    "title": title,
                    "description": desc,
                    "source": source["label"],
                    "category": source.get("category", "general"),
                    "published_at": pub_dt,
                }
            )

        await db.commit()

        # Update health: success
        await db.execute(
            """UPDATE feed_health
               SET last_success = ?, consecutive_failures = 0, status = 'healthy'
               WHERE source_id = ?""",
            (now, source["id"]),
        )
        await db.commit()

        return headlines

    except Exception as e:
        print(f"[news] Error fetching {source['label']}: {e}")
        # Update health: failure
        await db.execute(
            """UPDATE feed_health
               SET last_failure = ?, consecutive_failures = consecutive_failures + 1,
                   status = CASE WHEN consecutive_failures + 1 >= 5 THEN 'dead' ELSE 'unhealthy' END
               WHERE source_id = ?""",
            (now, source["id"]),
        )
        await db.commit()
        return []


async def get_recent_unscored(limit: int = 30) -> list[dict]:
    """Get recent unscored headlines for LLM scoring."""
    db = await get_db()
    cursor = await db.execute(
        """SELECT id, title, description, source_id, category, published_at
           FROM cache_news
           WHERE scored = 0
           ORDER BY fetched_at DESC
           LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def mark_scored(news_id: str, score: int, category: str | None = None):
    db = await get_db()
    await db.execute(
        "UPDATE cache_news SET scored = 1, score = ?, category = COALESCE(?, category) WHERE id = ?",
        (score, category, news_id),
    )
    await db.commit()


async def get_top_headlines(
    limit: int = 3,
    dedupe_window_minutes: int = 60,
    exclude_ids: list[str] | None = None,
) -> list[dict]:
    """Get top scored headlines within dedupe window, excluding already-used IDs."""
    db = await get_db()
    time_param = f"-{dedupe_window_minutes} minutes"

    if exclude_ids:
        placeholders = ",".join("?" for _ in exclude_ids)
        cursor = await db.execute(
            f"""SELECT id, title, description, source_id, category, score, published_at
               FROM cache_news
               WHERE scored = 1
                 AND score >= 4
                 AND fetched_at > datetime('now', ?)
                 AND id NOT IN ({placeholders})
               ORDER BY score DESC, fetched_at DESC
               LIMIT ?""",
            (time_param, *exclude_ids, limit),
        )
        rows = [dict(r) for r in await cursor.fetchall()]

        # Fallback: if exclusion left < limit, backfill without exclusion
        if len(rows) < limit:
            cursor = await db.execute(
                """SELECT id, title, description, source_id, category, score, published_at
                   FROM cache_news
                   WHERE scored = 1
                     AND score >= 4
                     AND fetched_at > datetime('now', ?)
                   ORDER BY score DESC, fetched_at DESC
                   LIMIT ?""",
                (time_param, limit),
            )
            all_rows = [dict(r) for r in await cursor.fetchall()]
            # Add any missing ones (preserve order: fresh first, then backfill)
            seen = {r["id"] for r in rows}
            for r in all_rows:
                if r["id"] not in seen and len(rows) < limit:
                    rows.append(r)
                    seen.add(r["id"])
        return rows

    cursor = await db.execute(
        """SELECT id, title, description, source_id, category, score, published_at
           FROM cache_news
           WHERE scored = 1
             AND score >= 4
             AND fetched_at > datetime('now', ?)
           ORDER BY score DESC, fetched_at DESC
           LIMIT ?""",
        (time_param, limit),
    )
    return [dict(r) for r in await cursor.fetchall()]
