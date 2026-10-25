from sqlalchemy import inspect, text
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from . import models  # noqa: F401 - registers the tables on SQLModel.metadata
from .config import settings

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(conn) -> None:
    """create_all never alters existing tables; add columns introduced since the DB was made."""
    insp = inspect(conn)
    for table in SQLModel.metadata.sorted_tables:
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in have:
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col.type.compile(conn.dialect)}'
                arg = getattr(col.default, "arg", None)
                if isinstance(arg, bool):  # NOT NULL columns need a default
                    ddl += f" DEFAULT {int(arg)}"
                elif isinstance(arg, (int, str)):
                    ddl += " DEFAULT '" + str(arg).replace("'", "''") + "'"
                conn.execute(text(ddl))
                if (table.name, col.name) == ("task", "notified"):
                    # Tasks that ended before this column existed were handled back then.
                    conn.execute(text("UPDATE task SET notified = 1"))


async def get_session():
    async with SessionLocal() as session:
        yield session
