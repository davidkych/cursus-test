// infra/main.bicep
targetScope = 'resourceGroup'

@description('Azure region')
param location string = resourceGroup().location

@description('App-Service plan SKU (B1, S1, P1v2 …)')
param planSkuName string = 'S1'

@description('Container start-up grace period for the **web-app** (sec, max 1800)')
param timeout int = 1800

var appName           = 'cursus-test-app'
var planName          = '${appName}-plan'
var cosmosAccountName = '${toLower(replace(appName, '-', ''))}${substring(uniqueString(resourceGroup().id), 0, 6)}'
var schedFuncName     = 'cursus-test-sched'
var schedStorageName  = '${toLower(replace(schedFuncName, '-', ''))}sa${substring(uniqueString(resourceGroup().id), 0, 6)}'

module plan './modules/plan.bicep' = {
  name: 'planModule'
  params: {
    location:    location
    planSkuName: planSkuName
    planName:    planName
  }
}

module cosmos './modules/cosmos.bicep' = {
  name: 'cosmosModule'
  params: {
    location:          location
    cosmosAccountName: cosmosAccountName
  }
  dependsOn: [ plan ]
}

module storage './modules/schedStorage.bicep' = {
  name: 'schedStorageModule'
  params: {
    location:         location
    schedStorageName: schedStorageName
  }
  dependsOn: [ cosmos ]
}

module webapp './modules/webapp.bicep' = {
  name: 'webappModule'
  params: {
    location:            location
    appName:             appName
    planId:              plan.outputs.planId
    timeout:             timeout
    cosmosEndpoint:      cosmos.outputs.endpoint
    cosmosDatabaseName:  cosmos.outputs.databaseName
    cosmosContainerName: cosmos.outputs.containerName
    schedFuncName:       schedFuncName
  }
  dependsOn: [ cosmos ]
}

module schedFunc './modules/schedFunc.bicep' = {
  name: 'schedFuncModule'
  params: {
    location:           location
    schedFuncName:      schedFuncName
    planId:             plan.outputs.planId
    cosmosEndpoint:     cosmos.outputs.endpoint
    cosmosDatabaseName: cosmos.outputs.databaseName
    cosmosContainerName: cosmos.outputs.containerName
    storageConnection:  storage.outputs.storageConnection
    appName:            appName
  }
  dependsOn: [ plan, storage, cosmos ]
}

module diag './modules/schedDiag.bicep' = {
  name: 'diagModule'
  params: {
    schedFuncName:    schedFuncName
    diagnosticName:   '${schedFuncName}-diag'
    storageAccountId: storage.outputs.storageAccountId
  }
  dependsOn: [ schedFunc, storage ]
}

output cosmosAccountName     string = cosmosAccountName
output schedulerFunctionName string = schedFuncName
output schedulerStorageName  string = schedStorageName
