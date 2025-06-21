# Google Cloud Authentication Setup for E2E Tests

## Overview

This document explains how to set up Google Cloud authentication for E2E tests using Application Default Credentials (ADC) without committing any sensitive information to the repository.

## For GitHub Actions

### Required Secrets

Add these secrets to your repository (Settings → Secrets → Actions):

1. **GCLOUD_USER_REFRESH_TOKEN** (required)
   - Get from your local gcloud setup: `cat ~/.config/gcloud/application_default_credentials.json | jq -r .refresh_token`
   - This allows the tests to use your personal Google account's Vertex AI permissions

2. **GCLOUD_OAUTH_CLIENT_ID** (optional)
   - Only needed if using a custom OAuth application
   - If not provided, uses gcloud CLI's public OAuth client

3. **GCLOUD_OAUTH_CLIENT_SECRET** (optional)
   - Only needed if using a custom OAuth application
   - If not provided, uses gcloud CLI's public OAuth secret

### How It Works

1. The workflow checks for service account credentials first
2. If not found, it uses the refresh token to create ADC
3. The `scripts/create-adc.sh` script builds the ADC JSON file at runtime
4. No OAuth credentials are stored in the repository

## For Local Development

### Setup Steps

1. **Copy the template**:
   ```bash
   cp .env.template .env
   ```

2. **Fill in your refresh token**:
   ```bash
   # Get your refresh token
   cat ~/.config/gcloud/application_default_credentials.json | jq -r .refresh_token
   
   # Add to .env file
   echo "GCLOUD_USER_REFRESH_TOKEN=your_refresh_token_here" >> .env
   ```

3. **Run tests with authentication**:
   ```bash
   # Source environment and create ADC
   source .env && source scripts/create-adc.sh
   
   # Run E2E tests
   ./tests/e2e/run-e2e-tests.sh
   ```

## Security Notes

- The `.env` file is gitignored and should NEVER be committed
- Refresh tokens are user-specific and grant access to Google Cloud APIs
- The default OAuth client ID/secret belong to gcloud CLI and are safe to use
- ADC files are created in temp directories and cleaned up after use

## Alternative: Service Account

If you obtain a service account with proper Vertex AI permissions:

1. Remove the `GCLOUD_USER_REFRESH_TOKEN` secret
2. Update `GOOGLE_APPLICATION_CREDENTIALS_JSON` with the service account JSON
3. The workflow will automatically prefer the service account over user credentials

## Troubleshooting

### "Permission denied" errors
- Ensure your Google account has Vertex AI User role in the project
- Verify the refresh token is still valid: `gcloud auth application-default print-access-token`

### Token expired
- Refresh your local credentials: `gcloud auth application-default login`
- Update the refresh token in GitHub secrets