// modules/scheduler.bicep
targetScope = 'resourceGroup'

@description('Azure region')
param location string

@description('App Service Plan resource ID')
param planId string

@description('Durable-scheduler function name')
param schedulerFunctionName string

@description('Cosmos DB endpoint URL')
param cosmosEndpoint string

@description('Cosmos database name')
param databaseName string

@description('Cosmos container name')
param containerName string

@description('Name of the FastAPI app (for callback URL)')
param appName string

var schedStorageName = '${toLower(replace(schedulerFunctionName, '-', ''))}sa${substring(uniqueString(resourceGroup().id), 0, 6)}'
resource schedStorage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name:     schedStorageName
  location: location
  kind:     'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion:        'TLS1_2'
    allowBlobPublicAccess:    false
    supportsHttpsTrafficOnly: true
  }
}

var schedStorageKey        = schedStorage.listKeys().keys[0].value
var schedStorageConnection = 'DefaultEndpointsProtocol=https;AccountName=${schedStorage.name};AccountKey=${schedStorageKey};EndpointSuffix=${environment().suffixes.storage}'

resource schedFunc 'Microsoft.Web/sites@2023-01-01' = {
  name: schedulerFunctionName
  location: location
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    httpsOnly:    true
    serverFarmId: planId
    siteConfig: {
      linuxFxVersion: 'Python|3.9'
      appSettings: [
        { name: 'FUNCTIONS_WORKER_RUNTIME',                 value: 'python' }
        { name: 'FUNCTIONS_EXTENSION_VERSION',              value: '~4' }
        { name: 'WEBSITE_RUN_FROM_PACKAGE',                 value: '1' }
        { name: 'WEBSITES_ENABLE_APP_SERVICE_STORAGE',      value: 'true' }
        { name: 'AzureWebJobsStorage',                      value: schedStorageConnection }
        { name: 'WEBSITE_CONTENTAZUREFILECONNECTIONSTRING', value: schedStorageConnection }
        { name: 'WEBSITE_CONTENTSHARE',                     value: toLower(schedulerFunctionName) }
        { name: 'COSMOS_ENDPOINT',                          value: cosmosEndpoint }
        { name: 'COSMOS_DATABASE',                          value: databaseName }
        { name: 'COSMOS_CONTAINER',                         value: containerName }
        { name: 'WEBAPP_BASE_URL',                          value: 'https://${appName}.azurewebsites.net' }
        { name: 'APP_LOG_LEVEL',                            value: 'Information' }
      ]
    }
  }
  dependsOn: [
    schedStorage
  ]
}

resource schedFuncDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name:  '${schedulerFunctionName}-diag'
  scope: schedFunc
  properties: {
    storageAccountId: schedStorage.id
    logs: [
      {
        category: 'FunctionAppLogs'
        enabled:  true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled:  true
      }
    ]
  }
}

output schedulerFunctionName string = schedFunc.name
output schedulerStorageName    string = schedStorage.name
