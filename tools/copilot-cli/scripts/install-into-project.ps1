[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TargetProjectPath,

    [switch]$Force
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $TargetProjectPath)) {
    throw "Target project path not found: $TargetProjectPath"
}

$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))

$copies = @(
    @{
        Source = Join-Path $repoRoot 'tools\copilot-cli'
        Target = Join-Path $TargetProjectPath 'tools\copilot-cli'
    },
    @{
        Source = Join-Path $repoRoot '.kilo\command\copilot-loop.md'
        Target = Join-Path $TargetProjectPath '.kilo\command\copilot-loop.md'
    },
    @{
        Source = Join-Path $repoRoot 'docs\COPILOT_CLI_LOOP_USAGE.md'
        Target = Join-Path $TargetProjectPath 'docs\COPILOT_CLI_LOOP_USAGE.md'
    }
)

foreach ($item in $copies) {
    $targetParent = Split-Path -Parent $item.Target
    if (-not (Test-Path -LiteralPath $targetParent)) {
        New-Item -ItemType Directory -Path $targetParent -Force | Out-Null
    }

    if ((Test-Path -LiteralPath $item.Target) -and (-not $Force)) {
        throw "Target already exists: $($item.Target). Use -Force to overwrite."
    }

    Copy-Item -LiteralPath $item.Source -Destination $item.Target -Recurse -Force
}

Write-Host 'Toolkit installed into project:'
Write-Host $TargetProjectPath
