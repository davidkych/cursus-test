// modules/cosmos.bicep
targetScope = 'resourceGroup'

@description('Azure region')
param location string

@description('Name of the app (for account naming)')
param appName string

var cosmosAccountName = '${toLower(replace(appName, '-', ''))}${substring(uniqueString(resourceGroup().id), 0, 6)}'

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2021-04-15' = {
  name:     cosmosAccountName
  location: location
  kind:     'GlobalDocumentDB'
  properties: {
    // ── existing settings ────────────────────────────────────────────────
    databaseAccountOfferType: 'Standard'
    locations: [
      {
        locationName:     location
        failoverPriority: 0
      }
    ]

    // ── NEW: enable data-plane RBAC so the Web-App’s MSI can access Cosmos ──
    isRoleBasedAccessControlEnabled: true
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

output cosmosAccountName string   = cosmos.name
output cosmosEndpoint    string   = cosmos.properties.documentEndpoint
output databaseName      string   = 'cursusdb'
output containerName     string   = 'jsonContainer'
