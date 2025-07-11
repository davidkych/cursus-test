# DurableSchedulerSmokeTest.ps1
# -------------------------------------------------
# End‑to‑end smoke tests for the FastAPI façade and
# the Durable scheduler Function‑App.  The script
# exercises **all** public functionality end‑to‑end
# and prints every server response so that failures
# are obvious in CI logs.
#
# Usage (interactive or CI pipeline):
#   pwsh -File DurableSchedulerSmokeTest.ps1 \
#        -BaseUrl "https://cursus-test-app.azurewebsites.net" \
#        -SchedulerBase "https://cursus-test-sched.azurewebsites.net"
#
# If parameters are omitted, the script falls back to
# environment variables BASE_URL / SCHEDULER_BASE.
# -------------------------------------------------
param(
    [Parameter()][ValidateNotNullOrEmpty()][string]$BaseUrl = $env:BASE_URL,
    [Parameter()][ValidateNotNullOrEmpty()][string]$SchedulerBase = $env:SCHEDULER_BASE
)

if (-not $BaseUrl) {
    throw "BaseUrl not provided (parameter or \$env:BASE_URL required)"
}
if (-not $SchedulerBase) {
    throw "SchedulerBase not provided (parameter or \$env:SCHEDULER_BASE required)"
}

# Ensure URLs have no trailing slashes so we can safely append paths
$BaseUrl       = $BaseUrl.TrimEnd('/')
$SchedulerBase = $SchedulerBase.TrimEnd('/')

Write-Host "ℹ️  BaseUrl       = $BaseUrl"
Write-Host "ℹ️  SchedulerBase = $SchedulerBase"

# --- helper: pretty JSON without external deps ------------------------
function Format-Json {
    param([Parameter(ValueFromPipeline)][string]$Json)
    $obj = $Json | ConvertFrom-Json -Depth 100
    return ($obj | ConvertTo-Json -Depth 100 -Compress:$false)
}

# --- helper: invoke REST and echo request + response ------------------
function Invoke-SmokeRequest {
    param(
        [Parameter(Mandatory)][ValidateSet('GET','POST','DELETE')][string]$Method,
        [Parameter(Mandatory)][string]$Url,
        [object]$Body = $null
    )
    Write-Host "\n── $Method $Url" -ForegroundColor Cyan
    if ($Body) {
        $jsonBody = $Body | ConvertTo-Json -Depth 20 -Compress:$false
        Write-Host "» Request body:" -ForegroundColor DarkGray
        Write-Host ($jsonBody | Format-Json)
    }

    try {
        if ($Body) {
            $response = Invoke-WebRequest -Method $Method -Uri $Url -ContentType 'application/json' -Body ($Body | ConvertTo-Json -Depth 20) -UseBasicParsing -TimeoutSec 30
        }
        else {
            $response = Invoke-WebRequest -Method $Method -Uri $Url -UseBasicParsing -TimeoutSec 30
        }
    }
    catch {
        Write-Host "❌ Request failed: $_" -ForegroundColor Red
        throw
    }

    Write-Host "« Status: $($response.StatusCode)" -ForegroundColor DarkGray
    if ($response.Content) {
        Write-Host "« Response body:" -ForegroundColor DarkGray
        Write-Host ($response.Content | Format-Json)
    }

    # Attempt to parse JSON, fall back to raw
    try { return $response.Content | ConvertFrom-Json -Depth 100 } catch { return $response.Content }
}

# --- helper: UTC ISO‑8601 (+00:00) -----------------------------------
function Get-IsoUtc {
    param([int]$MinutesAhead = 2)
    $ts = (Get-Date).AddMinutes($MinutesAhead).ToUniversalTime()
    # .NET custom format cannot emit "+00:00", so append manually
    return $ts.ToString('yyyy-MM-dd''T''HH:mm:ss') + '+00:00'
}

