# Authoring pipeline

These scripts created and inspected the scene. They are not required to play the Windows build.

| Folder | Purpose |
| --- | --- |
| `gis` | Acquire and transform terrain, water, canopy, and source records |
| `routes` | Build route geometry and direction records |
| `blender` | Generate and export editable models and textures |
| `unreal` | Import and assemble game assets |
| `audio` | Generate original ambient audio |
| `qa` | Offline geometry, capture, and timing analysis |
| `release` | Create and verify public ZIP archives |

Start with [build instructions](../docs/building.md) to restore the ready-made assets. The [GIS notes](gis/README.md) describe raw-data regeneration and its dependencies.

Many authoring scripts are named for a specific source or scene revision. They are retained for provenance. Do not run every script in sequence: use the relevant manifest and its named generator. Raw research downloads and old runtime evidence are not included in Git.
