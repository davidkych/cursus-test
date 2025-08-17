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
var mapsAccountName = '${toLower(replace(prefix, '-', ''))}maps${substring(uniqueString(resourceGroup().id), 0, 6)}'

// NEW: Images Storage Account name (letters/digits only, <=24 chars)
//   base   = lower(prefix) without dashes
//   suffix = "img" + 6-char unique
//   trim base to fit 24 char total
var _imgBase        = toLower(replace(prefix, '-', ''))
var _imgSuffix      = 'img${substring(uniqueString(resourceGroup().id), 0, 6)}'
var _imgMaxBaseLen  = 24 - length(_imgSuffix)
var _imgTrimmedBase = length(_imgBase) > _imgMaxBaseLen ? substring(_imgBase, 0, _imgMaxBaseLen) : _imgBase
var imagesAccountName = '${_imgTrimmedBase}${_imgSuffix}'

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

// 3.5) Images Storage (private) ----------------------------------------------
module imagesModule './modules/images.bicep' = {
  name: 'images'
  params: {
    location:          location
    imagesAccountName: imagesAccountName
    // can expand later: add more containers here
    containerNames: [
      'avatars'
    ]
  }
}

// 4) FastAPI Web-App ---------------------------------------------------------
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
  }
  dependsOn: [ cosmosModule, planModule, mapsModule ]
}

// 5) Durable Scheduler -------------------------------------------------------
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

// 6) Static Web-App (Vue frontend) ------------------------------------------
module staticWebModule './modules/staticweb.bicep' = {
  name: 'staticWeb'
  params: {
    location:       location
    staticSiteName: staticSiteName
  }
}

output cosmosAccountName     string = cosmosModule.outputs.cosmosAccountName
output schedulerFunctionName string = schedulerModule.outputs.schedulerFunctionName
output schedulerStorageName  string = schedulerModule.outputs.schedulerStorageName
output staticSiteHostname    string = staticWebModule.outputs.staticSiteHostname
output staticSiteName        string = staticWebModule.outputs.staticSiteName
output webAppName            string = webAppModule.outputs.webAppName    // ← existing
output mapsAccountName       string = mapsModule.outputs.mapsAccountName // ← NEW (non-secret)
output imagesAccountName     string = imagesModule.outputs.imagesAccountNameOut // ← NEW
output imagesBlobEndpoint    string = imagesModule.outputs.imagesBlobEndpoint   // ← NEW
