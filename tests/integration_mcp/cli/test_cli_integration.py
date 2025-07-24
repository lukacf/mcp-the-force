"""
Integration tests for CLI entry point.

These tests spawn actual Python subprocesses to test the full CLI behavior.
"""

import subprocess
import sys
import pytest
import io
from contextlib import redirect_stdout


class TestCLI:
    """Test the command-line interface."""

    def test_cli_help(self):
        """Test that CLI shows help without errors."""
        result = subprocess.run(
            [sys.executable, "-m", "mcp_the_force", "--help"],
            capture_output=True,
            text=True,
        )

        # Should exit successfully
        assert result.returncode == 0

        # Should show help text
        assert "mcp-the-force" in result.stdout
        assert "Usage:" in result.stdout
        assert "--help" in result.stdout

    def test_cli_version(self):
        """Test that CLI shows version."""
        result = subprocess.run(
            [sys.executable, "-m", "mcp_the_force", "--version"],
            capture_output=True,
            text=True,
        )

        # Should exit successfully
        assert result.returncode == 0

        # Should show version (format: X.Y.Z)
        assert result.stdout.strip()  # Non-empty
        parts = result.stdout.strip().split(".")
        assert len(parts) >= 2  # At least major.minor

    def test_cli_invalid_args(self):
        """Test CLI handles invalid arguments gracefully."""
        result = subprocess.run(
            [sys.executable, "-m", "mcp_the_force", "--invalid-option"],
            capture_output=True,
            text=True,
        )

        # Should exit with error code 2
        assert result.returncode == 2

        # Should show error message
        assert "Error: Unknown option: --invalid-option" in result.stderr
        assert "Try 'python -m mcp_the_force --help'" in result.stderr

    def test_module_imports(self):
        """Test that the package can be imported without errors."""
        result = subprocess.run(
            [sys.executable, "-c", "import mcp_the_force; print('OK')"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_direct_import_and_help(self):
        """Test that we can import __main__ module and call help directly."""
        # Import and capture help output
        import mcp_the_force.__main__ as main_module

        captured_output = io.StringIO()
        with redirect_stdout(captured_output):
            with pytest.raises(SystemExit) as exc_info:
                # Simulate --help argument
                original_argv = sys.argv
                try:
                    sys.argv = ["mcp_the_force", "--help"]
                    # Re-run the module logic
                    if "--help" in sys.argv:
                        main_module._print_help()
                        sys.exit(0)
                finally:
                    sys.argv = original_argv

        # Should exit with code 0
        assert exc_info.value.code == 0

        # Should have printed help
        output = captured_output.getvalue()
        assert "mcp-the-force" in output
        assert "Model-Context-Protocol server" in output

    def test_valid_arguments_recognized(self):
        """Test that valid arguments are recognized."""
        # Test with valid arguments (shouldn't error)
        result = subprocess.run(
            [sys.executable, "-m", "mcp_the_force", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        # The actual server startup would require proper environment setup,
        # so we just test that the arguments are parsed without error
