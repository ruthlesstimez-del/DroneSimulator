$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Get-NetTCPConnection -LocalPort 41451 -State Listen -ErrorAction SilentlyContinue)) {
    & "$PSScriptRoot\launch_simulator.ps1" -Map City
}
Write-Host 'Waiting for AirSim to become ready...'
& $python -u -c @'
import time
import airsim
deadline = time.monotonic() + 90
while time.monotonic() < deadline:
    try:
        client = airsim.MultirotorClient(timeout_value=2)
        if client.ping():
            vehicles = client.listVehicles()
            if 'PlayerDrone' in vehicles:
                raise SystemExit('Drone Duel is running. Close that simulator before starting the single-drone project.')
            if 'Drone1' not in vehicles:
                raise SystemExit('The running simulator has no Drone1. Close it and rerun this launcher.')
            print('AirSim ready. Vehicles:', vehicles)
            break
    except Exception:
        pass
    time.sleep(1)
else:
    raise SystemExit('AirSim did not become ready. Check the simulator window.')
'@
if ($LASTEXITCODE -ne 0) { throw 'Simulator startup failed.' }
& $python -u .\performance_setup.py
if ($LASTEXITCODE -ne 0) { throw 'Performance setup failed.' }
$processes = Get-CimInstance Win32_Process -Filter "Name='python.exe'"
foreach ($name in @('manual_control.py', 'map_view.py', 'aim_overlay.py')) {
    $script = Join-Path $PSScriptRoot $name
    $existing = $processes | Where-Object {
        $_.CommandLine -and $_.CommandLine.Contains($script)
    }
    if (-not $existing) {
        Start-Process -FilePath $python -ArgumentList @('-u', "`"$script`"") -WorkingDirectory $PSScriptRoot
    }
}
Write-Host 'Project running: high graphics, third-person view, mouse crosshair. T takeoff; WASD fly; arrows altitude; Shift boost; click to fire; L land. B follow; / chase; I front; K rear.'
