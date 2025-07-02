#!/usr/bin/env bash
set -e

# Handle Google Cloud authentication
if [ -n "$GCLOUD_USER_REFRESH_TOKEN" ]; then
    echo "Setting up Google Cloud auth from refresh token..."
    
    # OAuth client credentials are required for refresh token auth
    CLIENT_ID=${GCLOUD_OAUTH_CLIENT_ID:?GCLOUD_OAUTH_CLIENT_ID is required for refresh token auth}
    CLIENT_SECRET=${GCLOUD_OAUTH_CLIENT_SECRET:?GCLOUD_OAUTH_CLIENT_SECRET is required for refresh token auth}
    
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

# The Claude tool config is now created per-pytest worker (see conftest.py)
# Do NOT touch ~/.claude.json here – that causes write races.

# Execute the command passed to docker run (defaults to pytest)
exec "$@"