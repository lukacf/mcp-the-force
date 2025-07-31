# Configuration Reference

This document provides a comprehensive reference for all configuration settings available in the `mcp-the-force` server. Settings are managed via `config.yaml` and an optional `secrets.yaml` file, with environment variables taking the highest precedence.

## Configuration File Locations

### Default Location (Project-Local)
- **Location**: `./.mcp-the-force/` in your project directory
- **Files**: `config.yaml` and `secrets.yaml`
- **Note**: The server automatically creates this directory on first run
- **Security**: Add `.mcp-the-force/` to your `.gitignore` file to prevent committing secrets

### Custom Locations
- Set `MCP_CONFIG_FILE` and `MCP_SECRETS_FILE` environment variables to use any location
- These environment variables always take precedence over defaults

### For MCP Developers
When developing mcp-the-force itself, configuration works the same way - create `.mcp-the-force/config.yaml` and `.mcp-the-force/secrets.yaml` in your clone directory

## General Notes

*   **Configuration Files**:
    *   `config.yaml`: Used for non-sensitive configuration.
    *   `secrets.yaml`: Used for sensitive values like API keys and tokens. Values in this file are merged with and override `config.yaml`.
*   **Environment Variables**: Any setting can be overridden by an environment variable. The format is `SECTION__SETTING_NAME` (e.g., `MCP__PORT`). A number of legacy, non-nested environment variables are also supported for backward compatibility.
*   **Restart Required**: The server reads configuration files on startup. Any changes to `config.yaml`, `secrets.yaml`, or environment variables require a server restart to take effect.
*   **Paths**: All relative paths in the configuration are resolved relative to the directory containing the `config.yaml` file.

---

## Providers

These settings configure the various AI model providers. The settings are nested under a top-level `providers` key in YAML.

**YAML Example:**

```yaml
providers:
  openai:
    enabled: true
    api_key: "..."
  vertex:
    enabled: true
    project: "my-gcp-project"
    location: "us-central1"
```

### OpenAI (`openai`)

| YAML Path | Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `openai.enabled` | `MCP__OPENAI__ENABLED` | `bool` | `True` | Enable or disable the OpenAI provider. |
| `openai.api_key` | `MCP__OPENAI__API_KEY` or `OPENAI_API_KEY` | `string` | `null` | **Secret.** Your OpenAI API key. |
| `openai.max_output_tokens` | `MCP__OPENAI__MAX_OUTPUT_TOKENS` | `int` | `65536` | Default maximum number of tokens the model can generate. |
| `openai.max_function_calls` | `MCP__OPENAI__MAX_FUNCTION_CALLS` | `int` | `500` | Maximum number of function call rounds for agentic workflows. |
| `openai.max_parallel_tool_exec` | `MCP__OPENAI__MAX_PARALLEL_TOOL_EXEC` or `MAX_PARALLEL_TOOL_EXEC`| `int` | `8` | Maximum number of tools that can be executed in parallel (OpenAI specific). |

### Google Vertex AI (`vertex`)

| YAML Path | Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `vertex.enabled` | `MCP__VERTEX__ENABLED` | `bool` | `True` | Enable or disable the Vertex AI provider. |
| `vertex.api_key` | `MCP__VERTEX__API_KEY` | `string` | `null` | **Secret.** An API key for Vertex AI, if applicable. |
| `vertex.project` | `MCP__VERTEX__PROJECT` or `VERTEX_PROJECT` | `string` | `null` | Your Google Cloud Platform project ID. |
| `vertex.location` | `MCP__VERTEX__LOCATION` or `VERTEX_LOCATION` | `string` | `null` | The Google Cloud location for your Vertex AI resources (e.g., `us-central1`). |
| `vertex.oauth_client_id` | `MCP__VERTEX__OAUTH_CLIENT_ID` or `GCLOUD_OAUTH_CLIENT_ID` | `string` | `null` | **Secret.** OAuth Client ID for user authentication in CI/CD. |
| `vertex.oauth_client_secret` | `MCP__VERTEX__OAUTH_CLIENT_SECRET` or `GCLOUD_OAUTH_CLIENT_SECRET` | `string` | `null` | **Secret.** OAuth Client Secret for user authentication in CI/CD. |
| `vertex.user_refresh_token` | `MCP__VERTEX__USER_REFRESH_TOKEN` or `GCLOUD_USER_REFRESH_TOKEN` | `string` | `null` | **Secret.** User refresh token for OAuth authentication in CI/CD. |
| `vertex.adc_credentials_path` | `MCP__VERTEX__ADC_CREDENTIALS_PATH` | `string` | `null` | Path to a service account JSON file (Application Default Credentials). If set, `GOOGLE_APPLICATION_CREDENTIALS` will be set in the environment. |
| `vertex.max_output_tokens` | `MCP__VERTEX__MAX_OUTPUT_TOKENS` | `int` | `65536` | Default maximum number of tokens the model can generate. |
| `vertex.max_function_calls` | `MCP__VERTEX__MAX_FUNCTION_CALLS` | `int` | `500` | Maximum number of function call rounds for agentic workflows. |

