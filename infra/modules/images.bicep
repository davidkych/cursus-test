// infra/modules/images.bicep
targetScope = 'resourceGroup'

@description('Azure region')
param location string

@description('Images Storage Account name (globally unique, lowercase, 3–24 chars)')
param imagesAccountName string

@description('Blob container for user avatars')
param avatarsContainerName string = 'avatars'

/*
  Storage Account for private images (avatars now, expandable later)
  - Standard_LRS, StorageV2
  - HTTPS only, TLS1.2+, no public blob access
*/
resource imagesSa 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: imagesAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    accessTier: 'Hot'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
    encryption: {
      services: {
        blob: {
          enabled: true
        }
        file: {
          enabled: true
        }
      }
      keySource: 'Microsoft.Storage'
    }
  }
}

// Blob service (default) using parent syntax
resource blob 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  name: 'default'
  parent: imagesSa
}

// Private container for avatars (parent syntax)
resource avatars 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  name: avatarsContainerName
  parent: blob
  properties: {
    publicAccess: 'None'
    metadata: {
      purpose: 'user-avatars'
    }
  }
}

output imagesAccountName     string = imagesSa.name
output imagesAccountId       string = imagesSa.id
output avatarsContainerName  string = avatars.name
output blobEndpoint          string = imagesSa.properties.primaryEndpoints.blob
