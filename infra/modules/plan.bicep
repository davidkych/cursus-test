// modules/plan.bicep
targetScope = 'resourceGroup'

@description('Azure region')
param location string

@description('App-Service plan SKU (B1, S1, P1v2 …)')
param planSkuName string

@description('Name of the app (used for plan naming)')
param appName string

resource plan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: '${appName}-plan'
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

output planId string = plan.id
output planName string = plan.name
