# Shared functions and variables for project control scripts.
# Loaded via: . $PSScriptRoot\_shared.ps1

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try {
    & "$env:SystemRoot\System32\chcp.com" 65001 > $null
}
catch {
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$wslDistro = 'Debian'
$wslControlScript = Join-Path $PSScriptRoot 'project-control-wsl.sh'
$appPath = Join-Path $projectRoot 'app.py'
$runDir = Join-Path $projectRoot '.run'
$projectLogPath = Join-Path $runDir 'project.log'
$serverHost = '0.0.0.0'   # used in stop-project.ps1 (Test-TcpPort) and start-project.ps1 (Invoke-WslInProject)
$port = 8501
$appUrl = "http://localhost:$port"
$healthUrl = "$appUrl/_stcore/health"   # used in start-project.ps1 (Wait-HttpHealth)

if (-not (Test-Path $runDir)) { New-Item -ItemType Directory -Path $runDir | Out-Null }

function Convert-ToWslPath {
    param([string]$WindowsPath)

    $resolvedPath = (Resolve-Path -LiteralPath $WindowsPath).Path
    $normalizedPath = $resolvedPath -replace '\\', '/'
    if ($normalizedPath -notmatch '^([A-Za-z]):/(.*)$') {
        throw "Failed to convert path to WSL format: $WindowsPath"
    }
    return "/mnt/$($matches[1].ToLower())/$($matches[2])"
}

function Test-IsWindowsAbsolutePath {
    param([string]$Path)

    return ($Path -match '^[A-Za-z]:[\\/]')
}

function New-ValidationException {
    param([string]$Message)

    return [System.ArgumentException]::new($Message)
}

function Split-TestTarget {
    param([string]$Target)

    $parts = $Target -split '::', 2
    $filePart = $parts[0]
    $nodeSuffix = ''
    if ($parts.Count -eq 2) {
        $nodeSuffix = "::$($parts[1])"
    }

    return @{
        FilePart = $filePart
        NodeSuffix = $nodeSuffix
    }
}

function Test-IsUnderProjectRoot {
    param([string]$FullPath)

    $normalizedRoot = [System.IO.Path]::GetFullPath($projectRoot).TrimEnd([char[]]@('\', '/'))
    $normalizedPath = [System.IO.Path]::GetFullPath($FullPath)
    return $normalizedPath.Equals($normalizedRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
        $normalizedPath.StartsWith("$normalizedRoot\", [System.StringComparison]::OrdinalIgnoreCase)
}

function Normalize-TestTarget {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Target,

        [switch]$RequireNodeSuffix,
        [switch]$DisallowNodeSuffix
    )

    if ([string]::IsNullOrWhiteSpace($Target)) {
        throw (New-ValidationException 'Test target is required.')
    }

    $trimmedTarget = $Target.Trim()
    $targetParts = Split-TestTarget $trimmedTarget
    $filePart = [string]$targetParts.FilePart
    $nodeSuffix = [string]$targetParts.NodeSuffix

    if ($RequireNodeSuffix -and -not $nodeSuffix) {
        throw (New-ValidationException "Pytest node id is required: $trimmedTarget")
    }
    if ($RequireNodeSuffix -and $nodeSuffix -and [string]::IsNullOrWhiteSpace($nodeSuffix.Substring(2))) {
        throw (New-ValidationException "Pytest node id suffix must not be empty: $trimmedTarget")
    }
    if ($DisallowNodeSuffix -and $nodeSuffix) {
        throw (New-ValidationException "Expected a test file path without pytest node suffix: $trimmedTarget")
    }
    if ([string]::IsNullOrWhiteSpace($filePart)) {
        throw (New-ValidationException "Test target has an empty file part: $trimmedTarget")
    }
    if ($filePart.StartsWith('/') -or $filePart.StartsWith('\\')) {
        throw (New-ValidationException "Unsupported absolute path format for test target: $trimmedTarget")
    }

    $fullPath = if (Test-IsWindowsAbsolutePath $filePart) {
        [System.IO.Path]::GetFullPath($filePart)
    }
    else {
        [System.IO.Path]::GetFullPath((Join-Path $projectRoot $filePart))
    }

    if (-not (Test-IsUnderProjectRoot $fullPath)) {
        throw (New-ValidationException "Test target is outside repository root: $trimmedTarget")
    }

    $rootPath = [System.IO.Path]::GetFullPath($projectRoot).TrimEnd([char[]]@('\', '/'))
    $relativePath = $fullPath.Substring($rootPath.Length).TrimStart([char[]]@('\', '/')) -replace '\\', '/'

    if (-not $relativePath.StartsWith('tests/', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw (New-ValidationException "Test target must be under tests/: $trimmedTarget")
    }
    if (-not $relativePath.EndsWith('.py', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw (New-ValidationException "Test target must point to a Python test file: $trimmedTarget")
    }

    return "$relativePath$nodeSuffix"
}

function Invoke-WslInProject {
    param(
        [string]$Action,
        [string[]]$Arguments = @()
    )

    $wslScriptPath = Convert-ToWslPath $wslControlScript
    & wsl.exe -d $wslDistro bash $wslScriptPath $Action @Arguments
}

function ConvertTo-BoolFlag {
    param([string]$Value)

    return ($Value.Trim().ToLowerInvariant() -eq 'true')
}

function Get-ProjectStatus {
    $rawOutput = Invoke-WslInProject 'status' @("$port") 2>&1
    if ($LASTEXITCODE -ne 0) {
        $details = ($rawOutput | Out-String).Trim()
        if ($details) {
            throw "Failed to get project status: $details"
        }
        throw 'Failed to get project status.'
    }

    $status = @{}
    foreach ($line in @($rawOutput)) {
        $text = ($line | Out-String).Trim()
        if (-not $text) { continue }
        $delimiterIndex = $text.IndexOf('=')
        if ($delimiterIndex -lt 1) { continue }
        $key = $text.Substring(0, $delimiterIndex)
        $value = $text.Substring($delimiterIndex + 1)
        $status[$key] = $value
    }

    return $status
}

function Get-ProjectRuntimeStatus {
    $rawOutput = Invoke-WslInProject 'runtime-status' @("$port") 2>&1
    if ($LASTEXITCODE -ne 0) {
        $details = ($rawOutput | Out-String).Trim()
        if ($details) {
            throw "Failed to get project runtime status: $details"
        }
        throw 'Failed to get project runtime status.'
    }

    $status = @{}
    foreach ($line in @($rawOutput)) {
        $text = ($line | Out-String).Trim()
        if (-not $text) { continue }
        $delimiterIndex = $text.IndexOf('=')
        if ($delimiterIndex -lt 1) { continue }
        $key = $text.Substring(0, $delimiterIndex)
        $value = $text.Substring($delimiterIndex + 1)
        $status[$key] = $value
    }

    return $status
}

function Get-ProjectEnvironmentStatus {
    $rawOutput = Invoke-WslInProject 'env-status' 2>&1
    if ($LASTEXITCODE -ne 0) {
        $details = ($rawOutput | Out-String).Trim()
        if ($details) {
            throw "Failed to get project environment status: $details"
        }
        throw 'Failed to get project environment status.'
    }

    $status = @{}
    foreach ($line in @($rawOutput)) {
        $text = ($line | Out-String).Trim()
        if (-not $text) { continue }
        $delimiterIndex = $text.IndexOf('=')
        if ($delimiterIndex -lt 1) { continue }
        $key = $text.Substring(0, $delimiterIndex)
        $value = $text.Substring($delimiterIndex + 1)
        $status[$key] = $value
    }

    return $status
}

function Write-LogLine {
    param(
        [string]$Level,
        [string]$Message,
        [ConsoleColor]$Color
    )

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Append-ProjectLogEntry "$timestamp | $Level | $Message"
    Write-Host "[$Level] $Message" -ForegroundColor $Color
}

function Append-ProjectLogEntry {
    param([string]$Line)

    $stream = $null
    $writer = $null
    try {
        $stream = [System.IO.File]::Open($projectLogPath, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
        $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
        $writer.WriteLine($Line)
        $writer.Flush()
    }
    catch {
    }
    finally {
        if ($writer) { $writer.Dispose() }
        elseif ($stream) { $stream.Dispose() }
    }
}

function Write-Step {
    param([string]$Message)
    Write-LogLine -Level 'STEP' -Message $Message -Color Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-LogLine -Level 'OK' -Message $Message -Color Green
}

function Write-Warn {
    param([string]$Message)
    Write-LogLine -Level 'WARN' -Message $Message -Color Yellow
}

function Write-Fail {
    param([string]$Message)
    Write-LogLine -Level 'FAIL' -Message $Message -Color Red
}

function Test-TcpPort {
    param([string]$ComputerName, [int]$Port)

    $tcp = $null
    $asyncResult = $null
    try {
        $tcp = [System.Net.Sockets.TcpClient]::new()
        $asyncResult = $tcp.BeginConnect($ComputerName, $Port, $null, $null)
        if (-not $asyncResult.AsyncWaitHandle.WaitOne(1000)) {
            return $false
        }
        $tcp.EndConnect($asyncResult)
        $tcp.Close()
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($asyncResult -and $asyncResult.AsyncWaitHandle) {
            $asyncResult.AsyncWaitHandle.Close()
        }
        if ($tcp) {
            $tcp.Dispose()
        }
    }
}

function Test-HttpHealth {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return (($response.Content | Out-String).Trim() -eq 'ok')
    }
    catch {
        return $false
    }
}

function Wait-HttpHealth {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpHealth -Url $Url) {
            return $true
        }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

function Wait-ProjectHealth {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 30
    )

    $rawOutput = Invoke-WslInProject 'wait-health' @("$Port", "$TimeoutSeconds") 2>&1
    if ($LASTEXITCODE -ne 0) {
        return $false
    }

    return ((($rawOutput | Out-String).Trim()) -eq 'ok')
}

function Wait-ProjectReady {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 30
    )

    $rawOutput = Invoke-WslInProject 'wait-ready' @("$Port", "$TimeoutSeconds") 2>&1
    if ($LASTEXITCODE -ne 0) {
        return $false
    }

    return ((($rawOutput | Out-String).Trim()) -eq 'ok')
}
