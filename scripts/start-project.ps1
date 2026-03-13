. $PSScriptRoot\_shared.ps1

try {
    Write-Step 'Проверяю структуру проекта'
    if (-not (Test-Path $wslControlScript)) { throw "Не найден WSL helper script: $wslControlScript" }
    if (-not (Test-Path $appPath)) { throw "Не найден app.py: $appPath" }
    Write-Ok 'Файлы проекта на месте'

    Write-Step 'Проверяю статус проекта и окружения'
    $status = Get-ProjectStatus

    $healthOk = ConvertTo-BoolFlag $status['health_ok']
    $managedPidRunning = ConvertTo-BoolFlag $status['managed_pid_running']
    $portOpen = ConvertTo-BoolFlag $status['port_open']
    $venvOk = ConvertTo-BoolFlag $status['venv_ok']
    $depsOk = ConvertTo-BoolFlag $status['deps_ok']
    $pandocOk = ConvertTo-BoolFlag $status['pandoc_ok']
    $apiKeyOk = ConvertTo-BoolFlag $status['api_key_ok']
    $managedPid = $status['managed_pid']

    if ($managedPidRunning) {
        if ($healthOk) {
            Write-Ok "Проект уже запущен. PID=$managedPid"
            Write-Host "URL: $appUrl" -ForegroundColor Green
            exit 0
        }

        Write-Warn "Найден управляемый WSL-процесс приложения (PID=$managedPid), но health endpoint пока не отвечает. Жду готовности."
        if (-not (Wait-HttpHealth -Url $healthUrl -TimeoutSeconds 30)) {
            throw "Найден управляемый WSL-процесс приложения (PID=$managedPid), но health endpoint так и не ответил. Проверьте .run/streamlit.log или выполните Stop Project перед повторным запуском."
        }

        Write-Ok "Проект уже запущен. PID=$managedPid"
        Write-Host "URL: $appUrl" -ForegroundColor Green
        exit 0
    }

    if ($portOpen) {
        throw "Порт $port уже занят чужим процессом или незарегистрированным запуском. Освободите порт или используйте scripts/status-project.ps1 для диагностики."
    }

    if (-not $venvOk) {
        throw 'Не найден WSL virtualenv .venv/bin/python. Создайте окружение в WSL: python3 -m venv .venv'
    }
    if (-not $depsOk) {
        throw 'Не хватает Python-зависимостей. Выполните в WSL: . .venv/bin/activate && pip install -r requirements.txt'
    }
    if (-not $pandocOk) {
        throw 'Pandoc недоступен для текущего WSL-окружения. Проверьте установку pandoc и переменную PYPANDOC_PANDOC.'
    }
    if (-not $apiKeyOk) {
        throw 'OPENAI_API_KEY не найден или остался placeholder. Проверьте .env или переменные окружения.'
    }

    Write-Ok 'Окружение готово'

    Write-Step 'Запускаю Streamlit в WSL'
    $runOutput = Invoke-WslInProject 'run-streamlit' @($serverHost, "$port") 2>&1
    if ($LASTEXITCODE -ne 0) {
        $detail = ($runOutput | Out-String).Trim()
        throw "Не удалось запустить Streamlit в WSL.`n$detail"
    }

    Write-Step 'Ожидаю доступности health endpoint'
    if (-not (Wait-HttpHealth -Url $healthUrl -TimeoutSeconds 180)) {
        $tailOutput = Invoke-WslInProject 'tail-log' @('80') 2>&1
        $tailText = ($tailOutput | Out-String).Trim()
        if ($tailText) {
            Write-Warn "Последние строки streamlit.log:`n$tailText"
        }
        throw 'Streamlit не стал доступен по health endpoint за 180 секунд.'
    }

    Write-Ok 'Сервер доступен'
    Write-Host '' -ForegroundColor Green
    Write-Host '========================================' -ForegroundColor Green
    Write-Host "  App: $appUrl" -ForegroundColor Green
    Write-Host "  Health: $appUrl/_stcore/health" -ForegroundColor Green
    Write-Host '  Для остановки: Terminal > Run Task > Stop Project' -ForegroundColor Green
    Write-Host '========================================' -ForegroundColor Green
    Write-Host '' -ForegroundColor Green
    Add-Content -Path $projectLogPath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | INFO | App URL: $appUrl" -Encoding utf8
    exit 0
}
catch {
    Write-Fail $_.Exception.Message
    Add-Content -Path $projectLogPath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | FAIL | Status: FAILED" -Encoding utf8
    Write-Host 'Status: FAILED' -ForegroundColor Red
    Write-Host "App: $appUrl" -ForegroundColor Yellow
    exit 1
}