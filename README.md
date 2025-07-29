# MCP The Force Server

An intelligent Model Context Protocol (MCP) server that orchestrates multiple AI models with advanced context management for large codebases. Built with a sophisticated descriptor-based tool system, it supports both OpenAI (o3, o3-pro, gpt-4.1) and Google Gemini (2.5-pro, 2.5-flash) models with smart file inlining and vector store integration.

## 🚀 Quick Start

### For Claude Code Users (Recommended)

Install and run directly from GitHub with a single command:

```bash
claude mcp add the-force -- \
  uvx --from git+https://github.com/lukacf/mcp-the-force \
  mcp-the-force
```

On first run, the server will:
1. Create configuration files in `~/.config/mcp-the-force/`
2. Show you where to add your API keys
3. Start serving once configured

### Configure API Keys

After installation, add your API keys to `~/.config/mcp-the-force/secrets.yaml`:

```yaml
providers:
  openai:
    api_key: "sk-..."      # Your OpenAI API key
  xai:
    api_key: "xai-..."      # Your xAI API key
```

For Google Gemini models, authenticate with:
```bash
gcloud auth application-default login
```

### For Developers

If you want to modify the code or contribute:

```bash
# Clone and install for development
git clone https://github.com/lukacf/mcp-the-force
cd mcp-the-force
uv pip install -e ".[dev]"

# Initialize configuration
mcp-config init

# Run locally
uv run -- mcp-the-force
```

## 🤖 Claude Code Integration

### Using the Installed Server

If you used the Quick Start command above, your server is already configured! The Force is ready to assist you.

### Manual Configuration

If you need to manually configure or have installed from a local clone:

```bash
# For local development
claude mcp add-json the-force-dev '{
  "command": "uv",
  "args": ["--directory", "/path/to/mcp-the-force", "run", "mcp-the-force"],
  "env": {
    "OPENAI_API_KEY": "$OPENAI_API_KEY",
    "XAI_API_KEY": "$XAI_API_KEY",
    "LOG_LEVEL": "INFO"
  }
}'
```

### Environment Variables in Claude Code

Any configuration setting can be overridden via environment variables in the MCP server configuration. The pattern is:

- Use double underscores (`__`) to separate nested configuration levels
- Environment variables in the `env` block override YAML/secrets settings
- Examples:
  - `OPENAI_API_KEY` - Set OpenAI API key
  - `LOGGING__LEVEL` - Set logging level (DEBUG, INFO, WARNING, ERROR)
  - `MCP__CONTEXT_PERCENTAGE` - Set context window usage (0.0-1.0)
  - `PROVIDERS__VERTEX__PROJECT` - Set Google Cloud project

### Advanced Configuration

To override settings via environment variables:

```bash
claude mcp add-json the-force-custom '{
  "command": "uvx",
  "args": ["--from", "git+https://github.com/lukacf/mcp-the-force", "mcp-the-force"],
  "env": {
    "OPENAI_API_KEY": "$OPENAI_API_KEY",
    "XAI_API_KEY": "$XAI_API_KEY",
    "LOG_LEVEL": "DEBUG",
    "MCP__CONTEXT_PERCENTAGE": "0.75",
    "LOGGING__DEVELOPER_MODE__ENABLED": "true"
  },
  "description": "The-Force with custom settings"
}'
```

## 🔧 Configuration

MCP The-Force uses a unified YAML-based configuration system with environment variable overlay support.

### Configuration Sources

The system loads configuration from multiple sources with clear precedence (highest to lowest):

1. **Environment Variables** - Primarily for client integrations (e.g., Claude Desktop) or CI/CD. These will override YAML settings.
2. **YAML Files** - The primary and recommended method for local configuration (`config.yaml` for general settings, `secrets.yaml` for API keys).
3. **Defaults** - Sensible defaults built into the application.

### Setup Configuration Files

```bash
# Initialize configuration files
mcp-config init

# This creates:
# - config.yaml: Non-sensitive configuration (can be committed)
# - secrets.yaml: API keys and sensitive data (gitignored)
```

