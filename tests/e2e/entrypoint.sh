#!/usr/bin/env bash
set -e

# Create Claude Code config at runtime with actual environment variables
claude mcp add-json second-brain "$(cat <<EOF
{
  "command": "uv",
  "args": ["run", "--", "mcp-second-brain"],
  "env": {
    "OPENAI_API_KEY": "${OPENAI_API_KEY}",
    "VERTEX_PROJECT": "${VERTEX_PROJECT}",
    "VERTEX_LOCATION": "${VERTEX_LOCATION}",
    "GOOGLE_APPLICATION_CREDENTIALS": "${GOOGLE_APPLICATION_CREDENTIALS}",
    "MCP_ADAPTER_MOCK": "0"
  },
  "timeoutMs": 180000
}
EOF
)"

# Execute the command passed to docker run (defaults to pytest)
exec "$@"