"""Debug logger that writes to a file for MCP debugging."""

import time
from pathlib import Path


class DebugLogger:
    """Simple file-based debug logger for MCP where stderr is swallowed."""

    def __init__(self, filename: str = "mcp_debug.log"):
        self.filename = filename
        self._log_path = None
        self._initialized = False

    def _ensure_initialized(self):
        """Lazy initialization to avoid capturing Path.cwd() at import time."""
        if not self._initialized:
            # Use project-local directory for debug logs
            self._log_path = Path.cwd() / ".mcp-the-force" / "debug" / self.filename
            self._log_path.parent.mkdir(parents=True, exist_ok=True)

            # Clear the log on startup
            with open(self._log_path, "w") as f:
                f.write(
                    f"=== MCP Debug Log Started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
                )
            self._initialized = True

    @property
    def log_path(self):
        """Get the log path, initializing if needed."""
        self._ensure_initialized()
        return self._log_path

    def log(self, message: str, level: str = "INFO"):
        """Write a debug message to the log file."""
        self._ensure_initialized()
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        # Safe access to _log_path after initialization
        if self._log_path is not None:
            with open(self._log_path, "a") as f:
                f.write(f"[{timestamp}] [{level}] {message}\n")
                f.flush()

    def info(self, message: str):
        self.log(message, "INFO")

    def debug(self, message: str):
        self.log(message, "DEBUG")

    def warning(self, message: str):
        self.log(message, "WARNING")

    def error(self, message: str):
        self.log(message, "ERROR")

    def critical(self, message: str):
        self.log(message, "CRITICAL")


# Global debug logger instance
debug_logger = DebugLogger()
