// infra/modules/maps.bicep
targetScope = 'resourceGroup'

@description('Azure region (ignored by Azure Maps; resource is global)')
param location string

@description('Azure Maps account name (must be globally unique)')
param mapsAccountName string

@description('SKU name for Azure Maps (Gen2)')
@allowed([
  'G2'
])
param skuName string = 'G2'

@description('Kind for Azure Maps')
@allowed([
  'Gen2'
])
param kind string = 'Gen2'

/*
  Azure Maps is a GLOBAL resource. The RP requires location = "global".
  See: Microsoft.Maps/accounts API (2023-06-01)
*/
resource maps 'Microsoft.Maps/accounts@2023-06-01' = {
  name: mapsAccountName
  location: 'global'
  sku: {
    name: skuName
  }
  kind: kind
  // No additional properties required for a basic account
}

/*
  Output the account name and the primary key so the parent template
  can inject the key into your Web App app settings in the same deployment.
  (Note: This surfaces a secret to the parent template scope.)
*/
output mapsAccountName string = maps.name
output mapsPrimaryKey string = listKeys(maps.id, '2023-06-01').primaryKey
