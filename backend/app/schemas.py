from pydantic import BaseModel

from .models import Task


class AgentCreate(BaseModel):
    name: str
    role_prompt: str
    model: str = "claude-sonnet-5-5"
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
