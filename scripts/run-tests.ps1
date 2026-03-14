param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs = @()
)

. $PSScriptRoot\_shared.ps1

try {
    $pytestLogPath = Join-Path $runDir 'last-pytest-full.log'
    $wslScriptPath = Convert-ToWslPath $wslControlScript
    $maxAttempts = 3
    $runMarker = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    if (Test-Path $pytestLogPath) {
        Remove-Item -LiteralPath $pytestLogPath -Force -ErrorAction SilentlyContinue
    }

    $exitCode = 0
    $finalOutput = @()
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        if ($attempt -eq 1) {
            Write-Step "Running full pytest in WSL [$runMarker]"
        }
        else {
            Write-Step "Retrying full pytest in WSL [$runMarker] (attempt $attempt/$maxAttempts)"
        }

        if ($attempt -gt 1) {
            Add-Content -LiteralPath $pytestLogPath -Value "`n[retry] attempt $attempt of $maxAttempts`n" -Encoding UTF8
        }

        $finalOutput = & wsl.exe -d $wslDistro bash $wslScriptPath run-tests @PytestArgs 2>&1 |
            Tee-Object -FilePath $pytestLogPath -Append
        $exitCode = $LASTEXITCODE
        $details = (@($finalOutput) | ForEach-Object { $_ | Out-String }).Trim()
        $isTransientWslFailure = (
            $exitCode -eq -1 -or
            $details.Contains('Wsl/Service/') -or
            $details.Contains('0x8007274c')
        )

        if (-not $isTransientWslFailure -or $attempt -eq $maxAttempts) {
            break
        }

        Write-Warn "Transient WSL transport failure during full pytest (attempt $attempt/$maxAttempts)."
        Start-Sleep -Seconds $attempt
    }

    if ($exitCode -ne 0) {
        Write-Warn "Full pytest log saved to $pytestLogPath"
        Write-Fail "Pytest exited with code $exitCode"
        exit $exitCode
    }

    Write-Ok "Full pytest log saved to $pytestLogPath"
    Write-Ok 'Full pytest completed successfully'
    exit 0
}
catch {
    Write-Fail $_.Exception.Message
    exit 1
}