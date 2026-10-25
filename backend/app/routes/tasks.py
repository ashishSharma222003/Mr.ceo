from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sse_starlette.sse import EventSourceResponse

from ..db import get_session
from ..models import Task
from ..services import events

router = APIRouter(tags=["tasks"])


@router.get("/tasks", response_model=list[Task])
async def list_tasks(session: AsyncSession = Depends(get_session)):
    return (await session.exec(select(Task).order_by(Task.id.desc()))).all()


@router.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int, session: AsyncSession = Depends(get_session)):
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.get("/events")
async def stream_events(last_event_id: str | None = Header(default=None)):
    # The browser's EventSource re-sends the last id it saw when it reconnects.
    last = int(last_event_id) if last_event_id and last_event_id.isdigit() else None
    return EventSourceResponse(events.subscribe(last))
