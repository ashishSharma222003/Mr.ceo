"""Tools that let the Manager manage sub-agents and skills (tools).

The `GATED` ones change configuration, so the Manager pauses before running them and the user
must approve, edit or reject the call (human-in-the-loop, see manager.py). Read-only ones run freely.
Each tool opens its own DB session, and returns an error string instead of raising so the Manager
can read the problem and fix its call.
"""
from langchain_core.tools import StructuredTool
from sqlmodel import select

from ..config import settings
from ..db import SessionLocal
from ..models import Agent, Skill
from . import events
from .skills import unknown_skills, validate_skill

GATED = ("create_subagent", "update_subagent", "create_skill", "update_skill")


def _describe_agent(a: Agent) -> str:
    return f"#{a.id} '{a.name}' (model {a.model}; skills: {', '.join(a.skills) or 'none'}): {a.role_prompt}"


async def list_agents_text() -> str:
    async with SessionLocal() as s:
        agents = (await s.exec(select(Agent))).all()
    return "\n".join(_describe_agent(a) for a in agents) or "(none)"


def build_agent_tools() -> list[StructuredTool]:
    async def list_agents() -> str:
        return await list_agents_text()

    async def list_skills() -> str:
        async with SessionLocal() as s:
            rows = (await s.exec(select(Skill))).all()
        return "\n".join(f"{k.name} [{k.type}]: {k.description}" for k in rows) or "(none)"

    async def create_subagent(
        name: str, role_prompt: str, skills: list[str] | None = None, model: str | None = None
    ) -> str:
        skills = skills or []
        async with SessionLocal() as s:
            if bad := await unknown_skills(s, skills):
                return f"Unknown skills {bad}. Call list_skills, or create_skill first."
            agent = Agent(
                name=name, role_prompt=role_prompt, skills=skills, model=model or settings.resolved_agent_model
            )
            s.add(agent)
            await s.commit()
            await s.refresh(agent)
        await events.publish("agent.updated", agent.model_dump())
        return f"Created sub-agent #{agent.id} '{agent.name}'. You can delegate to it now."

    async def update_subagent(
        agent_id: int,
        name: str | None = None,
        role_prompt: str | None = None,
        skills: list[str] | None = None,
        model: str | None = None,
    ) -> str:
        async with SessionLocal() as s:
            agent = await s.get(Agent, agent_id)
            if not agent:
                return f"No sub-agent #{agent_id}."
            if skills is not None and (bad := await unknown_skills(s, skills)):
                return f"Unknown skills {bad}. Call list_skills, or create_skill first."
            for key, value in dict(name=name, role_prompt=role_prompt, skills=skills, model=model).items():
                if value is not None:
                    setattr(agent, key, value)
            s.add(agent)
            await s.commit()
            await s.refresh(agent)
        await events.publish("agent.updated", agent.model_dump())
        return f"Updated sub-agent: {_describe_agent(agent)}"

    async def create_skill(
        name: str,
        description: str,
        type: str,
        instructions: str = "",
        tool_key: str | None = None,
        mcp_config: dict | None = None,
    ) -> str:
        async with SessionLocal() as s:
            if (await s.exec(select(Skill).where(Skill.name == name))).first():
                return f"A skill named '{name}' already exists. Use update_skill."
            skill = Skill(
                name=name, description=description, instructions=instructions,
                type=type, tool_key=tool_key, mcp_config=mcp_config,
            )
            if err := validate_skill(skill):
                return err
            s.add(skill)
            await s.commit()
        await events.publish("skill.updated", {"name": name})
        return f"Created skill '{name}'. Add it to a sub-agent's skills to use it."

    async def update_skill(
        name: str,
        description: str | None = None,
        instructions: str | None = None,
        tool_key: str | None = None,
        mcp_config: dict | None = None,
    ) -> str:
        async with SessionLocal() as s:
            skill = (await s.exec(select(Skill).where(Skill.name == name))).first()
            if not skill:
                return f"No skill named '{name}'. Call list_skills."
            for key, value in dict(
                description=description, instructions=instructions, tool_key=tool_key, mcp_config=mcp_config
            ).items():
                if value is not None:
                    setattr(skill, key, value)
            if err := validate_skill(skill):
                return err
            s.add(skill)
            await s.commit()
        await events.publish("skill.updated", {"name": name})
        return f"Updated skill '{name}'. Agents with it use the change on their next task."

    mk = StructuredTool.from_function
    return [
        mk(coroutine=list_agents, name="list_agents", description="List all sub-agents with their ids, roles and skills."),
        mk(coroutine=list_skills, name="list_skills", description="List the skills (tools) a sub-agent can be given."),
        mk(coroutine=create_subagent, name="create_subagent",
           description="Create a new sub-agent for work no existing one fits. Needs the user's approval. "
                       "`skills` are skill names from list_skills."),
        mk(coroutine=update_subagent, name="update_subagent",
           description="Edit a sub-agent (name, role_prompt, skills, model). Only pass what changes. "
                       "Needs the user's approval."),
        mk(coroutine=create_skill, name="create_skill",
           description="Create a skill. type 'builtin' needs tool_key (a built-in tool); type 'mcp' needs "
                       "mcp_config with a 'transport'. Needs the user's approval."),
        mk(coroutine=update_skill, name="update_skill",
           description="Edit a skill's description, instructions, tool_key or mcp_config. Needs the user's approval."),
    ]
