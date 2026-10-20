"""Tasklist (todos) per Manager conversation.

Users can add / rename / remove items (REST). Only the Manager marks items done, via its
tasklist tools, after a sub-agent reports back. Every change is pushed over SSE.
"""
from datetime import datetime, timezone

from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models import Todo, TodoStatus
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
) -> Todo:
    todo = Todo(thread_id=thread_id, title=title, status=status, task_id=task_id)
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    events.publish("todo.updated", todo.model_dump())
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
) -> Todo:
    if title is not None:
        todo.title = title
    if status is not None:
        todo.status = status
    if task_id is not None:
        todo.task_id = task_id
    _touch(todo)
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    events.publish("todo.updated", todo.model_dump())
    return todo


async def remove_todo(session: AsyncSession, todo: Todo) -> None:
    data = todo.model_dump()
    await session.delete(todo)
    await session.commit()
    events.publish("todo.deleted", data)


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
        f"#{t.id} [{t.status.value}] {t.title}" + (f" (sub-agent task #{t.task_id})" if t.task_id else "")
        for t in todos
    )
