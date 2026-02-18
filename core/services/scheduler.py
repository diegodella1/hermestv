"""Break scheduler — triggers break generation on a configurable interval."""

import asyncio
from datetime import datetime, timezone

from core.database import get_db


class BreakScheduler:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._prepare_break_fn = None
        self._last_trigger: datetime | None = None
        self._next_trigger: datetime | None = None

    def set_prepare_break_fn(self, fn):
        self._prepare_break_fn = fn

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def last_trigger(self) -> datetime | None:
        return self._last_trigger

    @property
    def next_trigger(self) -> datetime | None:
        return self._next_trigger

    async def _get_interval_minutes(self) -> int:
        try:
            db = await get_db()
            cursor = await db.execute(
                "SELECT value FROM settings WHERE key = 'break_interval_minutes'"
            )
            row = await cursor.fetchone()
            if row:
                return max(1, int(row["value"]))
        except Exception:
            pass
        return 15

    async def _is_quiet_mode(self) -> bool:
        try:
            db = await get_db()
            cursor = await db.execute(
                "SELECT value FROM settings WHERE key = 'quiet_mode'"
            )
            row = await cursor.fetchone()
            return row["value"] == "true" if row else False
        except Exception:
            return False

    async def _loop(self):
        print("[scheduler] Started")
        first_run = True
        while self._running:
            try:
                interval = await self._get_interval_minutes()

                if first_run:
                    # Fire immediately on start, don't wait
                    first_run = False
                    print("[scheduler] First run — triggering immediately")
                else:
                    self._next_trigger = datetime.now(timezone.utc)
                    await asyncio.sleep(interval * 60)

                if not self._running:
                    break

                # Check quiet mode
                if await self._is_quiet_mode():
                    print("[scheduler] Quiet mode active, skipping break")
                    continue

                # Trigger break generation
                if self._prepare_break_fn:
                    self._last_trigger = datetime.now(timezone.utc)
                    print("[scheduler] Triggering break generation")
                    asyncio.create_task(self._prepare_break_fn())
                else:
                    print("[scheduler] No prepare_break function set")

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[scheduler] Error: {e}")
                await asyncio.sleep(30)

        print("[scheduler] Stopped")

    def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def status(self) -> dict:
        return {
            "running": self._running,
            "last_trigger": self._last_trigger.isoformat() if self._last_trigger else None,
            "next_trigger": self._next_trigger.isoformat() if self._next_trigger else None,
        }


# Singleton
scheduler = BreakScheduler()
