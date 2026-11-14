param([int]$Episodes = 20000)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$duel = Join-Path $PSScriptRoot 'duel_game.py'
if (Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {$_.CommandLine -and $_.CommandLine.Contains($duel)}) {
    throw 'Stop Drone Duel before starting the stationary-target mission.'
}
$controller = Join-Path $PSScriptRoot 'manual_control.py'
$viewer = Join-Path $PSScriptRoot 'mission_view.py'
$viewRunning = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object {$_.CommandLine -and $_.CommandLine.Contains($viewer)}
if (-not $viewRunning) {
    Start-Process -FilePath $python -ArgumentList @('-u', "`"$viewer`"") -WorkingDirectory $PSScriptRoot
}
# RL gets exclusive flight control; restore manual input on completion/failure.
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object {$_.CommandLine -and $_.CommandLine.Contains($controller)} |
    ForEach-Object {Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue}
try {
    & $python -u "$PSScriptRoot\rl_project.py" --episodes $Episodes
    if ($LASTEXITCODE -ne 0) { throw 'RL run stopped. See rl_artifacts/mission_result.json.' }
}
finally {
    Start-Process -FilePath $python -ArgumentList @('-u', "`"$controller`"") -WorkingDirectory $PSScriptRoot
}
