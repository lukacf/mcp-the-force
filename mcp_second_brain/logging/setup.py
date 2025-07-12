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

logger = logging.getLogger(__name__)

_log_server: Optional[ZMQLogServer] = None
_server_thread: Optional[threading.Thread] = None
_zmq_handler: Optional[ZMQLogHandler] = None


def setup_logging():
    """Initialize logging system."""
    settings = get_settings()

    # Always setup basic logging
    logging.basicConfig(
        level=settings.logging.level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Developer mode logging
    if not settings.logging.developer_mode.enabled:
        logger.info("Developer logging mode is disabled")
        return

    global _log_server, _server_thread, _zmq_handler

    port = settings.logging.developer_mode.port
    db_path = settings.logging.developer_mode.db_path

    # Try to start log server
    try:
        _log_server = ZMQLogServer(
            port=port,
            db_path=db_path,
            batch_size=settings.logging.developer_mode.batch_size,
            batch_timeout=settings.logging.developer_mode.batch_timeout,
        )

        _server_thread = threading.Thread(target=_log_server.run, daemon=False)
        _server_thread.start()

        logger.info(f"Started ZMQ log server on port {port}")

    except zmq.ZMQError as e:
        # Port already in use, another instance is the server
        logger.info(f"ZMQ log server already running on port {port}: {e}")
    except Exception as e:
        logger.error(f"Failed to start ZMQ log server: {e}")

    # Always setup client handler
    try:
        instance_id = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        _zmq_handler = ZMQLogHandler(f"tcp://localhost:{port}", instance_id)
        logging.getLogger().addHandler(_zmq_handler)
        logger.info(f"Connected to ZMQ log server as client {instance_id}")
    except Exception as e:
        logger.error(f"Failed to setup ZMQ log handler: {e}")

    # Register shutdown hook
    import atexit

    atexit.register(shutdown_logging)


def shutdown_logging():
    """Graceful shutdown of logging system."""
    global _log_server, _server_thread, _zmq_handler

    logger.info("Shutting down logging system")

    # Close handler first
    if _zmq_handler:
        try:
            _zmq_handler.close()
        except Exception as e:
            logger.error(f"Error closing ZMQ handler: {e}")

    # Then shutdown server if we're running one
    if _log_server:
        try:
            _log_server.shutdown()
            if _server_thread and _server_thread.is_alive():
                _server_thread.join(timeout=5.0)
                if _server_thread.is_alive():
                    logger.warning("ZMQ log server thread did not shutdown cleanly")
        except Exception as e:
            logger.error(f"Error shutting down ZMQ log server: {e}")
