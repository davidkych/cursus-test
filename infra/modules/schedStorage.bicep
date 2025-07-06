// modules/schedStorage.bicep
param location         string
param schedStorageName string

resource schedStorage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name:     schedStorageName
  location: location
  kind:     'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion:        'TLS1_2'
    allowBlobPublicAccess:    false
    supportsHttpsTrafficOnly: true
  }
}

var schedStorageKey       = schedStorage.listKeys().keys[0].value
var storageConnection     = 'DefaultEndpointsProtocol=https;AccountName=${schedStorage.name};AccountKey=${schedStorageKey};EndpointSuffix=${environment().suffixes.storage}'

output storageConnection string = storageConnection
output storageAccountId  string = schedStorage.id
