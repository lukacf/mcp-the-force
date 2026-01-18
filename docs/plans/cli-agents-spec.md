# CLI Agents Adapter - Specification

> **Status**: Draft
> **Methodology**: [RCT](../rtc_methodology.md) — contract-first, test-driven with Agent Gates
> **Architecture**: [cli-agents-architecture.md](cli-agents-architecture.md)

---

## Introduction

### What We're Building

**CLI Agents** adds agentic AI assistants (Claude Code, Gemini CLI, Codex CLI) as first-class tools in mcp-the-force. Instead of calling AI model APIs directly, these tools spawn CLI subprocesses that can read files, run commands, and take autonomous action.

### Goals

1. **Unified Tool API**: Replace 12+ `chat_with_*` tools with two semantic tools:
   - `work_with(agent, task)` — Agentic, can take action (default choice). Agent is a model name (e.g., "gpt-5.2"), system resolves to CLI.
   - `consult_with(model, question)` — Advisory, opinions only (no tools). Same model names, routes to API.

2. **Session Continuity**: Same `session_id` works across all tools. Conversations flow seamlessly between CLI agents and API models.

3. **Environment Isolation**: Each CLI session runs in an isolated HOME directory with minimal config (no MCPs, safe defaults).

4. **Extensibility**: Easy to add new CLI agents or roles without changing core architecture.

### Non-Goals

- Real-time streaming of CLI output (batch response only)
- Running multiple CLI agents in parallel within a single request
- Exposing CLI-specific features beyond core task execution

---

## Agentic Review Gates

This spec uses **agentic reviews** at the end of each phase. The agent performing implementation work spawns specialized reviewer sub-agents **in parallel** to validate the phase before proceeding.

### How It Works

1. **Implementation agent** completes phase checklist
2. **Implementation agent** spawns reviewer sub-agents (one per reviewer role)
3. **Reviewers run in parallel**, each producing a verdict
4. **All reviewers must approve** (or issues must be addressed) before proceeding

### Spawning Reviewers

Use the Task tool to spawn reviewer agents in parallel with Opus model:

```
Task(
    subagent_type="general-purpose",
    model="opus",
    prompt="<reviewer prompt from Appendix>"
)
```

Spawn ALL reviewers for a phase in a **single message** with multiple Task tool calls. This ensures they run in parallel.

### Reviewer Roles

| Reviewer | Scope | Blocks If |
|----------|-------|-----------|
| **RCT Guardian** | Representation boundaries | Schema changed without RCT update, round-trip broken, NULL semantics drifted |
| **Integration Sheriff** | Cross-component wiring | Choke point touched without integration test, wiring invariant violated |
| **Spec Auditor** | Requirements compliance | MUST/REQUIRED behavior missing, spec drift without update |
| **Concurrency Gate** | Session isolation | Shared state between sessions, race conditions possible |
| **Code Health** | Production readiness (soft) | Only blocks for clear production risks |

### Verdict Format

Each reviewer outputs a structured verdict:

```yaml
verdict: APPROVE | BLOCK
gate: <gate name>
blocking:
  - id: <unique id>
    claim: "<what's wrong>"
    evidence_type: TEST_MISSING | TEST_FAILING | SPEC_VIOLATION
    evidence: "<specific test or spec clause>"
    fix: "<actionable fix>"
non_blocking:
  - id: <id>
    note: "<suggestion>"
```

### Rules

- **Max 3 blocking issues per reviewer** — additional concerns are non-blocking
- **Evidence required** — reviewers can only block with test/spec evidence
- **Scope enforcement** — reviewers can only block within their scope

---

## Implementation Notes & Lessons Learned

### ToolMetadata Attribute Access

Access spec_class attributes via the `spec_class` property:

```python
# ❌ WRONG
metadata.service_cls  # AttributeError

# ✅ CORRECT
metadata.spec_class.service_cls
```

### Gate Review Iteration

Expect multiple BLOCK → fix → re-run cycles:

1. Run all reviewers in parallel
2. If ANY returns BLOCK, address feedback
3. Re-run ALL reviewers (not just the one that blocked)
4. Repeat until all APPROVE

This is normal. The spec captures this in exit criteria.

---

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **MCP-visible tools** | Only `work_with` + `consult_with` | Simplifies API surface; `chat_with_*` become internal-only |
| **CLI plugin registration** | `@cli_plugin` decorator | Consistent with `@tool` pattern; import-time registration to `CLI_PLUGIN_REGISTRY` |
| **Architecture pattern** | LocalService (validated) | CLI agents spawn subprocesses, not API calls; confirmed in Phase 0 RCT |
| Summarization model | `gemini-3-flash-preview` | Fast, cheap, good at summarization |
| Summarization trigger | Always | All CLI output passes through summarizer for consistency |
| CI testing strategy | Mock CLI scripts | Bash scripts output known JSON, hermetic CI |
| Migration approach | `internal_only=True` | `chat_with_*` still in TOOL_REGISTRY (for `consult_with` routing) but not exposed via MCP |
| Agent parameter | Model name | User specifies model (e.g., "gpt-5.2"), system resolves to CLI via `cli` attribute |
| Model naming | Unified vocabulary | Both `work_with(agent=)` and `consult_with(model=)` use same model names from registry |
| Model→CLI mapping | Via `cli` attribute | Model blueprints declare `cli` attribute: openai→codex, google→gemini, anthropic→claude |
| Blueprint extension | Add `cli` attr | Only new attribute on existing blueprints; no new blueprint system |
| Integration with autogen | Reuse existing | `model_cli_resolver` reads from same adapter registry that autogen uses |
| Project access | Full project | CLI agent gets `--add-dir` to project root by default |
| Cross-tool history | Caller decides | MCP user decides whether to continue session; not automatic injection |
| Timeout behavior | Partial + error | Return captured output plus error on timeout |
| Usage tracking | Full metrics | Time, CLI version, return code, output size via existing logging |
| Role extensibility | File-based | Custom roles via `.mcp-the-force/roles/*.txt` |
| Missing CLI handling | Startup + runtime | Check at startup (warn), clear error at runtime |
| CLI flags | Raw parameter | Power users can pass `cli_flags` for additional CLI arguments |

---

## Phase 0: RCT — Representation Contract Tests

**Gate**: 0 (MUST be green before proceeding)
**Purpose**: Prove CLIs and storage work as assumed. If any test fails, stop and revise design.

### Checklist

- [x] **0.1** Run Claude Code spike script (`scripts/rct/test_claude_headless.sh`)
  - Validates: headless JSON, session_id extraction, `--resume`, HOME isolation, `--add-dir`
  - Update capabilities matrix row for Claude

- [x] **0.2** Run Gemini CLI spike script (`scripts/rct/test_gemini_headless.sh`)
  - Validates: headless JSON, session extraction, resume mechanism, config isolation
  - Update capabilities matrix row for Gemini

