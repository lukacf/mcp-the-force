This file provides guidance to you when working with code in this repository.

## Project Overview

MCP The-Force Server - A Model Context Protocol (MCP) server that provides access to multiple AI models (OpenAI o-series, Google Gemini 3, and xAI Grok) with intelligent context management for large codebases. Built with a sophisticated descriptor-based tool system using Python descriptors for parameter routing. Uses FastMCP framework with smart file inlining and vector store integration for RAG. Supports multi-turn conversations for all models via UnifiedSessionCache.

## Commands

- **Install dependencies**: `uv pip install -e .`
- **Google Cloud auth** (for Gemini): `gcloud auth application-default login`
- **Run server**: `uv run -- mcp-the-force`
- **Server runs on**: Configurable via HOST/PORT env vars (default: 127.0.0.1:8000)

## Architecture

### Core Components

1. **Adapters** (`mcp_the_force/adapters/`)
   - Protocol-based architecture with `MCPAdapter` protocol
   - `openai/`: OpenAI models integration (GPT-5.2, GPT-5.2 Pro, GPT-4.1, GPT-5.1 Codex Max, o3/o4-mini deep research) via Responses API
   - `google/`: Google Vertex AI integration (Gemini 3 Pro preview, Gemini 3 Flash preview) via google-genai SDK
   - `xai/`: xAI integration (Grok 4.1)
   - `registry.py`: Central adapter registry

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

### Smart Context Management

