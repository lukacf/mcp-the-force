# MCP Second-Brain Tests

This directory contains the test suite for the MCP Second-Brain server.

## Test Structure

- `unit/` - Pure Python unit tests (no external dependencies)
- `internal/` - Integration tests for internal components (uses MockAdapter)
- `integration_mcp/` - MCP protocol integration tests (uses MockAdapter)
- `e2e/` - End-to-end tests with real adapters (requires API keys)

## Running Tests

### Unit Tests
```bash
# No special setup required
pytest tests/unit -v
```

### Internal Integration Tests
```bash
# Requires MCP_ADAPTER_MOCK=1 to use mock adapters
MCP_ADAPTER_MOCK=1 pytest tests/internal -v
```

### MCP Integration Tests
```bash
# Requires MCP_ADAPTER_MOCK=1 to use mock adapters
MCP_ADAPTER_MOCK=1 pytest tests/integration_mcp -v
```

### E2E Tests
```bash
# Requires real API keys
export OPENAI_API_KEY="your-key"
export VERTEX_PROJECT="your-project"
export VERTEX_LOCATION="us-central1"
pytest tests/e2e -v
```

## CI Configuration

In CI, the environment variables are set automatically:
- Unit tests: Run without special configuration
- Internal tests: `MCP_ADAPTER_MOCK=1` is set by CI
- MCP tests: `MCP_ADAPTER_MOCK=1` is set by CI
- E2E tests: Only run when API keys are available (not for external PRs)

## Mock Adapter

The MockAdapter is activated when `MCP_ADAPTER_MOCK=1` is set **before** importing any modules. This replaces all real adapters with a mock that returns predictable responses without making API calls.

Important: The environment variable must be set before Python imports the adapters module, otherwise the real adapters will be registered and API calls will be attempted.