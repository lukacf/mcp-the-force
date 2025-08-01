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
the-force-e2e-runner (host container)
├── test-scenario-1-network
│   ├── mcp-server (production build)
│   └── claude-runner (CLI execution)
├── test-scenario-2-network  
│   ├── mcp-server (production build)
│   └── claude-runner (CLI execution)
└── ...
```

## Test Scenarios

All tests run concurrently with 100% pass rate. Each test validates a complete user workflow from Claude CLI through MCP The-Force server to AI models.

### 1. Smoke Test (`test_smoke.py`)
- **Purpose**: Basic health check and core functionality validation
- **Models Used**: Gemini 2.5 Flash (fast response validation)
- **Tests**: 
  - MCP server health check and process validation
  - Model listing and availability verification
  - Simple chat request with structured JSON response
  - Basic tool invocation patterns
- **Duration**: ~75 seconds
- **Key Validation**: End-to-end communication pipeline works correctly

### 2. Context Overflow and RAG Workflow (`test_attachments.py`)
- **Purpose**: Validates the new context overflow mechanism and vector store RAG functionality
- **Models Used**: GPT-4.1 (large context, web search enabled)
- **Tests**:
  - Small files are included inline in the prompt
  - Large files (>250KB) automatically overflow to vector store
  - Model can seamlessly access both inline and vector store content
  - Stable list mechanism across multiple sessions
- **Duration**: ~89 seconds
- **Key Validation**: Context intelligently splits between inline and RAG based on size

### 3. Graceful Failure Handling (`test_failures.py`)
- **Purpose**: Error handling and graceful degradation validation
- **Models Used**: Multiple models (testing error scenarios across different adapters)
- **Tests**:
  - Invalid tool names and malformed parameters
  - Non-existent file paths and permission errors
  - Timeout scenarios and API error responses
  - Error message clarity and user-friendly responses
- **Duration**: ~129 seconds
- **Key Validation**: System fails safely with helpful error messages

### 4. Stable List Context Management (`test_stable_list.py`)
- **Purpose**: Validates the stable-inline list feature for predictable context across sessions
- **Models Used**: GPT-4.1 (best for multi-turn context management)
- **Tests**:
  - Initial context split between inline and vector store based on token budget
  - Context deduplication - unchanged files not resent in subsequent calls
  - Changed file detection - modified files are detected and resent
  - Model can access both directly provided and previously sent content
- **Duration**: ~180 seconds
- **Key Validation**: Stable list ensures consistent context handling across multi-turn conversations

### 5. Priority Context Override (`test_priority_context.py`)
- **Purpose**: Validates priority_context forces files inline regardless of size
- **Models Used**: GPT-4.1 (for testing context limits)
- **Tests**:
  - Large files in priority_context are forced inline (not sent to vector store)
  - File tree accurately reflects inline vs attached files
  - Dynamic overflow when context grows across multiple calls
  - Priority overrides normal token budget calculations
- **Duration**: ~150 seconds
- **Key Validation**: Priority context gives users explicit control over file placement

### 6. Session Management and Isolation (`test_session_management.py`)
- **Purpose**: Comprehensive session state management across models (consolidated from test_history.py and test_cross_model.py)
- **Models Used**: Gemini 2.5 Pro, o3, GPT-4.1 (testing cross-model behavior)
- **Tests**:
  - Session persistence within same session_id
  - Session isolation between different session_ids
  - Cross-model history sharing within same session
  - Parameter validation (reasoning_effort, temperature)
  - Multi-turn conversation context accumulation
- **Duration**: ~250 seconds
- **Key Validation**: Sessions are properly isolated and state persists correctly

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
  the-force-e2e-runner tests/e2e_dind/scenarios/test_smoke.py -v
```

### CI/CD
Each scenario runs as a separate GitHub Actions job for maximum parallelism and isolation.

## Benefits Over Previous Approach

### Eliminates Flakiness
- **No shared state**: Each test gets fresh environment
- **No resource contention**: Limited concurrent API calls
- **No race conditions**: Isolated filesystems and configs
- **Predictable load**: Max API calls = number of scenarios (5)
- **100% Pass Rate**: All tests consistently pass in parallel execution

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
├── README.md                        # This file  
├── Dockerfile.runner                # Test runner image
├── Dockerfile.server               # MCP server image
├── conftest.py                     # pytest fixtures and Docker setup
├── compose/
│   └── stack.yml                  # Docker compose template with shared volumes
└── scenarios/
    ├── test_smoke.py              # Basic health check and simple chat
    ├── test_attachments.py        # Context overflow and RAG workflow
    ├── test_failures.py           # Graceful error handling
    ├── test_stable_list.py        # Stable list context management
    ├── test_priority_context.py   # Priority context override testing
    └── test_session_management.py # Session isolation and persistence
```

## Migration from Old E2E Tests

The old `tests/e2e/` approach had fundamental issues:
- 40+ granular tests (pseudo-unit tests)
- Shared container causing state leakage
- pytest-xdist resource contention
- Fragile subprocess + pipes communication
- Inconsistent pass rates and flaky results

This new approach achieves:
- **6 comprehensive system validation tests** covering all critical functionality:
  * Core system health and basic model functionality
  * Context overflow with automatic split between inline and vector store
  * Error handling and graceful failure scenarios
  * Stable list feature for predictable multi-turn context management
  * Priority context override for explicit file placement control
  * Session isolation and cross-model state management
- **Complete isolation** via Docker-in-Docker with fresh containers per test
- **100% pass rate** with parallel execution at the job level
- **Robust communication** via Docker networks instead of pipes
- **Real E2E validation** from Claude CLI → MCP server → AI models
- **Intelligent context handling** with automatic overflow to vector stores

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