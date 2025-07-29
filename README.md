# MCP The Force Server

An intelligent Model Context Protocol (MCP) server that orchestrates multiple AI models with advanced context management for large codebases. Built with a sophisticated descriptor-based tool system, it supports both OpenAI (o3, o3-pro, gpt-4.1) and Google Gemini (2.5-pro, 2.5-flash) models with smart file inlining and vector store integration.

## 🚀 Quick Start

```bash
# 1. Install dependencies
uv pip install -e .

# 2. Initialize configuration (creates config.yaml and secrets.yaml)
mcp-config init

# 3. Add your API keys to secrets.yaml
# Edit secrets.yaml and add your OpenAI API keys

# 4. Set up Google Cloud authentication (for Gemini models)
# Option A: Use global ADC (default)
gcloud auth application-default login

# Option B: Use project-specific ADC (recommended for multiple accounts)
# See "Per-Project ADC Configuration" section below

# 5. Validate your configuration
mcp-config validate

# 6. Run the server
uv run -- mcp-the-force
```

## 🤖 Claude Desktop Integration

### Basic Configuration

Add the following to your Claude Desktop configuration file (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "the-force": {
      "command": "uv",
      "args": ["--directory", "/path/to/mcp-the-force", "run", "mcp-the-force"]
    }
  }
}
```

### Advanced Configuration with Logging

To enable the developer logging system for debugging MCP operations:

```json
{
  "mcpServers": {
    "the-force": {
      "command": "uv",
      "args": ["--directory", "/path/to/mcp-the-force", "run", "mcp-the-force"],
      "env": {
        "LOGGING__DEVELOPER_MODE__ENABLED": "true",
        "LOGGING__DEVELOPER_MODE__PORT": "4711",
        "LOGGING__DEVELOPER_MODE__DB_PATH": ".mcp_logs.sqlite3",
        "LOGGING__DEVELOPER_MODE__BATCH_SIZE": "100",
        "LOGGING__DEVELOPER_MODE__BATCH_TIMEOUT": "1.0",
        "LOGGING__DEVELOPER_MODE__MAX_DB_SIZE_MB": "1000"
      }
    }
  }
}
```

When developer logging is enabled in `config.yaml`, you can search logs using the `search_mcp_debug_logs` tool within Claude Desktop.

### Environment Variables in Claude Desktop

Any configuration setting can be overridden via environment variables in the MCP server configuration. The pattern is:

- Use double underscores (`__`) to separate nested configuration levels
- Examples:
  - `OPENAI_API_KEY` - Set OpenAI API key
  - `LOGGING__LEVEL` - Set logging level (DEBUG, INFO, WARNING, ERROR)
  - `MCP__CONTEXT_PERCENTAGE` - Set context window usage (0.0-1.0)
  - `PROVIDERS__VERTEX__PROJECT` - Set Google Cloud project

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

### Google Gemini / Vertex AI

The adapter supports three authentication methods with the following precedence:

1.  **API Key (Gemini API)**: For direct authentication with the Gemini API.
2.  **Service Account (Vertex AI)**: For authentication in production or CI/CD environments.
3.  **Application Default Credentials (ADC)**: For local development.

#### 1. API Key Setup
1. Get your API key from Google AI Studio.
2. Add to `secrets.yaml`:
   ```yaml
   providers:
     gemini:
       enabled: true
       api_key: "your-gemini-api-key"
   ```
3. Or set environment variable: `export GEMINI_API_KEY=your-gemini-api-key`

#### 2. Service Account
Follow the "For Production & CI/CD" instructions below to create and use a service account key.

#### 3. Application Default Credentials (ADC)
Follow the "For Local Development (Recommended)" instructions below to set up ADC.

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

### For Production & CI/CD

#### Option 1: Service Account (Traditional)
```bash
# Create service account
gcloud iam service-accounts create mcp-the-force

# Grant necessary permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT \
  --member="serviceAccount:mcp-the-force@YOUR_PROJECT.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

# Create and download key
gcloud iam service-accounts keys create service-account-key.json \
  --iam-account=mcp-the-force@YOUR_PROJECT.iam.gserviceaccount.com

# Set environment variable
export GOOGLE_APPLICATION_CREDENTIALS="./service-account-key.json"
```

#### Option 2: Workload Identity (Recommended for GitHub Actions)

**Setup Workload Identity Pool:**
```bash
# Create workload identity pool
gcloud iam workload-identity-pools create "github-actions" \
  --project="$PROJECT_ID" \
  --location="global"

# Create provider
gcloud iam workload-identity-pools providers create-oidc "github" \
  --project="$PROJECT_ID" \
  --location="global" \
  --workload-identity-pool="github-actions" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository"

# Bind service account
gcloud iam service-accounts add-iam-policy-binding \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions/attribute.repository/$REPO" \
  mcp-the-force@$PROJECT_ID.iam.gserviceaccount.com
