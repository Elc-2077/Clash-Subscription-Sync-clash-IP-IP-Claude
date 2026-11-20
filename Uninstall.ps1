#Requires -RunAsAdministrator
param([switch]$RestoreOriginalConfig)
$ErrorActionPreference='Stop'
$root=Join-Path $env:ProgramData 'ClashSubscriptionSync'
$taskName='ClashSubscriptionSync'
if(Get-Process clash-verge -ErrorAction SilentlyContinue){throw 'Fully exit Clash before removing subscription sync'}
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
foreach($p in @(Get-CimInstance Win32_Process)){
    if($p.Name -in @('python.exe','pythonw.exe') -and $p.CommandLine -like ('*'+$root+'*')){Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue}
}
if(Test-Path -LiteralPath (Join-Path $root 'settings.json')){
    & (Join-Path $root 'Routes.ps1') -Action Cleanup
}
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
if($RestoreOriginalConfig){
    $settings=Get-Content -LiteralPath (Join-Path $root 'settings.json') -Raw -Encoding UTF8|ConvertFrom-Json
    & $settings.python (Join-Path $root 'setup_config.py') --rollback
    if($LASTEXITCODE -ne 0){throw 'Original Clash configuration could not be restored; backups retained'}
}
Write-Host 'SUBSCRIPTION SYNC REMOVED. Latest working Clash configuration and original startup entry retained.' -ForegroundColor Green
