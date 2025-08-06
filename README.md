# The Force MCP Server

![The Force MCP Server](docs/the-force.png)

> Every AI assistant needs an AI assistant.

The Force is a Model Context Protocol (MCP) server that unifies the world's most advanced AI models in a single interface. It intelligently manages context to overcome token limits and automatically builds a searchable knowledge base of your project's evolution. Works seamlessly with any MCP-compatible client, like Claude Code.

## Key Features

- **Unified Multi-Model Access**: Work with premier models from OpenAI, Google, Anthropic, and xAI through one consistent set of tools. Leverage the best model for every task without switching contexts.
- **Infinite Context**: Provide entire codebases as context, regardless of size. The Force intelligently includes critical files directly in the prompt and makes the rest available via high-performance vector search, effectively breaking through model context window limitations. It intelligently handles context updates when files change.
- **Self-Building Project History**: Automatically captures and indexes every AI conversation and git commit. This creates a searchable, long-term history of your project's design decisions, debates, and evolution.

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

Note: `uvx` is included with `uv` and runs Python tools without installing them globally.

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

### 3. Run

The server is now ready. Claude Code will start it automatically. To run it manually for development:

```bash
uv run -- mcp-the-force
```

## Usage Examples

Here's how you would instruct an assistant like Claude to use The Force:

### 1. Analyze a large codebase that exceeds any model's context window:

> "Do we have any circular dependencies? Use The Force Claude!"

The assistant would call:
```
Use the-force chat_with_gpt41 with {"instructions": "Analyze the dependency graph and identify circular dependencies", "context": ["/src", "/packages", "/services"], "session_id": "dep-analysis"}
```

*The Force automatically handles splitting the context between an inline prompt and a searchable vector store.*

### 2. Ensure a critical file is always in context:

> "Ask o3 to propose an implementation, and make sure you pay close attention to our `security_config.py` file."

The assistant would call:
```
Use the-force chat_with_o3_pro with {"instructions": "Propose how to implement the new architecture we discussed.", "context": ["/src/api"], "priority_context": ["/src/config/security_config.py"], "session_id": "auth-implementation"}
```

*`priority_context` guarantees `security_config.py` is included directly in the prompt.*

### 3. Search your project's entire history:

> "Before I start, what were the key decisions made when we first implemented JWT authentication? Search the project's history."

The assistant would call:
```
Use the-force search_project_history with {"query": "JWT implementation decisions; authentication architecture"}
```

*This searches a vector database of all past conversations and git commits.*

## Available Tools

All tools share a common set of parameters like `instructions`, `context`, `session_id`, etc.

### OpenAI Models
- `chat_with_o3`: Advanced reasoning with web search (200k context)
- `chat_with_o3_pro`: Deep formal analysis with web search (200k context)
- `chat_with_gpt41`: High-speed, large-scale analysis (1M context)
- `chat_with_codex_mini`: Fast, coding-specialized reasoning model (200k context)
- `research_with_o3_deep_research`: In-depth, long-running research tasks (10-60 min)
- `research_with_o4_mini_deep_research`: Fast research with web search (2-10 min)

### Google Models
- `chat_with_gemini25_pro`: Superior code analysis and complex reasoning (1M context)
- `chat_with_gemini25_flash`: High-speed summarization and analysis (1M context)

### Anthropic Models
- `chat_with_claude41_opus`: Deep analysis and formal reasoning with extended thinking (200k context)
- `chat_with_claude4_sonnet`: Fast long-context processing with extended thinking (200k context)
- `chat_with_claude3_opus`: Exceptional theory of mind and thoughtful discussions (200k context)

### xAI Models
- `chat_with_grok4`: Advanced reasoning with real-time web/X data (256k context)
- `chat_with_grok3_beta`: Deep reasoning with real-time web/X data (131k context)

### Utility Tools
- `search_project_history`: Search past conversations and git commits
- `list_sessions`: List recent AI conversation sessions
- `describe_session`: Get an AI-powered summary of a past session
- `count_project_tokens`: Analyze token usage for specified files/directories
- `search_mcp_debug_logs`: Query debug logs with LogsQL (developer mode only)

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

### Known Issues

#### MCP Server Crashes on Tool Cancellation (Claude Code 1.0.64+)

**Issue**: When cancelling long-running tool calls (pressing Escape) in Claude Code version 1.0.64 or later, the MCP server crashes with an "AssertionError: Request already responded to" error and becomes unresponsive.

**Cause**: Claude Code 1.0.64 changed the cancellation mechanism from regular asyncio cancellation to AnyIO cancel scopes, which kills the entire MCP server process instead of just the individual tool operation.

**Workaround**: 
- Avoid cancelling long-running operations
- If the server crashes, restart Claude Code to restore MCP functionality
- Consider downgrading to Claude Code 1.0.63 if cancellation is critical to your workflow

**Status**: A fix has been implemented in the MCP Python SDK ([PR #1153](https://github.com/modelcontextprotocol/python-sdk/pull/1153)), but the client-side changes in Claude Code 1.0.64+ bypass this fix. The issue has been reported to the Claude Code team.

### Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) for architecture details and development guidelines.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
