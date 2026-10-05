# Project records

These files record asset identity, source dates, transformations, and limits. Paths inside them are relative to the project root unless a field states otherwise.

Start with:

- `release-v0.5.1.json`: current public download URLs, sizes, and SHA-256 values. Older release manifests remain available.
- `release-assets-v0.5.1.json`: exact editable files restored by the asset helper. The unversioned inventory belongs to v0.4.0.
- `active-assets.json`: current scene authoring entry points.
- `source-distribution.json`: source databases and notices included with the Windows build.
- `world-origin.json`: the shared coordinate origin.
- `blender-modules.json`: the modular Blender source layout.
- `park-details-v0.5.json`: new tree, understory, and picnic placement records.
- `nature-audio.json`: CC0 forest sound source, conversion, and hashes.

Other records describe individual data sources, generated objects, or historical geometry checks. They do not imply that every referenced raw download or inspection image is distributed. See [data and credits](../docs/data-and-credits.md) for source access and licences.
