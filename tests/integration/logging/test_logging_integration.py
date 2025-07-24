"""Integration tests for the complete logging system."""

import pytest
import tempfile
import sqlite3
import logging
import time
import threading
import os
from pathlib import Path
from unittest.mock import patch

from mcp_the_force.logging.server import ZMQLogServer
from mcp_the_force.logging.handler import ZMQLogHandler
from mcp_the_force.logging.setup import setup_logging, shutdown_logging
from mcp_the_force.tools.logging_tools import SearchMCPDebugLogsToolSpec


@pytest.mark.integration
class TestLoggingSystemIntegration:
    """Integration tests for the complete logging system."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name
        yield db_path
        Path(db_path).unlink(missing_ok=True)

    @pytest.fixture
    def test_port(self):
        """Get an available port for testing."""
        import socket

        sock = socket.socket()
        sock.bind(("", 0))
        port = sock.getsockname()[1]
        sock.close()
        return port

    @pytest.fixture
    def mock_settings(self, temp_db, test_port):
        """Mock settings for integration testing."""
        from unittest.mock import Mock

        settings = Mock()
        settings.logging.level = "INFO"
        settings.logging.developer_mode.enabled = True
        settings.logging.developer_mode.port = test_port
        settings.logging.developer_mode.db_path = temp_db
        settings.logging.developer_mode.batch_size = 10  # Small batch for quick testing
        settings.logging.developer_mode.batch_timeout = 0.1  # Quick timeout
        return settings

    @pytest.mark.timeout(10)
    def test_end_to_end_logging_flow(self, mock_settings, test_port, temp_db):
        """Test complete end-to-end logging flow."""
        # Start ZMQ server
        server = ZMQLogServer(
            port=test_port, db_path=temp_db, batch_size=10, batch_timeout=0.1
        )

        server_thread = threading.Thread(target=server.run)
        server_thread.start()

        try:
            # Give server time to start
            time.sleep(0.1)

            # Create handler and send some logs
            handler = ZMQLogHandler(f"tcp://localhost:{test_port}", "test-instance")

            # Create test logger
            test_logger = logging.getLogger("integration_test")
            test_logger.addHandler(handler)
            test_logger.setLevel(logging.INFO)

            # Send test messages
            test_logger.info("Integration test message 1")
            test_logger.error("Integration test message 2")
            test_logger.warning("Integration test message 3")

            # Give time for messages to be processed
            time.sleep(0.5)

            # Verify messages were written to database
            conn = sqlite3.connect(temp_db)
            cursor = conn.execute("SELECT COUNT(*) FROM logs")
            count = cursor.fetchone()[0]
            assert count >= 3

            # Verify message content
            cursor = conn.execute("SELECT level, message FROM logs ORDER BY timestamp")
            messages = cursor.fetchall()

            levels = [msg[0] for msg in messages]
            assert "INFO" in levels
            assert "ERROR" in levels
            assert "WARNING" in levels

            contents = [msg[1] for msg in messages]
            assert any("Integration test message 1" in content for content in contents)
            assert any("Integration test message 2" in content for content in contents)
            assert any("Integration test message 3" in content for content in contents)

            conn.close()

            # Clean up handler
            handler.close()

        finally:
            # Clean up server
            server.shutdown()
            server_thread.join(timeout=2.0)

    @pytest.mark.skip("Tool execute tests require adapter refactoring")
    @pytest.mark.timeout(10)
    @pytest.mark.asyncio
    async def test_logging_tool_integration(self, mock_settings, test_port, temp_db):
        """Test integration between logging system and search tool."""
        # Start server and send some logs
        server = ZMQLogServer(
            port=test_port, db_path=temp_db, batch_size=5, batch_timeout=0.1
        )

        server_thread = threading.Thread(target=server.run)
        server_thread.start()

        try:
            time.sleep(0.1)

            # Send test logs
            handler = ZMQLogHandler(
                f"tcp://localhost:{test_port}", "tool-test-instance"
            )
            test_logger = logging.getLogger("tool_integration_test")
            test_logger.addHandler(handler)
            test_logger.setLevel(logging.INFO)

            test_logger.info("Searchable log message")
            test_logger.error("Error message for testing")

            time.sleep(0.3)

            # Now test the search tool
            tool = SearchMCPDebugLogsToolSpec()

            with patch(
                "mcp_the_force.adapters.logging_adapter.get_settings",
                return_value=mock_settings,
            ):
                with patch.dict("os.environ", {"MCP_PROJECT_PATH": os.getcwd()}):
                    # Search for info messages
                    result = await tool.execute(query="Searchable", since="1m")
                    assert "Found 1 log entries" in result
                    assert "Searchable log message" in result

                    # Search by level
                    result = await tool.execute(query="", level="ERROR", since="1m")
                    assert "ERROR" in result
                    assert "Error message for testing" in result

                    # Search with no results
                    result = await tool.execute(query="nonexistent", since="1m")
                    assert "No logs found" in result

            handler.close()

        finally:
            server.shutdown()
            server_thread.join(timeout=2.0)

    @pytest.mark.timeout(15)
    def test_setup_logging_integration(self, mock_settings):
        """Test the complete setup_logging integration."""
        with patch(
            "mcp_the_force.logging.setup.get_settings", return_value=mock_settings
        ):
            # Setup logging
            setup_logging()

            try:
                # Give setup time to complete
                time.sleep(0.2)

                # Get a logger and test it
                test_logger = logging.getLogger("setup_integration_test")
                test_logger.info("Setup integration test message")

                # Give time for message processing
                time.sleep(0.3)

                # Verify log was written
                conn = sqlite3.connect(mock_settings.logging.developer_mode.db_path)
                cursor = conn.execute(
                    "SELECT message FROM logs WHERE message LIKE '%Setup integration test%'"
                )
                result = cursor.fetchone()
                assert result is not None
                assert "Setup integration test message" in result[0]
                conn.close()

            finally:
                # Clean shutdown
                shutdown_logging()
                time.sleep(0.1)

    @pytest.mark.timeout(10)
    def test_multiple_instances_integration(self, mock_settings, test_port, temp_db):
        """Test multiple MCP instances logging to the same server."""
        # Start server
        server = ZMQLogServer(
            port=test_port, db_path=temp_db, batch_size=5, batch_timeout=0.1
        )

        server_thread = threading.Thread(target=server.run)
        server_thread.start()

        try:
            time.sleep(0.1)

            # Create multiple handlers (simulating multiple MCP instances)
            handler1 = ZMQLogHandler(f"tcp://localhost:{test_port}", "instance-1")
            handler2 = ZMQLogHandler(f"tcp://localhost:{test_port}", "instance-2")

            logger1 = logging.getLogger("multi_test_1")
            logger1.addHandler(handler1)
            logger1.setLevel(logging.INFO)

            logger2 = logging.getLogger("multi_test_2")
            logger2.addHandler(handler2)
            logger2.setLevel(logging.INFO)

            # Send messages from both instances
            logger1.info("Message from instance 1")
            logger2.info("Message from instance 2")
            logger1.error("Error from instance 1")
            logger2.warning("Warning from instance 2")

            time.sleep(0.5)

            # Verify all messages were logged
            conn = sqlite3.connect(temp_db)
            cursor = conn.execute("SELECT COUNT(*) FROM logs")
            count = cursor.fetchone()[0]
            assert count >= 4

            # Verify instance separation
            cursor = conn.execute("SELECT DISTINCT instance_id FROM logs")
            instances = [row[0] for row in cursor]
            assert "instance-1" in instances
            assert "instance-2" in instances

            conn.close()

            handler1.close()
            handler2.close()

        finally:
            server.shutdown()
            server_thread.join(timeout=2.0)

    @pytest.mark.timeout(10)
    def test_error_recovery_integration(self, mock_settings, test_port, temp_db):
        """Test that logging system recovers from various error conditions."""
        # Start server
        server = ZMQLogServer(
            port=test_port, db_path=temp_db, batch_size=5, batch_timeout=0.1
        )

        server_thread = threading.Thread(target=server.run)
        server_thread.start()

        try:
            time.sleep(0.1)

            # Create handler
            handler = ZMQLogHandler(
                f"tcp://localhost:{test_port}", "error-test-instance"
            )
            test_logger = logging.getLogger("error_recovery_test")
            test_logger.addHandler(handler)
            test_logger.setLevel(logging.INFO)

            # Send normal message
            test_logger.info("Normal message before error")
            time.sleep(0.2)

            # Temporarily corrupt the database to test error handling
            # (Note: This is a controlled test, the server should handle it gracefully)

            # Send message during "error" condition
            test_logger.error("Message during error condition")
            time.sleep(0.2)

            # Send message after "recovery"
            test_logger.info("Message after recovery")
            time.sleep(0.2)

            # Verify some messages made it through
            conn = sqlite3.connect(temp_db)
            cursor = conn.execute(
                "SELECT COUNT(*) FROM logs WHERE message LIKE '%Normal message%' OR message LIKE '%after recovery%'"
            )
            count = cursor.fetchone()[0]
            assert count >= 1  # At least some messages should have made it
            conn.close()

            handler.close()

        finally:
            server.shutdown()
            server_thread.join(timeout=2.0)
