"""Event log feeding the SSE endpoint.

Every event is saved to the DB first (its row id is the "save point"), then pushed to live
subscribers. A client that reconnects with Last-Event-ID is replayed what it missed, so
nothing is lost across a server restart or a dropped connection. Swap the live fan-out for
Redis if we ever run several instances; the table stays.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

from sqlmodel import delete, select

from ..db import SessionLocal
from ..models import Event

RETENTION = timedelta(days=7)

_subscribers: set[asyncio.Queue] = set()


def _to_sse(row: Event) -> dict:
    return {"id": str(row.id), "event": row.type, "data": json.dumps(row.payload, default=str)}


async def publish(event: str, data: dict, persist: bool = True) -> None:
    """persist=False: live subscribers only (no DB row, no id, not replayed). For token streams."""
    if persist:
        # Own session: logging an event must not touch the caller's transaction.
        async with SessionLocal() as session:
            row = Event(type=event, payload=json.loads(json.dumps(data, default=str)))
            session.add(row)
            await session.commit()
            await session.refresh(row)
        payload = _to_sse(row)
    else:
        payload = {"event": event, "data": json.dumps(data, default=str)}
    for q in _subscribers:
        q.put_nowait(payload)


async def subscribe(last_event_id: int | None = None):
    # Register before replaying so nothing published in between is missed.
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.add(q)
    try:
        seen = last_event_id or 0
        if last_event_id is not None:
            async with SessionLocal() as session:
                missed = (
                    await session.exec(select(Event).where(Event.id > seen).order_by(Event.id))
                ).all()
            for row in missed:
                seen = row.id
                yield _to_sse(row)
        while True:
            payload = await q.get()
            if "id" not in payload:  # live-only event
                yield payload
            elif int(payload["id"]) > seen:  # skip what the replay already sent
                seen = int(payload["id"])
                yield payload
    finally:
        _subscribers.discard(q)


async def prune() -> None:
    cutoff = datetime.now(timezone.utc) - RETENTION
    async with SessionLocal() as session:
        await session.exec(delete(Event).where(Event.created_at < cutoff))
        await session.commit()
