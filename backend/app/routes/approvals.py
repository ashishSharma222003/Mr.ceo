from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..db import get_session
from ..models import Approval
from ..schemas import ApprovalResolve, ChatResponse
from ..services import manager, todos

router = APIRouter(tags=["approvals"])


@router.get("/threads/{thread_id}/approvals", response_model=list[Approval])
async def list_approvals(thread_id: str, session: AsyncSession = Depends(get_session)):
    q = select(Approval).where(Approval.thread_id == thread_id).order_by(Approval.id)
    return (await session.exec(q)).all()


@router.post("/approvals/{approval_id}/resolve", response_model=ChatResponse)
async def resolve(approval_id: int, body: ApprovalResolve, session: AsyncSession = Depends(get_session)):
    """Answer a paused Manager: one decision (approve | edit | reject) per listed tool call, in order."""
    approval = await session.get(Approval, approval_id)
    if not approval:
        raise HTTPException(404, "Approval not found")
    if approval.status != "pending":
        raise HTTPException(409, "Already answered")
    if len(body.decisions) != len(approval.actions):
        raise HTTPException(422, f"Expected {len(approval.actions)} decision(s)")

    decisions = []
    for action, d in zip(approval.actions, body.decisions):
        if d.type == "approve":
            decisions.append({"type": "approve"})
        elif d.type == "edit":
            if d.edited_args is None:
                raise HTTPException(422, "edit needs edited_args")
            decisions.append({"type": "edit", "edited_action": {"name": action["name"], "args": d.edited_args}})
        else:
            decisions.append({"type": "reject", "message": d.message or "The user rejected this change."})

    try:
        reply, tasks = await manager.resolve_approval(session, approval, decisions)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"LLM call failed: {type(e).__name__}: {e}") from e
    return ChatResponse(
        thread_id=approval.thread_id, reply=reply, tasks=tasks,
        todos=await todos.list_todos(session, approval.thread_id),
    )
