"""Tiny in-memory pub/sub feeding the SSE endpoint. Swap for Redis later."""
import asyncio
import json

_subscribers: set[asyncio.Queue] = set()


def publish(event: str, data: dict) -> None:
    payload = {"event": event, "data": json.dumps(data, default=str)}
    for q in _subscribers:
        q.put_nowait(payload)


async def subscribe():
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.add(q)
    try:
        while True:
            yield await q.get()
    finally:
        _subscribers.discard(q)
