// infra/modules/images.bicep
// Dedicated Storage Account for images (e.g., avatars). Private by default.
//
// Notes:
// - No public access; HTTPS only.
// - Container `avatars` is private (no anonymous list/read).
// - We do NOT grant any roles here; wire MSI role assignments in main.bicep
//   where the Web App principal is known.

targetScope = 'resourceGroup'

@description('Azure region')
param location string

@description('Globally unique Storage Account name (lowercase, 3–24 alphanum).')
param imagesAccountName string

@description('Blob container name for user avatars.')
@minLength(3)
param avatarsContainerName string = 'avatars'

// -----------------------------------------------------------------------------
// Storage Account (general-purpose v2, Standard_LRS)
// -----------------------------------------------------------------------------
resource imagesAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: imagesAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false         // prefer AAD (MSI) + user-delegation SAS
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    encryption: {
      services: {
        blob: {
          enabled: true
        }
      }
      keySource: 'Microsoft.Storage'
    }
  }
}

// Default Blob service (parent for containers)
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  name: '${imagesAccount.name}/default'
  properties: {
    // Keep defaults (e.g., no soft-delete tuning here). Can be extended later.
  }
}

// Private avatars container
resource avatars 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  name: avatarsContainerName
  parent: blobService
  properties: {
    publicAccess: 'None'   // private container
  }
}

// -----------------------------------------------------------------------------
// Outputs
// -----------------------------------------------------------------------------
@description('Images Storage Account name')
output imagesAccountName string = imagesAccount.name

@description('Images Storage Account resource ID')
output imagesAccountResourceId string = imagesAccount.id

@description('Private container name for avatars')
output avatarsContainerName string = avatars.name

@description('Blob endpoint base URL (no trailing slash)')
output blobEndpoint string = 'https://${imagesAccount.name}.blob.core.windows.net'
