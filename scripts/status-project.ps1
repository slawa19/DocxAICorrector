. $PSScriptRoot\_shared.ps1

try {
    Write-Step 'Checking project status and environment'
    $preferredRuntimeMode = Get-PreferredRuntimeMode
    if ($preferredRuntimeMode -eq 'wsl' -and -not (Test-Path $wslControlScript)) { throw "WSL helper script not found: $wslControlScript" }

    $status = Get-ProjectStatus
    $runtimeMode = [string]$status['runtime_mode']
    $healthOk = ConvertTo-BoolFlag $status['health_ok']
    $appPageOk = ConvertTo-BoolFlag $status['app_page_ok']
    $managedPidRunning = ConvertTo-BoolFlag $status['managed_pid_running']
    $portOpen = ConvertTo-BoolFlag $status['port_open']
    $venvOk = ConvertTo-BoolFlag $status['venv_ok']
    $depsOk = ConvertTo-BoolFlag $status['deps_ok']
    $pandocOk = ConvertTo-BoolFlag $status['pandoc_ok']
    $apiKeyOk = ConvertTo-BoolFlag $status['api_key_ok']
    $managedPid = $status['managed_pid']

    if ($healthOk -and $appPageOk -and $managedPidRunning) {
        Write-Ok "Project is running. PID=$managedPid"
    }
    elseif ($managedPidRunning) {
        Write-Warn "Managed project process exists, but the app page is not fully ready yet"
    }
    elseif ($portOpen) {
        Write-Warn "Port $port is occupied by a foreign or unmanaged process"
    }
    else {
        Write-Ok 'Project is not running'
    }

    if ($venvOk) {
        Write-Ok 'Virtualenv found'
    }
    else {
        Write-Warn 'Virtualenv not found'
    }

    if ($depsOk) {
        Write-Ok 'Python dependencies are available'
    }
    else {
        Write-Warn 'Python dependencies are incomplete'
    }

    if ($pandocOk) {
        Write-Ok 'Pandoc is available'
    }
    else {
        Write-Warn 'Pandoc is unavailable'
    }

    if ($apiKeyOk) {
        Write-Ok 'OPENAI_API_KEY is configured'
    }
    else {
        Write-Warn 'OPENAI_API_KEY is not configured'
    }

    $finalStatus = 'READY'
    if ($managedPidRunning -and $healthOk -and $appPageOk) {
        $finalStatus = 'RUNNING'
    }
    elseif ($managedPidRunning) {
        $finalStatus = 'STARTING'
    }
    elseif ($portOpen) {
        $finalStatus = 'CONFLICT'
    }
    elseif (-not ($venvOk -and $depsOk -and $pandocOk -and $apiKeyOk)) {
        $finalStatus = 'DEGRADED'
    }

    Write-Host ''
    Write-Host '========================================' -ForegroundColor Cyan
    Write-Host "  Status: $finalStatus" -ForegroundColor Cyan
    Write-Host "  Runtime: $runtimeMode" -ForegroundColor Cyan
    Write-Host "  App: $appUrl" -ForegroundColor Cyan
    Write-Host "  Health: $appUrl/_stcore/health" -ForegroundColor Cyan
    Write-Host '========================================' -ForegroundColor Cyan
    Write-Host ''

    exit 0
}
catch {
    Write-Fail $_.Exception.Message
    Write-Host 'Status: FAILED' -ForegroundColor Red
    Write-Host "App: $appUrl" -ForegroundColor Yellow
    exit 1
}