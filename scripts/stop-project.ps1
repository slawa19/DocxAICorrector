$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$runDir = Join-Path $projectRoot '.run'
$pidPath = Join-Path $runDir 'streamlit.pid'
$projectLogPath = Join-Path $runDir 'project.log'
$serverHost = 'localhost'
$port = 8501
$appUrl = "http://${serverHost}:${port}"

if (-not (Test-Path $runDir)) { New-Item -ItemType Directory -Path $runDir | Out-Null }

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
    try {
        $tcp = [System.Net.Sockets.TcpClient]::new()
        $tcp.Connect($ComputerName, $Port)
        $tcp.Close()
        return $true
    }
    catch {
        return $false
    }
}

try {
    Write-Step 'Останавливаю проект'

    $processId = $null
    if (Test-Path $pidPath) {
        $raw = (Get-Content -Path $pidPath -TotalCount 1 -ErrorAction SilentlyContinue | Out-String).Trim()
        try { $processId = [int]$raw } catch { $processId = $null }
    }

    if (-not $processId) {
        if (Test-TcpPort -ComputerName $serverHost -Port $port) {
            Write-Warn "PID-файл не найден, но порт $port занят. Остановите процесс вручную."
            Write-Host 'Status: UNKNOWN' -ForegroundColor Yellow
            exit 1
        }
        Write-Ok 'Проект уже остановлен'
        Write-Host 'Status: STOPPED' -ForegroundColor Green
        exit 0
    }

    $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if (-not $proc) {
        Write-Warn "Процесс PID=$processId уже не существует. Удаляю stale state."
        Remove-Item $pidPath -Force -ErrorAction SilentlyContinue
        Write-Host 'Status: STOPPED' -ForegroundColor Green
        exit 0
    }

    Write-Step "Завершаю дерево процессов PID=$processId"
    # taskkill /T убивает дерево: pwsh -> python -> streamlit
    taskkill /PID $processId /T /F 2>$null | Out-Null

    $stopped = $false
    for ($i = 1; $i -le 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (-not (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
            $stopped = $true
            break
        }
    }

    if (-not $stopped) {
        throw "Не удалось завершить процесс PID=$processId."
    }

    if (Test-Path $pidPath) { Remove-Item $pidPath -Force -ErrorAction SilentlyContinue }

    Write-Ok "Процесс PID=$processId остановлен"
    Add-Content -Path $projectLogPath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | INFO | Status: STOPPED" -Encoding utf8
    Write-Host 'Status: STOPPED' -ForegroundColor Green
    Write-Host "App: $appUrl" -ForegroundColor Green
    exit 0
}
catch {
    Write-Fail $_.Exception.Message
    Add-Content -Path $projectLogPath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | FAIL | Status: FAILED" -Encoding utf8
    Write-Host 'Status: FAILED' -ForegroundColor Red
    exit 1
}