### Google Gemini API (`gemini`)

Direct Gemini API configuration (alternative to Vertex AI).

| YAML Path | Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `gemini.enabled` | `MCP__GEMINI__ENABLED` | `bool` | `True` | Enable or disable the Gemini API provider. |
| `gemini.api_key` | `MCP__GEMINI__API_KEY` or `GEMINI_API_KEY` | `string` | `null` | **Secret.** Your Google AI Studio API key for direct Gemini API access. |

**Note**: The Gemini adapter supports three authentication methods with the following precedence:
1. **Service Account** (via `vertex.adc_credentials_path`) - highest priority
2. **Gemini API Key** (via `gemini.api_key`) - direct API authentication
3. **Application Default Credentials (ADC)** - for local development with `vertex.project` and `vertex.location`

### X AI (`xai`)

| YAML Path | Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `xai.enabled` | `MCP__XAI__ENABLED` | `bool` | `True` | Enable or disable the X AI (Grok) provider. |
| `xai.api_key` | `MCP__XAI__API_KEY` or `XAI_API_KEY` | `string` | `null` | **Secret.** Your X AI API key. |
| `xai.max_output_tokens` | `MCP__XAI__MAX_OUTPUT_TOKENS` | `int` | `65536` | Default maximum number of tokens the model can generate. |
| `xai.max_function_calls` | `MCP__XAI__MAX_FUNCTION_CALLS` | `int` | `500` | Maximum number of function call rounds for agentic workflows. |

### Anthropic (`anthropic`)

| YAML Path | Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `anthropic.enabled` | `MCP__ANTHROPIC__ENABLED` | `bool` | `True` | Enable or disable the Anthropic Claude provider. |
| `anthropic.api_key` | `MCP__ANTHROPIC__API_KEY` or `ANTHROPIC_API_KEY` | `string` | `null` | **Secret.** Your Anthropic API key. |
| `anthropic.max_output_tokens` | `MCP__ANTHROPIC__MAX_OUTPUT_TOKENS` | `int` | `65536` | Default maximum number of tokens the model can generate. |
| `anthropic.max_function_calls` | `MCP__ANTHROPIC__MAX_FUNCTION_CALLS` | `int` | `500` | Maximum number of function call rounds for agentic workflows. |

### LiteLLM (`litellm`)

The configuration structure for `litellm` is identical to the other providers, based on the `ProviderConfig` model.

| YAML Path | Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `litellm.enabled` | `MCP__LITELLM__ENABLED` | `bool` | `True` | Enable or disable the LiteLLM provider. |
| `litellm.api_key` | `MCP__LITELLM__API_KEY` | `string` | `null` | **Secret.** Your LiteLLM API key. |

---

## MCP Server (`mcp`)

Core settings for the `mcp-the-force` server process.

| YAML Path | Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `mcp.host` | `MCP__MCP__HOST` or `HOST` | `string` | `"127.0.0.1"` | Host address for the server to bind to. |
| `mcp.port` | `MCP__MCP__PORT` or `PORT` | `int` | `8000` | Port for the server to listen on. Range: `1-65535`. |
| `mcp.context_percentage` | `MCP__MCP__CONTEXT_PERCENTAGE` or `CONTEXT_PERCENTAGE` | `float` | `0.85` | Percentage of a model's total context window to use for history and prompts. Range: `0.1-0.95`. |
| `mcp.default_temperature` | `MCP__MCP__DEFAULT_TEMPERATURE` or `DEFAULT_TEMPERATURE` | `float` | `1.0` | Default sampling temperature for AI models, controlling creativity. Range: `0.0-2.0`. |
| `mcp.thread_pool_workers` | `MCP__MCP__THREAD_POOL_WORKERS` | `int` | `10` | Maximum number of worker threads in the shared thread pool for background tasks. Range: `1-100`. |
| `mcp.default_vector_store_provider` | `MCP__MCP__DEFAULT_VECTOR_STORE_PROVIDER` | `string` | `"openai"` | Default provider to use for creating vector stores. Options: `"openai"` (default), `"hnsw"` (local, requires C++ compiler). |

