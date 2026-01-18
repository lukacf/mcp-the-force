# CLI Agents Architecture

> **Related**: [Specification](cli-agents-spec.md) | [Plan](~/.claude/plans/tidy-prancing-wreath.md) | [RCT Methodology](../rtc_methodology.md)

## Overview

CLI Agents adds agentic AI assistants (Claude Code, Gemini CLI, Codex CLI) as first-class tools in mcp-the-force. This document describes the architectural design and how it integrates with the existing system.

---

## System Context

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MCP Client                                      │
│                    (Claude Desktop, other MCP clients)                       │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │ MCP Protocol
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           mcp-the-force Server                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         FastMCP Integration                           │   │
│  │            (tools/integration.py → register_all_tools)                │   │
│  └──────────────────────────────┬───────────────────────────────────────┘   │
│                                 │                                            │
│  ┌──────────────────────────────▼───────────────────────────────────────┐   │
│  │                         Tool Executor                                 │   │
│  │                    (tools/executor.py)                                │   │
│  │   ┌─────────────────┐              ┌─────────────────────────────┐   │   │
│  │   │  Route params   │              │  Dispatch to:               │   │   │
│  │   │  via RouteType  │─────────────▶│  • LocalService (service_cls)│   │   │
│  │   │                 │              │  • MCPAdapter (adapter_class)│   │   │
│  │   └─────────────────┘              └──────────────┬──────────────┘   │   │
│  └───────────────────────────────────────────────────┼──────────────────┘   │
│                                                      │                       │
│     ┌────────────────────────────────────────────────┼──────────────────┐   │
│     │                                                ▼                   │   │
│     │  ┌─────────────────────┐    ┌─────────────────────────────────┐  │   │
│     │  │   CLI Agent Service │    │      AI Model Adapters          │  │   │
│     │  │   (LocalService)    │    │      (MCPAdapter)               │  │   │
│     │  │                     │    │                                 │  │   │
│     │  │  • work_with tool   │    │  • chat_with_gpt52 (internal)   │  │   │
│     │  │  • consult_with tool│───▶│  • chat_with_gemini3_pro        │  │   │
│     │  │                     │    │  • chat_with_grok41             │  │   │
│     │  │         │           │    │  • ... (all internal_only)      │  │   │
│     │  └─────────┼───────────┘    └─────────────────────────────────┘  │   │
│     │            │                                                      │   │
│     └────────────┼──────────────────────────────────────────────────────┘   │
│                  │                                                           │
│     ┌────────────▼──────────────────────────────────────────────────────┐   │
│     │                     CLI Subprocess Layer                           │   │
│     │                                                                    │   │
│     │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │   │
│     │  │ Claude Code  │  │ Gemini CLI   │  │  Codex CLI   │             │   │
│     │  │ (subprocess) │  │ (subprocess) │  │ (subprocess) │             │   │
│     │  └──────────────┘  └──────────────┘  └──────────────┘             │   │
│     │            │               │               │                       │   │
│     │            └───────────────┴───────────────┘                       │   │
│     │                            │                                       │   │
│     │                    Isolated HOME dirs                              │   │
│     │               (~/.mcp-the-force/cli_sessions/)                     │   │
│     └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Architectural Decision: LocalService Pattern (Validated)

> **Status**: Validated by Phase 0 RCT (2026-01-17). All CLI capabilities confirmed working. See [RCT Findings](cli-agents-rct-findings.md).

### Analysis: MCPAdapter vs LocalService

**MCPAdapter** is designed for:
- Direct API calls to AI providers (OpenAI, Google, xAI)
- Token management and context window handling
- Response streaming and structured output
- Standard request/response patterns

**CLI agents** require:
- Subprocess spawning and lifecycle management
- Environment isolation (HOME redirection, config generation)
- Output parsing from CLI-specific JSON/JSONL formats
- Session mapping to CLI-native session IDs
- Variable execution times (minutes, not seconds)

### Recommendation: LocalService Pattern

Based on the requirements mismatch, **LocalService is recommended**. However, this should be validated during Phase 0.

The codebase has two tool patterns:

