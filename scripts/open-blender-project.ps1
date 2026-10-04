param(
    [ValidateSet('Assembly','Explorer','Terrain','Routes','Sites','Shore','Trees','Forest','Crowns','Retired')]
    [string]$Part = 'Assembly',
    [string]$BlenderPath = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$files = @{
    Assembly='blender\StanleyPark_Assembly.blend'
    Explorer='blender\Explorer.blend'
    Terrain='blender\modules\Terrain_Water.blend'
    Routes='blender\modules\Routes_Ground.blend'
    Sites='blender\modules\Sites_Details.blend'
    Shore='blender\modules\Shore_Edges.blend'
    Trees='blender\modules\SeawallTrees_0551a03260b4.blend'
    Forest='blender\modules\M3Forest_659dc73e2ffc.blend'
    Crowns='blender\modules\M3CrownRepair_a0f7b40568c5.blend'
    Retired='blender\modules\Retired_Reference.blend'
}
$path = Join-Path $projectRoot $files[$Part]
if (-not (Test-Path -LiteralPath $path)) { throw "Missing Blender source: $path" }
# The user runs this launcher to open an interactive editor.
Start-Process -FilePath $BlenderPath -ArgumentList ('"' + $path + '"') -WindowStyle Normal
