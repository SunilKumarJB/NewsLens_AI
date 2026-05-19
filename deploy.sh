#!/bin/bash

# Exit immediately if any command fails
set -e

# Define service parameters
SERVICE_NAME="newslens-portal"
DEFAULT_REGION="us-central1"

# Color formatting for premium terminal output
BOLD_BLUE="\033[1;34m"
BOLD_GREEN="\033[1;32m"
BOLD_RED="\033[1;31m"
BOLD_YELLOW="\033[1;33m"
RESET="\033[0m"

echo -e "${BOLD_BLUE}=======================================================${RESET}"
echo -e "${BOLD_BLUE}🏛️  NewsLens AI - Google Cloud Run Deployment Assistant${RESET}"
echo -e "${BOLD_BLUE}=======================================================${RESET}"

# 1. Verification: Check if gcloud CLI is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${BOLD_RED}Error: Google Cloud SDK (gcloud) is not installed.${RESET}"
    echo -e "Please install it from https://cloud.google.com/sdk/docs and authenticate first."
    exit 1
fi

# 2. Verify active authentication
echo -e "\n${BOLD_YELLOW}[1/4] Verifying Google Cloud Authentication...${RESET}"
ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)")

if [ -z "$ACTIVE_ACCOUNT" ]; then
    echo -e "${BOLD_RED}Error: No active Google Cloud account detected.${RESET}"
    echo -e "Please run 'gcloud auth login' to authenticate and run this script again."
    exit 1
else
    echo -e "${BOLD_GREEN}✔ Authenticated as: $ACTIVE_ACCOUNT${RESET}"
fi

# 3. Determine Target GCP Project
echo -e "\n${BOLD_YELLOW}[2/4] Fetching Google Cloud Project...${RESET}"
PROJECT_ID=$(gcloud config get-value project 2>/dev/null || true)

if [ -z "$PROJECT_ID" ]; then
    echo -e "${BOLD_YELLOW}No default GCP project configured in gcloud.${RESET}"
    read -p "Enter your GCP Project ID: " PROJECT_ID
fi

if [ -z "$PROJECT_ID" ]; then
    echo -e "${BOLD_RED}Error: Target GCP Project ID is required for deployment.${RESET}"
    exit 1
else
    echo -e "${BOLD_GREEN}✔ Target Project ID: $PROJECT_ID${RESET}"
fi

# Set target region
REGION=$DEFAULT_REGION
echo -e "${BOLD_GREEN}✔ Deployment Region: $REGION${RESET}"

# 4. Submit Container Image via Cloud Build
IMAGE_TAG="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest"

echo -e "\n${BOLD_YELLOW}[3/4] Submitting Build to Google Cloud Build...${RESET}"
echo -e "Building and tagging container image as: ${IMAGE_TAG}"
echo -e "This may take a moment. Press Ctrl+C at any time to cancel.\n"

gcloud builds submit --tag "$IMAGE_TAG" --project "$PROJECT_ID"

echo -e "\n${BOLD_GREEN}✔ Container built and pushed to Google Container Registry successfully!${RESET}"

# 5. Deploy Container Image to Cloud Run
echo -e "\n${BOLD_YELLOW}[4/4] Deploying Container Image to Google Cloud Run...${RESET}"
echo -e "Service Name: ${SERVICE_NAME}"
echo -e "Region: ${REGION}"

gcloud run deploy "$SERVICE_NAME" \
    --image "$IMAGE_TAG" \
    --platform managed \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --allow-unauthenticated \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=global,EXTRACTION_MODEL=gemini-3.1-pro-preview,EMBEDDING_MODEL=gemini-embedding-2"

# 6. Successful completion report
echo -e "\n${BOLD_GREEN}=======================================================${RESET}"
echo -e "${BOLD_GREEN}🎉 NewsLens AI Portal Deployed Successfully to Cloud Run!${RESET}"
echo -e "${BOLD_GREEN}=======================================================${RESET}"

# Get the Cloud Run URL
RUN_URL=$(gcloud run services describe "$SERVICE_NAME" --platform managed --region "$REGION" --project "$PROJECT_ID" --format="value(status.url)")

echo -e "\n👉 View your live application in browser at:"
echo -e "🔗 ${BOLD_BLUE}${RUN_URL}${RESET}\n"
