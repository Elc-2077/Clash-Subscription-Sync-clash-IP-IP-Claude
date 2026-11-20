@echo off
setlocal
title Remove Clash subscription sync
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0Entry.ps1" -Action Uninstall
pause
