from __future__ import annotations

import anyio


async def to_thread(fn, *a, **kw):
    return await anyio.to_thread.run_sync(lambda: fn(*a, **kw))
