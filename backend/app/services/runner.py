"""Generic sub-agent runner. A LangChain agent is built per task from the agent's current
config (prompt, skills); conversation history persists per (manager thread, agent)."""
import logging
import re
from datetime import datetime, timezone

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from pydantic import BaseModel, Field

from ..config import settings
from ..db import SessionLocal
from ..models import Agent, Task, TaskStatus
from . import events
from .llm import make_model
from .skills import load_skills
from .memory import agent_thread_id, get_checkpointer, save_message

log = logging.getLogger(__name__)


class AgentReport(BaseModel):
    """What a sub-agent hands back: one answer for the Manager, one short brief for the user."""

    response: str = Field(description="Your full answer / result for the Manager. Markdown is fine.")
    summary: str = Field(
        description="One or two short plain sentences, no markdown, no lists: what you did and why the "
        "task counts as complete (or what is missing)."
    )
    help_request: str = Field(
        default="",
        description="Leave empty unless you cannot finish without information or work from another "
        "specialist. Then say exactly what you need (the question to answer or the work to do).",
    )


HELP_PROMPT = (
    "\n\nIf you cannot finish without information or work from another specialist, do what you can, "
    "then put exactly what you need in help_request (or end with a line starting 'NEED HELP:'). "
    "The Manager will get it from a colleague or the user and send you the answer, so you can finish."
)
_NEED_HELP = re.compile(r"^\W*NEED HELP:\s*(.+)", re.I | re.M | re.S)


def plain(text: str, limit: int = 280) -> str:
    """Strip markdown, collapse whitespace, cut at a word boundary."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links -> their text
    text = re.sub(r"(?m)^\s*(#+|[-*+>]|\d+[.)])\s+", "", text)  # headings, bullets, quotes
    text = re.sub(r"[*_`~#>|]", "", text)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "\u2026"


def _text(content) -> str:
    if isinstance(content, list):  # content blocks -> plain text
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content


def _help_in(text: str) -> str | None:
    """A 'NEED HELP:' line in a plain-text answer (small models may skip the structured field)."""
    m = _NEED_HELP.search(text)
    return m.group(1).strip() if m else None


async def _execute(session, agent: Agent, task: Task) -> tuple[str, str, str | None]:
    """Run the sub-agent. Returns (full response, short plain-text summary, help request or None).
    Not streamed: only the Manager's replies stream to the user."""
    instruction = task.instruction
    if settings.fake_mode:
        # No key configured: keep the prototype usable with a canned result.
        return (
            f"[{agent.name}] (fake, no ANTHROPIC_API_KEY) finished: {instruction}",
            plain(f"{agent.name} finished: {instruction}"),
            None,
        )

    tools, skills_prompt = await load_skills(session, agent.skills)  # DB skills -> LangChain tools (+ MCP)

    def build(structured: bool):
        return create_agent(
            model=make_model(agent.model),
            tools=tools,
            system_prompt=agent.role_prompt + skills_prompt + HELP_PROMPT,  # config: fresh from DB every run
            response_format=ToolStrategy(AgentReport) if structured else None,
            checkpointer=get_checkpointer(),  # history: kept per (manager thread, agent)
        )

    inputs = {"messages": [{"role": "user", "content": instruction}]}
    config = {"configurable": {"thread_id": agent_thread_id(task.thread_id or f"task-{task.id}", agent.id, task.todo_id or f"t{task.id}")}}
    try:
        out = await build(True).ainvoke(inputs, config=config)
        report = out["structured_response"]
        return report.response, plain(report.summary), report.help_request.strip() or _help_in(report.response)
    except Exception:  # noqa: BLE001 - e.g. a small local model that can't fill the structure
        log.warning("Structured report failed for agent %s; falling back to plain text", agent.id, exc_info=True)
    out = await build(False).ainvoke(inputs, config=config)
    text = _text(out["messages"][-1].content)
    return text, plain(text), _help_in(text)


async def run_task(task_id: int, resume: bool = False) -> None:
    """Run a task. resume=True: the server restarted while it was running, so run it again."""
    async with SessionLocal() as session:
        task = await session.get(Task, task_id)
        if task.status in (TaskStatus.done, TaskStatus.failed):
            return
        agent = await session.get(Agent, task.agent_id)

        task.status = TaskStatus.running
        session.add(task)
        await session.commit()
        await events.publish("task.updated", task.model_dump())

        chat_thread = task.thread_id or f"task-{task.id}"
        try:
            if not resume:  # already in the history from the first attempt
                await save_message(session, chat_thread, "manager", task.instruction, agent_id=agent.id, todo_id=task.todo_id)
            task.result, task.summary, task.help_request = await _execute(session, agent, task)
            task.status = TaskStatus.done
            await save_message(session, chat_thread, "agent", task.result, agent_id=agent.id, todo_id=task.todo_id)
        except Exception as e:  # noqa: BLE001
            task.result = str(e)
            task.status = TaskStatus.failed

        task.finished_at = datetime.now(timezone.utc)
        session.add(task)
        await session.commit()
        await events.publish("task.updated", task.model_dump())

    # Tell the Manager (imported here: manager.py imports this module).
    from .manager import notify_task_finished

    await notify_task_finished(task_id)