- **Files within context percentage**: Inlined directly into prompt (default 85% of model's context window minus safety margin)
- **Larger contexts**: Automatic vector store creation for RAG
- **File filtering**: Respects .gitignore, skips binaries, size limits (500KB/file, 50MB total)
- **Extension support**: 60+ text file types, OpenAI vector store compatible formats

### Available Tools

The Force provides access to 12 cutting-edge AI models through `chat_with_*` tools, each with dynamically-generated descriptions showing their capabilities, context limits, and best use cases.

**Key models for most tasks:**
- For 90% of your work, use **`chat_with_gpt52_pro`** (flagship, 400k context, maximum accuracy) or **`chat_with_gpt52`** (400k context, advanced reasoning)
- For long documents: **`chat_with_gemini3_pro_preview`** (smart, 1M context, fast)
- For fast large-context work: **`chat_with_gemini3_flash_preview`** or **`chat_with_gpt41`**
- For search: GPT-5.2 models are best, but **`chat_with_grok41`** is a good and faster alternative
- For ultra-long-horizon tasks (24+ hours): **`chat_with_gpt51_codex_max`** with xhigh reasoning effort and automatic compaction

**Utility tools:**
- `list_sessions`: List existing AI conversation sessions for the current project
- `describe_session`: Generate an AI-powered summary of an existing session's conversation history
- `search_project_history`: Search past conversations and git commits from the project's long-term history
- `count_project_tokens`: Count tokens for specified files or directories
- `search_mcp_debug_logs`: (Developer mode only) Run a raw LogsQL query against VictoriaLogs debug logs

Use `search_project_history` whenever you need to recall prior AI decisions or code history. 

### Conversation Support

All AI chat and research tools support multi-turn conversations via the `session_id` parameter.

- **Unified Session Caching**: The server now uses a persistent SQLite database (`.mcp-the-force/sessions.sqlite3`) to manage conversation history for **all** models (OpenAI, Gemini, and Grok).
- **Session Continuity**:
  - **OpenAI/Grok**: The server caches the `response_id` (for OpenAI) or the full history (for Grok) to continue the conversation.
  - **Gemini**: The server stores the full conversation history locally in the SQLite database.
- **Session TTL**: The default Time-To-Live for all sessions is 6 months (configurable via `session.ttl_seconds`).
- **Session IDs**: Session IDs are global. Use unique names for different tasks (e.g., "refactor-auth-logic-2024-07-15"). 

### Configuration

The project uses YAML-based configuration managed by the `mcp-config` CLI tool:

**Setup:**
```bash
# Initialize configuration files
mcp-config init

# This creates:
# - config.yaml: Non-sensitive configuration (can be committed)
# - secrets.yaml: API keys and sensitive data (gitignored)
```

**Key Configuration:**
- `providers.openai.api_key`: Required for OpenAI models (GPT-5.2, GPT-5.2 Pro, GPT-4.1, GPT-5.1 Codex Max, o3/o4-mini deep research)
- `providers.vertex.project`, `providers.vertex.location`: Required for Google Vertex AI models
- `providers.xai.api_key`: Required for xAI models (Grok 4.1)
- `mcp.host`, `mcp.port`: Server configuration
- `mcp.context_percentage`: Percentage of model context to use (default: 0.85 = 85%)
- `mcp.default_temperature`: AI model temperature setting
- `logging.level`: Logging verbosity
- `session.ttl_seconds`: Session time-to-live (default: 15552000 = 6 months)
- `history.enabled`: Enable/disable long-term history system

The project uses a YAML-based configuration system managed by the `mcp-config` CLI tool. This is the recommended way to manage settings. Environment variables can also be used, which is particularly useful for integrating with clients like Claude Desktop, and they will override YAML settings.


## Development Notes

- Python 3.13+ required
- Uses `uv` package manager
- FastMCP framework for MCP protocol handling
- Descriptor-based tool system with parameter routing
- All adapters must implement `BaseAdapter.generate()` method
- Tools defined as dataclasses with `@tool` decorator
- Parameters use `Route.prompt()`, `Route.adapter()`, etc. for routing
- **Critical**: Always use absolute paths in context parameters

## File Paths

**Important**: When using this server, always provide absolute paths in `context` parameters:
- ✅ Correct: `["/Users/username/project/src/"]`
- ❌ Avoid: `["./src/", "../other/"]`

Relative paths will be resolved relative to the MCP server's working directory, not the client's.

## Testing

### Standardized Developer Workflow

The project uses Makefile as the **single source of truth** for all test commands, ensuring consistency across local development, pre-commit hooks, and CI/CD.

| Command               | Purpose                      | When to Use                           |
|-----------------------|------------------------------|---------------------------------------|
| `make test`           | Fast unit tests              | Before every commit (pre-commit hook) |
| `make test-unit`      | Full unit tests + coverage   | Before PR (pre-push hook)             |
| `make test-integration` | Integration tests with mocks | After adapter changes                 |
| `make e2e`            | End-to-end Docker tests      | Before major releases                 |
| `make ci`             | All CI checks locally        | Before pushing to CI                  |
| `make lint`           | Static analysis              | Part of all workflows                 |

### Test Categories

**Unit Tests** (`tests/unit/`):
- Test individual components in isolation
- All dependencies mocked
- Fast execution (< 4 seconds total)
- Run on every commit via pre-commit hooks

**Integration Tests** (`tests/internal/`):
- Test component interactions with MockAdapter
- Verify end-to-end tool execution workflows
- Mock external APIs but test real component plumbing
- Environment: `MCP_ADAPTER_MOCK=1` (set automatically by Makefile)

**MCP Integration Tests** (`tests/integration_mcp/`):
- Test MCP protocol compliance
- Validate tool registration and execution
- Mock adapters for consistent results

**E2E Tests** (`tests/e2e_dind/`):
- Docker-in-Docker complete system validation
- Real API calls in controlled environment
- Full deployment testing

## Key Dependencies

- `fastmcp`: MCP protocol implementation
- `openai`: OpenAI API client with Responses API support
- `google-genai`: Google Vertex AI client
- `tiktoken`: Token counting
- `lxml`: XML processing for prompts
- `pydantic-settings`: Configuration management
- Python descriptors for parameter routing system

 # Project Build Protocol

This repository is developed using a **contract-first, test-driven** workflow designed to avoid “platonic components” that don’t integrate.

The rules below apply to **any language / stack / project type** (backend, UI, pipelines, infra).

---

## Core Principle

**Representations first, behavior second, internals last.**

If the system cannot reliably round-trip its core data across its real boundaries (API wire formats, storage, schemas, migrations), then the spec/stack/encoding must be revised **before** significant implementation begins.

---

## Gates and Order of Work

### Gate 0 — Representation Contract Tests (RCT) MUST be green
Before writing E2E/integration tests or implementing features, establish a minimal suite of **Representation Contract Tests** that validates:

- API payloads ↔ types ↔ validation (or equivalent boundary)
- Persisted data ↔ types (DB/local storage/files) using the real storage layer
- Optional/null semantics (e.g., NULL vs “unset”/NONE)
- IDs/links/enums encoding strategy (stable, deterministic)
- Migrations/versioning apply cleanly and preserve compatibility

**If RCT fails:** stop and challenge the spec or representation strategy. Do not proceed.

> RCT should be small and ruthless (≈10–30 tests). It is a permanent guardrail.

---

### Gate 1 — E2E Scenarios exist and are executable (red is OK)
Define a small set of **E2E scenarios** (Given/When/Then) using only real external interfaces:
- HTTP/CLI/UI automation/etc.
- Real runtime harness (containers/emulators/test servers as applicable)

E2E tests may be red, but they must:
- start reliably
- fail for expected reasons (not “couldn’t boot”, “connection refused”, missing env)

---

### Gate 2 — Integration Choke-Point tests exist and are executable (red is OK)
Write **integration tests** that validate the **wiring seams** between subsystems, e.g.:
- API ↔ policy/authz ↔ storage
- migrations ↔ runtime startup
- background workers ↔ queues/outbox ↔ stream
- UI ↔ API ↔ state/cache (for frontend)

Integration tests are not “unit tests that hit a DB.”
They must prove **cross-component invariants**.

---

### Gate 3 — Unit tests are added only when they help unblock Gate 2/1
Unit tests are optional and should be written where they provide fast feedback for local logic.

Unit tests are not a substitute for integration/E2E.

---

## Implementation Order (Bottom-Up)

When tests exist (Gates 0–2 satisfied):

1) Implement minimal internals to get **unit** tests green (if present)
2) Prioritize getting **integration** tests green (main work)
3) Finally get **E2E** scenarios green (system behavior)

