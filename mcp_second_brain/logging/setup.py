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
            max_db_size_mb=settings.logging.developer_mode.max_db_size_mb,
        )

        _server_thread = threading.Thread(target=_log_server.run, daemon=False)
        _server_thread.start()

        logger.info(f"Started ZMQ log server on port {port}")

    except zmq.ZMQError as e:
        # Port already in use, another instance is the server
        logger.info(f"ZMQ log server already running on port {port}: {e}")
    except Exception as e:
        logger.error(f"Failed to start ZMQ log server: {e}")

    # Setup client handler (check for duplicates first)
    root_logger = logging.getLogger()
    
    # Check if ZMQ handler is already installed
    try:
        zmq_handler_exists = any(isinstance(h, ZMQLogHandler) for h in root_logger.handlers)
    except TypeError:
        # Handle case where ZMQLogHandler might be mocked in tests
        zmq_handler_exists = any(
            getattr(h, '__class__', None).__name__ == 'ZMQLogHandler' 
            for h in root_logger.handlers
        )
    
    if not zmq_handler_exists:
        try:
            instance_id = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
            _zmq_handler = ZMQLogHandler(f"tcp://localhost:{port}", instance_id)
            root_logger.addHandler(_zmq_handler)
            logger.info(f"Connected to ZMQ log server as client {instance_id}")
        except Exception as e:
            logger.error(f"Failed to setup ZMQ log handler: {e}")
    else:
        logger.debug("ZMQ log handler already installed, skipping")

    # Register shutdown hook (only once)
    import atexit
    
    # Use a simple flag to track registration
    if not hasattr(setup_logging, '_shutdown_registered'):
        atexit.register(shutdown_logging)
        setup_logging._shutdown_registered = True


def shutdown_logging():
    """Graceful shutdown of logging system."""
    global _log_server, _server_thread, _zmq_handler

    logger.info("Shutting down logging system")

    # Close handler first to stop new messages
    if _zmq_handler:
        try:
            _zmq_handler.close()
        except Exception as e:
            logger.error(f"Error closing ZMQ handler: {e}")

    # Give a moment for any in-flight messages to be processed
    import time
    time.sleep(0.1)

    # Then shutdown server if we're running one
    if _log_server:
        try:
            _log_server.shutdown()
            if _server_thread and _server_thread.is_alive():
                _server_thread.join(timeout=5.0)
                if _server_thread.is_alive():
                    logger.warning("ZMQ log server thread did not shutdown cleanly")
                    # Try to force resource cleanup even if thread is stuck
                    try:
                        if hasattr(_log_server, 'db') and _log_server.db:
                            _log_server.db.close()
                        if hasattr(_log_server, 'context') and _log_server.context:
                            _log_server.context.term()
                    except Exception as cleanup_error:
                        logger.error(f"Error during forced cleanup: {cleanup_error}")
        except Exception as e:
            logger.error(f"Error shutting down ZMQ log server: {e}")
