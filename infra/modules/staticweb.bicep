targetScope = 'resourceGroup'

@description('Azure region')
param location string

@description('Static Web App name (globally unique)')
param staticSiteName string

resource staticSite 'Microsoft.Web/staticSites@2023-01-01' = {
  name: staticSiteName
  location: location
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    allowConfigFileUpdates: true
  }
}

output staticSiteName     string = staticSite.name
output staticSiteHostname string = staticSite.properties.defaultHostname
