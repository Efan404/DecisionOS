from __future__ import annotations

import logging
import os

from app.core.request_logging import get_request_id

_DEFAULT_LEVEL = "INFO"
_FORMAT = "%(asctime)s %(levelname)s [%(name)s] [request_id=%(request_id)s] %(message)s"


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def setup_logging() -> None:
    level_name = os.getenv("DECISIONOS_LOG_LEVEL", _DEFAULT_LEVEL).strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in root_logger.handlers:
        if getattr(handler, "_decisionos_handler", False):
            handler.setLevel(level)
            return

    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.addFilter(_RequestIdFilter())
    setattr(handler, "_decisionos_handler", True)
    root_logger.addHandler(handler)
