$expected = @{
    'CityEnviron.zip.001' = 2000000000
    'CityEnviron.zip.002' = 966789399
    'AbandonedPark.zip' = 1269678666
}
foreach ($name in $expected.Keys | Sort-Object) {
    $path = Join-Path "$PSScriptRoot\downloads" $name
    $bytes = if (Test-Path -LiteralPath $path) { (Get-Item -LiteralPath $path).Length } else { 0 }
    [pscustomobject]@{
        File = $name
        DownloadedMB = [math]::Round($bytes / 1MB)
        TotalMB = [math]::Round($expected[$name] / 1MB)
        Percent = [math]::Round(100 * $bytes / $expected[$name], 1)
    }
}
foreach ($map in @('City', 'Park')) {
    $path = Join-Path "$PSScriptRoot\simulator" $map
    $found = if (Test-Path -LiteralPath $path) {
        Get-ChildItem -LiteralPath $path -Filter *.exe -Recurse |
            Where-Object { $_.Directory.Name -eq 'WindowsNoEditor' }
    }
    Write-Host "$map launcher extracted: $([bool]$found)"
}
