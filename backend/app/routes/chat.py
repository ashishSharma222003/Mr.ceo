import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import delete, func, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..db import get_session
from ..models import Agent, Approval, ChatMessage, Task, TaskStatus, Thread, Todo, TodoStatus
from ..schemas import ChatRequest, ChatResponse, ThreadCreate, ThreadOut
from ..services import manager, threads, todos
from ..services.memory import get_checkpointer

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


@router.get("/threads", response_model=list[ThreadOut])
async def list_threads(session: AsyncSession = Depends(get_session)):
    """Manager conversations, most recently active first, with how many tasks are still open."""
    q = select(Todo.thread_id, func.count()).where(Todo.status != TodoStatus.done).group_by(Todo.thread_id)
    open_tasks = dict((await session.exec(q)).all())
    rows = (await session.exec(select(Thread).order_by(Thread.updated_at.desc()))).all()
    return [ThreadOut(**t.model_dump(), open_tasks=open_tasks.get(t.id, 0)) for t in rows]


@router.post("/threads", response_model=ThreadOut, status_code=201)
async def create_thread(body: ThreadCreate, session: AsyncSession = Depends(get_session)):
    """Start a new chat, either with the shared sub-agents or with an empty team of its own."""
    return await threads.create(session, body.team)


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(thread_id: str, session: AsyncSession = Depends(get_session)):
    """Delete a chat with its tasks, messages and the sub-agents that belong only to it."""
    thread = await session.get(Thread, thread_id)
    if not thread:
        raise HTTPException(404, "Chat not found")
    busy = select(Task).where(Task.thread_id == thread_id, Task.status.in_([TaskStatus.pending, TaskStatus.running]))
    if (await session.exec(busy)).first():
        raise HTTPException(409, "Sub-agents are still working in this chat. Try again when they finish.")
    own = select(Agent.id).where(Agent.thread_id == thread_id)
    for model in (ChatMessage, Todo, Approval):
        await session.exec(delete(model).where(model.thread_id == thread_id))
    await session.exec(delete(Task).where(or_(Task.thread_id == thread_id, Task.agent_id.in_(own))))
    await session.exec(delete(Agent).where(Agent.thread_id == thread_id))
    await session.delete(thread)
    await session.commit()
    await get_checkpointer().adelete_thread(thread_id)
