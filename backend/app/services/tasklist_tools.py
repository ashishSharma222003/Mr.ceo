"""Tasklist tools given to the Manager (LangChain tools). Each opens its own DB session so
parallel tool calls never share one."""
from langchain_core.tools import StructuredTool

from ..db import SessionLocal
from . import todos


def build_tasklist_tools(thread_id: str) -> list[StructuredTool]:
    async def get_tasklist() -> str:
        async with SessionLocal() as s:
            return todos.format_tasklist(await todos.list_todos(s, thread_id))

    async def add_todo(title: str, description: str = "") -> str:
        async with SessionLocal() as s:
            t = await todos.add_todo(s, thread_id, title, description=description)
            return f"Added Task #{t.id}."

    async def edit_todo(todo_id: int, title: str | None = None, description: str | None = None) -> str:
        async with SessionLocal() as s:
            t = await todos.get_todo(s, todo_id, thread_id)
            if not t:
                return f"No Task #{todo_id} in this conversation."
            await todos.update_todo(s, t, title=title, description=description)
            return f"Updated Task #{todo_id}."

    async def remove_todo(todo_id: int) -> str:
        async with SessionLocal() as s:
            t = await todos.get_todo(s, todo_id, thread_id)
            if not t:
                return f"No Task #{todo_id} in this conversation."
            await todos.remove_todo(s, t)
            return f"Removed Task #{todo_id}."

    async def submit_for_review(todo_id: int) -> str:
        async with SessionLocal() as s:
            t = await todos.get_todo(s, todo_id, thread_id)
            if not t:
                return f"No Task #{todo_id} in this conversation."
            await todos.submit_for_review(s, t)
            return f"Task #{todo_id} is now waiting for the user's approval."

    mk = StructuredTool.from_function
    return [
        mk(coroutine=get_tasklist, name="get_tasklist",
           description="Show this conversation's tasklist (ids, status, titles)."),
        mk(coroutine=add_todo, name="add_todo",
           description="Add an item to the tasklist: a short `title` (heading) and a `description` "
                       "saying what the work involves. Returns its id; pass it as todo_id when delegating."),
        mk(coroutine=edit_todo, name="edit_todo", description="Change a todo's title and/or description (its requirements)."),
        mk(coroutine=remove_todo, name="remove_todo", description="Remove a todo from the tasklist."),
        mk(coroutine=submit_for_review, name="submit_for_review",
           description="Tell the user a todo looks finished so they can approve it (only the user can mark "
                       "it done). The sub-agent's report is saved on it automatically. Only call this after "
                       "a sub-agent reported it finished and you checked the result."),
    ]