| Pattern | `adapter_class` | `service_cls` | Use Case |
|---------|-----------------|---------------|----------|
| **MCPAdapter** | Set (e.g., `OpenAIAdapter`) | None | Direct AI API calls (chat_with_*) |
| **LocalService** | None | Set (e.g., `MyService`) | Orchestration, utilities, subprocess management |

If validated, CLI agents would use **LocalService**:

```python
@tool
class WorkWith(ToolSpec):
    model_name = "work_with"
    adapter_class = None          # ← NOT an MCPAdapter
    service_cls = CLIAgentService # ← LocalService handles execution
    timeout = 1800
```

**Rationale for LocalService**:
- CLI agents spawn external processes (claude, gemini, codex binaries)
- Need full control over environment, timeouts, output parsing
- Not calling AI provider APIs directly
- `consult_with` routes to existing tools via `executor.execute()`

**Phase 0 RCT validated** (2026-01-17):
- ✅ All CLIs run headless and produce parseable JSON/JSONL
- ✅ HOME isolation works correctly for all CLIs
- ✅ Session IDs exposed and resumable for all CLIs
- ✅ Project directory access via `--add-dir` / `--include-directories`

**LocalService interface** (simple):
```python
class CLIAgentService:
    async def execute(self, **kwargs) -> str:
        # All Route.adapter() params arrive here as kwargs
        # Return string (or dict, auto-converted to JSON)
```

Other LocalService examples in codebase: `ListSessions`, `DescribeSession`, `CountTokens`

---

## Component Architecture

```
mcp_the_force/
├── tools/
│   ├── work_with.py          # @tool decorated ToolSpec
│   └── consult_with.py       # @tool decorated ToolSpec
│
├── local_services/
│   ├── cli_agent_service.py  # CLIAgentService.execute()
│   └── consultation_service.py # ConsultationService.execute()
│
├── cli_plugins/              # NEW: CLI-specific plugins
│   ├── __init__.py
│   ├── base.py               # CLIPlugin protocol
│   ├── registry.py           # get_cli_plugin() registry
│   ├── claude.py             # Claude Code CLI plugin
│   ├── gemini.py             # Gemini CLI plugin
│   └── codex.py              # Codex CLI plugin
│
└── cli_agents/               # NEW MODULE
    ├── __init__.py
    ├── model_cli_resolver.py # Model name → CLI name resolution
    ├── executor.py           # CLIExecutor - subprocess management
    ├── session_bridge.py     # CLI session ID mapping
    ├── environment.py        # HOME isolation, config generation
    ├── compactor.py          # History summarization for handoffs
    ├── summarizer.py         # Output summarization
    ├── parsers/
    │   ├── base.py           # BaseParser, <SUMMARY> extraction
    │   ├── claude.py         # Claude JSON parsing
    │   ├── gemini.py         # Gemini JSON parsing
    │   └── codex.py          # Codex JSONL parsing
    └── roles/
        ├── default.txt       # General assistant prompt
        ├── planner.txt       # Design/architecture prompt
        └── codereviewer.txt  # Code review prompt
```

---

## Model → CLI Resolution

### Key Decision: Users Specify Model Names

Users call `work_with(agent="gpt-5.2")` with **model names**, not CLI names. The system resolves model names to CLI names via the `cli` attribute on adapter blueprints.

```
User input:           work_with(agent="gpt-5.2")
                              ↓
Model resolution:     resolve_model_to_cli("gpt-5.2") → "codex"
                              ↓
CLI plugin:           get_cli_plugin("codex") → CodexPlugin
                              ↓
Command build:        plugin.build_new_session_args(task, ...)
```

### Why Model Names?

1. **Unified vocabulary**: Same model names work across `work_with(agent=)` and `consult_with(model=)`
2. **Future-proof**: New models automatically get CLI routing if their blueprint has `cli` attribute
3. **User familiarity**: Users already know model names from `chat_with_*` tools

### Integration with Existing Systems

