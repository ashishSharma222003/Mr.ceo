"""The Manager: an LLM agent that plans work and delegates to sub-agents via tool calls.

Tools are built from the DB on every message, so any number of sub-agents works.
The Manager owns the conversation's tasklist (see tasklist_tools.py). When a sub-agent
finishes, `notify_task_finished` sends the Manager an update message so it can check the
result, mark the todo done and tell the user.

The Manager can also create and edit sub-agents and skills (agent_tools.py). Those calls pause the
run for the user's approval: the pause is saved as an `Approval` row, the run waits in the LangGraph
checkpoint, and `resolve_approval` resumes it with the user's decisions.
"""
import asyncio
import logging
import re

from datetime import datetime, timezone

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.tools import StructuredTool
from langgraph.types import Command
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..config import settings
from ..db import SessionLocal
from ..models import Agent, Approval, Task, TaskStatus, Todo, TodoStatus
from . import events, todos
from .agent_tools import GATED, build_agent_tools, list_agents_text
from .llm import make_model
from .memory import get_checkpointer, save_message
from .runner import run_task
from .stream import stream_agent
from .tasklist_tools import build_tasklist_tools

log = logging.getLogger(__name__)

_background: set[asyncio.Task] = set()
_locks: dict[str, asyncio.Lock] = {}  # one Manager run at a time per conversation

MANAGER_PROMPT = (
    "You are the Manager. You never do the work yourself: break the user's request "
    "into tasks and delegate each one to the best-suited sub-agent using its tool. "
    "Delegation is asynchronous, so a tool call only starts the task. After delegating, "
    "tell the user briefly who got what. "
    "If no sub-agent fits, you may propose one with create_subagent, or change one with "
    "update_subagent / create_skill / update_skill: the user is asked to approve every such "
    "call, so explain in a sentence why before calling. If they reject, respect that and do not "
    "retry the same change. "
    "A sub-agent remembers only its earlier conversation about the SAME todo, so to continue or "
    "rework a todo delegate again with that todo_id and refer to its previous work. For a different "
    "todo it starts with a clean memory: put all the context it needs in the instruction.\n\n"
    "TASKLIST: you own this conversation's tasklist. For each unit of work, add_todo first and "
    "pass its id as todo_id when delegating. The user may add, rename or remove items at any "
    "time; the current list is below, and get_tasklist shows it again. "
    "Messages starting with [UPDATE] are reports from the system that a sub-agent finished or "
    "failed. You are the gatekeeper: judge whether the result really meets the todo's requirements. "
    "If it does, call submit_for_review, then tell the user WHAT THE RESULT IS: the key findings or "
    "output in your own words (a few sentences or short bullets drawn from the result), not just that "
    "it awaits approval; end by saying they can approve it or ask for changes. Only the user can "
    "mark a todo done, and they only ever see what you submit. If it falls short, do NOT submit: "
    "call delegate_to_agent again with the same todo_id and the exact corrections (edit_todo first if "
    "the requirement itself changed), and tell the user briefly why. "
    "On a failed task do not submit it; tell the user and offer to retry. "
    "Never submit a todo without such a report. You cannot mark anything done: if the user asks "
    "you to complete a task, tell them to press Approve on it in the tasklist. "
    "ALWAYS finish with a short plain-text message to the user, even after tool calls. "
    "Messages starting with [ABOUT Task #n] are the user's words about that specific todo (they picked it "
    "in the tasklist). If they want changes: call edit_todo to update its requirements, then "
    "delegate_to_agent again to the same sub-agent with that todo_id, stating exactly what must change "
    "and referring to its previous work. If they only ask a question, answer it without re-delegating.\n\n"
    "TASK REFERENCES: tasklist items are called tasks and have ids like Task #3. Whenever you mention "
    "one to the user, write it exactly as Task #<id> (e.g. 'Task #3 is done'), so the user can click it.\n\n"
    "TASK WRITING: give every todo a short `title` (a heading) and a `description` saying what the "
    "work involves.\n\n"
    "{agents_note}"
    "Sub-agents (delegate with delegate_to_agent):\n{agents}\n\n"
    "Current tasklist:\n{tasklist}"
)

