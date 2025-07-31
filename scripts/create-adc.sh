#!/usr/bin/env bash
set -euo pipefail

# Create Google Application Default Credentials from environment variables
# This keeps OAuth credentials out of the repository

# 1) Refresh token is required (from CI secrets or local .env)
REFRESH_TOKEN=${GCLOUD_USER_REFRESH_TOKEN:?GCLOUD_USER_REFRESH_TOKEN is required}

# 2) OAuth client credentials are required
# Get these from your Google Cloud project or use gcloud CLI's credentials
CLIENT_ID=${GCLOUD_OAUTH_CLIENT_ID:?GCLOUD_OAUTH_CLIENT_ID is required}
CLIENT_SECRET=${GCLOUD_OAUTH_CLIENT_SECRET:?GCLOUD_OAUTH_CLIENT_SECRET is required}

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

# Note: No cleanup trap needed - this script is designed for CI environments
# where credentials must persist for the duration of the job/session.
# The CI environment itself is ephemeral and will be cleaned up entirely.