# MCP Second‑Brain Server

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
gcloud auth application-default login

# 5. Validate your configuration
mcp-config validate

# 6. Run the server
uv run -- mcp-second-brain
```

## 🤖 Claude Desktop Integration

### Basic Configuration

Add the following to your Claude Desktop configuration file (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "second-brain": {
      "command": "uv",
      "args": ["--directory", "/path/to/mcp-second-brain", "run", "mcp-second-brain"]
    }
  }
}
```

### Advanced Configuration with Logging

To enable the developer logging system for debugging MCP operations:

```json
{
  "mcpServers": {
    "second-brain": {
      "command": "uv",
      "args": ["--directory", "/path/to/mcp-second-brain", "run", "mcp-second-brain"],
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

When developer logging is enabled, you can search logs using the `search_mcp_debug_logs` tool within Claude Desktop.

### Environment Variables in Claude Desktop

Any configuration setting can be overridden via environment variables in the MCP server configuration. The pattern is:

- Use double underscores (`__`) to separate nested configuration levels
- Examples:
  - `OPENAI_API_KEY` - Set OpenAI API key
  - `LOGGING__LEVEL` - Set logging level (DEBUG, INFO, WARNING, ERROR)
  - `MCP__CONTEXT_PERCENTAGE` - Set context window usage (0.0-1.0)
  - `PROVIDERS__VERTEX__PROJECT` - Set Google Cloud project

## 🔧 Configuration

MCP Second-Brain uses a unified YAML-based configuration system with environment variable overlay support.

### Configuration Sources

The system loads configuration from multiple sources with clear precedence (highest to lowest):

1. **Environment Variables** - Override any setting for CI/CD and production (recommended for Claude Desktop)
2. **YAML Files** - Alternative configuration method (`config.yaml` + `secrets.yaml`)
3. **Defaults** - Sensible defaults built into the application

**Note**: For Claude Desktop integration, we recommend using environment variables in the MCP server configuration rather than YAML files.

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

### Environment Variable Override

You can override any setting using environment variables:

| Category | Environment Variables |
|----------|----------------------|
| OpenAI | `OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| MCP Server | `HOST`, `PORT`, `CONTEXT_PERCENTAGE`, `DEFAULT_TEMPERATURE` |
| Logging | `LOG_LEVEL` |
| Vertex AI | `VERTEX_PROJECT`, `VERTEX_LOCATION` |
| Vertex OAuth (CI/CD) | `GCLOUD_OAUTH_CLIENT_ID`, `GCLOUD_OAUTH_CLIENT_SECRET`, `GCLOUD_USER_REFRESH_TOKEN` |

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
       api_key: xai-...
   ```
3. Or set environment variable: `export XAI_API_KEY=xai-...`

### For Local Development (Recommended)

**Google Cloud Application Default Credentials (ADC)**:
```bash
# Install gcloud CLI
curl https://sdk.cloud.google.com | bash

# Authenticate
gcloud auth application-default login

# Set project (optional)
gcloud config set project your-project-id
```

### For Production & CI/CD

#### Option 1: Service Account (Traditional)
```bash
# Create service account
gcloud iam service-accounts create mcp-second-brain

# Grant necessary permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT \
  --member="serviceAccount:mcp-second-brain@YOUR_PROJECT.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

# Create and download key
gcloud iam service-accounts keys create service-account-key.json \
  --iam-account=mcp-second-brain@YOUR_PROJECT.iam.gserviceaccount.com

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
  mcp-second-brain@$PROJECT_ID.iam.gserviceaccount.com
