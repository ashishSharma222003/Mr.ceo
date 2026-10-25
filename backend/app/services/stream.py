"""Token streaming for agent runs.

Tokens go to the browser as live-only SSE events (never stored: one DB row per token would be
wasteful, and a half-written reply is worthless after a reconnect). The finished reply is still
saved as a normal ChatMessage, and clients reload it when the run ends.

Events (all carry `run`, plus the caller's `meta`):
  <event>      {text, msg}  a token. `msg` is the id of the LLM message it belongs to; when it
                            changes (e.g. after a tool call) the client starts the text over.
  stream.end   {}           no more tokens for this run
"""
import asyncio
import uuid

from . import events

_TEXT_NODES = {"model", "agent"}  # LangGraph node names that call the LLM ("agent" in older versions)


def chunk_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # content blocks -> plain text (skips thinking / tool-use blocks)
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


async def stream_agent(runnable, inputs: dict, config: dict, event: str, meta: dict):
    """Run a LangChain agent, publishing its tokens. Returns the final message content."""
    run = uuid.uuid4().hex
    final = None
    try:
        async for mode, data in runnable.astream(inputs, config=config, stream_mode=["messages", "values"]):
            if mode == "values":
                final = data
                continue
            chunk, info = data
            if info.get("langgraph_node") not in _TEXT_NODES:
                continue
            if text := chunk_text(chunk.content):
                await events.publish(event, {**meta, "run": run, "msg": chunk.id, "text": text}, persist=False)
    finally:
        await events.publish("stream.end", {**meta, "run": run}, persist=False)
    return final["messages"][-1].content


async def stream_text(text: str, event: str, meta: dict, delay: float = 0.08) -> None:
    """Fake mode: stream a canned reply word by word so the UI can be tested without an LLM."""
    run = uuid.uuid4().hex
    try:
        for word in text.split(" "):
            await events.publish(event, {**meta, "run": run, "msg": run, "text": word + " "}, persist=False)
            await asyncio.sleep(delay)
    finally:
        await events.publish("stream.end", {**meta, "run": run}, persist=False)