---

## Logging (`logging`)

Configuration for application logging.

| YAML Path | Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `logging.level` | `MCP__LOGGING__LEVEL` or `LOG_LEVEL` | `string` | `"INFO"` | Minimum logging level. Options: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `logging.victoria_logs_url` | `MCP__LOGGING__VICTORIA_LOGS_URL` or `VICTORIA_LOGS_URL` | `string` | `"http://localhost:9428"` | URL for the VictoriaLogs instance for remote log shipping. |
| `logging.victoria_logs_enabled` | `MCP__LOGGING__VICTORIA_LOGS_ENABLED` or `DISABLE_VICTORIA_LOGS` | `bool` | `True` | Enable or disable shipping logs to VictoriaLogs. Note the legacy env var is inverted. |
| `logging.loki_app_tag` | `MCP__LOGGING__LOKI_APP_TAG` or `LOKI_APP_TAG` | `string` | `"mcp-the-force"` | The `app` tag to use when sending logs to VictoriaLogs/Loki. |
| `logging.project_path` | `MCP__LOGGING__PROJECT_PATH` or `MCP_PROJECT_PATH` | `string` | `null` | The primary project path, used to create relative paths in logs for privacy and consistency. |

### Developer Logging (`logging.developer_mode`)

Specialized ZMQ-based logging for development and debugging tools.

| YAML Path | Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `logging.developer_mode.enabled` | `MCP__LOGGING__DEVELOPER_MODE__ENABLED` | `bool` | `False` | Enable or disable the developer logging mode. |
| `logging.developer_mode.port` | `MCP__LOGGING__DEVELOPER_MODE__PORT` | `int` | `4711` | The ZMQ port for publishing log messages. |
| `logging.developer_mode.db_path` | `MCP__LOGGING__DEVELOPER_MODE__DB_PATH` | `string` | `".mcp-the-force/logs.sqlite3"` | Path to the SQLite database for the log viewer. |
| `logging.developer_mode.batch_size` | `MCP__LOGGING__DEVELOPER_MODE__BATCH_SIZE` | `int` | `100` | Number of log entries to batch before writing to the database. |
| `logging.developer_mode.batch_timeout` | `MCP__LOGGING__DEVELOPER_MODE__BATCH_TIMEOUT`| `float` | `1.0` | Timeout in seconds to wait before writing a batch to the database. |
| `logging.developer_mode.max_db_size_mb`| `MCP__LOGGING__DEVELOPER_MODE__MAX_DB_SIZE_MB`| `int` | `1000`| Maximum size of the log database in megabytes before rotation occurs. |

---

## Session (`session`)

Settings related to user session management.

| YAML Path | Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `session.ttl_seconds` | `MCP__SESSION__TTL_SECONDS` or `SESSION_TTL_SECONDS` | `int` | `15552000` (6 months) | Time-to-live for sessions in seconds. Must be at least `60`. |
| `session.db_path` | `MCP__SESSION__DB_PATH` or `SESSION_DB_PATH` | `string` | `".mcp-the-force/sessions.sqlite3"` | Path to the SQLite database file for storing session data. |
| `session.cleanup_probability` | `MCP__SESSION__CLEANUP_PROBABILITY` or `SESSION_CLEANUP_PROBABILITY` | `float` | `0.01` | The probability (0.0 to 1.0) of triggering a cleanup of expired sessions on any given request. |

---

## Vector Stores (`vector_stores`)

Configuration for vector store lifecycle management.

| YAML Path | Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `vector_stores.ttl_seconds` | `MCP__VECTOR_STORES__TTL_SECONDS` | `int` | `7200` (2 hours) | Time-to-live for vector stores in seconds. Minimum: `300` (5 minutes). |
| `vector_stores.cleanup_interval_seconds` | `MCP__VECTOR_STORES__CLEANUP_INTERVAL_SECONDS` | `int` | `300` (5 minutes) | How often to run automatic cleanup of expired vector stores. Minimum: `60` (1 minute). |
| `vector_stores.cleanup_probability` | `MCP__VECTOR_STORES__CLEANUP_PROBABILITY` | `float` | `0.02` | The probability (0.0 to 1.0) of triggering a cleanup during operations. |

*   **Note**: Vector stores are automatically cleaned up when they expire, preventing quota exhaustion. This replaces the previous external loiter-killer service.

---

## Memory (`memory`)

Configuration for the long-term memory system.

