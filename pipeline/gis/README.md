# Measured GIS inputs

This pipeline produces inputs for the park blockout. It does not create Blender or engine scenes. No application test runs here.

## Data contract

The immutable origin is in `manifests/world-origin.json`:

- Horizontal grid: EPSG:3157, NAD83(CSRS) / UTM zone 10N.
- E0 = 489600 m, N0 = 5461100 m, H0 = 0 m.
- Blender/local axes: X east, Y north, Z up. One unit is one metre.
- Current terrain heights: CGVD2013. H0 is a coordinate offset. It does not set water height.

The origin comes from the downloaded City park polygon centroid, rounded to a 100 m grid. The City 2022 LiDAR uses a regional realization and CGVD28GVRD heights. Do not combine those heights with these NRCan products without a documented conversion.

| Product | Contract |
|---|---|
| `data/derived/terrain_park.npz` | 2 m grid. `x` and `y` ascend. `z[row_y,col_x]` is in metres. `valid` marks measured/interpolated source coverage. Missing values are NaN. `inside_park` marks the City boundary. |
| `data/derived/terrain_park.obj` | 8 m blockout mesh, in local metres. No invented vertices at source holes. About 174,000 vertices. |
| `data/derived/terrain_park_utm.tif` | Same 2 m height grid in EPSG:3157. North-up raster; nodata −32767. |
| `data/derived/terrain_surroundings.npz` | 80 m grid over 52 × 60 km. Same array and coordinate contract. |
| `data/derived/terrain_surroundings.obj` | Coarse measured surrounding terrain. The park crop interior is omitted. An overlap remains for an authored transition. |
| `data/derived/park_boundary.geojson` | City park polygon in **local metres**, declared in `coordinate_reference`. This is a project interchange file, not RFC 7946 geographic coordinates. |
| `data/derived/park_boundary_wgs84.geojson` | WGS84 boundary for geographic tools. |
| `data/derived/park_boundary_utm.geojson` | EPSG:3157 projected boundary. |
| `data/derived/shoreline.geojson` | Clipped City 2002 approximate shoreline, in local metres. Its tidal meaning is unknown. |

Route height query example:

```python
import numpy as np
from scipy.interpolate import RegularGridInterpolator
grid = np.load("data/derived/terrain_park.npz")
sample = RegularGridInterpolator((grid["y"], grid["x"]), grid["z"], bounds_error=False)
height = sample([[local_north, local_east]])[0]
```

Do not use the coarse blockout mesh as final bicycle contact geometry. Narrow paths, curbs, vertical cliffs, and under-canopy cross sections need separate checks and models.

## Sources and fallback

The City catalogue supplied the park boundary, shoreline, metadata, and eleven 2022 LiDAR tile references. The first direct request returned HTTP 403. All eleven original ZIP files were later downloaded and ingested. Their hashes and classification records are retained. They supply the current near terrain, route-surface review, canopy heights and roof masses. About 93.82% of the park grid has a 2022 replacement. The remaining historic coverage is labelled.

The measured near-terrain fallback is NRCan's public `VILLE_VANCOUVER-VILLE_VANCOUVER-1m` DTM. Its source timestamp is 19 February 2013. It is a LiDAR-derived height product in EPSG:3979 with CGVD2013 heights. The pipeline reads bounded byte ranges, clips the park crop, reduces it to 2 m, then reprojects it. This is a historic terrain baseline. It does not prove the park's September 2026 condition.

The far terrain is NRCan MRDEM-30. It is reduced to 80 m. Source dates vary. Both STAC collections declare OGL-Canada-2.0. City data uses OGL-Vancouver. The source and product manifests contain URLs, hashes, licence snapshots, source dates, processing details, limitations, and credits. The reviewed MRDEM/Copernicus notices are retained in `docs/legal/DATA-ATTRIBUTION.txt`.

