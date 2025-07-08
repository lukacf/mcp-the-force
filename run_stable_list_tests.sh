#!/bin/bash
set -e

echo "Running stable list e2e tests..."

# Build the images first
echo "Building Docker images..."
make docker-build

# Run the specific test with verbose output
echo "Running test_stable_list.py..."
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $(pwd):/workspace \
  -e OPENAI_API_KEY="${OPENAI_API_KEY}" \
  -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
  -e VERTEX_PROJECT="${VERTEX_PROJECT:-mcp-test-project}" \
  -e VERTEX_LOCATION="${VERTEX_LOCATION:-us-central1}" \
  -e GOOGLE_APPLICATION_CREDENTIALS_JSON="${GOOGLE_APPLICATION_CREDENTIALS_JSON}" \
  -e GCLOUD_USER_REFRESH_TOKEN="${GCLOUD_USER_REFRESH_TOKEN}" \
  -e GCLOUD_OAUTH_CLIENT_ID="${GCLOUD_OAUTH_CLIENT_ID}" \
  -e GCLOUD_OAUTH_CLIENT_SECRET="${GCLOUD_OAUTH_CLIENT_SECRET}" \
  -e E2E_ARTIFACT_DIR="/tmp/e2e-artifacts" \
  -w /workspace \
  mcp-e2e-runner tests/e2e_dind/scenarios/test_stable_list.py -xvs --tb=short