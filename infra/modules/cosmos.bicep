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
  name:   'cursus-test1db'
  properties: {
    resource: { id: 'cursus-test1db' }
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
      // ────────────────────────────────────────────────────────────────
      // Composite index to support:
      //   ORDER BY c.day DESC, c._ts DESC
      // ────────────────────────────────────────────────────────────────
      indexingPolicy: {
        automatic: true
        indexingMode: 'consistent'
        includedPaths: [
          { path: '/*' }
        ]
        excludedPaths: [
          { path: '/"_etag"/?' }
        ]
        compositeIndexes: [
          [
            {
              path: '/day'
              order: 'descending'
            }
            {
              path: '/_ts'
              order: 'descending'
            }
          ]
        ]
      }
    }
    options: {}
  }
}

output cosmosAccountName string   = cosmos.name
output cosmosEndpoint    string   = cosmos.properties.documentEndpoint
output databaseName      string   = 'cursus-test1db'
output containerName     string   = 'jsonContainer'
