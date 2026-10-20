"""Skills live in the DB (table `skill`) and are editable at runtime via /api/skills.

An agent's `skills` is a list of skill NAMES. `load_skills` resolves them to LangChain tools
fresh on every task, so edits apply to the next run.
"""
import logging

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models import Skill
from ..tools import BUILTIN_TOOLS

log = logging.getLogger(__name__)


async def seed_skills(session: AsyncSession) -> None:
    """Create a default Skill row for each built-in tool that has none (never overwrites edits)."""
    existing = {s.name for s in (await session.exec(select(Skill))).all()}
    for key, tool in BUILTIN_TOOLS.items():
        if key not in existing:
            session.add(Skill(name=key, description=tool.description, type="builtin", tool_key=key))
    await session.commit()


def validate_skill(skill: Skill) -> str | None:
    """Return an error message if the skill definition is unusable, else None."""
    if skill.type == "builtin":
        if skill.tool_key not in BUILTIN_TOOLS:
            return f"Unknown tool_key {skill.tool_key!r}. Available: {sorted(BUILTIN_TOOLS)}"
    elif skill.type == "mcp":
        if not skill.mcp_config or "transport" not in skill.mcp_config:
            return "mcp skills need mcp_config with a 'transport' (stdio | streamable_http | ...)"
    else:
        return "type must be 'builtin' or 'mcp'"
    return None


async def unknown_skills(session: AsyncSession, names: list[str]) -> list[str]:
    known = {s.name for s in (await session.exec(select(Skill))).all()}
    return [n for n in names if n not in known]


async def load_skills(session: AsyncSession, names: list[str]) -> tuple[list[BaseTool], str]:
    """Resolve skill names to (LangChain tools, extra prompt text). Broken skills are skipped."""
    if not names:
        return [], ""
    rows = {s.name: s for s in (await session.exec(select(Skill).where(Skill.name.in_(names)))).all()}

    tools: list[BaseTool] = []
    notes: list[str] = []
    for name in names:
        sk = rows.get(name)
        if sk is None:
            log.warning("Unknown skill %r; skipping", name)
            continue
        if sk.type == "builtin" and sk.tool_key in BUILTIN_TOOLS:
            tools.append(BUILTIN_TOOLS[sk.tool_key])
            notes.append(f"- {sk.name}: {sk.description} {sk.instructions}".strip())
        elif sk.type == "mcp" and sk.mcp_config:
            try:
                server_tools = await MultiServerMCPClient({sk.name: sk.mcp_config}).get_tools()
            except Exception:  # noqa: BLE001 - one dead server must not fail the task
                log.exception("MCP skill %r failed to load; skipping", sk.name)
                continue
            tools += server_tools
            notes.append(
                f"- {sk.name} (MCP tools: {', '.join(t.name for t in server_tools)}): "
                f"{sk.description} {sk.instructions}".strip()
            )
        else:
            log.warning("Skill %r is misconfigured; skipping", name)

    prompt = "\n\nYou can use these skills (tools):\n" + "\n".join(notes) if notes else ""
    return tools, prompt
