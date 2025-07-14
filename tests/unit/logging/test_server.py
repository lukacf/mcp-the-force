"""Unit tests for ZMQ log server."""

import pytest
import tempfile
import sqlite3
import json
import time
import threading
import zmq
from unittest.mock import Mock, patch
from pathlib import Path

from mcp_second_brain.logging.server import ZMQLogServer


class TestZMQLogServer:
    """Test ZMQ log server functionality."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name
        yield db_path
        Path(db_path).unlink(missing_ok=True)

    @pytest.fixture
    def mock_zmq_context(self):
        """Mock ZMQ context to avoid actual network operations."""
        with patch("zmq.Context") as mock_context:
            mock_socket = Mock()
            mock_context.return_value.socket.return_value = mock_socket
            yield mock_context, mock_socket

    def test_init_creates_database_schema(self, temp_db, mock_zmq_context):
        """Test that server initialization creates the correct database schema."""
        mock_context, mock_socket = mock_zmq_context

        ZMQLogServer(port=4711, db_path=temp_db)

        # Check database schema
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor]
        assert "logs" in tables

        # Check indexes
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor]
        assert any("timestamp" in idx for idx in indexes)
        assert any("instance" in idx for idx in indexes)
        assert any("level" in idx for idx in indexes)
        assert any("project" in idx for idx in indexes)

        conn.close()

    def test_init_configures_zmq_socket(self, temp_db, mock_zmq_context):
        """Test that server initialization configures ZMQ socket correctly."""
        mock_context, mock_socket = mock_zmq_context

        ZMQLogServer(port=4711, db_path=temp_db)

        # Verify socket configuration
        mock_socket.bind.assert_called_once_with("tcp://127.0.0.1:4711")
        # No RCVTIMEO set - we use Poller with timeout instead

    def test_flush_batch_writes_to_database(self, temp_db, mock_zmq_context):
        """Test that flush_batch correctly writes log records to database."""
        mock_context, mock_socket = mock_zmq_context

        server = ZMQLogServer(port=4711, db_path=temp_db)

        # Test data
        test_batch = [
            {
                "timestamp": 1234567890.0,
                "level": "INFO",
                "message": "Test message 1",
                "instance_id": "test-instance-1",
                "project_cwd": "/test/project",
                "module": "test.module",
                "extra": {"key": "value"},
            },
            {
                "timestamp": 1234567891.0,
                "level": "ERROR",
                "message": "Test message 2",
                "instance_id": "test-instance-2",
                "project_cwd": "/test/project",
                "module": "test.module2",
            },
        ]

        server._flush_batch(test_batch)

        # Verify data was written
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("SELECT * FROM logs ORDER BY timestamp")
        rows = cursor.fetchall()

        assert len(rows) == 2
        assert rows[0][1] == 1234567890.0  # timestamp
        assert rows[0][2] == "INFO"  # level
        assert rows[0][3] == "Test message 1"  # message
        assert rows[0][4] == "test-instance-1"  # instance_id
        assert rows[0][5] == "/test/project"  # project_cwd

        # Check that extra was JSON serialized
        extra_data = json.loads(rows[0][8])
        assert extra_data == {"key": "value"}

        conn.close()

    def test_flush_batch_handles_missing_fields(self, temp_db, mock_zmq_context):
        """Test that flush_batch handles messages with missing fields gracefully."""
        mock_context, mock_socket = mock_zmq_context

        server = ZMQLogServer(port=4711, db_path=temp_db)

        # Test data with missing fields
        test_batch = [
            {
                "message": "Minimal message"
                # Missing most fields
            }
        ]

        server._flush_batch(test_batch)

        # Verify data was written with defaults
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("SELECT level, instance_id, project_cwd FROM logs")
        row = cursor.fetchone()

        assert row[0] == "INFO"  # default level
        assert row[1] == "unknown"  # default instance_id
        assert row[2] == "unknown"  # default project_cwd

        conn.close()

    def test_flush_batch_handles_database_errors(self, temp_db, mock_zmq_context):
        """Test that flush_batch handles database errors gracefully."""
        mock_context, mock_socket = mock_zmq_context

        server = ZMQLogServer(port=4711, db_path=temp_db)

        # Close the database connection to force an error
        server.db.close()

        test_batch = [{"message": "test"}]

        # Should not raise an exception
        server._flush_batch(test_batch)

    def test_shutdown_sets_event(self, temp_db, mock_zmq_context):
        """Test that shutdown correctly sets the shutdown event."""
        mock_context, mock_socket = mock_zmq_context

        server = ZMQLogServer(port=4711, db_path=temp_db)

        assert not server.shutdown_event.is_set()
        server.shutdown()
        assert server.shutdown_event.is_set()

    @pytest.mark.timeout(5)
    @patch("zmq.Poller")
    def test_run_loop_with_mock_messages(
        self, mock_poller_class, temp_db, mock_zmq_context
    ):
        """Test the main run loop with mocked ZMQ messages."""
        mock_context, mock_socket = mock_zmq_context

        # Configure mock to return messages then timeout
        test_messages = [
            {"message": "test1", "level": "INFO"},
            {"message": "test2", "level": "ERROR"},
        ]

        # Mock recv to return orjson-encoded messages then raise zmq.Again
        import orjson

        encoded_messages = [orjson.dumps(msg) for msg in test_messages]
        mock_socket.recv.side_effect = encoded_messages + [zmq.Again()]

        # Mock poller to simulate message availability
        mock_poller = Mock()
        mock_poller_class.return_value = mock_poller

        # First two polls return socket ready, third returns nothing (timeout)
        mock_poller.poll.side_effect = [
            {mock_socket: zmq.POLLIN},  # Message 1 ready
            {mock_socket: zmq.POLLIN},  # Message 2 ready
            {},  # Timeout - no messages (triggers shutdown check)
        ] * 10  # Repeat pattern to avoid IndexError

        server = ZMQLogServer(port=4711, db_path=temp_db, batch_timeout=0.1)

        # Run server in a thread with quick shutdown
        def run_with_timeout():
            time.sleep(0.2)  # Let it process messages
            server.shutdown()

        shutdown_thread = threading.Thread(target=run_with_timeout)
        shutdown_thread.start()

        server.run()
        shutdown_thread.join()

        # Verify messages were processed
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("SELECT COUNT(*) FROM logs")
        count = cursor.fetchone()[0]
        assert count == 2
        conn.close()

    def test_database_wal_mode_enabled(self, temp_db, mock_zmq_context):
        """Test that database is configured with WAL mode for performance."""
        mock_context, mock_socket = mock_zmq_context

        ZMQLogServer(port=4711, db_path=temp_db)

        # Check WAL mode is enabled
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode.upper() == "WAL"
        conn.close()
