// infra/modules/images.bicep
targetScope = 'resourceGroup'

@description('Global name-prefix, e.g. "cursus-test1" (used to derive a unique storage account name)')
param prefix string

@description('Azure region')
param location string = resourceGroup().location

// ─────────────────────────────────────────────────────────────────────────────
// Storage account naming: 3–24 lowercase letters & numbers only. We derive
// from prefix, strip dashes, add "img" and a short unique suffix.
// Example: prefix=cursus-test1 → cursusTest1 → cursustest1imgabc123
// Final length is trimmed to 24 to satisfy platform constraints.
// ─────────────────────────────────────────────────────────────────────────────
var base          = toLower(replace(prefix, '-', ''))
var suffix        = substring(uniqueString(resourceGroup().id), 0, 6)
var proposed      = '${base}img${suffix}'
var imagesAccountName = length(proposed) <= 24 ? proposed : substring(proposed, 0, 24)

// ─────────────────────────────────────────────────────────────────────────────
// Storage Account (V2, LRS). We keep it private (no blob public access).
// ─────────────────────────────────────────────────────────────────────────────
resource imagesAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
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
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

// Default Blob service (required parent for containers)
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  name: '${imagesAccount.name}/default'
  properties: {
    // Optional: soft delete, versioning etc. can be enabled later.
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Private container for user avatars
// ─────────────────────────────────────────────────────────────────────────────
@description('Name of the private container for user avatars')
param avatarsContainerName string = 'avatars'

resource avatarsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  name: '${imagesAccount.name}/${blobService.name}:${avatarsContainerName}'
  properties: {
    publicAccess: 'None' // keep container private
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Outputs (consumed by infra/main.bicep → webapp + role assignments)
// ─────────────────────────────────────────────────────────────────────────────
output imagesAccountNameOut string = imagesAccount.name
output imagesAccountIdOut   string = imagesAccount.id
output avatarsContainerNameOut string = avatarsContainerName
output avatarsContainerIdOut   string = avatarsContainer.id
