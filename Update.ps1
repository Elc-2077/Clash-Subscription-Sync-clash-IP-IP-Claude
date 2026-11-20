#Requires -RunAsAdministrator
$ErrorActionPreference='Stop'
$source=$PSScriptRoot
$destination=Join-Path $env:ProgramData 'ClashSubscriptionSync'
$taskName='ClashSubscriptionSync'
$log=Join-Path $source ('update-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+$PID+'.log')
$mutex=New-Object Threading.Mutex($false,'Global\ClashSubscriptionSyncInstaller')
$owned=$false;$stopped=$false;$replaced=$false;$backup=$null
try{$owned=$mutex.WaitOne(0)}catch [Threading.AbandonedMutexException]{$owned=$true}
if(-not $owned){Write-Host 'Another installer is running.';$mutex.Dispose();exit 1}
Start-Transcript -Path $log -Force|Out-Null
try{
    $null=Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
    $settings=Get-Content -LiteralPath (Join-Path $destination 'settings.json') -Raw -Encoding UTF8|ConvertFrom-Json
    $helper=Join-Path $source 'update_support.py'
    if(-not(Test-Path -LiteralPath $helper)){throw 'Missing update_support.py'}
    if(-not(Test-Path -LiteralPath $settings.python)){throw 'Installed Python runtime is missing.'}
    foreach($name in @('sync.py','sync_model.py')){
        if(-not(Test-Path -LiteralPath (Join-Path $source $name))){throw ('Missing update file: '+$name)}
    }
    # Parse the new sources before stopping the existing synchronizer.
    & $settings.python $helper validate-source $source
    if($LASTEXITCODE -ne 0){throw 'Update sources failed syntax validation.'}
    $backup=Join-Path $destination ('backups\retention-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+$PID)
    New-Item -ItemType Directory -Path $backup -Force|Out-Null
    foreach($name in @('sync.py','sync_model.py')){Copy-Item -LiteralPath (Join-Path $destination $name) -Destination (Join-Path $backup $name) -Force}
    Stop-ScheduledTask -TaskName $taskName
    $stopped=$true
    # Stop only the installed synchronization worker and its own descendants.
    # Never terminate Clash or touch firewall, DNS adapters, or default routes.
    & $settings.python $helper stop-workers (Join-Path $destination 'sync.py')
    if($LASTEXITCODE -ne 0){throw 'Could not stop the existing synchronization worker safely.'}
    $replaced=$true
    foreach($name in @('sync.py','sync_model.py')){Copy-Item -LiteralPath (Join-Path $source $name) -Destination (Join-Path $destination $name) -Force}
    # Old bytecode must not hide the update on same-size/same-time replacements.
    & $settings.python $helper clear-bytecode $destination
    if($LASTEXITCODE -ne 0){throw 'Could not clear old synchronization bytecode.'}
    $started=[datetimeoffset]::Now
    Start-ScheduledTask -TaskName $taskName
    $fresh=$false
    for($i=0;$i -lt 24;$i++){
        Start-Sleep -Milliseconds 500
        $statusPath=Join-Path $destination 'data\status.json'
        if(Test-Path -LiteralPath $statusPath){
            try{
                $status=Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8|ConvertFrom-Json
                if([datetimeoffset]$status.time -ge $started.AddSeconds(-1) -and (Get-ScheduledTask -TaskName $taskName).State -eq 'Running'){$fresh=$true;break}
            }catch{}
        }
    }
    if(-not $fresh){throw 'Updated background task did not report a fresh status.'}
    [ordered]@{installed=$true;retention_policy='all-valid-subscription-nodes';state_poll_seconds=60;time=[datetimeoffset]::Now.ToString('o');state=$status.state;firewall_changes=$false}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $source 'update-result.json') -Encoding UTF8
    Write-Host 'ALL NODES RETENTION INSTALLED' -ForegroundColor Green
    Write-Host 'CURRENT STATE EXPORT ENABLED: every 60 seconds (read-only core API).' -ForegroundColor Green
    Write-Host 'Use your original Clash Verge icon. If Clash is open, allow the background refresh to finish.'
    Write-Host 'All valid subscription nodes are retained. Pending DNS nodes reject connections until resolved.'
    Write-Host 'Credentials, subscription, fixed exit, and Cloudflare DNS settings were preserved.'
    Write-Host ('Live status: '+(Join-Path $settings.report_dir 'sync-status.json'))
}catch{
    $failure=$_.Exception.Message
    if($stopped){
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if($replaced -and $backup){
            & $settings.python $helper stop-workers (Join-Path $destination 'sync.py')
            foreach($name in @('sync.py','sync_model.py')){Copy-Item -LiteralPath (Join-Path $backup $name) -Destination (Join-Path $destination $name) -Force}
            & $settings.python $helper clear-bytecode $destination
        }
        Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    }
    Write-Host ('UPDATE FAILED: '+$failure) -ForegroundColor Red
    throw
}finally{
    Stop-Transcript|Out-Null
    if($owned){$mutex.ReleaseMutex()}
    $mutex.Dispose()
}
