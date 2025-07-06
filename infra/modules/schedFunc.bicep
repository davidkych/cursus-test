// modules/schedFunc.bicep
param location              string
param schedFuncName         string
param planId                string
param cosmosEndpoint        string
param cosmosDatabaseName    string
param cosmosContainerName   string
param storageConnection     string
param appName               string

resource schedFunc 'Microsoft.Web/sites@2023-01-01' = {
  name:     schedFuncName
  location: location
  kind:     'functionapp,linux'
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
        { name: 'AzureWebJobsStorage',                      value: storageConnection }
        { name: 'WEBSITE_CONTENTAZUREFILECONNECTIONSTRING', value: storageConnection }
        { name: 'WEBSITE_CONTENTSHARE',                     value: toLower(schedFuncName) }
        { name: 'COSMOS_ENDPOINT',                          value: cosmosEndpoint }
        { name: 'COSMOS_DATABASE',                          value: cosmosDatabaseName }
        { name: 'COSMOS_CONTAINER',                         value: cosmosContainerName }
        { name: 'WEBAPP_BASE_URL',                          value: 'https://${appName}.azurewebsites.net' }
        { name: 'APP_LOG_LEVEL',                            value: 'Information' }
      ]
    }
  }
}
