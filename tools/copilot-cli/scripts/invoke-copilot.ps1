[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Prompt,

    [string]$WorkingDirectory = (Get-Location).Path,

    [string]$CopilotPath,

    [string[]]$AllowTool,

    [string[]]$DenyTool,

    [string[]]$AvailableTools,

    [string[]]$ExcludedTools,

    [string[]]$AddDirectory,

    [string]$Model,

    [ValidateSet('text', 'json')]
    [string]$OutputFormat = 'text',

    [switch]$Silent,

    [switch]$NoAskUser,

    [switch]$AllowAllTools,

    [switch]$AllowAllPaths,

    [switch]$AllowAllUrls,

    [switch]$PrintCommand
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$resolveScript = Join-Path $scriptDir 'resolve-copilot-cli.ps1'
$resolvedCopilotPath = & $resolveScript -ExplicitPath $CopilotPath -Quiet

if (-not (Test-Path -LiteralPath $WorkingDirectory)) {
    throw "Working directory not found: $WorkingDirectory"
}

$arguments = @('-C', $WorkingDirectory, '-p', $Prompt, '--output-format', $OutputFormat)

if ($Silent) {
    $arguments += '-s'
}

if ($NoAskUser) {
    $arguments += '--no-ask-user'
}

if ($AllowAllTools) {
    $arguments += '--allow-all-tools'
}

if ($AllowAllPaths) {
    $arguments += '--allow-all-paths'
}

if ($AllowAllUrls) {
    $arguments += '--allow-all-urls'
}

if ($Model) {
    $arguments += @('--model', $Model)
}

foreach ($tool in ($AllowTool | Where-Object { $_ })) {
    $arguments += "--allow-tool=$tool"
}

foreach ($tool in ($DenyTool | Where-Object { $_ })) {
    $arguments += "--deny-tool=$tool"
}

foreach ($tool in ($AvailableTools | Where-Object { $_ })) {
    $arguments += "--available-tools=$tool"
}

foreach ($tool in ($ExcludedTools | Where-Object { $_ })) {
    $arguments += "--excluded-tools=$tool"
}

foreach ($directory in ($AddDirectory | Where-Object { $_ })) {
    $arguments += @('--add-dir', $directory)
}

if ($PrintCommand) {
    $quoted = $arguments | ForEach-Object {
        if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
    }
    Write-Host ((@($resolvedCopilotPath) + $quoted) -join ' ')
}

& $resolvedCopilotPath @arguments
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    throw "Copilot CLI failed with exit code $exitCode"
}
