#!/usr/bin/env bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Load .env file if it exists and variables are not already set
if [ -f .env ]; then
    echo -e "${GREEN}Loading environment variables from .env file...${NC}"
    # Export variables from .env only if not already set
    set -a
    source .env
    set +a
fi

# If VERTEX_PROJECT still not set, try to get it from mcp-config.json
if [ -z "$VERTEX_PROJECT" ] && [ -f mcp-config.json ]; then
    echo -e "${GREEN}Loading VERTEX settings from mcp-config.json...${NC}"
    export VERTEX_PROJECT=$(jq -r '.mcpServers."second-brain".env.VERTEX_PROJECT // empty' mcp-config.json)
    export VERTEX_LOCATION=$(jq -r '.mcpServers."second-brain".env.VERTEX_LOCATION // empty' mcp-config.json)
fi

echo -e "${GREEN}Running E2E tests locally with ADC${NC}"

# Check for required environment variables
if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${RED}Error: OPENAI_API_KEY not set${NC}"
    exit 1
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${RED}Error: ANTHROPIC_API_KEY not set${NC}"
    exit 1
fi

if [ -z "$VERTEX_PROJECT" ]; then
    echo -e "${RED}Error: VERTEX_PROJECT not set${NC}"
    exit 1
fi

if [ -z "$VERTEX_LOCATION" ]; then
    echo -e "${YELLOW}Warning: VERTEX_LOCATION not set, defaulting to us-central1${NC}"
    export VERTEX_LOCATION="us-central1"
fi

# Check for project-specific credentials first, then fall back to global ADC
PROJECT_CREDS_PATH="$(pwd)/.gcloud/king_credentials.json"
GLOBAL_ADC_PATH="$HOME/.config/gcloud/application_default_credentials.json"

if [ -f "$PROJECT_CREDS_PATH" ]; then
    ADC_PATH="$PROJECT_CREDS_PATH"
    echo -e "${GREEN}Found project-specific credentials at $ADC_PATH${NC}"
elif [ -f "$GLOBAL_ADC_PATH" ]; then
    ADC_PATH="$GLOBAL_ADC_PATH"
    echo -e "${YELLOW}Using global ADC credentials at $ADC_PATH${NC}"
    echo -e "${YELLOW}Note: For Gemini tests, you may need project-specific credentials${NC}"
else
    echo -e "${RED}Error: No credentials found${NC}"
    echo -e "${YELLOW}Either run 'gcloud auth application-default login' or see README.md for project-specific setup${NC}"
    exit 1
fi

# Check for UID mismatch warning
if [[ "$(id -u)" != "1000" ]]; then
    echo -e "${YELLOW}Warning: Your UID ($(id -u)) differs from container UID (1000)${NC}"
    echo -e "${YELLOW}If you encounter permission errors, run: chmod 644 $ADC_PATH${NC}"
fi

# Build the Docker image
echo -e "${GREEN}Building E2E Docker image...${NC}"
docker build -f tests/e2e/Dockerfile -t mcp-e2e:latest .

# Run the tests with ADC mounted
echo -e "${GREEN}Running E2E tests...${NC}"
docker run --rm \
    -e CI_E2E=1 \
    -e OPENAI_API_KEY="$OPENAI_API_KEY" \
    -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
    -e VERTEX_PROJECT="$VERTEX_PROJECT" \
    -e VERTEX_LOCATION="$VERTEX_LOCATION" \
    -e GOOGLE_APPLICATION_CREDENTIALS="/home/tester/.config/gcloud/application_default_credentials.json" \
    -e LOG_LEVEL="${LOG_LEVEL:-INFO}" \
    -v "$ADC_PATH:/home/tester/.config/gcloud/application_default_credentials.json:ro" \
    mcp-e2e:latest "$@"