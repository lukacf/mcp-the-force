# GitHub Actions Secrets Setup

To run the CI/CD pipelines, you need to configure the following secrets in your GitHub repository.

## Required Secrets

Navigate to: Settings → Secrets and variables → Actions → New repository secret

### 1. API Keys

- **`OPENAI_API_KEY`**
  - Get from: https://platform.openai.com/api-keys
  - Required for: Integration tests, E2E tests
  - Used by: OpenAI models (o3, o3-pro, gpt-4.1)

- **`ANTHROPIC_API_KEY`**
  - Get from: https://console.anthropic.com/account/keys
  - Required for: E2E tests
  - Used by: Claude Code in E2E tests

### 2. Google Cloud Configuration

- **`VERTEX_PROJECT`**
  - Your Google Cloud project ID (e.g., `my-project-123`)
  - Required for: Integration tests, E2E tests
  - Used by: Gemini models

- **`VERTEX_LOCATION`**
  - Google Cloud region (e.g., `us-central1`)
  - Required for: Integration tests, E2E tests
  - Used by: Gemini models

- **`GOOGLE_APPLICATION_CREDENTIALS_JSON`**
  - The contents of a service account JSON file
  - Required for: E2E tests with Gemini models
  - Get by running: `./scripts/create-gcp-service-account.sh`
  - Copy contents: `cat gcp-service-account-key.json | pbcopy`

## Setting Up Secrets

1. **OpenAI API Key**:
   ```bash
   # Add to GitHub secrets as OPENAI_API_KEY
   # Get from https://platform.openai.com/api-keys
   ```

2. **Anthropic API Key**:
   ```bash
   # Add to GitHub secrets as ANTHROPIC_API_KEY
   # Get from https://console.anthropic.com/account/keys
   ```

3. **Google Cloud Credentials**:
   ```bash
   # Run the script to create service account
   ./scripts/create-gcp-service-account.sh
   
   # Copy the JSON contents
   cat gcp-service-account-key.json | pbcopy
   
   # Add to GitHub secrets as GOOGLE_APPLICATION_CREDENTIALS_JSON
   ```

4. **Vertex AI Settings**:
   ```bash
   # Add your project ID as VERTEX_PROJECT
   # Add your preferred location as VERTEX_LOCATION (e.g., us-central1)
   ```

## Testing Secrets

To verify your secrets are working:

1. Go to Actions tab
2. Run the "E2E Tests" workflow manually
3. Check the logs for any authentication errors

## Security Notes

- Never commit API keys or service account files to the repository
- Rotate keys regularly
- Use repository environments to restrict secret access to specific branches
- Enable secret scanning in your repository settings

## Workflow Usage

The secrets are used in different workflows:

- **CI Tests** (on every push):
  - Uses mock adapters for integration tests
  - No API keys required

- **E2E Tests** (nightly or manual):
  - Uses all secrets for real API calls
  - Tests actual model responses

## Troubleshooting

If you see authentication errors:

1. **OpenAI**: Check if the API key has sufficient credits
2. **Anthropic**: Verify the API key is active
3. **Google Cloud**: Ensure the service account has the necessary roles:
   - `roles/aiplatform.user` - For Vertex AI
   - `roles/storage.objectViewer` - For vector stores (optional)