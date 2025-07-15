#!/usr/bin/env python3
"""
Real-time viewer for cancellation trace.
Run this in a separate terminal while testing aborts.
"""

import time
import os
from datetime import datetime

def follow_file(filename):
    """Follow a file like tail -f"""
    with open(filename, 'r') as f:
        # Go to end of file
        f.seek(0, 2)
        
        while True:
            line = f.readline()
            if line:
                # Color code by level
                if "[CANCEL]" in line:
                    print(f"\033[91m{line}\033[0m", end='')  # Red
                elif "[TIMEOUT]" in line:
                    print(f"\033[93m{line}\033[0m", end='')  # Yellow
                elif "[ERROR]" in line:
                    print(f"\033[91m{line}\033[0m", end='')  # Red
                elif "[OPERATION]" in line:
                    print(f"\033[94m{line}\033[0m", end='')  # Blue
                elif "[TOOL]" in line:
                    print(f"\033[92m{line}\033[0m", end='')  # Green
                elif "[RESPONSE]" in line:
                    print(f"\033[95m{line}\033[0m", end='')  # Magenta
                else:
                    print(line, end='')
            else:
                time.sleep(0.1)

if __name__ == "__main__":
    print("=== Cancellation Trace Viewer ===")
    print("Waiting for trace events...")
    print("(Start MCP server with trace_cancellation.py in another terminal)")
    print("-" * 60)
    
    trace_file = "cancellation_trace.log"
    
    # Wait for file to exist
    while not os.path.exists(trace_file):
        time.sleep(0.5)
    
    try:
        follow_file(trace_file)
    except KeyboardInterrupt:
        print("\n\nViewer stopped.")