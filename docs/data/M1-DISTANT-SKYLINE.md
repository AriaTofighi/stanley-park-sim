> Historical source note from the development baseline. See [current release notes](../release-notes.md) for the public release. File paths below are relative to the project root. Raw inspection media remain in the local archive.

# M1 distant skyline package

This package supplies coarse downtown and West End silhouettes for M1-F12. It contains 4,056 authored parts in 135 mesh objects with 134,271 triangles. It does not complete the whole landmark inventory. Blender and runtime view acceptance remain false.

## Sources and dates

The horizontal source is the bounded OpenStreetMap snapshot acquired on 2026-09-27. The four XML files and their hashes are in `manifests/skyline-source-acquisition.json`. The bounds are longitude -123.150 to -123.097 and latitude 49.274 to 49.299. Each output part retains its OSM ID, edit time, tags and URL. Volunteered map geometry is not a survey.

`manifests/skyline-reference-sources.json` records the additional primary references, dates, uses and rights. The main references are the [Ledcor Stack project page](https://www.ledcor.com/our-projects/project-gallery/project-gallery-building/commercial/the-stack-office-tower), the [Alberni architect page](https://kkaa.co.jp/en/project/alberni/), the [2016 City Alberni design report](https://council.vancouver.ca/20160920/documents/p9.pdf), [Birdair Canada Place](https://www.birdair.com/birdair-portfolio/canada-place/), and the [SEABC 2017 structures guide](https://seabc.ca/wordpress/files/notable_structures/Vancouver_Notable_Structures_IABSE_SEABC_2017.pdf). Contractor and architect photos were inspected in the browser. The Canada Place and Harbour Centre pages of the SEABC guide were rendered and inspected locally. Reference photos are not textures.

The Stack developer PDF was unavailable. No dimensions were taken from that PDF. The City Alberni report was available as web text, but its local download failed; no local drawing inspection is claimed. The design height is not an as-built survey.

City 2009 building data is used only for conservative height scalars where current and historic polygons correspond. Coverage must be at least 80%, and the area ratio must be between 0.55 and 1.8. Historic footprints are not imported as geometry. Known new towers and features with post-2009 dates do not use these historic heights. A matched scalar can still be stale; this is recorded for each part.

## Geometry and editable estimates

All positions use EPSG:3157 and the immutable origin E489600, N5461100, H0. Blender X is east, Y is north and Z is up, in metres. Every building part uses the common terrain base of its current OSM parent. The base is the median of valid current near/far CGVD2013 terrain samples. It is a terrain estimate, not a surveyed finished-floor level. The manifest retains the terrain source and sample range.

The generator selects the smallest current building footprint that contains at least 80% of each part. A parent with child parts generates only its residual low podium area. It never fills all child outlines to the tallest child height. There are 392 residual podium fragments at or below 14 m, and 242 parent outlines have no remaining area and are suppressed. This preserves Paradox's rotated levels, Shangri-La's steps and Harbour Centre's disks.

| Form | Current implementation | Remaining limit |
| --- | --- | --- |
| The Stack | Four boxes; 161 m overall from contractor; inside current OSM envelope | Box heights, rotations and widths are visual estimates |
| Alberni by Kengo Kuma | 132.35 m City design height; 28 rings with two curved cuts | Curve depth, orientation and opposite-face shape are M1 estimates |
| Paradox | Current OSM rotated stacked parts up to 188 m | No facade detail; tagged dimensions are not surveyed |
| Shangri-La | Current stepped OSM parts up to 201 m | Roof simplification and source accuracy remain open |
| Butterfly | Current lobe polygons; one tagged 178.6 m lobe | Four other 57-floor lobes use an explicit transfer of that sibling height |
| Harbour Centre | Current shaft and stepped disks; valid upper cap | Contradictory 160/161 m interval excluded; separate 0.8 m diameter estimated mast joins valid 156 and 167 m source endpoints |
| Canada Place | Five current fabric polygons with curved membranes | Peak/sag form is an authored visual approximation, not structural form-finding |
| Landmark on Robson | Current two-tower polygons and levels | Floor spacing is estimated; OSM itself labels part of the footprint estimated |

Harbour Centre has multiple overlapping parent records. Its tower parts belong to the smaller unnamed 1977 office parent `way_139571552_0`, while the named low building and SFU use other parents. The tower remains an individual significant group. Parts retain their actual source parent; the preview combines these groups for inspection.

Canada Place roof elevations use matching City 2009 top values and a 24.8 m low-roof reference. The City metadata calls elevations geodetic but does not state the vertical datum. The project records CGVD28 as an assumption, then applies the regional CGVD28-to-CGVD2013 geoid correction, approximately +0.144 m. Absolute roof elevations are not treated as survey control. Each sail reaches its recorded source-derived high point. The shape between points is estimated.

`manifests/skyline-authoring-settings.json` contains all coarse form settings, floor spacing, podium cap and unresolved 9 m fallback. Of the authored parts, 958 use tagged height intervals, 928 use matched historic height differences, 1,261 use floor counts and estimated spacing, and 502 minor buildings use the explicit unresolved 9 m estimate. The remaining parts are residual podia and the named custom forms. Do not describe the full skyline as source-accurate or accepted.

Ten source fragments are excluded. Six have zero or contradictory vertical intervals; four have pinched solid topology after source clipping. Their exact IDs, reasons and source tags are in the output manifest and numerical report. An excluded fragment does not imply that every other part of its building is absent. This is particularly relevant to the Vancouver House parent residual. No invalid source interval is silently reversed.

## Reproduction and Blender handoff

1. Run `pipeline/gis/build_skyline_blockouts.py` with the GIS virtual environment. It reads the source register and writes `data/derived/skyline/*.npz` and `manifests/skyline-blockouts.json`.
2. Run `pipeline/gis/inspect_skyline_blockouts.py` for numerical and static geometry inspection. It does not start the application.
3. Through the live Blender MCP connection, execute `pipeline/blender/build_skyline_blockouts.py`. It verifies hashes before replacing only its owned objects in `SP_10_DistantSkyline`. It saves the editable `blender/StanleyPark_Blockout.blend`.
4. Inspect the live Blender scene, then use the shared export/import pipeline. All skyline objects have `collision=none`. The five sail materials need two-sided rendering in Unreal as well as Blender. Check this explicitly after import.

Generic masses are grouped by 512 m cell and material. Significant forms keep individual part objects. There are four neutral materials and no copied photos, logos, windows or facade textures. Existing shared scripts were not changed for skyline orchestration. The source-stage owner is `skyline_blockouts_v1`.

## Checks and retained evidence

`evidence/skyline-numerical-inspection.json` records source and mesh hashes, finite vertices, valid indices, unique part ranges, 2,694 shared parent bases, podium limits, the four Stack boxes, five sail peaks and the triangle count. Solid parts have closed, positive-volume geometry. Sail surfaces have intentional open perimeter edges. The five sail peak errors are zero to the numerical precision used here. All 4,208 source records are represented by produced parts, explicit exclusions or suppressed parent outlines.

The static previews `evidence/skyline-landmark-shapes.png` and `evidence/skyline-overview.png` were opened and inspected. They show neutral geometry without terrain, water, vegetation, haze or runtime lighting. They are not Blender or application screenshots. The initial inspection exposed a Harbour Centre preview/group selection error; the tower's true source parent was added and the inspection was repeated.

Before F12 acceptance, inspect Coal Harbour/Deadman's Island, Brockton, and the English Bay side from actual route cameras. Check tower order, relative height, shoreline placement, view occlusion, Canada Place roof shape and both sides of its membranes. Check that the skyline does not cast inappropriate distant shadows or add collision. Record live Blender and engine images and compare their screen silhouettes with references. The owner of the main scene controls these checks. A successful mesh build alone does not close this gate.

## Distribution

Current OSM-derived geometry and the source database require OpenStreetMap contributor attribution and the ODbL source offer used by this project. City data requires the Open Government Licence - Vancouver notice. NRCan terrain and geoid data keep the project's Canadian open-data notices. Include the transformation scripts and manifests in the source bundle as applicable.

Do not include `data/raw/skyline/seabc-structures-2017.pdf` or the two rendered `evidence/skyline-*-reference.png` pages in the distributed game or source bundle. They are retained research references under third-party copyright. No remote photograph is included in the generated assets.
