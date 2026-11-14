param([switch]$Verify)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$folder=Join-Path $PSScriptRoot 'duel_artifacts'
New-Item -ItemType Directory -Force -Path $folder | Out-Null
if (-not (Test-Path (Join-Path $folder 'policy.npy'))) {
    & $python -u .\duel_learning.py
    if ($LASTEXITCODE -ne 0) {throw 'Duel policy training failed'}
}
$names=@('manual_control.py','map_view.py','aim_overlay.py','mission_view.py','duel_game.py','duel_hud.py','rl_project.py','duel_camera.py','role_labels.py')
$paths=$names | ForEach-Object {Join-Path $PSScriptRoot $_}
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $command=$_.CommandLine
    $command -and @($paths | Where-Object {$command.Contains($_)}).Count -gt 0
} | ForEach-Object {Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue}
$cityRoot=Join-Path $PSScriptRoot 'simulator\City'
Get-CimInstance Win32_Process -Filter "Name='CityEnviron.exe'" | Where-Object {
    $_.ExecutablePath -and $_.ExecutablePath.StartsWith($cityRoot,[StringComparison]::OrdinalIgnoreCase)
} | ForEach-Object {Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue}
foreach ($name in @('state.json','verification.json','radar_verification.json','crash_verification.json')) {
    $file=Join-Path $folder $name
    if (Test-Path -LiteralPath $file) {Remove-Item -LiteralPath $file}
}
& "$PSScriptRoot\launch_simulator.ps1" -Map City -Mode Duel
& $python -u -c @'
import time,airsim
deadline=time.monotonic()+90
while time.monotonic()<deadline:
    try:
        c=airsim.MultirotorClient(timeout_value=2)
        if {'Drone1','PlayerDrone'}.issubset(set(c.listVehicles())):
            print('Two-drone simulator ready')
            break
    except Exception:
        pass
    time.sleep(1)
else:
    raise SystemExit('Duel simulator startup timed out')
'@
if ($LASTEXITCODE -ne 0) {throw 'Duel startup failed'}
& $python .\performance_setup.py
$game=Join-Path $PSScriptRoot 'duel_game.py'
$arguments=@('-u',"`"$game`"",'--autostart')
if ($Verify) {$arguments+='--verify'}
$gameProcess=Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $folder 'game.log') -RedirectStandardError (Join-Path $folder 'error.log')
$hud=Join-Path $PSScriptRoot 'duel_hud.py'
Start-Process -FilePath $python -ArgumentList @('-u',"`"$hud`"") -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
$deadline=(Get-Date).AddSeconds(120)
$ready=$false
while ((Get-Date) -lt $deadline) {
    if ($gameProcess.HasExited) {throw 'Duel controller exited. Read duel_artifacts/error.log.'}
    $file=Join-Path $folder 'state.json'
    if (Test-Path $file) {
        try {
            $state=Get-Content -LiteralPath $file -Raw | ConvertFrom-Json
            $verified=(-not $Verify) -or (Test-Path (Join-Path $folder 'verification.json'))
            if ($state.phase -in @('paused','starting','active') -and $verified -and ((-not $Verify) -or $state.round -ge 2)) {
                $ready=$true
                break
            }
        } catch {}
    }
    Start-Sleep -Milliseconds 300
}
if (-not $ready) {throw 'Duel did not become ready. Read duel_artifacts/game.log and error.log.'}
$camera=Join-Path $PSScriptRoot 'duel_camera.py'
Start-Process -FilePath $python -ArgumentList @('-u',"`"$camera`"") -WorkingDirectory $PSScriptRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $folder 'camera.log') -RedirectStandardError (Join-Path $folder 'camera_error.log')
& $python "$PSScriptRoot\mission_windows.py" --keep-view
$labels=Join-Path $PSScriptRoot 'role_labels.py'
Start-Process -FilePath $python -ArgumentList @('-u',"`"$labels`"") -WorkingDirectory $PSScriptRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $folder 'labels.log') -RedirectStandardError (Join-Path $folder 'labels_error.log')
Write-Host 'GAME RUNNING. You control PlayerDrone; AI radar chase starts automatically. WASD fly; arrows altitude; Shift boost; F9 respawn.'
