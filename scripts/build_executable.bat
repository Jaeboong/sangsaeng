@echo off
setlocal EnableExtensions
set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"
where python >nul 2>&1
if errorlevel 1 exit /b 1
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Sangsaeng_Report_Automation --paths "%PROJECT_ROOT%" --collect-all googleapiclient --collect-all google.auth --collect-all google.oauth2 --distpath "%PROJECT_ROOT%" --workpath "%PROJECT_ROOT%\output\build\pyinstaller\work" --specpath "%PROJECT_ROOT%\output\build\pyinstaller\spec" "%PROJECT_ROOT%\scripts\executable_launcher.py"
exit /b %ERRORLEVEL%
