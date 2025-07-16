#!/usr/bin/env python3
"""
Simple stdin logger to see what Claude sends after cancellation.
"""

import sys
import json
from datetime import datetime

LOG_FILE = "/Users/luka/src/cc/mcp-second-brain/stdin_messages.log"

def log_message(msg):
    """Log a message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {msg}\n")
        f.flush()

def main():
    """Log all stdin messages."""
    log_message("=== STDIN LOGGER STARTED ===")
    
    try:
        while True:
            line = sys.stdin.readline()
            if not line:
                log_message("EOF received")
                break
                
            log_message(f"RAW: {repr(line.strip())}")
            
            # Try to parse as JSON
            try:
                if line.strip():
                    parsed = json.loads(line.strip())
                    formatted = json.dumps(parsed, indent=2)
                    log_message(f"PARSED:\n{formatted}")
            except Exception as e:
                log_message(f"Parse error: {e}")
                
    except KeyboardInterrupt:
        log_message("Interrupted")
    except Exception as e:
        log_message(f"Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    main()