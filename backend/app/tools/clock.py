from datetime import datetime, timezone

from .registry import builtin_tool


@builtin_tool("current_time", "Get the current date and time in UTC.")
def current_time() -> str:
    return datetime.now(timezone.utc).isoformat()
