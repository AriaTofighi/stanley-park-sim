param(
    [string]$OutputPath,
    [string]$VerifyAgainst,
    [ValidateSet('Development','Shipping')][string]$Configuration = 'Development'
)
$ErrorActionPreference = 'Stop'
if ([bool]$OutputPath -eq [bool]$VerifyAgainst) { throw 'Select OutputPath or VerifyAgainst.' }
$ProjectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$Records = [Collections.Generic.List[object]]::new()
$Files = @((Get-Item -LiteralPath (Join-Path $ProjectRoot 'unreal\StanleyParkSim.uproject')))
foreach ($Directory in @('unreal\Source', 'unreal\Config', 'unreal\Content')) {
    $Files += @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot $Directory) -File -Recurse)
}
foreach ($File in ($Files | Sort-Object FullName)) {
    if ($File.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked input is not supported: $($File.FullName)" }
    $Records.Add([ordered]@{
        path = $File.FullName.Substring($ProjectRoot.Length + 1).Replace('\', '/')
        bytes = $File.Length
        sha256 = (Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    })
}
if ($VerifyAgainst) {
    $Expected = Get-Content -LiteralPath $VerifyAgainst -Raw | ConvertFrom-Json
    $ExpectedLines = @($Expected.files | ForEach-Object { $_.path + ':' + $_.sha256 })
    $ActualLines = @($Records | ForEach-Object { $_.path + ':' + $_.sha256 })
    $Difference = @(Compare-Object -ReferenceObject $ExpectedLines -DifferenceObject $ActualLines)
    if ($Difference.Count -gt 0) {
        $Difference | Select-Object -First 12 | Format-Table | Out-String | Write-Output
        throw 'Build inputs changed after packaging started. Rebuild in a new output directory before sealing.'
    }
    Write-Output "Build input hashes match ($($Records.Count) files)."
    return
}
$Destination = [IO.Path]::GetFullPath($OutputPath)
if (-not $Destination.StartsWith($ProjectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build input records must be saved inside the project.'
}
[ordered]@{
    schema_version = 1
    captured_utc = [DateTime]::UtcNow.ToString('o')
    map = '/Game/Maps/StanleyParkSeawall'
    configuration = $Configuration
    files = @($Records.ToArray())
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Destination -Encoding utf8
