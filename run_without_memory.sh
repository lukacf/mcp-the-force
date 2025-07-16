#!/bin/bash
# Run the MCP server with memory storage disabled

echo "Starting MCP second-brain server with memory storage DISABLED..."
echo "This should prevent the 'Request already responded to' error when aborting operations."
echo ""

export MEMORY_ENABLED=false
uv run -- mcp-second-brain