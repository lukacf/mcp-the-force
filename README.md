# The Force MCP Server

![The Force MCP Server](docs/the-force.png)

> Every AI assistant needs an AI assistant.

The Force is a Model Context Protocol (MCP) server that unifies the world's most advanced AI models in a single interface. It intelligently manages context to overcome token limits and automatically builds a searchable knowledge base of your project's evolution. Works seamlessly with any MCP-compatible client, like Claude Code.

## Key Features

- **Unified Multi-Model Access**: Work with premier models from OpenAI, Google, Anthropic, and xAI through one consistent set of tools. Leverage the best model for every task without switching contexts.
- **Infinite Context**: Provide entire codebases as context, regardless of size. The Force intelligently includes critical files directly in the prompt and makes the rest available via high-performance vector search, effectively breaking through model context window limitations. It intelligently handles context updates when files change.
- **Self-Building Project History**: Automatically captures and indexes every AI conversation and git commit. This creates a searchable, long-term history of your project's design decisions, debates, and evolution.
- **Multi-Model Collaboration (GroupThink)**: Orchestrate GPT‑5, Gemini 3 Pro/Flash Preview, Claude, Grok, and others to co-create multi-turn solutions with shared context, automatic summaries, and validation passes.

## Quick Start

### 1. Install

First, ensure you have `uv` installed (a fast Python package manager):

```bash
# On macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or with Homebrew
brew install uv
```

Then, for Claude Code users, install The Force with a single command:

```bash
claude mcp add the-force -- \
  uvx --from git+https://github.com/lukacf/mcp-the-force \
  mcp-the-force
```

**Note**: `uvx` is included with `uv` and runs Python tools without installing them globally. The installation uses our **stable main branch**, ensuring you always get the latest tested release.

### 2. Configure

**Recommended approach**: Pass API keys directly as environment variables using the JSON format:

```bash
claude mcp add-json the-force '{
  "command": "uvx",
  "args": ["--from", "git+https://github.com/lukacf/mcp-the-force", "mcp-the-force"],
  "env": {
    "OPENAI_API_KEY": "sk-your-openai-key-here",
    "GEMINI_API_KEY": "your-gemini-api-key-here",
    "XAI_API_KEY": "xai-your-xai-key-here",
    "ANTHROPIC_API_KEY": "sk-ant-your-anthropic-key-here"
  }
}'
```

**For Google Vertex AI models**: You need both API authentication and project configuration:
1. **Authenticate with Google Cloud** for Vertex AI Gemini models:
   ```bash
   gcloud auth application-default login
   ```
2. **Add Vertex AI project and region to your configuration:**
   ```bash
   claude mcp add-json the-force '{
     "command": "uvx",
     "args": ["--from", "git+https://github.com/lukacf/mcp-the-force", "mcp-the-force"],
     "env": {
       "OPENAI_API_KEY": "sk-your-openai-key-here",
       "VERTEX_PROJECT": "your-gcp-project-with-vertex-service-enabled",
       "VERTEX_LOCATION": "us-central1"
     }
   }'
   ```
   - `VERTEX_PROJECT`: Your Google Cloud project ID with Vertex AI enabled
   - `VERTEX_LOCATION`: GCP region (e.g., `us-central1`, `europe-west1`)

**Alternative: Configuration files**
On the first run, the server will create project-local configuration files in `./.mcp-the-force/`. You can edit `./.mcp-the-force/secrets.yaml`:

```yaml
providers:
  openai:
    api_key: "sk-..."           # For OpenAI models
  gemini:
    api_key: "your-key..."      # For Gemini models (alternative to Vertex)
  xai:
    api_key: "xai-..."          # For Grok models
  anthropic:
    api_key: "sk-ant-..."       # For Claude models
  vertex:
    project: "your-project"     # For Vertex AI Gemini models
    location: "us-central1"
```

**Important**: Add `.mcp-the-force/` to your `.gitignore` file to prevent committing secrets.

**Note for Existing Users**: If you have previously used mcp-the-force with global configuration in `~/.config/mcp-the-force/`, you'll need to:
- Copy your `secrets.yaml` to each project's `./.mcp-the-force/` directory
- If you want to preserve conversation history, also copy `sessions.sqlite3` from the global config directory

**For local/development setups**: If you run the MCP server from a different directory than your target project (e.g., using `uv run --directory /path/to/mcp-the-force`), you must set `MCP_PROJECT_DIR` to tell the server which project you're working on:

```json
{
  "command": "uv",
  "args": ["run", "--directory", "/path/to/mcp-the-force", "mcp-the-force"],
  "env": {
    "MCP_PROJECT_DIR": "/path/to/your/actual/project",
    "OPENAI_API_KEY": "sk-..."
  }
}
```

### 3. Run

The server is now ready. Claude Code will start it automatically. To run it manually for development:

```bash
uv run -- mcp-the-force
```

### 4. CLI Agents (for `work_with`)

The `work_with` tool spawns CLI agents that can read files, run commands, and take autonomous action. To use it, install at least one of these CLI tools:

