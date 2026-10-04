param(
    [string]$EngineRoot = $env:UE_ROOT,
    [string]$OutputDirectory = 'builds\Windows-Public-v0.4.0',
    [ValidateSet('Development','Shipping')][string]$Configuration = 'Shipping'
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if (-not $EngineRoot -or -not (Test-Path -LiteralPath (Join-Path $EngineRoot 'Engine\Build\BatchFiles\RunUAT.bat'))) {
    throw 'Set UE_ROOT or pass -EngineRoot with the Unreal Engine installation directory.'
}
$ArchiveDirectory = [IO.Path]::GetFullPath((Join-Path $ProjectRoot $OutputDirectory))
if (-not $ArchiveDirectory.StartsWith($ProjectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The package directory must be inside the project.'
}
if (Test-Path -LiteralPath $ArchiveDirectory) {
    throw 'Use a new package directory. Existing builds and their evidence must remain unchanged.'
}
$MapPath = '/Game/Maps/StanleyParkSeawall'
$PackagingConfig = Get-Content -LiteralPath (Join-Path $ProjectRoot 'unreal\Config\DefaultGame.ini') -Raw
foreach ($AssetDirectory in @('/Game/StanleyPark/Seawall/Birds', '/Game/StanleyPark/Explorer', '/Game/StanleyPark/Kit')) {
    if (-not $PackagingConfig.Contains('+DirectoriesToAlwaysCook=(Path="' + $AssetDirectory + '")')) {
        throw "Missing runtime asset cook rule: $AssetDirectory"
    }
}
New-Item -ItemType Directory -Path $ArchiveDirectory -Force | Out-Null
# Capture the exact build inputs before UAT. The final seal refuses changed inputs.
& (Join-Path $PSScriptRoot 'record-build-inputs.ps1') -OutputPath (Join-Path $ArchiveDirectory 'build-inputs.json') -Configuration $Configuration
$env:DOTNET_CLI_HOME = Join-Path $ProjectRoot 'tmp\dotnet'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
# Build and cook only. This command does not launch or test the application.
& (Join-Path $EngineRoot 'Engine\Build\BatchFiles\RunUAT.bat') BuildCookRun `
    "-project=$ProjectRoot\unreal\StanleyParkSim.uproject" -noP4 -platform=Win64 `
    "-clientconfig=$Configuration" -build -cook -stage -pak -compressed -archive -prereqs -nodebuginfo -unattended `
    "-map=$MapPath" `
    "-archivedirectory=$ArchiveDirectory" -utf8output
if ($LASTEXITCODE -ne 0) { throw 'Windows package step failed.' }
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs') -Destination (Join-Path $ArchiveDirectory 'docs') -Recurse
foreach ($Document in @('DATA-ATTRIBUTION.txt', 'SEAWALL-CREDITS.txt', 'PLAYER-TERMS.txt')) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot ('docs\legal\' + $Document)) -Destination $ArchiveDirectory
}
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'LICENSE.md') -Destination $ArchiveDirectory
@'
Stanley Park Seawall

Extract the complete archive, then open StanleyParkSim.exe.
Keep the Engine, StanleyParkSim, and SourceData folders with it.

WASD moves; Shift runs; Space jumps; Tab switches travel mode.
On the bicycle: W pedals, S brakes, A/D steers, F1 opens settings.
Esc pauses. See docs/player-guide.md for all controls.

Read PLAYER-TERMS.txt and the included attribution notices before use.
This preview uses historical data and is not a navigation aid.
'@ | Set-Content -LiteralPath (Join-Path $ArchiveDirectory 'START-HERE.txt') -Encoding utf8
# Include the registered, machine-readable database offer with the game.
& (Join-Path $PSScriptRoot 'copy-source-data.ps1') -ArchiveDirectory $ArchiveDirectory
Write-Output "Created $Configuration package: $ArchiveDirectory. No application test was run."
