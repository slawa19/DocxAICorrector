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
$loopbackHost = '127.0.0.1'
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

function New-ValidationException {
    param([string]$Message)

    return [System.ArgumentException]::new($Message)
}

function Invoke-WslInProject {
    param(
        [string]$Action,
        [string[]]$Arguments = @()
    )

    $wslScriptPath = Convert-ToWslPath $wslControlScript
    $maxAttempts = 3
    $lastOutput = @()
    $lastExitCode = 0

    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        $lastOutput = & wsl.exe -d $wslDistro bash $wslScriptPath $Action @Arguments 2>&1
        $lastExitCode = $LASTEXITCODE

        if ($lastExitCode -eq 0) {
            $global:LASTEXITCODE = 0
            return $lastOutput
        }

        $details = ConvertTo-OutputText $lastOutput
        $isTransientWslFailure = Test-IsTransientWslFailure -ExitCode $lastExitCode -Details $details

        if (-not $isTransientWslFailure -or $attempt -eq $maxAttempts) {
            $global:LASTEXITCODE = $lastExitCode
            return $lastOutput
        }

        Write-Warn "Transient WSL transport failure during '$Action' (attempt $attempt/$maxAttempts). Retrying..."
        Reset-WslTransport
        Start-Sleep -Seconds $attempt
    }

    $global:LASTEXITCODE = $lastExitCode
    return $lastOutput
}

function ConvertTo-OutputText {
    param([object[]]$Output)

    if ($null -eq $Output) {
        return ''
    }

    return ((@($Output) | ForEach-Object { $_ | Out-String }) -join '').Trim()
}

function Test-IsTransientWslFailure {
    param(
        [int]$ExitCode,
        [string]$Details
    )

    if ($ExitCode -eq -1) {
        return $true
    }

    if ([string]::IsNullOrWhiteSpace($Details)) {
        return $false
    }

    return (
        $Details.Contains('Wsl/Service/') -or
        $Details.Contains('0x8007274c') -or
        $Details.Contains('0xffffffff')
    )
}

function Reset-WslTransport {
    # Do NOT call wsl.exe --shutdown here — it terminates ALL WSL distros and
    # kills any running Streamlit/dev server sessions, causing cascade failures.
    # Transient pipe errors (0x8007274c) typically resolve on their own after a
    # short wait; hard exit-(-1) failures require a manual wsl --shutdown anyway.
    Start-Sleep -Seconds 3
}

function Get-PreferredRuntimeMode {
    $preference = ''
    if ($null -ne $env:DOCX_AI_RUNTIME_MODE) {
        $preference = [string]$env:DOCX_AI_RUNTIME_MODE
    }
    $normalizedPreference = $preference.Trim().ToLowerInvariant()

    if ($normalizedPreference -and $normalizedPreference -ne 'wsl') {
        throw 'This repository uses a WSL-first workflow. DOCX_AI_RUNTIME_MODE may only be empty or set to wsl.'
    }

    return 'wsl'
}

function Merge-StatusTables {
    param(
        [hashtable]$Left,
        [hashtable]$Right
    )

    $merged = @{}
    foreach ($key in $Left.Keys) {
        $merged[$key] = $Left[$key]
    }
    foreach ($key in $Right.Keys) {
        $merged[$key] = $Right[$key]
    }
    return $merged
}

function Parse-KeyValueOutput {
    param([object[]]$RawOutput)

    $status = @{}
    foreach ($line in @($RawOutput)) {
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

function Get-WslStatusMap {
    param(
        [string]$Action,
        [string[]]$Arguments = @()
    )

    $rawOutput = Invoke-WslInProject $Action $Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        $details = ($rawOutput | Out-String).Trim()
        if ($details) {
            throw "Failed to get WSL project status: $details"
        }
        throw 'Failed to get WSL project status.'
    }

    $status = Parse-KeyValueOutput -RawOutput $rawOutput
    $status['runtime_mode'] = 'wsl'
    return $status
}

function Start-ManagedProject {
    param(
        [string]$ServerHost,
        [int]$Port
    )

    return (Invoke-WslInProject 'run-streamlit' @($ServerHost, "$Port") 2>&1)
}

function Stop-ManagedProject {
    Invoke-WslInProject 'stop-streamlit' 2>$null | Out-Null
}

function Get-ProjectLogTail {
    param([int]$Lines = 80)

    return (Invoke-WslInProject 'tail-log' @("$Lines") 2>&1)
}

function ConvertTo-BoolFlag {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }

    return $Value.Trim().Equals('true', [System.StringComparison]::OrdinalIgnoreCase)
}

function Get-ProjectStatus {
    $runtimeStatus = Get-ProjectRuntimeStatus
    return (Merge-StatusTables -Left $runtimeStatus -Right (Get-WslStatusMap -Action 'env-status'))
}

function Get-ProjectRuntimeStatus {
    return (Get-WslStatusMap -Action 'runtime-status' -Arguments @("$port"))
}

function Get-ProjectEnvironmentStatus {
    return (Get-WslStatusMap -Action 'env-status')
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

    return (((($rawOutput | Out-String).Trim()) -eq 'ok'))
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

    return (((($rawOutput | Out-String).Trim()) -eq 'ok'))
}

function Wait-ProjectStopped {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 10
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $runtimeStatus = Get-ProjectRuntimeStatus
        $managedPidRunning = ConvertTo-BoolFlag $runtimeStatus['managed_pid_running']
        $portOpen = ConvertTo-BoolFlag $runtimeStatus['port_open']
        $windowsPortOpen = Test-TcpPort -ComputerName $loopbackHost -Port $Port

        if (-not $managedPidRunning -and -not $portOpen) {
            return @{
                stopped = $true
                managed_pid_running = $managedPidRunning
                port_open = $portOpen
                windows_port_open = $windowsPortOpen
            }
        }

        Start-Sleep -Milliseconds 500
    }

    $runtimeStatus = Get-ProjectRuntimeStatus
    $managedPidRunning = ConvertTo-BoolFlag $runtimeStatus['managed_pid_running']
    $portOpen = ConvertTo-BoolFlag $runtimeStatus['port_open']
    $windowsPortOpen = Test-TcpPort -ComputerName $loopbackHost -Port $Port
    return @{
        stopped = (-not $managedPidRunning -and -not $portOpen)
        managed_pid_running = $managedPidRunning
        port_open = $portOpen
        windows_port_open = $windowsPortOpen
    }
}