Python verifies TLS. `remote_raster.py` supplies bounded HTTP ranges through Rasterio's Python opener. This avoids the local GDAL/Schannel credential failure. It does not disable security checks. The initial 6 GB download allowance applied to the earlier raster investigation. The eleven selected LiDAR archives require about 10.74 GB, plus derived arrays and working space. Preserve the original downloads and inspect free disk space before adding large sources or caches.

## Reproduce

Use the separate `pipeline/gis/.venv`; no Blender MCP dependency changes are required. Install the exact packages in `requirements.lock.txt` with Python 3.12. Run these commands from the project root:

```powershell
& pipeline/gis/.venv/Scripts/python.exe pipeline/gis/acquire_sources.py
& pipeline/gis/.venv/Scripts/python.exe pipeline/gis/acquire_nrcan.py
& pipeline/gis/.venv/Scripts/python.exe pipeline/gis/build_terrain.py
& pipeline/gis/.venv/Scripts/python.exe pipeline/gis/validate_data.py
```

Cached source files are immutable. A changed remote ETag requires a new range-cache directory. Do not move the origin after assets use it. The scripts refuse a changed horizontal origin.

## Validation result and limits

`manifests/geospatial-validation.json` records the numerical result. Arrays, validity masks, grid spacing, boundary validity, and twenty coordinate round trips passed. The park polygon has complete valid terrain coverage. Some shore/intertidal source heights are below zero; retain them.

Coordinate round-trip precision is not survey accuracy. Independent horizontal and height controls, current route cross sections, water levels, cliff shape, and rendered alignment remain unchecked. A mesh export is not a visual or interactive acceptance result.

## Shared route surface and regional ocean mask

After the route data is available, run these additional stages:

```powershell
& pipeline/gis/.venv/Scripts/python.exe pipeline/gis/acquire_water_references.py
& pipeline/gis/.venv/Scripts/python.exe pipeline/gis/build_ocean_mask.py
& pipeline/gis/.venv/Scripts/python.exe pipeline/gis/build_surface_meshes.py
```

The surface stage retains 2 m terrain samples near routes and uses 8 m samples elsewhere. The main circuit now has separate pavement and collision, with terrain cut at its boundary. Interior route review strips still have no collision. Blender and Unreal use the same exported vertices. See `docs/PAVED-SURFACE-IMPLEMENTATION.md` for the current rebuild order. Transfer checks do not establish the real path cross section.

The ocean stage uses BC Freshwater Atlas Coastlines under OGL-BC. It masks the distant terrain by coast polygons instead of an elevation threshold. All source URLs and hashes are in `manifests/water-references.json`. The FWA lake outlines are retained for later measured lake models. The Access Only TRIM EBM Ocean layer is excluded. Distribute the applicable notices in `docs/legal/DATA-ATTRIBUTION.txt` with local review builds.

See `docs/SURFACE-AND-RIDE-CHECKS.md` for the mesh, collision, and short ride evidence. The 2,000 collision control points check transfer into Unreal. They are not independent survey controls.

## Path source review at 1 m

```powershell
& pipeline/gis/.venv/Scripts/python.exe pipeline/gis/build_corridor_reference.py
& pipeline/gis/.venv/Scripts/python.exe pipeline/routes/review_corridor.py
./scripts/focus-corridor.ps1 -Issue CR_05880
```

The first command creates `terrain_corridor_reference.npz` and its GeoTIFF without a mesh. It reuses the immutable source range cache and does not reduce the 1 m source before reprojection. It does not replace the runtime terrain. The second command samples the source circuit at intervals no greater than 1 m, compares the two DTM grids, and writes a review queue, profiles, a map, and fixed editor viewpoints. The 18% grade and 12% cross-slope thresholds are investigation triggers, not real-world design or acceptance standards. The 3 m cross-section probe is not a surveyed path width. Both grids derive from the same historic source and are correlated.

The initial review found 34 areas. No missing samples occurred along the circuit or its probe offsets. The highest-priority area was visually inspected in both open editors. The current scene confirms the need for separate, measured path geometry at the cliff. No correction is accepted by this source analysis. The exact walk-bike boundaries remain separate tasks.
