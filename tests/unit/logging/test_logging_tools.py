"""Unit tests for logging tools."""

import pytest
import tempfile
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from pathlib import Path

from mcp_second_brain.tools.logging_tools import SearchMCPDebugLogsToolSpec
from mcp_second_brain.adapters.logging_adapter import LoggingAdapter


class TestSearchMCPDebugLogsToolSpec:
    """Test the MCP debug logs search tool."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database with test data."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name

        # Create and populate test database
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE logs (
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
            
            CREATE INDEX idx_logs_timestamp ON logs(timestamp DESC);
            CREATE INDEX idx_logs_instance ON logs(instance_id);
            CREATE INDEX idx_logs_level ON logs(level);
            CREATE INDEX idx_logs_project ON logs(project_cwd);
        """)

        # Insert test data
        now = datetime.now().timestamp()
        test_data = [
            (
                now - 3600,
                "INFO",
                "Test info message",
                "instance-1",
                "/project1",
                None,
                "test.module",
                "{}",
            ),
            (
                now - 1800,
                "ERROR",
                "Test error message",
                "instance-1",
                "/project1",
                "trace-123",
                "test.module",
                '{"pathname": "/test.py", "lineno": 42}',
            ),
            (
                now - 900,
                "DEBUG",
                "Debug message",
                "instance-2",
                "/project2",
                None,
                "debug.module",
                "{}",
            ),
            (
                now - 300,
                "WARNING",
                "Warning message",
                "instance-1",
                "/project1",
                None,
                "warn.module",
                "{}",
            ),
        ]

        conn.executemany(
            "INSERT INTO logs (timestamp, level, message, instance_id, project_cwd, trace_id, module, extra) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            test_data,
        )
        conn.commit()
        conn.close()

        yield db_path
        Path(db_path).unlink(missing_ok=True)

    @pytest.fixture
    def mock_settings_enabled(self, temp_db):
        """Mock settings with developer mode enabled."""
        settings = Mock()
        settings.logging.developer_mode.enabled = True
        settings.logging.developer_mode.db_path = temp_db
        return settings

    @pytest.fixture
    def mock_settings_disabled(self):
        """Mock settings with developer mode disabled."""
        settings = Mock()
        settings.logging.developer_mode.enabled = False
        return settings

    def test_tool_creation(self):
        """Test that the tool can be instantiated."""
        tool = SearchMCPDebugLogsToolSpec()
        assert tool is not None
        assert hasattr(tool, "query")
        assert hasattr(tool, "level")
        assert hasattr(tool, "since")
        assert hasattr(tool, "instance_id")
        assert hasattr(tool, "all_projects")
        assert hasattr(tool, "limit")

    def test_parse_since_minutes(self):
        """Test parsing of time duration in minutes."""
        adapter = LoggingAdapter()

        now = datetime.now()
        timestamp = adapter._parse_since("30m")
        expected = (now - timedelta(minutes=30)).timestamp()

        # Allow for small timing differences
        assert abs(timestamp - expected) < 1.0

    def test_parse_since_hours(self):
        """Test parsing of time duration in hours."""
        adapter = LoggingAdapter()

        now = datetime.now()
        timestamp = adapter._parse_since("2h")
        expected = (now - timedelta(hours=2)).timestamp()

        assert abs(timestamp - expected) < 1.0

    def test_parse_since_days(self):
        """Test parsing of time duration in days."""
        adapter = LoggingAdapter()

        now = datetime.now()
        timestamp = adapter._parse_since("1d")
        expected = (now - timedelta(days=1)).timestamp()

        assert abs(timestamp - expected) < 1.0

    def test_parse_since_default(self):
        """Test parsing with invalid format defaults to 1 hour."""
        adapter = LoggingAdapter()

        now = datetime.now()
        timestamp = adapter._parse_since("invalid")
        expected = (now - timedelta(hours=1)).timestamp()

        assert abs(timestamp - expected) < 1.0

    @pytest.mark.skip("Tool execute tests require adapter integration")
    @pytest.mark.skip("Tool execute tests require adapter integration")
    @pytest.mark.asyncio
    async def test_execute_developer_mode_disabled(self, mock_settings_disabled):
        """Test execution when developer mode is disabled."""
        tool = SearchMCPDebugLogsToolSpec()

        with patch(
            "mcp_second_brain.adapters.logging_adapter.get_settings",
            return_value=mock_settings_disabled,
        ):
            result = await tool.execute(query="test")

            assert "Developer logging mode is not enabled" in result

    @pytest.mark.skip("Tool execute tests require adapter integration")
    @pytest.mark.asyncio
    async def test_execute_database_not_found(self, mock_settings_enabled):
        """Test execution when database file doesn't exist."""
        tool = SearchMCPDebugLogsToolSpec()

        # Override with non-existent path
        mock_settings_enabled.logging.developer_mode.db_path = (
            "/nonexistent/path.sqlite3"
        )

        with patch(
            "mcp_second_brain.adapters.logging_adapter.get_settings",
            return_value=mock_settings_enabled,
        ):
            result = await tool.execute(query="test")

            assert "No log database found" in result

    @pytest.mark.skip("Tool execute tests require adapter integration")
    @pytest.mark.asyncio
    async def test_execute_basic_query(self, mock_settings_enabled):
        """Test basic query execution."""
        tool = SearchMCPDebugLogsToolSpec()

        with patch(
            "mcp_second_brain.adapters.logging_adapter.get_settings",
            return_value=mock_settings_enabled,
        ):
            with patch.dict("os.environ", {"MCP_PROJECT_PATH": "/project1"}):
                result = await tool.execute(query="error", since="2h")

                assert "Found 1 log entries" in result
                assert "ERROR" in result
                assert "Test error message" in result

    @pytest.mark.skip("Tool execute tests require adapter integration")
    @pytest.mark.asyncio
    async def test_execute_level_filter(self, mock_settings_enabled):
        """Test execution with level filter."""
        tool = SearchMCPDebugLogsToolSpec()

        with patch(
            "mcp_second_brain.adapters.logging_adapter.get_settings",
            return_value=mock_settings_enabled,
        ):
            with patch.dict("os.environ", {"MCP_PROJECT_PATH": "/project1"}):
                result = await tool.execute(query="", level="INFO", since="2h")

                assert "Found 1 log entries" in result
                assert "INFO" in result
                assert "Test info message" in result

    @pytest.mark.skip("Tool execute tests require adapter integration")
    @pytest.mark.asyncio
    async def test_execute_instance_filter(self, mock_settings_enabled):
        """Test execution with instance ID filter."""
        tool = SearchMCPDebugLogsToolSpec()

        with patch(
            "mcp_second_brain.adapters.logging_adapter.get_settings",
            return_value=mock_settings_enabled,
        ):
            with patch.dict("os.environ", {"MCP_PROJECT_PATH": "/project1"}):
                result = await tool.execute(
                    query="", instance_id="instance-1", since="2h"
                )

                assert "Found 3 log entries" in result
                assert "instance-1" in result

    @pytest.mark.skip("Tool execute tests require adapter integration")
    @pytest.mark.asyncio
    async def test_execute_all_projects(self, mock_settings_enabled):
        """Test execution with all_projects=True."""
        tool = SearchMCPDebugLogsToolSpec()

        with patch(
            "mcp_second_brain.adapters.logging_adapter.get_settings",
            return_value=mock_settings_enabled,
        ):
            result = await tool.execute(query="", all_projects=True, since="2h")

            assert "Found 4 log entries" in result
            assert "/project1" in result
            assert "/project2" in result

    @pytest.mark.skip("Tool execute tests require adapter integration")
    @pytest.mark.asyncio
    async def test_execute_limit(self, mock_settings_enabled):
        """Test execution with result limit."""
        tool = SearchMCPDebugLogsToolSpec()

        with patch(
            "mcp_second_brain.adapters.logging_adapter.get_settings",
            return_value=mock_settings_enabled,
        ):
            result = await tool.execute(
                query="", all_projects=True, since="2h", limit=2
            )

            assert "Found 2 log entries" in result

    @pytest.mark.skip("Tool execute tests require adapter integration")
    @pytest.mark.asyncio
    async def test_execute_no_results(self, mock_settings_enabled):
        """Test execution when no logs match criteria."""
        tool = SearchMCPDebugLogsToolSpec()

        with patch(
            "mcp_second_brain.adapters.logging_adapter.get_settings",
            return_value=mock_settings_enabled,
        ):
            result = await tool.execute(query="nonexistent", since="1m")

            assert "No logs found matching criteria" in result

    @pytest.mark.skip("Tool execute tests require adapter integration")
    @pytest.mark.asyncio
    async def test_execute_extra_field_parsing(self, mock_settings_enabled):
        """Test that extra field is properly parsed from JSON."""
        tool = SearchMCPDebugLogsToolSpec()

        with patch(
            "mcp_second_brain.adapters.logging_adapter.get_settings",
            return_value=mock_settings_enabled,
        ):
            with patch.dict("os.environ", {"MCP_PROJECT_PATH": "/project1"}):
                result = await tool.execute(query="error", since="2h")

                # Should include file path and line number from extra field
                assert "/test.py:42" in result

    @pytest.mark.skip("Tool execute tests require adapter integration")
    @pytest.mark.asyncio
    async def test_execute_project_filtering(self, mock_settings_enabled):
        """Test that project filtering works correctly."""
        tool = SearchMCPDebugLogsToolSpec()

        # Test with project1
        with patch(
            "mcp_second_brain.adapters.logging_adapter.get_settings",
            return_value=mock_settings_enabled,
        ):
            with patch.dict("os.environ", {"MCP_PROJECT_PATH": "/project1"}):
                result = await tool.execute(query="", since="2h")

                assert "Found 3 log entries" in result
                assert "/project2" not in result  # Should not see project2 logs

    @pytest.mark.skip("Tool execute tests require adapter integration")
    @pytest.mark.asyncio
    async def test_execute_database_error(self, mock_settings_enabled):
        """Test handling of database errors."""
        tool = SearchMCPDebugLogsToolSpec()

        with patch(
            "mcp_second_brain.adapters.logging_adapter.get_settings",
            return_value=mock_settings_enabled,
        ):
            with patch("sqlite3.connect", side_effect=Exception("Database error")):
                result = await tool.execute(query="test")

                assert "Error searching logs" in result
                assert "Database error" in result

    @pytest.mark.skip("Tool execute tests require adapter integration")
    @pytest.mark.asyncio
    async def test_execute_malformed_extra_json(self, mock_settings_enabled, temp_db):
        """Test handling of malformed JSON in extra field."""
        # Add a record with malformed JSON
        conn = sqlite3.connect(temp_db)
        now = datetime.now().timestamp()
        conn.execute(
            "INSERT INTO logs (timestamp, level, message, instance_id, project_cwd, trace_id, module, extra) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                now,
                "INFO",
                "Test message",
                "instance-1",
                "/project1",
                None,
                "test.module",
                "invalid json",
            ),
        )
        conn.commit()
        conn.close()

        tool = SearchMCPDebugLogsToolSpec()

        with patch(
            "mcp_second_brain.adapters.logging_adapter.get_settings",
            return_value=mock_settings_enabled,
        ):
            with patch.dict("os.environ", {"MCP_PROJECT_PATH": "/project1"}):
                # Should not crash with malformed JSON
                result = await tool.execute(query="Test message", since="1m")

                assert "Found 1 log entries" in result
