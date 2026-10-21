from pydantic import BaseModel

from .models import Task, Todo


class AgentCreate(BaseModel):
    name: str
    role_prompt: str
    model: str | None = None  # empty = DEFAULT_AGENT_MODEL / provider default
    skills: list[str] = []


class AgentUpdate(BaseModel):
    """All fields optional: only the ones sent are changed."""

    name: str | None = None
    role_prompt: str | None = None
    model: str | None = None
    skills: list[str] | None = None


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None  # omit to start a new conversation


class ChatResponse(BaseModel):
    thread_id: str
    reply: str
    tasks: list[Task]
    todos: list[Todo] = []


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


class TodoUpdate(BaseModel):
    """Users may only rename. Completion belongs to the Manager."""

    title: str
