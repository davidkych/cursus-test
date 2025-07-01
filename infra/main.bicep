targetScope = 'resourceGroup'

@description('Azure region')
param location string = resourceGroup().location

@description('App-Service plan SKU (B1, S1, P1v2 …)')
param planSkuName string = 'S1'

@description('Container start-up grace period (sec, max 1800)')
param timeout string = '1800'

/* ────────────────────────────────────────────────────────────────
   TEST stack – all resource names carry the “-test” prefix
   so nothing can overlap with the production cursus resources.
   ──────────────────────────────────────────────────────────────── */
var appName  = 'cursus-test-app'
var planName = '${appName}-plan'
var cosmosAccountName = '${toLower(replace(appName, '-', ''))}${substring(uniqueString(resourceGroup().id),0,6)}'

/* ── App-Service Plan ── */
resource plan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name:     planName
  location: location
  sku:      {
    name: planSkuName
    tier: startsWith(planSkuName, 'S') ? 'Standard' : 'Basic'
  }
  kind: 'linux'
  properties: { reserved: true }
}

/* ── Cosmos-DB (SQL API) ── */
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2021-04-15' = {
  name: cosmosAccountName
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [ { locationName: location, failoverPriority: 0 } ]
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
      partitionKey: { paths: [ '/tag' ], kind: 'Hash' }
    }
    options: {}
  }
}

/* ── Web App (system-assigned MI) ── */
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
        { name: 'WEBSITES_CONTAINER_START_TIME_LIMIT', value: timeout }
        { name: 'COSMOS_ENDPOINT',                     value: cosmos.properties.documentEndpoint }
        { name: 'COSMOS_DATABASE',                     value: 'cursusdb' }
        { name: 'COSMOS_CONTAINER',                    value: 'jsonContainer' }
      ]
    }
  }
  dependsOn: [ cosmosContainer ]
}

/* ── Management-plane role (unchanged) ── */
resource cosmosRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(cosmos.id, 'cosmosrbac')
  scope: cosmos
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions','5bd9cd88-fe45-4216-938b-f97437e15450') // “DocumentDB Account Contributor”
    principalId:   app.identity.principalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [ app ]
}

/* ── expose real account name so GitHub Actions can see it ── */
output cosmosAccountName string = cosmosAccountName
