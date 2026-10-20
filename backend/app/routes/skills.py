from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..db import get_session
from ..models import Agent, Skill
from ..schemas import SkillCreate, SkillUpdate
from ..services.skills import validate_skill
from ..tools import BUILTIN_TOOLS

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=list[Skill])
async def list_skills(session: AsyncSession = Depends(get_session)):
    return (await session.exec(select(Skill).order_by(Skill.id))).all()


@router.get("/builtin-tools")
async def list_builtin_tools():
    """Python tools that a `builtin` skill can point at via `tool_key`."""
    return [{"tool_key": k, "description": t.description} for k, t in BUILTIN_TOOLS.items()]


@router.post("", response_model=Skill, status_code=201)
async def create_skill(body: SkillCreate, session: AsyncSession = Depends(get_session)):
    skill = Skill(**body.model_dump())
    if err := validate_skill(skill):
        raise HTTPException(422, err)
    session.add(skill)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, f"Skill {skill.name!r} already exists")
    await session.refresh(skill)
    return skill


@router.get("/{skill_id}", response_model=Skill)
async def get_skill(skill_id: int, session: AsyncSession = Depends(get_session)):
    skill = await session.get(Skill, skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    return skill


async def _rewrite_agents(session: AsyncSession, old: str, new: str | None) -> None:
    """Keep agents' skill-name lists consistent after a rename (new=name) or delete (new=None)."""
    for agent in (await session.exec(select(Agent))).all():
        if old in agent.skills:
            agent.skills = [new if n == old else n for n in agent.skills if n != old or new]
            session.add(agent)


@router.patch("/{skill_id}", response_model=Skill)
async def update_skill(
    skill_id: int, body: SkillUpdate, session: AsyncSession = Depends(get_session)
):
    skill = await session.get(Skill, skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    old_name = skill.name
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(skill, key, value)
    if err := validate_skill(skill):
        raise HTTPException(422, err)
    if skill.name != old_name:
        await _rewrite_agents(session, old_name, skill.name)
    session.add(skill)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, f"Skill {skill.name!r} already exists")
    await session.refresh(skill)
    return skill


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: int, session: AsyncSession = Depends(get_session)):
    skill = await session.get(Skill, skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    await _rewrite_agents(session, skill.name, None)  # detach from agents
    await session.delete(skill)
    await session.commit()
