# Shared functions and variables for project control scripts.
# Loaded via: . $PSScriptRoot\_shared.ps1

$ErrorActionPreference = 'Stop'

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

function Write-LogLine {
    param(
        [string]$Level,
        [string]$Message,
        [ConsoleColor]$Color
    )

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $projectLogPath -Value "$timestamp | $Level | $Message" -Encoding utf8
    Write-Host "[$Level] $Message" -ForegroundColor $Color
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
        $result = & wsl.exe -d $wslDistro bash -c "curl -s --max-time 3 '$Url' 2>/dev/null" 2>$null
        return (($result | Out-String).Trim() -eq 'ok')
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
        Start-Sleep -Seconds 2
    }
    return $false
}
