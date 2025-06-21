#!/bin/bash
# Run tests locally

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "🧪 Running MCP Second-Brain Tests"
echo "================================"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo -e "${RED}Error: uv is not installed. Please install with: pip install uv${NC}"
    exit 1
fi

# Install test dependencies if needed
echo "📦 Installing dependencies..."
uv pip install -e ".[test]"

# Run unit tests
echo -e "\n${GREEN}Running unit tests...${NC}"
pytest tests/unit -v

# Run integration tests
echo -e "\n${GREEN}Running integration tests...${NC}"
pytest tests/integration -v

# Optionally run E2E tests
if [ "$1" == "--e2e" ]; then
    echo -e "\n${GREEN}Running E2E tests...${NC}"
    cd tests/e2e
    docker-compose up --build --abort-on-container-exit --exit-code-from test-runner
    cd ../..
fi

echo -e "\n${GREEN}✅ All tests passed!${NC}"