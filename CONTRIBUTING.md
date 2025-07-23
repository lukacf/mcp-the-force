# Contributing to MCP Second-Brain

This guide covers everything you need to know to develop, test, and extend the MCP Second-Brain server.

## 🛠️ Development Setup

### Prerequisites
- Python 3.10+ required
- `uv` package manager
- Git with pre-commit hooks

### Initial Setup

```bash
# Clone and install
git clone <repository-url>
cd mcp-second-brain
uv pip install -e ".[dev]"

# Install pre-commit hooks
make install-hooks
# or manually: pre-commit install && pre-commit install --hook-type pre-push

# Initialize configuration
mcp-config init
# Edit secrets.yaml with your API keys

# Validate setup
make test
```

### Pre-commit Hooks

We use pre-commit hooks to ensure code quality:

**What runs automatically:**
- **On every commit** (fast, <5 seconds):
  - Ruff linting and formatting
  - MyPy type checking
  - Fast unit tests (excluding slow/integration tests)
- **On push** (optional, can skip with `--no-verify`):
  - Full unit test suite

### Development Commands

**Makefile is the Single Source of Truth** - All test commands are standardized in the Makefile to ensure consistency across local development, pre-commit hooks, and CI/CD.

```bash
make help              # Show all available commands
make lint              # Run ruff and mypy
make test              # Run fast unit tests only (pre-commit)
make test-unit         # Run all unit tests with coverage (pre-push)
make test-integration  # Run integration tests with MockAdapter
make e2e               # Run Docker-in-Docker E2E tests
make ci                # Run full CI suite locally
make clean             # Clean up generated files
```

### Standardized Testing Workflow

| Command               | Purpose                      | When to Use                           |
|-----------------------|------------------------------|---------------------------------------|
| `make test`           | Fast unit tests              | Before every commit (pre-commit hook) |
| `make test-unit`      | Full unit tests + coverage   | Before PR (pre-push hook)             |
| `make test-integration` | Integration tests with mocks | After adapter changes                 |
| `make e2e`            | End-to-end Docker tests      | Before major releases                 |
| `make ci`             | All CI checks locally        | Before pushing to CI                  |

### Running Tests

**Recommended Approach** (use Makefile commands):
```bash
# Fast feedback loop (what pre-commit runs)
make test

# Before creating PR
make test-unit

# After adapter/integration changes  
make test-integration

# Full CI validation locally
make ci
```

**Direct pytest commands** (for debugging specific tests):
```bash
# Unit tests only
pytest tests/unit -v                    # All unit tests
pytest tests/unit -m "not slow"         # Fast unit tests only

# Integration tests (requires MockAdapter)
MCP_ADAPTER_MOCK=1 pytest tests/internal -v           # Internal integration tests  
MCP_ADAPTER_MOCK=1 pytest tests/integration_mcp -v    # MCP protocol tests

# E2E tests
pytest tests/e2e_dind -v               # Docker-in-Docker E2E tests
```

**Important**: Always use Makefile commands for standard workflows. Direct pytest is only for debugging specific test files.

## 🏗️ Architecture

### Core Components

1. **Adapters** (`mcp_second_brain/adapters/`)
   - `base.py`: Abstract `BaseAdapter` defining the interface
   - `openai/`: OpenAI models integration (o3, o3-pro, gpt-4.1) via Responses API
   - `vertex/`: Google Vertex AI integration (Gemini 2.5 pro/flash) via google-genai SDK

2. **Tool System** (`mcp_second_brain/tools/`)
   - `descriptors.py`: Route descriptors for parameter routing
   - `base.py`: ToolSpec base class with dataclass-like definitions
   - `definitions.py`: Tool definitions for all models
   - `executor.py`: Orchestrates tool execution with component delegation
   - `integration.py`: FastMCP integration layer

3. **Server** (`mcp_second_brain/server.py`)
   - FastMCP-based MCP protocol implementation
   - Registers dataclass-based tools dynamically
   - Minimal orchestration logic

4. **Context Management** (`mcp_second_brain/utils/`)
   - `fs.py`: Intelligent file gathering with gitignore support and filtering
   - `prompt_builder.py`: Smart context inlining vs vector store routing
   - `vector_store.py`: OpenAI vector store integration for RAG
   - `token_counter.py`: Token counting for context management

### Configuration System

The configuration system uses a layered approach with Pydantic Settings:

