// infra/modules/images.bicep
targetScope = 'resourceGroup'

@description('Azure region')
param location string

@description('Images Storage Account name (globally unique, lowercase, 3–24 chars)')
param imagesAccountName string

// Optional future-proofing: allow overriding container name, default to "avatars"
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
    // Default network rules (public Internet allowed). If you later need
    // private networking, add VNets and integrate the Web App accordingly.
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

// Blob service (implicit "default")
resource blob 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  name: '${imagesSa.name}/default'
  properties: {
    // leave defaults
  }
}

// Private container for avatars
resource avatars 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  name: '${imagesSa.name}/${blob.name}/' + avatarsContainerName
  properties: {
    publicAccess: 'None'
    metadata: {
      purpose: 'user-avatars'
    }
  }
}

output imagesAccountName     string = imagesSa.name
output imagesAccountId       string = imagesSa.id
output avatarsContainerName  string = avatarsContainerName
output blobEndpoint          string = imagesSa.properties.primaryEndpoints.blob
