@echo off
rem Launcher for start-project.ps1 that works by double-click in Explorer and from any console.
rem The machine's default execution policy (Undefined = Restricted) refuses a .ps1 started
rem directly, so this runs it with -ExecutionPolicy Bypass for this one process only; the
rem machine policy is not changed. The window stays open when started from Explorer, so the
rem result can be read; set DOCX_AI_NO_PAUSE=1 to skip that. Returns the script's exit code.
rem No labels or parenthesised blocks: the repository checks .cmd files out with LF endings.
setlocal
set "DOCXAI_LAUNCHER_PAUSE="
echo "%CMDCMDLINE%" | "%SystemRoot%\System32\find.exe" /i "%~nx0" >nul && set "DOCXAI_LAUNCHER_PAUSE=1"
if defined DOCX_AI_NO_PAUSE set "DOCXAI_LAUNCHER_PAUSE="
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-project.ps1" %*
set "DOCXAI_LAUNCHER_EXIT=%ERRORLEVEL%"
if defined DOCXAI_LAUNCHER_PAUSE echo.
if defined DOCXAI_LAUNCHER_PAUSE pause
exit /b %DOCXAI_LAUNCHER_EXIT%
