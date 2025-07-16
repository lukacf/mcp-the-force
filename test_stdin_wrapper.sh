#!/bin/bash
# Wrapper that tees stdin to a log file before passing to the server

LOG_FILE="/Users/luka/src/cc/mcp-second-brain/stdin_raw.log"

# Clear previous log
echo "=== STDIN WRAPPER STARTED AT $(date) ===" > "$LOG_FILE"

# Use tee to log stdin while passing it through
exec tee -a "$LOG_FILE" | uv run -- mcp-second-brain