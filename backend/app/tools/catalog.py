"""Every tool the agent may call."""

from app.tools.analytics import analytics_tools
from app.tools.export import EXPORT_TOOLS
from app.tools.life_logging import life_logging_tools
from app.tools.memory import MEMORY_TOOLS
from app.tools.people import people_tools
from app.tools.planning import planning_tools
from app.tools.registry import ToolRegistry
from app.tools.reports import report_tools
from app.tools.turns import TURN_TOOLS
from app.tools.vault import VAULT_TOOLS


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in [
        *life_logging_tools(),
        *MEMORY_TOOLS,
        *people_tools(),
        *planning_tools(),
        *report_tools(),
        *analytics_tools(),
        *VAULT_TOOLS,
        *EXPORT_TOOLS,
        *TURN_TOOLS,
    ]:
        registry.register(tool)
    return registry
