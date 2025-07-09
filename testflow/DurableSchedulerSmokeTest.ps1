workflow DurableSchedulerSmokeTest {
    param(
        [string] $WebAppBase    = "https://cursus-test-app.azurewebsites.net",
        [string] $SchedFuncBase = "https://cursus-test-sched.azurewebsites.net",
        [string] $TZOffset      = "+08:00",
        [int]    $PollInterval  = 60,
        [int]    $PollLoops     = 18
    )

    InlineScript {
        # Pull in workflow parameters
        $webAppBase    = $Using:WebAppBase
        $schedFuncBase = $Using:SchedFuncBase
        $tzOffset      = $Using:TZOffset
        $PollInterval  = $Using:PollInterval
        $PollLoops     = $Using:PollLoops

        Write-Host "🌐 FastAPI   =" $webAppBase
        Write-Host "⚙️  Scheduler =" $schedFuncBase
        Write-Host ""

        # ── helpers ─────────────────────────────────────────────────────
        function Format-Json {
            param([Parameter(Mandatory)][string]$Json)
            try   { $Json | ConvertFrom-Json | ConvertTo-Json -Depth 20 }
            catch { $Json }
        }

        function Invoke-AndShow {
            param(
                [Parameter(Mandatory)][ValidateSet('GET','POST','DELETE')]$Method,
                [Parameter(Mandatory)][string]$Uri,
                [string]$Body
            )

            $params = @{
                Method      = $Method
                Uri         = $Uri
                TimeoutSec  = 30
                ErrorAction = 'Stop'
            }
            if ($Body) { $params.Body = $Body; $params.ContentType = 'application/json' }
            if ($PSVersionTable.PSVersion.Major -lt 6) { $params.UseBasicParsing = $true }

            try {
                $resp    = Invoke-WebRequest @params
                $status  = $resp.StatusCode
                $content = $resp.Content
            } catch {
                $ex      = $_.Exception
                $r       = $ex.Response
                if ($r -and $r.GetResponseStream()) {
                    $status  = [int]$r.StatusCode
                    $reader  = [IO.StreamReader]::new($r.GetResponseStream())
                    $content = $reader.ReadToEnd()
                } else {
                    $status  = 'n/a'
                    $content = $ex.Message
                }
            }

            Write-Host "`n$Method $Uri" -ForegroundColor Yellow
            Write-Host "HTTP $status"    -ForegroundColor Magenta
            if ($content) {
                Format-Json $content | ForEach-Object { Write-Host $_ }
                Write-Host ""
            }

            try { return $content | ConvertFrom-Json } catch { return $null }
        }

        # ── 1. CLEAN SLATE (wipe all existing jobs) ───────────────────────
        Invoke-AndShow DELETE "$webAppBase/api/schedule" | Out-Null

        # ── 2. HEALTH CHECKS ────────────────────────────────────────────
        Write-Host "`n🔎  Health probes" -ForegroundColor Cyan
        Invoke-AndShow GET "$webAppBase/healthz"        | Out-Null
        Invoke-AndShow GET "$schedFuncBase/api/healthz" | Out-Null

        # ── 3. CREATE & CANCEL a schedule (5 min in future) ─────────────
        Write-Host "`n🗑️  3. Create > cancel" -ForegroundColor Cyan
        $execAtCancel = (Get-Date).AddMinutes(5).ToString("yyyy-MM-ddTHH:mm:ss") + $tzOffset
        $bodyCancel   = @{
            exec_at     = $execAtCancel
            prompt_type = "log.append"
            payload     = @{ tag='demo'; base='info'; message='cancel-me' }
        } | ConvertTo-Json -Depth 10

        $resp      = Invoke-AndShow POST "$webAppBase/api/schedule" $bodyCancel
        $cancelId  = $resp.transaction_id
        if (-not $cancelId) { Write-Warning "❌ cancel-test creation failed"; exit }

        Invoke-AndShow DELETE "$webAppBase/api/schedule/$cancelId" | Out-Null

        # ── 4. CREATE schedule to actually fire (2 min) ─────────────────
        Write-Host "`n📝  4. Create schedule (fires in 2 min)" -ForegroundColor Cyan
        $execAt = (Get-Date).AddMinutes(2).ToString("yyyy-MM-ddTHH:mm:ss") + $tzOffset
        $body   = @{
            exec_at     = $execAt
            prompt_type = "log.append"
            payload     = @{ tag='demo'; base='info'; message='Hello from PS smoke test' }
        } | ConvertTo-Json -Depth 10

        $resp       = Invoke-AndShow POST "$webAppBase/api/schedule" $body
        $instanceId = $resp.transaction_id
        if (-not $instanceId) { Write-Warning "❌ schedule creation failed"; exit }

        # ── 5. POLL until Completed / Failed / Terminated ────────────────
        Write-Host "`n📡  5. Poll status until Completed" -ForegroundColor Cyan
        $pollUrl    = "$webAppBase/api/schedule/$instanceId/status"
        $execAtDto  = [DateTimeOffset]::Parse($execAt)
        $deadline   = $execAtDto.ToUniversalTime().AddMinutes(10)

        while ([DateTimeOffset]::UtcNow -lt $deadline) {
            $stat = Invoke-AndShow GET $pollUrl
            if ($stat -and $stat.runtimeStatus -in 'Completed','Failed','Terminated') {
                break
            }
            Start-Sleep -Seconds $PollInterval
        }

        # ── 6. LIST ALL schedules ───────────────────────────────────────
        Write-Host "`n📄  6. List schedules" -ForegroundColor Cyan
        Invoke-AndShow GET "$webAppBase/api/schedule" | Out-Null

        # ── 7. NEW TEST: schedule public API call (fires in 2 min) ─────
        Write-Host "`n🌐  7. Schedule public API (fires in 2 min)" -ForegroundColor Cyan
        $execAtPub   = (Get-Date).AddMinutes(2).ToString("yyyy-MM-ddTHH:mm:ss") + $tzOffset
        $bodyPub     = @{
            exec_at     = $execAtPub
            prompt_type = "http.call"
            payload     = @{
                url     = "https://httpbin.org/get"
                method  = "GET"
                headers = @{}
                timeout = 10
            }
        } | ConvertTo-Json -Depth 10

        $respPub     = Invoke-AndShow POST "$webAppBase/api/schedule" $bodyPub
        $pubInstance = $respPub.transaction_id
        if (-not $pubInstance) { Write-Warning "❌ public-api-test creation failed"; exit }

        Write-Host "`n📡  7.1 Poll public API status until Completed" -ForegroundColor Cyan
        $pollPubUrl   = "$webAppBase/api/schedule/$pubInstance/status"
        $execAtPubDto = [DateTimeOffset]::Parse($execAtPub)
        $deadlinePub  = $execAtPubDto.ToUniversalTime().AddMinutes(10)

        while ([DateTimeOffset]::UtcNow -lt $deadlinePub) {
            $statPub = Invoke-AndShow GET $pollPubUrl
            if ($statPub -and $statPub.runtimeStatus -in 'Completed','Failed','Terminated') {
                Write-Host "`n🚀 Public API job status:" $statPub.runtimeStatus
                break
            }
            Start-Sleep -Seconds $PollInterval
        }

        # ── 8. WIPE everything again (cleanup) ───────────────────────────
        Write-Host "`n🧹  8. Final wipe-all" -ForegroundColor Cyan
        Invoke-AndShow DELETE "$webAppBase/api/schedule" | Out-Null

        Write-Host "`n✅  Smoke test finished" -ForegroundColor Green
    }
}

# To run:
# .\DurableSchedulerSmokeTest.ps1
# DurableSchedulerSmokeTest
