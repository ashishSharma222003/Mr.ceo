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
from ..models import Agent, Approval, Task, TaskStatus, Thread, Todo, TodoStatus
from . import events, threads, todos
from .agent_tools import GATED, agents_text, build_agent_tools
from .llm import make_model
from .memory import get_checkpointer, save_message
from .runner import run_task
from .stream import stream_agent
from .tasklist_tools import Unpaired, build_tasklist_tools

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
    "ALWAYS pass its id as todo_id when delegating: delegate_to_agent without todo_id creates a second, "
    "duplicate task. Call add_todo once per unit of work, never twice for the same thing, and if the "
    "tasklist already has an item for the work (e.g. one the user added), delegate with that id instead "
    "of adding a new one. The user may add, rename or remove items at any "
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
    "HELP REQUESTS: an [UPDATE] saying a sub-agent is BLOCKED means it needs something it doesn't "
    "have. Do NOT submit that todo. Unblock it in ONE of three ways: (a) the answer is already in this "
    "conversation (sub-agents only see your instruction, not the user's messages): call answer_agent "
    "with the todo_id and the answer; (b) another sub-agent can work it out: call ask_agent with its "
    "agent_id, the todo_id and a self-contained question; (c) only the user can know (facts about them, "
    "their preferences, a choice to make): call ask_user with the todo_id and one clear question, which "
    "is shown to them in the chat. Every answer goes back to the blocked sub-agent automatically, "
    "which then finishes the todo and reports again.\n\n"
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