- [x] **0.3** Run Codex CLI spike script (`scripts/rct/test_codex_headless.sh`)
  - Validates: exec JSON/JSONL, threadId extraction, `--cd`, HOME isolation
  - Update capabilities matrix row for Codex

- [x] **0.4** Create storage round-trip tests (`tests/rct/test_session_roundtrip.py`)
  - CLI session mapping: write → read → equals
  - Conversation turn with CLI metadata: roundtrip preserves fields

- [x] **0.5** Create CLI output format tests (`tests/rct/test_cli_output_formats.py`)
  - Minimum viable schemas (only fields we extract)
  - Parser compatibility with real CLI output samples

- [x] **0.6** Run CLI model support spike script (`scripts/rct/test_cli_model_support.sh`)
  - Test which models each CLI actually supports (requires real API calls)
  - Finding: gpt-5.2-pro IS supported by codex (contrary to initial assumption)
  - Finding: claude-3-opus is NOT supported (deprecated)
  - Update Model Support Matrix below with results
  - NOTE: Cannot be automated in pytest (requires API calls, costs money)

### Capabilities Matrix (completed 2026-01-17)

| Capability | Claude | Gemini | Codex | Notes |
|------------|--------|--------|-------|-------|
| Headless JSON output | ✅ | ✅ | ✅ | `--print --output-format json` / `--output-format json` / `exec --json` |
| Session ID in output | ✅ | ✅ | ✅ | Field: `session_id` (Claude/Gemini), `thread_id` (Codex) |
| Resume specific session | ✅ | ✅ | ✅ | Flag: `--resume <id>` / `--resume latest` / `exec resume <id>` |
| Resume in headless mode | ✅ | ✅ | ✅ | All CLIs support combining resume with JSON output |
| HOME isolation works | ✅ | ✅ | ✅ | Custom HOME directory respected by all CLIs |
| Project dir access | ✅ | ✅ | ✅ | Via: `--add-dir` / `--include-directories` / `--add-dir` + `--cd` |

**Legend**: ✅ works, ❌ doesn't work, ⚠️ works with caveats, ⬜ not tested

> **RCT Status**: All capabilities validated. See [cli-agents-rct-findings.md](cli-agents-rct-findings.md) for details.

### Model Support Matrix (completed 2026-01-18)

| Model | Claude | Gemini | Codex | Notes |
|-------|--------|--------|-------|-------|
| claude-sonnet-4-5 | ✅ | - | - | Anthropic model |
| claude-opus-4-5-20251101 | ✅ | - | - | Anthropic model |
| claude-3-opus | ❌ | - | - | Not found (deprecated?) |
| sonnet (alias) | ✅ | - | - | Alias for latest sonnet |
| opus (alias) | ✅ | - | - | Alias for latest opus |
| gemini-3-pro-preview | - | ✅ | - | Google model |
| gemini-3-flash-preview | - | ✅ | - | Google model |
| gemini-2.5-flash | - | ✅ | - | Google model |
| gemini-2.5-pro | - | ✅ | - | Google model |
| gpt-5.2 | - | - | ✅ | OpenAI model |
| gpt-5.2-pro | - | - | ✅ | OpenAI model |
| gpt-4.1 | - | - | ✅ | OpenAI model |
| gpt-5.1-codex-max | - | - | ✅ | OpenAI model |
| o3 | - | - | ✅ | OpenAI reasoning model |
| o4-mini | - | - | ✅ | OpenAI reasoning model |

**Legend**: ✅ supported, ❌ not supported, `-` not applicable

> **RCT Status**: Validated via `./scripts/rct/test_cli_model_support.sh` on 2026-01-18.

### Gate Review: Phase 0

**Exit Criteria**:
1. All RCT tests green
2. Capabilities matrix complete
3. **ALL review agents must return APPROVE verdict**
4. If any agent returns BLOCK, address the feedback and re-run ALL review agents
5. Update completed checkboxes in this document after gate review passes

