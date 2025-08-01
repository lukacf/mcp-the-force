"""Logging system setup using VictoriaLogs via non-blocking queue handler."""

import logging
import os
import sys
import uuid
import queue
import logging.handlers
import atexit
from pathlib import Path
from ..config import get_settings
from .handlers import TimeoutLokiHandler

# Global instance ID - set once during logging setup
_INSTANCE_ID: str | None = None


def generate_instance_id() -> str:
    """Generate semantic instance ID based on runtime context."""
    project = Path.cwd().name  # Project name from current directory
    is_container = Path("/.dockerenv").exists()  # Docker container detection
    context = "test" if is_container else "dev"  # Simple context distinction
    session = str(uuid.uuid4())[:8]  # Unique session identifier

    return f"{project}_{context}_{session}"


def get_instance_id() -> str | None:
    """Get the current instance ID.

    Returns None if logging hasn't been set up yet.
    """
    return _INSTANCE_ID


def setup_logging():
    """Initialize VictoriaLogs-based logging."""
    settings = get_settings()

    # Get the root logger for the entire mcp_the_force package
    app_logger = logging.getLogger("mcp_the_force")
    app_logger.setLevel(settings.logging.level)
    # Allow child loggers to use parent handlers
    app_logger.propagate = False

    if app_logger.hasHandlers():
        app_logger.handlers.clear()

    # Check if VictoriaLogs is disabled
    if not settings.logging.victoria_logs_enabled:
        # Add stderr handler so we can still see critical messages
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.WARNING)
        stderr_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        app_logger.addHandler(stderr_handler)
        app_logger.warning("VictoriaLogs DISABLED via configuration")
        return

    # Generate instance ID once for this session
    global _INSTANCE_ID
    _INSTANCE_ID = generate_instance_id()
    instance_id = _INSTANCE_ID

    # Set up non-blocking VictoriaLogs handler using queue with timeout protection
    try:
        # Create a queue for non-blocking logging
        log_queue = queue.Queue(-1)  # -1 means unlimited size

        # Create our custom handler with timeout
        victoria_logs_url = settings.logging.victoria_logs_url

        # Debug log the URL in E2E mode
        if settings.dev.ci_e2e:
            print(
                f"E2E: VictoriaLogs URL configured as: {victoria_logs_url}",
                file=sys.stderr,
            )

        loki_handler = TimeoutLokiHandler(
            url=f"{victoria_logs_url}/insert/loki/api/v1/push?_stream_fields=app,instance_id",
            tags={
                "app": settings.logging.loki_app_tag,
                "instance_id": instance_id,
                "project": settings.logging.project_path or os.getcwd(),
            },
            version="1",
            timeout=10.0,  # 10 second timeout to prevent stale connection hangs
        )
        loki_handler.setLevel(settings.logging.level)

        # Create the queue handler
        queue_handler = logging.handlers.QueueHandler(log_queue)

        # Create and start the queue listener
        queue_listener = logging.handlers.QueueListener(
            log_queue, loki_handler, respect_handler_level=True
        )
        queue_listener.start()

        # Store listener for cleanup
        app_logger._queue_listener = queue_listener

        # Register cleanup on exit
        atexit.register(queue_listener.stop)

        app_logger.addHandler(queue_handler)
        app_logger.info(
            f"Non-blocking VictoriaLogs handler configured for instance {instance_id} with 10s timeout"
        )
    except Exception as e:
        # Don't block server startup if VictoriaLogs is unavailable
        print(
            f"Warning: Could not set up VictoriaLogs queue handler: {e}",
            file=sys.stderr,
        )
        import traceback

        traceback.print_exc()

    # CRITICAL: Also add stderr handler for MCP servers (stdout must stay clean for JSON-RPC)
    # TESTING: Commenting out stderr handler to test if it's causing hangs
    # stderr_handler = logging.StreamHandler(sys.stderr)
    # stderr_handler.setFormatter(
    #     logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    # )
    # app_logger.addHandler(stderr_handler)

    app_logger.info(
        "Logging initialized with VictoriaLogs only (stderr disabled for testing)"
    )


def shutdown_logging():
    """Stop the queue listener if it exists."""
    app_logger = logging.getLogger("mcp_the_force")
    if hasattr(app_logger, "_queue_listener"):
        app_logger._queue_listener.stop()
        delattr(app_logger, "_queue_listener")
