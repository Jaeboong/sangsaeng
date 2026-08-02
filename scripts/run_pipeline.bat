@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"

set "PAUSE_ON_EXIT=1"
if /I "%~1"=="--no-pause" (
    set "PAUSE_ON_EXIT=0"
    shift
)

where python >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Python executable not found.
    set "EXIT_CODE=1"
    goto :finish
)

python -B -m src.pipeline --env-file "%PROJECT_ROOT%\.env" %*
set "EXIT_CODE=%ERRORLEVEL%"

if "%EXIT_CODE%"=="0" (
    echo.
    echo [SUCCESS] Pipeline completed.
) else (
    echo.
    echo [FAIL] Pipeline stopped. Check output\logs.
)

:finish
if "%PAUSE_ON_EXIT%"=="1" pause
exit /b %EXIT_CODE%
