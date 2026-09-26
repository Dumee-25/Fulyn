"""Every tool the agent may call."""

from app.tools.life_logging import life_logging_tools
from app.tools.memory import MEMORY_TOOLS
from app.tools.people import people_tools
from app.tools.planning import planning_tools
from app.tools.registry import ToolRegistry


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in [*life_logging_tools(), *MEMORY_TOOLS, *people_tools(), *planning_tools()]:
        registry.register(tool)
    return registry