**Claude Code** (recommended):
```bash
npm install -g @anthropic/claude-code
```

**Gemini CLI**:
```bash
npm install -g @google/gemini-cli
```

**Codex CLI** (OpenAI):
```bash
npm install -g @openai/codex
```

The Force automatically detects which CLIs are available and routes `work_with` requests accordingly. If no CLI agents are installed, `work_with` will return an error—use `consult_with` instead for API-only access.

**Note**: The Force includes an idle timeout (10 minutes by default) that automatically terminates hung CLI processes. This works around [known Codex CLI hanging issues](https://github.com/openai/codex/issues/5773). If a task is killed due to idle timeout, the partial output is still returned.

## Usage Examples

Here's how you would instruct an assistant like Claude to use The Force:

### 1. Analyze and fix code (agentic):

> "Do we have any circular dependencies? Use The Force Claude!"

The assistant would call:
```
work_with(
    agent="claude-sonnet-4-5",
    task="Analyze the dependency graph and identify circular dependencies",
    session_id="dep-analysis"
)
```

*The `work_with` tool spawns a CLI agent that can read files, run commands, and take autonomous action.*

### 2. Get a quick opinion (advisory):

> "Ask GPT-5.2 Pro what they think about our authentication approach."

The assistant would call:
```
consult_with(
    model="gpt-5.2-pro",
    question="What are the pros and cons of JWT vs session tokens for our use case?",
    output_format="markdown",
    session_id="auth-design"
)
```

*The `consult_with` tool provides quick API access for opinions without file access.*

### 3. Search your project's entire history:

> "Before I start, what were the key decisions made when we first implemented JWT authentication? Search the project's history."

The assistant would call:
```
search_project_history(
    query="JWT implementation decisions; authentication architecture"
)
```

*This searches a vector database of all past conversations and git commits.*

## Available Tools

The Force provides two primary tools for AI collaboration:

### Primary Tools

| Tool | Purpose | How It Works |
|------|---------|--------------|
| **`work_with`** | Agentic tasks | Spawns CLI agents (Claude Code, Gemini CLI, Codex CLI) that can read files, run commands, and take action |
| **`consult_with`** | Quick opinions | Routes to API models for fast analysis without file access |

**When to use which:**
- Use `work_with` when you need the AI to explore code, make changes, or take autonomous action
- Use `consult_with` for quick questions, analysis, or second opinions

### Supported Models

Use these model names with `work_with` (agent parameter) or `consult_with` (model parameter):

**OpenAI:**
- `gpt-5.2-pro`: Flagship model - maximum accuracy for difficult problems (400k context)
- `gpt-5.2`: Advanced reasoning for coding, math, planning (272k context)
- `gpt-5.1-codex-max`: Elite coding model with xhigh reasoning (272k context)
- `gpt-4.1`: Fast long-context processing (1M) with web search

**Google:**
- `gemini-3-pro-preview`: Deep multimodal analysis with 1M context
- `gemini-3-flash-preview`: Fast summarization and quick analysis with 1M context

**Anthropic:**
- `claude-opus-4-5`: Premium long-form reasoning with extended thinking (200k context)
- `claude-sonnet-4-5`: Fast long-context processing with extended thinking (1M context)

**xAI:**
- `grok-4.1`: Advanced assistant with ~2M context and live search

**Research (special async tools):**
- `research_with_o3_deep_research`: Ultra-deep research with extensive web search (10-60 min)
- `research_with_o4_mini_deep_research`: Fast research with web search (2-10 min)

**Local Models (if Ollama is installed):**
The Force automatically detects and provides access to any Ollama models you have installed locally.

> **Note**: The individual `chat_with_*` tools are internal-only. Use `consult_with` to access them.

### Utility Tools
- `search_project_history`: Search past conversations and git commits
- `list_sessions`: List recent AI conversation sessions
- `describe_session`: Get an AI-powered summary of a past session
- `count_project_tokens`: Analyze token usage for specified files/directories
- `search_mcp_debug_logs`: Query debug logs with LogsQL (developer mode only)
- `start_job`, `poll_job`, `cancel_job`: Run any existing tool asynchronously via the built-in job queue

### Asynchronous Tool Execution
- **Why**: Long-running operations often exceed the 60s MCP tool timeout. The async job queue lets you offload work and check back later.
- **How it works**: `start_job` enqueues a tool call into `jobs.sqlite3`; a background worker (started with the server) processes jobs and persists results.
- **Usage pattern**:
  1) Call `start_job` with the target tool name and arguments; it returns a `job_id`.
  2) Poll with `poll_job` to see `pending`/`running`/`completed`/`failed`/`cancelled` plus any result payload.
  3) Use `cancel_job` to stop a pending or running job.
- **Limits**: Only existing tools can be run asynchronously. Jobs resume after server restarts; cancellation is best-effort for running work.

## Core Concepts Explained

### Context Management: The Stable-Inline List

