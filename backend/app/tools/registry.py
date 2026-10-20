"""Registry of built-in Python tools. Every entry is a LangChain `StructuredTool`, so it can be
passed straight to `create_agent(tools=[...])`.

Add a tool: create a file in this package, decorate a function with `@builtin_tool(...)`,
and import the file in `__init__.py`. It is then available to attach to a DB Skill
(`type="builtin"`, `tool_key=<name>`).
"""
from typing import Callable

from langchain_core.tools import BaseTool, StructuredTool

BUILTIN_TOOLS: dict[str, BaseTool] = {}


def builtin_tool(name: str, description: str):
    def deco(fn: Callable) -> Callable:
        BUILTIN_TOOLS[name] = StructuredTool.from_function(fn, name=name, description=description)
        return fn

    return deco
