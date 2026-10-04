param([string]$EngineRoot = $env:UE_ROOT)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $EngineRoot) { throw 'Set UE_ROOT or pass -EngineRoot.' }
New-Item -ItemType Directory -Path (Join-Path $ProjectRoot 'evidence') -Force | Out-Null
$env:DOTNET_CLI_HOME = Join-Path $ProjectRoot 'tmp\dotnet'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
$Project = Join-Path $ProjectRoot 'unreal\StanleyParkSim.uproject'
$Log = Join-Path $ProjectRoot 'evidence\unreal-seawall-editor.log'
$Arguments = '"' + $Project + '" /Game/Maps/StanleyParkSeawall -NoSplash -abslog="' + $Log + '"'
# This opens the separate authoring map. It does not start gameplay.
Start-Process -FilePath (Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe') `
    -ArgumentList $Arguments -WindowStyle Normal -PassThru | Select-Object Id
