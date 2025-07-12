"""ZMQ log handler for sending logs to the aggregation server."""

import zmq
import logging
import threading
import queue
import os
import time
import sys

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
        self.sender_thread = threading.Thread(
            target=self._sender_loop, 
            daemon=False,  # Fix: Don't use daemon to ensure proper shutdown
            name=f"LogSender-{os.getpid()}"  # Fix: Name thread for debugging
        )
        self.sender_thread.start()

    def _sender_loop(self):
        """Background thread for sending logs with retry logic."""
        context = zmq.Context()
        socket = context.socket(zmq.PUSH)
        socket.connect(self.address)
        socket.setsockopt(zmq.LINGER, 0)  # Don't block on close
        socket.setsockopt(zmq.SNDHWM, 1000)  # High water mark
        
        failed_sends = 0
        max_retries = 3

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

                # Try to send with retry logic
                retry_count = 0
                while retry_count < max_retries:
                    try:
                        socket.send_json(msg, flags=zmq.NOBLOCK)
                        failed_sends = 0  # Reset failure counter on success
                        break
                    except zmq.Again:
                        # Socket buffer full, retry with exponential backoff
                        retry_count += 1
                        if retry_count < max_retries:
                            time.sleep(0.1 * (2 ** retry_count))  # Exponential backoff
                        else:
                            # Final retry failed, fallback to stderr
                            print(f"Dropped log after {max_retries} retries: {record.getMessage()}", file=sys.stderr)
                            break
                else:
                    # All retries failed
                    failed_sends += 1

            except queue.Empty:
                continue
            except Exception as e:
                # Don't use logger here to avoid infinite recursion
                print(f"ZMQ handler error: {e}", file=sys.stderr)
                failed_sends += 1
                
                # If too many failures, add delay to avoid tight error loop
                if failed_sends > 10:
                    time.sleep(1.0)

        socket.close()
        context.term()

    def emit(self, record: logging.LogRecord):
        """Queue log record for sending with fallback."""
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            # Fallback: Log to stderr when queue is full
            print(f"Log queue full, dropping: {record.getMessage()}", file=sys.stderr)

    def close(self):
        """Shutdown handler with proper resource cleanup."""
        try:
            # Signal shutdown - use put() with timeout to handle full queue
            try:
                self.queue.put(None, timeout=1.0)
            except queue.Full:
                # Queue is full, try to drain some messages first
                try:
                    for _ in range(min(100, self.queue.qsize())):
                        self.queue.get_nowait()
                    self.queue.put(None, timeout=0.5)
                except (queue.Empty, queue.Full):
                    # Force shutdown if queue manipulation fails
                    pass
            
            # Wait for thread to finish
            if self.sender_thread.is_alive():
                self.sender_thread.join(timeout=5.0)  # Increased timeout
                
                if self.sender_thread.is_alive():
                    print(f"Warning: LogSender thread did not shutdown cleanly", file=sys.stderr)
            
            # Drain any remaining messages to prevent memory leaks
            try:
                while not self.queue.empty():
                    self.queue.get_nowait()
            except queue.Empty:
                pass
                
        except Exception as e:
            print(f"Error during ZMQ handler shutdown: {e}", file=sys.stderr)
        finally:
            super().close()
