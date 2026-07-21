@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0PF07-KVM-Evidence.ps1"
exit /b %ERRORLEVEL%
