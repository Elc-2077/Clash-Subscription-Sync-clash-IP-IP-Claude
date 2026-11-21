$ErrorActionPreference='Stop'
$source=Split-Path $PSScriptRoot -Parent
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('clash-sync-update-test-'+[guid]::NewGuid().ToString('N'))
$python=if($env:CLASH_SYNC_TEST_PYTHON){$env:CLASH_SYNC_TEST_PYTHON}else{(Get-Command python.exe -ErrorAction Stop).Source}
$null=New-Item -ItemType Directory -Path $fixture
function Start-Transcript {param($Path,[switch]$Force)}
function Stop-Transcript {}
function Get-ScheduledTask {param($TaskName) [pscustomobject]@{State=if($global:fixtureTaskRunning){'Running'}else{'Ready'}}}
function Stop-ScheduledTask {param($TaskName) $global:fixtureTaskRunning=$false}
function Start-ScheduledTask {
 param($TaskName)
 $global:fixtureTaskRunning=$true
 @{state='WAITING';time=[datetimeoffset]::Now.ToString('o')}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $global:fixtureInstalled 'data\status.json') -Encoding UTF8
}
function Start-Sleep {param($Milliseconds)}
function Copy-Item {
 param($LiteralPath,$Destination,[switch]$Force)
 if($global:fixtureFailCopy -and (Split-Path $LiteralPath -Leaf) -eq 'sync_model.py' -and (Split-Path $LiteralPath -Parent) -eq $global:fixturePackage -and (Split-Path $Destination -Parent) -eq $global:fixtureInstalled){$global:fixtureFailCopy=$false;throw 'Synthetic copy failure'}
 Microsoft.PowerShell.Management\Copy-Item -LiteralPath $LiteralPath -Destination $Destination -Force:$Force
}
$previousProgramData=$env:ProgramData
try{
 foreach($scenario in @('success','fallback-island','rollback')){
  $env:ProgramData=Join-Path $fixture $scenario
  $global:fixtureInstalled=Join-Path $env:ProgramData 'ClashSubscriptionSync'
  $global:fixturePackage=Join-Path $env:ProgramData 'package'
  $null=New-Item -ItemType Directory -Path (Join-Path $global:fixtureInstalled 'data'),$global:fixturePackage -Force
  foreach($name in @('sync.py','sync_model.py','update_support.py','island.py','island_probe.py','island_flags.py')){Copy-Item -LiteralPath (Join-Path $source $name) -Destination (Join-Path $global:fixturePackage $name)}
  $code=Get-Content -LiteralPath (Join-Path $source 'Update.ps1') -Raw -Encoding UTF8
  $code=$code.Replace('#Requires -RunAsAdministrator','')
  Set-Content -LiteralPath (Join-Path $global:fixturePackage 'Update.ps1') -Value $code -Encoding UTF8
  foreach($name in @('sync.py','sync_model.py')){Set-Content -LiteralPath (Join-Path $global:fixtureInstalled $name) -Value '# old fixture' -Encoding UTF8}
  @{python=$python;report_dir=$global:fixturePackage}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $global:fixtureInstalled 'settings.json') -Encoding UTF8
  $seedPath=Join-Path $global:fixtureInstalled 'data\seed.json'
  Set-Content -LiteralPath $seedPath -Value '{"synthetic":"preserve"}' -Encoding UTF8
  $beforeSeed=[IO.File]::ReadAllBytes($seedPath)
  $global:fixtureTaskRunning=$true;$global:fixtureFailCopy=$scenario -eq 'rollback';$threw=$false
  $beforeSettings=[IO.File]::ReadAllBytes((Join-Path $global:fixtureInstalled 'settings.json'))
  try{& (Join-Path $global:fixturePackage 'Update.ps1') -EnableAirportFallback:($scenario -ne 'success') -EnableIsland:($scenario -ne 'success')}catch{$threw=$true;if($scenario -ne 'rollback'){throw}}
  if(-not $global:fixtureTaskRunning){throw 'Task was not restarted'}
  if([Convert]::ToBase64String($beforeSeed) -ne [Convert]::ToBase64String([IO.File]::ReadAllBytes($seedPath))){throw 'Seed changed'}
  if($scenario -ne 'rollback'){
   foreach($name in @('sync.py','sync_model.py')){
    if((Get-FileHash -LiteralPath (Join-Path $source $name)).Hash -ne (Get-FileHash -LiteralPath (Join-Path $global:fixtureInstalled $name)).Hash){throw 'New code not installed'}
   }
   if(-not(Test-Path -LiteralPath (Join-Path $global:fixturePackage 'update-result.json'))){throw 'Missing success report'}
   $changed=Get-Content -LiteralPath (Join-Path $global:fixtureInstalled 'settings.json') -Raw -Encoding UTF8|ConvertFrom-Json
   if($scenario -eq 'fallback-island' -and (-not $changed.fallback_to_airport -or -not $changed.enable_island)){throw 'Feature flags were not saved'}
   foreach($name in @('island.py','island_probe.py','island_flags.py')){if(-not(Test-Path -LiteralPath (Join-Path $global:fixtureInstalled $name))){throw 'Island files missing'}}
  }else{
   if(-not $threw){throw 'Injected copy failure did not throw'}
   foreach($name in @('sync.py','sync_model.py')){
    if((Get-Content -LiteralPath (Join-Path $global:fixtureInstalled $name) -Raw).Trim() -ne '# old fixture'){throw 'Old code was not restored'}
   }
   if([Convert]::ToBase64String($beforeSettings) -ne [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $global:fixtureInstalled 'settings.json')))){throw 'Settings not restored'}
   foreach($name in @('island.py','island_probe.py','island_flags.py')){if(Test-Path -LiteralPath (Join-Path $global:fixtureInstalled $name)){throw 'New island files were not rolled back'}}
  }
  Write-Host ('PASS updater '+$scenario)
 }
}finally{$env:ProgramData=$previousProgramData}
