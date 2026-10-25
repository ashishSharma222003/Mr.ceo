"""Shared conversation memory (LangGraph SQLite checkpointer).

Uses the same SQLite file as the app DB (`settings.database_url`), so checkpoints and the
`chatmessage` table live together and survive restarts.

Two kinds of thread live here:
  - Manager thread:   `<thread_id>`            (user <-> Manager)
  - Sub-agent thread: `<thread_id>:<agent_id>:<todo_id>` (Manager <-> one sub-agent, for one tasklist
                      item: reworking an item continues it, other items start with a clean memory)
Agent config (prompt, skills) is NOT stored here; it is read fresh from the DB each run.
"""
import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from sqlmodel.ext.asyncio.session import AsyncSession

from ..config import settings
from ..models import ChatMessage

_conn: aiosqlite.Connection | None = None
_saver: AsyncSqliteSaver | None = None


def _sqlite_path() -> str:
    # "sqlite+aiosqlite:///./mrceo.db" -> "./mrceo.db"
    return settings.database_url.split(":///", 1)[1]


async def init_checkpointer() -> None:
    global _conn, _saver
    _conn = await aiosqlite.connect(_sqlite_path())
    _saver = AsyncSqliteSaver(_conn)
    await _saver.setup()


async def close_checkpointer() -> None:
    global _conn, _saver
    if _conn is not None:
        await _conn.close()
    _conn = _saver = None


def get_checkpointer() -> AsyncSqliteSaver:
    if _saver is None:
        raise RuntimeError("Checkpointer not initialised; call init_checkpointer() at startup")
    return _saver


def agent_thread_id(manager_thread_id: str, agent_id: int, todo_id: int | str) -> str:
    return f"{manager_thread_id}:{agent_id}:{todo_id}"


async def save_message(
    session: AsyncSession,
    thread_id: str,
    role: str,
    content: str,
    agent_id: int | None = None,
    todo_id: int | None = None,
) -> ChatMessage:
    """Persist one chat message (role: user | manager | agent | system)."""
    msg = ChatMessage(thread_id=thread_id, role=role, content=content, agent_id=agent_id, todo_id=todo_id)
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg
