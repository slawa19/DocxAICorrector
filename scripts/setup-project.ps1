. $PSScriptRoot\_shared.ps1

try {
    $runtimeMode = Get-PreferredRuntimeMode
    Write-Step "Installing project dependencies ($runtimeMode)"
    if ($runtimeMode -eq 'wsl' -and -not (Test-Path $wslControlScript)) { throw "WSL helper script not found: $wslControlScript" }

    $setupOutput = Invoke-WslInProject 'setup' 2>&1
    $setupExitCode = if ($runtimeMode -eq 'wsl') { $LASTEXITCODE } else { 0 }
    if ($setupExitCode -ne 0) {
        $detail = ($setupOutput | Out-String).Trim()
        throw "Project setup failed ($runtimeMode).`n$detail"
    }

    Write-Host ($setupOutput | Out-String).Trim()
    Write-Ok 'Project dependencies are installed'
    exit 0
}
catch {
    Write-Fail $_.Exception.Message
    Write-Host 'Status: FAILED' -ForegroundColor Red
    exit 1
}
