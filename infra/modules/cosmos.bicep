// modules/cosmos.bicep
targetScope = 'resourceGroup'

@description('Azure region')
param location string

@description('Name of the app (for account naming)')
param appName string

// ---------------------------------------------------------------------------
// Account name – keep it short & globally unique
// ---------------------------------------------------------------------------
var cosmosAccountName = '${toLower(replace(appName, '-', ''))}${substring(uniqueString(resourceGroup().id), 0, 6)}'

// ---------------------------------------------------------------------------
// Cosmos DB account
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Single SQL database (400 RU/s – shared)
// ---------------------------------------------------------------------------
resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2021-04-15' = {
  parent: cosmos
  name:   'cursus-test1db'
  properties: {
    resource: { id: 'cursus-test1db' }
    options:  { throughput: 400 }
  }
}

// ---------------------------------------------------------------------------
// Existing JSON container
// ---------------------------------------------------------------------------
resource jsonContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2021-04-15' = {
  parent: cosmosDb
  name:   'jsonContainer'
  properties: {
    resource: {
      id: 'jsonContainer'
      partitionKey: {
        paths: [ '/tag' ]
        kind:  'Hash'
      }
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
            { path: '/day', order: 'descending' }
            { path: '/_ts', order: 'descending' }
          ]
        ]
      }
    }
    options: {}
  }
}

// ---------------------------------------------------------------------------
// ✨ NEW: Users container (shared RU/s)
// ---------------------------------------------------------------------------
resource usersContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2021-04-15' = {
  parent: cosmosDb
  name:   'users'
  properties: {
    resource: {
      id: 'users'
      partitionKey: {
        paths: [ '/username' ]   // fast point-reads
        kind:  'Hash'
      }
      // Enforce unique username & e-mail
      uniqueKeyPolicy: {
        uniqueKeys: [
          { paths: [ '/username' ] }
          { paths: [ '/email'    ] }
        ]
      }
    }
    options: {}                  // inherit DB throughput (cheapest)
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------
output cosmosAccountName string = cosmos.name
output cosmosEndpoint    string = cosmos.properties.documentEndpoint
output databaseName      string = 'cursus-test1db'
output containerName     string = 'jsonContainer'
