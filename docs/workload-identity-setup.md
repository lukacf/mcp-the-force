# Workload Identity Federation Setup for GitHub Actions

This guide shows how to use Workload Identity Federation instead of storing Google Cloud credentials as GitHub secrets.

## Benefits
- No service account keys to rotate or leak
- Automatic credential management
- Fine-grained access control per repository/workflow
- Google Cloud audit logs show which GitHub workflow made each request

## Prerequisites
- Google Cloud project with billing enabled
- Permissions to create service accounts and workload identity pools

## Setup Steps

### 1. Create a Service Account
```bash
export PROJECT_ID="your-project-id"
export SERVICE_ACCOUNT="github-actions-sa"

gcloud iam service-accounts create $SERVICE_ACCOUNT \
  --display-name="GitHub Actions Service Account" \
  --project=$PROJECT_ID
```

### 2. Grant Vertex AI permissions
```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

### 3. Create Workload Identity Pool
```bash
export POOL_NAME="github-actions-pool"

gcloud iam workload-identity-pools create $POOL_NAME \
  --location="global" \
  --display-name="GitHub Actions Pool" \
  --project=$PROJECT_ID
```

### 4. Create Workload Identity Provider
```bash
export PROVIDER_NAME="github-provider"
export REPO_OWNER="your-github-username"
export REPO_NAME="mcp-second-brain"

gcloud iam workload-identity-pools providers create-oidc $PROVIDER_NAME \
  --location="global" \
  --workload-identity-pool=$POOL_NAME \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner == '$REPO_OWNER'" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --project=$PROJECT_ID
```

### 5. Grant the Service Account permissions
```bash
gcloud iam service-accounts add-iam-policy-binding \
  $SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL_NAME/attribute.repository/$REPO_OWNER/$REPO_NAME" \
  --project=$PROJECT_ID
```

### 6. Update GitHub Actions workflow

```yaml
name: E2E Tests with Workload Identity

on:
  push:
    branches: [main]

# Required for OIDC token
permissions:
  contents: read
  id-token: write

jobs:
  e2e-tests:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - id: auth
      uses: google-github-actions/auth@v2
      with:
        workload_identity_provider: 'projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions-pool/providers/github-provider'
        service_account: 'github-actions-sa@PROJECT_ID.iam.gserviceaccount.com'
        
    - name: Set up Cloud SDK
      uses: google-github-actions/setup-gcloud@v2
      
    - name: Build and run E2E tests
      env:
        OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        VERTEX_PROJECT: ${{ vars.VERTEX_PROJECT }}
        VERTEX_LOCATION: ${{ vars.VERTEX_LOCATION }}
      run: |
        docker build -f Dockerfile.e2e -t mcp-e2e:latest .
        docker run --rm \
          -e OPENAI_API_KEY \
          -e ANTHROPIC_API_KEY \
          -e VERTEX_PROJECT \
          -e VERTEX_LOCATION \
          -e GOOGLE_APPLICATION_CREDENTIALS \
          -v $GOOGLE_APPLICATION_CREDENTIALS:$GOOGLE_APPLICATION_CREDENTIALS:ro \
          mcp-e2e:latest
```

## Security Notes

1. The `attribute-condition` ensures only your repository can use these credentials
2. You can further restrict by branch, environment, or specific workflows
3. Credentials are temporary and automatically rotated
4. No long-lived secrets are stored in GitHub

## Troubleshooting

### "Permission denied" errors
- Check the service account has the correct Vertex AI permissions
- Verify the workload identity binding is correct
- Ensure the repository name matches exactly

### "Invalid OIDC token" errors  
- Check that `id-token: write` permission is set in the workflow
- Verify the issuer URI is correct
- Ensure you're using the correct project number (not project ID)

## Additional Resources
- [Google Cloud Workload Identity Federation docs](https://cloud.google.com/iam/docs/workload-identity-federation)
- [GitHub OIDC token docs](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)