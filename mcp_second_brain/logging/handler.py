"""ZMQ log handler for sending logs to the aggregation server."""

import zmq
import logging
import threading
import queue
import os
import orjson

from ..utils.logging_filter import RedactionFilter


class ZMQLogHandler(logging.Handler):
    def __init__(self, address: str, instance_id: str, handover_timeout: float = 5.0):
        super().__init__()
        self.address = address
        self.instance_id = instance_id
        self.handover_timeout = handover_timeout

        # Add redaction filter
        self.addFilter(RedactionFilter())

        # Queue for async sending
        self.queue: queue.Queue = queue.Queue(maxsize=10000)
        self.sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self.sender_thread.start()

    def _sender_loop(self):
        """Background thread for sending logs with server handover logic."""
        import time

        context = zmq.Context()
        socket = context.socket(zmq.PUSH)
        socket.connect(self.address)
        socket.setsockopt(zmq.LINGER, 0)  # Don't block on close
        socket.setsockopt(zmq.SNDHWM, 1000)  # High water mark

        consecutive_failures = 0
        last_failure_time = 0

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

                try:
                    # Use orjson for GIL-friendly JSON serialization
                    serialized = orjson.dumps(msg)
                    socket.send(serialized, flags=zmq.NOBLOCK)
                    consecutive_failures = 0  # Reset failure counter on success
                except zmq.Again:
                    # Socket buffer full, drop message but don't count as server failure
                    pass

            except queue.Empty:
                continue
            except zmq.ZMQError:
                # Server connection issue - potential handover scenario
                consecutive_failures += 1
                current_time = time.time()

                if (
                    consecutive_failures >= 3
                    and (current_time - last_failure_time) > self.handover_timeout
                ):
                    # Attempt server takeover
                    print(
                        f"Attempting server takeover after {consecutive_failures} failures..."
                    )
                    if self._attempt_server_takeover():
                        consecutive_failures = 0
                    last_failure_time = current_time

            except Exception as e:
                print(f"ZMQ handler error: {e}")

        socket.close()
        context.term()

    def _attempt_server_takeover(self) -> bool:
        """Attempt to become the log server if current server is unresponsive."""
        try:
            # Import here to avoid circular imports
            from .setup import _start_log_server

            return _start_log_server()
        except Exception as e:
            print(f"Server takeover failed: {e}")
            return False

    def emit(self, record: logging.LogRecord):
        """Queue log record for sending."""
        try:
            # Truncate large messages to prevent GIL starvation during JSON serialization
            msg = record.getMessage()
            if len(msg) > 8192:  # 8KB limit
                record.msg = msg[:8192] + " ...[truncated]..."
                record.args = ()  # Clear args to prevent re-formatting

            self.queue.put_nowait(record)
        except queue.Full:
            # Drop message if queue is full
            pass

    def close(self):
        """Shutdown handler."""
        self.queue.put(None)  # Signal shutdown
        if self.sender_thread.is_alive():
            self.sender_thread.join(timeout=5.0)
        super().close()
