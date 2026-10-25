from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import SessionLocal, init_db
from .services import events, manager
from .services.skills import seed_skills
from .routes import agents, approvals, chat, skills, tasks, todos
from .services.memory import close_checkpointer, init_checkpointer


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await events.prune()
    async with SessionLocal() as session:
        await seed_skills(session)
    await init_checkpointer()
    manager.spawn(manager.recover())  # resume work a restart cut off
    yield
    await close_checkpointer()


app = FastAPI(title="Mr.ceo", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (agents.router, approvals.router, skills.router, tasks.router, todos.router, chat.router):
    app.include_router(r, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
