#!/usr/bin/env python3
"""Find the PID of the running MCP second-brain server."""

import psutil
import sys


def find_mcp_server():
    """Find MCP second-brain server process."""
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline", [])
            if cmdline and any("mcp-second-brain" in arg for arg in cmdline):
                print("Found MCP server:")
                print(f"  PID: {proc.info['pid']}")
                print(f"  Command: {' '.join(cmdline)}")
                return proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    print("MCP second-brain server not found")
    return None


if __name__ == "__main__":
    pid = find_mcp_server()
    if pid:
        sys.exit(0)
    else:
        sys.exit(1)
