<# 
Fix avatar upload 403 by granting data-plane RBAC to the Web App's MSI on the images Storage Account.
- Assigns:
    • Storage Blob Data Contributor   (required for uploads)
    • Storage Blob Data Delegator     (enables SAS via user delegation key)
- Verifies assignments (including inherited) and waits for propagation.

Run (override defaults as needed):
  .\grant-storage-rbac.ps1 -RG "cursus-test1-rg" -App "cursus-test1-app" -Images "cursustest1imgkhavcd"
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory = $false)][string]$RG     = "cursus-test1-rg",
  [Parameter(Mandatory = $false)][string]$App    = "cursus-test1-app",
  [Parameter(Mandatory = $false)][string]$Images = "cursustest1imgkhavcd",
  [Parameter(Mandatory = $false)][int]$VerifyTimeoutSec = 180,
  [Parameter(Mandatory = $false)][int]$VerifyIntervalSec = 6
)

$ErrorActionPreference = 'Stop'

function W-Section([string]$t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function W-OK([string]$t)      { Write-Host "✔ $t" -ForegroundColor Green }
function W-Warn([string]$t)    { Write-Host "⚠ $t" -ForegroundColor Yellow }
function W-Err([string]$t)     { Write-Host "✖ $t" -ForegroundColor Red }

function Require-Az() {
  W-Section "Azure CLI context"
  try {
    $who = az account show --only-show-errors | ConvertFrom-Json
    if (-not $who) { throw "Not logged in." }
    W-OK ("Logged in as: {0} (sub: {1})" -f $who.user.name, $who.id)
  }
  catch {
    W-Err "Not logged in. Run: az login"
    throw
  }
}

function Get-MsiPrincipalId([string]$ResourceGroup, [string]$WebAppName) {
  W-Section "Resolve Web App MSI"
  $msi = az webapp identity show -g $ResourceGroup -n $WebAppName --only-show-errors | ConvertFrom-Json
  $principalId = $msi.principalId
  if ([string]::IsNullOrWhiteSpace($principalId)) {
    W-Err "System-assigned identity is NOT enabled on the Web App '$WebAppName'. Enable it first."
    throw "MSI missing"
  }
  W-OK "MSI principalId: $principalId"
  return $principalId
}

function Get-StorageScope([string]$ResourceGroup, [string]$AccountName) {
  W-Section "Resolve Storage Account scope"
  $st = az storage account show -g $ResourceGroup -n $AccountName --only-show-errors | ConvertFrom-Json
  if (-not $st) {
    W-Err "Storage account '$AccountName' in RG '$ResourceGroup' not found."
    throw "Storage not found"
  }
  $scope = $st.id
  W-OK "Storage account id: $scope"
  Write-Host ("Sku: {0}  Kind: {1}  Location: {2}" -f $st.sku.name, $st.kind, $st.location)
  return $scope
}

function Test-RolePresent([string]$PrincipalId, [string]$Scope, [string]$RoleName) {
  # Check assignments that apply to the storage scope (including inherited).
  $res = az role assignment list --assignee $PrincipalId --include-inherited --all --only-show-errors `
    --query "[?roleDefinitionName=='$RoleName' && starts_with(scope, '$Scope')].id" -o tsv
  return -not [string]::IsNullOrWhiteSpace(($res | Out-String).Trim())
}

function Ensure-Role([string]$PrincipalId, [string]$Scope, [string]$RoleName) {
  if (Test-RolePresent -PrincipalId $PrincipalId -Scope $Scope -RoleName $RoleName) {
    W-OK "Role already present: '$RoleName' on $Scope"
    return
  }
  W-Section "Grant role: $RoleName"
  try {
    az role assignment create --assignee $PrincipalId --role "$RoleName" --scope $Scope --only-show-errors | Out-Null
    W-OK "Assignment created"
  }
  catch {
    W-Err "Failed to create role assignment ($RoleName)."
    W-Warn "If the error is AuthorizationFailed, your current identity lacks 'Microsoft.Authorization/roleAssignments/write'."
    throw
  }
}

function Wait-For-Roles([string]$PrincipalId, [string]$Scope, [string[]]$Roles, [int]$TimeoutSec, [int]$IntervalSec) {
  W-Section "Verify RBAC propagation"
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  do {
    $allOk = $true
    foreach ($r in $Roles) {
      if (-not (Test-RolePresent -PrincipalId $PrincipalId -Scope $Scope -RoleName $r)) {
        $allOk = $false
        break
      }
    }
    if ($allOk) {
      W-OK "All required roles effective on scope."
      return $true
    }
    Start-Sleep -Seconds $IntervalSec
  } while ((Get-Date) -lt $deadline)

  # Print what we do see for debugging
  W-Err "Timed out waiting for RBAC propagation."
  Write-Host "Current assignments (filtered to storage scope):"
  az role assignment list --assignee $PrincipalId --include-inherited --all --only-show-errors `
    --query "[?starts_with(scope, '$Scope')].[roleDefinitionName, scope]" -o table
  return $false
}

# ─────────────────────────────────────────────────────────────────────────────

Require-Az

$principalId = Get-MsiPrincipalId -ResourceGroup $RG -WebAppName $App
$scope       = Get-StorageScope    -ResourceGroup $RG -AccountName $Images

$requiredRoles = @(
  'Storage Blob Data Contributor', # required for upload
  'Storage Blob Data Delegator'    # enables SAS via user delegation key
)

foreach ($role in $requiredRoles) {
  Ensure-Role -PrincipalId $principalId -Scope $scope -RoleName $role
}

if (-not (Wait-For-Roles -PrincipalId $principalId -Scope $scope -Roles $requiredRoles -TimeoutSec $VerifyTimeoutSec -IntervalSec $VerifyIntervalSec)) {
  exit 1
}

# Final summary
W-Section "Summary"
W-OK "MSI on Web App '$App' now has:"
$summary = az role assignment list --assignee $principalId --include-inherited --all --only-show-errors `
  --query "[?starts_with(scope, '$scope') && (roleDefinitionName=='Storage Blob Data Contributor' || roleDefinitionName=='Storage Blob Data Delegator' || roleDefinitionName=='Storage Blob Data Owner')].[roleDefinitionName, scope]" -o table
$summary | Out-String | Write-Host

W-OK "You can re-try the avatar upload now. If it still fails, wait a minute for RBAC propagation and try again."
