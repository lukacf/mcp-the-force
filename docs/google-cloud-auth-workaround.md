# Google Cloud Authentication Workaround for E2E Tests

## Problem
The default Compute Engine service account lacks Vertex AI permissions, and we can't modify IAM policies.

## Solution: Use Personal User Credentials

Instead of a service account, we use Application Default Credentials (ADC) with a user refresh token.

### Setup Steps

1. **Get your refresh token** (already done):
   ```bash
   cat ~/.config/gcloud/application_default_credentials.json | jq -r .refresh_token
   ```

2. **Add to GitHub Secrets**:
   - Name: `GCLOUD_USER_REFRESH_TOKEN`
   - Value: Your refresh token

3. **How it works**:
   - E2E workflow checks for service account JSON first
   - Falls back to creating ADC file with user credentials
   - Uses the standard Google Cloud client ID/secret for gcloud CLI
   - Your personal account permissions are used for Vertex AI

### Security Notes
- Refresh tokens are long-lived but can be revoked
- Only gives access to Google Cloud APIs (not your Google account)
- Scoped to the project specified in environment variables
- Can be revoked with: `gcloud auth application-default revoke`

### Alternative: Service Account with Proper Permissions
If you later get a service account with proper permissions:
1. Remove `GCLOUD_USER_REFRESH_TOKEN` secret
2. Update `GOOGLE_APPLICATION_CREDENTIALS_JSON` with new service account JSON