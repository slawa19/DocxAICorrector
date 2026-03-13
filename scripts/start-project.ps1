. $PSScriptRoot\_shared.ps1

try {
    Write-Step 'Проверяю структуру проекта'
    if (-not (Test-Path $wslControlScript)) { throw "Не найден WSL helper script: $wslControlScript" }
    if (-not (Test-Path $appPath)) { throw "Не найден app.py: $appPath" }
    Write-Ok 'Файлы проекта на месте'

    Write-Step 'Проверяю runtime status проекта'
    $status = Get-ProjectRuntimeStatus

    $healthOk = ConvertTo-BoolFlag $status['health_ok']
    $appPageOk = ConvertTo-BoolFlag $status['app_page_ok']
    $managedPidRunning = ConvertTo-BoolFlag $status['managed_pid_running']
    $portOpen = ConvertTo-BoolFlag $status['port_open']
    $venvOk = ConvertTo-BoolFlag $status['venv_ok']
    $depsOk = ConvertTo-BoolFlag $status['deps_ok']
    $pandocOk = ConvertTo-BoolFlag $status['pandoc_ok']
    $apiKeyOk = ConvertTo-BoolFlag $status['api_key_ok']
    $managedPid = $status['managed_pid']

    if ($managedPidRunning) {
        if ($healthOk -and $appPageOk) {
            Write-Ok "Проект уже запущен. PID=$managedPid"
            Write-Host "URL: $appUrl" -ForegroundColor Green
            exit 0
        }

        Write-Warn "Найден управляемый WSL-процесс приложения (PID=$managedPid), но приложение ещё не отвечает по основному URL. Жду готовности."
        if (-not (Wait-ProjectReady -Port $port -TimeoutSeconds 30)) {
            throw "Найден управляемый WSL-процесс приложения (PID=$managedPid), но приложение так и не стало доступно по основному URL. Проверьте .run/streamlit.log или выполните Stop Project перед повторным запуском."
        }

        Write-Ok "Проект уже запущен. PID=$managedPid"
        Write-Host "URL: $appUrl" -ForegroundColor Green
        exit 0
    }

    if ($portOpen) {
        throw "Порт $port уже занят чужим процессом или незарегистрированным запуском. Освободите порт или используйте scripts/status-project.ps1 для диагностики."
    }

    Write-Warn 'Пропускаю тяжёлый preflight окружения для быстрого старта. Для полной диагностики используйте Project Status.'

    Write-Step 'Запускаю Streamlit в WSL'
    $runOutput = Invoke-WslInProject 'run-streamlit' @($serverHost, "$port") 2>&1
    if ($LASTEXITCODE -ne 0) {
        $detail = ($runOutput | Out-String).Trim()
        throw "Не удалось запустить Streamlit в WSL.`n$detail"
    }

    Write-Step 'Ожидаю полной готовности приложения'
    if (-not (Wait-ProjectReady -Port $port -TimeoutSeconds 180)) {
        $tailOutput = Invoke-WslInProject 'tail-log' @('80') 2>&1
        $tailText = ($tailOutput | Out-String).Trim()
        if ($tailText) {
            Write-Warn "Последние строки streamlit.log:`n$tailText"
        }
        throw 'Приложение не стало доступно по основному URL за 180 секунд.'
    }

    Write-Ok 'Сервер доступен'
    Write-Host '' -ForegroundColor Green
    Write-Host '========================================' -ForegroundColor Green
    Write-Host "  App: $appUrl" -ForegroundColor Green
    Write-Host "  Health: $appUrl/_stcore/health" -ForegroundColor Green
    Write-Host '  Для остановки: Terminal > Run Task > Stop Project' -ForegroundColor Green
    Write-Host '========================================' -ForegroundColor Green
    Write-Host '' -ForegroundColor Green
    Append-ProjectLogEntry "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | INFO | App URL: $appUrl"
    exit 0
}
catch {
    Write-Fail $_.Exception.Message
    Append-ProjectLogEntry "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | FAIL | Status: FAILED"
    Write-Host 'Status: FAILED' -ForegroundColor Red
    Write-Host "App: $appUrl" -ForegroundColor Yellow
    exit 1
}