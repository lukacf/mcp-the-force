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

    # Check if we should disable VictoriaLogs
    if os.getenv("DISABLE_VICTORIA_LOGS", "").lower() in ("1", "true", "yes"):
        # Add stderr handler so we can still see critical messages
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.WARNING)
        stderr_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        app_logger.addHandler(stderr_handler)
        app_logger.warning("VictoriaLogs DISABLED via DISABLE_VICTORIA_LOGS env var")
        return

    # Generate instance ID once for this session
    instance_id = generate_instance_id()

    # Set up non-blocking VictoriaLogs handler using queue with timeout protection
    try:
        # Create a queue for non-blocking logging
        log_queue = queue.Queue(-1)  # -1 means unlimited size

        # Create our custom handler with timeout
        # Allow overriding the VictoriaLogs URL for E2E tests
        victoria_logs_url = os.getenv("VICTORIA_LOGS_URL", "http://localhost:9428")

        # Debug log the URL in E2E mode
        if os.getenv("CI_E2E") == "1":
            print(
                f"E2E: VictoriaLogs URL configured as: {victoria_logs_url}",
                file=sys.stderr,
            )

        loki_handler = TimeoutLokiHandler(
            url=f"{victoria_logs_url}/insert/loki/api/v1/push?_stream_fields=app,instance_id",
            tags={
                "app": os.getenv("LOKI_APP_TAG", "mcp-second-brain"),
                "instance_id": instance_id,
                "project": os.getenv("MCP_PROJECT_PATH", os.getcwd()),
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
    app_logger = logging.getLogger("mcp_second_brain")
    if hasattr(app_logger, "_queue_listener"):
        app_logger._queue_listener.stop()
        delattr(app_logger, "_queue_listener")
