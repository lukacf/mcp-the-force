"""Debug logger that writes to a file for MCP debugging."""

import time
from pathlib import Path


class DebugLogger:
    """Simple file-based debug logger for MCP where stderr is swallowed."""

    def __init__(self, filename: str = "mcp_debug.log"):
        self.log_path = Path.home() / ".the_force_debug" / filename
        self.log_path.parent.mkdir(exist_ok=True)

        # Clear the log on startup
        with open(self.log_path, "w") as f:
            f.write(
                f"=== MCP Debug Log Started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
            )

    def log(self, message: str, level: str = "INFO"):
        """Write a debug message to the log file."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(self.log_path, "a") as f:
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
