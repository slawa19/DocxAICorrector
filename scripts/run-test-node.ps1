param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Target,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs = @()
)

. $PSScriptRoot\_shared.ps1

try {
    $normalizedTarget = Normalize-TestTarget -Target $Target -RequireNodeSuffix
    $wslArguments = @($normalizedTarget) + $PytestArgs
    Write-Step "Running test node in WSL: $normalizedTarget"
    Invoke-WslInProject 'run-test-node' $wslArguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Fail "Pytest exited with code $exitCode"
        exit $exitCode
    }

    Write-Ok "Test node completed successfully: $normalizedTarget"
    exit 0
}
catch [System.ArgumentException] {
    Write-Fail $_.Exception.Message
    exit 2
}
catch {
    Write-Fail $_.Exception.Message
    exit 1
}