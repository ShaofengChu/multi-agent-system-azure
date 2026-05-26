#!/bin/bash
set -euo pipefail

# ============================================================
# Azure Container Apps Deployment Script
# Deploys: MCP Server, HR Agent, IT Agent
# Idempotent: safe to re-run after a partial or failed run.
# ============================================================

# --- Configuration ---
RESOURCE_GROUP="azure-openai"
LOCATION="japaneast"
ENVIRONMENT_NAME="multi-agent-env"
ACR_NAME="multiagentsystemacr"

# Ensure required env vars are set
: "${AZURE_OPENAI_ENDPOINT:?Set AZURE_OPENAI_ENDPOINT}"
: "${AZURE_OPENAI_API_KEY:?Set AZURE_OPENAI_API_KEY}"
AZURE_OPENAI_API_VERSION="${AZURE_OPENAI_API_VERSION:-2024-12-01-preview}"
AZURE_OPENAI_DEPLOYMENT_NAME="${AZURE_OPENAI_DEPLOYMENT_NAME:-gpt-5-mini}"

echo "📦 Resource Group : $RESOURCE_GROUP"
echo "🌏 Location       : $LOCATION"
echo "🔧 Environment    : $ENVIRONMENT_NAME"

# --- Helper: create or update a Container App ---
# Usage: deploy_app <app-name> <image> <ingress-type> <env-vars...>
deploy_containerapp() {
    local APP_NAME="$1"
    local IMAGE="$2"
    local INGRESS="$3"
    shift 3
    local ENV_VARS=("$@")

    APP_EXISTS=$(az containerapp show \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "name" -o tsv 2>/dev/null || echo "")

    if [ -z "$APP_EXISTS" ]; then
        echo "   Creating $APP_NAME..."
        az containerapp create \
            --name "$APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --environment "$ENVIRONMENT_NAME" \
            --image "$IMAGE" \
            --registry-server "$ACR_LOGIN_SERVER" \
            --registry-username "$ACR_NAME" \
            --registry-password "$ACR_PASSWORD" \
            --target-port 8080 \
            --ingress "$INGRESS" \
            --min-replicas 1 \
            --env-vars "${ENV_VARS[@]}"
    else
        echo "   Updating $APP_NAME..."
        az containerapp update \
            --name "$APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --image "$IMAGE" \
            --set-env-vars "${ENV_VARS[@]}"
    fi
}

# --- Step 0: Ensure Azure CLI extensions ---
az extension add --name containerapp --upgrade --yes 2>/dev/null || true

# --- Step 1: Create ACR (if needed) ---
echo ""
echo "▶ 0/3 Ensuring Azure Container Registry..."
ACR_EXISTS=$(az acr list \
    --resource-group "$RESOURCE_GROUP" \
    --query "[0].name" -o tsv 2>/dev/null || echo "")

if [ -n "$ACR_EXISTS" ]; then
    ACR_NAME="$ACR_EXISTS"
    echo "   Using existing ACR: $ACR_NAME"
else
    az acr create \
        --resource-group "$RESOURCE_GROUP" \
        --name "$ACR_NAME" \
        --sku Basic \
        --admin-enabled true \
        --location "$LOCATION"
    echo "   Created ACR: $ACR_NAME"
fi

ACR_LOGIN_SERVER=$(az acr show \
    --resource-group "$RESOURCE_GROUP" \
    --name "$ACR_NAME" \
    --query "loginServer" -o tsv)

# Retrieve password into a variable to avoid exposing it in process arguments.
# Note: for production, prefer managed identity over admin credentials.
ACR_PASSWORD=$(az acr credential show \
    --resource-group "$RESOURCE_GROUP" \
    --name "$ACR_NAME" \
    --query "passwords[0].value" -o tsv)

# --- Step 2: Create Container Apps Environment (if needed) ---
echo ""
echo "▶ Ensuring Container Apps Environment..."
ENV_EXISTS=$(az containerapp env show \
    --name "$ENVIRONMENT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "name" -o tsv 2>/dev/null || echo "")

if [ -z "$ENV_EXISTS" ]; then
    az containerapp env create \
        --name "$ENVIRONMENT_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION"
    echo "   Created environment: $ENVIRONMENT_NAME"
else
    echo "   Using existing environment: $ENVIRONMENT_NAME"
fi

# --- Step 3: Build and Push Docker Images ---
echo ""
echo "▶ Building and pushing Docker images to ACR..."

az acr build --registry "$ACR_NAME" --resource-group "$RESOURCE_GROUP" \
    --image mcp-server:latest --file ./mcp_server/Dockerfile ./mcp_server

az acr build --registry "$ACR_NAME" --resource-group "$RESOURCE_GROUP" \
    --image hr-agent:latest --file ./hr_agent/Dockerfile ./hr_agent

az acr build --registry "$ACR_NAME" --resource-group "$RESOURCE_GROUP" \
    --image it-agent:latest --file ./it_agent/Dockerfile ./it_agent

# --- Step 4: Deploy MCP Server ---
echo ""
echo "▶ 1/3 Deploying MCP Server..."
deploy_containerapp "mcp-server" \
    "${ACR_LOGIN_SERVER}/mcp-server:latest" \
    "external" \
    "PORT=8080"

MCP_FQDN=$(az containerapp show \
    --name mcp-server \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.configuration.ingress.fqdn" -o tsv)

# Abort early if the FQDN could not be retrieved, to avoid deploying agents
# with a silently broken MCP_SERVER_URL.
: "${MCP_FQDN:?Failed to retrieve MCP Server FQDN. Check the mcp-server deployment.}"

MCP_URL="https://${MCP_FQDN}/mcp"
echo "   MCP URL: $MCP_URL"

# --- Step 5: Deploy HR Agent ---
echo ""
echo "▶ 2/3 Deploying HR Agent..."
deploy_containerapp "hr-agent" \
    "${ACR_LOGIN_SERVER}/hr-agent:latest" \
    "external" \
    "MCP_SERVER_URL=${MCP_URL}" \
    "AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}" \
    "AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY}" \
    "AZURE_OPENAI_API_VERSION=${AZURE_OPENAI_API_VERSION}" \
    "AZURE_OPENAI_DEPLOYMENT_NAME=${AZURE_OPENAI_DEPLOYMENT_NAME}"

HR_FQDN=$(az containerapp show \
    --name hr-agent \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.configuration.ingress.fqdn" -o tsv)

# --- Step 6: Deploy IT Agent ---
echo ""
echo "▶ 3/3 Deploying IT Agent..."
deploy_containerapp "it-agent" \
    "${ACR_LOGIN_SERVER}/it-agent:latest" \
    "external" \
    "MCP_SERVER_URL=${MCP_URL}" \
    "AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}" \
    "AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY}" \
    "AZURE_OPENAI_API_VERSION=${AZURE_OPENAI_API_VERSION}" \
    "AZURE_OPENAI_DEPLOYMENT_NAME=${AZURE_OPENAI_DEPLOYMENT_NAME}"

IT_FQDN=$(az containerapp show \
    --name it-agent \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.configuration.ingress.fqdn" -o tsv)

# --- Done ---
echo ""
echo "✅ Deployment completed!"
echo ""
echo "📋 Service URLs:"
echo "   MCP Server (internal): $MCP_URL"
echo "   HR Agent:  https://${HR_FQDN}"
echo "   IT Agent:  https://${IT_FQDN}"
echo ""
echo "🔗 Update agent card URLs in hr_agent/main.py and it_agent/main.py with the URLs above."