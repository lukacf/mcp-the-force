#!/usr/bin/env python3
"""
Create a modified version of the server that can be debugged interactively.
"""

import sys
import os
import signal
import threading
import time

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Global flag for debugging
debug_break = False

def signal_handler(signum, frame):
    """Handle SIGUSR1 to break into debugger."""
    global debug_break
    debug_break = True
    print("\n[DEBUGGER] Signal received! Will break at next opportunity...", file=sys.stderr)

# Install signal handler
signal.signal(signal.SIGUSR1, signal_handler)

# Patch the operation manager to check for debug breaks
from mcp_second_brain import operation_manager
original_run_with_timeout = operation_manager.operation_manager.run_with_timeout

async def debug_run_with_timeout(self, operation_id, coro, timeout):
    """Wrapped version that can break into debugger."""
    global debug_break
    
    # Check if we should break
    if debug_break:
        debug_break = False
        print(f"\n[DEBUGGER] Breaking at operation: {operation_id}", file=sys.stderr)
        import pdb
        pdb.set_trace()
    
    # Call original
    return await original_run_with_timeout(self, operation_id, coro, timeout)

# Apply the patch
operation_manager.operation_manager.run_with_timeout = debug_run_with_timeout.__get__(
    operation_manager.operation_manager, 
    operation_manager.OperationManager
)

print(f"[DEBUGGER] Process PID: {os.getpid()}", file=sys.stderr)
print(f"[DEBUGGER] Send 'kill -USR1 {os.getpid()}' to break into debugger", file=sys.stderr)
print(f"[DEBUGGER] Debugger injection complete. Starting server...", file=sys.stderr)

# Now run the actual server
from mcp_second_brain.server import main
main()