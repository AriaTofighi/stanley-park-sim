# Build and edit

## Requirements

- Windows 64-bit.
- Unreal Engine 5.8.3 and its supported Visual Studio C++ toolchain.
- PowerShell 7 for the helper scripts.
- Blender 5.2 only if you want to edit the Blender sources.
- Python 3.12 for the data-processing pipeline. Its dependencies are listed in `pipeline/gis/requirements.lock.txt`.

The Windows download runs without the development tools above.

## Restore large assets

Clone this repository, then run this from its root:

```powershell
.\scripts\restore-assets.ps1
```

The script downloads the editable asset archive from the v0.5.1 release, verifies its SHA-256 value against `manifests/release-v0.5.1.json`, and extracts it into the project. It refuses to overwrite a different existing file. You can also download the archive yourself and pass its path with `-ArchivePath`.

The archive restores `unreal/Content`, `blender`, `exports`, and the included data inputs. The Git repository and this archive together form the editable project. They do not include Unreal Engine source, an engine installation, or the complete raw LiDAR/research download cache.

## Open or compile

Open `unreal/StanleyParkSim.uproject`. The startup map is `/Game/Maps/StanleyParkSeawall`.

To compile the editor target:

```powershell
.\scripts\build-editor.ps1 -EngineRoot 'C:\Program Files\Epic Games\UE_5.8'
```

The optional MCP authoring plugins are disabled by default. They are not required to compile or run the simulation.

For Blender, open `blender/StanleyPark_Assembly.blend`. Smaller source files are under `blender/modules`. The explorer and animated bicycle also have separate `.blend` files.

## Package Windows

```powershell
.\scripts\package-windows.ps1 `
  -EngineRoot 'C:\Program Files\Epic Games\UE_5.8' `
  -OutputDirectory 'builds\Windows-custom'
```

The default configuration is Shipping. Use `-Configuration Development` for a diagnostic build. Each package must use a new output directory. Packaging does not run the application. It includes the registered source database offer and attribution notices.

To make release ZIPs with Python 3.12:

```powershell
.\scripts\package-release.ps1 -BuildDirectory 'builds\Windows-custom'
```

The archive step checks the explicit asset list, scans text files for private-data patterns, and verifies ZIP checksums. It does not run the game. Use a new output directory if archives already exist. Update the release asset manifest deliberately when you change an editable asset.

## Folder layout

| Folder | Purpose |
| --- | --- |
| `unreal/Source` | Simulation and interface C++ code |
| `unreal/Config` | Shared project configuration |
| `unreal/Content` | Maps and game assets, restored from the release |
| `pipeline` | GIS, route, Blender, audio, import, and diagnostic scripts |
| `manifests` | Source provenance and asset records |
| `scripts` | Build, packaging, launch, and asset restoration helpers |
| `docs` | Player, contributor, release, and legal information |
| `blender`, `exports`, `data` | Large editable inputs, restored from the release |

Generated builds, logs, caches, machine settings, and local research archives are ignored by Git. Raw-data regeneration needs the dated source acquisitions described by the pipeline and manifests; downloading the editable archive is enough to open the included Unreal scene.
