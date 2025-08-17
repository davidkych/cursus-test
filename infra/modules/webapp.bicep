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

// ⟨NEW⟩ Images Storage (private) – values are passed from the images module via main.bicep
@description('Images Storage Account name')
param imagesAccountName string

@description('Images Storage Account resource ID (for RBAC scope)')
param imagesAccountId string

@description('Blob container name for avatars')
param imagesContainerName string = 'avatars'

@description('Blob endpoint for the Images Storage Account, e.g. https://<acct>.blob.core.windows.net/')
param imagesBlobEndpoint string

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
// App Service (Linux)
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
        // Core container/runtime
        { name: 'WEBSITES_PORT',                       value: '8000' }
        { name: 'WEBSITES_CONTAINER_START_TIME_LIMIT', value: string(timeout) }

        // Cosmos wiring
        { name: 'COSMOS_ENDPOINT',                     value: cosmosEndpoint }
        { name: 'COSMOS_DATABASE',                     value: databaseName }
        { name: 'COSMOS_CONTAINER',                    value: containerName }
        // Codes container name (kept configurable via app settings)
        { name: 'CODES_CONTAINER',                     value: 'codes' }

        // Scheduler wiring
        { name: 'SCHEDULER_BASE_URL',                  value: schedulerBaseUrl }
        { name: 'SCHEDULER_FUNCTION_NAME',             value: schedFuncName }

        // Telemetry wiring (safe defaults; empty values are fine)
        { name: 'LOGIN_TELEMETRY',                     value: loginTelemetry }
        { name: 'GEOIP_PROVIDER',                      value: geoipProvider }
        { name: 'AZURE_MAPS_KEY',                      value: azureMapsKey }

        // ⟨NEW⟩ Images Storage wiring (used by avatar endpoints)
        { name: 'IMAGES_ACCOUNT_NAME',                 value: imagesAccountName }
        { name: 'IMAGES_CONTAINER',                    value: imagesContainerName }
        { name: 'IMAGES_BLOB_ENDPOINT',                value: imagesBlobEndpoint }

        // ⟨NEW⟩ Avatar policy defaults (premium users only; admins bypass in code)
        { name: 'AVATAR_MAX_KIB',                      value: '512' }
        { name: 'AVATAR_ALLOWED_TYPES',                value: 'image/jpeg,image/jpg,image/png' }
        { name: 'AVATAR_REQUIRE_PREMIUM',              value: '1' }
      ]
    }
  }
}

// ---------------------------------------------------------------------------
// Easy Auth v2 (allows anonymous; enables AAD sign-in)
// - Uses environment().authentication.loginEndpoint to avoid hardcoded URLs.
// ---------------------------------------------------------------------------
resource auth 'Microsoft.Web/sites/config@2023-01-01' = {
  name: 'authsettingsV2'
  parent: app
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
          // Avoid hardcoded cloud endpoints
          openIdIssuer: '${environment().authentication.loginEndpoint}${aadTenantId}/v2.0'
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

// ---------------------------------------------------------------------------
// RBAC: Grant Web-App MSI "Storage Blob Data Contributor" on Images SA
// - Name uses only values resolvable at start (avoids BCP120).
// - principalId is allowed in properties (runtime).
// ---------------------------------------------------------------------------
resource blobDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(imagesAccountId, app.id, 'blob-data-contributor')
  scope: resourceId('Microsoft.Storage/storageAccounts', imagesAccountName)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Storage Blob Data Contributor
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output webAppName string = app.name
