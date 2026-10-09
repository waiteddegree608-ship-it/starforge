param(
    [Parameter(Mandatory=$true)][string]$Config,
    [string]$Python = (Get-Command python.exe -ErrorAction Stop).Source
)
$ErrorActionPreference = 'Stop'
$resolvedConfig = (Resolve-Path -LiteralPath $Config).Path
$projectDirectory = Split-Path -Parent $PSScriptRoot
$settings = Get-Content -LiteralPath $resolvedConfig -Raw | ConvertFrom-Json
$existing = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
    $_.CommandLine -like '*-m starforge*' -and $_.CommandLine -like '* loop*' -and
    $_.CommandLine.Contains($resolvedConfig)
}
if ($existing) {
    Write-Output "Starforge is already running: $($existing.ProcessId -join ', ')"
    exit 0
}
$logDirectory = Join-Path $settings.state_dir 'logs'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$arguments = '-X utf8 -m starforge --config "' + $resolvedConfig + '" loop'
$process = Start-Process -FilePath $Python -ArgumentList $arguments -WorkingDirectory $projectDirectory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDirectory "worker-$stamp.stdout") -RedirectStandardError (Join-Path $logDirectory "worker-$stamp.stderr")
Write-Output "Started Starforge PID $($process.Id)"
