"""Unit tests for logging setup module."""

import pytest
import logging
from unittest.mock import Mock, patch
import zmq

from mcp_second_brain.logging.setup import setup_logging, shutdown_logging


class TestLoggingSetup:
    """Test logging setup functionality."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings object for testing."""
        settings = Mock()
        settings.logging.level = "INFO"
        settings.logging.developer_mode.enabled = True
        settings.logging.developer_mode.port = 4711
        settings.logging.developer_mode.db_path = "test.sqlite3"
        settings.logging.developer_mode.batch_size = 100
        settings.logging.developer_mode.batch_timeout = 1.0
        settings.logging.developer_mode.max_db_size_mb = 1000
        settings.logging.developer_mode.handover_timeout = 5.0
        return settings

    @pytest.fixture
    def mock_settings_disabled(self):
        """Mock settings with developer mode disabled."""
        settings = Mock()
        settings.logging.level = "INFO"
        settings.logging.developer_mode.enabled = False
        return settings

    @pytest.fixture
    def mock_zmq_server(self):
        """Mock ZMQ log server."""
        with patch("mcp_second_brain.logging.setup.ZMQLogServer") as mock_server_class:
            mock_server = Mock()
            mock_server_class.return_value = mock_server
            yield mock_server_class, mock_server

    @pytest.fixture
    def mock_zmq_handler(self):
        """Mock ZMQ log handler."""
        with patch(
            "mcp_second_brain.logging.setup.ZMQLogHandler"
        ) as mock_handler_class:
            mock_handler = Mock()
            mock_handler_class.return_value = mock_handler
            yield mock_handler_class, mock_handler

    def test_setup_logging_configures_basic_logging(self, mock_settings):
        """Test that setup_logging configures application logger."""
        with patch(
            "mcp_second_brain.logging.setup.get_settings", return_value=mock_settings
        ):
            with patch("logging.getLogger") as mock_get_logger:
                mock_app_logger = Mock()
                mock_get_logger.return_value = mock_app_logger

                setup_logging()

                # Should configure our app logger with level from settings
                mock_get_logger.assert_called_with("mcp_second_brain")
                mock_app_logger.setLevel.assert_called_with(
                    "INFO"
                )  # From mock_settings
                # propagate should be False to prevent stderr pollution
                assert mock_app_logger.propagate is False

    def test_setup_logging_with_developer_mode_disabled(self, mock_settings_disabled):
        """Test that setup_logging skips ZMQ setup when developer mode is disabled."""
        with patch(
            "mcp_second_brain.logging.setup.get_settings",
            return_value=mock_settings_disabled,
        ):
            with patch("mcp_second_brain.logging.setup.ZMQLogServer") as mock_server:
                setup_logging()

                # Should not attempt to create ZMQ server
                mock_server.assert_not_called()

    def test_setup_logging_starts_zmq_server(
        self, mock_settings, mock_zmq_server, mock_zmq_handler
    ):
        """Test that setup_logging starts ZMQ server when enabled."""
        mock_server_class, mock_server = mock_zmq_server
        mock_handler_class, mock_handler = mock_zmq_handler

        with patch(
            "mcp_second_brain.logging.setup.get_settings", return_value=mock_settings
        ):
            with patch("threading.Thread") as mock_thread:
                with patch("atexit.register") as mock_atexit:
                    # Clear the shutdown registration flag to ensure registration happens
                    if hasattr(setup_logging, "_shutdown_registered"):
                        delattr(setup_logging, "_shutdown_registered")

                    setup_logging()

                    # Verify server was created with correct parameters
                    # Path is resolved by centralization logic
                    import os

                    expected_path = os.path.expanduser("~/.mcp_logs/test.sqlite3")
                    mock_server_class.assert_called_once_with(
                        port=4711,
                        db_path=expected_path,
                        batch_size=100,
                        batch_timeout=1.0,
                    )

                    # Verify thread was started
                    mock_thread.assert_called_once()
                    mock_thread.return_value.start.assert_called_once()

                    # Verify atexit handler was registered
                    mock_atexit.assert_called_once_with(shutdown_logging)

    def test_setup_logging_handles_port_in_use(self, mock_settings, mock_zmq_handler):
        """Test that setup_logging handles port already in use gracefully."""
        mock_handler_class, mock_handler = mock_zmq_handler

        with patch(
            "mcp_second_brain.logging.setup.get_settings", return_value=mock_settings
        ):
            with patch(
                "mcp_second_brain.logging.setup.ZMQLogServer",
                side_effect=zmq.ZMQError("Port in use"),
            ):
                with patch("logging.getLogger") as mock_get_logger:
                    mock_logger = Mock()
                    mock_logger.handlers = []  # Add handlers attribute
                    mock_get_logger.return_value = mock_logger

                    setup_logging()

                    # Should still setup handler even if server fails
                    mock_handler_class.assert_called_once()

    def test_setup_logging_creates_zmq_handler(
        self, mock_settings, mock_zmq_server, mock_zmq_handler, caplog
    ):
        """Test that setup_logging creates and configures ZMQ handler."""
        mock_server_class, mock_server = mock_zmq_server
        mock_handler_class, mock_handler = mock_zmq_handler

        with patch(
            "mcp_second_brain.logging.setup.get_settings", return_value=mock_settings
        ):
            with patch("threading.Thread"):
                with patch("uuid.uuid4") as mock_uuid:
                    mock_uuid.return_value.hex = "abcd1234"
                    with patch("os.getpid", return_value=12345):
                        # Create a mock for the root logger only when called without arguments
                        mock_app_logger = Mock()
                        mock_app_logger.handlers = []
                        # Mock the manager to avoid issues with pytest's logging capture
                        mock_manager = Mock()
                        mock_manager.disable = 0  # Set a valid integer value
                        mock_app_logger.manager = mock_manager

                        # Patch logging.getLogger to mock our app logger call
                        original_get_logger = logging.getLogger

                        def mock_get_logger(name=None):
                            if name == "mcp_second_brain":  # Our app logger
                                return mock_app_logger
                            return original_get_logger(
                                name
                            )  # Let other loggers work normally

                        with patch("logging.getLogger", side_effect=mock_get_logger):
                            with caplog.at_level(logging.INFO):
                                setup_logging()

                                # Verify handler was created with correct parameters
                                mock_handler_class.assert_called_once_with(
                                    "tcp://localhost:4711", "12345-abcd1234", 5.0
                                )

                                # Verify handler was added to app logger
                                mock_app_logger.addHandler.assert_called_once_with(
                                    mock_handler_class.return_value
                                )

    def test_setup_logging_handles_handler_creation_error(
        self, mock_settings, mock_zmq_server, caplog
    ):
        """Test that setup_logging handles handler creation errors gracefully."""
        mock_server_class, mock_server = mock_zmq_server

        with patch(
            "mcp_second_brain.logging.setup.get_settings", return_value=mock_settings
        ):
            with patch("threading.Thread"):
                with patch(
                    "mcp_second_brain.logging.setup.ZMQLogHandler",
                    side_effect=Exception("Handler error"),
                ):
                    # Create a mock for the root logger only when called without arguments
                    mock_root_logger = Mock()
                    mock_root_logger.handlers = []
                    # Mock the manager to avoid issues with pytest's logging capture
                    mock_manager = Mock()
                    mock_manager.disable = 0  # Set a valid integer value
                    mock_root_logger.manager = mock_manager

                    # Patch logging.getLogger to only mock the root logger call
                    original_get_logger = logging.getLogger

                    def mock_get_logger(name=None):
                        if name is None:  # Root logger
                            return mock_root_logger
                        return original_get_logger(
                            name
                        )  # Let other loggers work normally

                    with patch("logging.getLogger", side_effect=mock_get_logger):
                        # Should not raise an exception
                        try:
                            setup_logging()
                        except Exception as e:
                            pytest.fail(f"setup_logging() raised an exception: {e}")

                        # Verify no handler was added to root logger (since creation failed)
                        mock_root_logger.addHandler.assert_not_called()

    def test_shutdown_logging_closes_handler(self, caplog):
        """Test that shutdown_logging closes ZMQ handler."""
        with patch("mcp_second_brain.logging.setup._zmq_handler") as mock_handler:
            mock_handler.close = Mock()

            with caplog.at_level(logging.INFO):
                shutdown_logging()

                mock_handler.close.assert_called_once()
                assert "Shutting down logging system" in caplog.text

    def test_shutdown_logging_shuts_down_server(self, caplog):
        """Test that shutdown_logging shuts down ZMQ server."""
        with patch("mcp_second_brain.logging.setup._log_server") as mock_server:
            with patch("mcp_second_brain.logging.setup._server_thread") as mock_thread:
                mock_server.shutdown = Mock()
                mock_thread.is_alive.return_value = True
                mock_thread.join = Mock()

                with caplog.at_level(logging.INFO):
                    shutdown_logging()

                    mock_server.shutdown.assert_called_once()
                    mock_thread.join.assert_called_once_with(timeout=5.0)
                    assert "Shutting down logging system" in caplog.text

    def test_shutdown_logging_handles_thread_timeout(self, caplog):
        """Test that shutdown_logging handles thread timeout gracefully."""
        with patch("mcp_second_brain.logging.setup._log_server") as mock_server:
            with patch("mcp_second_brain.logging.setup._server_thread") as mock_thread:
                mock_server.shutdown = Mock()
                mock_thread.is_alive.return_value = True
                mock_thread.join = Mock()

                with caplog.at_level(logging.WARNING):
                    shutdown_logging()

                    # Should warn about thread not shutting down cleanly
                    assert (
                        "ZMQ log server thread did not shutdown cleanly" in caplog.text
                    )

    def test_shutdown_logging_handles_errors(self, caplog):
        """Test that shutdown_logging handles errors gracefully."""
        with patch("mcp_second_brain.logging.setup._zmq_handler") as mock_handler:
            mock_handler.close.side_effect = Exception("Handler error")

            with patch("mcp_second_brain.logging.setup._log_server") as mock_server:
                mock_server.shutdown.side_effect = Exception("Server error")

                with caplog.at_level(logging.ERROR):
                    # Should not raise an exception
                    shutdown_logging()

                    # Check that errors were logged
                    assert "Error closing ZMQ handler: Handler error" in caplog.text
                    assert (
                        "Error shutting down ZMQ log server: Server error"
                        in caplog.text
                    )

    def test_multiple_setup_calls_safe(
        self, mock_settings, mock_zmq_server, mock_zmq_handler
    ):
        """Test that multiple setup_logging calls are safe."""
        mock_server_class, mock_server = mock_zmq_server
        mock_handler_class, mock_handler = mock_zmq_handler

        with patch(
            "mcp_second_brain.logging.setup.get_settings", return_value=mock_settings
        ):
            with patch("threading.Thread"):
                with patch("atexit.register"):
                    with patch("logging.getLogger"):
                        # First call
                        setup_logging()
                        # Second call should not crash
                        setup_logging()

    def test_global_variables_reset_properly(self):
        """Test that global variables are properly managed."""
        # Import the module to access globals
        import mcp_second_brain.logging.setup as setup_module

        # Reset globals
        setup_module._log_server = None
        setup_module._server_thread = None
        setup_module._zmq_handler = None

        # Verify they start as None
        assert setup_module._log_server is None
        assert setup_module._server_thread is None
        assert setup_module._zmq_handler is None
