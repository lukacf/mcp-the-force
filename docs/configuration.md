# Configuration Guide

MCP Second-Brain uses a unified configuration system that supports multiple sources with clear precedence rules.

## Configuration Sources

Configuration is loaded from the following sources (in order of precedence, highest to lowest):

1. **Environment Variables** - Always takes precedence
2. **YAML Configuration Files** - `config.yaml` and `secrets.yaml`
3. **Legacy .env File** - For backward compatibility
4. **Default Values** - Built into the application

## Quick Start

### 1. Initialize Configuration

```bash
mcp-config init
```

This creates two files:
- `config.yaml` - Non-sensitive configuration (can be committed to version control)
- `secrets.yaml` - API keys and sensitive data (automatically gitignored)

### 2. Configure Your Settings

Edit `config.yaml`:

```yaml
mcp:
  host: 127.0.0.1
  port: 8000
  context_percentage: 0.85
  default_temperature: 0.2

providers:
  openai:
    enabled: true
  vertex:
    enabled: true
    project: my-gcp-project
    location: us-central1

memory:
  enabled: true
  rollover_limit: 9500
```

Edit `secrets.yaml`:

```yaml
providers:
  openai:
    api_key: sk-proj-...
  vertex:
    # For CI/CD environments that can't use gcloud auth:
    oauth_client_id: "your-oauth-client-id"
    oauth_client_secret: "your-oauth-client-secret"
    user_refresh_token: "your-refresh-token"
  anthropic:
    api_key: claude-...
```

### 3. Validate Configuration

```bash
mcp-config validate
```

## CLI Commands

The `mcp-config` CLI provides several commands for managing configuration:

### `init`
Create initial configuration files.

```bash
mcp-config init [--force]
```

Options:
- `--force, -f`: Overwrite existing files

### `validate`
Validate configuration and check for missing required values.

```bash
mcp-config validate
```

### `export-env`
Export configuration as a `.env` file (useful for Docker or legacy systems).

```bash
mcp-config export-env [--output PATH]
```

Options:
- `--output, -o`: Output file path (default: `.env`)

### `export-client`
Generate `mcp-config.json` for Claude Code or other MCP clients.

```bash
mcp-config export-client [--output PATH]
```

Options:
- `--output, -o`: Output file path (default: `mcp-config.json`)

### `show`
Display current configuration.

```bash
mcp-config show [KEY] [--format FORMAT]
```

Arguments:
- `KEY`: Specific configuration key to show (e.g., `mcp.port`)

Options:
- `--format, -f`: Output format (`yaml`, `json`, `env`)

Examples:
```bash
# Show all configuration
mcp-config show

# Show specific value
mcp-config show openai.api_key

# Show as JSON
mcp-config show --format json
```

### `import-legacy`
Import configuration from legacy `.env` and `mcp-config.json` files.

```bash
mcp-config import-legacy [--env PATH] [--mcp-config PATH] [--force]
```

Options:
- `--env, -e`: Path to legacy .env file (default: `.env`)
- `--mcp-config, -m`: Path to legacy mcp-config.json
- `--force, -f`: Overwrite existing files

## Configuration Structure

### MCP Server Settings

```yaml
mcp:
  host: 127.0.0.1          # Server bind address
  port: 8000               # Server port
  context_percentage: 0.85 # Use 85% of model's context window
  default_temperature: 0.2 # Default AI temperature
```

### Logging

```yaml
logging:
  level: INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### Provider Configuration

```yaml
providers:
  openai:
    enabled: true
    api_key: sk-...  # Usually in secrets.yaml
  
  vertex:
    enabled: true
    project: my-project
    location: us-central1
    # OAuth config for CI/CD (usually in secrets.yaml):
    oauth_client_id: ""     # For refresh token auth
    oauth_client_secret: "" # For refresh token auth
    user_refresh_token: ""  # For refresh token auth
  
  anthropic:
    enabled: false
    api_key: claude-...  # Usually in secrets.yaml
```

### Session Management

```yaml
session:
  ttl_seconds: 3600           # Session timeout (1 hour)
  db_path: .mcp_sessions.sqlite3
  cleanup_probability: 0.01   # 1% chance to cleanup expired sessions
```

### Memory System

```yaml
memory:
  enabled: true
  rollover_limit: 9500        # Items before creating new vector store
  session_cutoff_hours: 2     # Hours to look back for related sessions
  summary_char_limit: 200000  # Max characters for summaries
  max_files_per_commit: 50    # Max files to list in commit summaries
