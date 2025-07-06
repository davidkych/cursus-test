// modules/webapp.bicep
param location              string
param appName               string
param planId                string
param timeout               int
param cosmosEndpoint        string
param cosmosDatabaseName    string
param cosmosContainerName   string
param schedFuncName         string

resource app 'Microsoft.Web/sites@2023-01-01' = {
  name:     appName
  location: location
  kind:     'app,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: planId
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.9'
      appCommandLine: 'gunicorn --log-level info --worker-class uvicorn.workers.UvicornWorker --workers 2 --bind 0.0.0.0:8000 main:app'
      healthCheckPath: '/healthz'
      appSettings: [
        { name: 'WEBSITES_PORT',                       value: '8000' }
        { name: 'WEBSITES_CONTAINER_START_TIME_LIMIT', value: string(timeout) }
        { name: 'COSMOS_ENDPOINT',                     value: cosmosEndpoint }
        { name: 'COSMOS_DATABASE',                     value: cosmosDatabaseName }
        { name: 'COSMOS_CONTAINER',                    value: cosmosContainerName }
        { name: 'SCHEDULER_BASE_URL',                  value: 'https://${schedFuncName}.azurewebsites.net' }
        { name: 'SCHEDULER_FUNCTION_NAME',             value: schedFuncName }
      ]
    }
  }
  dependsOn: [
    // Ensure container exists before deploying app
  ]
}
