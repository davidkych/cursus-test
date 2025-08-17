// infra/modules/webapp.bicep
targetScope = 'resourceGroup'

@description('Azure region')
param location string

@description('App Service Plan resource ID')
param planId string

@description('Container start-up grace period (sec)')
param timeout int

@description('Cosmos DB endpoint URL')
param cosmosEndpoint string

@description('Cosmos database name')
param databaseName string

@description('Cosmos container name')
param containerName string

@description('Name of the app')
param appName string

@description('Durable-scheduler function name')
param schedFuncName string

@description('Azure AD tenant ID')
param aadTenantId string

@description('Azure AD application (client) ID')
param aadClientId string

// ⟨NEW⟩ Azure Maps + telemetry integration (optional; empty to disable)
@description('Azure Maps subscription key to enable IP geolocation (leave empty to skip)')
param azureMapsKey string = ''

@description('Login telemetry feature flag: "1" to enable, "0" to disable')
@allowed([
  '0'
  '1'
])
param loginTelemetry string = '1'

@description('Geo-IP provider selector (only "azmaps" supported)')
@allowed([
  'azmaps'
  ''
])
param geoipProvider string = 'azmaps'

// ---------------------------------------------------------------------------
// Derived values
// ---------------------------------------------------------------------------
var schedulerBaseUrl = 'https://${schedFuncName}.azurewebsites.net'

// ---------------------------------------------------------------------------
// App Service (Linux)  -------------------------------------------------------
// ---------------------------------------------------------------------------
resource app 'Microsoft.Web/sites@2023-01-01' = {
  name: appName
  location: location
  kind: 'app,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: planId
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.9'
      appCommandLine: 'gunicorn --log-level info --worker-class uvicorn.workers.UvicornWorker --workers 2 --bind 0.0.0.0:8000 main:app'
      healthCheckPath: '/healthz'
      appSettings: [
        { name: 'WEBSITES_PORT',                       value: '8000' }
        { name: 'WEBSITES_CONTAINER_START_TIME_LIMIT', value: string(timeout) }

        // Cosmos wiring
        { name: 'COSMOS_ENDPOINT',                     value: cosmosEndpoint }
        { name: 'COSMOS_DATABASE',                     value: databaseName }
        { name: 'COSMOS_CONTAINER',                    value: containerName }
        // ✨ NEW: Codes container name (kept configurable via app settings)
        { name: 'CODES_CONTAINER',                      value: 'codes' }

        // Scheduler wiring
        { name: 'SCHEDULER_BASE_URL',                  value: schedulerBaseUrl }
        { name: 'SCHEDULER_FUNCTION_NAME',             value: schedFuncName }

        // ⟨NEW⟩ Telemetry wiring (safe defaults; empty values are fine)
        { name: 'LOGIN_TELEMETRY',                     value: loginTelemetry }
        { name: 'GEOIP_PROVIDER',                      value: geoipProvider }
        { name: 'AZURE_MAPS_KEY',                      value: azureMapsKey }
      ]
    }
  }
}

// ---------------------------------------------------------------------------
// Easy Auth v2  (allows anonymous; enables AAD sign-in) -----------------------
// ---------------------------------------------------------------------------
resource auth 'Microsoft.Web/sites/config@2023-01-01' = {
  name: '${app.name}/authsettingsV2'
  properties: {
    platform: {
      enabled: true
    }
    globalValidation: {
      unauthenticatedClientAction: 'AllowAnonymous'
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: aadClientId
          openIdIssuer: 'https://login.microsoftonline.com/${aadTenantId}/v2.0'
        }
        validation: {
          allowedAudiences: [
            aadClientId
          ]
        }
      }
    }
  }
}

output webAppName string = app.name