```

## Environment Variable Names

All configuration values can be overridden using environment variables:

| Config Path | Environment Variable |
|------------|---------------------|
| `mcp.host` | `HOST` |
| `mcp.port` | `PORT` |
| `mcp.context_percentage` | `CONTEXT_PERCENTAGE` |
| `mcp.default_temperature` | `DEFAULT_TEMPERATURE` |
| `logging.level` | `LOG_LEVEL` |
| `providers.openai.api_key` | `OPENAI_API_KEY` |
| `providers.vertex.project` | `VERTEX_PROJECT` |
| `providers.vertex.location` | `VERTEX_LOCATION` |
| `providers.vertex.oauth_client_id` | `GCLOUD_OAUTH_CLIENT_ID` |
| `providers.vertex.oauth_client_secret` | `GCLOUD_OAUTH_CLIENT_SECRET` |
| `providers.vertex.user_refresh_token` | `GCLOUD_USER_REFRESH_TOKEN` |
| `providers.anthropic.api_key` | `ANTHROPIC_API_KEY` |
| `session.ttl_seconds` | `SESSION_TTL_SECONDS` |
| `session.db_path` | `SESSION_DB_PATH` |
| `session.cleanup_probability` | `SESSION_CLEANUP_PROBABILITY` |
| `memory.enabled` | `MEMORY_ENABLED` |
| `memory.rollover_limit` | `MEMORY_ROLLOVER_LIMIT` |
| `memory.session_cutoff_hours` | `MEMORY_SESSION_CUTOFF_HOURS` |
| `memory.summary_char_limit` | `MEMORY_SUMMARY_CHAR_LIMIT` |
| `memory.max_files_per_commit` | `MEMORY_MAX_FILES_PER_COMMIT` |
| `adapter_mock` | `MCP_ADAPTER_MOCK` |

You can also use nested environment variables with `__` delimiter:
- `OPENAI__API_KEY` → `providers.openai.api_key`
- `VERTEX__PROJECT` → `providers.vertex.project`

## Migration from Legacy Configuration

If you're upgrading from an older version that uses `.env` files:

1. **Automatic Import**:
   ```bash
   mcp-config import-legacy
   ```

2. **Manual Migration**:
   - Copy non-sensitive values from `.env` to `config.yaml`
   - Copy API keys and secrets from `.env` to `secrets.yaml`
   - Delete or rename old `.env` file

3. **Verify Migration**:
   ```bash
   mcp-config validate
   mcp-config show
   ```

## Security Best Practices

1. **Separate Secrets**: Keep API keys in `secrets.yaml`, never in `config.yaml`
2. **Git Ignore**: Ensure `secrets.yaml` is in `.gitignore`
3. **File Permissions**: `secrets.yaml` is created with mode 600 (owner read/write only)
4. **Production**: Use environment variables or secret management systems in production

## Docker and CI/CD

### Docker
```dockerfile
# Generate .env from config files
RUN mcp-config export-env

# Or use environment variables directly
ENV OPENAI_API_KEY=${OPENAI_API_KEY}
```

### GitHub Actions
```yaml
- name: Configure MCP
  run: |
    mcp-config init
    # Use GitHub secrets
    echo "providers:" > secrets.yaml
    echo "  openai:" >> secrets.yaml
    echo "    api_key: ${{ secrets.OPENAI_API_KEY }}" >> secrets.yaml
```

### Claude Code Integration

Generate the MCP client configuration:

```bash
mcp-config export-client
```

This creates `mcp-config.json` that Claude Code can use to connect to your server.

## Troubleshooting

### Configuration Not Loading

1. Check file paths:
   ```bash
   ls -la config.yaml secrets.yaml
   ```

2. Validate syntax:
   ```bash
   mcp-config validate
   ```

3. Check environment variables:
   ```bash
   env | grep -E "(OPENAI|VERTEX|MCP)"
   ```

### API Keys Not Working

1. Ensure secrets.yaml has correct permissions:
   ```bash
   chmod 600 secrets.yaml
   ```

2. Verify keys are loaded:
   ```bash
   mcp-config show openai.api_key
   ```

### Legacy .env Still Being Used

The system loads configuration in this order:
1. Default values
2. `.env` file (if exists)
3. YAML files (`config.yaml`, `secrets.yaml`)
4. Environment variables

To ensure YAML files are used:
1. Remove or rename `.env`
2. Or set `MCP_CONFIG_FILE` and `MCP_SECRETS_FILE` environment variables