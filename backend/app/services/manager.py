"""The Manager: an LLM agent that plans work and delegates to sub-agents via tool calls.

Tools are built from the DB on every message, so any number of sub-agents works.
"""
import asyncio
import re

from langchain.agents import create_agent
from langchain_core.tools import StructuredTool
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..config import settings
from ..models import Agent, Task
from . import events
from .memory import get_checkpointer, save_message
from .runner import run_task

_background: set[asyncio.Task] = set()

MANAGER_PROMPT = (
    "You are the Manager. You never do the work yourself: break the user's request "
    "into tasks and delegate each one to the best-suited sub-agent using its tool. "
    "Delegation is asynchronous, so a tool call only starts the task. After delegating, "
    "tell the user briefly who got what. If no sub-agent fits, say so. "
    "Each sub-agent remembers your earlier conversation with it, so for follow-ups "
    "delegate to the same sub-agent and refer to its previous work."
)


async def _dispatch(session: AsyncSession, agent: Agent, instruction: str, thread_id: str) -> Task:
    task = Task(agent_id=agent.id, instruction=instruction, thread_id=thread_id)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    events.publish("task.updated", task.model_dump())

    bg = asyncio.create_task(run_task(task.id))
    _background.add(bg)  # keep a reference so it isn't garbage collected
    bg.add_done_callback(_background.discard)
    return task


def _delegate_tool(
    session: AsyncSession, agent: Agent, thread_id: str, created: list[Task]
) -> StructuredTool:
    async def delegate(instruction: str) -> str:
        task = await _dispatch(session, agent, instruction, thread_id)
        created.append(task)
        return f"Task #{task.id} started on '{agent.name}'. It runs in the background."

    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", agent.name).strip("_").lower() or "agent"
    return StructuredTool.from_function(
        coroutine=delegate,
        name=f"delegate_to_{slug}_{agent.id}",  # id keeps names unique
        description=(
            f"Send a message/task to sub-agent '{agent.name}'. "
            f"Its role: {agent.role_prompt}. Skills: {', '.join(agent.skills) or 'none'}. "
            "It remembers your previous messages to it in this conversation."
        ),
    )


async def handle_message(
    session: AsyncSession, message: str, thread_id: str
) -> tuple[str, list[Task]]:
    agents = (await session.exec(select(Agent))).all()
    if not agents:
        return "You have no agents yet. Create one first.", []

    created: list[Task] = []
    await save_message(session, thread_id, "user", message)

    if not settings.anthropic_api_key:
        # Fake mode: send the instruction to every agent.
        for a in agents:
            created.append(await _dispatch(session, a, message, thread_id))
        reply = f"(fake) Delegated to {len(created)} agent(s)."
        await save_message(session, thread_id, "manager", reply)
        return reply, created

    manager = create_agent(
        model=f"anthropic:{settings.manager_model}",
        tools=[_delegate_tool(session, a, thread_id, created) for a in agents],
        system_prompt=MANAGER_PROMPT,
        checkpointer=get_checkpointer(),
    )
    out = await manager.ainvoke(
        {"messages": [{"role": "user", "content": message}]},
        config={"configurable": {"thread_id": thread_id}},
    )
    content = out["messages"][-1].content
    if isinstance(content, list):
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
    await save_message(session, thread_id, "manager", content)
    return content, created
