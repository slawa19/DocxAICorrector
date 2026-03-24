param(
    [int]$Lines = 80
)

. $PSScriptRoot\_shared.ps1

try {
    if ($Lines -lt 1) {
        throw (New-ValidationException 'Lines must be a positive integer.')
    }

    Write-Step "Showing last $Lines lines from streamlit.log"
    Get-ProjectLogTail -Lines $Lines

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
