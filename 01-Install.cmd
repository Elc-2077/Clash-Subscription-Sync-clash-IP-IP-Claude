@echo off
setlocal
title Install Clash subscription sync
echo Extract the whole ZIP first. Fill in user-config.yaml with YOUR OWN nodes before installing.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0Entry.ps1" -Action Install
pause
