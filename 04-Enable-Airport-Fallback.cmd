@echo off
setlocal
if not exist "%~dp0Update-Entry.ps1" (
    echo Extract the complete ZIP. Do not copy this CMD alone.
    pause
    exit /b 1
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0Update-Entry.ps1" -EnableAirportFallback
pause
