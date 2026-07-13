$ErrorActionPreference = 'Stop'

$out = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifestPath = Join-Path $out 'all80_bounded_delta_official_route_manifest.csv'
$cacheDir = Join-Path (Split-Path -Parent $out) '_all80d_legacy_cache_20260713'
$progressPath = Join-Path $out 'twse_legacy_fallback_progress.json'
$stepPath = Join-Path $out 'current_step.txt'
$tracePath = Join-Path $out 'twse_legacy_fallback_trace.log'

if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Missing route manifest: $manifestPath"
}
New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null

$routes = @(Import-Csv -LiteralPath $manifestPath | Where-Object {
    $_.market -eq 'TWSE' -and $_.outcome -eq 'source_route_failed'
})
$total = $routes.Count
$completed = 0
$accepted = 0
$blocked = 0

foreach ($route in $routes) {
    $completed++
    $ticker = $route.ticker
    $month = $route.year_month
    $requested = $month.Replace('-', '') + '01'
    $cache = Join-Path $cacheDir ($route.route_id + '.legacy.json')
    $status = 'blocked'
    $errorText = ''
    "$(Get-Date -Format o) start $($route.route_id)" | Add-Content -LiteralPath $tracePath -Encoding UTF8

    if (Test-Path -LiteralPath $cache) {
        try {
            $payload = Get-Content -LiteralPath $cache -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($payload.stat -eq 'OK' -and [string]$payload.date -eq $requested) {
                $status = 'accepted_cache_reuse'
            } else {
                $errorText = 'cached_payload_schema_or_month_mismatch'
            }
        } catch {
            $errorText = 'cached_payload_parse_failed:' + $_.Exception.GetType().Name
        }
    }

    if ($status -eq 'blocked') {
        $url = 'https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=' + $requested + '&stockNo=' + $ticker
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            try {
                "$(Get-Date -Format o) request $($route.route_id) attempt=$attempt" | Add-Content -LiteralPath $tracePath -Encoding UTF8
                $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 30 -Headers @{
                    'User-Agent' = 'Mozilla/5.0 RadarAll80Delta/1.0'
                    'Referer' = 'https://www.twse.com.tw/'
                    'Accept-Language' = 'zh-TW,zh;q=0.9,en;q=0.7'
                }
                $payload = $response.Content | ConvertFrom-Json
                if ($payload.stat -ne 'OK' -or [string]$payload.date -ne $requested) {
                    throw 'official_payload_schema_or_month_mismatch'
                }
                $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($response.Content)
                $tmp = Join-Path $cacheDir ('.p' + $PID + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.tmp')
                [System.IO.File]::WriteAllBytes($tmp, $bytes)
                Move-Item -LiteralPath $tmp -Destination $cache -Force
                $status = 'accepted_new_official_legacy'
                $errorText = ''
                "$(Get-Date -Format o) accepted $($route.route_id) bytes=$($bytes.Length)" | Add-Content -LiteralPath $tracePath -Encoding UTF8
                break
            } catch {
                $errorText = $_.Exception.Message
                "$(Get-Date -Format o) error $($route.route_id) attempt=$attempt $errorText" | Add-Content -LiteralPath $tracePath -Encoding UTF8
                Start-Sleep -Seconds $attempt
            }
        }
    }

    if ($status -like 'accepted*') { $accepted++ } else { $blocked++ }
    if (($completed % 20) -eq 0 -or $completed -eq $total) {
        $progress = [ordered]@{
            task_id = 'TASK-RADAR-DATA-VNEXT-P3-LAYER5-ALL80-CONTINUOUS-LIFECYCLE-ADJUSTED-HLC-BOUNDED-DELTA-ACQUISITION-001'
            family = 'twse_legacy_failed_only_fallback'
            status = if ($completed -eq $total) { 'completed' } else { 'running' }
            completed = $completed
            total = $total
            accepted = $accepted
            blocked = $blocked
            cursor = "$ticker/$month"
            last_error = $errorText
            updated_at = [DateTimeOffset]::UtcNow.ToString('o')
            resume_command = 'pwsh -File repair_twse_legacy_fallback.ps1'
        }
        $progress | ConvertTo-Json | Set-Content -LiteralPath $progressPath -Encoding UTF8
        "twse_legacy_failed_only_fallback $completed/$total accepted=$accepted blocked=$blocked $ticker/$month" | Set-Content -LiteralPath $stepPath -Encoding UTF8
    }
    Start-Sleep -Milliseconds 120
}
