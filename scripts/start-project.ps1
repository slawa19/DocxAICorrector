$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$wslDistro = 'Debian'
$wslControlScript = Join-Path $PSScriptRoot 'project-control-wsl.sh'
$appPath = Join-Path $projectRoot 'app.py'
$envPath = Join-Path $projectRoot '.env'
$runDir = Join-Path $projectRoot '.run'
$pidPath = Join-Path $runDir 'streamlit.pid'
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

function Invoke-WslInProject {
    param(
        [string]$Action,
        [string[]]$Arguments = @()
    )

    $wslScriptPath = Convert-ToWslPath $wslControlScript
    & wsl.exe -d $wslDistro bash $wslScriptPath $Action @Arguments
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

function Test-HttpHealth {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 2
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
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Remove-StalePid {
    if (-not (Test-Path $pidPath)) { return }
    $raw = (Get-Content -Path $pidPath -TotalCount 1 -ErrorAction SilentlyContinue | Out-String).Trim()
    if (-not $raw) {
        Remove-Item $pidPath -Force -ErrorAction SilentlyContinue
        return
    }
    try {
        $oldPid = [int]$raw
        $proc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
        if ($proc) {
            if (Test-TcpPort -ComputerName $serverHost -Port $port) {
                Write-Ok "Проект уже запущен. PID=$oldPid"
                Write-Host "URL: $appUrl" -ForegroundColor Green
                exit 0
            }
            Write-Warn "Найден PID=$oldPid, но порт $port не отвечает. Убиваю."
            taskkill /PID $oldPid /T /F 2>$null | Out-Null
        }
    } catch {}
    Remove-Item $pidPath -Force -ErrorAction SilentlyContinue
}

try {
    Write-Step 'Проверяю структуру проекта'
    if (-not (Test-Path $wslControlScript)) { throw "Не найден WSL helper script: $wslControlScript" }
    if (-not (Test-Path $appPath))    { throw "Не найден app.py: $appPath" }
    if (-not (Test-Path $envPath))    { throw "Не найден .env: $envPath" }
    if (-not (Test-Path $runDir))     { New-Item -ItemType Directory -Path $runDir | Out-Null }
    Write-Ok 'Файлы проекта на месте'

    Write-Step 'Проверяю, не запущен ли уже проект'
    Remove-StalePid
    if (Test-TcpPort -ComputerName $serverHost -Port $port) {
        throw "Порт $port уже занят другим процессом."
    }
    Write-Ok "Порт $port свободен"

    Write-Step 'Проверяю Python-зависимости'
    Invoke-WslInProject 'check-python' 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Одна или несколько Python-зависимостей не установлены.' }
    Write-Ok 'Python-зависимости доступны'

    Write-Step 'Проверяю Pandoc'
    Invoke-WslInProject 'check-pandoc' 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Pandoc не найден в WSL PATH.' }
    Write-Ok 'Pandoc доступен'

    Write-Step 'Проверяю .env и API-ключ'
    $keyCheck = Invoke-WslInProject 'check-api-key' 2>&1
    if (($keyCheck | Out-String).Trim() -ne 'KEY_OK') {
        throw 'OPENAI_API_KEY не задан или остался placeholder в .env.'
    }
    Write-Ok 'API-ключ найден'

    Write-Step 'Запускаю Streamlit в WSL'
    Invoke-WslInProject 'run-streamlit' @($serverHost, "$port") 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось запустить Streamlit в WSL.' }

    Write-Step 'Ожидаю доступности health endpoint (через WSL)'
    $healthResult = Invoke-WslInProject 'wait-health' @("$port", '90') 2>&1
    if (($healthResult | Out-String).Trim() -ne 'ok') {
        throw 'Streamlit не стал доступен по health endpoint за 90 секунд.'
    }

    Write-Ok 'Сервер доступен'
    Write-Host '' -ForegroundColor Green
    Write-Host '========================================' -ForegroundColor Green
    Write-Host "  App: $appUrl" -ForegroundColor Green
    Write-Host "  Health: $appUrl/_stcore/health" -ForegroundColor Green
    Write-Host '  Для остановки: Terminal > Run Task > Project: Stop' -ForegroundColor Green
    Write-Host '========================================' -ForegroundColor Green
    Write-Host '' -ForegroundColor Green
    Add-Content -Path $projectLogPath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | INFO | App URL: $appUrl" -Encoding utf8
    if (Test-Path $pidPath) { Remove-Item $pidPath -Force -ErrorAction SilentlyContinue }
    exit 0
}
catch {
    Write-Fail $_.Exception.Message
    if (Test-Path $pidPath) { Remove-Item $pidPath -Force -ErrorAction SilentlyContinue }
    Add-Content -Path $projectLogPath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | FAIL | Status: FAILED" -Encoding utf8
    Write-Host 'Status: FAILED' -ForegroundColor Red
    Write-Host "App: $appUrl" -ForegroundColor Yellow
    exit 1
}