**config.yaml** - General settings (safe to commit):
```yaml
mcp:
  host: 127.0.0.1
  port: 8000
  context_percentage: 0.85  # Use 85% of model's context window
  default_temperature: 0.2

providers:
  openai:
    enabled: true
  vertex:
    enabled: true
    project: your-gcp-project
    location: us-central1

memory:
  enabled: true
  rollover_limit: 9500
```

**secrets.yaml** - API keys and credentials (gitignored):
```yaml
providers:
  openai:
    api_key: sk-proj-...
  anthropic:
    api_key: sk-ant-...
```


### Configuration CLI

```bash
mcp-config init                   # Create initial config files
mcp-config validate               # Validate configuration
mcp-config show                   # View merged configuration
mcp-config show --format json     # As JSON
mcp-config show --format env      # As environment variables
mcp-config export-client          # Generate mcp-config.json for Claude
```

### Configuration Reference

Below are the key configuration options. Settings can be configured via:
- YAML files (`config.yaml` and `secrets.yaml`)
- Environment variables (use `__` for nested settings, e.g., `MCP__CONTEXT_PERCENTAGE`)

#### Core Server Settings (`mcp`)

| Setting | Environment Variable | Type | Default | Description |
|---------|---------------------|------|---------|-------------|
| `mcp.host` | `MCP__HOST` or `HOST` | string | `"127.0.0.1"` | Host address to bind to |
| `mcp.port` | `MCP__PORT` or `PORT` | int | `8000` | Port to listen on (1-65535) |
| `mcp.context_percentage` | `MCP__CONTEXT_PERCENTAGE` | float | `0.85` | Percentage of model's context window to use (0.1-0.95) |
| `mcp.default_temperature` | `MCP__DEFAULT_TEMPERATURE` | float | `1.0` | Default sampling temperature (0.0-2.0) |
| `mcp.thread_pool_workers` | `MCP__THREAD_POOL_WORKERS` | int | `10` | Worker threads for background tasks (1-100) |

#### Provider Settings

**OpenAI** (`providers.openai`):
| Setting | Environment Variable | Type | Default | Description |
|---------|---------------------|------|---------|-------------|
| `openai.api_key` | `OPENAI_API_KEY` | string | - | **Secret.** Your OpenAI API key |
| `openai.max_parallel_tool_exec` | `MAX_PARALLEL_TOOL_EXEC` | int | `8` | Max parallel tool executions |

**Google Vertex AI** (`providers.vertex`):
| Setting | Environment Variable | Type | Default | Description |
|---------|---------------------|------|---------|-------------|
| `vertex.project` | `VERTEX_PROJECT` | string | - | GCP project ID |
| `vertex.location` | `VERTEX_LOCATION` | string | - | GCP location (e.g., us-central1) |

**xAI** (`providers.xai`):
| Setting | Environment Variable | Type | Default | Description |
|---------|---------------------|------|---------|-------------|
| `xai.api_key` | `XAI_API_KEY` | string | - | **Secret.** Your xAI API key |

#### Session Management (`session`)

| Setting | Environment Variable | Type | Default | Description |
|---------|---------------------|------|---------|-------------|
| `session.ttl_seconds` | `SESSION_TTL_SECONDS` | int | `15552000` (6 months) | Session time-to-live |
| `session.db_path` | `SESSION_DB_PATH` | string | `".mcp_sessions.sqlite3"` | Session database path |

#### Memory System (`memory`)

| Setting | Environment Variable | Type | Default | Description |
|---------|---------------------|------|---------|-------------|
| `memory.enabled` | `MEMORY_ENABLED` | bool | `true` | Enable memory system |
| `memory.rollover_limit` | `MEMORY_ROLLOVER_LIMIT` | int | `9500` | Token limit before rollover |

#### Logging (`logging`)

| Setting | Environment Variable | Type | Default | Description |
|---------|---------------------|------|---------|-------------|
| `logging.level` | `LOG_LEVEL` | string | `"INFO"` | Log level (DEBUG/INFO/WARNING/ERROR) |
| `logging.developer_mode.enabled` | `LOGGING__DEVELOPER_MODE__ENABLED` | bool | `false` | Enable developer logging |

For the complete list of all configuration options, see [CONFIGURATION.md](docs/CONFIGURATION.md).

## 🔐 Authentication

### xAI (Grok Models)

