"""Agent tool pointing the user at their data export."""

from typing import Any

from app.tools.life_logging import ToolArgs
from app.tools.registry import Tool, ToolContext


class ExportArgs(ToolArgs):
    pass


def export_data(ctx: ToolContext, args: ExportArgs) -> dict[str, Any]:
    # Files can't be sent through chat; point to the download links instead.
    return {
        "settings_page": "/settings",
        "downloads": {
            "everything (ZIP, vault excluded)": "/api/export/zip",
            "everything (JSON)": "/api/export/json",
            "expenses (CSV)": "/api/export/expenses.csv",
            "private vault (ZIP, separate)": "/api/export/vault.zip",
        },
    }


EXPORT_TOOLS = [
    Tool(
        "export_data",
        "Tell the user where to download their data (ZIP, JSON, CSV, or the separate vault "
        "export). Exports are downloaded from the Settings page.",
        ExportArgs,
        export_data,
    )
]
