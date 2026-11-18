#!/bin/bash
# Cloud Deployment には下記環境変数を設定してください。
# export AZURE_OPENAI_ENDPOINT=
# export AZURE_OPENAI_API_KEY=
# export AZURE_OPENAI_API_VERSION=
# export AZURE_OPENAI_DEPLOYMENT_NAME=

set -euo pipefail

# ============================================================
# Azure Container Apps Deployment Script
# Deploys:
#   - Internal only: MCP Server, HR Agent, IT Agent
#   - External only: Main Agent (A2A Orchestrator)
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
# Usage: deploy_containerapp <app-name> <image> <ingress-type> <target-port> <env-vars...>
deploy_containerapp() {
    local APP_NAME="$1"
    local IMAGE="$2"
    local INGRESS="$3"
    local TARGET_PORT="$4"
    shift 4
    local ENV_VARS=("$@")

    APP_EXISTS=$(az containerapp show \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "name" -o tsv 2>/dev/null || echo "")

    if [ -z "$APP_EXISTS" ]; then
        echo "   Creating $APP_NAME (ingress=$INGRESS, target-port=$TARGET_PORT)..."
        az containerapp create \
            --name "$APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --environment "$ENVIRONMENT_NAME" \
            --image "$IMAGE" \
            --registry-server "$ACR_LOGIN_SERVER" \
            --registry-username "$ACR_NAME" \
            --registry-password "$ACR_PASSWORD" \
            --target-port "$TARGET_PORT" \
            --ingress "$INGRESS" \
            --min-replicas 1 \
            --env-vars "${ENV_VARS[@]}"
    else
        echo "   Updating $APP_NAME (ingress=$INGRESS, target-port=$TARGET_PORT)..."
        az containerapp ingress enable \
            --name "$APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --type "$INGRESS" \
            --target-port "$TARGET_PORT"
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
echo "▶ Ensuring Azure Container Registry..."
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

az acr build --registry "$ACR_NAME" --resource-group "$RESOURCE_GROUP" \
    --image main-agent:latest --file ./main_agent/Dockerfile ./main_agent

# --- Step 4: Deploy MCP Server (Internal Ingress) ---
echo ""
echo "▶ 1/4 Deploying MCP Server (internal)..."
deploy_containerapp "mcp-server" \
    "${ACR_LOGIN_SERVER}/mcp-server:latest" \
    "internal" \
    "8080" \
    "PORT=8080"

MCP_URL="http://mcp-server/mcp"
echo "   MCP Internal URL: $MCP_URL"

# --- Step 5: Deploy HR Agent (Internal Ingress) ---
echo ""
echo "▶ 2/4 Deploying HR Agent (internal)..."
HR_INTERNAL_URL="http://hr-agent"
deploy_containerapp "hr-agent" \
    "${ACR_LOGIN_SERVER}/hr-agent:latest" \
    "internal" \
    "8080" \
    "MCP_SERVER_URL=${MCP_URL}" \
    "AGENT_URL=${HR_INTERNAL_URL}" \
    "AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}" \
    "AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY}" \
    "AZURE_OPENAI_API_VERSION=${AZURE_OPENAI_API_VERSION}" \
    "AZURE_OPENAI_DEPLOYMENT_NAME=${AZURE_OPENAI_DEPLOYMENT_NAME}"

# --- Step 6: Deploy IT Agent (Internal Ingress) ---
echo ""
echo "▶ 3/4 Deploying IT Agent (internal)..."
IT_INTERNAL_URL="http://it-agent"
deploy_containerapp "it-agent" \
    "${ACR_LOGIN_SERVER}/it-agent:latest" \
    "internal" \
    "8080" \
    "MCP_SERVER_URL=${MCP_URL}" \
    "AGENT_URL=${IT_INTERNAL_URL}" \
    "AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}" \
    "AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY}" \
    "AZURE_OPENAI_API_VERSION=${AZURE_OPENAI_API_VERSION}" \
    "AZURE_OPENAI_DEPLOYMENT_NAME=${AZURE_OPENAI_DEPLOYMENT_NAME}"

# --- Step 7: Deploy Main Agent Orchestrator (External Ingress) ---
echo ""
echo "▶ 4/4 Deploying Main Agent (external)..."
deploy_containerapp "main-agent" \
    "${ACR_LOGIN_SERVER}/main-agent:latest" \
    "external" \
    "8000" \
    "HR_AGENT_URL=${HR_INTERNAL_URL}" \
    "IT_AGENT_URL=${IT_INTERNAL_URL}" \
    "AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}" \
    "AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY}" \
    "AZURE_OPENAI_API_VERSION=${AZURE_OPENAI_API_VERSION}" \
    "AZURE_OPENAI_DEPLOYMENT_NAME=${AZURE_OPENAI_DEPLOYMENT_NAME}"

MAIN_FQDN=$(az containerapp show \
    --name main-agent \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.configuration.ingress.fqdn" -o tsv)

: "${MAIN_FQDN:?Failed to retrieve Main Agent FQDN. Check the main-agent deployment.}"

# --- Done ---
echo ""
echo "✅ Deployment completed!"
echo ""
echo "🌐 External Endpoint (Main Agent):"
echo "   https://${MAIN_FQDN}"
echo "   Chat API : https://${MAIN_FQDN}/chat"
echo "   Health   : https://${MAIN_FQDN}/health"
echo ""
echo "🔒 Internal-Only Services (ACA Environment Internal Ingress):"
echo "   MCP Server       : $MCP_URL"
echo "   HR Agent         : $HR_INTERNAL_URL"
echo "   IT Agent         : $IT_INTERNAL_URL"
