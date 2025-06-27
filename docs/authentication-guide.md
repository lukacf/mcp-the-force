# Google Cloud Authentication Guide

This guide explains how to authenticate with Google Cloud for using Gemini models in the MCP Second-Brain server.

## Authentication Methods

### Method 1: Service Account (Recommended for Production)

Service accounts provide the most secure and scalable authentication method.

**Setup Steps:**

1. Create a service account in your Google Cloud project:
   ```bash
   gcloud iam service-accounts create mcp-second-brain \
     --display-name="MCP Second Brain Service Account"
   ```

2. Grant the necessary permissions:
   ```bash
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:mcp-second-brain@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/aiplatform.user"
   ```

3. Create and download a key:
   ```bash
   gcloud iam service-accounts keys create ~/mcp-second-brain-key.json \
     --iam-account=mcp-second-brain@YOUR_PROJECT_ID.iam.gserviceaccount.com
   ```

4. Set the environment variable:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="$HOME/mcp-second-brain-key.json"
   ```

**Advantages:**
- No user interaction required
- Can be easily rotated
- Suitable for CI/CD environments
- Fine-grained permission control

**Disadvantages:**
- Requires Google Cloud project ownership
- Key file must be securely stored

### Method 2: Application Default Credentials (Recommended for Development)

Use your personal Google Cloud credentials via gcloud CLI.

**Setup Steps:**

1. Install gcloud CLI: https://cloud.google.com/sdk/docs/install

2. Authenticate:
   ```bash
   gcloud auth application-default login
   ```

3. The SDK will automatically use these credentials

**Advantages:**
- Simple setup for developers
- No key management required
- Uses existing gcloud authentication

**Disadvantages:**
- Requires gcloud CLI installation
- Not suitable for production or CI/CD
- Uses personal credentials

### Method 3: Workload Identity Federation (Recommended for GitHub Actions)

For GitHub Actions, use Workload Identity Federation to avoid storing credentials.

**Setup Steps:**

1. Create a Workload Identity Pool:
   ```bash
   gcloud iam workload-identity-pools create "github" \
     --location="global" \
     --display-name="GitHub Actions Pool"
   ```

2. Create a provider:
   ```bash
   gcloud iam workload-identity-pools providers create-oidc "github-provider" \
     --location="global" \
     --workload-identity-pool="github" \
     --issuer-uri="https://token.actions.githubusercontent.com" \
     --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository"
   ```

3. Grant permissions to your repository:
   ```bash
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/YOUR_GITHUB_ORG/YOUR_REPO" \
     --role="roles/aiplatform.user"
   ```

4. Use the Google Cloud auth action in your workflow:
   ```yaml
   - uses: google-github-actions/auth@v2
     with:
       workload_identity_provider: 'projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github-provider'
       service_account: 'mcp-second-brain@YOUR_PROJECT_ID.iam.gserviceaccount.com'
   ```

**Advantages:**
- No stored credentials
- Automatic rotation
- Secure by design
- GitHub-native integration

**Disadvantages:**
- Complex initial setup
- Requires Google Cloud project ownership

### Method 4: OAuth Refresh Tokens (For CI/CD Only)

This method is specifically for CI/CD environments (GitHub Actions, Docker) where:
- You cannot use interactive `gcloud auth` 
- You cannot create service accounts with required permissions
- You need to run E2E tests with real Vertex AI APIs

**When to Use:**
- GitHub Actions workflows
- Docker containers in CI/CD
- Automated testing environments
- When service account creation is not possible

**Setup:**

1. Use existing OAuth credentials (or obtain from gcloud CLI)
2. Obtain a refresh token via OAuth flow
3. Configure in `secrets.yaml`:
   ```yaml
   providers:
     vertex:
       oauth_client_id: "your-client-id"
       oauth_client_secret: "your-client-secret"
       user_refresh_token: "your-refresh-token"
   ```
   
   Or via environment variables:
   ```bash
   export GCLOUD_OAUTH_CLIENT_ID="your-client-id"
   export GCLOUD_OAUTH_CLIENT_SECRET="your-client-secret"
   export GCLOUD_USER_REFRESH_TOKEN="your-refresh-token"
   ```

**Security Notes:**
- Store these credentials as encrypted secrets in your CI/CD platform
- Never commit these values to version control
- Refresh tokens are user-specific and long-lived
- Consider token rotation policies

## Environment Variables

Required environment variables for Vertex AI:

```bash
# Google Cloud project configuration
VERTEX_PROJECT=your-project-id
VERTEX_LOCATION=us-central1  # or your preferred region

# Authentication (choose one method)
# Method 1: Service Account
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json

# Method 2: ADC (no variables needed if gcloud is configured)

# Method 3: Workload Identity (handled by GitHub Actions)

# Method 4: OAuth (not recommended)
GCLOUD_OAUTH_CLIENT_ID=your-client-id
GCLOUD_OAUTH_CLIENT_SECRET=your-client-secret
GCLOUD_USER_REFRESH_TOKEN=your-refresh-token
```

## Troubleshooting

### "Permission denied" errors
- Ensure the authenticated principal has the `Vertex AI User` role
- Check project ID and location are correct
- Verify billing is enabled for the project

### "Could not load the default credentials"
- Run `gcloud auth application-default login` for local development
- Check `GOOGLE_APPLICATION_CREDENTIALS` points to a valid file
- Ensure the SDK can find credentials in the standard locations

### Testing authentication
```bash
# Test with gcloud
gcloud auth application-default print-access-token

# Test with Python
python -c "from google.auth import default; print(default())"
```

## Security Best Practices

1. **Never commit credentials** to version control
2. **Use .gitignore** to exclude credential files
3. **Rotate service account keys** regularly
4. **Use least privilege** - only grant necessary permissions
5. **Monitor usage** via Google Cloud audit logs
6. **Use Workload Identity** for CI/CD when possible

## Getting OAuth Credentials for gcloud CLI

If you need the gcloud CLI's OAuth credentials for legacy compatibility:

1. These are publicly documented in gcloud's source code
2. Find them at: https://github.com/google-cloud-sdk/google-cloud-sdk
3. Search for `CLOUDSDK_CLIENT_ID` in the codebase

**Note**: Using gcloud's OAuth credentials is not recommended for production use.