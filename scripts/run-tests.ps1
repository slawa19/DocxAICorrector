param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs = @()
)

. $PSScriptRoot\_shared.ps1

try {
    Write-Step 'Running full pytest in WSL'
    Invoke-WslInProject 'run-tests' $PytestArgs
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Fail "Pytest exited with code $exitCode"
        exit $exitCode
    }

    Write-Ok 'Full pytest completed successfully'
    exit 0
}
catch {
    Write-Fail $_.Exception.Message
    exit 1
}