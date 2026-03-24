. $PSScriptRoot\_shared.ps1

try {
    Write-Step 'Restarting project'

    $startScript = Join-Path $PSScriptRoot 'start-project.ps1'
    $powershellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

    if (-not (Test-Path $startScript)) {
        throw "Missing start-project.ps1: $startScript"
    }
    if (-not (Test-Path $powershellExe)) {
        throw "Missing powershell.exe: $powershellExe"
    }

    $commonArgs = @(
        '-NoProfile'
        '-ExecutionPolicy'
        'Bypass'
        '-File'
    )

    Write-Step 'Step 1/2: stopping project'
    $stopStatus = Invoke-ProjectStopSequence -Port $port -AllowRepoOwnedPortRecovery
    if ([bool]$stopStatus['already_stopped']) {
        Write-Ok 'Проект уже был остановлен перед рестартом'
    }
    elseif ([bool]$stopStatus['windows_port_open']) {
        Write-Warn "WSL runtime уже остановлен, но Windows localhost:$port ещё кратковременно виден занятым. Продолжаю рестарт."
    }

    Write-Step 'Step 2/2: starting project'
    & $powershellExe @commonArgs $startScript
    $startExitCode = $LASTEXITCODE
    if ($startExitCode -ne 0) {
        throw "Start Project failed with exit code $startExitCode"
    }

    exit 0
}
catch {
    Write-Fail $_.Exception.Message
    exit 1
}