import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..db import get_session
from ..models import ChatMessage
from ..schemas import ChatRequest, ChatResponse
from ..services import manager, todos

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, session: AsyncSession = Depends(get_session)):
    thread_id = body.thread_id or uuid.uuid4().hex
    try:
        reply, tasks = await manager.handle_message(session, body.message, thread_id)
    except Exception as e:  # noqa: BLE001 - LLM down, bad key, model not pulled, ...
        raise HTTPException(502, f"LLM call failed: {type(e).__name__}: {e}") from e
    return ChatResponse(
        thread_id=thread_id, reply=reply, tasks=tasks, todos=await todos.list_todos(session, thread_id)
    )


@router.get("/chat/{thread_id}/messages", response_model=list[ChatMessage])
async def history(thread_id: str, session: AsyncSession = Depends(get_session)):
    q = select(ChatMessage).where(ChatMessage.thread_id == thread_id).order_by(ChatMessage.id)
    return (await session.exec(q)).all()
