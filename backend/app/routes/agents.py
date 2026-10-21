from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import delete, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from ..config import settings
from ..db import get_session
from ..models import Agent, Task, Todo
from ..schemas import AgentCreate, AgentUpdate
from ..services.skills import unknown_skills

router = APIRouter(prefix="/agents", tags=["agents"])


async def _check_skills(session: AsyncSession, names: list[str]) -> None:
    if bad := await unknown_skills(session, names):
        raise HTTPException(422, f"Unknown skills: {bad}. See GET /api/skills")


@router.get("", response_model=list[Agent])
async def list_agents(session: AsyncSession = Depends(get_session)):
    return (await session.exec(select(Agent))).all()


@router.post("", response_model=Agent, status_code=201)
async def create_agent(body: AgentCreate, session: AsyncSession = Depends(get_session)):
    await _check_skills(session, body.skills)
    data = body.model_dump()
    data["model"] = data["model"] or settings.resolved_agent_model
    agent = Agent(**data)
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=Agent)
async def get_agent(agent_id: int, session: AsyncSession = Depends(get_session)):
    agent = await session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=Agent)
async def update_agent(
    agent_id: int, body: AgentUpdate, session: AsyncSession = Depends(get_session)
):
    agent = await session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    if body.skills is not None:
        await _check_skills(session, body.skills)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(agent, key, value)
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: int, session: AsyncSession = Depends(get_session)):
    agent = await session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    # Remove the agent's tasks too so nothing is left pointing at a missing agent.
    task_ids = select(Task.id).where(Task.agent_id == agent_id)
    await session.exec(update(Todo).where(Todo.task_id.in_(task_ids)).values(task_id=None))
    await session.exec(delete(Task).where(Task.agent_id == agent_id))
    await session.delete(agent)
    await session.commit()
