# Contributing to MCP The-Force

MCP The-Force is a protocol-based AI server designed to integrate multiple AI providers and tools. This guide covers how to extend its architecture to support additional AI providers, tools, and memory sources.

## Development Philosophy

This project is not only a tool but also a product of its own methodology. The "The Force" MCP server was developed by an AI assistant (Claude) relying extensively on the very tools this server provides. This dogfooding approach—using the system to build itself—ensures that the architecture is practical, robust, and built from a user-centric perspective. Test-Driven Development (TDD) is a central practice in this project, ensuring reliability and maintainability.

## Architecture Highlights

- **Protocol-Based Adapters**: Implement the `MCPAdapter` protocol to add support for a new AI provider. The system handles lifecycle management, parameter validation and integration.

- **Declarative Tool Definitions**: A declarative system using Python descriptors to define tool parameters, capabilities, and routing, which are then used to automatically generate tool classes and validations.

- **Automatic Capability Checking**: Model and tool capabilities are defined declaratively. Parameters are automatically validated against these capabilities at runtime. 

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
<summary>Makefile Commands</summary>

The Makefile is the source of truth for all test and maintenance commands to maintain consistency across local development and CI/CD.

```bash
make help              # Show available commands  
make lint              # Run ruff and mypy  
make test              # Run fast unit tests only (for pre-commit)
make test-unit         # Run all unit tests with coverage
make test-integration  # Run integration tests (uses mock adapters) 
make e2e               # Run Docker-in-Docker E2E tests
make ci                # Run full CI suite locally
make clean             # Clean generated files
make backup            # Manually backup SQLite databases   
```
</details>

## Testing Strategy

The project relies on a multi-layered testing strategy, with Test-Driven Development (TDD) as its core philosophy. Each layer provides a different level of validation, from fast unit checks to full end-to-end workflow verification.

### Pre-commit and Pre-push Hooks
To enforce code quality and prevent regressions, the repository uses pre-commit hooks that run automatically:
-   **On every commit** (`make test`): Fast unit tests (<5 seconds) are run, along with `ruff` and `mypy` checks.
-   **On every push** (`make test-unit` & `make test-integration`): The full unit and integration test suites are run. This can be skipped with `git push --no-verify`.

### Unit Tests
-   **Command**: `make test-unit`
-   **Location**: `tests/unit/`
-   **Purpose**: Test individual components in complete isolation. All external dependencies, I/O, and API calls are mocked. These tests are fast and verify the correctness of specific functions and classes.

### Integration Tests
-   **Command**: `make test-integration`
-   **Location**: `tests/internal/` and `tests/integration_mcp/`
-   **Purpose**: Verify that components work together correctly. These tests use a `MockAdapter` to simulate AI model behavior, allowing for validation of the full internal workflow (parameter routing, context building, session management) without making real API calls.

### End-to-End (E2E) Tests
-   **Command**: `make e2e`
-   **Location**: `tests/e2e_dind/`
-   **Purpose**: Validate complete, real-world user workflows in an isolated Docker-in-Docker environment. These tests use real API keys and models to ensure the system works as expected from the client's perspective.
-   **Scenarios**: The E2E suite includes comprehensive scenarios for:
    1.  **Smoke Test**: Basic health check and core functionality.
    2.  **Context Overflow & RAG**: Verification of context splitting between inline and vector stores.
    3.  **Session Management**: Testing session persistence, isolation, and cross-model state.
    4.  **Stable List**: Validating consistent context handling in multi-turn conversations.
    5.  **Priority Context**: Ensuring the priority override forces files inline.
    6.  **Environment Checks**: Validating the test environment itself is correctly configured.
-   **Architecture**: Each test scenario runs in its own Docker Compose stack, providing complete network and filesystem isolation. This design ensures that tests are reliable and free from flakiness caused by shared state or resource contention. The scenarios are designed to run in parallel and test the system's stability and correctness under real-world conditions.

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
- `context_builder.py`: Decides whether to inline context or route to vector store based on a stable-list algorithm and token budget
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

## Contributing Guidelines

We appreciate contributions to MCP The-Force! Here's how to get started:

1. Create a branch for your feature or bug fix.
2. Write tests to cover new code (we use pytest).
3. Follow conventions using pre-commit hooks for consistent style.
4. Keep pull requests small and focused on a single change.
5. Use descriptive commit messages and PR titles/descriptions.

Before submitting a PR, make sure to:
1. Run the full CI suite with `make ci`.
2. Update relevant documentation.
3. Add a changelog entry for your change.

Open a PR against the main branch for review by maintainers. Feel free to open an issue or reach out if you have any questions!
