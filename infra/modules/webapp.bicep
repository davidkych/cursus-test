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
@allowed([ '0' '1' ])
param loginTelemetry string = '1'

@description('Geo-IP provider selector (only "azmaps" supported)')
@allowed([ 'azmaps' '' ])
param geoipProvider string = 'azmaps'

// ⟨NEW⟩ Images Storage wiring (for avatars via SAS/stream)
@description('Images Storage Account name (for avatars and future images)')
param imagesAccountName string

@description('Images Storage container name (e.g., "avatars")')
param imagesContainerName string

@description('Images Storage blob endpoint (e.g., https://<acct>.blob.core.windows.net/ )')
param imagesBlobEndpoint string

@description('Images Storage Account resource ID (for RBAC scope)')
param imagesAccountId string

// ⟨NEW⟩ Avatar upload policy knobs (avoid hardcoding in code)
@description('Max avatar size in KiB for non-admins')
param avatarMaxKiB int = 512

@description('Comma-separated MIME types allowed for non-admins')
param avatarAllowedTypes string = 'image/jpeg,image/jpg,image/png'

@description('Require premium membership for avatar uploads ("1" yes, "0" no)')
@allowed([ '0' '1' ])
param avatarRequirePremium string = '1'

// ---------------------------------------------------------------------------
// Derived values
// ---------------------------------------------------------------------------
var schedulerBaseUrl = 'https://${schedFuncName}.azurewebsites.net'

// Bring the images Storage Account into scope for RBAC
resource imagesSa 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: imagesAccountName
}

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
        // ✨ Codes container name (kept configurable via app settings)
        { name: 'CODES_CONTAINER',                     value: 'codes' }

        // Scheduler wiring
        { name: 'SCHEDULER_BASE_URL',                  value: schedulerBaseUrl }
        { name: 'SCHEDULER_FUNCTION_NAME',             value: schedFuncName }

        // ⟨NEW⟩ Telemetry wiring (safe defaults; empty values are fine)
        { name: 'LOGIN_TELEMETRY',                     value: loginTelemetry }
        { name: 'GEOIP_PROVIDER',                      value: geoipProvider }
        { name: 'AZURE_MAPS_KEY',                      value: azureMapsKey }

        // ⟨NEW⟩ Images Storage (backend builds clients with MSI)
        { name: 'IMAGES_ACCOUNT_NAME',                 value: imagesAccountName }
        { name: 'IMAGES_BLOB_ENDPOINT',                value: imagesBlobEndpoint }
        { name: 'IMAGES_CONTAINER',                    value: imagesContainerName }

        // ⟨NEW⟩ Avatar policy knobs (no hardcoding in code)
        { name: 'AVATAR_MAX_KIB',                      value: string(avatarMaxKiB) }
        { name: 'AVATAR_ALLOWED_TYPES',                value: avatarAllowedTypes }
        { name: 'AVATAR_REQUIRE_PREMIUM',              value: avatarRequirePremium }
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

// ---------------------------------------------------------------------------
// ⟨NEW⟩ RBAC: Grant the Web App MSI access to images Storage (Blob Data Contributor)
// ---------------------------------------------------------------------------
resource blobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(imagesSa.id, app.identity.principalId, 'StorageBlobDataContributor')
  scope: imagesSa
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Storage Blob Data Contributor
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [
    app
  ]
}

output webAppName string = app.name
