"""ZMQ log server for aggregating logs from multiple MCP instances."""

import zmq
import sqlite3
import threading
import time
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class ZMQLogServer:
    """ZeroMQ-based log server that aggregates logs to SQLite."""

    def __init__(
        self, port: int, db_path: str, batch_size: int = 100, batch_timeout: float = 1.0
    ):
        self.port = port
        self.db_path = db_path
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.shutdown_event = threading.Event()

        # ZMQ setup
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PULL)
        self.socket.bind(f"tcp://127.0.0.1:{port}")  # Local only
        self.socket.setsockopt(zmq.RCVTIMEO, 100)  # 100ms timeout

        # Database setup
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                project_cwd TEXT NOT NULL,
                trace_id TEXT,
                module TEXT,
                extra TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_logs_instance ON logs(instance_id);
            CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level);
            CREATE INDEX IF NOT EXISTS idx_logs_project ON logs(project_cwd);
        """)
        self.db.commit()

    def run(self):
        """Main server loop with batched writes."""
        batch: List[Dict[str, Any]] = []
        last_flush = time.time()

        logger.info(f"ZMQ log server started on port {self.port}")

        while not self.shutdown_event.is_set():
            try:
                # Try to receive with timeout
                try:
                    msg = self.socket.recv_json(flags=zmq.NOBLOCK)
                    batch.append(msg)
                except zmq.Again:
                    # No message available
                    pass
                except Exception as e:
                    logger.error(f"Error receiving message: {e}")
                    continue

                # Flush if batch is full or timeout reached
                now = time.time()
                if len(batch) >= self.batch_size or (
                    batch and now - last_flush >= self.batch_timeout
                ):
                    self._flush_batch(batch)
                    batch = []
                    last_flush = now

            except Exception as e:
                # Log error but don't crash
                logger.error(f"Log server error: {e}")
                continue

        # Final flush on shutdown
        if batch:
            self._flush_batch(batch)

        logger.info("ZMQ log server shutting down")
        self.db.close()
        self.socket.close()
        self.context.term()

    def _flush_batch(self, batch: List[Dict[str, Any]]):
        """Write batch to database."""
        if not batch:
            return

        try:
            records = [
                (
                    msg.get("timestamp", time.time()),
                    msg.get("level", "INFO"),
                    msg.get("message", ""),
                    msg.get("instance_id", "unknown"),
                    msg.get("project_cwd", "unknown"),
                    msg.get("trace_id"),
                    msg.get("module"),
                    json.dumps(msg.get("extra", {})),
                )
                for msg in batch
            ]

            self.db.executemany(
                """INSERT INTO logs 
                   (timestamp, level, message, instance_id, project_cwd, trace_id, module, extra)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                records,
            )
            self.db.commit()

        except Exception as e:
            logger.error(f"Failed to write batch of {len(batch)} records: {e}")

    def shutdown(self):
        """Graceful shutdown."""
        logger.info("Initiating ZMQ log server shutdown")
        self.shutdown_event.set()
