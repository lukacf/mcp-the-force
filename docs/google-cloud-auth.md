# Google Cloud Authentication Guide

This guide explains how to authenticate with Google Cloud for using Gemini models in MCP Second-Brain.

## Authentication Methods

### 1. Application Default Credentials (Recommended for Development)

The simplest method for local development:

```bash
# Login with your Google account
gcloud auth application-default login

# The server will automatically find your credentials
```

**Pros:**
- Simple one-time setup
- No credential management
- Works with your existing Google Cloud access

**Cons:**
- Only for local development
- Not suitable for CI/CD or production

### 2. Service Account (Recommended for Production)

For production deployments and CI/CD:

```bash
# Create service account (requires appropriate permissions)
gcloud iam service-accounts create mcp-second-brain \
  --display-name="MCP Second Brain Service Account"

# Grant Vertex AI permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:mcp-second-brain@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

# Create and download key
gcloud iam service-accounts keys create key.json \
  --iam-account=mcp-second-brain@YOUR_PROJECT_ID.iam.gserviceaccount.com

# Set environment variable
export GOOGLE_APPLICATION_CREDENTIALS="path/to/key.json"
```

### 3. User Refresh Token (Alternative for CI/CD)

If you cannot create service accounts with Vertex AI permissions:

1. **Create OAuth 2.0 Client ID** in Google Cloud Console:
   - Go to [APIs & Services > Credentials](https://console.cloud.google.com/apis/credentials)
   - Click "Create Credentials" > "OAuth client ID"
   - Choose "Desktop app" as application type
   - Download the client configuration

2. **Get refresh token**:
   ```bash
   # Install gcloud if not already installed
   gcloud auth application-default login
   
   # Your refresh token is in:
   cat ~/.config/gcloud/application_default_credentials.json
   ```

3. **Set environment variables**:
   ```bash
   export GCLOUD_USER_REFRESH_TOKEN="your-refresh-token"
   export GCLOUD_OAUTH_CLIENT_ID="your-client-id"
   export GCLOUD_OAUTH_CLIENT_SECRET="your-client-secret"
   ```

**Important:** Never commit refresh tokens or client secrets to version control!

## Environment Variables

Required for all Gemini models:
- `VERTEX_PROJECT`: Your Google Cloud project ID
- `VERTEX_LOCATION`: Region for Vertex AI (e.g., `us-central1`)

Plus one of:
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to service account key file
- Application Default Credentials (via `gcloud auth`)
- Refresh token setup (all three variables required):
  - `GCLOUD_USER_REFRESH_TOKEN`
  - `GCLOUD_OAUTH_CLIENT_ID`
  - `GCLOUD_OAUTH_CLIENT_SECRET`

## Troubleshooting

### "Could not automatically determine credentials"
- Run `gcloud auth application-default login`
- Or set `GOOGLE_APPLICATION_CREDENTIALS` to point to a service account key

### "Permission denied" or "403 Forbidden"
- Ensure your account/service account has Vertex AI User role
- Check that `VERTEX_PROJECT` is correct and you have access to it

### "Invalid refresh token"
- Refresh tokens expire after 6 months of non-use
- Re-run `gcloud auth application-default login` to get a new one

## Security Best Practices

1. **Never commit credentials** to version control
2. **Use service accounts** for production deployments
3. **Rotate credentials** regularly
4. **Limit permissions** to only what's needed (Vertex AI User role)
5. **Use Secret Management** services for production deployments

## GitHub Actions Setup

See `.github/workflows/e2e.yml` for an example. Store credentials as GitHub Secrets:
- For service account: Store the JSON key as `GOOGLE_APPLICATION_CREDENTIALS_JSON`
- For refresh token: Store `GCLOUD_USER_REFRESH_TOKEN`, `GCLOUD_OAUTH_CLIENT_ID`, and `GCLOUD_OAUTH_CLIENT_SECRET`