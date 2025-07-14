// infra/main.bicep
targetScope = 'resourceGroup'

@description('Azure region')
param location string = resourceGroup().location

@description('App-Service plan SKU')
param planSkuName string = 'S1'

@description('Container start-up grace period for the **web-app** (sec)')
param timeout int = 1800

// ── NEW ─────────────────────────────────────────────────────────────
@description('Azure AD tenant ID')
param aadTenantId string

@description('Azure AD application (client) ID')
param aadClientId string
// ────────────────────────────────────────────────────────────────────

var appName        = 'cursus-test-app'
var schedFuncName  = 'cursus-test-sched'
var staticSiteName = 'cursus-test-web'

// 1) App-Service Plan ------------------------------------------------
module planModule './modules/plan.bicep' = {
  name: 'plan'
  params: {
    location:     location
    planSkuName:  planSkuName
    appName:      appName
  }
}

// 2) Cosmos DB -------------------------------------------------------
module cosmosModule './modules/cosmos.bicep' = {
  name: 'cosmos'
  params: {
    location: location
    appName:  appName
  }
  dependsOn: [ planModule ]
}

// 3) FastAPI Web-App -----------------------------------------------
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
    aadTenantId:    aadTenantId        // ← NEW
    aadClientId:    aadClientId        // ← NEW
  }
  dependsOn: [ cosmosModule, planModule ]
}

// 4) Durable Scheduler ----------------------------------------------
module schedulerModule './modules/scheduler.bicep' = {
  name: 'scheduler'
  params: {
    location:               location
    planId:                 planModule.outputs.planId
    schedulerFunctionName:  schedFuncName
    cosmosEndpoint:         cosmosModule.outputs.cosmosEndpoint
    databaseName:           cosmosModule.outputs.databaseName
    containerName:          cosmosModule.outputs.containerName
    appName:                appName
  }
  dependsOn: [ cosmosModule, planModule ]
}

// 5) Static Web-App (Vue frontend) ----------------------------------
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
