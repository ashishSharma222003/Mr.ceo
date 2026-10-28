from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class Thread(SQLModel, table=True):
    """A conversation with the Manager.

    team="shared": the Manager works with the shared sub-agent library (and adds new ones to it).
    team="own":    the chat starts with no sub-agents; the ones made in it belong to it alone.
    """

    id: str = Field(primary_key=True)
    title: str = "New chat"  # becomes the first user message, shortened
    team: str = "shared"
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Agent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    role_prompt: str
    model: str = "claude-sonnet-5-5"
    skills: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    thread_id: str | None = Field(default=None, index=True)  # set: private to that "own team" chat
    created_at: datetime = Field(default_factory=_now)


class Task(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    agent_id: int = Field(foreign_key="agent.id")
    instruction: str
    thread_id: str | None = None  # Manager conversation this task belongs to
    todo_id: int | None = None  # tasklist item this work is for; the sub-agent's memory is keyed by it
    status: TaskStatus = TaskStatus.pending
    result: str | None = None  # the sub-agent's full response (for the Manager)
    summary: str | None = None  # short plain-text brief: why it is complete and what was done (for the user)
    notified: bool = False  # the Manager has been told how it ended (so a restart doesn't skip or repeat it)
    help_request: str | None = None  # the sub-agent is blocked: what it needs from another specialist
    helps_task_id: int | None = None  # this task answers that (blocked) task's help_request
    user_question: str | None = None  # blocked, and the Manager asked the user this in the chat
    created_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None


class ChatMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    thread_id: str = Field(index=True)  # Manager thread id
    role: str  # "user" | "manager" | "agent"
    content: str
    agent_id: int | None = Field(default=None, foreign_key="agent.id")  # set for sub-agent messages
    todo_id: int | None = None  # tasklist item the message is about / belongs to
    created_at: datetime = Field(default_factory=_now)


class TodoStatus(str, Enum):
    todo = "todo"
    in_progress = "in_progress"  # set automatically when work is delegated
    review = "review"  # sub-agent finished and the Manager checked it: waiting for the user's approval
    done = "done"  # set only by the user, via approve


class Todo(SQLModel, table=True):
    """One item of a conversation's tasklist, owned by the Manager."""

    id: int | None = Field(default=None, primary_key=True)
    thread_id: str = Field(index=True)
    title: str  # short heading shown in the list
    description: str = ""  # longer explanation, shown when the item is opened
    status: TodoStatus = TodoStatus.todo
    summary: str | None = None  # what the sub-agent reported when this item was completed
    task_id: int | None = Field(default=None, foreign_key="task.id")  # latest sub-agent Task
    origin_message_id: int | None = None  # the user message that led the Manager to create this item
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Skill(SQLModel, table=True):
    """A capability an agent can be given (by name). Editable at runtime.

    type="builtin": `tool_key` names a Python tool in app/tools.
    type="mcp":     `mcp_config` is a langchain-mcp-adapters connection; all the server's tools load.
    """

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: str = ""
    instructions: str = ""  # extra system-prompt text for agents with this skill
    type: str  # "builtin" | "mcp"
    tool_key: str | None = None
    mcp_config: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=_now)


class Event(SQLModel, table=True):
    """Append-only log of live events. `id` is the position clients resume from."""

    id: int | None = Field(default=None, primary_key=True)
    type: str
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=_now, index=True)


class Approval(SQLModel, table=True):
    """A pause in the Manager's run: it wants to change agents/skills and needs the user's yes.

    `actions` are the tool calls awaiting review ({name, args, description}); `decisions` are the
    user's answers, in the same order. The paused run itself lives in the LangGraph checkpoint.
    """

    id: int | None = Field(default=None, primary_key=True)
    thread_id: str = Field(index=True)
    actions: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    status: str = "pending"  # "pending" | "resolved"
    decisions: list[dict] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=_now)
    resolved_at: datetime | None = None
