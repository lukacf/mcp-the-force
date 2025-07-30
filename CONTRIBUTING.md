# Contributing to MCP The-Force

This guide covers everything you need to know to develop, test, and extend the MCP The-Force server.

## 🛠️ Development Setup

### Prerequisites
- Python 3.13+ required
- `uv` package manager
- Git with pre-commit hooks

### Initial Setup

```bash
# Clone and install
git clone <repository-url>
cd mcp-the-force
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

1. **Adapters** (`mcp_the_force/adapters/`)
   - **Protocol-based design**: All adapters implement `MCPAdapter` protocol
   - **Central Registry** (`registry.py`): Single source of truth for adapter listing
   - **Self-contained packages**: Each adapter owns its definitions, capabilities, and implementation
   - Current adapters: OpenAI, Google Gemini, xAI Grok, Anthropic

2. **Tool System** (`mcp_the_force/tools/`)
   - `descriptors.py`: Route descriptors with capability requirements
   - `base.py`: ToolSpec base class with dataclass-like definitions
   - `autogen.py`: Automatic tool generation from adapter blueprints
   - `executor.py`: Orchestrates tool execution with capability validation
   - `capability_validator.py`: Validates parameters against model capabilities
   - `factories.py`: Dynamic tool class generation
   - `integration.py`: FastMCP integration layer

3. **Server** (`mcp_the_force/server.py`)
   - FastMCP-based MCP protocol implementation
   - Registers dataclass-based tools dynamically
   - Minimal orchestration logic

4. **Context Management** (`mcp_the_force/utils/`)
   - `fs.py`: Intelligent file gathering with gitignore support and filtering
   - `prompt_builder.py`: Smart context inlining vs vector store routing
   - `vector_store.py`: OpenAI vector store integration for RAG
   - `token_counter.py`: Token counting for context management

5. **Vector Store Abstraction** (`mcp_the_force/vectorstores/`)
   - `manager.py`: Central VectorStoreManager for provider-agnostic operations
   - `protocol.py`: VectorStore protocol defining the interface all providers must implement
   - `openai/`: OpenAI vector store implementation
   - `in_memory.py`: In-memory implementation for testing
   - Vector store lifecycle management with TTL and automatic cleanup

### Protocol-Based Adapter Architecture

The system uses a protocol-based architecture with capability-aware validation:

```python
# Each adapter implements this protocol
class MCPAdapter(Protocol):
    param_class: Type[Any]           # Links to parameter class
    capabilities: AdapterCapabilities # What the model can do
    
    async def generate(
        self,
        prompt: str,
        params: Any,              # Instance of param_class
        ctx: CallContext,
        *,
        tool_dispatcher: ToolDispatcher,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Generate response from the model."""
        ...
```

**Key Design Principles:**
1. **ONE central registry**: Only `adapters/registry.py` lists adapters
2. **Self-contained adapters**: Each adapter package owns its complete definition
3. **Type-safe validation**: Lambda-based capability requirements, no magic strings
4. **Single source of truth**: Each adapter has one `definitions.py` file

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
- Vector stores created automatically for large contexts are session-scoped
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
python -m mcp_the_force.memory.commit
```

### Vector Store Architecture

The project uses a provider-agnostic vector store abstraction layer:

**Core Components:**
- **VectorStoreManager** (`vectorstores/manager.py`): Central manager handling all vector store operations
- **VectorStore Protocol** (`vectorstores/protocol.py`): Defines the interface all providers must implement
- **VectorStoreCache** (`vector_store_cache.py`): SQLite-based caching with TTL and automatic cleanup
- **Provider Implementations**: OpenAI (production) and InMemory (testing)

**Key Features:**
- Automatic lifecycle management with configurable TTL (default: 2 hours)
- Provider-agnostic API - switch providers without changing code
- Unified handling for session-specific and named (permanent) stores
- Automatic cleanup of expired stores to prevent quota exhaustion
- Support for rollover lineage tracking in memory stores

**Usage Example:**
```python
from mcp_the_force.vectorstores.manager import vector_store_manager

# Create a vector store for a session
store_id = await vector_store_manager.create(
    files=files,
    session_id="user-session-123",
    ttl_seconds=7200  # 2 hour TTL
)

# Add files to an existing store
await vector_store_manager.add_files(
    vector_store_id=store_id,
    files=[VSFile(path="doc.txt", content="...")]
)

# Search across stores
results = await vector_store_manager.search(
    vector_store_ids=[store_id],
    query="search query"
)
```

### Session Management: The UnifiedSessionCache

The server features a persistent, unified session management system that works across **all** AI providers.

- **Unified Cache**: All conversation history is stored in a single SQLite database (`.mcp_sessions.sqlite3` by default), managed by the `UnifiedSessionCache`.
- **Persistence**: Sessions are preserved across server restarts with a default TTL of 6 months, ensuring long-term conversational memory.
- **Provider-Agnostic**: The executor and adapters use the cache to maintain conversational context, regardless of whether you're using OpenAI, Gemini, Grok, or Anthropic models.
- **How it Works**: When a `session_id` is provided, the executor retrieves the message history from the cache and passes it to the adapter, ensuring the model has the full context of the conversation.
- **Thread-Safe**: Built with SQLite's thread-safety and proper async handling for concurrent access.

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

### Adding a New Adapter

Adding support for a new AI provider (e.g., Mistral) involves creating a self-contained adapter package:

#### 1. Create the adapter package structure
```
mcp_the_force/adapters/mistral/
├── __init__.py
├── adapter.py          # MCPAdapter implementation
└── definitions.py      # Single source of truth
```

#### 2. Create `definitions.py` (Single source of truth)
```python
# adapters/mistral/definitions.py

from typing import Dict, Any, Optional
from dataclasses import dataclass

from ..params import BaseToolParams
from ..capabilities import AdapterCapabilities
from ...tools.descriptors import Route
from ...tools.blueprint import ToolBlueprint
from ...tools.blueprint_registry import register_blueprints

# Parameter class with capability requirements
class MistralToolParams(BaseToolParams):
    """Mistral-specific parameters."""
    
    temperature: float = Route.adapter(
        default=0.7,
        description="Model temperature",
        requires_capability=lambda c: c.supports_temperature,
    )
    
    max_tokens: int = Route.adapter(
        default=4096,
        description="Maximum tokens to generate",
    )

# Capability definitions
@dataclass
class MistralCapabilities(AdapterCapabilities):
    provider: str = "mistral"
    model_family: str = "mistral"
    supports_temperature: bool = True
    supports_tools: bool = True
    max_context_window: int = 32_000

@dataclass
class MistralLargeCapabilities(MistralCapabilities):
    model_name: str = "mistral-large"
    description: str = "Most capable Mistral model"

# Model registry
MISTRAL_MODEL_CAPABILITIES = {
    "mistral-large": MistralLargeCapabilities(),
}

# Auto-generate and register blueprints
def _generate_and_register_blueprints():
    blueprints = []
    for model_name, capabilities in MISTRAL_MODEL_CAPABILITIES.items():
        blueprint = ToolBlueprint(
            model_name=model_name,
            adapter_key="mistral",
            param_class=MistralToolParams,
            description=capabilities.description,
            timeout=600,
            context_window=capabilities.max_context_window,
            tool_type="chat",
        )
        blueprints.append(blueprint)
    register_blueprints(blueprints)

_generate_and_register_blueprints()
```

#### 3. Implement the adapter
```python
# adapters/mistral/adapter.py

from ..protocol import CallContext, ToolDispatcher
from .definitions import MistralToolParams, MISTRAL_MODEL_CAPABILITIES

class MistralAdapter:
    """Mistral adapter implementing MCPAdapter protocol."""
    
    param_class = MistralToolParams
    
    def __init__(self, model_name: str):
        if model_name not in MISTRAL_MODEL_CAPABILITIES:
            raise ValueError(f"Unknown model: {model_name}")
            
        self.model_name = model_name
        self.capabilities = MISTRAL_MODEL_CAPABILITIES[model_name]
        self.display_name = f"Mistral {model_name}"
    
    async def generate(
        self,
        prompt: str,
        params: MistralToolParams,
        ctx: CallContext,
        *,
        tool_dispatcher: ToolDispatcher,
        **kwargs
    ) -> Dict[str, Any]:
        # Implement your API call
        response = await self.client.chat(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=params.temperature,
            max_tokens=params.max_tokens,
        )
        return {"content": response.choices[0].message.content}
```

#### 4. Set up the package `__init__.py`
```python
# adapters/mistral/__init__.py

from .adapter import MistralAdapter
# This import triggers blueprint registration!
from . import definitions  # noqa: F401
from .definitions import MISTRAL_MODEL_CAPABILITIES

__all__ = ["MistralAdapter", "MISTRAL_MODEL_CAPABILITIES"]
```

#### 5. Add ONE line to the central registry
```python
# adapters/registry.py
_ADAPTER_REGISTRY: Dict[str, Tuple[str, str]] = {
    "openai": ("mcp_the_force.adapters.openai.adapter", "OpenAIProtocolAdapter"),
    "google": ("mcp_the_force.adapters.google.adapter", "GeminiAdapter"),
    "xai": ("mcp_the_force.adapters.xai.adapter", "GrokAdapter"),
    "anthropic": ("mcp_the_force.adapters.anthropic.adapter", "AnthropicAdapter"),
    "mistral": ("mcp_the_force.adapters.mistral.adapter", "MistralAdapter"),  # ADD THIS
}
```

**That's it!** The system automatically generates tool classes and validates parameters.

### Adding Models to Existing Adapters

To add a new model (e.g., GPT-5) to an existing adapter, only edit `definitions.py`:

```python
# adapters/openai/definitions.py

# Add capability class
@dataclass
class GPT5Capabilities(OpenAIBaseCapabilities):
    model_name: str = "gpt-5"
    max_context_window: int = 2_000_000
    description: str = "Next generation GPT"
    supports_reasoning_effort: bool = True

# Add to registry
OPENAI_MODEL_CAPABILITIES = {
    # ... existing models ...
    "gpt-5": GPT5Capabilities(),
}
```

### Adding New Parameters

Add parameters with capability requirements in `definitions.py`:

```python
class OpenAIToolParams(BaseToolParams):
    # ... existing parameters ...
    
    new_param: str = Route.adapter(
        default="value",
        description="New parameter description",
        requires_capability=lambda c: c.supports_new_feature,
    )
```

Then update capability classes to define `supports_new_feature`.

### How Tools Are Generated

Tools are automatically generated from blueprints:

1. **At startup**: `tools/autogen.py` imports all adapters
2. **Blueprint registration**: Each adapter's `definitions.py` registers blueprints
3. **Tool generation**: `factories.py` creates tool classes like `ChatWithMistralLarge`
4. **Capability extraction**: Capabilities are retrieved from the adapter's definitions
5. **Registration**: Tools are registered with the MCP server

### Parameter Validation Flow

```
User provides parameters
    ↓
ParameterValidator (type checking)
    ↓
CapabilityValidator (model-specific checks)
    ↓
Clear error if unsupported:
"Parameter 'temperature' is not supported by model 'o3' because its 'supports_temperature' is False"
```

### Adding Memory Sources

To add new memory sources (beyond conversations and git commits):

1. Create storage function in `mcp_the_force/memory/`
2. Implement search integration in memory adapters
3. Add to unified search in `search_project_history`

Example:
```python
from ..vectorstores.manager import vector_store_manager
from ..vectorstores.protocol import VSFile

async def store_new_memory_type(content: str, metadata: Dict[str, Any]) -> None:
    """Store new memory type using the vector store manager."""
    from ..memory.async_config import get_async_memory_config
    
    config = get_async_memory_config()
    store_id = await config.get_active_conversation_store()  # Or create a new store type
    
    # The VectorStoreManager abstracts away provider-specific details
    vs_file = VSFile(
        path=f"memory_type/{metadata['id']}.json",
        content=json.dumps({
            "content": content,
            "metadata": {
                "type": "new_memory_type",
                "timestamp": datetime.utcnow().isoformat(),
                **metadata
            }
        }),
        metadata={"type": "new_memory_type", **metadata}
    )
    
    # Add to vector store using the manager
    await vector_store_manager.add_files(
        vector_store_id=store_id,
        files=[vs_file]
    )
```

### Adding a New `LocalService` (Utility Tool)

For tools that run locally (e.g., database queries, file system operations) without calling an external AI model, the project uses the `LocalService` protocol. This ensures a clean separation from AI-backed tools.

#### 1. Create the Service Class

Implement the `LocalService` protocol in a new file, for example, in `mcp_the_force/local_services/`:

```python
# mcp_the_force/local_services/my_utility.py
from typing import Any, Dict

class MyUtilityService:
    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        # Your logic here
        param_value = kwargs.get("my_param")
        result = await self.perform_operation(param_value)
        return {"status": "success", "result": result}
    
    async def perform_operation(self, value: str) -> str:
        # Implement your utility logic
        return f"Processed {value}"
```

#### 2. Define the ToolSpec

Create a `ToolSpec` class in `mcp_the_force/tools/`. Set `service_cls` to your new service and `adapter_class` to `None`:

```python
# mcp_the_force/tools/my_utility_tool.py
from .base import ToolSpec
from .registry import tool
from .descriptors import Route
from ..local_services.my_utility import MyUtilityService

@tool
class MyUtilityTool(ToolSpec):
    """Description of your utility tool."""
    service_cls = MyUtilityService
    adapter_class = None  # This signals it's a local service
    timeout = 30
    
    my_param: str = Route.adapter(description="A parameter for the service")
    optional_param: Optional[str] = Route.adapter(
        description="Optional parameter",
        default=None
    )
```

#### 3. Register the Tool

Import your new tool file in `mcp_the_force/tools/definitions.py` to ensure it's registered on startup:

```python
# mcp_the_force/tools/definitions.py
# ... existing imports ...
from . import my_utility_tool  # Add this import
```

The executor will now automatically route calls to `my_utility_tool` to your `MyUtilityService.execute` method instead of an AI adapter.

### Error Handling Best Practices

1. **Use specific exception types**:
```python
from mcp_the_force.errors import (
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

### Working with Vector Stores

When implementing features that use vector stores:

1. **Always use VectorStoreManager**, never create stores directly:
   ```python
   # ✅ Correct
   from mcp_the_force.vectorstores.manager import vector_store_manager
   store_id = await vector_store_manager.create(files=files)
   
   # ❌ Wrong - don't use provider clients directly
   client = OpenAI()
   store = await client.vector_stores.create()
   ```

2. **Respect the abstraction** - the code should work with any provider:
   ```python
   # Good - uses protocol types
   from mcp_the_force.vectorstores.protocol import VSFile
   
   # Bad - uses provider-specific types
   from openai.types import FileObject
   ```

3. **Handle cleanup properly** - stores have TTL and will be cleaned up:
   ```python
   # For temporary stores (most common)
   store_id = await vector_store_manager.create(
       files=files,
       session_id="user-123",
       ttl_seconds=7200  # Will be auto-cleaned after 2 hours
   )
   
   # For permanent stores (rare, needs explicit protection)
   store_id = await vector_store_manager.create(
       files=files,
       name="project-knowledge-base",
       protected=True  # Won't be auto-cleaned
   )
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
python -c "from mcp_the_force.tools.registry import list_tools; print(list_tools())"
```

**Memory/Vector store issues:**
```bash
# Check vector store status
python -c "from mcp_the_force.memory.config import get_memory_config; print(get_memory_config())"
```

### Debug Logging

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
uv run -- mcp-the-force
```

Or in configuration:
```yaml
logging:
  level: DEBUG
```

### Concurrency and Thread Safety

The server is designed to handle concurrent requests safely:

**Key Considerations:**
1. **SQLite Databases**: All use WAL mode for better concurrency
   ```python
   # Automatically set in SQLiteBaseCache
   await conn.execute("PRAGMA journal_mode=WAL")
   await conn.execute("PRAGMA busy_timeout=5000")
   ```

2. **Vector Store Operations**: The VectorStoreManager uses async locks to prevent race conditions
   ```python
   async with self._operation_lock:
       # Critical section for store creation
   ```

3. **Session Cache**: Thread-safe with proper connection pooling
4. **File-based Locks**: Used for cross-process coordination (e.g., cleanup tasks)

**Best Practices:**
- Always use `async with` for database connections
- Don't share database connections across coroutines
- Use the provided managers (VectorStoreManager, UnifiedSessionCache) rather than direct access
- Be aware of the cleanup probability mechanism to avoid thundering herd

### Database Migrations

The project uses a simple migration system for schema changes:

**Current Schema Version**: 001 (unified vector stores)
- Migration files in `mcp_the_force/migrations/`
- Automatic backup before migrations
- Rollback support for safety

**Adding a Migration:**
1. Create SQL file: `002_your_feature.sql`
2. Update `CURRENT_VERSION` in `migrate.py`
3. Test with rollback: `002_your_feature_rollback.sql`
4. Run: `python -m mcp_the_force.migrations.migrate`

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

Thank you for contributing to MCP The-Force! 🧠✨