# --- helper: poll Durable status until Completed/Failed/Terminated ----
function Wait-ForCompletion {
    param(
        [Parameter(Mandatory)][string]$StatusUrl,
        [Parameter()][int]$TimeoutSec = 300,
        [Parameter()][int]$PollInterval = 10
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        $stat = Invoke-SmokeRequest -Method GET -Url $StatusUrl
        $runtime = $stat.runtimeStatus
        Write-Host "·· runtimeStatus = $runtime" -ForegroundColor Yellow
        if ($runtime -in @('Completed','Failed','Terminated')) { return $stat }
        Start-Sleep -Seconds $PollInterval
    } while ((Get-Date) -lt $deadline)
    throw "Timeout waiting for orchestration to finish"
}

# =====================================================================
# 1) WIPE all existing schedules --------------------------------------
# =====================================================================
Invoke-SmokeRequest -Method DELETE -Url "$BaseUrl/api/schedule"

# =====================================================================
# 2) HEALTH CHECKS -----------------------------------------------------
# =====================================================================
Invoke-SmokeRequest -Method GET -Url "$BaseUrl/healthz"
Invoke-SmokeRequest -Method GET -Url "$SchedulerBase/api/healthz"

# =====================================================================
# 3) CREATE **and cancel** a schedule ---------------------------------
# =====================================================================
$execCancel = Get-IsoUtc -MinutesAhead 5
$cancelReq = @{
    exec_at     = $execCancel
    prompt_type = 'log.append'
    payload     = @{ tag = 'smoke'; base = 'info'; message = 'cancel-demo' }
    tag          = 'smoke'
    secondary_tag= 'cancel'
}
$cancelResp = Invoke-SmokeRequest -Method POST -Url "$BaseUrl/api/schedule" -Body $cancelReq
$cancelId   = $cancelResp.transaction_id
if (-not $cancelId) { throw "transaction_id not returned" }
# Delete it immediately
Invoke-SmokeRequest -Method DELETE -Url "$BaseUrl/api/schedule/$cancelId"

# =====================================================================
# 4) FASTAPI schedule, run in 2 min -----------------------------------
# =====================================================================
$execFast = Get-IsoUtc -MinutesAhead 2
$fastReq = @{
    exec_at     = $execFast
    prompt_type = 'log.append'
    payload     = @{ tag = 'smoke'; base = 'info'; message = 'fastapi-2min' }
    tag          = 'fastapi'
    secondary_tag= 'smoke'
}
$fastResp = Invoke-SmokeRequest -Method POST -Url "$BaseUrl/api/schedule" -Body $fastReq
$fastId   = $fastResp.transaction_id
if (-not $fastId) { throw "transaction_id missing from schedule response" }

# 4a) verify tag metadata via status
$statusUrlFast = "$BaseUrl/api/schedule/$fastId/status"
Invoke-SmokeRequest -Method GET -Url $statusUrlFast | Out-Null

# 4b) poll until finished
Wait-ForCompletion -StatusUrl $statusUrlFast -TimeoutSec 240

# =====================================================================
# 5) LIST schedules after execution -----------------------------------
# =====================================================================
Invoke-SmokeRequest -Method GET -Url "$BaseUrl/api/schedule"

# =====================================================================
# 6) PUBLIC API (scheduler) schedule ----------------------------------
# =====================================================================
$execSched = Get-IsoUtc -MinutesAhead 2
$schedReq = @{
    exec_at     = $execSched
    prompt_type = 'log.append'
    payload     = @{ tag = 'smoke'; base = 'info'; message = 'scheduler-2min' }
    tag          = 'scheduler'
    secondary_tag= 'smoke'
}
$schedResp = Invoke-SmokeRequest -Method POST -Url "$SchedulerBase/api/schedule" -Body $schedReq
$schedId   = $schedResp.id  # scheduler returns {"id": "..."}
if (-not $schedId) { throw "id missing in scheduler response" }

# 6a) verify tag metadata via status
$statusUrlSched = "$SchedulerBase/api/status/$schedId"
Invoke-SmokeRequest -Method GET -Url $statusUrlSched | Out-Null

# 6b) poll until finished
Wait-ForCompletion -StatusUrl $statusUrlSched -TimeoutSec 240

# =====================================================================
# 7) FINAL wipe --------------------------------------------------------
# =====================================================================
Invoke-SmokeRequest -Method DELETE -Url "$BaseUrl/api/schedule"

Write-Host "\n🎉 Smoke tests completed successfully" -ForegroundColor Green
