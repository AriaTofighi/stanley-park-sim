param([Parameter(Mandatory = $true)][string]$ArchiveDirectory)
$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$ArchiveRoot = [IO.Path]::GetFullPath($ArchiveDirectory)
if (-not $ArchiveRoot.StartsWith($ProjectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The source bundle must be inside the project package directory.'
}
$BundleRoot = Join-Path $ArchiveRoot 'SourceData'
$RegisterPath = Join-Path $ProjectRoot 'manifests\source-distribution.json'
$Register = Get-Content -LiteralPath $RegisterPath -Raw | ConvertFrom-Json
$Copied = [Collections.Generic.List[object]]::new()

function Copy-BundleFile {
    param([string]$Group, [string]$Relative, [string]$ExpectedHash = '')
    if ($Group -notmatch '^[A-Za-z]+$' -or [IO.Path]::IsPathRooted($Relative)) {
        throw "Invalid source bundle path: $Group / $Relative"
    }
    $Source = [IO.Path]::GetFullPath((Join-Path $ProjectRoot $Relative))
    if (-not $Source.StartsWith($ProjectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Source path is outside the project: $Relative"
    }
    if ([IO.Path]::GetExtension($Source) -notin @('.txt', '.md', '.json', '.geojson', '.osm', '.py', '.npz', '.h')) {
        throw "Source file type is not approved for redistribution: $Relative"
    }
    if ($Relative.Replace('\', '/') -in $Register.excluded_research_files) {
        throw "Research-only file must not be distributed: $Relative"
    }
    $GroupRoot = Join-Path $BundleRoot $Group
    $Destination = [IO.Path]::GetFullPath((Join-Path $GroupRoot $Relative))
    if (-not $Destination.StartsWith($GroupRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Source destination is outside its group: $Relative"
    }
    $Hash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ExpectedHash -and $Hash -ne $ExpectedHash.ToLowerInvariant()) {
        throw "Source mesh changed after its manifest was written: $Relative"
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination
    $Copied.Add([ordered]@{ group = $Group; project_path = $Relative.Replace('\', '/'); sha256 = $Hash })
}

# Keep explicit project-relative paths. Never copy a research directory or all
# old mesh files: previous authoring passes can leave unused outputs on disk.
foreach ($Group in $Register.groups) {
    foreach ($Relative in $Group.files) { Copy-BundleFile $Group.id $Relative }
    $MeshManifest = Get-Content -LiteralPath (Join-Path $ProjectRoot $Group.mesh_manifest) -Raw | ConvertFrom-Json
    $CollectionName = if ($Group.mesh_collection) { $Group.mesh_collection } else { 'meshes' }
    $PathProperty = if ($Group.mesh_path_property) { $Group.mesh_path_property } else { 'path' }
    foreach ($Mesh in $MeshManifest.$CollectionName) {
        $Relative = $Mesh.$PathProperty.Replace('\', '/')
        if (-not $Relative.StartsWith($Group.mesh_root, [StringComparison]::Ordinal) -or
            [IO.Path]::GetExtension($Relative) -ne '.npz') {
            throw "Mesh is outside the approved source folder: $Relative"
        }
        Copy-BundleFile $Group.id $Relative $Mesh.sha256
    }
}
Copy-Item -LiteralPath (Join-Path $ProjectRoot $Register.notice) -Destination (Join-Path $BundleRoot 'OSM-DATA-LICENCE.txt')
Copy-Item -LiteralPath $RegisterPath -Destination (Join-Path $BundleRoot 'source-distribution.json')
$Index = [ordered]@{
    schema_version = 1
    generated_utc = [DateTime]::UtcNow.ToString('o')
    licence_url = $Register.licence_url
    register_sha256 = (Get-FileHash -LiteralPath $RegisterPath -Algorithm SHA256).Hash.ToLowerInvariant()
    files = @($Copied.ToArray())
}
$Index | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $BundleRoot 'source-bundle-index.json') -Encoding utf8
