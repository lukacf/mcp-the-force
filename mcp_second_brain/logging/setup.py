"""Logging system setup and initialization."""

import os
import logging
import threading
import uuid
import zmq
from typing import Optional

from .server import ZMQLogServer
from .handler import ZMQLogHandler
from ..config import get_settings

_log_server: Optional[ZMQLogServer] = None
_server_thread: Optional[threading.Thread] = None
_zmq_handler: Optional[ZMQLogHandler] = None


def setup_logging():
    """Initialize centralized logging system without polluting stderr."""
    settings = get_settings()

    # Configure ONLY our application logger, not the root logger
    # This prevents third-party libraries (like httpx) from writing to stderr
    app_logger = logging.getLogger("mcp_second_brain")
    app_logger.setLevel(settings.logging.level)
    app_logger.propagate = False  # Critical: prevent propagation to root logger

    # Clear any existing handlers to prevent duplicates
    if app_logger.hasHandlers():
        app_logger.handlers.clear()

    # Developer mode logging
    if not settings.logging.developer_mode.enabled:
        # Add NullHandler to prevent "No handler found" warnings
        app_logger.addHandler(logging.NullHandler())
        return

    global _log_server, _server_thread, _zmq_handler

    port = settings.logging.developer_mode.port

    # CENTRALIZED: Resolve database path with centralization logic
    from pathlib import Path

    configured_path = Path(settings.logging.developer_mode.db_path).expanduser()

    if configured_path.is_absolute():
        # Absolute path: use as-is (for advanced use cases)
        db_path = str(configured_path)
        configured_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        # Relative path: resolve relative to ~/.mcp_logs/ (centralization)
        global_log_dir = Path.home() / ".mcp_logs"
        global_log_dir.mkdir(exist_ok=True)
        db_path = str(global_log_dir / configured_path)

    # Try to start log server
    try:
        _log_server = ZMQLogServer(
            port=port,
            db_path=db_path,
            batch_size=settings.logging.developer_mode.batch_size,
            batch_timeout=settings.logging.developer_mode.batch_timeout,
        )

        _server_thread = threading.Thread(target=_log_server.run)
        _server_thread.start()

        logging.info(f"Started ZMQ log server on port {port}")

    except zmq.ZMQError:
        # Port already in use, another instance is the server
        logging.info(f"ZMQ log server already running on port {port}")

    # Add ZMQ handler to our application logger (already configured above)
    try:
        instance_id = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        handover_timeout = getattr(
            settings.logging.developer_mode, "handover_timeout", 5.0
        )
        _zmq_handler = ZMQLogHandler(
            f"tcp://localhost:{port}", instance_id, handover_timeout
        )
        app_logger.addHandler(_zmq_handler)
    except Exception as e:
        logging.error(f"Failed to create ZMQ log handler: {e}")
        # Continue without ZMQ logging

    # Register shutdown hook
    import atexit

    atexit.register(shutdown_logging)


def _start_log_server() -> bool:
    """Internal helper to start log server (used for handover)."""
    global _log_server, _server_thread

    if _log_server is not None:
        return True  # Already running

    try:
        settings = get_settings()
        port = settings.logging.developer_mode.port

        # Use same database path resolution logic
        from pathlib import Path

        configured_path = Path(settings.logging.developer_mode.db_path).expanduser()

        if configured_path.is_absolute():
            db_path = str(configured_path)
            configured_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            global_log_dir = Path.home() / ".mcp_logs"
            global_log_dir.mkdir(exist_ok=True)
            db_path = str(global_log_dir / configured_path)

        _log_server = ZMQLogServer(
            port=port,
            db_path=db_path,
            batch_size=settings.logging.developer_mode.batch_size,
            batch_timeout=settings.logging.developer_mode.batch_timeout,
        )

        _server_thread = threading.Thread(target=_log_server.run)
        _server_thread.start()

        print(f"Successfully took over as ZMQ log server on port {port}")
        return True

    except Exception as e:
        print(f"Failed to start log server during handover: {e}")
        return False


def shutdown_logging():
    """Graceful shutdown of logging system."""
    global _log_server, _server_thread, _zmq_handler

    logging.info("Shutting down logging system")

    # Close ZMQ handler
    if _zmq_handler:
        try:
            _zmq_handler.close()
        except Exception as e:
            logging.error(f"Error closing ZMQ handler: {e}")

    # Shutdown ZMQ server
    if _log_server:
        try:
            _log_server.shutdown()
            if _server_thread and _server_thread.is_alive():
                _server_thread.join(timeout=5.0)
                if _server_thread.is_alive():
                    logging.warning("ZMQ log server thread did not shutdown cleanly")
        except Exception as e:
            logging.error(f"Error shutting down ZMQ log server: {e}")
