# Authoring pipeline

These scripts created and inspected the scene. They are not required to play the Windows build.

For the current editor revision, `gis/build_minimap.py` generates the overview and coordinate bounds. Apply `unreal/refine_ground_and_minimap.py` after the base park detail pass, then apply `unreal/apply_sunny_weather.py` last. These authoring commands save assets and the Seawall map without running gameplay. The older lighting/detail passes can restore their earlier ground or cloudy sky, so do not rerun them after these refinements without reapplying the current passes.

| Folder | Purpose |
| --- | --- |
| `gis` | Acquire and transform terrain, water, canopy, and source records |
| `routes` | Build route geometry and direction records |
| `blender` | Generate and export editable models and textures |
| `unreal` | Import and assemble game assets |
| `audio` | Generate the original bell and prepare licensed nature audio |
| `qa` | Offline geometry, capture, and timing analysis |
| `release` | Create and verify public ZIP archives |

Start with [build instructions](../docs/building.md) to restore the ready-made assets. The [GIS notes](gis/README.md) describe raw-data regeneration and its dependencies.

Many authoring scripts are named for a specific source or scene revision. They are retained for provenance. Do not run every script in sequence: use the relevant manifest and its named generator. Raw research downloads and old runtime evidence are not included in Git.

For v0.5 scenery, use `blender/build_park_details.py`, then `unreal/apply_park_details.py`. The new library is separate from the original modules. Use `audio/prepare_nature_audio.py` to prepare the recorded CC0 loop before the Unreal import. The Unreal script runs as a Python authoring commandlet and never starts gameplay.