```

**GitHub Secrets Setup:**
- `GCP_PROJECT_ID`: Your Google Cloud project ID
- `GCP_WORKLOAD_IDENTITY_PROVIDER`: `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions/providers/github`
- `GCP_SERVICE_ACCOUNT`: `mcp-second-brain@PROJECT_ID.iam.gserviceaccount.com`

## 🛠️ Available Tools

### Primary Chat Tools

| Tool | Model | Best For | Context | Sessions |
|------|-------|----------|---------|----------|
| `chat_with_gemini25_pro` | Gemini 2.5 Pro | Deep analysis, multimodal content | ~1M tokens | ✅ |
| `chat_with_gemini25_flash` | Gemini 2.5 Flash | Fast summaries, quick insights | ~1M tokens | ✅ |
| `chat_with_o3` | OpenAI o3 | Step-by-step reasoning, algorithms | ~200k tokens | ✅ |
| `chat_with_o3_pro` | OpenAI o3-pro | Formal analysis, complex debugging | ~200k tokens | ✅ |
| `chat_with_gpt4_1` | GPT-4.1 | Large-scale refactoring, RAG workflows | ~1M tokens | ✅ |
| `chat_with_grok3_reasoning` | xAI Grok 3 Beta | Complex problem solving, debugging | ~131k tokens | ✅ |
| `chat_with_grok4` | xAI Grok 4 | Advanced reasoning, large documents | ~256k tokens | ✅ |

### Research Tools

| Tool | Model | Best For | Features |
|------|-------|----------|----------|
| `research_with_o3_deep_research` | OpenAI o3-deep-research | Ultra-deep research with web search | 10-60 min response time |
| `research_with_o4_mini_deep_research` | OpenAI o4-mini-deep-research | Fast research with web search | 2-10 min response time |

### Utility Tools

- `list_models` - List all available models and their capabilities
- `search_project_history` - Search past conversations and git commits
- `search_session_attachments` - Search files attached to current session
- `search_mcp_debug_logs` - Search debug logs (requires developer mode enabled)

### Tool Naming Convention

Tools follow these naming patterns for clarity and consistency:
- `chat_with_{model_name}` - Conversational AI assistance with specific models
- `research_with_{model_name}` - Autonomous research tools with web search capabilities

## 📁 Smart Context Management

The server intelligently handles large codebases through a two-tier approach:

### 🔄 **Inline Context** (Fast Access)
- Files within context percentage (default 85% of model limit) are embedded directly in the prompt
- Provides immediate access for small to medium projects
- Optimized for quick analysis and focused tasks

### 🔍 **Vector Store/RAG** (Large Projects)
- Files exceeding the inline limit are uploaded to OpenAI vector stores
- Automatic semantic search and retrieval
- Handles codebases of any size with intelligent chunking

### File Filtering
- **Respects .gitignore**: Automatically excludes files based on your project's .gitignore rules
- **Binary file detection**: Skips non-text files (images, binaries, archives)
- **Size limits**: 500KB per file, 50MB total maximum
- **Supported extensions**: 60+ text file types including code, docs, configs

## 💬 Conversation Support

### Multi-Turn Sessions

All models support persistent conversations through session management:

**OpenAI models (o3, o3-pro, gpt-4.1, research models)**:
- Pass `session_id` parameter to maintain conversation continuity
- Server maintains ephemeral cache (1 hour TTL) of OpenAI response IDs
- No conversation history stored - OpenAI maintains full context

**Gemini models (gemini-2.5-pro, gemini-2.5-flash)**:
- Require `session_id` parameter for multi-turn conversations
- Full conversation history stored locally in SQLite
- Same TTL and cache management as OpenAI models

### Session Best Practices
- Use descriptive session IDs: `"debug-auth-issue-2024"`
- Keep sessions focused on single topics for better context
- Clean up long sessions by starting fresh when context becomes cluttered

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
Use second-brain chat_with_gemini25_flash with {"instructions": "Review this function for potential improvements", "output_format": "Bullet points with specific suggestions", "context": ["/src/utils.py"], "session_id": "code-review-session"}
```

### Large Codebase Analysis with RAG

```
# Analyze large codebase using attachments for RAG
Use second-brain chat_with_gpt4_1 with {"instructions": "Analyze this codebase for architectural patterns and potential improvements", "output_format": "Structured analysis with specific recommendations", "context": [], "attachments": ["/path/to/docs/", "/path/to/src/"], "session_id": "architecture-analysis"}
```

### Structured Output for Reliable Results

```
# Get structured JSON output for programmatic use
Use second-brain chat_with_o3 with {"instructions": "Calculate the complexity and provide metrics for this codebase", "output_format": "JSON object with metrics", "context": ["/src"], "session_id": "complexity-analysis", "structured_output_schema": {"type": "object", "properties": {"cyclomatic_complexity": {"type": "integer"}, "lines_of_code": {"type": "integer"}, "maintainability_score": {"type": "string"}}, "required": ["cyclomatic_complexity", "lines_of_code", "maintainability_score"]}}
```

### Research with Web Search

```
# Deep research with autonomous web search
Use second-brain research_with_o3_deep_research with {"instructions": "Research the latest advances in vector databases and their applications in RAG", "output_format": "Comprehensive report with recent developments and practical applications", "context": [], "session_id": "vector-db-research"}
```

### Cross-Model Collaboration

```
# Use multiple models for comprehensive analysis
Use second-brain chat_with_gemini25_flash with {"instructions": "What are the main security concerns in this authentication system?", "output_format": "List of potential security issues", "context": ["/src/auth/"], "session_id": "security-review-quick"}

# Then deep dive with reasoning model
Use second-brain chat_with_o3_pro with {"instructions": "Analyze the authentication system for subtle security vulnerabilities", "output_format": "Detailed security analysis with remediation steps", "context": ["/src/auth/"], "session_id": "security-review-deep"}
```

## 🧠 Project History

The server automatically captures and indexes:
- **Conversation History**: All AI interactions with context and decisions
- **Git Commits**: Commit messages, diffs, and metadata for institutional memory

Search across project history:
```
# Search past decisions and commit history
Use second-brain search_project_history with {"query": "authentication implementation decisions", "max_results": 10}
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
search_mcp_debug_logs(instance="mcp-second-brain_dev_8747aa1d")

# Oldest to newest with time range
search_mcp_debug_logs(since="24h", order="asc")
```

### Search Parameters
- `text`: Search for text in log messages (case-insensitive)
- `severity`: Filter by log level (debug|info|warning|error|critical)
- `since/until`: Time range (5m, 2h, 3d) or absolute timestamps
- `project`: "current" (default), "all", or specific path
- `context`: Environment filter (dev|test|e2e|*)
- `instance`: Instance ID filter (exact or wildcard pattern)
- `limit`: Maximum results (default: 100)
- `order`: Sort order ("desc" newest first, "asc" oldest first)

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