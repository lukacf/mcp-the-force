# Testing Plan for MCP Second-Brain

## Overview

Based on investigation and review, we're implementing a three-layer testing strategy:

1. **Unit Tests** - Fast, isolated component tests (existing)
2. **Integration Tests** - MCP protocol testing with FastMCP Client (priority)
3. **E2E Tests** - Full Docker + Claude Code + real models (future)

## 1. Unit Tests (Existing)

- Mock all external dependencies
- Test individual components in isolation
- Run on every PR
- Target: <1 minute

## 2. Integration Tests (Priority)

### Approach
Use FastMCP's built-in `Client` class for in-memory MCP protocol testing:

```python
from fastmcp import FastMCP, Client

@pytest.fixture
def mcp_server():
    # Import triggers tool registration
    from mcp_second_brain import server
    return server.mcp

@pytest.fixture
async def client(mcp_server):
    async with Client(mcp_server) as client:
        yield client
```

### Mock Adapter
Create a lightweight mock that echoes metadata for validation:

```python
class MockAdapter(BaseAdapter):
    async def generate(self, prompt: str, vector_store_ids=None, **kwargs):
        return json.dumps({
            "model": self.model_name,
            "prompt_preview": prompt[:40],
            "vector_store_ids": vector_store_ids,
            "adapter_kwargs": kwargs,
        }, indent=2)
```

Activated via environment variable:
```python
# In adapters/__init__.py
if os.getenv("MCP_MOCK", "").lower() in {"1", "true"}:
    from .mock_adapter import MockAdapter
    ADAPTER_REGISTRY["openai"] = MockAdapter
    ADAPTER_REGISTRY["vertex"] = MockAdapter
```

### Test Structure
```
tests/integration_mcp/
  conftest.py              # Fixtures and mock setup
  test_tool_sanity.py      # One happy-path test per tool
  test_scenarios.py        # Cross-tool workflow tests
```

### Example Tests
```python
async def test_list_models(client):
    result = await client.call_tool("list_models")
    assert "chat_with_gemini25_pro" in result

async def test_gemini_routing(client):
    result = await client.call_tool("chat_with_gemini25_flash", {
        "instructions": "test",
        "output_format": "json",
        "context": []
    })
    data = json.loads(result)
    assert data["model"] == "gemini-2.5-flash"
```

### Benefits
- No Docker required
- Tests actual MCP protocol
- Fast execution (<30s)
- Catches routing and parameter issues
- Standard MCP testing approach

## 3. E2E Tests (Future)

### Docker Environment
```dockerfile
# Dockerfile.e2e
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    python3 python3-pip curl git \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:${PATH}"

RUN pip install claude-code pytest pytest-asyncio

WORKDIR /app
COPY . /app
RUN uv pip install -e .
```

### Claude Code Configuration
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

### Test Scenarios (Real Models)
1. **List Models**: Verify tool discovery works
2. **Simple Analysis**: "Analyze this Python function"
3. **Large Context**: Test vector store creation
4. **Model Comparison**: Compare outputs from different models
5. **Session Continuity**: Multi-turn conversation
6. **Error Recovery**: Missing API keys, network issues

### Test Implementation
```python
# tests/e2e/conftest.py
@pytest.fixture
def cc(tmp_path):
    """Helper to call claude-code CLI"""
    config_dir = tmp_path / ".config" / "claude-code"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text(CC_CONFIG)
    
    def _run(prompt: str, timeout=180):
        cmd = f'claude-code -p {shlex.quote(prompt)}'
        return subprocess.check_output(
            cmd, shell=True, text=True, timeout=timeout,
            env={**os.environ, "XDG_CONFIG_HOME": str(tmp_path)}
        )
    return _run

# tests/e2e/test_real_models.py
def test_gemini_analysis(cc):
    out = cc('Use second-brain chat_with_gemini25_flash to explain recursion in 2 sentences')
    assert "recursion" in out.lower()
    assert len(out.split('.')) >= 2  # At least 2 sentences
```

### CI/CD Strategy
```yaml
jobs:
  unit-and-integration:
    runs-on: ubuntu-latest
    steps:
      - name: Run tests
        env:
          MCP_MOCK: "1"
        run: pytest -xvs --ignore=tests/e2e

  e2e:
    runs-on: ubuntu-latest
    needs: unit-and-integration
    if: github.event_name == 'schedule' || github.ref == 'refs/heads/main'
    steps:
      - name: Run E2E tests
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          docker build -f Dockerfile.e2e -t mcp-e2e .
          docker run -e OPENAI_API_KEY mcp-e2e pytest tests/e2e -v
```

## Implementation Order

### Phase 1 (Now) - Integration Tests
1. Create `MockAdapter` with env-based activation
2. Set up integration test structure
3. Write per-tool sanity tests
4. Add cross-tool scenario tests
5. Update CI to run integration tests

### Phase 2 (Later) - E2E Tests
1. Create Docker environment
2. Write real-model test scenarios
3. Set up nightly CI runs
4. Monitor costs and adjust

## Key Decisions

1. **Integration before E2E**: Faster to implement, provides immediate value
2. **FastMCP Client**: Use the standard MCP testing approach
3. **Mock adapters**: Simple JSON echo for routing validation
4. **Cost control**: E2E tests only run nightly or on main branch
5. **Progressive rollout**: Start with integration, add E2E when stable

## Success Criteria

- Integration tests catch MCP protocol issues before merge
- E2E tests validate real user workflows weekly
- Total test time stays under 5 minutes for PR checks
- Mock adapters stay synchronized with real implementations
- No flaky tests in the integration suite