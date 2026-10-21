"""The Manager: an LLM agent that plans work and delegates to sub-agents via tool calls.

Tools are built from the DB on every message, so any number of sub-agents works.
The Manager owns the conversation's tasklist (see tasklist_tools.py). When a sub-agent
finishes, `notify_task_finished` sends the Manager an update message so it can check the
result, mark the todo done and tell the user.
"""
import asyncio
import logging
import re

from langchain.agents import create_agent
from langchain_core.tools import StructuredTool
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..config import settings
from ..db import SessionLocal
from ..models import Agent, Task, TaskStatus, TodoStatus
from . import events, todos
from .llm import make_model
from .memory import get_checkpointer, save_message
from .runner import run_task
from .tasklist_tools import build_tasklist_tools

log = logging.getLogger(__name__)

_background: set[asyncio.Task] = set()
_locks: dict[str, asyncio.Lock] = {}  # one Manager run at a time per conversation

MANAGER_PROMPT = (
    "You are the Manager. You never do the work yourself: break the user's request "
    "into tasks and delegate each one to the best-suited sub-agent using its tool. "
    "Delegation is asynchronous, so a tool call only starts the task. After delegating, "
    "tell the user briefly who got what. If no sub-agent fits, say so. "
    "Each sub-agent remembers your earlier conversation with it, so for follow-ups "
    "delegate to the same sub-agent and refer to its previous work.\n\n"
    "TASKLIST: you own this conversation's tasklist. For each unit of work, add_todo first and "
    "pass its id as todo_id when delegating. The user may add, rename or remove items at any "
    "time; the current list is below, and get_tasklist shows it again. "
    "Messages starting with [UPDATE] are reports from the system that a sub-agent finished or "
    "failed. On a finished task, check the result, call complete_todo, then tell the user what "
    "was done. On a failed task do not complete the todo; tell the user and offer to retry. "
    "Never mark a todo done without such a report.\n\n"
    "Current tasklist:\n{tasklist}"
)


def _lock(thread_id: str) -> asyncio.Lock:
    return _locks.setdefault(thread_id, asyncio.Lock())


def _text(content) -> str:
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content


async def _dispatch(
    session: AsyncSession, agent: Agent, instruction: str, thread_id: str, todo_id: int | None
) -> Task:
    task = Task(agent_id=agent.id, instruction=instruction, thread_id=thread_id)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    events.publish("task.updated", task.model_dump())

    # Link to the tasklist: use the given todo, or create one so work is always tracked.
    todo = await todos.get_todo(session, todo_id, thread_id) if todo_id else None
    if todo:
        await todos.update_todo(session, todo, status=TodoStatus.in_progress, task_id=task.id)
    else:
        await todos.add_todo(session, thread_id, instruction[:80], TodoStatus.in_progress, task.id)

    bg = asyncio.create_task(run_task(task.id))
    _background.add(bg)  # keep a reference so it isn't garbage collected
    bg.add_done_callback(_background.discard)
    return task


def _delegate_tool(agent: Agent, thread_id: str, created: list[Task]) -> StructuredTool:
    async def delegate(instruction: str, todo_id: int | None = None) -> str:
        async with SessionLocal() as session:  # own session: tool calls may run in parallel
            task = await _dispatch(session, agent, instruction, thread_id, todo_id)
        created.append(task)
        return f"Task #{task.id} started on '{agent.name}'. It runs in the background."

    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", agent.name).strip("_").lower() or "agent"
    return StructuredTool.from_function(
        coroutine=delegate,
        name=f"delegate_to_{slug}_{agent.id}",  # id keeps names unique
        description=(
            f"Send a message/task to sub-agent '{agent.name}'. "
            f"Its role: {agent.role_prompt}. Skills: {', '.join(agent.skills) or 'none'}. "
            "Pass todo_id (from add_todo) to link the task to a tasklist item. "
            "It remembers your previous messages to it in this conversation."
        ),
    )


async def _run_manager(
    session: AsyncSession, agents: list[Agent], thread_id: str, message: str, created: list[Task]
) -> str:
    tasklist = todos.format_tasklist(await todos.list_todos(session, thread_id))
    manager = create_agent(
        model=make_model(settings.resolved_manager_model),
        tools=[_delegate_tool(a, thread_id, created) for a in agents]
        + build_tasklist_tools(thread_id),
        system_prompt=MANAGER_PROMPT.format(tasklist=tasklist),
        checkpointer=get_checkpointer(),
    )
    out = await manager.ainvoke(
        {"messages": [{"role": "user", "content": message}]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return _text(out["messages"][-1].content)


async def handle_message(
    session: AsyncSession, message: str, thread_id: str
) -> tuple[str, list[Task]]:
    agents = (await session.exec(select(Agent))).all()
    if not agents:
        return "You have no agents yet. Create one first.", []

    created: list[Task] = []
    await save_message(session, thread_id, "user", message)

    async with _lock(thread_id):
        if settings.fake_mode:
            # Fake mode: send the instruction to every agent.
            for a in agents:
                created.append(await _dispatch(session, a, message, thread_id, None))
            reply = f"(fake) Delegated to {len(created)} agent(s)."
        else:
            reply = await _run_manager(session, list(agents), thread_id, message, created)
        await save_message(session, thread_id, "manager", reply)
    return reply, created


async def notify_task_finished(task_id: int) -> None:
    """Called by the runner when a sub-agent task ends: the Manager learns the outcome,
    updates the tasklist and posts a message for the user."""
    try:
        async with SessionLocal() as session:
            task = await session.get(Task, task_id)
            if not task or not task.thread_id:
                return
            agent = await session.get(Agent, task.agent_id)
            thread_id = task.thread_id
            ok = task.status == TaskStatus.done
            update = (
                f"[UPDATE] Sub-agent '{agent.name}' {'finished' if ok else 'FAILED'} task "
                f"#{task.id}.\nInstruction: {task.instruction}\nResult: {task.result}"
            )

            async with _lock(thread_id):
                await save_message(session, thread_id, "system", update)
                if settings.fake_mode:
                    # Fake manager: same rule as the real one, done only on success.
                    todo = await todos.todo_for_task(session, task.id)
                    if todo and ok:
                        await todos.update_todo(session, todo, status=TodoStatus.done)
                    reply = f"(fake) Task #{task.id} {'finished' if ok else 'failed'}."
                else:
                    agents = list((await session.exec(select(Agent))).all())
                    reply = await _run_manager(session, agents, thread_id, update, [])
                await save_message(session, thread_id, "manager", reply)
            events.publish(
                "chat.message", {"thread_id": thread_id, "role": "manager", "content": reply}
            )
    except Exception:  # noqa: BLE001 - never crash the background task
        log.exception("Manager notification for task %s failed", task_id)
