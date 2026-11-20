#Requires -RunAsAdministrator
$ErrorActionPreference='Stop'
$source=$PSScriptRoot
$destination=Join-Path $env:ProgramData 'ClashSubscriptionSync'
$taskName='ClashSubscriptionSync'
$created=$false;$initialized=$false;$python=$null
$log=Join-Path $source ('install-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+$PID+'.log')
$mutex=New-Object Threading.Mutex($false,'Global\ClashSubscriptionSyncInstaller')
$owned=$false
try{$owned=$mutex.WaitOne(0)}catch [Threading.AbandonedMutexException]{$owned=$true}
if(-not $owned){Write-Host 'Another installer is running. Keep its window open.';$mutex.Dispose();exit 1}
Start-Transcript -Path $log -Force|Out-Null
try{
    if(Get-Process clash-verge -ErrorAction SilentlyContinue){throw 'Fully EXIT Clash from the tray menu before installation.'}
    $userConfig=Join-Path $source 'user-config.yaml'
    if(-not(Test-Path -LiteralPath $userConfig)){
        Copy-Item -LiteralPath (Join-Path $source 'user-config.example.yaml') -Destination $userConfig
        throw 'Created user-config.yaml. Fill in YOUR OWN final exit and bootstrap nodes, then run this installer again.'
    }
    if(Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue){throw 'A subscription sync task already exists. Remove it using its own uninstaller before installing another copy.'}
    if(Get-ScheduledTask -TaskName 'ClashFixedExitGuard' -ErrorAction SilentlyContinue){throw 'An old custom network guard exists. Roll it back before installing this tool.'}
    $candidates=@()
    if($env:CLASH_SYNC_PYTHON){$candidates+=@($env:CLASH_SYNC_PYTHON)}
    $py=Get-Command py.exe -ErrorAction SilentlyContinue
    if($py){try{$candidate=& $py.Source -3 -c 'import sys;print(sys.executable)' 2>$null;if($LASTEXITCODE -eq 0){$candidates+=@($candidate|Select-Object -Last 1)}}catch{}}
    foreach($name in @('python.exe','python3.exe')){
        $command=Get-Command $name -ErrorAction SilentlyContinue
        if($command -and $command.Source -notlike '*\WindowsApps\*'){$candidates+=@($command.Source)}
    }
    foreach($pattern in @((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python*\python.exe'),(Join-Path $env:ProgramFiles 'Python*\python.exe'),(Join-Path $env:ProgramFiles 'python\python.exe'))){
        $candidates+=@(Get-Item -Path $pattern -ErrorAction SilentlyContinue|ForEach-Object FullName)
    }
    foreach($candidate in @($candidates|Select-Object -Unique)){
        if(-not(Test-Path -LiteralPath $candidate)){continue}
        try{
            & $candidate -c 'import sys,psutil,yaml;assert sys.version_info >= (3,8)' 2>$null
            if($LASTEXITCODE -eq 0){$python=$candidate;break}
        }catch{}
    }
    if(-not $python){throw 'Install Python with PyYAML and psutil first (see README). If needed set CLASH_SYNC_PYTHON to the full python.exe path.'}
    $metadataText=& $python (Join-Path $source 'discover.py') $userConfig
    if($LASTEXITCODE -ne 0){throw 'Your config or local runtime could not be validated. See CONFIG ERROR above; no Clash settings changed.'}
    $metadata=($metadataText -join "`n")|ConvertFrom-Json
    if(-not $metadata.interface){
        $route=Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0'|Where-Object{$_.NextHop -ne '0.0.0.0'}|Sort-Object RouteMetric|Select-Object -First 1
        if(-not $route){throw 'No IPv4 default route found. Set physical_interface in user-config.yaml.'}
        $adapter=Get-NetAdapter|Where-Object ifIndex -eq $route.InterfaceIndex|Select-Object -First 1
        if($adapter.HardwareInterface -ne $true){throw 'Default route uses a virtual adapter. Set physical_interface to your real Ethernet/Wi-Fi adapter name.'}
        $metadata.interface=$adapter.Name
    }else{
        $adapter=Get-NetAdapter -Name $metadata.interface
        if($adapter.Status -ne 'Up'){throw 'Selected physical interface is not up'}
    }
    $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    New-Item -ItemType Directory -Path $destination,(Join-Path $destination 'data') -Force|Out-Null
    $acl=New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true,$false)
    foreach($entry in @(@('S-1-5-18','FullControl'),@('S-1-5-32-544','FullControl'),@($sid,'ReadAndExecute'))){
        $id=New-Object Security.Principal.SecurityIdentifier($entry[0])
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($id,$entry[1],'ContainerInherit,ObjectInherit','None','Allow')))
    }
    Set-Acl -LiteralPath $destination -AclObject $acl
    foreach($name in @('sync.py','sync_model.py','Routes.ps1','setup_config.py','Uninstall.ps1')){
        Copy-Item -LiteralPath (Join-Path $source $name) -Destination (Join-Path $destination $name) -Force
    }
    Copy-Item -LiteralPath $userConfig -Destination (Join-Path $destination 'user-config.yaml') -Force
    $settings=[ordered]@{base=$metadata.base;python=$metadata.python;core=$metadata.core;interface=$metadata.interface;report_dir=$source;userSid=$sid;shareVersion=1}
    $settings|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $destination 'settings.json') -Encoding UTF8
    # No network lock or endpoint routes are applied during initial setup.
    & $python (Join-Path $destination 'setup_config.py')
    if($LASTEXITCODE -ne 0){throw 'First setup did not complete. Previous Clash configuration is retained; no scheduled task was registered.'}
    $initialized=$true
    $action=New-ScheduledTaskAction -Execute $metadata.pythonw -Argument ('-B "'+(Join-Path $destination 'sync.py')+'"') -WorkingDirectory $destination
    $trigger=New-ScheduledTaskTrigger -AtLogOn -User $sid
    $principal=New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Highest
    $options=New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $options -Description 'Airport subscription and endpoint route synchronization only; no firewall changes or application startup interception.' -Force|Out-Null
    $created=$true;$started=Get-Date
    Start-ScheduledTask -TaskName $taskName
    Start-Sleep -Seconds 3
    $task=Get-ScheduledTask -TaskName $taskName
    $status=Get-Content -LiteralPath (Join-Path $destination 'data\status.json') -Encoding UTF8 -Raw|ConvertFrom-Json
    if($task.State -ne 'Running' -or $status.state -ne 'WAITING' -or [datetimeoffset]$status.time -lt [datetimeoffset]$started.AddSeconds(-1)){throw 'The synchronizer did not report a fresh ready status'}
    Write-Host 'SUBSCRIPTION SYNC INSTALLED. Open your original Clash Verge shortcut.' -ForegroundColor Green
    Write-Host 'Keep TUN and Global enabled. Update your airport using its normal refresh button in Clash.'
    Write-Host 'First install verified configuration syntax and Cloudflare bootstrap resolution only; verify your actual TCP/UDP exit before relying on it.' -ForegroundColor Yellow
}catch{
    Write-Host ('SETUP FAILED: '+$_.Exception.Message) -ForegroundColor Red
    if($created){
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        foreach($p in @(Get-CimInstance Win32_Process|Where-Object{$_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -like ('*'+$destination+'*')})){
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    if($initialized -and $python){& $python (Join-Path $destination 'setup_config.py') --rollback}
    throw
}finally{Stop-Transcript|Out-Null;if($owned){$mutex.ReleaseMutex()};$mutex.Dispose()}
