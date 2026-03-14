. $PSScriptRoot\_shared.ps1

try {
    Write-Step 'Останавливаю проект'

    $status = Get-ProjectRuntimeStatus
    $portOpen = ConvertTo-BoolFlag $status['port_open']
    $managedPidRunning = ConvertTo-BoolFlag $status['managed_pid_running']

    if (-not $portOpen -and -not $managedPidRunning) {
        Write-Ok 'Проект уже остановлен'
        Write-Host 'Status: STOPPED' -ForegroundColor Green
        exit 0
    }

    if ($portOpen -and -not $managedPidRunning) {
        throw "Порт $port занят неуправляемым процессом. Stop Project останавливает только экземпляр, запущенный через scripts/start-project.ps1."
    }

    Stop-ManagedProject

    $stopped = $false
    for ($i = 1; $i -le 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (-not (Test-TcpPort -ComputerName $loopbackHost -Port $port)) {
            $stopped = $true
            break
        }
    }

    if (-not $stopped) {
        throw "Порт $port всё ещё занят после команды остановки."
    }

    Append-ProjectLogEntry "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | INFO | Status: STOPPED"
    Write-Ok 'Проект остановлен'
    Write-Host 'Status: STOPPED' -ForegroundColor Green
    exit 0
}
catch {
    Write-Fail $_.Exception.Message
    Append-ProjectLogEntry "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | FAIL | Status: FAILED"
    Write-Host 'Status: FAILED' -ForegroundColor Red
    exit 1
}
