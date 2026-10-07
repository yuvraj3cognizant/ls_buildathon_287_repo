"""
Centralized structured logging.

Every agent/service logs through `get_logger(__name__)` and uses
`log_event(...)` so that log lines are consistent JSON objects that can be
tailed for the Streamlit "Agent Execution Flow" panel as well as CloudWatch.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from src.config.settings import settings

_CONFIGURED = False


def _configure_root() -> None:
    """Attach a stdout handler plus a rotating file handler.

    Streamlit swallows the launching terminal's scrollback, so stdout alone
    makes post-hoc debugging of an agent run impractical. `LOG_FILE` (default
    `logs/app.log`) gives a durable copy; set `LOG_TO_FILE=false` to disable.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if os.getenv("LOG_TO_FILE", "true").lower() not in ("false", "0", "no"):
        log_path = Path(os.getenv("LOG_FILE", "logs/app.log"))
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(
                RotatingFileHandler(
                    log_path, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
                )
            )
        except OSError as exc:  # pragma: no cover - permissions/read-only fs
            print(f"Could not open log file {log_path}: {exc}", file=sys.stderr)

    for handler in handlers:
        handler.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger()
    root.setLevel(settings.log_level)
    root.handlers = handlers
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure_root()
    return logging.getLogger(name)


def new_trace_id() -> str:
    return str(uuid.uuid4())


def log_event(
    logger: logging.Logger,
    *,
    trace_id: str,
    agent: str,
    event: str,
    level: str = "INFO",
    **fields: Any,
) -> None:
    """Emit one structured JSON log line.

    This is the single instrumentation point that also backs the
    Streamlit execution-flow panel (the UI reads the same event shape).
    """
    payload = {
        "ts": time.time(),
        "trace_id": trace_id,
        "agent": agent,
        "event": event,
        **fields,
    }
    line = json.dumps(payload, default=str)
    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn(line)
