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

### 3. Google Cloud Authentication (Choose One)

#### Option A: Service Account (Recommended if you have permissions)
- **`GOOGLE_APPLICATION_CREDENTIALS_JSON`**
  - The contents of a service account JSON file
  - Required for: E2E tests with Gemini models
  - Get by running: `./scripts/create-gcp-service-account.sh`
  - Copy contents: `cat gcp-service-account-key.json | pbcopy`

#### Option B: User Refresh Token (If you can't create service accounts)
- **`GCLOUD_USER_REFRESH_TOKEN`**
  - Your Google Cloud refresh token
  - Get from: `~/.config/gcloud/application_default_credentials.json` after running `gcloud auth application-default login`
  - Required with: `GCLOUD_OAUTH_CLIENT_ID` and `GCLOUD_OAUTH_CLIENT_SECRET`

- **`GCLOUD_OAUTH_CLIENT_ID`** (Optional)
  - OAuth 2.0 client ID from Google Cloud Console
  - Get from: [APIs & Services > Credentials](https://console.cloud.google.com/apis/credentials)
  - If not provided, uses gcloud CLI's default client

- **`GCLOUD_OAUTH_CLIENT_SECRET`** (Optional)
  - OAuth 2.0 client secret
  - Get from: Same OAuth client in Google Cloud Console
  - If not provided, uses gcloud CLI's default client

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

3. **Google Cloud Credentials** (Choose one method):
   
   **Option A - Service Account**:
   ```bash
   # Run the script to create service account
   ./scripts/create-gcp-service-account.sh
   
   # Copy the JSON contents
   cat gcp-service-account-key.json | pbcopy
   
   # Add to GitHub secrets as GOOGLE_APPLICATION_CREDENTIALS_JSON
   ```
   
   **Option B - Refresh Token**:
   ```bash
   # Get your refresh token
   cat ~/.config/gcloud/application_default_credentials.json | jq -r .refresh_token
   
   # Add to GitHub secrets:
   # - GCLOUD_USER_REFRESH_TOKEN (the refresh token)
   # - GCLOUD_OAUTH_CLIENT_ID (optional, from Google Cloud Console)
   # - GCLOUD_OAUTH_CLIENT_SECRET (optional, from Google Cloud Console)
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