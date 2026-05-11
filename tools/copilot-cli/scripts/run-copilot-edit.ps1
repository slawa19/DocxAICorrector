[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Prompt,

    [string]$WorkingDirectory = (Get-Location).Path,

    [string]$CopilotPath,

    [string[]]$AllowTool,

    [string[]]$DenyTool,

    [string[]]$AddDirectory,

    [string]$Model,

    [switch]$AllowAllTools,

    [switch]$AllowAllPaths,

    [switch]$AllowAllUrls,

    [switch]$PrintCommand
)

$ErrorActionPreference = 'Stop'

$defaultAllowTools = @('write')
$mergedAllowTools = @($defaultAllowTools + ($AllowTool | Where-Object { $_ })) | Select-Object -Unique

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$invokeScript = Join-Path $scriptDir 'invoke-copilot.ps1'

& $invokeScript `
    -Prompt $Prompt `
    -WorkingDirectory $WorkingDirectory `
    -CopilotPath $CopilotPath `
    -AllowTool $mergedAllowTools `
    -DenyTool $DenyTool `
    -AddDirectory $AddDirectory `
    -Model $Model `
    -OutputFormat 'text' `
    -Silent `
    -NoAskUser `
    -AllowAllTools:$AllowAllTools `
    -AllowAllPaths:$AllowAllPaths `
    -AllowAllUrls:$AllowAllUrls `
    -PrintCommand:$PrintCommand
