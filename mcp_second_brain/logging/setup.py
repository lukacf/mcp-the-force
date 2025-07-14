"""Logging system setup using VictoriaLogs via logging-loki."""

import logging
import os
import uuid
from pathlib import Path
from logging_loki import LokiHandler
from ..config import get_settings


def generate_instance_id() -> str:
    """Generate semantic instance ID based on runtime context."""
    project = Path.cwd().name  # Project name from current directory
    is_container = Path("/.dockerenv").exists()  # Docker container detection
    context = "test" if is_container else "dev"  # Simple context distinction
    session = str(uuid.uuid4())[:8]  # Unique session identifier

    return f"{project}_{context}_{session}"


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
            "instance_id": generate_instance_id(),  # Semantic instance ID
            "project": os.getenv("MCP_PROJECT_PATH", os.getcwd()),
        },
        version="1",
    )

    app_logger.addHandler(loki_handler)

    # CRITICAL: Also add stderr handler for MCP servers (stdout must stay clean for JSON-RPC)
    import sys

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    app_logger.addHandler(stderr_handler)

    app_logger.info("Logging initialized with VictoriaLogs and stderr")


def shutdown_logging():
    """No-op shutdown for compatibility."""
    pass