```python
# Configuration precedence (highest to lowest):
1. Environment variables (OPENAI_API_KEY, etc.)
2. YAML files (config.yaml + secrets.yaml)
3. Default values (in pydantic models)
```

Key components:
- `config.py`: Pydantic Settings models with custom sources
- `cli/config_cli.py`: Typer-based CLI for configuration management
- YAML file merging with deep merge for nested configurations

### Tool System Architecture

The tool system uses Python descriptors for sophisticated parameter routing:

```python
@tool
class ChatWithGPT4(ToolSpec):
    model_name = "gpt-4.1"
    adapter_class = "openai"
    context_window = 1_000_000
    timeout = 600
    
    # Parameter routing
    instructions: str = Route.prompt(pos=0, description="Task instructions")
    context: List[str] = Route.prompt(pos=2, description="File paths")
    temperature: float = Route.adapter(default=0.7)
    session_id: Optional[str] = Route.session()
    structured_output_schema: Optional[Dict] = Route.structured_output()
```

**Route Types:**
- `Route.prompt()`: Passed to model prompt
- `Route.adapter()`: Passed to adapter configuration
- `Route.session()`: Used for session management
- `Route.vector_store()`: Used for vector store operations
- `Route.structured_output()`: JSON schema for structured responses

### Memory System Architecture

**Two-Store Approach:**
1. **Conversation Memory**: AI consultations stored in vector stores with metadata
2. **Git Commit Memory**: Commit messages and diffs for institutional memory

**Search Architecture:**
- `search_project_history`: Searches permanent knowledge (conversations, commits)
- `search_session_attachments`: Searches ephemeral attachment stores
- Automatic deduplication and relevance ranking

**Implementation:**
```python
# Conversation storage on every AI call
await store_conversation_memory(
    prompt=prompt,
    response=response,
    context_files=context_files,
    model=model_name
)

# Git commit storage via post-commit hook
python -m mcp_second_brain.memory.commit
```

### Session Management

**OpenAI Models:**
- Ephemeral cache using SQLite with TTL
- Stores response IDs for conversation continuity
- OpenAI maintains full conversation context

**Gemini Models:**
- Full conversation history in SQLite
- Message persistence with automatic cleanup
- TTL-based session expiration

### Context Management Logic

**Inline vs RAG Decision:**
```python
if total_tokens < (model_context_window * context_percentage):
    # Inline files directly in prompt
    return inline_context(files)
else:
    # Create vector store for RAG
    vector_store_id = create_vector_store(files)
    return {"vector_store_ids": [vector_store_id]}
```

**File Processing Pipeline:**
1. Gitignore filtering
2. Binary file detection
3. Size limit validation (500KB per file, 50MB total)
4. Token counting with tiktoken
5. Smart chunking for vector stores

## 🔧 Extending the System

### Adding a New Tool

Create a new tool by defining a class with the `@tool` decorator:

```python
@tool
class ChatWithMyModel(ToolSpec):
    """Description of what this tool does."""
    
    # Model configuration
    model_name = "gpt-4"
    adapter_class = "openai"
    context_window = 100_000
    timeout = 300
    
    # Define parameters with routing
    instructions: str = Route.prompt(pos=0, description="Task instructions")
    output_format: str = Route.prompt(pos=1)
    context: List[str] = Route.prompt(pos=2)
    temperature: float = Route.adapter(default=0.7)
    session_id: Optional[str] = Route.session()
```

### Adding a New Adapter

1. Create adapter class inheriting from `BaseAdapter`
2. Implement the `generate()` method
3. Add configuration in Settings model
4. Register adapter class in the tool definition

Example:
```python
class MyAdapter(BaseAdapter):
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.client = MyAPIClient()
    
    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        session_id: Optional[str] = None,
        structured_output_schema: Optional[Dict] = None,
        **kwargs
    ) -> str:
        # Implement your API call
        response = await self.client.generate(
            prompt=prompt,
            model=self.model_name,
            temperature=temperature
        )
        return response.text
```

### Adding Memory Sources

To add new memory sources (beyond conversations and git commits):

1. Create storage function in `mcp_second_brain/memory/`
2. Implement search integration in memory adapters
3. Add to unified search in `search_project_history`

Example:
```python
async def store_new_memory_type(content: str, metadata: Dict[str, Any]) -> None:
    """Store new memory type in vector store."""
    memory_config = get_memory_config()
    client = get_client()
    
    # Create document with metadata
    document = {
        "content": content,
        "metadata": {
            "type": "new_memory_type",
            "timestamp": datetime.utcnow().isoformat(),
            **metadata
        }
    }
    
    # Store in vector store
    await client.beta.vector_stores.file_batches.upload_and_poll(
        vector_store_id=memory_config.conversation_store_id,
        files=[document]
    )
```

