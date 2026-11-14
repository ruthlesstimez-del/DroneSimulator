$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $python -u .\download_maps.py
if ($LASTEXITCODE -ne 0) { throw 'Map download failed. Rerun install_maps.ps1 to resume.' }
& $python -u .\extract_maps.py
if ($LASTEXITCODE -ne 0) { throw 'Map extraction failed.' }
Write-Output 'City and Park are installed. Opening City...'
& "$PSScriptRoot\launch_simulator.ps1" -Map City
