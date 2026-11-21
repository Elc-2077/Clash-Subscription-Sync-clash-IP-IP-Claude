param([switch]$EnableAirportFallback,[switch]$EnableIsland)
$ErrorActionPreference='Stop'
try{
    $target=Join-Path $PSScriptRoot 'Update.ps1'
    foreach($name in @('Update.ps1','update_support.py','sync.py','sync_model.py','island.py','island_probe.py','island_flags.py')){
        if(-not(Test-Path -LiteralPath (Join-Path $PSScriptRoot $name))){throw ('Missing '+$name+'. Extract the complete update package and run 03-Update.cmd from that folder.')}
    }
    $arguments='-NoProfile -NoExit -ExecutionPolicy Bypass -File "'+$target+'"'
    if($EnableAirportFallback){$arguments+=' -EnableAirportFallback'}
    if($EnableIsland){$arguments+=' -EnableIsland'}
    Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Verb RunAs -ArgumentList $arguments -Wait
}catch{Write-Host $_.Exception.Message -ForegroundColor Red;Read-Host 'Press Enter to close'}
