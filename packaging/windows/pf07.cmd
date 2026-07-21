@echo off
setlocal
set "PF07_ROOT=%~dp0"
set "PYTHONPATH=%PF07_ROOT%launcher"
set "PYTHONDONTWRITEBYTECODE=1"
where py.exe >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py.exe -3 -B -m pf07_launcher.cli %*
) else (
  python.exe -B -m pf07_launcher.cli %*
)
exit /b %ERRORLEVEL%
