@echo off
setlocal
set "PF07_ROOT=%~dp0"
set "PYTHONPATH=%PF07_ROOT%launcher"
where py.exe >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py.exe -3 -m pf07_launcher.cli %*
) else (
  python.exe -m pf07_launcher.cli %*
)
exit /b %ERRORLEVEL%
