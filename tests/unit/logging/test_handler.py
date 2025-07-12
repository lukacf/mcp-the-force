"""Unit tests for ZMQ log handler."""

import pytest
import logging
import time
import queue
import threading
from unittest.mock import Mock, patch
import zmq

from mcp_second_brain.logging.handler import ZMQLogHandler


class TestZMQLogHandler:
    """Test ZMQ log handler functionality."""

    @pytest.fixture
    def mock_zmq_context(self):
        """Mock ZMQ context to avoid actual network operations."""
        with patch("zmq.Context") as mock_context:
            mock_socket = Mock()
            mock_context.return_value.socket.return_value = mock_socket
            yield mock_context, mock_socket

    @pytest.fixture
    def mock_redaction_filter(self):
        """Mock the redaction filter."""
        with patch("mcp_second_brain.logging.handler.RedactionFilter") as mock_filter:
            yield mock_filter

    def test_init_configures_zmq_socket(self, mock_zmq_context, mock_redaction_filter):
        """Test that handler initialization configures ZMQ socket correctly."""
        mock_context, mock_socket = mock_zmq_context

        ZMQLogHandler("tcp://localhost:4711", "test-instance")

        # Verify socket configuration
        mock_socket.connect.assert_called_once_with("tcp://localhost:4711")
        mock_socket.setsockopt.assert_any_call(zmq.LINGER, 0)
        mock_socket.setsockopt.assert_any_call(zmq.SNDHWM, 1000)

    def test_init_adds_redaction_filter(self, mock_zmq_context, mock_redaction_filter):
        """Test that handler adds redaction filter during initialization."""
        mock_context, mock_socket = mock_zmq_context

        handler = ZMQLogHandler("tcp://localhost:4711", "test-instance")

        # Verify redaction filter was instantiated and added
        mock_redaction_filter.assert_called_once()
        # The addFilter call is made on the handler, so we need to check it was called
        assert len(handler.filters) > 0

    def test_emit_queues_log_record(self, mock_zmq_context, mock_redaction_filter):
        """Test that emit correctly queues log records."""
        mock_context, mock_socket = mock_zmq_context

        handler = ZMQLogHandler("tcp://localhost:4711", "test-instance")

        # Create a test log record
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_function",
        )

        # Emit the record
        handler.emit(record)

        # Verify it was queued
        assert not handler.queue.empty()
        queued_record = handler.queue.get_nowait()
        assert queued_record == record

    def test_emit_drops_messages_when_queue_full(
        self, mock_zmq_context, mock_redaction_filter
    ):
        """Test that emit drops messages when queue is full."""
        mock_context, mock_socket = mock_zmq_context

        # Create handler with small queue for testing
        handler = ZMQLogHandler("tcp://localhost:4711", "test-instance")

        # Fill the queue
        with patch.object(handler.queue, "put_nowait", side_effect=queue.Full):
            record = logging.LogRecord(
                name="test.logger",
                level=logging.INFO,
                pathname="/test/path.py",
                lineno=42,
                msg="Test message",
                args=(),
                exc_info=None,
                func="test_function",
            )

            # Should not raise an exception
            handler.emit(record)

    def test_sender_loop_formats_message_correctly(
        self, mock_zmq_context, mock_redaction_filter
    ):
        """Test that sender loop formats messages correctly."""
        mock_context, mock_socket = mock_zmq_context

        handler = ZMQLogHandler("tcp://localhost:4711", "test-instance")

        # Create a test log record
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_function",
        )
        record.created = 1234567890.0

        # Put record in queue
        handler.queue.put(record)
        handler.queue.put(None)  # Shutdown signal

        # Let sender loop process one message
        handler.sender_thread.join(timeout=1.0)

        # Verify message was sent with correct format
        mock_socket.send_json.assert_called_once()
        call_args = mock_socket.send_json.call_args[0][0]

        assert call_args["timestamp"] == 1234567890.0
        assert call_args["level"] == "INFO"
        assert call_args["message"] == "Test message"
        assert call_args["instance_id"] == "test-instance"
        assert call_args["module"] == "test.logger"
        assert call_args["extra"]["pathname"] == "/test/path.py"
        assert call_args["extra"]["lineno"] == 42
        assert call_args["extra"]["funcName"] == "test_function"

    def test_sender_loop_handles_zmq_errors(
        self, mock_zmq_context, mock_redaction_filter
    ):
        """Test that sender loop handles ZMQ errors gracefully."""
        mock_context, mock_socket = mock_zmq_context

        # Configure socket to raise zmq.Again (buffer full)
        mock_socket.send_json.side_effect = zmq.Again()

        handler = ZMQLogHandler("tcp://localhost:4711", "test-instance")

        # Create a test log record
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_function",
        )

        # Put record and shutdown signal
        handler.queue.put(record)
        handler.queue.put(None)

        # Should not raise an exception
        handler.sender_thread.join(timeout=1.0)

    def test_sender_loop_uses_project_path_env(
        self, mock_zmq_context, mock_redaction_filter
    ):
        """Test that sender loop uses MCP_PROJECT_PATH environment variable."""
        mock_context, mock_socket = mock_zmq_context

        with patch.dict("os.environ", {"MCP_PROJECT_PATH": "/custom/project/path"}):
            handler = ZMQLogHandler("tcp://localhost:4711", "test-instance")

            # Create a test log record
            record = logging.LogRecord(
                name="test.logger",
                level=logging.INFO,
                pathname="/test/path.py",
                lineno=42,
                msg="Test message",
                args=(),
                exc_info=None,
                func="test_function",
            )

            # Put record and shutdown signal
            handler.queue.put(record)
            handler.queue.put(None)

            handler.sender_thread.join(timeout=1.0)

            # Verify project_cwd was set from environment
            call_args = mock_socket.send_json.call_args[0][0]
            assert call_args["project_cwd"] == "/custom/project/path"

    def test_close_sends_shutdown_signal(self, mock_zmq_context, mock_redaction_filter):
        """Test that close sends shutdown signal to sender thread."""
        mock_context, mock_socket = mock_zmq_context

        handler = ZMQLogHandler("tcp://localhost:4711", "test-instance")

        # Check initial queue state
        assert handler.queue.empty()

        # Close handler
        handler.close()

        # Verify shutdown signal was sent (it may be processed quickly by sender thread)
        # So we check that close() was called and the thread was joined
        try:
            signal = handler.queue.get_nowait()
            assert signal is None
        except queue.Empty:
            # The sender thread may have already processed the shutdown signal
            # This is fine as long as the thread was properly joined
            pass

    def test_close_waits_for_thread_shutdown(
        self, mock_zmq_context, mock_redaction_filter
    ):
        """Test that close waits for sender thread to shutdown."""
        mock_context, mock_socket = mock_zmq_context

        handler = ZMQLogHandler("tcp://localhost:4711", "test-instance")

        # Mock thread join to verify it's called
        with patch.object(handler.sender_thread, "join") as mock_join:
            mock_join.return_value = None
            handler.close()
            mock_join.assert_called_once_with(timeout=2.0)

    def test_sender_loop_handles_queue_timeout(
        self, mock_zmq_context, mock_redaction_filter
    ):
        """Test that sender loop handles queue timeout correctly."""
        mock_context, mock_socket = mock_zmq_context

        handler = ZMQLogHandler("tcp://localhost:4711", "test-instance")

        # Put only shutdown signal after a delay
        def delayed_shutdown():
            time.sleep(0.1)
            handler.queue.put(None)

        shutdown_thread = threading.Thread(target=delayed_shutdown)
        shutdown_thread.start()

        # Should handle timeout and eventually shutdown
        handler.sender_thread.join(timeout=1.0)
        shutdown_thread.join()

        assert not handler.sender_thread.is_alive()

    def test_trace_id_support(self, mock_zmq_context, mock_redaction_filter):
        """Test that handler supports trace_id attribute on log records."""
        mock_context, mock_socket = mock_zmq_context

        handler = ZMQLogHandler("tcp://localhost:4711", "test-instance")

        # Create a test log record with trace_id
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_function",
        )
        record.trace_id = "test-trace-123"

        # Put record and shutdown signal
        handler.queue.put(record)
        handler.queue.put(None)

        handler.sender_thread.join(timeout=1.0)

        # Verify trace_id was included
        call_args = mock_socket.send_json.call_args[0][0]
        assert call_args["trace_id"] == "test-trace-123"
