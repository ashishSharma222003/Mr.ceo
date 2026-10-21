"""Generic sub-agent runner. A LangChain agent is built per task from the agent's current
config (prompt, skills); conversation history persists per (manager thread, agent)."""
import asyncio
from datetime import datetime, timezone

from langchain.agents import create_agent

from ..config import settings
from ..db import SessionLocal
from ..models import Agent, Task, TaskStatus
from . import events
from .llm import make_model
from .skills import load_skills
from .memory import agent_thread_id, get_checkpointer, save_message


async def _execute(session, agent: Agent, task: Task) -> str:
    instruction = task.instruction
    if settings.fake_mode:
        # No key configured: keep the prototype usable with a canned result.
        await asyncio.sleep(3)
        return f"[{agent.name}] (fake, no ANTHROPIC_API_KEY) finished: {instruction}"

    tools, skills_prompt = await load_skills(session, agent.skills)  # DB skills -> LangChain tools (+ MCP)
    runnable = create_agent(
        model=make_model(agent.model),
        tools=tools,
        system_prompt=agent.role_prompt + skills_prompt,  # config: fresh from DB every run
        checkpointer=get_checkpointer(),  # history: kept per (manager thread, agent)
    )
    thread = agent_thread_id(task.thread_id or f"task-{task.id}", agent.id)
    out = await runnable.ainvoke(
        {"messages": [{"role": "user", "content": instruction}]},
        config={"configurable": {"thread_id": thread}},
    )
    content = out["messages"][-1].content
    if isinstance(content, list):  # content blocks -> plain text
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content


async def run_task(task_id: int) -> None:
    async with SessionLocal() as session:
        task = await session.get(Task, task_id)
        agent = await session.get(Agent, task.agent_id)

        task.status = TaskStatus.running
        session.add(task)
        await session.commit()
        events.publish("task.updated", task.model_dump())

        chat_thread = task.thread_id or f"task-{task.id}"
        try:
            await save_message(session, chat_thread, "manager", task.instruction, agent_id=agent.id)
            task.result = await _execute(session, agent, task)
            task.status = TaskStatus.done
            await save_message(session, chat_thread, "agent", task.result, agent_id=agent.id)
        except Exception as e:  # noqa: BLE001
            task.result = str(e)
            task.status = TaskStatus.failed

        task.finished_at = datetime.now(timezone.utc)
        session.add(task)
        await session.commit()
        events.publish("task.updated", task.model_dump())

    # Tell the Manager (imported here: manager.py imports this module).
    from .manager import notify_task_finished

    await notify_task_finished(task_id)
