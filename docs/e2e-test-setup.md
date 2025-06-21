# E2E Test Setup Documentation

## Overview

The E2E tests use Docker to run Claude Code CLI against the MCP Second-Brain server with real AI models. Tests are designed to validate end-to-end functionality from Claude Code through MCP protocol to actual model responses.

## GitHub Secrets Required

The following secrets must be configured in GitHub repository settings for E2E tests to work:

### Required Secrets

1. **OPENAI_API_KEY** (Required)
   - OpenAI API key with access to o3, o3-pro, and gpt-4.1 models
   - Used for testing OpenAI-based tools

2. **ANTHROPIC_API_KEY** (Required)
   - Anthropic API key for Claude Code CLI
   - Used by Claude Code to process test commands

3. **VERTEX_PROJECT** (Required)
   - Google Cloud project ID with Vertex AI enabled
   - Example: `my-gcp-project-123`

4. **VERTEX_LOCATION** (Required)
   - Google Cloud region for Vertex AI
   - Example: `us-central1`

5. **GOOGLE_APPLICATION_CREDENTIALS_JSON** (Optional but recommended)
   - Google Cloud service account credentials in JSON format
   - If not provided, tests requiring Gemini models will be skipped
   - To create:
     ```bash
     # Create service account
     gcloud iam service-accounts create mcp-e2e-tests \
       --display-name="MCP E2E Tests"
     
     # Grant Vertex AI User role
     gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
       --member="serviceAccount:mcp-e2e-tests@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
       --role="roles/aiplatform.user"
     
     # Create and download key
     gcloud iam service-accounts keys create key.json \
       --iam-account=mcp-e2e-tests@YOUR_PROJECT_ID.iam.gserviceaccount.com
     
     # Copy the contents of key.json to GitHub secret
     ```

## E2E Test Structure

### Test Files

- `tests/e2e/test_smoke.py` - Basic smoke tests (list models, simple queries)
- `tests/e2e/test_scenarios.py` - Complex scenarios (vector stores, model comparison)
- `tests/e2e/conftest.py` - Test configuration and Claude Code fixture

### Test Environment

- **Docker Image**: `Dockerfile.e2e` creates isolated test environment
- **Claude Code Version**: v0.1.9 (update `CLAUDE_VERSION` in Dockerfile as needed)
- **Timeout**: Default 180s per MCP call, configurable in claude-config.json

### Running E2E Tests

#### Locally with Application Default Credentials (ADC)

```bash
# First, authenticate with Google Cloud
gcloud auth application-default login

# Set required environment variables
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export VERTEX_PROJECT="your-project"
export VERTEX_LOCATION="us-central1"

# Run with ADC mounted from your host machine
./tests/e2e/run-local-docker.sh

# Note: If you encounter permission errors, make your ADC file readable:
chmod 644 ~/.config/gcloud/application_default_credentials.json
```

#### Locally with Service Account

```bash
# Set required environment variables
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export VERTEX_PROJECT="your-project"
export VERTEX_LOCATION="us-central1"
export GOOGLE_APPLICATION_CREDENTIALS_JSON="$(cat path/to/service-account-key.json)"
export CI_E2E=1  # Required to enable E2E tests

# Run with local script (includes Google Cloud auth check)
./tests/e2e/run-e2e-tests.sh

# Or run directly with Docker
docker build -f Dockerfile.e2e -t mcp-e2e:latest .
docker run --rm \
  -e CI_E2E=1 \
  -e OPENAI_API_KEY \
  -e ANTHROPIC_API_KEY \
  -e VERTEX_PROJECT \
  -e VERTEX_LOCATION \
  -e GOOGLE_APPLICATION_CREDENTIALS_JSON \
  mcp-e2e:latest
```

#### In CI

E2E tests run automatically on:
- Push to `main` branch
- Push to `feature/comprehensive-testing` branch (temporary)
- Nightly at 2 AM UTC
- Manual workflow dispatch

## Cost Considerations

E2E tests use real AI models and incur costs:
- **Gemini 2.5 Flash**: ~$0.001 per test (used for most tests)
- **GPT-4.1**: ~$0.01 per test
- **o3/o3-pro**: $0.10-1.00 per test (skipped by default)

Estimated cost per full E2E run: ~$0.05

## Troubleshooting

### Common Issues

1. **"CI_E2E not set"**: E2E tests are skipped unless `CI_E2E=1` is set
2. **"fixture 'claude_code' not found"**: Ensure you're running from the Docker container
3. **Authentication errors**: Check that all required secrets are properly set
4. **Timeouts**: Some models (especially o3-pro) can take 10-30 minutes to respond

### Debug Mode

To enable verbose logging:
```bash
docker run --rm \
  -e CI_E2E=1 \
  -e LOG_LEVEL=DEBUG \
  ... other env vars ... \
  mcp-e2e:latest pytest tests/e2e -v -s
```

## Maintenance

1. **Update Claude Code version**: Edit `CLAUDE_VERSION` in `Dockerfile.e2e`
2. **Add new tests**: Place in `tests/e2e/` and follow existing patterns
3. **Skip expensive tests**: Use `@pytest.mark.skip(reason="...")` decorator
4. **Adjust timeouts**: Update `timeoutMs` in `claude-config.json` or use `@pytest.mark.timeout()`