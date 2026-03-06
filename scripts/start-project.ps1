$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$appPath = Join-Path $projectRoot 'app.py'
$envPath = Join-Path $projectRoot '.env'
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
    if (-not (Test-Path $venvPython)) { throw "Не найден Python в .venv: $venvPython" }
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
    & $venvPython -c "import openai, streamlit, docx, pypandoc, dotenv" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Одна или несколько Python-зависимостей не установлены.' }
    Write-Ok 'Python-зависимости доступны'

    Write-Step 'Проверяю Pandoc'
    $pandocCheck = & pandoc --version 2>$null
    if (-not $pandocCheck) { throw 'Pandoc не найден в PATH.' }
    Write-Ok 'Pandoc доступен'

    Write-Step 'Проверяю .env и API-ключ'
    $keyCheck = & $venvPython -c "from dotenv import load_dotenv; import os; load_dotenv(); v=os.getenv('OPENAI_API_KEY','').strip(); print('KEY_OK' if v and v!='your_api_key_here' else 'KEY_MISSING')" 2>&1
    if (($keyCheck | Out-String).Trim() -ne 'KEY_OK') {
        throw 'OPENAI_API_KEY не задан или остался placeholder в .env.'
    }
    Write-Ok 'API-ключ найден'

    Write-Host '' -ForegroundColor Green
    Write-Host '========================================' -ForegroundColor Green
    Write-Host "  App: $appUrl" -ForegroundColor Green
    Write-Host "  Health: $appUrl/_stcore/health" -ForegroundColor Green
    Write-Host '  Для остановки: Terminal > Run Task > Project: Stop' -ForegroundColor Green
    Write-Host '========================================' -ForegroundColor Green
    Write-Host '' -ForegroundColor Green
    Add-Content -Path $projectLogPath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | INFO | App URL: $appUrl" -Encoding utf8

    # Записываем PID текущего процесса pwsh (stop-скрипт убьет дерево через taskkill /T)
    Set-Content -Path $pidPath -Value $PID -NoNewline

    # Запускаем Streamlit прямо в этом процессе — VS Code task держит его живым
    Set-Location $projectRoot
    & $venvPython -m streamlit run app.py --server.headless true --server.address $serverHost --server.port $port

    # Сюда попадаем только когда Streamlit завершится
    if (Test-Path $pidPath) { Remove-Item $pidPath -Force -ErrorAction SilentlyContinue }
    Write-Ok 'Сервер завершил работу'
    Add-Content -Path $projectLogPath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | INFO | Status: STOPPED" -Encoding utf8
    Write-Host 'Status: STOPPED' -ForegroundColor Green
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