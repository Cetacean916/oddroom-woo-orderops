@echo off
setlocal
set "PF07_ROOT=%~dp0"
set "PYTHONPATH=%PF07_ROOT%launcher"
set "PYTHONDONTWRITEBYTECODE=1"
where py.exe >nul 2>nul
if %ERRORLEVEL% EQU 0 goto use_py
where python.exe >nul 2>nul
if %ERRORLEVEL% NEQ 0 goto python_required
python.exe -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if %ERRORLEVEL% NEQ 0 goto python_required
python.exe -B -m pf07_launcher.cli %*
exit /b %ERRORLEVEL%

:use_py
py.exe -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if %ERRORLEVEL% NEQ 0 goto python_required
py.exe -3 -B -m pf07_launcher.cli %*
exit /b %ERRORLEVEL%

:python_required
echo Python 3.10 or newer is required. Install it from https://www.python.org/downloads/windows/ and retry. 1>&2
exit /b 20
