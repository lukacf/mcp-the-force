#!/usr/bin/env python3
"""
Debug version of the MCP server that enables remote debugging.
This allows us to attach a debugger from another process.
"""

import sys
import os

# Add the project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Enable remote debugging with debugpy
import debugpy

# Configure debugpy to listen on a port
debugpy.listen(5678)
print("Debugger listening on port 5678")
print("You can now attach a debugger to this process")
print("Waiting for debugger to attach...")

# Wait for debugger to attach before continuing
debugpy.wait_for_client()
print("Debugger attached!")

# Now import and run the actual server
from mcp_second_brain.server import main

if __name__ == "__main__":
    main()
