// modules/schedDiag.bicep
param schedFuncName    string
param diagnosticName   string
param storageAccountId string

resource schedFuncDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name:  diagnosticName
  scope: resourceId('Microsoft.Web/sites', schedFuncName)
  properties: {
    storageAccountId: storageAccountId
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
