"""Host rotation — alternates between hosts for breaks."""

from core.database import get_db


async def get_next_host(is_breaking: bool = False) -> dict | None:
    """
    Get the next host for a break.
    - Breaking: always the designated breaking host
    - Regular: alternate (odd breaks → host_b, even → host_a)
    """
    db = await get_db()

    if is_breaking:
        cursor = await db.execute(
            "SELECT * FROM hosts WHERE is_breaking_host = 1 AND enabled = 1 LIMIT 1"
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    # Get rotation state
    cursor = await db.execute("SELECT * FROM host_rotation WHERE id = 1")
    rotation = await cursor.fetchone()
    break_count = (rotation["break_count"] if rotation else 0) + 1

    # Odd → host_b, Even → host_a
    next_id = "host_b" if break_count % 2 == 1 else "host_a"

    cursor = await db.execute(
        "SELECT * FROM hosts WHERE id = ? AND enabled = 1", (next_id,)
    )
    host = await cursor.fetchone()

    if not host:
        # Fallback to any enabled host
        cursor = await db.execute(
            "SELECT * FROM hosts WHERE enabled = 1 LIMIT 1"
        )
        host = await cursor.fetchone()

    if host:
        # Update rotation
        await db.execute(
            "UPDATE host_rotation SET last_host_id = ?, break_count = ? WHERE id = 1",
            (host["id"], break_count),
        )
        await db.commit()

    return dict(host) if host else None
