"""Logging system setup using VictoriaLogs via logging-loki."""

import logging
import os
from logging_loki import LokiHandler
from ..config import get_settings


def setup_logging():
    """Initialize VictoriaLogs-based logging."""
    settings = get_settings()

    app_logger = logging.getLogger("mcp_second_brain")
    app_logger.setLevel(settings.logging.level)
    app_logger.propagate = False

    if app_logger.hasHandlers():
        app_logger.handlers.clear()

    if not settings.logging.developer_mode.enabled:
        app_logger.addHandler(logging.NullHandler())
        return

    # Use standard logging-loki handler
    loki_handler = LokiHandler(
        url="http://localhost:9428/insert/loki/api/v1/push?_stream_fields=app,instance_id",
        tags={
            "app": "mcp-second-brain",
            "instance_id": settings.instance_id,
            "project": os.getenv("MCP_PROJECT_PATH", os.getcwd()),
        },
        version="1",
    )

    app_logger.addHandler(loki_handler)
    app_logger.info("Logging initialized with VictoriaLogs")


def shutdown_logging():
    """No-op shutdown for compatibility."""
    pass
