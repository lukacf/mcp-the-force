#!/bin/bash
# Script to run E2E tests with proper credentials

# Check if required environment variables are set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY environment variable is not set"
    exit 1
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "Error: ANTHROPIC_API_KEY environment variable is not set"
    exit 1
fi

if [ -z "$VERTEX_PROJECT" ]; then
    echo "Error: VERTEX_PROJECT environment variable is not set"
    exit 1
fi

if [ -z "$VERTEX_LOCATION" ]; then
    echo "Error: VERTEX_LOCATION environment variable is not set"
    exit 1
fi

# Check for Google Cloud credentials
GCLOUD_CREDS="$HOME/.config/gcloud/application_default_credentials.json"
if [ ! -f "$GCLOUD_CREDS" ]; then
    echo "Error: Google Cloud credentials not found at $GCLOUD_CREDS"
    echo "Please run: gcloud auth application-default login"
    exit 1
fi

# Build the Docker image
echo "Building E2E test Docker image..."
docker build -f Dockerfile.e2e -t mcp-e2e-test .

# Run the tests
echo "Running E2E tests..."
docker run --rm \
  -e CI_E2E=1 \
  -e OPENAI_API_KEY="${OPENAI_API_KEY}" \
  -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
  -e VERTEX_PROJECT="${VERTEX_PROJECT}" \
  -e VERTEX_LOCATION="${VERTEX_LOCATION}" \
  -e GOOGLE_APPLICATION_CREDENTIALS="/tmp/gcloud/application_default_credentials.json" \
  -v "$GCLOUD_CREDS:/tmp/gcloud/application_default_credentials.json:ro" \
  mcp-e2e-test "$@"