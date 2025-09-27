from __future__ import annotations

import asyncio
import random
import time
from typing import Awaitable, Callable, Optional

from .store import dlq_delete, dlq_fetch


class SyncState:
    def __init__(self) -> None:
        self.running = False
        self.last_started: Optional[float] = None
        self.last_finished: Optional[float] = None
        self.last_error: Optional[str] = None
        self.total_runs = 0
        self.total_errors = 0


state = SyncState()
_lock = asyncio.Lock()


async def run_periodic(
    task: Callable[[], Awaitable[None]],
    interval: int,
    jitter: int,
    backoff_max: int,
) -> None:
    backoff = 1
    while True:
        delay = interval + random.randint(0, max(0, jitter))
        await asyncio.sleep(delay)
        async with _lock:
            if state.running:
                continue
            state.running = True
            state.last_started = time.time()
        try:
            await task()
            state.last_error = None
            state.total_runs += 1
            backoff = 1
        except Exception as exc:  # noqa: BLE001
            state.last_error = str(exc)
            state.total_errors += 1
            await asyncio.sleep(min(backoff, backoff_max))
            backoff = min(backoff * 2, backoff_max)
        finally:
            state.last_finished = time.time()
            state.running = False


async def retry_dlq(task: Callable[[object], Awaitable[None]], interval: int, batch: int):
    while True:
        await asyncio.sleep(interval)
        rows = dlq_fetch(batch)
        if not rows:
            continue
        ok_ids: list[int] = []
        for row in rows:
            try:
                await task(row)
            except Exception:  # noqa: BLE001
                continue
            else:
                if getattr(row, "id", None) is not None:
                    ok_ids.append(row.id)
        if ok_ids:
            dlq_delete(ok_ids)
