. $PSScriptRoot\_shared.ps1

try {
    Write-Step 'Restarting project'

    $stopScript = Join-Path $PSScriptRoot 'stop-project.ps1'
    $startScript = Join-Path $PSScriptRoot 'start-project.ps1'
    $powershellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

    if (-not (Test-Path $stopScript)) {
        throw "Missing stop-project.ps1: $stopScript"
    }
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
    & $powershellExe @commonArgs $stopScript
    $stopExitCode = $LASTEXITCODE
    if ($stopExitCode -ne 0) {
        throw "Stop Project failed with exit code $stopExitCode"
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