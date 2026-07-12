"""Structured logging configuration for the agent service.

One stderr handler on the root logger, in a grep-friendly single-line format.
Uvicorn keeps its own loggers non-propagating, so app loggers configured here
never duplicate its lines. Modules log via `logging.getLogger(__name__)`.
"""

from __future__ import annotations

import logging

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s  %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: int = logging.INFO) -> None:
    """Attach one formatted stderr handler to the root logger, exactly once.

    Idempotent so repeated imports (uvicorn workers, tests importing main) never
    stack duplicate handlers.
    """
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))
    root.addHandler(handler)
    root.setLevel(level)
