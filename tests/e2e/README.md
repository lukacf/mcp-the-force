# E2E Testing

This directory contains end-to-end tests that use Claude Code to test the MCP Second-Brain server in a realistic environment.

## Prerequisites

1. **API Keys**: Set the following environment variables:
   ```bash
   export OPENAI_API_KEY="your-openai-key"
   export ANTHROPIC_API_KEY="your-anthropic-key"
   export VERTEX_PROJECT="your-gcp-project"
   export VERTEX_LOCATION="us-central1"  # or your preferred location
   ```

2. **Google Cloud Authentication**: 
   ```bash
   gcloud auth application-default login
   ```
   This creates credentials at `~/.config/gcloud/application_default_credentials.json`

## Running Tests Locally

Use the provided script:
```bash
chmod +x tests/e2e/run-e2e-tests.sh
./tests/e2e/run-e2e-tests.sh
```

Or run manually:
```bash
# Build the Docker image
docker build -f Dockerfile.e2e -t mcp-e2e-test .

# Run tests with credentials mounted
docker run --rm \
  -e CI_E2E=1 \
  -e OPENAI_API_KEY="${OPENAI_API_KEY}" \
  -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
  -e VERTEX_PROJECT="${VERTEX_PROJECT}" \
  -e VERTEX_LOCATION="${VERTEX_LOCATION}" \
  -e GOOGLE_APPLICATION_CREDENTIALS="/tmp/gcloud/application_default_credentials.json" \
  -v "$HOME/.config/gcloud/application_default_credentials.json:/tmp/gcloud/application_default_credentials.json:ro" \
  mcp-e2e-test pytest tests/e2e -v
```

## CI/CD Setup

For GitHub Actions, add these secrets:
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `VERTEX_PROJECT`
- `VERTEX_LOCATION`
- `GOOGLE_APPLICATION_CREDENTIALS_JSON` - The contents of a service account JSON file

## Test Structure

- `test_smoke.py` - Basic tests to verify the MCP server is working
- `test_scenarios.py` - More complex scenarios including vector stores and model comparisons
- `conftest.py` - Pytest fixtures for Claude Code integration

## Writing E2E Tests

E2E tests should:
1. Use structured output formats to make assertions reliable
2. Test real functionality without mocks
3. Be cost-conscious (avoid expensive models for simple tests)

Example:
```python
def test_something(claude_code):
    output = claude_code(
        'Use second-brain tool_name with parameters. '
        'If successful, output "SUCCESS: <result>". '
        'If failed, output "FAILED: <reason>".'
    )
    assert "SUCCESS:" in output
```