The server uses a **Stable-Inline List** to provide predictable context:

1. **First Call**: The server calculates a token budget (e.g., 85% of the model's window). It fills this budget by inlining the smallest files from your `context` first. Any files that don't fit are sent to a searchable vector store. The list of inlined files is then saved for the session.

2. **Subsequent Calls**: The server only resends files from that "stable list" *if they have changed*. This saves tokens and ensures the model isn't confused by files moving in and out of its direct context. `priority_context` files are always included inline.

### Session Management: The Unified Cache

All conversations are managed by the `UnifiedSessionCache`, a persistent SQLite database. This means:
- Sessions are preserved even if the server restarts
- The default session Time-To-Live (TTL) is 6 months, giving you long-term conversational memory
- Using descriptive `session_id`s helps build a rich, searchable project history

### Project History: How It Works

The Force continuously captures and indexes your development history:

1. **AI Conversations**: Every interaction with The Force is summarized and indexed
2. **Git Commits**: A post-commit hook captures code changes with context
3. **Searchable Knowledge**: Query your project's entire history instantly

Install the git hook to capture commits:
```bash
cd your-project
# Run from the mcp-the-force repository directory:
bash /path/to/mcp-the-force/scripts/install-history-hook.sh
```

### Multi-Model Collaboration (GroupThink)

GroupThink lets multiple models think together on the same objective with shared memory:
- **Mix models by strength**: e.g., GPT-5.2 Pro (reasoning), Gemini 3 Pro (1M-context code analysis), Claude Opus (writing).
- **Shared whiteboard**: Every turn writes to a vector-store "whiteboard" so later turns see all prior arguments.
- **Two phases + validation**: Discussion turns → synthesis by a large-context model → validation rounds by the original panel.
- **Resume anytime**: Reuse the same `session_id` to continue an ongoing collaboration.

Quick start:
```json
{
  "session_id": "design-rag-pipeline-2025-11-21",
  "objective": "Design a production-ready RAG pipeline for our docs service",
  "models": ["chat_with_gpt52_pro", "chat_with_gemini3_pro_preview", "chat_with_claude45_opus", "chat_with_grok41"],
  "output_format": "Architecture doc with: Overview, Data Flow, Components, Ops, Risks",
  "discussion_turns": 6,
  "validation_rounds": 2,
  "context": ["/abs/path/to/repo"],
  "priority_context": ["/abs/path/to/repo/diagrams/system.md"]
}
```
Run it by invoking the `group_think` tool from your MCP client (e.g., Claude Code or `mcp-cli`). Keep the `session_id` stable to let the models build on prior turns; change it to start a fresh panel.

> **Note**: GroupThink uses internal `chat_with_*` tool names in the `models` parameter.

## Advanced Topics

### Configuration
For a full list of settings, see [CONFIGURATION.md](docs/CONFIGURATION.md). You can manage settings via YAML files or the `mcp-config` CLI tool.

### Local Vector Store (HNSW)

The Force includes a high-performance local vector store option using HNSW (Hierarchical Navigable Small World) graphs. This provides:

- **No External Dependencies**: Works completely offline, no API calls required
- **Fast Performance**: HNSW provides logarithmic search complexity
- **Automatic Model Download**: Downloads a compact 45MB embedding model on first use
- **Smart Caching**: Embeddings are cached in memory for repeated queries
- **Cosine Similarity**: Uses cosine distance for accurate semantic search

To use the local HNSW vector store instead of OpenAI:

```yaml
# config.yaml
vector_stores:
  default_vector_store_provider: hnsw  # Use 'openai' for OpenAI's vector store
```

**Note**: HNSW requires a C++ compiler to install (`hnswlib` builds from source). Install build tools first:
- macOS: `xcode-select --install`
- Linux: `apt-get install build-essential`
- Windows: Install Microsoft C++ Build Tools

The HNSW implementation includes:
- Automatic persistence to `./.mcp-the-force/vectorstores/hnsw/`
- Optimized search with `ef=50` for better accuracy
- Thread-safe operations with proper locking
- Dynamic index resizing as your knowledge base grows

### Developer Logging

The Force integrates with VictoriaLogs for centralized debugging. 

#### Setting up VictoriaLogs

1. Start VictoriaLogs using Docker:
```bash
docker run --rm -it -p 9428:9428 \
  -v ./victoria-logs-data:/victoria-logs-data \
  docker.io/victoriametrics/victoria-logs:v1.26.0 \
  -storageDataPath=/victoria-logs-data
```

Note: The `victoria-logs-data/` directory is already in `.gitignore` to prevent accidentally committing logs.

2. Enable developer mode to access log search:
```bash
# Enable in environment
LOGGING__DEVELOPER_MODE__ENABLED=true
```

3. Search logs using LogsQL:
```python
# In Claude or any MCP client
search_mcp_debug_logs(query='_time:10m error {app="mcp-the-force"}')
```

VictoriaLogs UI is available at http://localhost:9428/vmui/

### Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) for architecture details and development guidelines.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
