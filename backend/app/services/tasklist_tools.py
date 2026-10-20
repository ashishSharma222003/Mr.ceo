"""Tasklist tools given to the Manager (LangChain tools). Each opens its own DB session so
parallel tool calls never share one."""
from langchain_core.tools import StructuredTool

from ..db import SessionLocal
from ..models import TodoStatus
from . import todos


def build_tasklist_tools(thread_id: str) -> list[StructuredTool]:
    async def get_tasklist() -> str:
        async with SessionLocal() as s:
            return todos.format_tasklist(await todos.list_todos(s, thread_id))

    async def add_todo(title: str) -> str:
        async with SessionLocal() as s:
            t = await todos.add_todo(s, thread_id, title)
            return f"Added todo #{t.id}."

    async def rename_todo(todo_id: int, title: str) -> str:
        async with SessionLocal() as s:
            t = await todos.get_todo(s, todo_id, thread_id)
            if not t:
                return f"No todo #{todo_id} in this conversation."
            await todos.update_todo(s, t, title=title)
            return f"Renamed todo #{todo_id}."

    async def remove_todo(todo_id: int) -> str:
        async with SessionLocal() as s:
            t = await todos.get_todo(s, todo_id, thread_id)
            if not t:
                return f"No todo #{todo_id} in this conversation."
            await todos.remove_todo(s, t)
            return f"Removed todo #{todo_id}."

    async def complete_todo(todo_id: int) -> str:
        async with SessionLocal() as s:
            t = await todos.get_todo(s, todo_id, thread_id)
            if not t:
                return f"No todo #{todo_id} in this conversation."
            await todos.update_todo(s, t, status=TodoStatus.done)
            return f"Todo #{todo_id} marked done."

    mk = StructuredTool.from_function
    return [
        mk(coroutine=get_tasklist, name="get_tasklist",
           description="Show this conversation's tasklist (ids, status, titles)."),
        mk(coroutine=add_todo, name="add_todo",
           description="Add an item to the tasklist. Returns its id; pass it as todo_id when delegating."),
        mk(coroutine=rename_todo, name="rename_todo", description="Change a todo's title."),
        mk(coroutine=remove_todo, name="remove_todo", description="Remove a todo from the tasklist."),
        mk(coroutine=complete_todo, name="complete_todo",
           description="Mark a todo done. Only call this after a sub-agent reported it finished "
                       "and you checked the result."),
    ]
