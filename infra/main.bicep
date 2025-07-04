// ── infra/main.bicep  (cursus-test) ──────────────────────────────────
targetScope = 'resourceGroup'

@description('Azure region')
param location string = resourceGroup().location

@description('App-Service plan SKU (B1, S1, P1v2 …)')
param planSkuName string = 'S1'

@description('Container start-up grace period for the **web-app** (sec, max 1800)')
param timeout int = 1800

/* ────────────────────────────────────────────────────────────────
   TEST stack – every resource carries the “-test” prefix so that
   nothing can overlap with production “cursus”.
   ──────────────────────────────────────────────────────────────── */
var appName           = 'cursus-test-app'
var planName          = '${appName}-plan'
var cosmosAccountName = '${toLower(replace(appName, '-', ''))}${substring(uniqueString(resourceGroup().id),0,6)}'

/* ===== Durable Scheduler vars ==================================== */
var schedFuncName    = 'cursus-test-sched'
var schedStorageName = '${toLower(replace(schedFuncName, '-', ''))}sa${substring(uniqueString(resourceGroup().id),0,6)}'

/* ── App-Service Plan (shared) ──────────────────────────────────── */
resource plan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name:     planName
  location: location
  sku: {
    name: planSkuName
    tier: startsWith(planSkuName, 'S') ? 'Standard' : 'Basic'
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

/* ── Cosmos DB (SQL API) ────────────────────────────────────────── */
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2021-04-15' = {
  name:     cosmosAccountName
  location: location
  kind:     'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [
      {
        locationName:     location
        failoverPriority: 0
      }
    ]
  }
}

resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2021-04-15' = {
  parent: cosmos
  name:   'cursusdb'
  properties: {
    resource: { id: 'cursusdb' }
    options:  { throughput: 400 }
  }
}

resource cosmosContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2021-04-15' = {
  parent: cosmosDb
  name:   'jsonContainer'
  properties: {
    resource: {
      id: 'jsonContainer'
      partitionKey: {
        paths: [ '/tag' ]
        kind:  'Hash'
      }
    }
    options: {}
  }
}

/* ── Web-App (FastAPI) ──────────────────────────────────────────── */
resource app 'Microsoft.Web/sites@2023-01-01' = {
  name: appName
  location: location
  kind: 'app,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.9'
      appCommandLine: 'gunicorn --log-level info --worker-class uvicorn.workers.UvicornWorker --workers 2 --bind 0.0.0.0:8000 main:app'
      healthCheckPath: '/healthz'
      appSettings: [
        { name: 'WEBSITES_PORT',                       value: '8000' }
        { name: 'WEBSITES_CONTAINER_START_TIME_LIMIT', value: string(timeout) }
        { name: 'COSMOS_ENDPOINT',                     value: cosmos.properties.documentEndpoint }
        { name: 'COSMOS_DATABASE',                     value: 'cursusdb' }
        { name: 'COSMOS_CONTAINER',                    value: 'jsonContainer' }

        /* ── NEW: expose Durable-scheduler endpoint on first boot ── */
        { name: 'SCHEDULER_BASE_URL',                  value: 'https://${schedFuncName}.azurewebsites.net' }
        { name: 'SCHEDULER_FUNCTION_NAME',             value: schedFuncName }
      ]
    }
  }
  dependsOn: [
    cosmosContainer
  ]
}

/* ===================================================================
   DURABLE SCHEDULER  (Function-App + Storage + Diagnostics)
   =================================================================== */

/* ── Storage account for Durable state & logs ────────────────────── */
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

/* Connection string for Function-App settings */
var schedStorageKey        = schedStorage.listKeys().keys[0].value
var schedStorageConnection = 'DefaultEndpointsProtocol=https;AccountName=${schedStorage.name};AccountKey=${schedStorageKey};EndpointSuffix=${environment().suffixes.storage}'

/* ── Function-App (Durable Scheduler) ────────────────────────────── */
resource schedFunc 'Microsoft.Web/sites@2023-01-01' = {
  name: schedFuncName
  location: location
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    httpsOnly:   true
    serverFarmId: plan.id
    siteConfig: {
      linuxFxVersion: 'Python|3.9'
      appSettings: [
        { name: 'FUNCTIONS_WORKER_RUNTIME',                 value: 'python' }
        { name: 'FUNCTIONS_EXTENSION_VERSION',              value: '~4' }
        { name: 'WEBSITE_RUN_FROM_PACKAGE',                 value: '1' }
        { name: 'WEBSITES_ENABLE_APP_SERVICE_STORAGE',      value: 'true' }

        /* Durable storage */
        { name: 'AzureWebJobsStorage',                      value: schedStorageConnection }
        { name: 'WEBSITE_CONTENTAZUREFILECONNECTIONSTRING', value: schedStorageConnection }
        { name: 'WEBSITE_CONTENTSHARE',                     value: toLower(schedFuncName) }

        /* Cosmos settings */
        { name: 'COSMOS_ENDPOINT',                          value: cosmos.properties.documentEndpoint }
        { name: 'COSMOS_DATABASE',                          value: 'cursusdb' }
        { name: 'COSMOS_CONTAINER',                         value: 'jsonContainer' }

        { name: 'APP_LOG_LEVEL',                            value: 'Information' }
      ]
    }
  }
  dependsOn: [
    cosmosContainer
  ]
}

/* ── Diagnostic Settings (Function-App ➜ Storage) ────────────────── */
resource schedFuncDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name:  '${schedFuncName}-diag'
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

/* ── Outputs (for GitHub Actions) ────────────────────────────────── */
output cosmosAccountName     string = cosmosAccountName
output schedulerFunctionName string = schedFuncName
output schedulerStorageName  string = schedStorageName
