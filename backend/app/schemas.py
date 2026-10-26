from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from .models import Task, Todo


class AgentCreate(BaseModel):
    name: str
    role_prompt: str
    model: str | None = None  # empty = DEFAULT_AGENT_MODEL / provider default
    skills: list[str] = []
    thread_id: str | None = None  # set: private to that chat (its own team); omit for the shared library


class AgentUpdate(BaseModel):
    """All fields optional: only the ones sent are changed."""

    name: str | None = None
    role_prompt: str | None = None
    model: str | None = None
    skills: list[str] | None = None


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None  # omit to start a new conversation
    todo_id: int | None = None  # the task this message is about (e.g. a change request)


class ChatResponse(BaseModel):
    thread_id: str
    reply: str
    tasks: list[Task]
    todos: list[Todo] = []


class ThreadOut(BaseModel):
    id: str
    title: str
    team: str
    open_tasks: int = 0  # tasklist items not done yet
    created_at: datetime
    updated_at: datetime


class ThreadCreate(BaseModel):
    team: Literal["shared", "own"] = "shared"  # use the existing sub-agents, or start with none


class SkillCreate(BaseModel):
    name: str
    description: str = ""
    instructions: str = ""
    type: str  # "builtin" | "mcp"
    tool_key: str | None = None
    mcp_config: dict | None = None


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    type: str | None = None
    tool_key: str | None = None
    mcp_config: dict | None = None


class TodoCreate(BaseModel):
    title: str
    description: str = ""


class TodoUpdate(BaseModel):
    """Users may edit the text only. Completion belongs to the Manager."""

    title: str | None = None
    description: str | None = None


class DecisionIn(BaseModel):
    """The user's answer to one pending tool call, in the order the calls were listed."""

    type: Literal["approve", "edit", "reject"]
    edited_args: dict | None = None  # for "edit": the full replacement arguments
    message: str | None = None  # for "reject": why, shown to the Manager


class ApprovalResolve(BaseModel):
    decisions: list[DecisionIn]
