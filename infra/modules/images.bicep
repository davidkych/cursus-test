// infra/modules/images.bicep
targetScope = 'resourceGroup'

@description('Azure region')
param location string

@description('Globally-unique Storage Account name for images (letters & digits only, 3–24 chars)')
param imagesAccountName string

@description('Blob container names to create (all private). Defaults include the avatars container.')
param containerNames array = [
  'avatars'
]

/* ────────────────────────────────────────────────────────────────────────────
   Storage Account (StorageV2) – private blobs, TLS1_2, HTTPS-only
   This account is intended to host user-uploaded images (e.g., avatars),
   and can be expanded later with additional containers via `containerNames`.
   ──────────────────────────────────────────────────────────────────────────── */
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
    accessTier: 'Hot'
    encryption: {
      keySource: 'Microsoft.Storage'
      services: {
        blob: {
          enabled: true
        }
      }
    }
  }
}

/* Use parent-property syntax for child resources (no linter warnings) */
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  name: 'default'
  parent: imagesAccount
  properties: {}
}

/* Create each requested private container (no public access) */
resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = [for cname in containerNames: {
  name: cname
  parent: blobService
  properties: {
    publicAccess: 'None'
  }
}]

/* ────────────────────────────────────────────────────────────────────────────
   Outputs
   ──────────────────────────────────────────────────────────────────────────── */
output imagesAccountNameOut string = imagesAccount.name
output imagesAccountId      string = imagesAccount.id
output imagesBlobEndpoint   string = imagesAccount.properties.primaryEndpoints.blob