**This is critical**: CLI agents don't create a parallel universe. They integrate deeply with the existing descriptor-based architecture:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Existing Adapter Registry                            │
│                                                                         │
│   OpenAI Blueprints          Google Blueprints        Anthropic        │
│   ┌──────────────┐          ┌──────────────┐        ┌──────────────┐   │
│   │ gpt-5.2      │          │ gemini-3-pro │        │ claude-4.5   │   │
│   │ ─────────────│          │ ─────────────│        │ ─────────────│   │
│   │ provider: oai│          │ provider: goo│        │ provider: ant│   │
│   │ cli: "codex" │◀─NEW     │ cli: "gemini"│◀─NEW   │ cli: "claude"│◀─ │
│   │ ...          │          │ ...          │        │ ...          │   │
│   └──────────────┘          └──────────────┘        └──────────────┘   │
│           │                        │                        │           │
│           └────────────────────────┼────────────────────────┘           │
│                                    │                                    │
│                           TOOL_REGISTRY                                 │
│                    (autogen creates chat_with_*)                        │
└────────────────────────────────────┼────────────────────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
              ▼                      ▼                      ▼
     ┌─────────────┐        ┌─────────────┐        ┌─────────────┐
     │ chat_with_  │        │  work_with  │        │consult_with │
     │   gpt52     │        │             │        │             │
     │ (internal)  │        │ Uses same   │        │ Routes to   │
     │             │        │ model names │        │ internal    │
     │ Used by     │◀───────│ Resolves to │        │ chat_with_* │
     │ consult_with│        │ CLI via     │        │             │
     └─────────────┘        │ blueprint   │        └─────────────┘
                            │ .cli attr   │
                            └─────────────┘
```

**Reuse of existing components**:

| Existing Component | How CLI Agents Reuse It |
|-------------------|------------------------|
| Adapter Registry | `resolve_model_to_cli()` reads `blueprint.cli` attribute |
| TOOL_REGISTRY | `consult_with` routes to existing `chat_with_*` tools |
| RouteDescriptors | `work_with` uses same `Route.adapter()` param routing |
| autogen.py | Could auto-generate CLI capabilities from blueprints |
| UnifiedSessionCache | Stores turns for cross-tool handoffs |
| executor.py | Dispatches to CLIAgentService via `service_cls` pattern |

**Blueprint extension** (the only new attribute):

```python
# In adapter blueprints (e.g., openai/definitions.py)
class GPT52Blueprint(ModelBlueprint):
    model_id = "gpt-5.2"
    provider = "openai"
    # ... existing fields ...
    cli = "codex"  # ← NEW: Maps to Codex CLI

class O3DeepResearchBlueprint(ModelBlueprint):
    model_id = "o3-deep-research"
    provider = "openai"
    # ... existing fields ...
    cli = None  # ← API-only, no CLI support
```

### Resolution Flow

```python
# In model_cli_resolver.py
def resolve_model_to_cli(model_name: str) -> str:
    """
    Resolve model name to CLI name via adapter registry.

    Examples:
        "gpt-5.2" → "codex"
        "claude-sonnet-4-5" → "claude"
        "gemini-3-flash-preview" → "gemini"

    Raises:
        ModelNotFoundError: Model not in registry
        NoCLIAvailableError: Model exists but has no CLI (API-only)
    """
    metadata = get_adapter_metadata(model_name)
    if not hasattr(metadata.blueprint, 'cli'):
        raise NoCLIAvailableError(model_name)
    return metadata.blueprint.cli
