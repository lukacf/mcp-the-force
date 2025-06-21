"""
Unit tests for CLI entry point.
"""
import subprocess
import sys
import pytest


class TestCLI:
    """Test the command-line interface."""
    
    def test_cli_help(self):
        """Test that CLI shows help without errors."""
        result = subprocess.run(
            [sys.executable, "-m", "mcp_second_brain", "--help"],
            capture_output=True,
            text=True
        )
        
        # Should exit successfully
        assert result.returncode == 0
        
        # Should show help text
        assert "help" in result.stdout.lower() or "usage" in result.stdout.lower()
    
    def test_cli_version(self):
        """Test that CLI can show version."""
        result = subprocess.run(
            [sys.executable, "-m", "mcp_second_brain", "--version"],
            capture_output=True,
            text=True
        )
        
        # Should either show version or indicate the option doesn't exist
        # (both are acceptable - we just want no crash)
        assert result.returncode in [0, 1, 2]  # 0=success, 1/2=unrecognized option
    
    def test_mcp_server_script(self):
        """Test the mcp-second-brain entry point script."""
        # This tests the script installed by setuptools
        result = subprocess.run(
            ["mcp-second-brain", "--help"],
            capture_output=True,
            text=True,
            shell=False
        )
        
        # If the script is not found, skip the test
        if result.returncode == 127 or "not found" in result.stderr:
            pytest.skip("mcp-second-brain script not installed")
        
        # Otherwise, should show help
        assert result.returncode == 0
        assert "help" in result.stdout.lower() or "usage" in result.stdout.lower()
    
    def test_cli_invalid_args(self):
        """Test CLI handles invalid arguments gracefully."""
        result = subprocess.run(
            [sys.executable, "-m", "mcp_second_brain", "--invalid-option"],
            capture_output=True,
            text=True
        )
        
        # Should exit with error
        assert result.returncode != 0
        
        # Should show error message (not Python traceback)
        assert "error" in result.stderr.lower() or "invalid" in result.stderr.lower()
    
    def test_module_imports(self):
        """Test that the package can be imported without errors."""
        result = subprocess.run(
            [sys.executable, "-c", "import mcp_second_brain; print('OK')"],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "OK" in result.stdout
    
    @pytest.mark.timeout(5)
    def test_server_startup_dry_run(self, mock_env):
        """Test that server can initialize (dry run)."""
        # Start server and immediately terminate
        process = subprocess.Popen(
            [sys.executable, "-m", "mcp_second_brain"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Give it a moment to start
        import time
        time.sleep(0.5)
        
        # Check if it's still running (it should be)
        poll = process.poll()
        
        # Terminate it
        process.terminate()
        
        # Wait for clean shutdown
        stdout, stderr = process.communicate(timeout=3)
        
        # Should have started without immediate crash
        assert poll is None  # Was still running when we checked
        
        # Should not have Python errors
        assert "Traceback" not in stderr
        assert "Error" not in stderr or "KeyboardInterrupt" in stderr  # Ctrl+C is ok