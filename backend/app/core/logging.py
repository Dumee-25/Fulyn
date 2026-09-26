import logging

from app.core.config import get_settings


def configure_logging() -> None:
    # Never log request bodies: they may contain journal or vault content.
    logging.basicConfig(
        level=get_settings().log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
