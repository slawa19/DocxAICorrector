$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$wslDistro = 'Debian'
$wslControlScript = Join-Path $PSScriptRoot 'project-control-wsl.sh'
$runDir = Join-Path $projectRoot '.run'
$projectLogPath = Join-Path $runDir 'project.log'
$serverHost = 'localhost'
$port = 8501
$appUrl = "http://${serverHost}:${port}"

if (-not (Test-Path $runDir)) { New-Item -ItemType Directory -Path $runDir | Out-Null }

function Convert-ToWslPath {
    param([string]$WindowsPath)

    $resolvedPath = (Resolve-Path -LiteralPath $WindowsPath).Path
    $normalizedPath = $resolvedPath -replace '\\', '/'
    if ($normalizedPath -notmatch '^([A-Za-z]):/(.+)$') {
        throw "Не удалось преобразовать путь в WSL-формат: $WindowsPath"
    }
    return "/mnt/$($matches[1].ToLower())/$($matches[2])"
}

function Stop-WslStreamlit {
    if (-not (Test-Path $wslControlScript)) {
        return
    }

    $wslScriptPath = Convert-ToWslPath $wslControlScript
    & wsl.exe -d $wslDistro bash $wslScriptPath stop-streamlit 2>$null | Out-Null
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
        if (-not $asyncResult.AsyncWaitHandle.WaitOne(1000, $false)) {
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

try {
    Write-Step 'Останавливаю проект'

    if (-not (Test-TcpPort -ComputerName $serverHost -Port $port)) {
        Write-Ok 'Проект уже остановлен'
        Write-Host 'Status: STOPPED' -ForegroundColor Green
        exit 0
    }

    # Streamlit всегда запускается через WSL — останавливаем через WSL helper.
    # helper читает .run/wsl_streamlit.pid и посылает kill.
    Stop-WslStreamlit

    $stopped = $false
    for ($i = 1; $i -le 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (-not (Test-TcpPort -ComputerName $serverHost -Port $port)) {
            $stopped = $true
            break
        }
    }

    if (-not $stopped) {
        throw "Порт $port всё ещё занят после команды остановки."
    }

    Add-Content -Path $projectLogPath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | INFO | Status: STOPPED" -Encoding utf8
    Write-Ok 'Проект остановлен'
    Write-Host 'Status: STOPPED' -ForegroundColor Green
    exit 0
}
catch {
    Write-Fail $_.Exception.Message
    Add-Content -Path $projectLogPath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | FAIL | Status: FAILED" -Encoding utf8
    Write-Host 'Status: FAILED' -ForegroundColor Red
    exit 1
}