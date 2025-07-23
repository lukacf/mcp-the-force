"""E2E test logging configuration for VictoriaLogs."""

import logging
import os
import sys
import queue
import logging.handlers
from typing import Optional

# Conditionally import Loki handler only if available
try:
    # The package name is python-logging-loki but the import is logging_loki
    from logging_loki import LokiQueueHandler

    LOKI_AVAILABLE = True
except ImportError:
    LOKI_AVAILABLE = False
    print("Warning: python-logging-loki not available, using stderr logging")


def setup_e2e_logging(
    test_name: str = "unknown", victoria_logs_url: Optional[str] = None
) -> None:
    """Setup logging for E2E tests to send to VictoriaLogs.

    Args:
        test_name: Specific test name for tagging logs (e.g., "smoke", "environment")
        victoria_logs_url: VictoriaLogs URL (defaults to env var or localhost)
    """
    # Get VictoriaLogs URL
    if victoria_logs_url is None:
        victoria_logs_url = os.getenv(
            "VICTORIA_LOGS_URL", "http://host.docker.internal:9428"
        )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Clear existing handlers
    root_logger.handlers.clear()

    if LOKI_AVAILABLE and not os.getenv("DISABLE_VICTORIA_LOGS"):
        try:
            # Create Loki handler for VictoriaLogs
            loki_url = f"{victoria_logs_url}/insert/loki/api/v1/push?_stream_fields=app,test_name"

            # Create a queue for non-blocking logging
            log_queue = queue.Queue(-1)

            # Use queue handler for non-blocking
            # LokiQueueHandler creates its own LokiHandler internally
            queue_handler = LokiQueueHandler(
                log_queue,
                url=loki_url,
                tags={
                    "app": f"e2e-test-{test_name}",
                    "test_name": test_name,
                    "environment": "docker",
                },
                version="1",
            )
            queue_handler.setLevel(logging.INFO)

            # Add formatter
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            queue_handler.setFormatter(formatter)

            # Add handler to root logger
            root_logger.addHandler(queue_handler)

            # Also add stderr handler for critical messages
            stderr_handler = logging.StreamHandler(sys.stderr)
            stderr_handler.setLevel(logging.WARNING)
            stderr_handler.setFormatter(formatter)
            root_logger.addHandler(stderr_handler)

            print(
                f"✅ E2E logging configured to send to VictoriaLogs at {victoria_logs_url}"
            )

        except Exception as e:
            print(f"❌ Failed to setup VictoriaLogs logging: {e}")
            # Fall back to stderr
            _setup_stderr_logging(root_logger)
    else:
        # Use stderr logging
        _setup_stderr_logging(root_logger)


def _setup_stderr_logging(root_logger):
    """Setup basic stderr logging as fallback."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    print("⚠️  Using stderr logging (VictoriaLogs not available)")
