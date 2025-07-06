// modules/plan.bicep
param location    string
param planSkuName string
param planName    string

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

output planId   string = plan.id
output planName string = plan.name
