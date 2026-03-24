. $PSScriptRoot\_shared.ps1

try {
    Write-Step 'Останавливаю проект'

    $status = Get-ProjectRuntimeStatus
    $portOpen = ConvertTo-BoolFlag $status['port_open']
    $managedPidRunning = ConvertTo-BoolFlag $status['managed_pid_running']
    Append-ProjectLogEntry "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | INFO | Stop requested: managed_pid_running=$managedPidRunning; wsl_port_open=$portOpen"

    $stopStatus = Invoke-ProjectStopSequence -Port $port
    $alreadyStopped = [bool]$stopStatus['already_stopped']
    if ($alreadyStopped) {
        Write-Ok 'Проект уже остановлен'
        Write-Host 'Status: STOPPED' -ForegroundColor Green
        exit 0
    }

    $stopped = [bool]$stopStatus['stopped']
    $managedPidStillRunning = [bool]$stopStatus['managed_pid_running']
    $wslPortStillOpen = [bool]$stopStatus['port_open']
    $windowsPortOpen = [bool]$stopStatus['windows_port_open']
    Append-ProjectLogEntry "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | INFO | Stop diagnostics: stopped=$stopped; managed_pid_running=$managedPidStillRunning; wsl_port_open=$wslPortStillOpen; windows_port_open=$windowsPortOpen"

    if ($windowsPortOpen) {
        Write-Warn "WSL runtime уже остановлен, но Windows localhost:$port ещё кратковременно виден занятым. Считаю остановку успешной."
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
