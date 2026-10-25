import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..db import get_session
from ..models import ChatMessage
from ..schemas import ChatRequest, ChatResponse, ThreadSummary
from ..services import manager, todos

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, session: AsyncSession = Depends(get_session)):
    thread_id = body.thread_id or uuid.uuid4().hex
    if await manager.pending_approval(session, thread_id):
        raise HTTPException(409, "The Manager is waiting for your approval. Answer it first.")
    try:
        reply, tasks = await manager.handle_message(session, body.message, thread_id, body.todo_id)
    except Exception as e:  # noqa: BLE001 - LLM down, bad key, model not pulled, ...
        raise HTTPException(502, f"LLM call failed: {type(e).__name__}: {e}") from e
    return ChatResponse(
        thread_id=thread_id, reply=reply, tasks=tasks, todos=await todos.list_todos(session, thread_id)
    )


@router.get("/chat/{thread_id}/messages", response_model=list[ChatMessage])
async def history(thread_id: str, session: AsyncSession = Depends(get_session)):
    q = select(ChatMessage).where(ChatMessage.thread_id == thread_id).order_by(ChatMessage.id)
    return (await session.exec(q)).all()


@router.get("/threads", response_model=list[ThreadSummary])
async def list_threads(session: AsyncSession = Depends(get_session)):
    """Manager conversations, most recently active first."""
    base = ChatMessage.agent_id.is_(None)  # sub-agent messages share the thread id; don't count them
    rows = (
        await session.exec(
            select(ChatMessage.thread_id, func.count(), func.max(ChatMessage.created_at))
            .where(base)
            .group_by(ChatMessage.thread_id)
            .order_by(func.max(ChatMessage.id).desc())
        )
    ).all()
    firsts: dict[str, str] = {}
    if rows:
        q = (
            select(ChatMessage)
            .where(ChatMessage.role == "user", base, ChatMessage.thread_id.in_([r[0] for r in rows]))
            .order_by(ChatMessage.id)
        )
        for m in (await session.exec(q)).all():
            firsts.setdefault(m.thread_id, m.content)
    return [
        ThreadSummary(
            thread_id=tid,
            title=" ".join((firsts.get(tid) or "New conversation").split())[:60],
            message_count=n,
            updated_at=at,
        )
        for tid, n, at in rows
    ]