OWN_TEAM_NOTE = (
    "The user chose to build their own team for this conversation: only the sub-agents listed below "
    "exist here, and any you create belong to this conversation alone.\n\n"
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
    spawn(run_task(task.id))
    return task


async def _ask_helper(session: AsyncSession, helper: Agent, question: str, blocked: Task) -> Task:
    """Start a task on `helper` that answers `blocked`'s help request. The todo stays linked to the
    blocked task; when the helper finishes, its answer is relayed back (see _relay_answer)."""
    task = Task(
        agent_id=helper.id, instruction=question, thread_id=blocked.thread_id,
        todo_id=blocked.todo_id, helps_task_id=blocked.id,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await events.publish("task.updated", task.model_dump())
    spawn(run_task(task.id))
    return task


async def _helper_of(session: AsyncSession, task_id: int) -> Task | None:
    """A helper that is answering (or answered) this task's request. A failed one can be retried."""
    q = select(Task).where(Task.helps_task_id == task_id, Task.status != TaskStatus.failed)
    return (await session.exec(q)).first()


async def _blocked(session: AsyncSession, thread_id: str, todo_id: int) -> Task | str:
    """The sub-agent task blocked on this todo and waiting for an answer, or why there is none."""
    todo = await todos.get_todo(session, todo_id, thread_id)
    blocked = await session.get(Task, todo.task_id) if todo and todo.task_id else None
    if not blocked or not blocked.help_request:
        return f"No sub-agent is blocked on Task #{todo_id}. Use delegate_to_agent for new work."
    if await _helper_of(session, blocked.id):
        return f"A sub-agent is already answering Task #{todo_id}'s request. Wait for it."
    return blocked


async def _answer_blocked(session: AsyncSession, blocked: Task, who: str, answer: str) -> Task:
    """Send an answer, verbatim, to the blocked sub-agent on the same todo (so it remembers its draft)."""
    agent = await session.get(Agent, blocked.agent_id)
    instruction = (
        f"You asked for help: {blocked.help_request}\n{who} answered:\n{answer}\n\n"
        "Use this answer to finish your task. Do not ask for the same help again."
    )
    return await _dispatch(session, agent, instruction, blocked.thread_id, blocked.todo_id)


async def _open_questions(session: AsyncSession, thread_id: str) -> list[Task]:
    """Blocked tasks whose question to the user (ask_user) is still unanswered."""
    q = (
        select(Task)
        .join(Todo, Todo.task_id == Task.id)
        .where(Task.thread_id == thread_id, Task.user_question.is_not(None), Todo.status == TodoStatus.in_progress)
    )
    return list((await session.exec(q.order_by(Task.id))).all())


def _question_text(agent: Agent, task: Task) -> str:
    return (
        f"**{agent.name}** has a question about Task #{task.todo_id}:\n\n{task.user_question}\n\n"
        "Reply here in the chat and I'll pass your answer on."
    )


async def _relay_answer(session: AsyncSession, helper_task: Task) -> str:
    """The helper finished: send its answer back to the blocked sub-agent. Returns the message for the user."""
    blocked = await session.get(Task, helper_task.helps_task_id)
    agent = await session.get(Agent, blocked.agent_id)
    helper = await session.get(Agent, helper_task.agent_id)
    await _answer_blocked(session, blocked, f"'{helper.name}'", helper_task.result)
    return (
        f"'{helper.name}' answered '{agent.name}' on Task #{blocked.todo_id}. "
        f"I passed the answer on, and '{agent.name}' is finishing the task."
    )


async def _unlinked(session: AsyncSession, added: list[int]) -> int | None:
    """Claim the first todo added in this Manager run that no task works on yet."""
    for todo_id in list(added):
        todo = await session.get(Todo, todo_id)
        # Re-check after the await: a parallel delegate call may have claimed it meanwhile.
        if todo and todo.task_id is None and todo.status == TodoStatus.todo and todo_id in added:
            added.remove(todo_id)
            return todo_id
    return None


def _delegate_tool(thread_id: str, created: list[Task], unpaired: Unpaired) -> StructuredTool:
    async def delegate_to_agent(agent_id: int, instruction: str, todo_id: int | None = None) -> str:
        async with SessionLocal() as session:  # own session: tool calls may run in parallel
            agent = await session.get(Agent, agent_id)
            if not agent or not threads.in_team(await session.get(Thread, thread_id), agent):
                return f"No sub-agent #{agent_id} in this chat's team. Call list_agents."
            # Small models often skip todo_id: use the item add_todo just made, not a duplicate.
            if todo_id in unpaired.added:
                unpaired.added.remove(todo_id)  # claimed explicitly
            todo_id = todo_id or await _unlinked(session, unpaired.added)
            task = await _dispatch(session, agent, instruction, thread_id, todo_id)
            if todo_id is None:  # _dispatch made an item; a later add_todo in this run names it
                unpaired.auto.append(task.todo_id)
        created.append(task)
        return f"Task #{task.todo_id} started on '{agent.name}'. It runs in the background."

    return StructuredTool.from_function(
        coroutine=delegate_to_agent,
        name="delegate_to_agent",
        description=(
            "Send a task to a sub-agent by id (see the sub-agent list). Always pass todo_id (from add_todo "
            "or the tasklist); without it a duplicate tasklist item is created. The sub-agent remembers earlier messages about the "
            "same todo_id only; a new todo starts with a clean memory, so include all needed context."
        ),
    )


def _help_tools(thread_id: str, created: list[Task], user_message: str | None) -> list[StructuredTool]:
    """Ways to unblock a sub-agent. `user_message`: set when this run answers a user chat message."""

    async def ask_agent(agent_id: int, todo_id: int, question: str) -> str:
        async with SessionLocal() as session:
            helper = await session.get(Agent, agent_id)
            if not helper or not threads.in_team(await session.get(Thread, thread_id), helper):
                return f"No sub-agent #{agent_id} in this chat's team. Call list_agents."
            blocked = await _blocked(session, thread_id, todo_id)
            if isinstance(blocked, str):
                return blocked
            if helper.id == blocked.agent_id:
                return "That is the blocked sub-agent itself. Pick a different sub-agent."
            task = await _ask_helper(session, helper, question, blocked)
        created.append(task)
        return f"Asked '{helper.name}'. Its answer will be passed back automatically when it finishes."

    async def ask_user(todo_id: int, question: str) -> str:
        async with SessionLocal() as session:
            blocked = await _blocked(session, thread_id, todo_id)
            if isinstance(blocked, str):
                return blocked
            if blocked.user_question:
                return f"The user was already asked about Task #{todo_id}. Wait for their reply."
            blocked.user_question = question
            session.add(blocked)
            await session.commit()
            await events.publish("task.updated", blocked.model_dump())
        return "The question is shown to the user in the chat. When they reply, pass it on with answer_agent."

    async def answer_agent(todo_id: int, answer: str) -> str:
        async with SessionLocal() as session:
            blocked = await _blocked(session, thread_id, todo_id)
            if isinstance(blocked, str):
                return blocked
            if blocked.user_question and user_message:
                who, answer = "The user", user_message  # their own words, not a paraphrase
            else:
                who = "The Manager"
            task = await _answer_blocked(session, blocked, who, answer)
        created.append(task)
        return f"Sent the answer to the sub-agent on Task #{todo_id}. It is finishing the task."

    return [
        StructuredTool.from_function(
            coroutine=ask_agent,
            name="ask_agent",
            description=(
                "When a sub-agent is BLOCKED on a todo and asks for help: ask another sub-agent (agent_id) "
                "a self-contained question for that todo_id. Its answer goes back to the blocked sub-agent "
                "automatically, which then finishes the todo."
            ),
        ),
        StructuredTool.from_function(
            coroutine=ask_user,
            name="ask_user",
            description=(
                "When a BLOCKED sub-agent needs something only the user knows: ask the user one clear "
                "question for that todo_id. It is shown in the chat; their reply comes as a normal message."
            ),
        ),
        StructuredTool.from_function(
            coroutine=answer_agent,
            name="answer_agent",
            description=(
                "Answer a BLOCKED sub-agent on a todo_id: with facts already in this conversation, or with "
                "the user's reply to a question you asked with ask_user. The sub-agent then finishes the todo."
            ),
        ),
    ]


def _action_lines(actions: list[dict]) -> str:
    return "\n".join(f"- {a['name']}({', '.join(f'{k}={v!r}' for k, v in a['args'].items())})" for a in actions)


async def pending_approval(session: AsyncSession, thread_id: str) -> Approval | None:
    q = select(Approval).where(Approval.thread_id == thread_id, Approval.status == "pending")
    return (await session.exec(q.order_by(Approval.id.desc()))).first()


async def _run_manager(
    session: AsyncSession, agents: list[Agent], thread_id: str, inputs, created: list[Task],
    user_message: str | None = None,
) -> str:
    """Run the Manager on a user message / update (str) or resume it after an approval (Command).
    `user_message`: the user's own words, when this run answers a chat message."""
    tasklist = todos.format_tasklist(await todos.list_todos(session, thread_id))
    thread = await session.get(Thread, thread_id)
    own = OWN_TEAM_NOTE if thread and thread.team == "own" else ""
    unpaired = Unpaired()  # pairs add_todo with delegations that skip todo_id, in this run
    manager = create_agent(
        model=make_model(settings.resolved_manager_model),
        tools=[_delegate_tool(thread_id, created, unpaired), *_help_tools(thread_id, created, user_message)]
        + build_agent_tools(thread_id)
        + build_tasklist_tools(thread_id, unpaired),
        system_prompt=MANAGER_PROMPT.format(
            tasklist=tasklist,
            agents=agents_text(agents),
            agents_note=own + ("" if agents else NO_AGENTS_NOTE),
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
    thread = await threads.ensure(session, thread_id)
    await threads.touch(session, thread, first_message=message)
    agents = await threads.team_agents(session, thread_id)
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
            if waiting := await _open_questions(session, thread_id):
                text = (
                    "[WAITING FOR THE USER] You asked the user, for blocked sub-agents:\n"
                    + "\n".join(f"- Task #{t.todo_id}: {t.user_question}" for t in waiting)
                    + "\nIf the message below answers one, call answer_agent with that todo_id "
                    "(the user's words are passed on as they are). Otherwise handle it as usual.\n\n"
                    + text
                )
            reply = await _run_manager(session, agents, thread_id, text, created, user_message=message)
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

        agents = await threads.team_agents(session, thread_id)
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
            blocked = ok and bool(task.help_request) and not task.helps_task_id
            if task.helps_task_id:  # a helper's answer to a blocked sub-agent
                asker = await session.get(Agent, (await session.get(Task, task.helps_task_id)).agent_id)
                update = (
                    f"[UPDATE] Sub-agent '{agent.name}' FAILED to answer '{asker.name}''s help request on "
                    f"{about}. Error: {task.result}\nTell the user; offer to ask another sub-agent."
                )
            elif blocked:
                update = (
                    f"[UPDATE] Sub-agent '{agent.name}' is BLOCKED on {about} and needs help.\n"
                    f"Help needed: {task.help_request}\nIts work so far: {task.result}\n\n"
                    f"Do not submit it. Unblock it (todo_id={task.todo_id}) with answer_agent if the answer is in "
                    "this conversation, ask_agent if another sub-agent can work it out, or ask_user if only the "
                    "user knows."
                )
            else:
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
                if ok and task.helps_task_id:
                    # No Manager LLM call: the answer goes back word for word, so nothing is lost.
                    reply = await _relay_answer(session, task)
                else:
                    await save_message(session, thread_id, "system", update, todo_id=task.todo_id)
                    if settings.fake_mode:
                        reply = f"(fake) Task #{task.todo_id} {'finished' if ok else 'failed'}."
                    else:
                        agents = await threads.team_agents(session, thread_id)
                        reply = await _run_manager(session, agents, thread_id, update, [])

                # The Manager must decide: submit for approval, or send the work back (a new task
                # replaces todo.task_id), or get help for a blocked sub-agent. If it did none, ask once more.
                todo = await todos.todo_for_task(session, task.id) if not task.helps_task_id else None
                if todo:
                    await session.refresh(todo)  # the Manager's tools changed it in their own sessions

                def undecided() -> bool:
                    return todo.status == TodoStatus.in_progress and todo.task_id == task.id

                await session.refresh(task)  # ask_user may have set user_question in its own session
                if (
                    todo and ok and not settings.fake_mode and undecided()
                    and not task.user_question and not await _helper_of(session, task.id)
                ):
                    nudge = (
                        f"[UPDATE] You did not act on Task #{todo.id} yet. The sub-agent is blocked: call "
                        "answer_agent if the answer is in this conversation, ask_agent if another sub-agent can "
                        "help, or ask_user if only the user knows."
                        if blocked else
                        f"[UPDATE] You did not decide on Task #{todo.id} yet. Either call submit_for_review "
                        "if the work meets the requirements, or delegate it again with corrections."
                    )
                    agents = await threads.team_agents(session, thread_id)
                    reply = await _run_manager(session, agents, thread_id, nudge, []) or reply
                    await session.refresh(todo)
                    await session.refresh(task)
                if todo and blocked and task.user_question and undecided():
                    reply = _question_text(agent, task)  # the question itself, in the chat, not a paraphrase
                if todo and ok and not blocked and undecided():
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
            if task and task.status == TaskStatus.done and task.notified and not task.help_request:
                await todos.submit_for_review(session, todo)
    for tid in cut_off:
        log.info("Resuming task %s after restart", tid)
        spawn(run_task(tid, resume=True))
    await process_pending()
