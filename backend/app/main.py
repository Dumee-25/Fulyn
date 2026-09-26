import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.llm import LLMUnavailableError
from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import DomainError, NotFoundError
from app.core.logging import configure_logging
from app.core.version import __version__

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(title=settings.app_name, version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(LLMUnavailableError)
    async def llm_unavailable(request: Request, exc: LLMUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def sanitized_error(request: Request, exc: Exception) -> JSONResponse:
        # Log the type and path only; exception messages may echo user content.
        logger.error("Unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.include_router(api_router)
    return app


app = create_app()
