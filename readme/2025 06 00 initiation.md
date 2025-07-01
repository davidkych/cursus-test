# Cursus FastAPI Azure Deployment

## Overview

This project demonstrates deploying a Python FastAPI application on Azure using GitHub Actions, Azure CLI, and Bicep for infrastructure-as-code (IaC).

## Repository Structure

```
.
├── .github/
│   └── workflows/
│       └── deploy.yml      # GitHub Actions workflow for CI/CD
├── infra/
│   └── main.bicep          # Azure Bicep template defining infrastructure
├── src/
│   ├── main.py             # FastAPI application entrypoint
│   ├── routers/
│   │   ├── hello/
│   │   │   ├── __init__.py
│   │   │   └── endpoints.py  # /api/hello router
│   │   └── healthz/
│   │       ├── __init__.py
│   │       └── endpoints.py  # /healthz router
│   └── requirements.txt    # Python dependencies
└── README.md               # This file
```

## Prerequisites

- **Azure Subscription** with permission to create Resource Groups and Web App Services
- **Azure CLI** installed and authenticated (`az login`)
- **GitHub Secrets** configured:
  - `AZURE_CLIENT_ID`
  - `AZURE_TENANT_ID`
  - `AZURE_SUBSCRIPTION_ID`
- **Python 3.9** (for local development)
- **Optional**: ngrok (for exposing local server)

## Deployment Workflow

### GitHub Actions (`.github/workflows/deploy.yml`)

- **Triggers**:
  - Push to `main` branch
  - Manual dispatch (`workflow_dispatch`)
- **Permissions**:
  - `id-token: write` (OIDC login)
  - `contents: read`
- **Environment Variables**:
  ```yaml
  RG:          cursus-rg
  LOCATION:    westeurope
  APP:         cursus-app
  PLAN_SKU:    S1
  TIMEOUT:     1800  # container startup grace in seconds
  ```
- **Key Steps**:
  1. **Checkout & Python Setup**: installs Python 3.9 and caches pip packages
  2. **Vendor Dependencies**: `pip install -r src/requirements.txt --target src/`
  3. **Azure Login** (OIDC via `azure/login@v1`)
  4. **Resource Group & Bicep Deploy**:
     ```bash
     az group create -n $RG -l $LOCATION
     az deployment group create \
       --resource-group $RG \
       --template-file infra/main.bicep \
       --parameters planSkuName=$PLAN_SKU timeout=$TIMEOUT
     ```
  5. **Configure App Service**: sets app settings and logging
  6. **Build & Zip Deploy**: packages `src/` into `app.zip` and retries up to 3 times
  7. **Failure Handling**: tails Docker logs on failure

## Infrastructure Definition (`infra/main.bicep`)

- **Target Scope**: `resourceGroup`
- **Parameters**:
  - `location` (defaults to resource group location)
  - `planSkuName` (e.g., `S1`)
  - `timeout` (container startup time limit)
- **Resources**:
  - **App Service Plan** (`Microsoft.Web/serverfarms`)
  - **Web App** (`Microsoft.Web/sites`) with Python 3.9 on Linux
- **Output**:
  ```bicep
  output endpoint string = 'https://${app.properties.defaultHostName}/api/hello'
  ```

## Application Code (`src/`)

- ``:
  - Creates `FastAPI()` app
  - Includes modular routers for `/api/hello` and `/healthz`
  - Root endpoint at `/`
- **Routers**:
  - `src/routers/hello/endpoints.py` → GET `/api/hello`
  - `src/routers/healthz/endpoints.py` → GET `/healthz`
- **Dependencies**:
  - `fastapi`
  - `uvicorn[standard]`
  - `gunicorn`

## Local Development

1. Install dependencies:
   ```bash
   cd src
   pip install -r requirements.txt
   ```
2. Run Uvicorn:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```
3. Access endpoints:
   - `http://localhost:8000/api/hello`
   - `http://localhost:8000/healthz`

### Exposing Locally via ngrok

```bash
ngrok http 8000
```

Use the generated ngrok URL to test from external machines.

## Adding New Features

1. Create a new folder `src/routers/<feature>/`
2. Add `__init__.py` and `endpoints.py` with an `APIRouter()`
3. Import and include the new router in `src/main.py`
4. (Optional) Add tests and update documentation

## Environment Variables & App Settings

Set via Azure App Service or in your workflow:

```bash
WEBSITE_RUN_FROM_PACKAGE=1
SCM_DO_BUILD_DURING_DEPLOYMENT=false
WEBSITES_PORT=8000
PYTHONPATH=/home/site/wwwroot
WEBSITES_CONTAINER_START_TIME_LIMIT=<timeout>
WEBSITES_STARTUP_COMMAND="gunicorn --worker-class uvicorn.workers.UvicornWorker --workers 1 --bind 0.0.0.0:8000 main:app"
```

## Troubleshooting

- **Windows PowerShell**: use `curl.exe` or `Invoke-RestMethod`
- **Azure CLI Logs**:
  ```bash
  az webapp log tail -g cursus-rg -n cursus-app
  ```
- **Bicep What-If**:
  ```bash
  az deployment group what-if -g cursus-rg --template-file infra/main.bicep
  ```

## License

This project is licensed under the MIT License.

## Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/)
- [Azure Bicep](https://docs.microsoft.com/azure/azure-resource-manager/bicep/)
- [GitHub Actions](https://github.com/features/actions)



git add .
git commit -m "jsondata upload and download"
git push origin +main:main