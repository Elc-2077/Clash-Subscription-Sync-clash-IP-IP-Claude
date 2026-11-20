[CmdletBinding()]
param([ValidateSet('Install','Uninstall')][string]$Action='Install')
$ErrorActionPreference='Stop'
try{
    $target=if($Action -eq 'Install'){Join-Path $PSScriptRoot 'Install.ps1'}else{Join-Path $env:ProgramData 'ClashSubscriptionSync\Uninstall.ps1'}
    if(-not(Test-Path -LiteralPath $target)){throw 'Required script was not found'}
    $argsText='-NoProfile -NoExit -ExecutionPolicy Bypass -File "'+$target+'"'
    Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Verb RunAs -ArgumentList $argsText -Wait
}catch{Write-Host $_.Exception.Message -ForegroundColor Red;Read-Host 'Press Enter to close';exit 1}
