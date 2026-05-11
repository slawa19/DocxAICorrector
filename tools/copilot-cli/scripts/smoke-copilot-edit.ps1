[CmdletBinding()]
param(
    [string]$TempDirectory = 'E:\Temp\kilo',
    [string]$CopilotPath,
    [switch]$KeepFiles
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $TempDirectory)) {
    throw "Temp directory not found: $TempDirectory"
}

$testDirectory = Join-Path $TempDirectory 'copilot-cli-smoke'
if (Test-Path -LiteralPath $testDirectory) {
    Remove-Item -LiteralPath $testDirectory -Recurse -Force
}

New-Item -ItemType Directory -Path $testDirectory | Out-Null

$targetFile = Join-Path $testDirectory 'sample.txt'
Set-Content -LiteralPath $targetFile -Value @(
    'before',
    'TODO: replace me'
) -Encoding UTF8

$prompt = @"
Edit the file sample.txt and replace the line 'TODO: replace me' with 'DONE: replaced by Copilot CLI'.
Do not change anything else.
"@

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runScript = Join-Path $scriptDir 'run-copilot-edit.ps1'

$response = & $runScript -WorkingDirectory $testDirectory -Prompt $prompt -CopilotPath $CopilotPath

$content = Get-Content -LiteralPath $targetFile
$expected = @('before', 'DONE: replaced by Copilot CLI')
$actualText = (@($content) -join "`n").TrimEnd()
$expectedText = (@($expected) -join "`n").TrimEnd()

if ($actualText -ne $expectedText) {
    throw "Smoke test failed: unexpected file content in $targetFile"
}

Write-Host 'Smoke test passed.'
Write-Host "Test directory: $testDirectory"
Write-Host 'Copilot response:'
Write-Output $response

if (-not $KeepFiles) {
    Remove-Item -LiteralPath $testDirectory -Recurse -Force
}
