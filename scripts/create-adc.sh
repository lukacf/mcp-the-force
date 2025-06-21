#!/usr/bin/env bash
set -euo pipefail

# Create Google Application Default Credentials from environment variables
# This keeps OAuth credentials out of the repository

# 1) Refresh token is required (from CI secrets or local .env)
REFRESH_TOKEN=${GCLOUD_USER_REFRESH_TOKEN:?GCLOUD_USER_REFRESH_TOKEN is required}

# 2) Use custom OAuth client or fall back to gcloud CLI's public client
# These are the official gcloud CLI OAuth credentials - safe to use as defaults
CLIENT_ID=${GCLOUD_OAUTH_CLIENT_ID:-764086051850-6qr4p6gpi6hn506pt8ejuq83di341hur.apps.googleusercontent.com}
CLIENT_SECRET=${GCLOUD_OAUTH_CLIENT_SECRET:-d-FL95Q19q7MQmFpd7hHD0Ty}

# 3) Create temporary ADC file
ADC_PATH=${ADC_PATH:-$(mktemp -t gcp_adc_XXXXXX.json)}

cat >"$ADC_PATH" <<JSON
{
  "type": "authorized_user",
  "client_id": "${CLIENT_ID}",
  "client_secret": "${CLIENT_SECRET}",
  "refresh_token": "${REFRESH_TOKEN}"
}
JSON

# Secure the file
chmod 600 "$ADC_PATH"

# Export for use by Google Cloud libraries
export GOOGLE_APPLICATION_CREDENTIALS="$ADC_PATH"
echo "Created ADC at: $ADC_PATH"

# Optional: Set up cleanup on exit
# trap 'rm -f "$ADC_PATH"' EXIT