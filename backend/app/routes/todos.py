from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from ..db import get_session
from ..models import Todo
from ..schemas import TodoCreate, TodoUpdate
from ..services import todos

router = APIRouter(tags=["todos"])


@router.get("/threads/{thread_id}/todos", response_model=list[Todo])
async def list_todos(thread_id: str, session: AsyncSession = Depends(get_session)):
    return await todos.list_todos(session, thread_id)


@router.post("/threads/{thread_id}/todos", response_model=Todo, status_code=201)
async def add_todo(thread_id: str, body: TodoCreate, session: AsyncSession = Depends(get_session)):
    return await todos.add_todo(session, thread_id, body.title)


@router.patch("/todos/{todo_id}", response_model=Todo)
async def rename_todo(todo_id: int, body: TodoUpdate, session: AsyncSession = Depends(get_session)):
    todo = await todos.get_todo(session, todo_id)
    if not todo:
        raise HTTPException(404, "Todo not found")
    return await todos.update_todo(session, todo, title=body.title)


@router.delete("/todos/{todo_id}", status_code=204)
async def remove_todo(todo_id: int, session: AsyncSession = Depends(get_session)):
    todo = await todos.get_todo(session, todo_id)
    if not todo:
        raise HTTPException(404, "Todo not found")
    await todos.remove_todo(session, todo)
