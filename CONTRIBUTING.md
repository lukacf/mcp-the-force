# Contributing to MCP The-Force

MCP The-Force is a thoughtfully designed AI server that empowers developers to integrate new capabilities with ease. This guide covers how to extend the robust architecture to support additional AI providers, tools, and memory sources.

## Architecture Highlights

- **Protocol-Based Adapters**: Implement the `MCPAdapter` protocol to add support for a new AI provider. The system handles lifecycle management, parameter validation and integration.

- **Declarative Tool Definitions**: Use the declarative magic of Python dataclasses to describe a tool's parameters, capabilities and routing. The appropriate tool classes and validations are automatically generated.

- **Automatic Capability Checking**: Specify model and tool capabilities with definitions. Parameters are automatically validated against those capabilities to provide strong guarantees. 

- **Unified Memory Abstractions**: The VectorStoreManager and UnifiedSessionCache provide interfaces for working with embeddings and conversation history across providers, enabling long-term memory integration independent of vendor specifics.

## Development Setup

<details>
<summary>Prerequisites</summary>

- Python 3.13+
- `uv` package manager 
- Git with pre-commit hooks
</details>

<details>
<summary>Initial Setup</summary>

```bash
# Clone and install
git clone <repository-url>  
cd mcp-the-force
uv pip install -e ".[dev]"

# Install pre-commit hooks
make install-hooks

# Initialize configuration 
mcp-config init
# Edit secrets.yaml with API keys

# Validate setup
make test  
```
</details>

<details>
<summary>Pre-commit Hooks</summary>

Pre-commit hooks ensure code quality:

- **On every commit** (fast, <5 seconds):
  - Ruff linting and formatting
  - MyPy type checking
  - Fast unit tests (excluding slow/integration)
- **On push** (can skip with `--no-verify`): 
  - Full unit test suite
</details>

<details>
<summary>Development Commands</summary>

The Makefile is the source of truth for all test commands to maintain consistency across local development, pre-commit hooks and CI/CD.

```bash
make help              # Show available commands  
make lint              # Run ruff and mypy  
make test              # Run fast unit tests only
make test-unit         # Run all unit tests with coverage
make test-integration  # Run integration tests 
make e2e               # Run Docker-in-Docker E2E tests
make ci                # Run full CI suite locally
make clean             # Clean generated files   
```
</details>

## Architecture Overview

<details>
<summary>Adapters</summary>

`mcp_the_force/adapters/` defines how MCP The-Force communicates with different AI providers.

- All adapters implement the `MCPAdapter` protocol for seamless swapping
- The central registry (`registry.py`) is the single truth source for available adapters
- Each adapter owns its definitions, capabilities and implementations as a self-contained package
</details>

<details>
<summary>Tools</summary>

`mcp_the_force/tools/` handles tool definition and execution:

- `descriptors.py`: Use Python descriptors to declaratively define tool parameter routing 
- `base.py`: Subclass `ToolSpec` and use descriptors to define tools
- `autogen.py`: Automatically generates tool classes and capability validators based on tool definitions
- `executor.py`: Orchestrates tool execution - validates parameters, calls adapters, returns results
- `capability_validator.py`: Automatically checks tool parameters against adapter-defined capabilities
- `factories.py`: Dynamically generates tool classes like `ChatWithGPT4` based on specs
- `integration.py`: FastMCP integration layer exposes tools over MCP protocol
</details>

<details>
<summary>Server</summary>

`mcp_the_force/server.py` is the core that connects the MCP protocol with the tools. It uses FastMCP to expose dynamically registered tools, with adapters and executors handling the heavy lifting. 
</details>

<details>
<summary>Context Management</summary>

`mcp_the_force/utils/` handles conversation context:

- `fs.py`: Intelligently gathers relevant context files respecting `.gitignore`  
- `prompt_builder.py`: Decides whether to inline context or route to vector store based on token count
- `vector_store.py`: Provides clean integration with vector databases for retrieval-augmented generation  
- `token_counter.py`: Counts tokens to control context size
</details>

<details>
<summary>Vector Store Abstraction</summary>  

`mcp_the_force/vectorstores/` manages embeddings and similarity search:

- `manager.py`: The `VectorStoreManager` handles all vector store operations across providers
- `protocol.py`: The `VectorStore` protocol defines the interface for vector store providers  
- `openai/`: An example implementation of the protocol for OpenAI
</details>

<details>
<summary>Session Management</summary>

The `UnifiedSessionCache` enables stateful conversations:  