```

**GitHub Secrets Setup:**
- `GCP_PROJECT_ID`: Your Google Cloud project ID
- `GCP_WORKLOAD_IDENTITY_PROVIDER`: `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions/providers/github`
- `GCP_SERVICE_ACCOUNT`: `mcp-the-force@PROJECT_ID.iam.gserviceaccount.com`

## 🛠️ Available Tools

### Primary Chat Tools

| Tool | Model | Best For | Context | Sessions | Web Search |
|---|---|---|---|---|---|
| `chat_with_gemini25_pro` | Gemini 2.5 Pro | Deep analysis, multimodal | ~1M tokens | ✅ | No |
| `chat_with_gemini25_flash` | Gemini 2.5 Flash | Fast summaries, triage | ~1M tokens | ✅ | No |
| `chat_with_o3` | OpenAI o3 | Step-by-step reasoning | ~200k tokens | ✅ | ✅ |
| `chat_with_o3_pro` | OpenAI o3-pro | Formal analysis, deep debugging | ~200k tokens | ✅ | ✅ |
| `chat_with_gpt4_1` | GPT-4.1 | Large-scale refactoring, RAG | ~1M tokens | ✅ | ✅ |
| `chat_with_grok4` | xAI Grok 4 | Advanced reasoning, real-time info | ~256k tokens | ✅ | ✅ |
| `chat_with_grok3_reasoning` | Grok 3 Beta | Complex problem solving, real-time info | ~131k tokens | ✅ | ✅ |

### Research Tools

| Tool | Model | Best For | Features |
|---|---|---|---|
| `research_with_o3_deep_research` | o3-deep-research | Ultra-deep research | Autonomous web search (10-60 min) |
| `research_with_o4_mini_deep_research` | o4-mini-deep-research | Fast, focused research | Autonomous web search (2-10 min) |

### Utility Tools

-   `list_models` - List all available models and their capabilities.
-   `count_project_tokens` - Count tokens for specified files or directories.
-   `search_project_history` - Search past conversations and git commits from the project's long-term memory.
-   `search_mcp_debug_logs` - (Developer mode only) Run a raw LogsQL query against VictoriaLogs debug logs. Note: This tool no longer accepts friendly parameters; it takes a single `query` string containing the raw LogsQL.

### Tool Naming Convention

Tools follow these naming patterns for clarity and consistency:
- `chat_with_{model_name}` - Conversational AI assistance with specific models
- `research_with_{model_name}` - Autonomous research tools with web search capabilities

## 📁 Smart Context Management

The server intelligently handles large codebases through a "stable inline list" approach, which optimizes context for multi-turn conversations.

### How It Works

1.  **First Request**: The server analyzes your `context` files.
    *   It calculates a `token_budget` based on the model's context window (e.g., 85% of 1M tokens).
    *   It fills this budget by inlining the smallest files first to maximize the number of complete files the model sees.
    *   Files that don't fit are designated for a vector store.
    *   This initial set of inlined files becomes the **stable inline list** for the session.

2.  **Subsequent Requests (in the same session)**:
    *   The server only sends files from the stable list that have **changed** since the last turn.
    *   Unchanged files are not sent, saving significant tokens and reducing latency.
    *   Files that were sent to the vector store remain available for searching via the model's internal `search_task_files` function.

This provides the speed of inline context with the scale of a vector store, making conversations about large projects efficient.

### File Filtering
- **Respects .gitignore**: Automatically excludes files based on your project's .gitignore rules.
- **Binary file detection**: Skips non-text files (images, binaries, archives).
- **Size limits**: 2MB per file, 50MB total maximum per request.
- **Supported extensions**: 60+ text file types including code, docs, and configs.

## 💬 Conversation Support

All AI chat and research tools support persistent multi-turn conversations via the `session_id` parameter.

-   **Unified Persistent Caching**: The server uses a single SQLite database (`.mcp_sessions.sqlite3` by default) to manage conversation history for **all** models (OpenAI, Gemini, and Grok). This ensures conversations survive server restarts.
-   **How it Works**:
    -   **OpenAI**: The server caches the `response_id` required by the OpenAI Responses API to continue a conversation.
    -   **Gemini/Grok**: The server stores the full conversation history (all user and assistant messages) in the database.
-   **Session TTL**: The default Time-To-Live for all sessions is 1 hour, but this is configurable in `config.yaml`.
-   **Session IDs**: Session IDs are global. Use unique, descriptive names for different tasks (e.g., "debug-auth-issue-2024-07-15").

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
# Analyze large codebase using attachments for RAG
Use the-force chat_with_gpt4_1 with {"instructions": "Analyze this codebase for architectural patterns and potential improvements", "output_format": "Structured analysis with specific recommendations", "context": [], "attachments": ["/path/to/docs/", "/path/to/src/"], "session_id": "architecture-analysis"}
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
