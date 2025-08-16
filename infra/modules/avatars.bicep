// infra/modules/avatars.bicep
// Dedicated Storage Account for user avatars (separate from any existing storage)
// - Creates a StorageV2 account
// - Creates a public-read "avatars" blob container
// - Leaves IAM (role assignment for Web App MSI) to the workflow step

targetScope = 'resourceGroup'

@description('Azure region')
param location string

@description('Globally unique storage account name (lowercase, 3–24 chars, letters & numbers)')
param avatarsAccountName string

@description('Blob container name to store avatars')
param containerName string = 'avatars'

// ─────────────────────────────────────────────────────────────────────────────
// Storage Account (gen2)
// ─────────────────────────────────────────────────────────────────────────────
resource avatarsStorage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: avatarsAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: true                // required to enable public-access containers
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowSharedKeyAccess: true                 // workflows may use key-based ops if needed
    accessTier: 'Hot'
    encryption: {
      services: {
        blob: {
          keyType: 'Account'
          enabled: true
        }
        file: {
          keyType: 'Account'
          enabled: true
        }
      }
      keySource: 'Microsoft.Storage'
    }
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

// Default blob service (parent for containers)
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  name: 'default'
  parent: avatarsStorage
  properties: {}
}

// Public-read container for avatars
resource avatarsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  name: containerName
  parent: blobService
  properties: {
    publicAccess: 'Blob'             // public read of blobs (no list)
    defaultEncryptionScope: 'blobEncryptionScope'
    denyEncryptionScopeOverride: false
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Outputs
// ─────────────────────────────────────────────────────────────────────────────
output avatarsAccountNameOut string = avatarsStorage.name
output avatarsContainerNameOut string = avatarsContainer.name
output avatarsPrimaryEndpoint string = 'https://${avatarsStorage.name}.blob.core.windows.net/${avatarsContainer.name}'
