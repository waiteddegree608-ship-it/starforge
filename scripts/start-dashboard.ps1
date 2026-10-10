param([string]$Config='E:\APPdata\starforge\config.json',[int]$Port=8766)
$projectRoot=Split-Path -Parent $PSScriptRoot
$existing=Get-CimInstance Win32_Process | Where-Object {$_.Name -match '^python' -and $_.CommandLine -match 'starforge.dashboard'}
if ($existing) { Write-Output "Dashboard already running: http://127.0.0.1:$Port"; exit }
$pythonPath=(Get-Command python).Source
Start-Process -FilePath $pythonPath -ArgumentList @('-X','utf8','-m','starforge.dashboard','--config', $Config,'--port', $Port) -WorkingDirectory $projectRoot -WindowStyle Hidden
Write-Output "Dashboard: http://127.0.0.1:$Port"
