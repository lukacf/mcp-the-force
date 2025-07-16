#!/usr/bin/env python3
"""
Wrapper that starts the MCP server with remote debugging capability.
This allows us to break into the debugger from another session.
"""

import sys
import os
import threading
import socket
import pdb

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Global debugger trigger
debug_trigger = threading.Event()


def debug_listener():
    """Listen on a socket for debug commands."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("localhost", 9999))
    sock.listen(1)

    print("[DEBUG] Listening on localhost:9999 for debug commands", file=sys.stderr)

    while True:
        conn, addr = sock.accept()
        data = conn.recv(1024).decode().strip()

        if data == "BREAK":
            print(f"[DEBUG] Break command received from {addr}", file=sys.stderr)
            debug_trigger.set()
            conn.send(b"OK\n")
        else:
            conn.send(b"UNKNOWN\n")

        conn.close()


# Start debug listener in background
listener_thread = threading.Thread(target=debug_listener, daemon=True)
listener_thread.start()

# Patch the operation manager to check for debug breaks
from mcp_second_brain.operation_manager import OperationManager

original_run_with_timeout = OperationManager.run_with_timeout


async def debug_aware_run_with_timeout(self, operation_id: str, coro, timeout: int):
    """Check for debug trigger before running operation."""
    if debug_trigger.is_set():
        debug_trigger.clear()
        print(f"\n[DEBUG] Breaking at operation: {operation_id}", file=sys.stderr)
        print(
            "[DEBUG] You are now in pdb. Commands: n(ext), s(tep), c(ontinue), l(ist), p <var>",
            file=sys.stderr,
        )
        pdb.set_trace()

    # Call original
    return await original_run_with_timeout(self, operation_id, coro, timeout)


# Apply patch
OperationManager.run_with_timeout = debug_aware_run_with_timeout

print("[DEBUG] Debug wrapper installed. To trigger debugger:", file=sys.stderr)
print("[DEBUG]   echo 'BREAK' | nc localhost 9999", file=sys.stderr)
print("[DEBUG] Starting MCP server...", file=sys.stderr)

# Now run the server
from mcp_second_brain.server import main

main()
