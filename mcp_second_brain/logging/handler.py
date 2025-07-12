"""ZMQ log handler for sending logs to the aggregation server."""

import zmq
import logging
import threading
import queue
import os

from ..utils.logging_filter import RedactionFilter

logger = logging.getLogger(__name__)


class ZMQLogHandler(logging.Handler):
    """Async log handler that sends records to ZMQ log server."""

    def __init__(self, address: str, instance_id: str):
        super().__init__()
        self.address = address
        self.instance_id = instance_id

        # Add redaction filter
        self.addFilter(RedactionFilter())

        # Queue for async sending
        self.queue: queue.Queue = queue.Queue(maxsize=10000)
        self.sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self.sender_thread.start()

    def _sender_loop(self):
        """Background thread for sending logs."""
        context = zmq.Context()
        socket = context.socket(zmq.PUSH)
        socket.connect(self.address)
        socket.setsockopt(zmq.LINGER, 0)  # Don't block on close
        socket.setsockopt(zmq.SNDHWM, 1000)  # High water mark

        while True:
            try:
                record = self.queue.get(timeout=1.0)
                if record is None:  # Shutdown signal
                    break

                msg = {
                    "timestamp": record.created,
                    "level": record.levelname,
                    "message": record.getMessage(),
                    "instance_id": self.instance_id,
                    "project_cwd": os.environ.get(
                        "MCP_PROJECT_PATH", os.getcwd()
                    ),  # Canonical project path
                    "module": record.name,
                    "trace_id": getattr(record, "trace_id", None),
                    "extra": {
                        "pathname": record.pathname,
                        "lineno": record.lineno,
                        "funcName": record.funcName,
                    },
                }

                socket.send_json(msg, flags=zmq.NOBLOCK)

            except queue.Empty:
                continue
            except zmq.Again:
                # Socket buffer full, drop message
                pass
            except Exception as e:
                # Don't use logger here to avoid infinite recursion
                print(f"ZMQ handler error: {e}")

        socket.close()
        context.term()

    def emit(self, record: logging.LogRecord):
        """Queue log record for sending."""
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            # Drop message if queue is full
            pass

    def close(self):
        """Shutdown handler."""
        self.queue.put(None)  # Signal shutdown
        if self.sender_thread.is_alive():
            self.sender_thread.join(timeout=2.0)
        super().close()
