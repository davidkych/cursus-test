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
var appName        = '${prefix}-app'
var schedFuncName  = '${prefix}-sched'
var staticSiteName = '${prefix}-web'

// Keep it globally unique & compliant: lower, no dashes + short unique suffix
var mapsAccountName   = '${toLower(replace(prefix, '-', ''))}maps${substring(uniqueString(resourceGroup().id), 0, 6)}'
var imagesAccountName = '${toLower(replace(prefix, '-', ''))}img${substring(uniqueString(resourceGroup().id), 0, 6)}'

// 1) App-Service Plan --------------------------------------------------------
module planModule './modules/plan.bicep' = {
  name: 'plan'
  params: {
    location:    location
    planSkuName: planSkuName
    appName:     appName
  }
}

// 2) Cosmos DB ---------------------------------------------------------------
module cosmosModule './modules/cosmos.bicep' = {
  name: 'cosmos'
  params: {
    location: location
    appName:  appName
  }
  dependsOn: [ planModule ]
}

// 3) Azure Maps (Gen2)  ------------------------------------------------------
module mapsModule './modules/maps.bicep' = {
  name: 'maps'
  params: {
    location:        location
    mapsAccountName: mapsAccountName
  }
}

// 4) Images Storage (private avatars) ----------------------------------------
module imagesModule './modules/images.bicep' = {
  name: 'images'
  params: {
    location:          location
    imagesAccountName: imagesAccountName
  }
}

// 5) FastAPI Web-App ---------------------------------------------------------
module webAppModule './modules/webapp.bicep' = {
  name: 'webApp'
  params: {
    location:       location
    planId:         planModule.outputs.planId
    timeout:        timeout
    cosmosEndpoint: cosmosModule.outputs.cosmosEndpoint
    databaseName:   cosmosModule.outputs.databaseName
    containerName:  cosmosModule.outputs.containerName
    appName:        appName
    schedFuncName:  schedFuncName
    aadTenantId:    aadTenantId
    aadClientId:    aadClientId

    // ⟨NEW⟩ Pipe Azure Maps primary key into app settings
    azureMapsKey:   mapsModule.outputs.mapsPrimaryKey
    // Optional: set defaults here so single deployment is enough
    loginTelemetry: '1'
    geoipProvider:  'azmaps'

    // ⟨NEW⟩ Images storage wiring (for avatars via SAS/stream)
    imagesAccountName:   imagesModule.outputs.imagesAccountName
    imagesContainerName: imagesModule.outputs.avatarsContainerName
    imagesBlobEndpoint:  imagesModule.outputs.blobEndpoint
    imagesAccountId:     imagesModule.outputs.imagesAccountId
  }
  dependsOn: [ cosmosModule, planModule, mapsModule, imagesModule ]
}

// 6) Durable Scheduler -------------------------------------------------------
module schedulerModule './modules/scheduler.bicep' = {
  name: 'scheduler'
  params: {
    location:              location
    planId:                planModule.outputs.planId
    schedulerFunctionName: schedFuncName
    cosmosEndpoint:        cosmosModule.outputs.cosmosEndpoint
    databaseName:          cosmosModule.outputs.databaseName
    containerName:         cosmosModule.outputs.containerName
    appName:               appName
  }
  dependsOn: [ cosmosModule, planModule ]
}

// 7) Static Web-App (Vue frontend) ------------------------------------------
module staticWebModule './modules/staticweb.bicep' = {
  name: 'staticWeb'
  params: {
    location:       location
    staticSiteName: staticSiteName
  }
}

output cosmosAccountName       string = cosmosModule.outputs.cosmosAccountName
output schedulerFunctionName   string = schedulerModule.outputs.schedulerFunctionName
output schedulerStorageName    string = schedulerModule.outputs.schedulerStorageName
output staticSiteHostname      string = staticWebModule.outputs.staticSiteHostname
output staticSiteName          string = staticWebModule.outputs.staticSiteName
output webAppName              string = webAppModule.outputs.webAppName    // ← existing
output mapsAccountName         string = mapsModule.outputs.mapsAccountName // ← NEW (non-secret)

// ⟨NEW⟩ Images outputs for downstream workflows (if needed)
output imagesAccountName       string = imagesModule.outputs.imagesAccountName
output imagesAccountId         string = imagesModule.outputs.imagesAccountId
output avatarsContainerName    string = imagesModule.outputs.avatarsContainerName
output imagesBlobEndpoint      string = imagesModule.outputs.blobEndpoint