```

### Model Support Matrix (from RCT)

| Model | CLI | Status |
|-------|-----|--------|
| claude-sonnet-4-5 | claude | ✅ |
| claude-opus-4-5-20251101 | claude | ✅ |
| claude-3-opus | claude | ❌ (deprecated) |
| gpt-5.2 | codex | ✅ |
| gpt-5.2-pro | codex | ✅ |
| gpt-4.1 | codex | ✅ |
| gpt-5.1-codex-max | codex | ✅ |
| o3 | codex | ✅ |
| o4-mini | codex | ✅ |
| gemini-3-pro-preview | gemini | ✅ |
| gemini-3-flash-preview | gemini | ✅ |
| o3-deep-research | - | ❌ (API-only) |

### CLI Plugin Architecture

Each CLI has a plugin that knows how to:
- Build commands for new sessions
- Build commands for resuming sessions
- Parse output specific to that CLI

**Registration Pattern**: CLI plugins use the `@cli_plugin` decorator, following the same pattern as `@tool` for tool registration. This ensures consistency with the existing codebase architecture.

```python
# In cli_plugins/base.py
class CLIPlugin(Protocol):
    """Protocol that CLI plugins must implement."""
    name: str  # "claude", "gemini", "codex"

    @property
    def executable(self) -> str:
        """CLI executable name (e.g., 'claude', 'gemini', 'codex')."""
        ...

    def build_new_session_args(self, task: str, context_dirs: List[str], ...) -> List[str]:
        """Build command args for new session."""
        ...

    def build_resume_args(self, session_id: str, task: str, ...) -> List[str]:
        """Build command args for resuming session."""
        ...
```

```python
# In cli_plugins/registry.py
CLI_PLUGIN_REGISTRY: Dict[str, CLIPlugin] = {}

def cli_plugin(name: str) -> Callable[[Type[T]], Type[T]]:
    """
    Decorator that registers a CLI plugin.

    Usage:
        @cli_plugin("codex")
        class CodexPlugin:
            ...

    Similar to @tool decorator for tools.
    """
    def decorator(cls: Type[T]) -> Type[T]:
        instance = cls()
        CLI_PLUGIN_REGISTRY[name] = instance
        return cls
    return decorator

def get_cli_plugin(cli_name: str) -> Optional[CLIPlugin]:
    """Get CLI plugin by name."""
    return CLI_PLUGIN_REGISTRY.get(cli_name)

def list_cli_plugins() -> List[str]:
    """List all registered CLI plugin names."""
    return list(CLI_PLUGIN_REGISTRY.keys())
```

```python
# In cli_plugins/codex.py
@cli_plugin("codex")
class CodexPlugin:
    name = "codex"
    executable = "codex"

    def build_new_session_args(self, task, context_dirs):
        return ["exec", "--json", task]

    def build_resume_args(self, session_id, task):
        # Codex uses subcommand, NOT flag!
        return ["exec", "resume", session_id, "--json"]
```

**Critical difference in resume patterns**:
- Claude/Gemini: `--resume <session_id>` flag
- Codex: `exec resume <thread_id>` subcommand (NOT a flag!)

**Validation**: At startup, the system validates:
1. All model blueprints with `cli` attribute point to registered plugins
2. All registered plugins have required methods
3. CLI executables exist on PATH (warning if missing)

---

## Data Flow

### work_with Execution Flow

```
User: work_with(agent="claude-sonnet-4-5", task="fix bug", session_id="debug-123")
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. Integration Layer (tools/integration.py)                              │
│    • Extract parameters from MCP call                                    │
│    • Extract ctx (FastMCP Context) for progress reporting                │
│    • Call executor.execute(metadata, ctx=ctx, **params)                  │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. Tool Executor (tools/executor.py)                                     │
│    • Route parameters via RouteDescriptors                               │
│    • All Route.adapter() params → routed["adapter"] dict                 │
│    • Detect service_cls → dispatch to LocalService                       │
│    • service = CLIAgentService()                                         │
│    • result = await service.execute(**routed["adapter"])                 │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. CLI Agent Service (local_services/cli_agent_service.py)               │
│    │                                                                     │
│    ├─▶ resolve_model_to_cli("claude-sonnet-4-5") → "claude"             │
│    │   • Looks up model in adapter registry                              │
│    │   • Returns blueprint.cli attribute                                 │
│    │   • Raises ModelNotFoundError or NoCLIAvailableError if invalid     │
│    │                                                                     │
│    ├─▶ get_cli_plugin("claude") → ClaudePlugin                          │
│    │   • Gets CLI-specific plugin from cli_plugins registry              │
│    │                                                                     │
│    ├─▶ SessionBridge.get_cli_session_id(project, session_id, "claude")  │
│    │   • Returns existing CLI session ID if resuming                     │
│    │                                                                     │
│    ├─▶ CLISessionEnvironment.prepare(session_id, "claude")              │
│    │   • Creates isolated HOME: ~/.mcp-the-force/cli_sessions/debug-123/│
│    │   • Generates minimal CLI config (no MCPs, safe defaults)           │
│    │                                                                     │
│    ├─▶ plugin.build_new_session_args(task, context_dirs, role)          │
│    │   OR plugin.build_resume_args(cli_session_id, task)                │
│    │   • Claude: ["--print", "-p", "task", "--output-format", "json"]    │
│    │   • Gemini: ["--output-format", "json", "task"]                     │
│    │   • Codex: ["exec", "--json", "task"] or ["exec", "resume", "<id>"] │
│    │   • Resume: --resume <id> (Claude/Gemini) vs subcommand (Codex)     │
│    │                                                                     │
│    ├─▶ CLIExecutor.execute([plugin.executable] + args, env, timeout)    │
│    │   • asyncio.create_subprocess_exec()                                │
│    │   • Captures stdout with 10MB limit                                 │
│    │   • Kills on timeout (30 min default)                               │
│    │                                                                     │
│    ├─▶ parser.parse(stdout) → ParsedCLIResponse                         │
│    │   • Parser selected based on cli_name                               │
│    │   • Extracts session_id/thread_id from output                       │
│    │   • Extracts content (result/message fields)                        │
│    │                                                                     │
│    ├─▶ Summarizer.summarize(parsed.content)                             │
│    │   • Always summarizes via gemini-3-flash-preview                    │
│    │   • Preserves key information (decisions, code, paths)              │
│    │                                                                     │
│    ├─▶ SessionBridge.store_cli_session_id(project, session_id, cli, id) │
│    │   • Maps global session_id to CLI-native session for resume         │
│    │                                                                     │
│    └─▶ Return summarized content                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### consult_with Execution Flow

