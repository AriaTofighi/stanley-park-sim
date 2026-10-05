param([string]$ArchivePath, [string]$Version = '0.5.1')
$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Use a semantic release version.' }
$Manifest = Get-Content -LiteralPath (Join-Path $ProjectRoot "manifests/release-v$Version.json") -Raw | ConvertFrom-Json
$Asset = @($Manifest.assets | Where-Object { $_.name -eq "StanleyPark-Assets-v$Version.zip" })
if ($Asset.Count -ne 1) { throw 'Expected one editable asset archive in the release manifest.' }
$Asset = $Asset[0]
if (-not $ArchivePath) {
    $CachePath = Join-Path $ProjectRoot 'cache/downloads'
    New-Item -ItemType Directory -Path $CachePath -Force | Out-Null
    $ArchivePath = Join-Path $CachePath $Asset.name
    if (-not (Test-Path -LiteralPath $ArchivePath)) {
        $Partial = $ArchivePath + '.partial'
        Invoke-WebRequest -Uri $Asset.url -OutFile $Partial
        Move-Item -LiteralPath $Partial -Destination $ArchivePath
    }
}
$ArchivePath = (Resolve-Path -LiteralPath $ArchivePath).Path
if ((Get-Item -LiteralPath $ArchivePath).Length -ne $Asset.bytes -or
    (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Asset.sha256) {
    throw 'The asset archive does not match the published checksum.'
}
$InventoryPath = if ($Version -eq '0.4.0') { 'manifests/release-assets.json' } else { "manifests/release-assets-v$Version.json" }
if ($Manifest.asset_inventory -and $Manifest.asset_inventory -ne $InventoryPath) { throw 'Unexpected asset inventory path.' }
$InventoryFullPath = Join-Path $ProjectRoot $InventoryPath
if ($Manifest.asset_inventory_sha256 -and
    (Get-FileHash -LiteralPath $InventoryFullPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Manifest.asset_inventory_sha256) {
    throw 'The asset inventory does not match the release checksum.'
}
$Inventory = Get-Content -LiteralPath $InventoryFullPath -Raw | ConvertFrom-Json
$ByPath = [Collections.Generic.Dictionary[string,object]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($Entry in $Inventory.files) { $ByPath.Add($Entry.path, $Entry) }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$Zip = [IO.Compression.ZipFile]::OpenRead($ArchivePath)
try {
    if ($Zip.Entries.Count -ne $ByPath.Count) { throw 'Unexpected asset count in ZIP.' }
    $Seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    # Validate every destination and existing file before writing any asset.
    foreach ($Entry in $Zip.Entries) {
        $Name = $Entry.FullName.Replace('\','/')
        if (-not $Seen.Add($Name) -or -not $ByPath.ContainsKey($Name) -or $Name -notmatch '^(blender|exports|data|unreal/Content)/') {
            throw "Unexpected ZIP entry: $Name"
        }
        $Destination = [IO.Path]::GetFullPath((Join-Path $ProjectRoot $Name))
        if (-not $Destination.StartsWith($ProjectRoot + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe extraction path.' }
        if ($Entry.Length -ne $ByPath[$Name].bytes) { throw "Unexpected asset size: $Name" }
        $Parent = Split-Path -Parent $Destination
        while ($Parent.Length -ge $ProjectRoot.Length) {
            if ((Test-Path -LiteralPath $Parent) -and ((Get-Item -LiteralPath $Parent -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw "Extraction path contains a link: $Parent"
            }
            if ($Parent -eq $ProjectRoot) { break }
            $Parent = Split-Path -Parent $Parent
        }
        if (Test-Path -LiteralPath $Destination) {
            $Item = Get-Item -LiteralPath $Destination -Force
            if ($Item.PSIsContainer -or ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
                (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ByPath[$Name].sha256) {
                throw "Keep the existing changed asset: $Name. Use a separate clean checkout to restore this version."
            }
        }
    }
    foreach ($Entry in $Zip.Entries) {
        $Name = $Entry.FullName.Replace('\','/')
        $Destination = Join-Path $ProjectRoot $Name
        if (Test-Path -LiteralPath $Destination) { continue }
        New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
        [IO.Compression.ZipFileExtensions]::ExtractToFile($Entry,$Destination,$false)
        if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ByPath[$Name].sha256) {
            throw "Extracted asset hash mismatch: $Name"
        }
    }
}
finally { $Zip.Dispose() }
Write-Output "Verified and restored $($ByPath.Count) asset files. Open unreal/StanleyParkSim.uproject to continue."
