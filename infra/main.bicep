// infra/main.bicep
targetScope = 'resourceGroup'

@description('Global name-prefix, e.g. "cursus-test1"')
param prefix string

@description('Azure region')
param location string = resourceGroup().location

@description('App-Service plan SKU')
param planSkuName string = 'S1'

@description('Container start-up grace period for the **web-app** (sec)')
param timeout int = 1800

@description('Azure AD tenant ID')
param aadTenantId string

@description('Azure AD application (client) ID')
param aadClientId string

// ---------------------------------------------------------------------------
// Derived resource names (single dash)
// ---------------------------------------------------------------------------
var appName = '${prefix}-app'
var schedFuncName = '${prefix}-sched'
var staticSiteName = '${prefix}-web'

// Keep it globally unique & compliant: lower, no dashes + short unique suffix
var mapsAccountName = '${toLower(replace(prefix, '-', ''))}maps${substring(uniqueString(resourceGroup().id), 0, 6)}'

// ✨ NEW: Images storage account (private)
// lower-case, short unique suffix; avoids dashes per Storage rules
var imagesAccountName = '${toLower(replace(prefix, '-', ''))}img${substring(uniqueString(resourceGroup().id), 0, 6)}'
var avatarsContainerName = 'avatars'

// 1) App-Service Plan --------------------------------------------------------
module planModule './modules/plan.bicep' = {
  name: 'plan'
  params: {
    location: location
    planSkuName: planSkuName
    appName: appName
  }
}

// 2) Cosmos DB ---------------------------------------------------------------
module cosmosModule './modules/cosmos.bicep' = {
  name: 'cosmos'
  params: {
    location: location
    appName: appName
  }
  dependsOn: [
    planModule
  ]
}

// 3) Azure Maps (Gen2) ------------------------------------------------------
module mapsModule './modules/maps.bicep' = {
  name: 'maps'
  params: {
    location: location
    mapsAccountName: mapsAccountName
  }
}

// 4) ✨ NEW: Images storage (private avatars container) ----------------------
module imagesModule './modules/images.bicep' = {
  name: 'images'
  params: {
    location: location
    imagesAccountName: imagesAccountName
    avatarsContainerName: avatarsContainerName
  }
}

// 5) FastAPI Web-App ---------------------------------------------------------
module webAppModule './modules/webapp.bicep' = {
  name: 'webApp'
  params: {
    location: location
    planId: planModule.outputs.planId
    timeout: timeout

    cosmosEndpoint: cosmosModule.outputs.cosmosEndpoint
    databaseName: cosmosModule.outputs.databaseName
    containerName: cosmosModule.outputs.containerName

    appName: appName
    schedFuncName: schedFuncName

    aadTenantId: aadTenantId
    aadClientId: aadClientId

    // ⟨NEW⟩ Pipe Azure Maps primary key into app settings
    azureMapsKey: mapsModule.outputs.mapsPrimaryKey

    // Optional: set defaults here so single deployment is enough
    loginTelemetry: '1'
    geoipProvider: 'azmaps'
  }
  dependsOn: [
    cosmosModule
    planModule
    mapsModule
    imagesModule // ensure images account exists before we wire RBAC below
  ]
}

// 6) Durable Scheduler -------------------------------------------------------
module schedulerModule './modules/scheduler.bicep' = {
  name: 'scheduler'
  params: {
    location: location
    planId: planModule.outputs.planId
    schedulerFunctionName: schedFuncName

    cosmosEndpoint: cosmosModule.outputs.cosmosEndpoint
    databaseName: cosmosModule.outputs.databaseName
    containerName: cosmosModule.outputs.containerName

    appName: appName
  }
  dependsOn: [
    cosmosModule
    planModule
  ]
}

// 7) Static Web-App (Vue frontend) ------------------------------------------
module staticWebModule './modules/staticweb.bicep' = {
  name: 'staticWeb'
  params: {
    location: location
    staticSiteName: staticSiteName
  }
}

// ---------------------------------------------------------------------------
// ✨ NEW: RBAC for Web App MSI → Images Storage
// - Data plane write: Storage Blob Data Contributor
// - Ability to mint user-delegation SAS: Storage Blob Delegator
// We reference both the Web App and Storage as 'existing' to bind roleAssignments.
// ---------------------------------------------------------------------------

// Existing Web App (created by webAppModule)
resource appExisting 'Microsoft.Web/sites@2023-01-01' existing = {
  name: appName
}

// Existing Images Storage Account (created by imagesModule)
resource imagesAccountExisting 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: imagesAccountName
}

// Built-in role IDs (stable GUIDs)
// Storage Blob Data Contributor: ba92f5b4-2d11-453d-a403-e96b0029c9fe
// Storage Blob Delegator:        db58b8e5-c6ad-4a2a-8342-4190687cbf4a

resource raBlobDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(imagesAccountExisting.id, 'blobDataContributor', appExisting.id)
  scope: imagesAccountExisting
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: appExisting.identity.principalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [
    webAppModule
    imagesModule
  ]
}

resource raBlobDelegator 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(imagesAccountExisting.id, 'blobDelegator', appExisting.id)
  scope: imagesAccountExisting
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'db58b8e5-c6ad-4a2a-8342-4190687cbf4a')
    principalId: appExisting.identity.principalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [
    webAppModule
    imagesModule
  ]
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------
output cosmosAccountName string = cosmosModule.outputs.cosmosAccountName
output schedulerFunctionName string = schedulerModule.outputs.schedulerFunctionName
output schedulerStorageName string = schedulerModule.outputs.schedulerStorageName
output staticSiteHostname string = staticWebModule.outputs.staticSiteHostname
output staticSiteName string = staticWebModule.outputs.staticSiteName
output webAppName string = webAppModule.outputs.webAppName // ← existing output
output mapsAccountName string = mapsModule.outputs.mapsAccountName // ← NEW (non-secret)

// ✨ NEW: images outputs (non-secrets)
output imagesAccountName string = imagesModule.outputs.imagesAccountName
output avatarsContainerName string = imagesModule.outputs.avatarsContainerName
output imagesBlobEndpoint string = imagesModule.outputs.blobEndpoint