```
User: consult_with(model="gpt52", question="review this?", session_id="review-456")
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 1-2. Same as work_with (Integration → Executor → LocalService)          │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. Consultation Service (local_services/consultation_service.py)         │
│    │                                                                     │
│    ├─▶ TOOL_REGISTRY.get(f"chat_with_{model}")                          │
│    │   • Resolves "gpt52" → chat_with_gpt52 tool metadata                │
│    │   • Falls back to model_name matching in registry                   │
│    │                                                                     │
│    ├─▶ executor.execute(metadata, instructions=question, ...)           │
│    │   • Calls existing chat_with_* tool internally                      │
│    │   • Passes through session_id, context, output_format               │
│    │                                                                     │
│    └─▶ Return response content                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

### Cross-Tool Session Flow

```
Turn 1: consult_with(model="gpt-5.2", question="design auth?", session_id="auth-789")
        └─▶ Stored in UnifiedSessionCache with tool="chat_with_gpt52"

Turn 2: work_with(agent="claude-sonnet-4-5", task="implement the design", session_id="auth-789")
        │
        ├─▶ resolve_model_to_cli("claude-sonnet-4-5") → "claude"
        │
        ├─▶ SessionBridge: No Claude session for "auth-789" (first time)
        │
        ├─▶ UnifiedSessionCache: Found history from chat_with_gpt52
        │   └─▶ History: [{role: "user", content: "design auth?"},
        │                 {role: "assistant", content: "Here's the design..."}]
        │
        ├─▶ Compactor.compact_for_cli(history, "claude", max_tokens=8000)
        │   └─▶ If fits: Format as context block
        │   └─▶ If exceeds: Summarize via gemini-3-flash-preview
        │
        ├─▶ Inject compacted context as task prefix:
        │   "Previous conversation context:\n{compacted}\n\nTask: implement the design"
        │
        └─▶ Execute Claude CLI (new session, context injected)

Turn 3: work_with(agent="claude-sonnet-4-5", task="add tests", session_id="auth-789")
        │
        ├─▶ resolve_model_to_cli("claude-sonnet-4-5") → "claude"
        │
        ├─▶ SessionBridge: Found Claude session "abc123" for "auth-789"
        │
        └─▶ Execute with --resume abc123 (native CLI resume)
