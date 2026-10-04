param([string]$EngineRoot = $env:UE_ROOT)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $EngineRoot) { throw 'Set UE_ROOT or pass -EngineRoot.' }
New-Item -ItemType Directory -Path (Join-Path $ProjectRoot 'evidence') -Force | Out-Null
$env:DOTNET_CLI_HOME = Join-Path $ProjectRoot 'tmp\dotnet'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
& (Join-Path $EngineRoot 'Engine\Build\BatchFiles\Build.bat') StanleyParkSimEditor Win64 Development `
    "-Project=$ProjectRoot\unreal\StanleyParkSim.uproject" `
    "-Log=$ProjectRoot\evidence\build-editor.log" -WaitMutex -NoHotReloadFromIDE
if ($LASTEXITCODE -ne 0) { throw "Editor build failed. Read evidence\build-editor.log." }
