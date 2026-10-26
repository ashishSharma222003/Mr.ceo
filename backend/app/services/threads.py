"""Manager conversations and which sub-agents each one may use (its team)."""
import uuid
from datetime import datetime, timezone

from sqlmodel import or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models import Agent, ChatMessage, Thread, Todo

TEAMS = ("shared", "own")


async def create(session: AsyncSession, team: str = "shared", thread_id: str | None = None) -> Thread:
    thread = Thread(id=thread_id or uuid.uuid4().hex, team=team)
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    return thread


async def ensure(session: AsyncSession, thread_id: str) -> Thread:
    """The thread, created as a shared-team chat if it doesn't exist yet."""
    return await session.get(Thread, thread_id) or await create(session, thread_id=thread_id)


def _team_filter(thread: Thread | None, thread_id: str):
    own = Agent.thread_id == thread_id
    return own if thread and thread.team == "own" else or_(Agent.thread_id.is_(None), own)


async def team_agents(session: AsyncSession, thread_id: str) -> list[Agent]:
    thread = await session.get(Thread, thread_id)
    return list((await session.exec(select(Agent).where(_team_filter(thread, thread_id)).order_by(Agent.id))).all())


def in_team(thread: Thread | None, agent: Agent) -> bool:
    if thread and thread.team == "own":
        return agent.thread_id == thread.id
    return agent.thread_id is None or agent.thread_id == (thread.id if thread else None)


def owner_of_new_agent(thread: Thread | None) -> str | None:
    """Agents made in an own-team chat stay in it; elsewhere they join the shared library."""
    return thread.id if thread and thread.team == "own" else None


async def touch(session: AsyncSession, thread: Thread, first_message: str | None = None) -> None:
    if first_message and thread.title == "New chat":
        thread.title = " ".join(first_message.split())[:60] or thread.title
    thread.updated_at = datetime.now(timezone.utc)
    session.add(thread)
    await session.commit()


async def adopt_legacy(session: AsyncSession) -> None:
    """Conversations from before threads were stored get a row (shared team, titled by their first message)."""
    have = set((await session.exec(select(Thread.id))).all())
    ids = set((await session.exec(select(ChatMessage.thread_id).distinct())).all())
    ids |= set((await session.exec(select(Todo.thread_id).distinct())).all())
    for tid in sorted(ids - have):
        first = (
            await session.exec(
                select(ChatMessage)
                .where(ChatMessage.thread_id == tid, ChatMessage.role == "user", ChatMessage.agent_id.is_(None))
                .order_by(ChatMessage.id)
            )
        ).first()
        last = (await session.exec(select(ChatMessage).where(ChatMessage.thread_id == tid).order_by(ChatMessage.id.desc()))).first()
        thread = Thread(id=tid)
        if first:
            thread.title = " ".join(first.content.split())[:60]
        if last:
            thread.created_at = thread.updated_at = last.created_at
        session.add(thread)
    await session.commit()
