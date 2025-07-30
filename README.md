# The Force MCP Server

> Every AI assistant needs an AI assistant.

The Force is a Model Context Protocol (MCP) server that unifies the world's most advanced AI models in a single interface. It intelligently manages context to overcome token limits and automatically builds a searchable knowledge base of your project's evolution. Works seamlessly with any MCP-compatible client, like Claude Code.

## Key Features

- **Unified Multi-Model Access**: Work with premier models from OpenAI, Google, Anthropic, and xAI through one consistent set of tools. Leverage the best model for every task without switching contexts.
- **Infinite Context**: Provide entire codebases as context, regardless of size. The Force intelligently includes critical files directly in the prompt and makes the rest available via high-performance vector search, effectively breaking through model context window limitations. It intelligently handles context updates when files change.
- **Self-Building Project Memory**: Automatically captures and indexes every AI conversation and git commit. This creates a searchable, long-term memory of your project's design decisions, debates, and history.

## Quick Start

### 1. Install

For Claude Code users, install with a single `uvx` command:

```bash
claude mcp add the-force -- \
  uvx --from git+https://github.com/lukacf/mcp-the-force \
  mcp-the-force
```

### 2. Configure

On the first run, the server will create configuration files in `~/.config/mcp-the-force/`.

- **Add API Keys**: Edit `~/.config/mcp-the-force/secrets.yaml` to add your API keys:
  ```yaml
  providers:
    openai:
      api_key: "sk-..."      # For OpenAI models
    xai:
      api_key: "xai-..."      # For Grok models
    anthropic:
      api_key: "sk-ant-..."  # For Claude models
  ```
- **Set up Google Cloud**: For Gemini models, authenticate with the gcloud CLI:
  ```bash
  gcloud auth application-default login
  ```
- Run `mcp-config init` to create these files manually if needed.

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

> "Before I start, what were the key decisions made when we first implemented JWT authentication? Search the project's memory."

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
- `chat_with_claude4_opus`: Deep analysis and formal reasoning with extended thinking (200k context)
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

### Project Memory: How It Works

The Force continuously captures and indexes your development history:

1. **AI Conversations**: Every interaction with The Force is summarized and indexed
2. **Git Commits**: A post-commit hook captures code changes with context
3. **Searchable Knowledge**: Query your project's entire history instantly

Install the git hook to capture commits:
```bash
cd your-project
bash ~/.config/mcp-the-force/scripts/install-memory-hook.sh
```

## Advanced Topics

### Configuration
For a full list of settings, see [CONFIGURATION.md](docs/CONFIGURATION.md). You can manage settings via YAML files or the `mcp-config` CLI tool.

### Loiter Killer Service
This companion service, enabled by default in `docker-compose.yaml`, automatically cleans up temporary OpenAI vector stores to prevent hitting account limits and incurring unnecessary costs.

```bash
docker-compose up -d loiter-killer
```

### Developer Logging
The Force integrates with VictoriaLogs for centralized debugging. Enable developer mode to search logs:

```bash
# Enable in environment
LOGGING__DEVELOPER_MODE__ENABLED=true

# Search logs with LogsQL
search_mcp_debug_logs(query='_time:10m error {app="mcp-the-force"}')
```

### Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) for architecture details and development guidelines.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
