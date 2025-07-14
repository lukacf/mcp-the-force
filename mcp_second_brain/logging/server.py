"""ZMQ-based logging server for MCP Second Brain."""

import zmq
import sqlite3
import threading
import time
import json
from typing import List, Dict, Any


class ZMQLogServer:
    def __init__(
        self,
        port: int,
        db_path: str,
        batch_size: int = 100,
        batch_timeout: float = 1.0,
        max_db_size_mb: int = 1000,
    ):
        self.port = port
        self.db_path = db_path
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.max_db_size_mb = max_db_size_mb
        self.shutdown_event = threading.Event()

        # ZMQ setup
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PULL)
        self.socket.bind(f"tcp://127.0.0.1:{port}")  # Local only
        # No RCVTIMEO needed - using Poller with timeout instead

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
        """Main server loop with efficient polling and batched writes."""
        batch: List[Dict[str, Any]] = []
        last_flush = time.time()

        print(f"ZMQ log server started on port {self.port}")

        # Use ZMQ Poller for efficient event-based waiting (no busy loop)
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)

        while not self.shutdown_event.is_set():
            try:
                # Poll with timeout to check shutdown event periodically
                events = dict(poller.poll(timeout=100))  # 100ms timeout

                if self.socket in events:
                    # Message available - receive it
                    try:
                        msg = self.socket.recv_json(flags=zmq.NOBLOCK)
                        batch.append(msg)
                    except zmq.Again:
                        # Should not happen since poll indicated data ready
                        pass

                # Flush if batch is full or timeout reached
                now = time.time()
                if len(batch) >= self.batch_size or (
                    batch and now - last_flush >= self.batch_timeout
                ):
                    self._flush_batch(batch)
                    batch = []
                    last_flush = now

            except zmq.ZMQError as e:
                if e.errno == zmq.ETERM:
                    # Context terminated, shutdown gracefully
                    break
                print(f"ZMQ error in log server: {e}")
                continue
            except Exception as e:
                # Log error but don't crash
                print(f"Log server error: {e}")
                continue

        # Final flush on shutdown
        if batch:
            self._flush_batch(batch)

        self.db.close()
        self.socket.close()
        self.context.term()

    def _flush_batch(self, batch: List[Dict[str, Any]]):
        """Write batch to database."""
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
            print(f"Failed to write batch: {e}")

    def shutdown(self):
        """Graceful shutdown."""
        self.shutdown_event.set()
