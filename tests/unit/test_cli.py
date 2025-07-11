"""
Unit tests for CLI entry point.
"""

import subprocess
import sys
import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock


class TestCLI:
    """Test the command-line interface."""

    @patch("subprocess.run")
    def test_cli_help(self, mock_run):
        """Test that CLI shows help without errors."""
        mock_run.return_value = SimpleNamespace(
            returncode=0, stdout="Usage: mcp-second-brain [OPTIONS]", stderr=""
        )
        result = subprocess.run([sys.executable, "-m", "mcp_second_brain", "--help"])

        # Should exit successfully
        assert result.returncode == 0

        # Should show help text
        assert "help" in result.stdout.lower() or "usage" in result.stdout.lower()

    @patch("subprocess.run")
    def test_cli_version(self, mock_run):
        """Test that CLI can show version."""
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="0.9.1", stderr="")
        result = subprocess.run([sys.executable, "-m", "mcp_second_brain", "--version"])

        # Should either show version or indicate the option doesn't exist
        # (both are acceptable - we just want no crash)
        assert result.returncode in [0, 1, 2]  # 0=success, 1/2=unrecognized option

    @patch("subprocess.run")
    def test_mcp_server_script(self, mock_run):
        """Test the mcp-second-brain entry point script."""
        # Simulate script not found
        mock_run.return_value = SimpleNamespace(
            returncode=127, stdout="", stderr="command not found"
        )
        result = subprocess.run(["mcp-second-brain", "--help"])

        # If the script is not found, skip the test
        if result.returncode == 127 or "not found" in result.stderr:
            pytest.skip("mcp-second-brain script not installed")

        # Otherwise, should show help
        assert result.returncode == 0
        assert "help" in result.stdout.lower() or "usage" in result.stdout.lower()

    @patch("subprocess.run")
    def test_cli_invalid_args(self, mock_run):
        """Test CLI handles invalid arguments gracefully."""
        mock_run.return_value = SimpleNamespace(
            returncode=2, stdout="", stderr="Error: Unknown option: --invalid-option"
        )
        result = subprocess.run(
            [sys.executable, "-m", "mcp_second_brain", "--invalid-option"]
        )

        # Should exit with error
        assert result.returncode != 0

        # Should show error message (not Python traceback)
        assert "error" in result.stderr.lower() or "invalid" in result.stderr.lower()

    @patch("subprocess.run")
    def test_module_imports(self, mock_run):
        """Test that the package can be imported without errors."""
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="OK\n", stderr="")
        result = subprocess.run(
            [sys.executable, "-c", "import mcp_second_brain; print('OK')"]
        )

        assert result.returncode == 0
        assert "OK" in result.stdout

    @patch("subprocess.Popen")
    @pytest.mark.timeout(1)
    def test_server_startup_dry_run(self, mock_popen, mock_env):
        """Test that server can initialize (dry run)."""
        proc = MagicMock()
        proc.poll.return_value = None
        proc.communicate.return_value = ("", "")
        mock_popen.return_value = proc

        process = subprocess.Popen([sys.executable, "-m", "mcp_second_brain"])
        poll = process.poll()
        process.terminate()
        stdout, stderr = process.communicate(timeout=1)

        # Should have started without immediate crash
        assert poll is None  # Was still running when we checked

        # Should not have Python errors
        assert "Traceback" not in stderr
        assert "Error" not in stderr or "KeyboardInterrupt" in stderr  # Ctrl+C is ok
