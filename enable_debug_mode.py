#!/usr/bin/env python3
"""
Enable debug mode for MCP server by setting environment variables.
This will make the server start with debugging hooks when Claude spawns it.
"""

import os
import json

# Set debug environment variables
debug_env = {
    "MCP_DEBUG_MODE": "1",
    "MCP_DEBUG_CANCELLATION": "1",
    "MCP_DEBUG_TRACE": "1"
}

print("To enable debug mode for MCP server, add these environment variables to your Claude Code settings:")
print("\nIn Claude Code's MCP configuration, add an 'env' section:")
print(json.dumps({"env": debug_env}, indent=2))

print("\nOr export them in your shell before starting Claude Code:")
for key, value in debug_env.items():
    print(f"export {key}={value}")

print("\nThen the MCP server will start with debugging enabled when Claude spawns it.")