**API Key Setup**:
1. Get your API key from [x.ai](https://x.ai) (requires X Premium+ subscription)
2. Add to `secrets.yaml`:
   ```yaml
   providers:
     xai:
       enabled: true
       api_key: "xai-..." # Add your key here
   ```
3. Or set environment variable: `export XAI_API_KEY=xai-...`

### For Local Development (Recommended)

**Google Cloud Application Default Credentials (ADC)**:

#### Option 1: Global ADC (Simple)
```bash
# Install gcloud CLI
curl https://sdk.cloud.google.com | bash

# Authenticate
gcloud auth application-default login

# Set project (optional)
gcloud config set project your-project-id
```

#### Option 2: Per-Project ADC (Multiple Accounts)
If you work with multiple Google Cloud accounts/projects, you can configure project-specific ADC credentials:

1. **Generate project-specific credentials**:
```bash
# Create a .gcp directory in your project
mkdir .gcp

# Generate ADC for this specific project
GOOGLE_APPLICATION_CREDENTIALS=.gcp/adc-credentials.json \
  gcloud auth application-default login

# This creates credentials in .gcp/adc-credentials.json instead of the global location
```

2. **Configure in config.yaml**:
```yaml
providers:
  vertex:
    project: your-project-id
    location: us-central1
    adc_credentials_path: .gcp/adc-credentials.json
```

3. **Benefits**:
- Each project can use different Google Cloud accounts
- No need to switch global gcloud configurations
- Credentials are project-local (already in .gitignore)
- Works seamlessly with Docker/CI (mount the .gcp directory)

### For CI/CD Environments

For CI/CD environments where interactive authentication isn't possible, you have several options:

1. **Use existing ADC from the CI environment** - Many CI services provide Google Cloud authentication
2. **Set environment variables directly** - Pass credentials through the `env` block in your MCP configuration
3. **Use the OAuth refresh token approach** - Configure `oauth_client_id`, `oauth_client_secret`, and `user_refresh_token` in `secrets.yaml`

For detailed CI/CD setup instructions, see the project's CI configuration files.

## Available Tools

The server provides a suite of powerful tools for AI-assisted development, including chat/research models from various providers and local utilities for project management.

### AI Chat & Research Tools

These tools are dynamically generated based on provider-specific capabilities. Common parameters for all AI tools include:

-   `instructions` (string, required): The primary directive for the AI model.
-   `output_format` (string, required): A description of the desired response format.
-   `context` (list[string], required): A list of file or directory paths to be used as context.
-   `priority_context` (list[string], optional): A list of file or directory paths to prioritize for inline inclusion.
-   `session_id` (string, required): A unique identifier for a multi-turn conversation.
-   `disable_memory_store` (boolean, optional): If true, prevents the conversation from being saved to long-term project history.
-   `structured_output_schema` (dict, optional): A JSON schema that the model's output must conform to.

#### OpenAI Models

| Tool Name | Model Name | Context Window | Description |
| :--- | :--- | :--- | :--- |
| `chat_with_o3` | o3 | 200,000 | Chain-of-thought reasoning with web search. |
| `chat_with_o3_pro` | o3-pro | 200,000 | Deep analysis and formal reasoning with web search. |
| `chat_with_o4_mini` | o4-mini | 200,000 | Fast reasoning model. |
| `chat_with_gpt41` | gpt-4.1 | 1,000,000 | Fast long-context processing with web search. |
| `research_with_o3_deep_research` | o3-deep-research | 200,000 | Ultra-deep research with extensive web search (10-60 min). |
| `research_with_o4_mini_deep_research`| o4-mini-deep-research| 200,000 | Fast research with web search (2-10 min). |

**Key OpenAI Parameters:**
- `temperature` (float, optional): Controls randomness. Supported by GPT-4 models only. Default: `0.2`.
- `reasoning_effort` (string, optional): Controls 'thinking' time. Supported by o-series models only. Can be `low`, `medium`, or `high`.

#### Google Models

| Tool Name | Model Name | Context Window | Description |
| :--- | :--- | :--- | :--- |
| `chat_with_gemini25_pro` | gemini-2.5-pro | 1,000,000 | Deep multimodal analysis and complex reasoning. |
| `chat_with_gemini25_flash` | gemini-2.5-flash | 1,000,000 | Fast summarization and quick analysis. |

**Key Google Parameters:**
- `temperature` (float, optional): Controls randomness. Default: `1.0`.
- `reasoning_effort` (string, optional): Controls the 'thinking budget' for the model. Can be `low`, `medium`, or `high`.
- `disable_memory_search` (boolean, optional): If true, prevents the model from using the `search_project_history` tool.

#### xAI (Grok) Models

| Tool Name | Model Name | Context Window | Description |
| :--- | :--- | :--- | :--- |
| `chat_with_grok3_beta` | grok-3-beta | 131,000 | Deep reasoning using xAI Grok 3 Beta model. |
| `chat_with_grok4` | grok-4 | 256,000 | Advanced assistant using xAI Grok 4 model. |

**Key Grok Parameters:**
- `search_mode` (string, optional): Controls the 'Live Search' feature. Can be `auto`, `on`, or `off`. Default: `auto`.
- `search_parameters` (dict, optional): Fine-grained control over web search functionality.
- `return_citations` (boolean, optional): If true, response will include citations for web search results. Default: `true`.

### Utility Tools

These tools run locally to provide information about the project and server.

-   **`list_sessions`**: List existing AI conversation sessions for the current project.
    -   `limit` (int, optional): Maximum number of sessions to return. Default: `5`.
    -   `search` (string, optional): Substring filter for session ID or tool name.
    -   `include_summary` (boolean, optional): Whether to include cached summaries in the results.

-   **`describe_session`**: Generate an AI-powered summary of an existing session's conversation history.
    -   `session_id` (string, required): The ID of the session to summarize.
    -   `summarization_model` (string, optional): The AI model to use for summarization. Defaults to the one configured in `config.yaml`.
    -   `extra_instructions` (string, optional): Additional instructions for the AI generating the summary.
    -   `clear_cache` (boolean, optional): If true, forces regeneration of the summary.

-   **`search_project_history`**: Search the project's long-term memory (vector database of past conversations and commits).
    -   `query` (string, required): The query to search for. Semicolon-separated for multiple queries.
    -   `max_results` (int, optional): Maximum number of search results. Default: `40`.
    -   `store_types` (list[string], optional): Types of memory to search. Can be `['conversation', 'commit']`. Default searches both.

-   **`count_project_tokens`**: Count tokens for specified files or directories, respecting `.gitignore` and skipping binaries.
    -   `items` (list[string], required): A list of file and/or directory paths to analyze.
    -   `top_n` (int, optional): The number of top files and directories to include in the report. Default: `10`.

-   **`search_mcp_debug_logs`** (Developer Mode Only): Run a raw LogsQL query against the VictoriaLogs debug logging system.
    -   `query` (string, required): The raw LogsQL query string to execute.

## Smart Context Management

The server features an advanced context management system designed to handle large codebases efficiently, ensuring that models always have the most relevant information without exceeding their context window.

### The `context` and `priority_context` Parameters

All AI tools accept `context` and `priority_context` parameters, which take a list of file or directory paths.

-   **`context`**: The primary list of files and directories that the model should be aware of.
-   **`priority_context`**: A special list of files and directories that are **guaranteed** to be included directly in the prompt, as long as they fit within the model's total token budget. These files are processed first.

### The Stable-Inline List Feature

To ensure a predictable and efficient multi-turn conversation, the server uses a **Stable-Inline List**.

1.  **First Request**: When you make the first call in a new `session_id`, the server analyzes all files in `context` and `priority_context`.
    *   It calculates a token budget (typically 85% of the model's total context window).
    *   It fills this budget by inlining the smallest files first, maximizing the number of complete files the model sees directly.
    *   Any files that do not fit into this budget are designated for a searchable vector store.
    *   The list of files that were included inline is then saved and becomes the "stable list" for this session.

2.  **Subsequent Requests**: For all following requests in the same session:
    *   The server only sends files from the stable list that have been **modified** since the last turn. Unchanged files are not resent, saving a significant number of tokens.
    *   Files not on the stable list (i.e., those that initially went to the vector store) remain available for the model to search using its internal `search_task_files` function.

This mechanism provides the "best of both worlds": the speed and direct access of inline context, and the scalability of a vector store for large codebases.

### Token Budget Calculation

The token budget for inline context is calculated based on the `context_percentage` setting in `config.yaml` (default: `0.85`).

-   **Formula**: `token_budget = model_max_context * context_percentage`
-   The remaining percentage is reserved as a safety buffer for the prompt template, tool definitions, and the model's generated response.

### File Filtering
- **Respects .gitignore**: Automatically excludes files based on your project's .gitignore rules.
- **Binary file detection**: Skips non-text files (images, binaries, archives).
- **Size limits**: 500KB per file, 50MB total maximum per request.
- **Supported extensions**: 60+ text file types including code, docs, and configs.

## Session Management

### The UnifiedSessionCache

MCP The-Force uses a centralized and persistent session management system, the `UnifiedSessionCache`, to provide a seamless multi-turn conversation experience across all supported AI providers.

-   **Persistence**: All session data is stored in a local SQLite database (`.mcp_sessions.sqlite3` by default). This means your conversations are preserved even if you restart the server.
-   **Unified History**: The cache stores conversation history in a standardized format, allowing different models to participate in the same conceptual session (though they maintain separate histories).

### The `session_id` Parameter

The `session_id` is the key to conversational continuity.

-   **How it works**: When you make a call with a `session_id`, the server retrieves the history for that session from the cache and provides it to the model. After the model responds, the new turn is added to the session's history.
-   **Continuity Across Models**: While the history for `chat_with_o3` and `chat_with_gemini25_pro` are stored separately even with the same `session_id`, using the same ID is a good practice for conceptually related tasks. It also allows the `search_project_history` tool to find all related conversation turns.
-   **TTL**: Sessions have a Time-To-Live (TTL) configured in `config.yaml` (`session.ttl_seconds`). The default is 6 months, after which inactive sessions are automatically purged.

By using descriptive `session_id`s (e.g., `debug-auth-refactor-2024-07-22`), you create a rich, searchable history of your interactions that becomes a valuable part of your project's long-term memory.

## 📋 Structured Output Support

Most chat tools support structured JSON output through the `structured_output_schema` parameter.

**Supported Models**: `o3`, `o3-pro`, `gpt-4.1`, `gemini-2.5-pro`, `gemini-2.5-flash`  
**Not Supported**: Research models (`o3-deep-research`, `o4-mini-deep-research`) do not support custom structured output schemas.

### Basic Usage

```python
# Request structured output with a JSON schema
result = await mcp.call_tool(
    "chat_with_gpt4_1",
    instructions="Analyze this code for potential bugs",
    output_format="JSON with bug list and severity",
    context=["/src/main.py"],
    structured_output_schema={
        "type": "object",
        "properties": {
            "bugs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "line": {"type": "integer"},
                        "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                        "description": {"type": "string"}
                    },
                    "required": ["file", "line", "severity", "description"]
                }
            },
            "summary": {"type": "string"}
        },
        "required": ["bugs", "summary"]
    }
)
```

## 📖 Usage Examples

### Basic Analysis with Claude Code

```
# Simple code review
Use the-force chat_with_gemini25_flash with {"instructions": "Review this function for potential improvements", "output_format": "Bullet points with specific suggestions", "context": ["/src/utils.py"], "session_id": "code-review-session"}
```

### Large Codebase Analysis with RAG

```
# Analyze large codebase with automatic RAG for files that exceed context
Use the-force chat_with_gpt4_1 with {"instructions": "Analyze this codebase for architectural patterns and potential improvements", "output_format": "Structured analysis with specific recommendations", "context": ["/path/to/docs/", "/path/to/src/"], "session_id": "architecture-analysis"}
```

### Structured Output for Reliable Results

```
# Get structured JSON output for programmatic use
Use the-force chat_with_o3 with {"instructions": "Calculate the complexity and provide metrics for this codebase", "output_format": "JSON object with metrics", "context": ["/src"], "session_id": "complexity-analysis", "structured_output_schema": {"type": "object", "properties": {"cyclomatic_complexity": {"type": "integer"}, "lines_of_code": {"type": "integer"}, "maintainability_score": {"type": "string"}}, "required": ["cyclomatic_complexity", "lines_of_code", "maintainability_score"]}}
```

### Research with Web Search

```
# Deep research with autonomous web search
Use the-force research_with_o3_deep_research with {"instructions": "Research the latest advances in vector databases and their applications in RAG", "output_format": "Comprehensive report with recent developments and practical applications", "context": [], "session_id": "vector-db-research"}
```

### Cross-Model Collaboration

```
# Use multiple models for comprehensive analysis
Use the-force chat_with_gemini25_flash with {"instructions": "What are the main security concerns in this authentication system?", "output_format": "List of potential security issues", "context": ["/src/auth/"], "session_id": "security-review-quick"}

# Then deep dive with reasoning model
Use the-force chat_with_o3_pro with {"instructions": "Analyze the authentication system for subtle security vulnerabilities", "output_format": "Detailed security analysis with remediation steps", "context": ["/src/auth/"], "session_id": "security-review-deep"}
```

## 🧠 Project History

The server automatically captures and indexes:
- **Conversation History**: All AI interactions with context and decisions
- **Git Commits**: Commit messages, diffs, and metadata for institutional memory

Search across project history:
```
# Search past decisions and commit history
Use the-force search_project_history with {"query": "authentication implementation decisions", "max_results": 10}
```

## 🧹 Loiter Killer Service

The MCP server includes a companion service called "Loiter Killer" that manages the lifecycle of OpenAI vector stores created during RAG operations.

### Purpose
- **Automatic cleanup**: Deletes expired vector stores to prevent hitting API limits
- **Resource management**: Tracks and manages vector store usage across sessions
- **Cost optimization**: Prevents accumulation of unused vector stores that count against quotas

### Running the Service
```bash
# Start with docker-compose (recommended)
docker-compose up -d loiter-killer

# Or run directly
cd loiter_killer && python loiter_killer.py
```

The service runs on port 9876 by default (configurable via `services.loiter_killer_port`).

## 🔍 Developer Logging System

The MCP server integrates with VictoriaLogs for centralized logging and debugging across multiple projects and instances.

### Features
- **VictoriaLogs integration**: High-performance log aggregation and search
- **Multi-project support**: Logs from multiple MCP servers in one place
- **Instance tracking**: Semantic instance IDs for dev/test/e2e environments
- **Rich metadata**: Project paths, logger names, severity levels, and structured data
- **Docker-based deployment**: Easy setup with docker-compose

### Setup
1. **Start VictoriaLogs**:
   ```bash
   docker-compose up -d victorialogs
   ```

2. **Enable developer mode** in Claude Desktop config:
   ```json
   {
     "env": {
       "LOGGING__DEVELOPER_MODE__ENABLED": "true"
     }
   }
   ```

### Searching Logs
Use the `search_mcp_debug_logs` tool with AI-friendly parameters:

```
# Recent warnings in current project
search_mcp_debug_logs(severity="warning", since="30m")

# Find text across all projects
search_mcp_debug_logs(text="CallToolRequest", project="all")

# E2E test errors
search_mcp_debug_logs(severity="error", context="e2e")

# Specific instance logs
search_mcp_debug_logs(instance="mcp-the-force_dev_8747aa1d")

# Oldest to newest with time range
search_mcp_debug_logs(since="24h", order="asc")
```

### Searching Logs
Use the `search_mcp_debug_logs` tool with a raw LogsQL query string. This provides maximum flexibility for debugging.

**LogsQL Pocket Guide**
- `_time:5m error` - Find "error" in the last 5 minutes.
- `{app="mcp-the-force"} "CallToolRequest"` - Find a phrase in a specific app's logs.
- `_time:1h | stats count() by (tool_id)` - Aggregate logs to find the most used tools.

**Example Usage in Claude:**
`search_mcp_debug_logs(query='_time:10m error OR critical {app="mcp-the-force"} | sort by (_time desc)')`

### Log Levels
- `debug`: Detailed debugging information
- `info`: General informational messages  
- `warning`: Warning messages
- `error`: Error messages
- `critical`: Critical failures

## 📚 Documentation

- [CONTRIBUTING.md](CONTRIBUTING.md) - Development guide and architecture
- [docs/ADVANCED.md](docs/ADVANCED.md) - Advanced integration strategies
- [docs/API-REFERENCE.md](docs/API-REFERENCE.md) - LLM-facing API documentation

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
