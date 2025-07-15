#!/usr/bin/env python3
"""Test if disabling memory storage prevents the 'Request already responded to' error."""

import os
import sys

# Disable memory storage before importing anything else
os.environ["MEMORY_ENABLED"] = "false"

print(f"Memory storage disabled: MEMORY_ENABLED={os.environ.get('MEMORY_ENABLED')}")
print("Please start the MCP server and test aborting a long-running operation.")
print("The server should handle the abort gracefully without the 'Request already responded to' error.")