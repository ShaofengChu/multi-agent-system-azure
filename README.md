# Multi-Agent System (HR & IT)

This repository implements a multi-agent orchestration system using **Azure OpenAI** and the **Model Context Protocol (MCP)**. It demonstrates how specialized agents can interact with a centralized tool server to perform business operations like retrieving employee data and managing IT equipment.

## Architecture

The system consists of three primary components deployed on **Azure Container Apps**:

1.  **MCP Tool Server (`/mcp_server`)**: A `FastMCP` server that exposes tools for data retrieval and state modification (e.g., assigning laptops).
2.  **HR Agent (`/hr_agent`)**: A specialized Azure OpenAI-powered agent focused on employee information and onboarding. It is instructed to delegate hardware tasks to IT.
3.  **IT Agent (`/it_agent`)**: A specialized Azure OpenAI-powered agent focused on equipment management and assignment.

```
[Client] --JSON-RPC/A2A--> [HR/IT Agent (FastAPI)] --MCP/streamable-http--> [MCP Server (FastMCP)]
                                    |
                            [Azure OpenAI API]
```

## Key Features

-   **Decoupled Tools**: Logic for data access is handled by the MCP server, making it reusable across different agents.
-   **Native JSON Schema**: Azure OpenAI accepts standard JSON Schema for tool definitions — no schema translation needed.
-   **Autonomous Tool Execution**: Agents can autonomously call tools in a loop (up to 5 iterations) to resolve complex queries.
-   **Persona-Based Routing**: System instructions ensure agents stay within their functional domain.
-   **A2A Protocol**: Agents expose Google's Agent-to-Agent protocol endpoints for interoperability.

## Prerequisites

- Python 3.10 or higher
- An Azure subscription with:
  - An **Azure OpenAI** resource with a deployed chat model (e.g., `gpt-5-mini`)
  - (For cloud deployment) Azure CLI (`az`) installed and logged in

## Configuration

Set the following environment variables before running the services:

| Variable | Description |
| :--- | :--- |
| `AZURE_OPENAI_ENDPOINT` | Your Azure OpenAI resource endpoint (e.g., `https://your-resource.openai.azure.com/`). |
| `AZURE_OPENAI_API_KEY` | Your Azure OpenAI API key. |
| `AZURE_OPENAI_API_VERSION` | API version (default: `2024-12-01-preview`). |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Your model deployment name (default: `gpt-5-mini`). |
| `MCP_SERVER_URL` | The URL where the MCP server is hosted (default: `http://localhost:8003/mcp`). |
| `PORT` | Port for the MCP server (defaults to `8080`). |

## Getting Started

### Local Development (Docker Compose)

1.  Create a `.env` file in the project root:
    ```bash
    AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
    AZURE_OPENAI_API_KEY=your-api-key-here
    AZURE_OPENAI_API_VERSION=2024-12-01-preview
    AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5-mini
    ```

2.  Start all services:
    ```bash
    docker-compose up --build
    ```

3.  Test the agents:
    ```bash
    # HR Agent (port 8081)
    curl -X POST http://localhost:8081/tasks/send \
      -H "Content-Type: application/json" \
      -d '{"jsonrpc":"2.0","method":"tasks/send","params":{"message":{"role":"user","parts":[{"text":"従業員E001の情報を教えてください"}]}},"id":"test-1"}'

    # IT Agent (port 8082)
    curl -X POST http://localhost:8082/tasks/send \
      -H "Content-Type: application/json" \
      -d '{"jsonrpc":"2.0","method":"tasks/send","params":{"message":{"role":"user","parts":[{"text":"利用可能なノートPCを教えてください"}]}},"id":"test-2"}'
    ```

### Cloud Deployment (Azure Container Apps)

1.  Ensure Azure CLI is installed and logged in:
    ```bash
    az login
    ```

2.  Set environment variables:
    ```bash
    export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
    export AZURE_OPENAI_API_KEY="your-api-key-here"
    export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5-mini"
    ```

3.  Run the deployment script:
    ```bash
    bash deploy.sh
    ```

    This will:
    - Create an Azure Container Registry (if needed)
    - Create a Container Apps Environment (if needed)
    - Build and push Docker images
    - Deploy MCP Server (internal ingress), HR Agent, and IT Agent (external ingress)

4.  Update the agent card URLs in `hr_agent/main.py` and `it_agent/main.py` with the deployed URLs printed by the script.

## Project Structure

```text
multi-agent-system/
├── deploy.sh          # Azure Container Apps deployment script
├── docker-compose.yml # Local development with Docker Compose
├── hr_agent/
│   ├── agent.py       # HR Agent — Azure OpenAI + MCP tool-calling loop
│   └── main.py        # FastAPI server with A2A protocol endpoints
├── it_agent/
│   ├── agent.py       # IT Agent — Azure OpenAI + MCP tool-calling loop
│   └── main.py        # FastAPI server with A2A protocol endpoints
└── mcp_server/
    ├── main.py        # FastMCP server definition and tool logic
    └── data.py        # Mock database for employees and laptops
```

## Tooling

The following tools are available via the MCP server:
- `get_employee_info`: Retrieve name, department, and hire date.
- `get_available_laptops`: List hardware with "available" status.
- `assign_equipment`: Link a specific laptop to an employee ID.