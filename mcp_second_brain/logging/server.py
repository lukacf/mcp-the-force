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
        self, port: int, db_path: str, batch_size: int = 100, batch_timeout: float = 1.0, max_db_size_mb: int = 1000
    ):
        self.port = port
        self.db_path = db_path
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.max_db_size_mb = max_db_size_mb
        self.shutdown_event = threading.Event()
        self.db_lock = threading.Lock()  # Fix threading issues

        # ZMQ setup
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PULL)
        self.socket.bind(f"tcp://127.0.0.1:{port}")  # Local only
        self.socket.setsockopt(zmq.RCVTIMEO, 100)  # 100ms timeout

        # Database setup
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        """Initialize database schema with optimizations."""
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            PRAGMA auto_vacuum=INCREMENTAL;
            PRAGMA wal_autocheckpoint=1000;
            
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
            CREATE INDEX IF NOT EXISTS idx_logs_message ON logs(message);
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
                    raw_msg = self.socket.recv(flags=zmq.NOBLOCK)
                    try:
                        msg = json.loads(raw_msg.decode('utf-8'))
                        batch.append(msg)
                    except (json.JSONDecodeError, UnicodeDecodeError) as e:
                        logger.error(f"Failed to parse log message, dropping: {e}")
                        # Log the raw message for debugging
                        logger.error(f"Raw message: {raw_msg[:200]}...")  # Truncate for safety
                        continue
                except zmq.Again:
                    # No message available
                    pass
                except Exception as e:
                    logger.error(f"Error receiving message from ZMQ socket: {e}")
                    continue

                # Flush if batch is full or timeout reached
                now = time.time()
                if len(batch) >= self.batch_size or (
                    batch and now - last_flush >= self.batch_timeout
                ):
                    # Make a copy of batch before flushing to avoid race conditions
                    batch_to_flush = batch.copy()
                    batch = []
                    last_flush = now
                    self._flush_batch(batch_to_flush)

            except Exception as e:
                # Log error but don't crash - this is the outer exception handler
                logger.error(f"Unexpected error in log server loop: {e}")
                # Add a small delay to prevent tight error loops
                time.sleep(0.1)
                continue

        # Final flush on shutdown - also check for any last-minute messages
        try:
            # Try to receive any final messages that arrived during shutdown
            while True:
                try:
                    msg = self.socket.recv_json(flags=zmq.NOBLOCK)
                    batch.append(msg)
                except zmq.Again:
                    break  # No more messages
        except Exception:
            pass  # Ignore errors during final message collection
            
        if batch:
            self._flush_batch(batch)

        logger.info("ZMQ log server shutting down")
        with self.db_lock:  # Ensure clean shutdown
            self.db.close()
        self.socket.close()
        self.context.term()

    def _flush_batch(self, batch: List[Dict[str, Any]]):
        """Write batch to database with thread safety and rotation."""
        if not batch:
            return

        with self.db_lock:  # Fix threading issues
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
                
                # Check database size and rotate if needed
                self._check_and_rotate_db()

            except Exception as e:
                logger.error(f"Failed to write batch of {len(batch)} records: {e}")

    def _check_and_rotate_db(self):
        """Check database size and rotate if exceeding limit."""
        try:
            import os
            
            # Check main DB file size
            db_size_mb = os.path.getsize(self.db_path) / (1024 * 1024)
            
            # Also check for WAL file
            wal_path = self.db_path + "-wal"
            if os.path.exists(wal_path):
                db_size_mb += os.path.getsize(wal_path) / (1024 * 1024)
            
            if db_size_mb > self.max_db_size_mb:
                logger.info(f"Database size ({db_size_mb:.1f} MB) exceeds limit ({self.max_db_size_mb} MB), rotating")
                self._rotate_database()
                
        except Exception as e:
            logger.error(f"Error checking database size: {e}")
    
    def _rotate_database(self):
        """Rotate the database by backing up old logs and recreating."""
        try:
            import os
            import shutil
            from datetime import datetime
            
            # Create backup filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{self.db_path}.{timestamp}.backup"
            
            # Close current connection
            self.db.close()
            
            # Move current database to backup
            shutil.move(self.db_path, backup_path)
            logger.info(f"Backed up database to {backup_path}")
            
            # Remove WAL and SHM files if they exist
            for suffix in ["-wal", "-shm"]:
                old_file = self.db_path + suffix
                if os.path.exists(old_file):
                    os.remove(old_file)
            
            # Recreate database connection and schema
            self.db = sqlite3.connect(self.db_path, check_same_thread=False)
            self._init_db()
            
            logger.info("Database rotated successfully")
            
        except Exception as e:
            logger.error(f"Error rotating database: {e}")
            # Try to restore connection even if rotation failed
            try:
                self.db = sqlite3.connect(self.db_path, check_same_thread=False)
            except Exception as restore_error:
                logger.error(f"Failed to restore database connection: {restore_error}")

    def shutdown(self):
        """Graceful shutdown."""
        logger.info("Initiating ZMQ log server shutdown")
        self.shutdown_event.set()
