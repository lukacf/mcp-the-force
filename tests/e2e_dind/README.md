# Docker-in-Docker E2E Testing

This directory contains the new robust E2E testing system that replaces the flaky pytest-xdist approach.

## Architecture

### Complete Isolation
Each test scenario runs in its own Docker compose stack:
- **Dedicated network**: No cross-test interference
- **Isolated filesystem**: Temporary directories per test
- **Resource limits**: CPU/memory limits prevent contention
- **Clean environment**: Fresh containers for each test

### Docker-in-Docker Setup
```
mcp-e2e-runner (host container)
├── test-scenario-1-network
│   ├── mcp-server (production build)
│   └── claude-runner (CLI execution)
├── test-scenario-2-network  
│   ├── mcp-server (production build)
│   └── claude-runner (CLI execution)
└── ...
```

## Test Scenarios

### 1. Smoke Test (`test_smoke.py`)
- **Purpose**: Basic health check and simple functionality
- **Tests**: Model listing, simple chat, structured requests
- **Duration**: ~30 seconds

### 2. Memory Lifecycle (`test_memory.py`)
- **Purpose**: Session persistence and recall
- **Tests**: Store information, immediate recall, cross-session access
- **Duration**: ~45 seconds

### 3. Attachment Search (`test_attachments.py`)
- **Purpose**: Vector store creation and semantic search
- **Tests**: Document upload, vector store creation, semantic queries
- **Duration**: ~60 seconds

### 4. Large Context (`test_large_context.py`)
- **Purpose**: Handling files that exceed inline context limits
- **Tests**: Large file processing, vector store fallback, specific content retrieval
- **Duration**: ~90 seconds

### 5. Cross-Model Continuity (`test_cross_model.py`)
- **Purpose**: Information sharing between different AI models
- **Tests**: Store with one model, recall with another, session isolation
- **Duration**: ~60 seconds

### 6. Failure Handling (`test_failures.py`)
- **Purpose**: Graceful error handling for invalid requests
- **Tests**: Invalid files, malformed parameters, non-existent tools
- **Duration**: ~45 seconds

## Running Tests

### Local Development
```bash
# Run all scenarios
make e2e

# Run specific scenario (for debugging)
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $(PWD):/workspace \
  -e OPENAI_API_KEY="your-key" \
  -e ANTHROPIC_API_KEY="your-key" \
  -e VERTEX_PROJECT="your-project" \
  mcp-e2e-runner tests/e2e_dind/scenarios/test_smoke.py -v
```

### CI/CD
Each scenario runs as a separate GitHub Actions job for maximum parallelism and isolation.

## Benefits Over Previous Approach

### Eliminates Flakiness
- **No shared state**: Each test gets fresh environment
- **No resource contention**: Limited concurrent API calls
- **No race conditions**: Isolated filesystems and configs
- **Predictable load**: Max API calls = number of scenarios (6)

### Better Developer Experience
- **Clear failure isolation**: Logs belong to specific scenario
- **Faster debugging**: Run individual scenarios
- **Meaningful tests**: Real user workflows, not API edge cases
- **Reliable CI**: Consistent results across runs

### Technical Improvements
- **True E2E testing**: Network boundaries, containerization, production-like setup
- **Automatic log collection**: Container logs attached on failure
- **Resource monitoring**: CPU/memory limits prevent runaway tests
- **Clean teardown**: Complete stack cleanup after each test

## File Structure

```
tests/e2e_dind/
├── README.md                    # This file
├── Dockerfile.runner            # Test runner image
├── Dockerfile.server           # MCP server image
├── conftest.py                 # pytest fixtures
├── compose/
│   └── stack.yml              # Docker compose template
└── scenarios/
    ├── test_smoke.py          # Basic functionality
    ├── test_memory.py         # Session persistence
    ├── test_attachments.py    # Vector store workflow
    ├── test_large_context.py  # Large file handling
    ├── test_cross_model.py    # Cross-model continuity
    └── test_failures.py       # Error handling
```

## Migration from Old E2E Tests

The old `tests/e2e/` approach had fundamental issues:
- 40+ granular tests (pseudo-unit tests)
- Shared container causing state leakage
- pytest-xdist resource contention
- Fragile subprocess + pipes communication

This new approach:
- 6 comprehensive user workflow tests
- Complete isolation via Docker-in-Docker
- Parallel execution at the job level (not process level)
- Robust container-to-container communication

## Troubleshooting

### Test Failures
1. Check scenario-specific logs in CI artifacts
2. Run scenario locally with `-v` flag for verbose output
3. Examine Docker compose logs: `docker logs <container>`

### Local Development Issues
1. Ensure Docker socket is accessible: `ls -la /var/run/docker.sock`
2. Check API keys are set: `echo $OPENAI_API_KEY`
3. Verify Docker has enough resources (4GB+ RAM recommended)

### CI Issues
1. Check GitHub Actions artifacts for container logs
2. Verify secrets are properly configured in repository settings
3. Monitor API quota usage across parallel jobs