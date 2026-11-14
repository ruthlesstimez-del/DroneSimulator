param(
    [ValidateSet('City', 'Park', 'Blocks')]
    [string]$Map = 'City',
    [ValidateSet('Project', 'Duel')]
    [string]$Mode = 'Project'
)
$ErrorActionPreference = 'Stop'
$mapFolders = @{ City = 'City'; Park = 'Park'; Blocks = 'Blocks' }
$folder = Join-Path "$PSScriptRoot\simulator" $mapFolders[$Map]
if (-not (Test-Path -LiteralPath $folder)) {
    throw "$Map is not installed yet. Run .\.venv\Scripts\python.exe .\extract_maps.py after downloads finish."
}
$exe = Get-ChildItem -LiteralPath $folder -Filter *.exe -Recurse |
    Where-Object { $_.Directory.Name -eq 'WindowsNoEditor' } |
    Select-Object -First 1
if (-not $exe) { throw "No simulator launcher found for $Map in $folder" }
if (Get-NetTCPConnection -LocalPort 41451 -State Listen -ErrorAction SilentlyContinue) {
    throw 'An AirSim map is already running. Close its window before opening another map.'
}
$settings = Join-Path $PSScriptRoot $(if ($Mode -eq 'Duel') {'settings_duel.json'} else {'settings.json'})
Start-Process -FilePath $exe.FullName -WorkingDirectory $exe.DirectoryName -ArgumentList @("-settings=`"$settings`"", '-windowed', '-ResX=1280', '-ResY=720', '-nosplash')
