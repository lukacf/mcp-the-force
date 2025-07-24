#!/bin/bash
# Script to create a GCP service account for E2E testing

PROJECT_ID="${1:-$(gcloud config get-value project)}"
SERVICE_ACCOUNT_NAME="mcp-the-force-e2e"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
KEY_FILE="gcp-service-account-key.json"

echo "Creating service account for project: $PROJECT_ID"

# Create service account
echo "Creating service account: $SERVICE_ACCOUNT_NAME"
gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
    --display-name="MCP The Force E2E Testing" \
    --description="Service account for MCP The Force E2E tests" \
    --project=$PROJECT_ID || echo "Service account might already exist"

# Grant necessary roles
echo "Granting Vertex AI User role..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/aiplatform.user" \
    --condition=None

echo "Granting Storage Object Viewer role (for vector stores)..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/storage.objectViewer" \
    --condition=None

# Create key
echo "Creating service account key..."
gcloud iam service-accounts keys create $KEY_FILE \
    --iam-account=$SERVICE_ACCOUNT_EMAIL \
    --project=$PROJECT_ID

echo ""
echo "Service account created successfully!"
echo "Key saved to: $KEY_FILE"
echo ""
echo "To add this to GitHub secrets:"
echo "1. Go to your GitHub repository settings"
echo "2. Navigate to Secrets and variables > Actions"
echo "3. Create a new secret named GOOGLE_APPLICATION_CREDENTIALS_JSON"
echo "4. Copy the contents of $KEY_FILE as the secret value:"
echo ""
echo "cat $KEY_FILE | pbcopy  # (on macOS)"
echo ""
echo "IMPORTANT: Keep this key file secure and do not commit it to git!"
echo "Add $KEY_FILE to .gitignore"