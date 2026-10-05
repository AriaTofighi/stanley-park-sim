param(
    [Parameter(Mandatory=$true)][string]$BuildDirectory,
    [string]$OutputDirectory = 'dist/v0.5.1',
    [string]$Version = '0.5.1',
    [string]$Python = 'python',
    [string]$AssetManifest = 'manifests/release-assets-v0.5.1.json'
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
& $Python (Join-Path $ProjectRoot 'pipeline/release/build_archives.py') `
    --build $BuildDirectory --output $OutputDirectory --version $Version --asset-manifest $AssetManifest
if ($LASTEXITCODE -ne 0) { throw 'Release archive preparation failed.' }