**Rule:** The system is only considered working when E2E scenarios pass.

---

## Definition of “Integration Test” (Strict)

A test qualifies as an integration test only if it exercises **at least two** of:
- external interface (HTTP/CLI/UI automation)
- policy/authz layer
- storage layer (real DB/local storage)
- migrations/versioning
- background processing / queues / streams
- cross-service boundaries (router/proxy/etc.)

…and asserts at least one **cross-component invariant**.

---

## PR / Change Rules

### Every meaningful change must improve system fit
- A PR should turn at least **one Integration or E2E** test from red → green,
  or introduce a new failing test and then make it pass.

“Unit-only PRs” are discouraged unless they directly unblock an integration test.

### Any change to representations must update RCT
If you change:
- wire format
- schema/migrations
- enum encoding
- ID formats
- null/optional semantics
- persisted state formats

…then update RCT and keep it green.

### Avoid “spec drift by implementation”
If an implementation cannot satisfy the spec without hacks or excessive complexity:
- stop
- propose a spec adjustment (or representation strategy change)
- update Gate 0 RCT accordingly

---

## Reviewer Mental Model (for self-check)

Before declaring a feature “done,” verify:
- Can a real client call it and get correct behavior?
- Does it obey policy/authz/redaction rules?
- Does it survive restarts/migrations (where applicable)?
- Do integration tests prove system wiring, not just type correctness?

---

## Output Discipline

When reporting progress, always state:
- Which gate you’re working on (0/1/2/3)
- Which tests were added/changed
- Which tests moved red → green (and how)

Avoid claiming completeness based on code quality alone.
Passing system-level tests is the source of truth.