**Reviewers**: Use prompts from [Appendix: Reviewer Agent Prompts](#appendix-reviewer-agent-prompts) with `{PHASE}=0`.

**Phase-Specific Verification Commands** (for `{PHASE_SPECIFIC_COMMANDS}`):
```bash
# Phase 0: Verify RCT coverage for all CLIs
python -m pytest tests/rct/test_cli_output_formats.py -v 2>&1
python -m pytest tests/rct/test_session_roundtrip.py -v 2>&1
python -m pytest tests/rct/test_cli_command_formats.py -v 2>&1
```

**Review Status**:
- [ ] **RCT Guardian**: (pending)

---

### Phase 0 Decision Point: Document Updates

> **Required**: Even if all RCT tests pass, this step captures learnings and updates documents.

- [x] **0.6** Review findings and update documentation

  **Findings Report** (create `docs/plans/cli-agents-rct-findings.md`):
  - Capabilities matrix summary (what works, what doesn't, caveats)
  - Unexpected behaviors discovered
  - Field names, flag syntax, and output formats observed
  - Performance characteristics (startup time, output size)
  - Any security considerations discovered

  **Architecture Updates** (`docs/plans/cli-agents-architecture.md`):
  - [x] Confirm or revise LocalService recommendation based on findings
  - [x] Update interface definitions with actual field names from CLI output
  - [x] Add/remove/modify components based on discovered requirements
  - [x] Document any CLI-specific quirks that affect design

  **Spec Updates** (`docs/plans/cli-agents-spec.md`):
  - [x] Update capabilities matrix with actual results
  - [x] Revise checklist items if scope changed (e.g., CLI doesn't support feature)
  - [x] Add new requirements discovered during RCT
  - [x] Remove requirements that are no longer applicable
  - [x] Update test names/paths if they changed

  **Decision Required**:
  - [x] **PROCEED**: Findings confirm design, move to Phase 1
  - [ ] **REVISE**: Significant issues found, update design before proceeding
  - [ ] **DESCOPE**: CLI doesn't support required features, remove from scope

**Exit criteria**: Findings documented. Architecture and spec updated. Explicit proceed/revise/descope decision recorded.

---

## Phase 1: Test-First — E2E & Integration Tests

**Gate**: 1 + 2 (red is OK, but must be executable)
**Purpose**: Define system behavior as real tests before implementation (TDD).

### Checklist

- [x] **1.1** Create E2E tests (`tests/e2e/test_cli_agents.py`)
  - Scenario: `work_with(agent="claude-sonnet-4-5")` → resolves to claude CLI, returns response
  - Scenario: `work_with(agent="gemini-3-flash-preview")` → resolves to gemini CLI, returns response
  - Scenario: `work_with(agent="gpt-5.2")` → resolves to codex CLI, returns response
  - Scenario: Resume same CLI → `--resume` flag used (model→CLI consistent)
  - Scenario: Codex resume → `exec resume` command used (different pattern)
  - Scenario: Cross-CLI handoff → context injected (e.g., claude-sonnet-4-5 → gemini-3-flash-preview)
  - Scenario: API→CLI handoff → `consult_with` history compacted into `work_with`
  - Scenario: `consult_with` multi-turn → session continuity via internal routing
  - Tests are real (import actual modules, call actual functions, assert real behavior)
  - Tests fail with `NotImplementedError` (code stubs exist, behavior not implemented)

- [x] **1.2** Create integration tests (`tests/integration/cli_agents/`)
  - `test_session_bridge.py`: SessionBridge ↔ SQLite mapping persistence
  - `test_executor.py`: CLIExecutor ↔ subprocess ↔ Parser
  - `test_mcp_tool.py`: MCP tool ↔ LocalService ↔ session cache
  - `test_cross_tool.py`: Compactor ↔ context injection
  - `test_model_cli_map.py`: Model registry ↔ CLI plugin resolution
  - `test_cli_plugin.py`: CLI plugin registration ↔ discovery ↔ validation

- [x] **1.3** Create choke point matrix (`docs/choke-points-cli-agents.yaml`)
  - CP-CLI-SESSION: session mapping + resume
  - CP-CROSS-TOOL: cross-tool context injection
  - CP-MCP-WIRING: tool → LocalService → cache flow
  - CP-CLI-PLUGIN: `@cli_plugin` decorator → `CLI_PLUGIN_REGISTRY` → discovery
  - CP-MODEL-CLI-MAP: model name → CLI plugin resolution
  - CP-EXECUTOR: subprocess execution + output parsing
  - CP-PARSER: CLI output parsing

- [x] **1.4** Create unit tests (`tests/unit/cli_agents/`)
  - Parser tests (Claude, Gemini, Codex)
  - Environment builder tests
  - Session bridge CRUD tests
  - Compactor logic tests
  - Command builder tests
  - Summarizer tests

- [x] **1.5** Create RCT for command construction (`tests/rct/test_cli_command_formats.py`)
  - Claude resume command format (`--resume <session_id>`)
  - Gemini resume command format (`--resume <session_id>`)
  - Codex resume command format (`exec resume <thread_id>`) — CRITICAL: different pattern!
  - Cross-CLI resume semantics validation

- [x] **1.5.1** Create RCT for CLI plugin registration (`tests/rct/test_cli_plugin_registration.py`)
  - `@cli_plugin` decorator registers plugin in `CLI_PLUGIN_REGISTRY`
  - `get_cli_plugin()` returns registered plugin
  - `get_cli_plugin()` returns None for unknown CLI (not exception)
  - `list_cli_plugins()` returns all registered CLI names

- [x] **1.6** Create module scaffolding (stubs with `NotImplementedError`)
  - `mcp_the_force/cli_agents/` package
  - `mcp_the_force/cli_agents/model_cli_resolver.py` — model→CLI resolution
  - `mcp_the_force/cli_plugins/` package — CLI plugin registry with `@cli_plugin` decorator
  - `mcp_the_force/cli_plugins/base.py` — CLIPlugin protocol
  - `mcp_the_force/cli_plugins/registry.py` — CLI_PLUGIN_REGISTRY, @cli_plugin, get_cli_plugin, list_cli_plugins
  - `mcp_the_force/tools/work_with.py` registered in TOOL_REGISTRY
  - `mcp_the_force/tools/consult_with.py` registered in TOOL_REGISTRY
  - `mcp_the_force/local_services/cli_agent_service.py` service stubs

### Gate Review: Phase 1

**Exit Criteria**:
1. All test files exist and run (failures expected because code not implemented)
2. Choke points documented
3. **ALL review agents must return APPROVE verdict**
4. If any agent returns BLOCK, address the feedback and re-run ALL review agents
5. Update completed checkboxes in this document after gate review passes

**Reviewers**: Use prompts from [Appendix: Reviewer Agent Prompts](#appendix-reviewer-agent-prompts) with `{PHASE}=1`.

**Phase-Specific Verification Commands** (for `{PHASE_SPECIFIC_COMMANDS}`):
```bash
# Phase 1: Verify tests fail at assertion level, not import level
python -m pytest tests/e2e/test_cli_agents.py -v --tb=line 2>&1 | head -60
python -m pytest tests/e2e/test_cli_agents.py::test_work_with_anthropic_model_returns_response -v --tb=short 2>&1 | tail -30
python -m pytest tests/integration/cli_agents/test_model_cli_map.py -v --tb=short 2>&1 | tail -30
# NEW: CLI plugin registration tests
python -m pytest tests/rct/test_cli_plugin_registration.py -v --tb=short 2>&1 | tail -30
python -m pytest tests/integration/cli_agents/test_cli_plugin.py -v --tb=short 2>&1 | tail -30
```

**Review Status** (COMPLETED 2026-01-18):
- [x] **Integration Sheriff**: APPROVE - All choke points have tests, all tests fail at NotImplementedError (correct TDD mode)
- [x] **Spec Auditor**: APPROVE - All REQ-X.Y.Z have test coverage, TDD compliance verified


**Phase 1 Results**: ✅ PASSED - Ready to proceed to Phase 2

## Phase 2: Core Infrastructure

**Gate**: 3 → 2 (unit green first, then integration)
**Purpose**: Build foundational components bottom-up.

### Checklist

**Note**: Infrastructure goes under `mcp_the_force/cli_agents/` (new module), used by LocalService.

- [ ] **2.1** Implement CLI parsers (`mcp_the_force/cli_agents/parsers/`)
  - `base.py`: BaseParser protocol, content extraction
  - `claude.py`: Claude JSON parsing, session_id + result/message extraction
  - `gemini.py`: Gemini JSON parsing (field names from RCT)
  - `codex.py`: Codex JSONL parsing, threadId extraction
  - **Unit tests green**

- [ ] **2.1.1** Implement output summarizer (`mcp_the_force/cli_agents/summarizer.py`)
  - Always summarize CLI output via `gemini-3-flash-preview`
  - Preserve key information: decisions, code changes, file paths
  - Include raw output in session metadata for debugging
  - **Unit tests green**

- [ ] **2.2** Implement CLI executor (`mcp_the_force/cli_agents/executor.py`)
  - Async subprocess execution
  - Timeout handling (kill on timeout)
  - Stream capture with limit (10MB)
  - **Unit tests green**

- [ ] **2.3** Implement session bridge (`mcp_the_force/cli_agents/session_bridge.py`)
  - SQLite schema for CLI session mapping
  - `get_cli_session_id(project, session_id, cli_name)`
  - `store_cli_session_id(...)`
  - **Unit tests green**, **RCT round-trip green**

- [ ] **2.4** Implement environment isolation (`mcp_the_force/cli_agents/environment.py`)
  - Session directory creation (`~/.mcp-the-force/cli_sessions/{session_id}/{cli}/`)
  - HOME redirection
  - Minimal CLI config generation (no MCPs, safe defaults)
  - **Note**: Command building is in CLI plugins (`cli_plugins/*.py`), not here
  - **Unit tests green**

- [ ] **2.4.1** Implement CLI availability checker (`mcp_the_force/cli_agents/availability.py`)
  - Check which CLIs are installed at startup (log warnings for missing)
  - Provide clear error message at runtime if CLI not available
  - Include install instructions in error (e.g., "Install with: npm install -g @anthropic/claude-code")
  - **Unit tests green**

- [ ] **2.5** Implement role system (`mcp_the_force/cli_agents/roles.py`)
  - Load built-in roles from package resources
  - Load custom roles from `.mcp-the-force/roles/*.txt`
  - Built-in roles:
    - `default.txt`: General assistant, cite paths, markdown
    - `planner.txt`: Design, phases, dependencies
    - `codereviewer.txt`: Quality, security, OWASP
  - Custom roles override built-in if same name

### Gate Review: Phase 2

**Exit Criteria**:
1. All unit tests green
2. Integration tests making progress (some green)
3. **ALL review agents must return APPROVE verdict**
4. If any agent returns BLOCK, address the feedback and re-run ALL review agents
5. Update completed checkboxes in this document after gate review passes

**Reviewers**: Use prompts from [Appendix: Reviewer Agent Prompts](#appendix-reviewer-agent-prompts) with `{PHASE}=2`.

**Phase-Specific Verification Commands** (for `{PHASE_SPECIFIC_COMMANDS}`):
```bash
# Phase 2: Verify unit tests green, integration tests progressing
python -m pytest tests/rct/ -v 2>&1 | tail -30
python -m pytest tests/unit/cli_agents/ -v 2>&1 | tail -50
python -m pytest tests/integration/cli_agents/ -v --tb=line 2>&1 | head -80
```

**Review Status**:
- [ ] **RCT Guardian**: (pending)
- [ ] **Integration Sheriff**: (pending)

---

## Phase 3: Tool Implementation

**Gate**: 2 (integration green)
**Purpose**: Wire tools into MCP and existing adapters.

> **Note**: This is ~90% of the implementation work. Follow existing patterns in codebase.

### 3.1 Architecture — Adapter-Based with CLI Plugins

**Decision**: Extend the existing adapter-based architecture with CLI plugins.

**Key Insight**: The `agent` parameter in `work_with` uses the same model vocabulary as `consult_with`. Model blueprints declare a `cli` attribute that maps to CLI plugins.

#### 3.1.1 Model Blueprint Extension

Each model blueprint gains a `cli` attribute:

```python
# In existing adapter blueprints (mcp_the_force/adapters/*/definitions.py)
class GPT52Blueprint:
    model_name = "gpt-5.2"
    cli = "codex"           # ← NEW: maps to CLI plugin
    provider = "openai"
    context_window = 272000
    ...

class Gemini3FlashBlueprint:
    model_name = "gemini-3-flash-preview"
    cli = "gemini"          # ← NEW: maps to CLI plugin
    provider = "google"
    ...

class Claude45SonnetBlueprint:
    model_name = "claude-sonnet-4-5"
    cli = "claude"          # ← NEW: maps to CLI plugin
    provider = "anthropic"
    ...
```

#### 3.1.2 CLI Plugin Registry

CLI plugins define invocation mechanics (pure infrastructure, no model logic):

```
mcp_the_force/cli_plugins/
├── __init__.py           # Plugin registry
├── base.py               # CLIPlugin protocol
├── claude.py             # Claude Code mechanics
├── gemini.py             # Gemini CLI mechanics
└── codex.py              # Codex CLI mechanics
```

```python
# mcp_the_force/cli_plugins/base.py
class CLIPlugin(Protocol):
    name: str                    # "claude", "gemini", "codex"
    executable: str              # "claude", "gemini", "codex"

    def build_new_session_args(self, task: str, context_dirs: list[str]) -> list[str]: ...
    def build_resume_args(self, session_id: str, task: str) -> list[str]: ...
    def parse_output(self, stdout: str, stderr: str, returncode: int) -> CLIResponse: ...
```

```python
# mcp_the_force/cli_plugins/codex.py
class CodexPlugin(CLIPlugin):
    name = "codex"
    executable = "codex"

    def build_new_session_args(self, task: str, context_dirs: list[str]) -> list[str]:
        return ["--json", task]

    def build_resume_args(self, session_id: str, task: str) -> list[str]:
        return ["exec", "resume", session_id, "--json"]  # Codex-specific!

    def parse_output(self, stdout: str, stderr: str, returncode: int) -> CLIResponse:
        return CodexOutputParser().parse(stdout)
```

#### 3.1.3 Model→CLI Resolution

```python
def resolve_cli_plugin(agent: str) -> CLIPlugin:
    """Resolve model name to CLI plugin."""
    # 1. Look up model in adapter registry
    model_blueprint = get_model_blueprint(agent)
    if not model_blueprint:
        raise ValueError(f"Unknown model: {agent}")

    # 2. Get CLI name from blueprint
    cli_name = model_blueprint.cli
    if not cli_name:
        raise ValueError(f"Model {agent} has no CLI mapping")

    # 3. Look up CLI plugin
    return get_cli_plugin(cli_name)
```

#### 3.1.4 Flow Diagram

```
work_with(agent="gpt-5.2", task="...")
    │
    ▼
┌─────────────────────────────┐
│ Model Registry              │
│ gpt-5.2 → cli="codex"       │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ CLI Plugin Registry         │
│ "codex" → CodexPlugin       │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ CLIAgentService             │
│ ├── uses CodexPlugin        │
│ ├── uses SessionBridge      │
│ ├── uses CLIExecutor        │
│ └── uses CLISessionEnv      │
└─────────────────────────────┘
```

#### 3.1.5 Autogen Integration

Autogen reads the model registry to generate:
- Valid choices for `agent` parameter (all models with `cli` attribute)
- Valid choices for `model` parameter in `consult_with` (all models)
- Documentation showing which CLI each model maps to

### 3.2 work_with Tool — Agentic CLI Tool

**File**: `mcp_the_force/tools/work_with.py`

**Reference**: `mcp_the_force/tools/group_think.py` (LocalService orchestrator pattern)

**Pattern**: LocalService tool that spawns CLI subprocesses. Uses `Route.adapter()` for all parameters since they go to the service, not an AI model prompt.

- [ ] **3.2.1** Create `CLIAgentService` (LocalService protocol)
  ```python
  # mcp_the_force/local_services/cli_agent_service.py
  class CLIAgentService:
      """Spawns and manages CLI agent subprocesses."""

      async def execute(
          self,
          agent: str,           # Model name (e.g., "gpt-5.2") - resolves to CLI via registry
          task: str,
          role: str,
          session_id: str,
          context: List[str],
          cli_flags: List[str],
          **kwargs
      ) -> str:
          # 1. Resolve model→CLI: agent="gpt-5.2" → cli_plugin=CodexPlugin
          # 2. Check CLI availability (error if not installed)
          # 3. Get/create CLISessionEnvironment
          # 4. Check SessionBridge for existing CLI session
          # 5. Load role prompt (built-in or custom from .mcp-the-force/roles/)
          # 6. Build command via cli_plugin.build_*_args()
          # 7. Append cli_flags to command
          # 8. Execute via CLIExecutor
          # 9. Parse response via cli_plugin.parse_output()
          # 10. Summarize output via Gemini Flash (always)
          # 11. Log metrics (time, CLI version, return code, output size)
          # 12. Store CLI session mapping
          # 13. Store raw output in session metadata
          # 14. Return summarized content
  ```

- [ ] **3.2.2** Create `@tool` decorated `WorkWith` class
  ```python
  @tool
  class WorkWith(ToolSpec):
      model_name = "work_with"
      adapter_class = None              # LocalService, not an adapter
      service_cls = CLIAgentService
      timeout = 1800                    # 30 min default
      description = """Default choice for most tasks. Spawns agentic assistant
      that can read files, run commands, take action. Use for help *doing* something.
      Agent is a model name (e.g., gpt-5.2, claude-sonnet-4-5) - system resolves to CLI.
      Roles: default, planner, codereviewer."""
  ```

- [ ] **3.2.3** Define parameters using Route.adapter() (all go to service)
  ```python
  # All Route.adapter() - parameters go to LocalService.execute()
  agent: str = Route.adapter(
      description="Model name (e.g., 'gpt-5.2', 'claude-sonnet-4-5'). Resolves to CLI via model registry."
  )
  task: str = Route.adapter(
      description="What to do - the task/prompt for the agent"
  )
  role: str = Route.adapter(
      default="default",
      description="Role: default, planner, codereviewer, or custom from .mcp-the-force/roles/"
  )
  session_id: str = Route.adapter(
      description="Session ID for conversation continuity"
  )
  context: List[str] = Route.adapter(
      default_factory=list,
      description="Additional file paths (project root included by default)"
  )
  cli_flags: List[str] = Route.adapter(
      default_factory=list,
      description="Additional CLI flags for power users (e.g., ['--dangerously-skip-permissions'])"
  )
  ```

- [ ] **3.2.4** Verify auto-registration via `@tool` decorator
  - Tool ID: `work_with` (from class name)
  - Appears in `TOOL_REGISTRY`

### 3.3 consult_with Tool — Advisory API Tool

**File**: `mcp_the_force/tools/consult_with.py`

**Reference**: `mcp_the_force/tools/group_think.py` (orchestrator pattern)

**Pattern**: LocalService tool that uses `TOOL_REGISTRY` to look up and execute existing tools.

- [ ] **3.3.1** Create `ConsultationService` (LocalService protocol)
  ```python
  # mcp_the_force/local_services/consultation_service.py
  class ConsultationService:
      """Routes to existing tools via TOOL_REGISTRY."""

      async def execute(
          self,
          model: str,           # e.g., "gpt52", "gemini-3-pro"
          question: str,
          session_id: str,
          context: List[str],
          output_format: str,
          **kwargs
      ) -> str:
          # 1. Look up tool in TOOL_REGISTRY by model name
          #    - Try exact match: "gpt52" -> "chat_with_gpt52"
          #    - Or use blueprint model_name mapping
          # 2. Get tool metadata from registry
          # 3. Execute via executor with proper parameters
          # 4. Return response content
  ```

- [ ] **3.3.2** Implement model discovery from TOOL_REGISTRY
  ```python
  def _resolve_model_tool(self, model: str) -> ToolMetadata:
      """Resolve user-friendly model name to registered tool."""
      from mcp_the_force.tools.registry import TOOL_REGISTRY

      # Try direct lookup: "chat_with_gpt52"
      if f"chat_with_{model}" in TOOL_REGISTRY:
          return TOOL_REGISTRY[f"chat_with_{model}"]

      # Try by model_name in tool metadata
      for tool_id, metadata in TOOL_REGISTRY.items():
          if metadata.model_config.get("model_name") == model:
              return metadata

      raise ValueError(f"Unknown model: {model}")
  ```

- [ ] **3.3.3** Create `@tool` decorated `ConsultWith` class
  ```python
  @tool
  class ConsultWith(ToolSpec):
      model_name = "consult_with"
      adapter_class = None              # LocalService, not an adapter
      service_cls = ConsultationService
      timeout = 300                     # 5 min for quick queries
      description = """Quick API query for opinions, analysis, brainstorming.
      No file access, no actions. Use for second perspective without tool access.
      Available models discovered from registered tools."""
  ```

- [ ] **3.3.4** Define parameters using Route.adapter() (all go to service)
  ```python
  # All Route.adapter() - parameters go to LocalService.execute()
  model: str = Route.adapter(
      description="Model name (e.g., gpt52, gemini-3-pro, claude-sonnet)"
  )
  question: str = Route.adapter(
      description="What to ask the model"
  )
  session_id: str = Route.adapter(
      description="Session ID for multi-turn continuity"
  )
  context: List[str] = Route.adapter(
      default_factory=list,
      description="File paths to include as context"
  )
  output_format: str = Route.adapter(
      default="plain text",
      description="Desired response format"
  )
  ```

- [ ] **3.3.5** Wire service to use executor for tool execution
  - Import `executor.execute(metadata, **params)`
  - Pass through session_id for conversation continuity
  - Handle errors gracefully

### 3.4 Session Key Migration

**File**: `mcp_the_force/unified_session_cache.py`

**Current**: Key is `(project, tool, session_id)` — tool-scoped sessions

**Target**: Key is `(project, session_id)` — global sessions, tool in metadata

- [ ] **3.4.1** Update `UnifiedSession` dataclass
  ```python
  # Remove 'tool' from primary key fields
  # Add 'tool' to history turn metadata instead
  ```

- [ ] **3.4.2** Update database schema
  ```sql
  -- Migration: drop tool from composite PK
  -- Add tool column to history entries
  ```

- [ ] **3.4.3** Update `get_session(project, session_id)` signature
  - Remove `tool` parameter
  - Return session with all tools' history

- [ ] **3.4.4** Update `set_session()` and `delete_session()` signatures

- [ ] **3.4.5** Update all callers in executor.py
  - Pass tool name in turn metadata, not key

- [ ] **3.4.6** Add migration for existing sessions (if any)

### 3.5 Hide chat_with_* Tools from MCP (Keep for Internal Routing)

**Important**: `consult_with` needs `chat_with_*` tools internally to route requests. We hide them from MCP but keep them in TOOL_REGISTRY.

**Files**: `mcp_the_force/tools/autogen.py`, `mcp_the_force/tools/integration.py`

- [ ] **3.5.1** Add `internal_only` flag to ToolSpec/ToolMetadata
  ```python
  class ToolSpec:
      # ... existing fields
      internal_only: bool = False  # If True, don't expose via MCP
  ```

- [ ] **3.5.2** Mark chat_with_* tools as internal_only in autogen
  ```python
  # In make_chat_tool() or blueprint processing
  tool_class.internal_only = True
  ```

- [ ] **3.5.3** Filter internal tools in MCP registration (`integration.py`)
  ```python
  def register_all_tools():
      for tool_id, metadata in TOOL_REGISTRY.items():
          if metadata.spec_class.internal_only:
              continue  # Don't register with MCP
          # ... register normally
  ```

- [ ] **3.5.4** Verify chat_with_* still in TOOL_REGISTRY (for consult_with routing)

- [ ] **3.5.5** Verify chat_with_* NOT in MCP tool list

- [ ] **3.5.6** Update CLAUDE.md tool documentation
  - Remove chat_with_* references (they're now internal)
  - Add work_with and consult_with documentation

### 3.6 Integration Verification

- [ ] **3.6.1** `test_mcp_tool.py::test_work_with_registered` — green
- [ ] **3.6.2** `test_mcp_tool.py::test_consult_with_registered` — green
- [ ] **3.6.3** `test_mcp_tool.py::test_chat_with_tools_hidden` — green
- [ ] **3.6.4** `test_session_bridge.py::test_mapping_persists` — green
- [ ] **3.6.5** `test_executor.py::test_resume_flag_used` — green
- [ ] **3.6.6** Manual: call work_with via MCP client, verify response

### Gate Review: Phase 3

**Exit Criteria**:
1. All integration tests green
2. Both tools callable via MCP
3. chat_with_* tools hidden from MCP (internal_only=True)
4. **ALL review agents must return APPROVE verdict**
5. If any agent returns BLOCK, address the feedback and re-run ALL review agents
6. Update completed checkboxes in this document after gate review passes

**Reviewers**: Use prompts from [Appendix: Reviewer Agent Prompts](#appendix-reviewer-agent-prompts) with `{PHASE}=3`.

**Phase-Specific Verification Commands** (for `{PHASE_SPECIFIC_COMMANDS}`):
```bash
# Phase 3: Verify integration tests green, MCP wiring complete
python -m pytest tests/rct/ -v 2>&1 | tail -30
python -m pytest tests/integration/cli_agents/ -v --tb=line 2>&1 | head -100
python -m pytest tests/integration/cli_agents/test_mcp_tool.py -v --tb=short 2>&1
python -m pytest tests/integration/cli_agents/test_environment.py -v --tb=short 2>&1
```

**Review Status**:
- [ ] **RCT Guardian**: (pending)
- [ ] **Integration Sheriff**: (pending)
- [ ] **Spec Auditor**: (pending)
- [ ] **Concurrency Gate**: (pending)

---

## Phase 4: Cross-Tool & Session Continuity

**Gate**: 1 (E2E green)
**Purpose**: Enable seamless conversation flow across tools.

### Checklist

- [ ] **4.1** Implement session compactor (`mcp_the_force/adapters/cli_agents/compactor.py`)
  - `compact_for_cli(history, target_cli, max_tokens)`
  - If history fits: format as context block
  - If history exceeds: summarize via API model
  - Token counting for decision

- [ ] **4.2** Implement cross-tool handoff logic
  - In CLIAgentAdapter: check for existing history from other tools
  - Compact and inject as task prefix
  - Store metadata: `context_injected`, `context_source`

- [ ] **4.3** Implement same-CLI resume logic
  - In CLIAgentAdapter: check for existing CLI session mapping
  - Use native `--resume` flag when available
  - Store metadata: `resumed_from`, `used_resume_flag`

- [ ] **4.4** Validate E2E scenarios
  - All E2E tests green
  - Manual smoke test of cross-tool conversation

### Gate Review: Phase 4

**Exit Criteria**:
1. All E2E scenarios green
2. Cross-tool handoff working
3. **ALL review agents must return APPROVE verdict**
4. If any agent returns BLOCK, address the feedback and re-run ALL review agents
5. Update completed checkboxes in this document after gate review passes

**Reviewers**: Use prompts from [Appendix: Reviewer Agent Prompts](#appendix-reviewer-agent-prompts) with `{PHASE}=4`.

**Phase-Specific Verification Commands** (for `{PHASE_SPECIFIC_COMMANDS}`):
```bash
# Phase 4: Verify E2E scenarios green, cross-tool handoff working
python -m pytest tests/integration/cli_agents/test_cross_tool.py -v --tb=short 2>&1
python -m pytest tests/integration/cli_agents/test_session_bridge.py -v --tb=short 2>&1
python -m pytest tests/e2e/test_cli_agents.py -v --tb=line 2>&1 | head -60
```

**Review Status**:
- [ ] **Integration Sheriff**: (pending)
- [ ] **Concurrency Gate**: (pending)
- [ ] **Spec Auditor**: (pending)

---

## Phase 5: Configuration & Completion

**Gate**: Full review board
**Purpose**: Finalize configuration, documentation, and validation.

### Checklist

- [ ] **5.1** Update configuration
  - Add `cli_agents:` section to config schema
  - Document in config.yaml.example
  - Add CLI-specific env vars if needed

- [ ] **5.2** Update documentation
  - README: new tool API
  - CLAUDE.md: work_with/consult_with usage
  - Migration guide if needed

- [ ] **5.3** Final validation
  - Full test suite green (RCT, unit, integration, E2E)
  - Manual testing of all scenarios
  - Performance check (timeout, memory)

### Gate Review: Phase 5 (Final)

**Exit Criteria**:
1. All tests green (RCT, unit, integration, E2E)
2. Documentation complete
3. **ALL review agents must return APPROVE verdict**
4. If any agent returns BLOCK, address the feedback and re-run ALL review agents
5. Update completed checkboxes in this document after gate review passes
6. Ready for merge

**Reviewers**: Use prompts from [Appendix: Reviewer Agent Prompts](#appendix-reviewer-agent-prompts) with `{PHASE}=5 (Final)`.

**Phase-Specific Verification Commands** (for `{PHASE_SPECIFIC_COMMANDS}`):
```bash
# Phase 5 (Final): Verify all tests green, ready for merge
python -m pytest tests/rct/ -v 2>&1
python -m pytest tests/integration/cli_agents/ -v 2>&1
python -m pytest tests/e2e/test_cli_agents.py -v 2>&1
python -m pytest tests/ -k "cli_agents" -v 2>&1 | tail -100
```

**Review Status**:
- [ ] **RCT Guardian**: (pending)
- [ ] **Integration Sheriff**: (pending)
- [ ] **Spec Auditor**: (pending)
- [ ] **Concurrency Gate**: (pending)
- [ ] **Code Health**: (pending, soft gate)

---

## Appendix: Requirements Traceability

| REQ | Description | Test Coverage |
|-----|-------------|---------------|
| REQ-1.1.1 | work_with parameters | `test_mcp_tool.py::test_work_with_registered_in_tool_registry` |
| REQ-1.1.2 | CLI subprocess spawn | `test_executor.py::test_executor_spawns_subprocess_with_correct_env` |
| REQ-1.1.3 | Structured response | `test_mcp_tool.py::test_work_with_dispatches_to_cli_agent_service` |
| REQ-1.2.1 | consult_with parameters | `test_mcp_tool.py::test_consult_with_registered_in_tool_registry` |
| REQ-1.2.2 | Route to API adapters | `test_mcp_tool.py::test_consult_with_routes_to_internal_chat_tool` |
| REQ-1.3.1 | Hide chat_with_* from MCP | `test_mcp_tool.py::test_chat_with_tools_not_exposed_via_mcp` |
| REQ-3.1.1 | Session ID mapping | `test_session_bridge.py::test_store_and_retrieve_cli_session_mapping` |
| REQ-3.2.1 | History compaction | `test_cross_tool.py::test_compactor_formats_history_when_fits` |
| REQ-3.3.1 | Native resume (Claude/Gemini) | `test_executor.py::test_resume_flag_added_when_mapping_exists` |
| REQ-3.3.1 | Native resume (Codex) | `test_cli_command_formats.py::TestCodexCommandFormat::test_resume_command_uses_exec_resume` |
| REQ-3.3.2 | Cross-tool inject | `test_cross_tool.py::test_cross_cli_handoff_injects_compacted_context` |
| REQ-4.3.2 | Output summarization | `test_summarizer.py::test_always_summarizes_cli_output` |
| REQ-5.1.2 | HOME isolation | `test_environment.py::test_home_redirect_creates_isolated_path` |
| REQ-6.1-6.4 | Role prompts | Manual verification |

---

## Appendix: File Manifest

| File | Phase | Purpose |
|------|-------|---------|
| `scripts/rct/test_claude_headless.sh` | 0 | Claude spike |
| `scripts/rct/test_gemini_headless.sh` | 0 | Gemini spike |
| `scripts/rct/test_codex_headless.sh` | 0 | Codex spike |
| `tests/rct/test_session_roundtrip.py` | 0 | Storage RCT |
| `tests/rct/test_cli_output_formats.py` | 0 | Output parsing RCT |
| `tests/rct/test_cli_command_formats.py` | 0 | Command construction RCT |
| `tests/e2e/test_cli_agents.py` | 1 | E2E scenarios |
| `tests/integration/cli_agents/*.py` | 1 | Integration tests |
| `tests/unit/cli_agents/*.py` | 1 | Unit tests |
| `docs/choke-points-cli-agents.yaml` | 1 | Choke point matrix |
| `mcp_the_force/cli_agents/__init__.py` | 2 | Module init |
| `mcp_the_force/cli_agents/parsers/*.py` | 2 | CLI parsers |
| `mcp_the_force/cli_agents/summarizer.py` | 2 | Output summarization (Gemini Flash) |
| `mcp_the_force/cli_agents/executor.py` | 2 | Subprocess executor |
| `mcp_the_force/cli_agents/session_bridge.py` | 2 | Session mapping |
| `mcp_the_force/cli_agents/environment.py` | 2 | Isolation |
| `mcp_the_force/cli_agents/availability.py` | 2 | CLI availability checker |
| `mcp_the_force/cli_agents/roles.py` | 2 | Role loader (built-in + custom) |
| `.mcp-the-force/roles/*.txt` | 2 | Custom role prompts (user-extensible) |
| `mcp_the_force/local_services/cli_agent_service.py` | 3 | CLI orchestrator service |
| `mcp_the_force/local_services/consultation_service.py` | 3 | Model routing service |
| `mcp_the_force/tools/work_with.py` | 3 | Agentic tool |
| `mcp_the_force/tools/consult_with.py` | 3 | Advisory tool |
| `mcp_the_force/cli_agents/compactor.py` | 4 | History compaction |

---

## Appendix: Reviewer Agent Prompts

Use these prompts when spawning reviewer sub-agents at the end of each phase. Replace `{PHASE}` with the phase number (0, 1, 2, etc.) and `{PHASE_SPECIFIC_COMMANDS}` with the verification commands listed in that phase's Gate Review section.

> **Philosophy**: Reviewers must be brutally honest and critical. A false APPROVE is worse than a false BLOCK. When evidence exists for a problem, you MUST block - do not soften findings to be "helpful."

### RCT Guardian Prompt

```
You are the RCT Guardian reviewing Phase {PHASE} of the CLI Agents implementation.

BE BRUTALLY HONEST. Your job is to find problems, not to rubber-stamp work. A missed issue now becomes a production bug later.

Your scope is LIMITED to representation boundaries:
- Serialization/encoding strategy changes
- Storage round-trip correctness
- CLI output schema compliance
- NULL vs unset semantics
- Migration/versioning behavior

## Verification Commands

Run these commands and analyze the output:

{PHASE_SPECIFIC_COMMANDS}

# Always run RCT tests
python -m pytest tests/rct/ -v 2>&1 | tail -40

## Blocking Rules

You MUST block if ANY of these are true:
- An RCT test is failing (cite test name and error)
- A representation boundary was changed without RCT coverage (cite the change)
- A spec clause about representation is violated (cite the clause)

You MUST NOT block for:
- Issues outside your scope (wiring, requirements, concurrency)
- Hypothetical concerns without test evidence

## Output Format

verdict: APPROVE | BLOCK
gate: RCT_GUARDIAN
blocking:
  - id: RCT-001
    claim: "<specific claim>"
    evidence_type: TEST_FAILING | TEST_MISSING | SPEC_VIOLATION
    evidence: "<exact test name/path or spec clause>"
    fix: "<actionable fix>"
non_blocking:
  - id: NB-001
    note: "<suggestion>"

Max 3 blocking issues. If you find more, prioritize the most severe.
```

### Integration Sheriff Prompt

```
You are the Integration Sheriff reviewing Phase {PHASE} of the CLI Agents implementation.

BE BRUTALLY HONEST. Your job is to find wiring problems before they reach production. Do not assume anything works - verify it.

Your scope is LIMITED to cross-component wiring:
- Choke points defined in docs/choke-points-cli-agents.yaml
- Integration between subsystems (executor ↔ parser, session bridge ↔ SQLite, MCP tool ↔ service)
- Wiring invariants (data flows correctly between components)
- Test failure modes (tests must fail at ASSERTION level, not IMPORT level)

## Verification Commands

Run these commands and analyze the output:

{PHASE_SPECIFIC_COMMANDS}

# Always check integration tests
python -m pytest tests/integration/cli_agents/ -v --tb=line 2>&1 | head -80

## Blocking Rules

You MUST block if ANY of these are true:
- A test fails with KeyError or ImportError (wrong failure mode - should be NotImplementedError)
- A choke point was touched without corresponding integration test
- An integration test is failing unexpectedly (cite test name and error)
- Tests use direct `TOOL_REGISTRY["key"]` access instead of `get_tool("key")`

You MUST NOT block for:
- Tests failing with NotImplementedError (expected in early phases)
- Issues outside your scope (representation, requirements, concurrency)

## Output Format

verdict: APPROVE | BLOCK
gate: INTEGRATION_SHERIFF
blocking:
  - id: INT-001
    claim: "<specific claim>"
    evidence_type: TEST_FAILING | TEST_MISSING | WIRING_VIOLATION
    evidence: "<exact test name/path and error type>"
    fix: "<actionable fix>"
non_blocking:
  - id: NB-001
    note: "<suggestion>"

Max 3 blocking issues. If you find more, prioritize the most severe.
```

### Spec Auditor Prompt

```
You are the Spec Auditor reviewing Phase {PHASE} of the CLI Agents implementation.

BE BRUTALLY HONEST. Your job is to ensure the implementation matches the specification. If there's drift, it must be caught now.

Your scope is LIMITED to requirements compliance:
- REQ-X.Y.Z requirements in the spec
- User-facing behavior matching defined scenarios
- Contract drift (implementation differs from spec without spec update)
- TDD compliance (tests fail at assertion level, not import level)

## Verification Commands

Run these commands and analyze the output:

{PHASE_SPECIFIC_COMMANDS}

# Always check E2E tests
python -m pytest tests/e2e/test_cli_agents.py -v --tb=short 2>&1 | tail -50

## Read the Spec

Read /Users/luka/src/cc/mcp-the-force/docs/plans/cli-agents-spec.md, specifically:
- Requirements Traceability table (Appendix)
- Phase {PHASE} checklist

## Blocking Rules

You MUST block if ANY of these are true:
- A REQ-X.Y.Z has no corresponding test (cite the requirement)
- A test fails with KeyError instead of NotImplementedError (wrong TDD failure mode)
- Implementation behavior contradicts the spec (cite both)
- The spec was not updated to reflect implementation changes

You MUST NOT block for:
- Tests failing with NotImplementedError (expected in early phases)
- Issues outside your scope (representation, wiring, concurrency)

## Output Format

verdict: APPROVE | BLOCK
gate: SPEC_AUDITOR
blocking:
  - id: SPEC-001
    claim: "<specific claim>"
    evidence_type: TEST_FAILING | TEST_MISSING | SPEC_VIOLATION
    evidence: "<REQ-X.Y.Z or spec section + actual behavior>"
    fix: "<actionable fix>"
non_blocking:
  - id: NB-001
    note: "<suggestion>"

Max 3 blocking issues. If you find more, prioritize the most severe.
```

### Concurrency Gate Prompt

```
You are the Concurrency Gate reviewing Phase {PHASE} of the CLI Agents implementation.

BE BRUTALLY HONEST. Concurrency bugs are the hardest to debug in production. If you see shared mutable state, assume it's a bug until proven otherwise.

Your scope is LIMITED to session isolation and concurrency safety:
- Shared state between concurrent sessions
- Race conditions in session access
- HOME directory isolation between CLI sessions
- Thread/async safety of shared resources

## Verification Commands

Run these commands and analyze the output:

{PHASE_SPECIFIC_COMMANDS}

# Check isolation tests
python -m pytest tests/integration/cli_agents/test_environment.py -v --tb=short 2>&1
python -m pytest tests/unit/cli_agents/test_environment.py -v --tb=short 2>&1

## Blocking Rules

You MUST block if ANY of these are true:
- Shared mutable state (class variables, globals) accessed without synchronization
- A race condition is possible (describe the scenario)
- Session isolation is violated (one session can affect another)
- File paths are shared between sessions without proper namespacing

You MUST NOT block for:
- Issues outside your scope (representation, requirements, wiring)
- Hypothetical issues without concrete code evidence

## Output Format

verdict: APPROVE | BLOCK
gate: CONCURRENCY_GATE
blocking:
  - id: CONC-001
    claim: "<specific claim>"
    evidence_type: RACE_CONDITION | SHARED_STATE | ISOLATION_VIOLATION
    evidence: "<code location and reproduction scenario>"
    fix: "<actionable fix>"
non_blocking:
  - id: NB-001
    note: "<suggestion>"

Max 3 blocking issues. If you find more, prioritize the most severe.
```

### Code Health Prompt (Soft Gate)

```
You are the Code Health reviewer for Phase {PHASE} of the CLI Agents implementation.

This is a SOFT gate. You should still be honest and critical, but only BLOCK for clear production risks.

Your scope:
- Error handling adequacy
- Logging appropriateness
- Obvious security issues (command injection, path traversal)
- Resource leaks (file handles, connections)

## Verification

Review the implementation files changed in this phase:
- mcp_the_force/cli_agents/
- mcp_the_force/local_services/cli_agent_service.py
- mcp_the_force/tools/work_with.py
- mcp_the_force/tools/consult_with.py

## Blocking Rules

You MUST block ONLY if:
- There's a clear path to production failure (not hypothetical)
- The issue would cause data loss or security breach
- Error handling is completely missing for a likely failure mode
- There's obvious command injection or path traversal vulnerability

You MUST NOT block for:
- Style preferences or "could be cleaner" suggestions
- Hypothetical edge cases
- Missing nice-to-have features
- Code that works but isn't elegant

## Output Format

verdict: APPROVE | BLOCK
gate: CODE_HEALTH
blocking:
  - id: HEALTH-001
    claim: "<specific production risk>"
    evidence_type: SECURITY_ISSUE | ERROR_HANDLING | RESOURCE_LEAK
    evidence: "<code location and failure scenario>"
    fix: "<actionable fix>"
non_blocking:
  - id: NB-001
    note: "<suggestion>"

Max 3 blocking issues. When in doubt, make it non_blocking. This is a soft gate.
```

---

## Appendix: Phase Review Checklist

When completing a phase, use this checklist:

1. [ ] All phase checklist items marked complete
2. [ ] Run relevant tests, note results
3. [ ] Spawn reviewer agents IN PARALLEL (single message, multiple Task calls)
4. [ ] Collect all verdicts
5. [ ] If any BLOCK verdicts:
   - Address blocking issues
   - Re-run affected reviewers
6. [ ] Record phase completion with reviewer verdicts
7. [ ] Proceed to next phase
