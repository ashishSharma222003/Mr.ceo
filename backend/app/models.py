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


class Agent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    role_prompt: str
    model: str = "claude-sonnet-5-5"
    skills: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=_now)


class Task(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    agent_id: int = Field(foreign_key="agent.id")
    instruction: str
    thread_id: str | None = None  # Manager conversation this task belongs to
    status: TaskStatus = TaskStatus.pending
    result: str | None = None
    created_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None


class ChatMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    thread_id: str = Field(index=True)  # Manager thread id
    role: str  # "user" | "manager" | "agent"
    content: str
    agent_id: int | None = Field(default=None, foreign_key="agent.id")  # set for sub-agent messages
    created_at: datetime = Field(default_factory=_now)
