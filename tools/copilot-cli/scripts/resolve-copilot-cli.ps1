[CmdletBinding()]
param(
    [string]$ExplicitPath,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

function Write-ResolvedPath {
    param([string]$Path)

    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if (-not $Quiet) {
        Write-Output $resolved
    }
    $script:ResolvedPath = $resolved
}

if ($ExplicitPath) {
    if (-not (Test-Path -LiteralPath $ExplicitPath)) {
        throw "Explicit Copilot CLI path not found: $ExplicitPath"
    }
    Write-ResolvedPath -Path $ExplicitPath
    return
}

$envCandidates = @(
    $env:COPILOT_CLI_PATH,
    $env:GITHUB_COPILOT_CLI_PATH
) | Where-Object { $_ }

foreach ($candidate in $envCandidates) {
    if (Test-Path -LiteralPath $candidate) {
        Write-ResolvedPath -Path $candidate
        return
    }
}

$command = Get-Command copilot -ErrorAction SilentlyContinue
if ($command -and $command.Source -and (Test-Path -LiteralPath $command.Source)) {
    Write-ResolvedPath -Path $command.Source
    return
}

$knownCandidates = @(
    'C:\Users\slawa\AppData\Local\Microsoft\WinGet\Packages\GitHub.Copilot_Microsoft.Winget.Source_8wekyb3d8bbwe\copilot.exe',
    (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\GitHub.Copilot_Microsoft.Winget.Source_8wekyb3d8bbwe\copilot.exe'),
    (Join-Path $env:APPDATA 'npm\copilot.cmd'),
    (Join-Path $env:APPDATA 'npm\copilot.exe')
) | Where-Object { $_ }

foreach ($candidate in $knownCandidates) {
    if (Test-Path -LiteralPath $candidate) {
        Write-ResolvedPath -Path $candidate
        return
    }
}

throw 'Copilot CLI not found. Install it, run `copilot login`, or set COPILOT_CLI_PATH.'