```

---

## Interface Definitions

### CLIAgentService

```python
class CLIAgentService:
    """Spawns and manages CLI agent subprocesses."""

    async def execute(
        self,
        agent: str,           # MODEL NAME (e.g., "gpt-5.2", "claude-sonnet-4-5")
        task: str,            # The prompt/task for the agent
        role: str,            # "default" | "planner" | "codereviewer"
        session_id: str,      # Global session identifier
        context: List[str],   # Additional file paths
        ctx: Optional[Context] = None,  # FastMCP context for progress
        **kwargs,
    ) -> str:
        """
        Execute CLI agent task.

        The `agent` parameter accepts MODEL NAMES (same as chat_with_* tools),
        NOT CLI names. The service resolves model → CLI internally:

            agent="gpt-5.2"           → codex CLI
            agent="claude-sonnet-4-5" → claude CLI
            agent="gemini-3-flash"    → gemini CLI

        This uses the same model registry as all other tools, ensuring
        consistent vocabulary across work_with() and consult_with().

        Returns:
            Summarized response content (always via gemini-3-flash-preview)

        Raises:
            ModelNotFoundError: If model name not in registry
            NoCLIAvailableError: If model is API-only (no CLI support)
        """
```

### ConsultationService

```python
class ConsultationService:
    """Routes to existing AI model tools via TOOL_REGISTRY."""

    async def execute(
        self,
        model: str,           # Model identifier (e.g., "gpt-5.2", "gemini-3-pro-preview")
        question: str,        # The query for the model
        session_id: str,      # Global session identifier
        context: List[str],   # File paths for context
        output_format: str,   # Desired response format
        ctx: Optional[Context] = None,
        **kwargs,
    ) -> str:
        """
        Execute advisory query via existing model tool.

        Uses the SAME model names as work_with(agent=). Internally routes
        to the corresponding chat_with_* tool from TOOL_REGISTRY:

            model="gpt-5.2" → executor.execute(chat_with_gpt52, ...)

        This ensures uniform vocabulary: users don't need to know
        whether they're calling a CLI or API - same model names work.
        """
```

### CLIExecutor

```python
class CLIExecutor:
    """Manages CLI subprocess execution."""

    async def execute(
        self,
        command: List[str],
        env: Dict[str, str],
        timeout: int = 1800,  # 30 min default
        stream_limit: int = 10 * 1024 * 1024,  # 10 MB
    ) -> CLIResult:
        """
        Execute CLI command as subprocess.

        Returns:
            CLIResult(stdout, stderr, return_code, timed_out)
        """
```

### SessionBridge

```python
class SessionBridge:
    """Maps global session_id to CLI-native session IDs."""

    def get_cli_session_id(
        self,
        project: str,
        session_id: str,
        cli_name: str,
    ) -> Optional[str]:
        """Get CLI-native session ID if exists."""

    def store_cli_session_id(
        self,
        project: str,
        session_id: str,
        cli_name: str,
        cli_session_id: str,
    ) -> None:
        """Store mapping after CLI execution."""
```

### BaseParser

```python
class BaseParser(Protocol):
    """Protocol for CLI output parsers."""

    def parse(self, stdout: str) -> ParsedCLIResponse:
        """
        Parse CLI JSON output.

        Returns:
            ParsedCLIResponse(
                content: str,        # Main response content
                session_id: str,     # CLI-native session ID (see field names below)
                summary: Optional[str],  # Extracted <SUMMARY> if present
                metadata: Dict,      # Additional fields
            )

        Session ID field names (from RCT findings):
        - Claude: `session_id` (in init event, top-level)
        - Gemini: `session_id` (in response JSON, top-level)
        - Codex: `thread_id` (in thread.started event) ← Note: different field name!
        """

    def extract_summary(self, content: str, max_chars: int = 20000) -> str:
        """Extract <SUMMARY> block or truncate content."""