### Error Handling Best Practices

1. **Use specific exception types**:
```python
from mcp_second_brain.errors import (
    AdapterError,
    ConfigurationError,
    VectorStoreError
)
```

2. **Implement graceful degradation**:
```python
try:
    result = await expensive_operation()
except VectorStoreError:
    # Fall back to simple search
    result = await fallback_search()
```

3. **Log appropriately**:
```python
logger.info("Starting operation")        # User-visible progress
logger.debug("Internal state: %s", data) # Debug information
logger.error("Operation failed: %s", e)  # Error conditions
```

### Testing Guidelines

**Unit Tests** (`tests/unit/`):
- Test individual components in isolation  
- Mock all external dependencies (OpenAI, Google APIs, file system)
- Focus on business logic and edge cases
- Fast execution (< 4 seconds total)
- No network calls, no real API usage

**Integration Tests** (`tests/internal/`):
- Test component interactions with MockAdapter
- Verify end-to-end tool execution workflows
- Mock external APIs but test real component plumbing
- Environment: `MCP_ADAPTER_MOCK=1` (set automatically by Makefile)
- Test parameter routing, session management, error handling

**MCP Integration Tests** (`tests/integration_mcp/`):
- Test MCP protocol compliance
- Validate tool registration and execution via MCP
- Mock adapters for consistent results
- Verify MCP server/client communication

**E2E Tests** (`tests/e2e_dind/`):
- Test complete user workflows in Docker environment
- Use Docker-in-Docker for full isolation
- Real API calls in controlled environment
- Full deployment and configuration testing

Example test structure:
```python
@pytest.mark.asyncio
async def test_tool_execution(mock_adapter):
    """Test tool execution with mocked adapter."""
    tool_spec = ChatWithGPT4()
    
    # Mock the adapter response
    mock_adapter.generate.return_value = "Test response"
    
    # Execute tool
    result = await execute_tool(tool_spec, {
        "instructions": "Test instruction",
        "output_format": "Test format"
    })
    
    assert result == "Test response"
    mock_adapter.generate.assert_called_once()
```

## 🚀 Release Process

1. **Update version** in `pyproject.toml`
2. **Run full test suite**: `make ci`
3. **Update CHANGELOG.md** with new features and fixes
4. **Create release PR** with version bump
5. **Tag release** after merge: `git tag v1.2.3`
6. **Push tags**: `git push origin --tags`

## 📝 Code Style

- **Formatting**: Ruff (replaces Black + isort)
- **Linting**: Ruff (replaces flake8 + many plugins)
- **Type checking**: MyPy with strict mode
- **Docstrings**: Google style for public APIs
- **Import sorting**: Ruff handles this automatically

### Key Conventions

- Use `async/await` for all I/O operations
- Prefer dataclasses over regular classes for data structures
- Use type hints for all function signatures
- Log at appropriate levels (DEBUG/INFO/WARNING/ERROR)
- Use dependency injection for testability

## 🐛 Debugging

### Common Issues

**Configuration not loading:**
```bash
# Debug configuration loading
mcp-config show --debug

# Check environment variables
env | grep -E "(OPENAI|VERTEX|MCP)"
```

**Tool registration failures:**
```bash
# Check tool registry
python -c "from mcp_second_brain.tools.registry import list_tools; print(list_tools())"
```

**Memory/Vector store issues:**
```bash
# Check vector store status
python -c "from mcp_second_brain.memory.config import get_memory_config; print(get_memory_config())"
```

### Debug Logging

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
uv run -- mcp-second-brain
```

Or in configuration:
```yaml
logging:
  level: DEBUG
```

## 🤝 Contributing Guidelines

1. **Fork and branch**: Create feature branches from `main`
2. **Write tests**: All new code requires tests
3. **Follow conventions**: Use pre-commit hooks
4. **Document changes**: Update relevant documentation
5. **Small PRs**: Keep changes focused and reviewable
6. **Descriptive commits**: Use conventional commit messages

### Pull Request Process

1. Ensure all tests pass: `make ci`
2. Update documentation if needed
3. Add entry to CHANGELOG.md
4. Request review from maintainers
5. Address feedback and iterate
6. Squash commits before merge

Thank you for contributing to MCP Second-Brain! 🧠✨
