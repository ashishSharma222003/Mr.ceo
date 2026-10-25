"""Tasklist (todos) per Manager conversation.

Users can add / edit / remove items (REST). The Manager sends a finished item to review
(submit_for_review); only the user can approve it (done). Every change is pushed over SSE.
"""
from datetime import datetime, timezone

from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models import Task, TaskStatus, Todo, TodoStatus
from . import events


def _touch(todo: Todo) -> None:
    todo.updated_at = datetime.now(timezone.utc)


async def list_todos(session: AsyncSession, thread_id: str) -> list[Todo]:
    q = select(Todo).where(Todo.thread_id == thread_id).order_by(Todo.id)
    return list((await session.exec(q)).all())


async def add_todo(
    session: AsyncSession,
    thread_id: str,
    title: str,
    status: TodoStatus = TodoStatus.todo,
    task_id: int | None = None,
    description: str = "",
) -> Todo:
    todo = Todo(thread_id=thread_id, title=title, description=description, status=status, task_id=task_id)
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    await events.publish("todo.updated", todo.model_dump())
    return todo


async def get_todo(session: AsyncSession, todo_id: int, thread_id: str | None = None) -> Todo | None:
    todo = await session.get(Todo, todo_id)
    if todo and thread_id is not None and todo.thread_id != thread_id:
        return None  # an item from another conversation is invisible
    return todo


async def update_todo(
    session: AsyncSession,
    todo: Todo,
    title: str | None = None,
    status: TodoStatus | None = None,
    task_id: int | None = None,
    description: str | None = None,
    summary: str | None = None,
) -> Todo:
    if title is not None:
        todo.title = title
    if description is not None:
        todo.description = description
    if summary is not None:
        todo.summary = summary
    if status is not None:
        todo.status = status
    if task_id is not None:
        todo.task_id = task_id
    _touch(todo)
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    await events.publish("todo.updated", todo.model_dump())
    return todo


async def _report(session: AsyncSession, todo: Todo) -> str | None:
    task = await session.get(Task, todo.task_id) if todo.task_id else None
    return (task.summary or task.result) if task and task.status == TaskStatus.done else None


async def submit_for_review(session: AsyncSession, todo: Todo) -> Todo:
    """The Manager's verdict: work looks done. Keeps the sub-agent's report and waits for the user."""
    return await update_todo(session, todo, status=TodoStatus.review, summary=await _report(session, todo))


async def complete_todo(session: AsyncSession, todo: Todo) -> Todo:
    """The user's approval: mark done. The report stays on the item, so the completed list shows what was done."""
    return await update_todo(session, todo, status=TodoStatus.done, summary=await _report(session, todo))


async def remove_todo(session: AsyncSession, todo: Todo) -> None:
    data = todo.model_dump()
    await session.delete(todo)
    await session.commit()
    await events.publish("todo.deleted", data)


async def todo_for_task(session: AsyncSession, task_id: int) -> Todo | None:
    q = select(Todo).where(Todo.task_id == task_id)
    return (await session.exec(q)).first()


async def delete_thread_todos(session: AsyncSession, thread_id: str) -> None:
    await session.exec(delete(Todo).where(Todo.thread_id == thread_id))
    await session.commit()


def format_tasklist(todos: list[Todo]) -> str:
    if not todos:
        return "(empty)"
    return "\n".join(
        f"Task #{t.id} [{t.status.value}] {t.title}"
        + (f" - {t.description[:160]}" if t.description and t.status != TodoStatus.done else "")
        for t in todos
    )
