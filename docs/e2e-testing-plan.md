# E2E Testing Plan for MCP Second-Brain

## Overview

End-to-end tests will use Claude Code (CC) running in a Docker container to test the actual MCP server integration. This tests the real stdio protocol communication between CC and the MCP server.

## Architecture

### 1. Docker Environment Setup

```dockerfile
# Dockerfile.e2e
FROM ubuntu:22.04

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 python3-pip curl git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for Python package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:${PATH}"

# Install Claude Code
RUN pip install claude-code

# Copy local mcp-second-brain package
COPY . /mcp-second-brain
WORKDIR /mcp-second-brain

# Install mcp-second-brain as editable package
RUN uv pip install -e .

# Setup Claude Code configuration
RUN mkdir -p ~/.config/claude-code
COPY tests/e2e/claude-config.json ~/.config/claude-code/config.json
```

### 2. Claude Code MCP Configuration

```json
// tests/e2e/claude-config.json
{
  "mcpServers": {
    "second-brain": {
      "command": "uv",
      "args": ["run", "--", "mcp-second-brain"],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "VERTEX_PROJECT": "test-project",
        "VERTEX_LOCATION": "us-central1"
      }
    }
  }
}
```

### 3. E2E Test Scenarios

1. **List Models Test**: Verify `list_models` tool works
2. **Simple Query Test**: Use `chat_with_gemini25_flash` for a basic query
3. **File Context Test**: Use `chat_with_o3` with file context
4. **Multi-file Test**: Use `chat_with_gpt4_1` with multiple files
5. **Vector Store Test**: Create a vector store with `create_vector_store_tool`
6. **Session Test**: Test multi-turn conversation with session_id
7. **Error Handling Test**: Test with missing API keys

### 4. Test Runner Script

```python
# tests/e2e/run_e2e_tests.py
import subprocess
import json
import sys
import time

def run_test(name, command, expected_output=None, should_fail=False):
    """Run a single E2E test and check output"""
    print(f"\n=== Running: {name} ===")
    result = subprocess.run(
        command, 
        shell=True, 
        capture_output=True, 
        text=True,
        timeout=60  # 60 second timeout
    )
    
    if should_fail:
        if result.returncode == 0:
            print(f"FAILED: {name} - Expected failure but succeeded")
            return False
    else:
        if result.returncode != 0:
            print(f"FAILED: {name}")
            print(f"Error: {result.stderr}")
            return False
    
    if expected_output and expected_output not in result.stdout:
        print(f"FAILED: {name} - Output validation failed")
        print(f"Expected: {expected_output}")
        print(f"Got: {result.stdout[:200]}...")
        return False
    
    print(f"PASSED: {name}")
    return True

def main():
    tests = [
        ("List Models", 
         'claude-code -p "Use the second-brain MCP server list_models tool to show available models"',
         "gemini25_pro"),
         
        ("Gemini Flash Query", 
         'claude-code -p "Use chat_with_gemini25_flash to explain Python decorators in exactly 2 sentences"',
         None),
         
        ("File Analysis", 
         'echo "def hello(): pass" > /tmp/test.py && claude-code -p "Use chat_with_o3 with context [\\"/tmp/test.py\\\"] to analyze this code"',
         None),
         
        ("Vector Store Creation", 
         'claude-code -p "Use create_vector_store_tool with files [\\"/mcp-second-brain/README.md\\\"]"',
         "vector_store_id"),
         
        ("Missing API Key", 
         'OPENAI_API_KEY="" claude-code -p "Use chat_with_o3 to say hello"',
         None,
         True),  # Should fail
    ]
    
    passed = 0
    for test in tests:
        if run_test(*test):
            passed += 1
    
    print(f"\n=== Results: {passed}/{len(tests)} passed ===")
    return 0 if passed == len(tests) else 1

if __name__ == "__main__":
    sys.exit(main())
```

### 5. GitHub Actions Integration

```yaml
# .github/workflows/ci.yml (updated)
name: CI

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install uv
          uv pip install -e ".[dev]"
      - name: Run unit/integration tests
        run: pytest -xvs --ignore=tests/e2e

  e2e-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    steps:
      - uses: actions/checkout@v3
      - name: Build E2E Docker image
        run: docker build -f Dockerfile.e2e -t mcp-e2e .
      - name: Run E2E tests
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          docker run \
            -e OPENAI_API_KEY \
            -e ANTHROPIC_API_KEY \
            mcp-e2e python tests/e2e/run_e2e_tests.py
```

## Implementation Steps

1. Create `docs/e2e-testing-plan.md` (this file)
2. Create `Dockerfile.e2e` 
3. Create `tests/e2e/claude-config.json`
4. Create `tests/e2e/run_e2e_tests.py`
5. Update GitHub Actions workflow
6. Test locally with Docker
7. Deploy to CI

## Benefits

- Tests actual MCP stdio protocol integration
- Tests real Claude Code interaction
- Catches issues that mocked tests miss
- Validates end-user experience
- Simple and focused test scenarios