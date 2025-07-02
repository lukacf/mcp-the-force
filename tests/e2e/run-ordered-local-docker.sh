#!/usr/bin/env bash
# Run E2E tests in Docker with ordered execution (simple to complex)
set -euo pipefail

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Build the docker image
echo -e "${GREEN}Building E2E Docker image...${NC}"
docker build -f tests/e2e/Dockerfile.e2e -t mcp-e2e:latest .

# Get current working directory
CWD=$(pwd)

# Read credentials from mcp-config.json
CONFIG_FILE="mcp-config.json"
if [ -f "$CONFIG_FILE" ]; then
    echo -e "${GREEN}Loading VERTEX settings from $CONFIG_FILE...${NC}"
    
    # Parse JSON and export variables
    export VERTEX_PROJECT=$(python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)
    print(config.get('vertex', {}).get('project', ''))
")
    
    export VERTEX_LOCATION=$(python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)
    print(config.get('vertex', {}).get('location', ''))
")
fi

# Check for ADC credentials
ADC_PATH=""
DOCKER_ADC_PATH="/tmp/adc.json"

# Try gcloud ADC path first
GCLOUD_ADC="$HOME/.config/gcloud/application_default_credentials.json"
if [ -f "$GCLOUD_ADC" ]; then
    echo -e "${GREEN}Running E2E tests locally with ADC${NC}"
    echo -e "${GREEN}Found ADC credentials at $GCLOUD_ADC${NC}"
    ADC_PATH="$GCLOUD_ADC"
    
    # Check permissions
    if [ "$(uname)" = "Darwin" ]; then
        # macOS
        USER_UID=$(id -u)
        if [ "$USER_UID" -ne 1000 ]; then
            echo -e "${YELLOW}Warning: Your UID ($USER_UID) differs from container UID (1000)${NC}"
            echo -e "${YELLOW}If you encounter permission errors, run: chmod 644 $ADC_PATH${NC}"
        fi
    fi
else
    echo -e "${RED}No Google Cloud credentials found${NC}"
    echo -e "${RED}Please run 'gcloud auth application-default login' or set GOOGLE_APPLICATION_CREDENTIALS_JSON${NC}"
    exit 1
fi

# Prepare volume mounts
VOLUMES="-v $CWD:/app:ro"
if [ -n "$ADC_PATH" ]; then
    VOLUMES="$VOLUMES -v $ADC_PATH:$DOCKER_ADC_PATH:ro"
fi

# Run docker with ordered tests
echo -e "${GREEN}Running E2E tests in order (simple to complex)...${NC}"

# Use python3 to run ordered tests
docker run --rm \
    -e OPENAI_API_KEY \
    -e ANTHROPIC_API_KEY \
    -e CI_E2E=true \
    -e VERTEX_PROJECT="$VERTEX_PROJECT" \
    -e VERTEX_LOCATION="$VERTEX_LOCATION" \
    -e GOOGLE_APPLICATION_CREDENTIALS="$DOCKER_ADC_PATH" \
    -e HOST=0.0.0.0 \
    -e PORT=8000 \
    -e MCP_ADAPTER_MOCK=0 \
    -e PYTEST_XDIST_WORKER_COUNT="${PYTEST_XDIST_WORKER_COUNT:-4}" \
    $VOLUMES \
    mcp-e2e:latest \
    /entrypoint.sh python3 tests/e2e/run_ordered_tests.py "$@"