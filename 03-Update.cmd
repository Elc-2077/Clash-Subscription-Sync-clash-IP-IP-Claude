@echo off
setlocal
title Update subscription node retention
if not exist "%~dp0Update-Entry.ps1" (
    echo Update files are missing. Extract the complete ZIP and run 03-Update.cmd inside that folder.
    echo To launch from Desktop, create a shortcut to the original file; do not copy the CMD alone.
    pause
    exit /b 1
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0Update-Entry.ps1"
pause