NO_AGENTS_NOTE = (
    "There are NO sub-agents yet, so nothing can be delegated. If the work needs one, propose "
    "it with create_subagent (the user approves); otherwise answer directly.\n\n"
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

    # Link to the tasklist: use the given todo, or create one so work is always tracked.
    todo = await todos.get_todo(session, todo_id, thread_id) if todo_id else None
    if todo:
        todo.summary = None  # the old report no longer applies to the new attempt
        await todos.update_todo(session, todo, status=TodoStatus.in_progress, task_id=task.id)
    else:
        todo = await todos.add_todo(
            session, thread_id, instruction[:80], TodoStatus.in_progress, task.id, description=instruction
        )
    task.todo_id = todo.id  # the sub-agent's memory is per todo
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await events.publish("task.updated", task.model_dump())

    bg = asyncio.create_task(run_task(task.id))
    _background.add(bg)  # keep a reference so it isn't garbage collected
    bg.add_done_callback(_background.discard)
    return task


def _delegate_tool(thread_id: str, created: list[Task]) -> StructuredTool:
    async def delegate_to_agent(agent_id: int, instruction: str, todo_id: int | None = None) -> str:
        async with SessionLocal() as session:  # own session: tool calls may run in parallel
            agent = await session.get(Agent, agent_id)
            if not agent:
                return f"No sub-agent #{agent_id}. Call list_agents."
            task = await _dispatch(session, agent, instruction, thread_id, todo_id)
        created.append(task)
        return f"Task #{task.todo_id} started on '{agent.name}'. It runs in the background."

    return StructuredTool.from_function(
        coroutine=delegate_to_agent,
        name="delegate_to_agent",
        description=(
            "Send a task to a sub-agent by id (see the sub-agent list). Pass todo_id (from add_todo) "
            "to link the task to a tasklist item. The sub-agent remembers earlier messages about the "
            "same todo_id only; a new todo starts with a clean memory, so include all needed context."
        ),
    )


def _action_lines(actions: list[dict]) -> str:
    return "\n".join(f"- {a['name']}({', '.join(f'{k}={v!r}' for k, v in a['args'].items())})" for a in actions)


async def pending_approval(session: AsyncSession, thread_id: str) -> Approval | None:
    q = select(Approval).where(Approval.thread_id == thread_id, Approval.status == "pending")
    return (await session.exec(q.order_by(Approval.id.desc()))).first()


async def _run_manager(
    session: AsyncSession, agents: list[Agent], thread_id: str, inputs, created: list[Task]
) -> str:
    """Run the Manager on a user message / update (str) or resume it after an approval (Command)."""
    tasklist = todos.format_tasklist(await todos.list_todos(session, thread_id))
    manager = create_agent(
        model=make_model(settings.resolved_manager_model),
        tools=[_delegate_tool(thread_id, created)] + build_agent_tools() + build_tasklist_tools(thread_id),
        system_prompt=MANAGER_PROMPT.format(
            tasklist=tasklist,
            agents=await list_agents_text(),
            agents_note="" if agents else NO_AGENTS_NOTE,
        ),
        middleware=[HumanInTheLoopMiddleware(interrupt_on={name: True for name in GATED})],
        checkpointer=get_checkpointer(),
    )
    config = {"configurable": {"thread_id": thread_id}}
    if isinstance(inputs, str):
        inputs = {"messages": [{"role": "user", "content": inputs}]}
    final = await stream_agent(manager, inputs, config, "chat.delta", {"thread_id": thread_id})
    reply = _text(final)

    # Paused for approval? The pending tool calls are in the checkpoint; record them for the UI.
    state = await manager.aget_state(config)
    interrupts = [i for t in state.tasks for i in t.interrupts]
    if interrupts:
        actions = [
            {"name": a["name"], "args": a["args"], "description": a.get("description", "")}
            for a in interrupts[0].value["action_requests"]
        ]
        approval = Approval(thread_id=thread_id, actions=actions)
        session.add(approval)
        await session.commit()
        await session.refresh(approval)
        await events.publish("approval.requested", approval.model_dump())
        reply = reply or "I'd like to make these changes, if you approve:\n" + _action_lines(actions)
    return reply or _fallback_reply(state.values.get("messages", []))


def _fallback_reply(messages) -> str:
    """Small models sometimes end a turn with no text after their tool calls; never show silence."""
    calls: list[str] = []
    for m in reversed(messages):
        if m.type == "human":
            break
        if m.type == "ai":
            if text := _text(m.content):
                return text
            calls += [c["name"] for c in m.tool_calls]
    return "Done (" + ", ".join(reversed(calls)) + ")." if calls else "I didn't have anything to add."


def _about(todo: Todo, task: Task | None) -> str:
    """Prefix telling the Manager which task a user message is about. The user only sees 'Task #n'."""
    where = f", sub-agent #{task.agent_id}" if task else ""
    return f"[ABOUT Task #{todo.id} '{todo.title}' (status {todo.status.value}{where})]\n"


async def handle_message(
    session: AsyncSession, message: str, thread_id: str, todo_id: int | None = None
) -> tuple[str, list[Task]]:
    agents = (await session.exec(select(Agent))).all()
    todo = await todos.get_todo(session, todo_id, thread_id) if todo_id else None
    task = await session.get(Task, todo.task_id) if todo and todo.task_id else None

    created: list[Task] = []
    asked = await save_message(session, thread_id, "user", message, todo_id=todo.id if todo else None)
    known = {t.id for t in await todos.list_todos(session, thread_id)}

    async with _lock(thread_id):
        if settings.fake_mode:
            # Fake mode: send the instruction to the task's agent, or to every agent.
            agent = await session.get(Agent, task.agent_id) if task else None
            for a in [agent] if agent else agents:
                created.append(await _dispatch(session, a, message, thread_id, todo.id if agent else None))
            reply = (
                f"(fake) Delegated to {len(created)} agent(s)."
                if created
                else "(fake) No sub-agents yet, so nothing was delegated. Create one to get work done."
            )
        else:
            text = (_about(todo, task) + message) if todo else message
            reply = await _run_manager(session, list(agents), thread_id, text, created)
        await save_message(session, thread_id, "manager", reply, todo_id=todo.id if todo else None)
        # Items created while answering this message remember it, so each task page can show
        # the request it came from.
        for t in await todos.list_todos(session, thread_id):
            if t.id not in known and t.origin_message_id is None:
                t.origin_message_id = asked.id
                session.add(t)
        await session.commit()
    return reply, created


async def resolve_approval(
    session: AsyncSession, approval: Approval, decisions: list[dict]
) -> tuple[str, list[Task]]:
    """Resume the paused Manager with the user's decisions (LangChain HITL format)."""
    created: list[Task] = []
    thread_id = approval.thread_id
    async with _lock(thread_id):
        approval.status, approval.decisions = "resolved", decisions
        approval.resolved_at = datetime.now(timezone.utc)
        session.add(approval)
        await session.commit()
        await events.publish("approval.resolved", approval.model_dump())

        agents = list((await session.exec(select(Agent))).all())
        resume = Command(resume={"decisions": decisions})
        reply = await _run_manager(session, agents, thread_id, resume, created)
        await save_message(session, thread_id, "manager", reply)
    await events.publish("chat.message", {"thread_id": thread_id, "role": "manager", "content": reply})
    spawn(process_pending(thread_id))  # reports that arrived during the pause
    return reply, created


def spawn(coro) -> None:
    bg = asyncio.create_task(coro)
    _background.add(bg)
    bg.add_done_callback(_background.discard)


async def notify_task_finished(task_id: int) -> None:
    """Called by the runner when a sub-agent task ends: the Manager learns the outcome,
    updates the tasklist and posts a message for the user. Safe to call twice: `task.notified`
    makes it happen once, and leaves it pending if the server dies midway."""
    try:
        async with SessionLocal() as session:
            task = await session.get(Task, task_id)
            if not task or not task.thread_id:
                return
            agent = await session.get(Agent, task.agent_id)
            thread_id = task.thread_id
            ok = task.status == TaskStatus.done
            todo = await todos.get_todo(session, task.todo_id) if task.todo_id else None
            about = f"Task #{todo.id} '{todo.title}'" if todo else "its task"
            update = (
                f"[UPDATE] Sub-agent '{agent.name}' {'finished' if ok else 'FAILED'} {about}."
                f"\nInstruction: {task.instruction}\nResult: {task.result}"
                + ("\n\nIf the work meets the requirements, submit it and report the key points of this "
                   "result to the user." if ok else "")
            )

            async with _lock(thread_id):
                await session.refresh(task)
                if task.notified:
                    return
                if not settings.fake_mode and await pending_approval(session, thread_id):
                    return  # the Manager is paused mid-run; process_pending retries after the answer
                await save_message(session, thread_id, "system", update, todo_id=task.todo_id)
                if settings.fake_mode:
                    reply = f"(fake) Task #{task.todo_id} {'finished' if ok else 'failed'}."
                else:
                    agents = list((await session.exec(select(Agent))).all())
                    reply = await _run_manager(session, agents, thread_id, update, [])

                # The Manager must decide: submit for approval, or send the work back (a new task
                # replaces todo.task_id). If it did neither, ask once more.
                todo = await todos.todo_for_task(session, task.id)
                if todo:
                    await session.refresh(todo)  # the Manager's tools changed it in their own sessions
                if todo and ok and not settings.fake_mode and todo.status == TodoStatus.in_progress:
                    nudge = (
                        f"[UPDATE] You did not decide on Task #{todo.id} yet. Either call submit_for_review "
                        "if the work meets the requirements, or delegate it again with corrections."
                    )
                    agents = list((await session.exec(select(Agent))).all())
                    reply = await _run_manager(session, agents, thread_id, nudge, []) or reply
                    await session.refresh(todo)
                if todo and ok and todo.status == TodoStatus.in_progress and todo.task_id == task.id:
                    # Still undecided (or fake mode): never leave finished work stuck, let the user judge.
                    await todos.submit_for_review(session, todo)
                await save_message(session, thread_id, "manager", reply, todo_id=task.todo_id)
                task.notified = True
                session.add(task)
                await session.commit()
            await events.publish(
                "chat.message", {"thread_id": thread_id, "role": "manager", "content": reply}
            )
    except Exception:  # noqa: BLE001 - never crash the background task
        log.exception("Manager notification for task %s failed", task_id)


async def process_pending(thread_id: str | None = None) -> None:
    """Finish what a restart (or an approval pause) left undone: tell the Manager about ended tasks
    it hasn't heard about."""
    async with SessionLocal() as session:
        tq = select(Task).where(Task.notified == False, Task.status.in_([TaskStatus.done, TaskStatus.failed]))  # noqa: E712
        if thread_id:
            tq = tq.where(Task.thread_id == thread_id)
        task_ids = [t.id for t in (await session.exec(tq.order_by(Task.id))).all()]
    for tid in task_ids:
        await notify_task_finished(tid)


async def recover() -> None:
    """Run at startup. Background work lives only in memory, so anything still 'pending' or
    'running' was cut off by the restart: run it again. Then catch up on missed notifications."""
    async with SessionLocal() as session:
        q = select(Task).where(Task.status.in_([TaskStatus.pending, TaskStatus.running])).order_by(Task.id)
        cut_off = [t.id for t in (await session.exec(q)).all()]
    async with SessionLocal() as session:  # finished work stuck before review (e.g. Manager never reported)
        q = select(Todo).where(Todo.status == TodoStatus.in_progress, Todo.task_id.is_not(None))
        for todo in (await session.exec(q)).all():
            task = await session.get(Task, todo.task_id)
            if task and task.status == TaskStatus.done and task.notified:
                await todos.submit_for_review(session, todo)
    for tid in cut_off:
        log.info("Resuming task %s after restart", tid)
        spawn(run_task(tid, resume=True))
    await process_pending()
