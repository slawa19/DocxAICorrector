param(
    [int]$Lines = 80
)

. $PSScriptRoot\_shared.ps1

try {
    if ($Lines -lt 1) {
        throw (New-ValidationException 'Lines must be a positive integer.')
    }

    Write-Step "Showing last $Lines lines from streamlit.log"
    Invoke-WslInProject 'tail-log' @("$Lines")
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Fail "Failed to read streamlit.log. Exit code: $exitCode"
        exit $exitCode
    }

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