```

---

## Session Architecture

### Key Change: Global session_id

**Before** (tool-scoped):
```
Key: (project, tool, session_id)
Example: ("myproject", "chat_with_gpt52", "debug-123")
```

**After** (global):
```
Key: (project, session_id)
Example: ("myproject", "debug-123")
Tool stored in: turn metadata
```

### Storage Schema

```sql
-- Existing: unified sessions (conversation history)
CREATE TABLE sessions (
    project TEXT NOT NULL,
    session_id TEXT NOT NULL,
    -- tool removed from PK
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    PRIMARY KEY (project, session_id)
);

CREATE TABLE conversation_turns (
    id INTEGER PRIMARY KEY,
    project TEXT NOT NULL,
    session_id TEXT NOT NULL,
    tool TEXT NOT NULL,        -- Which tool produced this turn
    role TEXT NOT NULL,        -- "user" | "assistant"
    content TEXT NOT NULL,
    metadata JSON,
    created_at TIMESTAMP,
    FOREIGN KEY (project, session_id) REFERENCES sessions
);

-- New: CLI session mapping
CREATE TABLE cli_session_mapping (
    project TEXT NOT NULL,
    session_id TEXT NOT NULL,  -- Global session_id
    cli_name TEXT NOT NULL,    -- "claude" | "gemini" | "codex"
    cli_session_id TEXT NOT NULL,  -- CLI-native session ID
    created_at TIMESTAMP,
    PRIMARY KEY (project, session_id, cli_name)
);
```

---

## Environment Isolation

### Directory Structure

```
~/.mcp-the-force/
└── cli_sessions/
    └── {session_id}/
        ├── claude/
        │   ├── .claude/           # Claude-specific config
        │   │   └── settings.json  # Minimal, no MCPs
        │   └── .clauderc          # Empty or minimal
        ├── gemini/
        │   └── .gemini/
        │       └── settings.yaml
        └── codex/
            └── .codex/
                └── config.json
```

### Isolation Mechanism

```python
# environment.py
class CLISessionEnvironment:
    def prepare(self, session_id: str, cli_name: str) -> Dict[str, str]:
        """
        Prepare isolated environment for CLI execution.

        Returns:
            Environment dict with HOME redirected
        """
        session_dir = self.base_dir / session_id / cli_name
        session_dir.mkdir(parents=True, exist_ok=True)

        # Create minimal config (no MCPs, safe defaults)
        self._write_minimal_config(session_dir, cli_name)

        # Return environment with redirected HOME
        env = os.environ.copy()
        env["HOME"] = str(session_dir)
        return env
```

---

## Tool Visibility

### Key Change: chat_with_* Become Internal-Only

**Before CLI Agents**: MCP clients saw 12+ `chat_with_*` tools (one per model).

**After CLI Agents**: MCP clients see only 2 AI tools: `work_with` and `consult_with`.

**Why?**
1. **Simpler API surface**: Users don't need to know which model to use
2. **Unified vocabulary**: Same model names for agentic (`work_with`) and advisory (`consult_with`)
3. **Future flexibility**: Internal routing can change without breaking MCP clients

### internal_only Flag Implementation

```python
# In ToolSpec base class
class ToolSpec:
    internal_only: bool = False  # If True, not exposed via MCP

# In autogen.py (for chat_with_* tools generated from blueprints)
tool_class.internal_only = True  # ← All autogen'd tools become internal

# In integration.py
def register_all_tools(mcp: FastMCP) -> None:
    for tool_id, metadata in TOOL_REGISTRY.items():
        if getattr(metadata.spec_class, 'internal_only', False):
            continue  # Skip - don't register with MCP
        # ... register normally
