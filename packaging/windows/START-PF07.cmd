@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-PF07.ps1" -Action Hub
exit /b %ERRORLEVEL%
