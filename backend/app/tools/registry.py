"""Tool registry: the only way the model can read or change data.

Each tool has a strict Pydantic argument model. Arguments from the model are validated
before anything runs; validation and domain errors are returned to the model as a
tool result so it can correct itself, never raised to the user.
"""

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import DomainError

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    """Per-turn state shared by the tools of one agent run."""

    db: Session
    user_message: str
    # Journal entry holding this turn's raw message, once one exists.
    journal_entry_id: uuid.UUID | None = None
    # Records created in this turn: (model class, id), used to link them to the journal entry.
    created: list[tuple[type, uuid.UUID]] = field(default_factory=list)
    # The model, for tools that write report prose. None in contexts without one.
    llm: Any = None


Handler = Callable[[ToolContext, Any], Any]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Handler

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": simplify_schema(self.args_model.model_json_schema()),
            },
        }


@dataclass
class ToolResult:
    name: str
    ok: bool
    payload: dict[str, Any]

    def to_message_content(self) -> str:
        return json.dumps(self.payload, default=_json_default, ensure_ascii=False)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool {tool.name}")
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def execute(self, ctx: ToolContext, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(name, False, {"ok": False, "error": f"unknown tool '{name}'"})
        try:
            args = tool.args_model.model_validate(arguments)
        except ValidationError as exc:
            return ToolResult(name, False, {"ok": False, "error": _format_validation(exc)})
        try:
            result = tool.handler(ctx, args)
        except DomainError as exc:
            ctx.db.rollback()
            return ToolResult(name, False, {"ok": False, "error": str(exc)})
        except Exception:
            ctx.db.rollback()
            # Type only: exception text may contain user content.
            logger.exception("Tool %s failed", name)
            return ToolResult(name, False, {"ok": False, "error": "internal error"})
        return ToolResult(name, True, {"ok": True, **result})


def _format_validation(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors(include_url=False, include_input=False):
        loc = ".".join(str(p) for p in err["loc"]) or "arguments"
        parts.append(f"{loc}: {err['msg']}")
    return "invalid arguments: " + "; ".join(parts)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        # Show the model local wall-clock time, not UTC.
        return value.astimezone(get_settings().tz).isoformat(timespec="minutes")
    if isinstance(value, Decimal | uuid.UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"not serializable: {type(value).__name__}")


def simplify_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make Pydantic JSON schema friendlier to small models.

    Inlines $defs, drops titles, and collapses ``anyOf: [X, null]`` into ``X``.
    """
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return walk(dict(defs[node["$ref"].split("/")[-1]]))
        # "title" is Pydantic metadata, except inside "properties", where it can be a
        # real field name (e.g. a reminder's title).
        node = {
            k: ({name: walk(sub) for name, sub in v.items()} if k == "properties" else walk(v))
            for k, v in node.items()
            if k != "title"
        }
        if "anyOf" in node:
            options = [o for o in node["anyOf"] if o.get("type") != "null"]
            if len(options) == 1:
                merged = {**options[0], **{k: v for k, v in node.items() if k != "anyOf"}}
                if "default" in merged and merged["default"] is None:
                    del merged["default"]
                return merged
            # Decimal fields: accept a number (a string also validates).
            if {o.get("type") for o in options} == {"number", "string"}:
                rest = {k: v for k, v in node.items() if k != "anyOf"}
                return {"type": "number", **rest}
        return node

    return walk(schema)