| YAML Path | Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `memory.enabled` | `MCP__MEMORY__ENABLED` or `MEMORY_ENABLED` | `bool` | `True` | Globally enable or disable the memory system. |
| `memory.rollover_limit` | `MCP__MEMORY__ROLLOVER_LIMIT` or `MEMORY_ROLLOVER_LIMIT` | `int` | `9500` | Token limit for memory stores before a rollover (summarization) is triggered. Must be at least `10`. |
| `memory.session_cutoff_hours` | `MCP__MEMORY__SESSION_CUTOFF_HOURS` or `MEMORY_SESSION_CUTOFF_HOURS` | `int` | `2` | Time in hours after which a user's session history is considered for summarization. Must be at least `1`. |
| `memory.summary_char_limit` | `MCP__MEMORY__SUMMARY_CHAR_LIMIT` or `MEMORY_SUMMARY_CHAR_LIMIT` | `int` | `200000`| Character limit for content sent to be summarized by the memory system. Must be at least `100`. |
| `memory.max_files_per_commit` | `MCP__MEMORY__MAX_FILES_PER_COMMIT` or `MEMORY_MAX_FILES_PER_COMMIT` | `int` | `50` | Maximum number of files to include from a single commit when storing git history in memory. Must be at least `1`. |

---

## Tools (`tools`)

Settings for built-in tools.

| YAML Path | Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tools.default_summarization_model` | `MCP__TOOLS__DEFAULT_SUMMARIZATION_MODEL` | `string` | `"chat_with_gemini25_flash"` | The default model used by the `describe_session` tool for summarization tasks. |

---

## Features (`features`)

This section is for experimental feature flags. Currently, there are no features configured.

---

## Backup (`backup`)

Configuration for database backup scripts.

| YAML Path | Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `backup.path` | `MCP__BACKUP__PATH` | `string` | `".mcp-the-force/backups"` | The directory where database backup files will be stored. |

---

## Security (`security`)

Settings to enforce security constraints.

| YAML Path | Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `security.path_blacklist` | `MCP__SECURITY__PATH_BLACKLIST` | `list[string]` | See below | A list of file system paths that are blocked from access. |

Default blacklisted paths:
- `/etc`
- `/usr`
- `/bin`
- `/sbin`
- `/boot`
- `/dev`
- `/proc`
- `/sys`
- `/root`
- `~/.ssh`
- `~/.gnupg`
- `~/.aws`
- `~/.config/gcloud`
- `~/.kube`
- `~/.docker`
- `/var/log`
- `/var/run`
- `/private/etc` (macOS)
- `/private/var` (macOS)
- `/System` (macOS)
- `/Library` (macOS)
- `C:\\Windows` (Windows)
- `C:\\Program Files` (Windows)

---

## Services (`services`)

Configuration for external services that MCP interacts with.

*Currently no external services are configured.*

---

## Development (`dev`)

Settings used exclusively for development and testing.

| YAML Path | Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `dev.adapter_mock` | `MCP__DEV__ADAPTER_MOCK` or `MCP_ADAPTER_MOCK` | `bool` | `False` | If `True`, use mock provider adapters for testing instead of making real API calls. |
| `dev.ci_e2e` | `MCP__DEV__CI_E2E` or `CI_E2E` | `bool` | `False` | Set to `True` when running in a Continuous Integration End-to-End testing environment. |

---

## Example Configuration Files

### Basic `config.yaml`

```yaml
mcp:
  context_percentage: 0.85
  default_temperature: 0.2

providers:
  openai:
    enabled: true
  vertex:
    enabled: true
    project: my-gcp-project
    location: us-central1

logging:
  level: INFO

session:
  ttl_seconds: 604800  # 1 week

memory:
  enabled: true
```

### Basic `secrets.yaml`

```yaml
providers:
  openai:
    api_key: sk-...
  gemini:
    api_key: AIza...  # Google AI Studio API key
  xai:
    api_key: xai-...
  anthropic:
    api_key: sk-ant-...
```

---

## Configuration Precedence

When a setting is defined in multiple places, the following precedence applies (highest to lowest):

1. **Environment variables** - Always take precedence
2. **secrets.yaml** - Overrides config.yaml
3. **config.yaml** - Overrides defaults
4. **Built-in defaults** - Used when nothing else is specified

### Environment Variable Configuration

You can pass configuration directly via environment variables when adding the server to Claude:

```bash
claude mcp add the-force -- \
  uvx --from git+https://github.com/lukacf/mcp-the-force \
  mcp-the-force \
  --env OPENAI_API_KEY=sk-... \
  --env XAI_API_KEY=xai-... \
  --env VERTEX_PROJECT=my-gcp-project
```

This is particularly useful for API keys, allowing you to configure the server without editing files.