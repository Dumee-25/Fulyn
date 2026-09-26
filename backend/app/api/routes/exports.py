from typing import Any

from fastapi import APIRouter, Response

from app.api.deps import DbSession
from app.core.config import get_settings
from app.core.time import today_local
from app.core.version import __version__
from app.exports import service

exports_router = APIRouter(prefix="/export", tags=["export"])
settings_router = APIRouter(prefix="/settings", tags=["settings"])


def _download(content: bytes | str, filename: str, media_type: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@exports_router.get("/zip")
def export_zip(db: DbSession) -> Response:
    """Everything except the vault: journal Markdown, CSVs, memories and conversations."""
    return _download(service.build_zip(db), f"fulyn-export-{today_local()}.zip", "application/zip")


@exports_router.get("/vault.zip")
def export_vault(db: DbSession) -> Response:
    """The private vault only. A separate, explicit download."""
    return _download(
        service.build_zip(db, private=True), f"fulyn-vault-{today_local()}.zip", "application/zip"
    )


@exports_router.get("/json")
def export_json(db: DbSession) -> dict[str, Any]:
    return service.full_json(db)


@exports_router.get("/expenses.csv")
def export_expenses(db: DbSession) -> Response:
    return _download(
        service.expenses_csv(db), f"fulyn-expenses-{today_local()}.csv", "text/csv; charset=utf-8"
    )


@settings_router.get("")
def read_settings() -> dict[str, Any]:
    """Current configuration, without secrets. Change it in .env and restart."""
    s = get_settings()
    return {
        "version": __version__,
        "environment": s.app_env,
        "timezone": s.default_timezone,
        "currency": s.default_currency,
        "expense_categories": s.expense_categories,
        "major_purchase_amount": str(s.major_purchase_amount),
        "chat_model": s.ollama_model,
        "embedding_model": s.ollama_embed_model,
        "agent_max_tool_iterations": s.agent_max_tool_iterations,
        "agent_history_messages": s.agent_history_messages,
    }
