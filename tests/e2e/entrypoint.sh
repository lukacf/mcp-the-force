#!/usr/bin/env bash
set -e

# Handle Google Cloud authentication
if [ -n "$GCLOUD_USER_REFRESH_TOKEN" ]; then
    echo "Setting up Google Cloud auth from refresh token..."
    
    # Use custom OAuth client or fall back to gcloud CLI's public client
    CLIENT_ID=${GCLOUD_OAUTH_CLIENT_ID:-764086051850-6qr4p6gpi6hn506pt8ejuq83di341hur.apps.googleusercontent.com}
    CLIENT_SECRET=${GCLOUD_OAUTH_CLIENT_SECRET:-d-FL95Q19q7MQmFpd7hHD0Ty}
    
    # Create ADC file
    ADC_PATH="/tmp/adc.json"
    cat >"$ADC_PATH" <<JSON
{
  "type": "authorized_user",
  "client_id": "${CLIENT_ID}",
  "client_secret": "${CLIENT_SECRET}",
  "refresh_token": "${GCLOUD_USER_REFRESH_TOKEN}"
}
JSON
    
    chmod 600 "$ADC_PATH"
    export GOOGLE_APPLICATION_CREDENTIALS="$ADC_PATH"
    
elif [ -n "$GOOGLE_APPLICATION_CREDENTIALS_JSON" ]; then
    echo "Setting up Google Cloud auth from service account JSON..."
    echo "$GOOGLE_APPLICATION_CREDENTIALS_JSON" > /tmp/service-account.json
    export GOOGLE_APPLICATION_CREDENTIALS="/tmp/service-account.json"
fi

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