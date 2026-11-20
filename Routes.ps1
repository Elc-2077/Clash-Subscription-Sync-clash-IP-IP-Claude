#Requires -RunAsAdministrator
param([ValidateSet('Add','Cleanup')][string]$Action)
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$data=Join-Path $root 'data'
$statePath=Join-Path $data 'routes.json'
$settings=Get-Content -LiteralPath (Join-Path $root 'settings.json') -Raw -Encoding UTF8|ConvertFrom-Json
$metric=42777
function Save-Routes($records){
    $temporary=$statePath+'.new'
    @{routes=@($records)}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $temporary -Encoding UTF8
    if([IO.File]::Exists($statePath)){[IO.File]::Replace($temporary,$statePath,[Management.Automation.Language.NullString]::Value)}
    else{[IO.File]::Move($temporary,$statePath)}
}
$records=@()
if(Test-Path -LiteralPath $statePath){$records=@((Get-Content -LiteralPath $statePath -Raw -Encoding UTF8|ConvertFrom-Json).routes)}
if($Action -eq 'Cleanup'){
    $adapters=@(Get-NetAdapter)
    foreach($batch in @($records|Group-Object{$_.guid+'|'+$_.gateway})){
        $first=$batch.Group[0]
        $adapter=$adapters|Where-Object{([guid]$_.InterfaceGuid) -eq ([guid]$first.guid)}
        if($adapter){
            Get-NetRoute -AddressFamily IPv4 -DestinationPrefix @($batch.Group.prefix) -InterfaceIndex $adapter.ifIndex -PolicyStore ActiveStore -ErrorAction SilentlyContinue|
                Where-Object{$_.NextHop -eq $first.gateway -and $_.RouteMetric -eq $metric}|Remove-NetRoute -Confirm:$false
        }
    }
    if(Test-Path -LiteralPath $statePath){Remove-Item -LiteralPath $statePath}
    exit 0
}
if(-not(Get-Process clash-verge -ErrorAction SilentlyContinue)){throw 'Clash exited; no endpoint routes added'}
$adapter=Get-NetAdapter -Name $settings.interface -ErrorAction Stop
$gateway=Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -InterfaceIndex $adapter.ifIndex|Sort-Object RouteMetric|Select-Object -First 1
if(-not $gateway){throw 'Physical IPv4 gateway missing'}
$addresses=@((Get-Content -LiteralPath (Join-Path $data 'endpoints.json') -Raw -Encoding UTF8|ConvertFrom-Json).addresses)
foreach($value in $addresses){
    $ip=$null
    if(-not[Net.IPAddress]::TryParse($value,[ref]$ip) -or $ip.AddressFamily -ne 'InterNetwork'){throw 'Invalid endpoint IPv4'}
    if(-not(Get-Process clash-verge -ErrorAction SilentlyContinue)){throw 'Clash exited; remaining endpoint routes not added'}
    $prefix=$ip.ToString()+'/32'
    $existing=@(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix $prefix -InterfaceIndex $adapter.ifIndex -PolicyStore ActiveStore -ErrorAction SilentlyContinue|Where-Object NextHop -eq $gateway.NextHop)
    if($existing.Count){continue}
    $record=[pscustomobject]@{prefix=$prefix;guid=([guid]$adapter.InterfaceGuid).ToString('D');gateway=$gateway.NextHop;metric=$metric}
    if(-not @($records|Where-Object{$_.prefix -eq $record.prefix -and $_.guid -eq $record.guid -and $_.gateway -eq $record.gateway}).Count){$records+=@($record);Save-Routes $records}
    New-NetRoute -DestinationPrefix $prefix -InterfaceIndex $adapter.ifIndex -NextHop $gateway.NextHop -RouteMetric $metric -PolicyStore ActiveStore|Out-Null
}