- Uses SQLite (`.mcp_sessions.sqlite3`) to store conversation history across all providers
- Allows long-running conversations to persist across restarts
- Completely provider-agnostic session management  
</details>

## Extending MCP The-Force

<details>
<summary>Adding a New Adapter</summary>

To add support for a new AI provider "Mistral":

1. Create `mcp_the_force/adapters/mistral/` with `__init__.py`, `adapter.py`, `definitions.py`
2. Define capabilities, parameters, tool blueprints in `definitions.py`  
3. Implement `MCPAdapter` protocol in `adapter.py` for Mistral API calls
4. Expose adapter class and definitions in `__init__.py`
5. Add adapter to `mcp_the_force/adapters/registry.py`

The system will automatically pick up the new adapter and generate corresponding tool classes.  
</details>

<details>
<summary>Adding Models to Existing Adapters</summary>

To add a new model to an existing adapter, update its `definitions.py`:

1. Define a capability class for the model (e.g. `GPT5Capabilities`)
2. Add it to the `OPENAI_MODEL_CAPABILITIES` dictionary

Tool classes will be automatically generated based on the new model's defined capabilities.
</details>  

<details>
<summary>Adding New Tool Parameters</summary>

Expose new tool parameters in the adapter's `definitions.py`:  

```python
class OpenAIToolParams(BaseToolParams):
    new_param: str = Route.adapter(
        default="value",
        description="New parameter description",
        requires_capability=lambda c: c.supports_new_feature,
    )
```

Update capability classes to define `supports_new_feature`.
</details>

<details>  
<summary>Adding Memory Sources</summary>

To add a new memory source beyond conversation history and git commits:

1. Create a storage function in `mcp_the_force/memory/` that stores content and metadata via `VectorStoreManager` 
2. Include the new source in the memory search function
3. Expose the updated search in the `search_project_history` tool

The new memory source will now be included in historical searches.
</details>

<details>
<summary>Adding Local Services (Utility Tools)</summary>  

For local utilities that don't require an AI model:

1. Define the service class in `mcp_the_force/local_services/` implementing `LocalService` protocol
2. Create a `ToolSpec` in `mcp_the_force/tools/` setting `service_cls` to the new service and `adapter_class` to `None`
3. Register the tool by importing in `mcp_the_force/tools/definitions.py` 

The executor will route calls to the local service instead of an adapter. 
</details>

## Docker-in-Docker E2E Testing

The `tests/e2e_dind/` directory contains a robust end-to-end testing system that validates complete user workflows in isolated Docker environments.  

### Architecture

Each test scenario runs in its own Docker compose stack, providing:
- Dedicated network to prevent cross-test interference
- Isolated filesystem with temporary directories per test 
- CPU and memory limits to avoid resource contention
- Fresh containers for a clean environment in each test

The Docker-in-Docker setup is admittedly complex, but that byzantine architecture enables complete isolation and parallelism for truly comprehensive testing:
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

### Test Scenarios

The 6 comprehensive test scenarios cover all critical functionality:  
1. Smoke Test: Basic health check and core functionality
2. Context Overflow and RAG Workflow: Context splitting between inline and vector store 
3. Graceful Failure Handling: Error scenarios and user-friendly responses
4. Stable List Context Management: Consistent multi-turn context handling
5. Priority Context Override: Explicit control over file placement 
6. Session Management and Isolation: Cross-model state management

All tests run in parallel with an impressive 100% pass rate. The isolated environments eliminate flakiness from shared state, resource contention, and race conditions.

### Running Tests

Locally, use `make e2e` to run all scenarios or `docker run` individual scenarios for debugging. In CI/CD, each scenario runs as a separate job for maximum parallelism.

### Benefits Over Previous Approach  

The new Docker-in-Docker approach provides:
- Flake-free tests with no shared state, resource contention, or race conditions  
- Meaningful tests of real user workflows, not just API edge cases
- Clear failure isolation and faster debugging of individual scenarios
- True end-to-end validation with production-like network boundaries and setup

## Contributing Guidelines

We appreciate contributions to MCP The-Force! Here's how to get started:

1. Create a branch for your feature or bug fix
2. Write tests to cover new code (we use pytest) 
3. Follow conventions using pre-commit hooks for consistent style
4. Keep pull requests small and focused on a single change  
5. Use descriptive commit messages and PR titles/descriptions

Before submitting a PR, make sure to:
1. Run full test suite with `make ci`
2. Update relevant documentation
3. Add a changelog entry for your change

Open a PR against the main branch for review by maintainers. Feel free to open an issue or reach out if you have any questions!