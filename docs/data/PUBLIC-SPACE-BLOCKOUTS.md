> Historical source note from the development baseline. See [current release notes](../release-notes.md) for the public release. File paths below are relative to the project root. Raw inspection media remain in the local archive.

# M1 public-space source package

The entry point is `manifests/public-space-blockouts.json`. It supplies 67 source components for terrain authoring: 48 surface patches, 13 boundaries for review, and 6 railway reference lines. It does not produce meshes or change terrain. The M1 groups are not complete from this package alone.

| M1 group | Components | Supplied form |
| --- | ---: | --- |
| F03 | 6 | Four Brockton playing fields, the Totem precinct boundary, and the small concrete waterfront court north of it |
| F05 | 3 | Water-park pad, playground sand area, and the approach/crossing boundary |
| F07 | 4 | Nature House plaza, Lost Lagoon outer edge, north and west wetland boundaries |
| F08 | 31 | Ceperley field, meadow, wetland, playground and basketball space; two bowling greens; 22 tennis playing rectangles; pitch-and-putt site boundary |
| F09 | 17 | Air Force, Greig and Rose Garden boundaries; eleven small Pavilion garden beds; Malkin Bowl site boundary |
| F10 | 6 | Miniature railway reference lines, including separate bridge and tunnel segments |

## Sources and limits

The original selected OSM geometries are saved in `data/derived/public-spaces/osm-source-polygons-wgs84.geojson`. The authoring layer is `public-space-blockouts-local.geojson` in the same folder. Its coordinates use local metres: EPSG:3157 minus E489600, N5461100. No elevation is assigned. Source coordinates are unchanged. Each component records its way ID, node IDs, tags, edit time, URL, source hash and use restrictions. An OSM edit date is not a survey or image capture date.

The City park map, revision May 19, 2026, supplies the named-area context. Its artwork is not part of the package. The City orthophoto was captured June 6–July 1, 2022. It supplies the visual source check, not a September 2026 condition claim. The OSM data uses ODbL 1.0 with `© OpenStreetMap contributors` attribution. Keep the OSM source and derived database separate and retain this attribution in the project distribution. The saved source inventory contains exact URLs and hashes.

All 67 geometries are finite and valid. Four overlay images were opened and inspected: `evidence/public-spaces/public-spaces-brockton-review.png`, `public-spaces-central-review.png`, `public-spaces-south-review.png`, and `named-lumberman-wide-review.png`. These are source-image checks, not Blender or engine checks. They show all component IDs, but some sites are partly outside a panel or hidden by trees. They do not establish survey accuracy.

The Brockton field outlines match the visible playing areas at this scale. The cricket and rugby source boundaries do not supply every track, diamond, marking, seat or fence. The Totem precinct contains lawn, planting, roof and visitor paving. Do not use uniform concrete in that entire boundary. Individual pole positions and forms remain open work. The small north waterfront court is distinct from the main visitor court.

The water-park pad and playground fit the visible ground spaces. The OSM approach polygon also crosses Stanley Park Drive. It is therefore a boundary for review only. Split it at the road and the other paths before surface authoring. The source `bicycle=dismount` tag does not establish the whole restriction area.

The Nature House plaza is above the building. Its outline must not be draped onto the lower ground beside the lagoon. Inspect its level with the building and road. The Lost Lagoon component contains only the outer member of the water relation. Use it to compare the shore; it must not replace the existing water mesh or erase islands.

The official map places Biofiltration Pond near the north lagoon/causeway corner. The north wetland is in that area, but its boundary is not a basin survey. The separate Ceperley wetland is southwest of the lagoon and is not the mapped biofiltration pond. The source Ceperley north meadow overlaps this wetland by **100.506 m²**. This overlap remains in the saved source. Remove it from the grass authoring output with the component exclusion in the manifest.

Tennis polygons are playing rectangles, not complete paved aprons. Garden and golf envelopes contain paths and trees. Malkin Bowl contains the stage and seating as well as open ground. These boundaries must not become uniform filled surfaces or remove trees. The Air Force Garden and parts of the railway are hidden by canopy in the image. Bridge and tunnel rail segments cannot use a ground drape.

## Integration contract

1. Use `display_mode=surface_patch` only for the 48 candidate surface patches. Review flags can withhold a patch, such as the Nature House level. Keep the 13 boundary and 6 line components as authoring references.
2. Clip patches to the final terrain triangles after the pavement and underpass changes. Subtract roads, bicycle and walking pavement, buildings, independent water, and component-specific wetland exclusions. Preserve terrain elevation and trees. Use a small surface lift and existing terrain contact; do not add collision from these source footprints.
3. Name the generated objects with each component's `expected_object_name`. Keep the source component ID and hash on the object or export manifest. Use the same base material scale and roughness conventions as the surrounding terrain.
4. Keep numerical evidence for finite geometry, exclusions, triangle counts, terrain contact and road/path overlap. In Blender, inspect the blockout from above and from the route. Check ground contact and each mixed site. Engine viewing and ride checks remain root work.

Rebuild this package with `pipeline/gis/build_public_space_blockouts.py`, then `pipeline/gis/plot_public_space_review.py`. The scripts do not launch an application. The geometry check is at `evidence/public-spaces/numerical-check.json`.

## Generated terrain patches

`pipeline/gis/build_public_space_meshes.py` now creates the separate mesh package at `data/derived/public-spaces/public-space-meshes.json`. It contains **50 meshes, 47 source components and 6,628 triangles**. Each triangle is clipped to one actual v15 terrain triangle and uses that plane plus 0.02 m. The maximum numerical plane-offset error is 1.08e-13 m. There is no remaining overlap with the saved pavement, branch/road overlays, walking overlays, lake water, underpass openings, building footprints or wetland masks. Coverage of each allowed patch is complete to numerical precision. The check is `evidence/public-spaces/mesh-checks.json`.

The Nature House plaza is withheld because its upper level requires a structure. It joins the 13 mixed-site boundaries and six rail lines as 20 reference components. These are not completed ground surfaces. The Blender stage `pipeline/blender/build_public_space_blockouts.py` creates the allowed meshes in `SP_08_PublicSpaces` and keeps withheld source boundaries as hidden curves in `SP_REF_PublicSpaceBoundaries`. The curves have source XY and unknown Z. They are not exported as surface meshes. The stage has not been run by this subtask; root operates the live Blender scene.

The four `*-mesh-review.png` images in `evidence/public-spaces/` show the actual saved triangles on the same source imagery. All four were opened and inspected. The Ceperley wetland cut is preserved. Mixed garden, golf, Totem and Malkin envelopes remain unfilled. The source building mask leaves several small holes in Ceperley Field; these may be temporary structures present in the survey. They remain explicit source exclusions and add no collision. A final Blender and engine view must check the visual effect. No application test was run by this subtask.

Still open: most Totem visitor paving and poles; water-park equipment; Nature House levels; fountain structure and current restoration state; court surrounds and fences; verified Community, Shakespeare and Rock Garden forms; railway buildings/clearing; Cob House and heron-colony setting. Existing named-building work may supply some of these separately. No full group completion is claimed here.