```

### Result

```
MCP-visible tools:           Internal-only tools (still in TOOL_REGISTRY):
├── work_with                ├── chat_with_gpt52         ← Used by consult_with
├── consult_with             ├── chat_with_gpt52_pro     ← Used by consult_with
├── group_think              ├── chat_with_gemini3_pro_preview
├── list_sessions            ├── chat_with_gemini3_flash_preview
├── describe_session         ├── chat_with_grok41
├── search_project_history   ├── chat_with_claude45_opus
└── count_project_tokens     └── ... (all chat_with_* tools)
```

**Important**: `chat_with_*` tools MUST remain in TOOL_REGISTRY because `consult_with` uses them internally via `executor.execute()`.

---

## CLI-Specific Quirks (from RCT)

These behaviors were discovered during Phase 0 RCT validation:

### Codex CLI
- **Requires git repository**: By default, Codex won't run outside a git repo. Use `--skip-git-repo-check` for non-git directories.
- **JSONL output**: Output is JSON Lines (one JSON object per line), not a single JSON object.
- **Resume is a subcommand**: Use `codex exec resume <thread_id>`, not a flag like other CLIs.
- **Session field name**: Uses `thread_id` instead of `session_id`.

### Gemini CLI
- **Project-scoped sessions**: Sessions are tied to the project directory, not global. This aligns with our design.
- **Multiple resume options**: Supports `--resume latest`, `--resume <index>`, or `--resume <uuid>`.
- **Directory flag name**: Uses `--include-directories` (not `--add-dir`).

### Claude Code CLI
- **Workspace trust**: May prompt for workspace trust in interactive mode. Use `--print` mode to bypass.
- **Two flags for headless**: Requires both `--print` and `--output-format json` for headless JSON output.

---

## Error Handling

### CLI Execution Errors

| Error | Detection | Recovery |
|-------|-----------|----------|
| Timeout | asyncio.timeout() exceeded | Kill process, return partial output + error |
| Crash | Non-zero return code | Parse stderr, return error message |
| Parse failure | JSON decode error | Return raw stdout (truncated) |
| CLI not installed | FileNotFoundError | Clear error: "CLI not found: claude" |

### Session Errors

| Error | Detection | Recovery |
|-------|-----------|----------|
| Resume fails | CLI returns error on --resume | Start fresh session, inject history |
| Session not found | SessionBridge returns None | Start fresh session |
| Compaction fails | API error during summarization | Use raw truncated history |

---

## Extension Points

### Adding a New CLI Agent

1. **Create parser** in `cli_agents/parsers/{name}.py`:
   ```python
   class NewCLIParser(BaseParser):
       def parse(self, stdout: str) -> ParsedCLIResponse: ...
   ```

2. **Add to CommandBuilder** in `cli_agents/environment.py`:
   ```python
   def _build_newcli_command(self, task, role, resume_id, context): ...
   ```

3. **Add to capabilities matrix** in spec (Phase 0 RCT)

4. **Add to CLIAgentService** dispatcher

### Adding a New Role

1. **Create prompt** in `cli_agents/roles/{role}.txt`
2. **Register** in CLIAgentService role mapping
3. **Document** in tool description

---

## Testing Strategy

### Unit Tests (cli_agents module)
- Parser edge cases (malformed JSON, missing fields)
- Environment isolation (correct paths, config generation)
- Session bridge CRUD operations
- Compactor logic (fits/exceeds threshold)

### Integration Tests
- SessionBridge ↔ SQLite round-trip
- CLIExecutor ↔ subprocess ↔ Parser pipeline
- Cross-tool session continuity

### E2E Tests (with mock CLI scripts)
- Full work_with flow with Claude
- Resume same CLI session
- Cross-CLI handoff (consult_with → work_with)
- consult_with multi-turn via TOOL_REGISTRY

---

## References

**Architecture**:
- [Tool Executor](../../mcp_the_force/tools/executor.py) - dispatch to LocalService or MCPAdapter
- [Route Descriptors](../../mcp_the_force/tools/descriptors.py) - parameter routing system
- [Integration Layer](../../mcp_the_force/tools/integration.py) - FastMCP registration
- [Tool Base](../../mcp_the_force/tools/base.py) - ToolSpec base class

**LocalService Examples**:
- [ListSessions](../../mcp_the_force/tools/list_sessions.py) - simple utility service
- [DescribeSession](../../mcp_the_force/tools/describe_session.py) - service calling other tools
- [CountTokens](../../mcp_the_force/tools/count_tokens.py) - service with file processing

**External Documentation**:
- [Claude Code Headless](https://code.claude.com/docs/en/headless)
- [Codex CLI Reference](https://developers.openai.com/codex/cli/reference/)
- [Gemini CLI Sessions](https://geminicli.com/docs/cli/session-management/)
