param(
    [Parameter(Mandatory=$true)][string]$BuildDirectory,
    [string]$OutputDirectory = 'dist/v0.4.0',
    [string]$Version = '0.4.0',
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
& $Python (Join-Path $ProjectRoot 'pipeline/release/build_archives.py') `
    --build $BuildDirectory --output $OutputDirectory --version $Version
if ($LASTEXITCODE -ne 0) { throw 'Release archive preparation failed.' }
