> Historical source note from the development baseline. See [current release notes](../release-notes.md) for the public release. File paths below are relative to the project root. Raw inspection media remain in the local archive.

# M1 functional navigation package

This package provides readable route guidance for the current blockout. It is not a reconstruction of physical sign locations. No georeferenced physical sign positions are verified. The source ledger and each marker record state this limit.

The current package has 25 boards and posts, with 10 pavement arrows. Its GIS geometry has 60 meshes and 650 triangles before text. The live Blender stage adds 25 text meshes. The shortest calculated board-to-pavement gap is 0.400 m. All markers are non-colliding functional aids. They do not replace required physical barrier models or change route permissions.

## Covered navigation

- The three current walk-bike zones: Lumberman's Arch, Prospect Point and Third Beach. Each has an advance board 40 source metres before the start, a start board and an end board. Limits use the same existing M1 estimates as `world.json`; their actual sign endpoints are not surveyed.
- Seven main-route source junctions. Boards and arrows identify the continuing circuit. They do not grant unresolved branch permissions. The Coal Harbour, English Bay/Ceperley and Chilco entrance connections have distinct text.
- Nine mapped boundary nodes entering Beaver Lake or Ravine trails. The City map restriction and OSM `bicycle=no` tags support walking-only guidance. These are topology boundaries, not surveyed signs.
- Counter-clockwise direction and the map's 15 km/h guidance. The user's faster debug setting remains a separate runtime control.

City junction 041 has no junction marker and no transfer. It is the road above the Chilco underpass. The City map's cliff-access warning is retained as a restriction record; its approximate printed kilometre range is not converted into invented exact sign locations.

The 2025 maze-gate report describes existing conditions and proposed changes. The 2026 map still has walk-bike callouts. This package creates no maze gates from unverified construction proposals. Exact physical gate state remains a separate source question.

## Files and use

- `manifests/navigation-detail-settings.json`: editable dimensions, source references, placement policy and entrance names.
- `pipeline/routes/build_navigation_details.py`: route, junction and restriction generation.
- `pipeline/routes/navigation_meshes.py`: small original geometry and numerical checks.
- `data/routes/derived/navigation-details.json`: every marker, source association, restriction, source/runtime chainage, placement class and mesh hash.
- `pipeline/blender/build_navigation_details.py`: live Blender authoring stage. It uses the built-in font, creates ordinary mesh labels, stores their text as an editable property and saves the `.blend` source.

Run the GIS stage after the current route and `world.json` have been generated:

```powershell
.\pipeline\gis\.venv\Scripts\python.exe pipeline/routes/build_navigation_details.py
```

Then run the Blender stage through the existing live MCP connection. The stage does not launch Blender. It checks all source hashes before it replaces its owned objects in `SP_09_Navigation`. The existing shared exporter can export the resulting mesh objects. All source transforms remain translation-only and use the established metre-based local frame.

## Checks and remaining work

The GIS stage checks finite geometry, positive solid volume, non-degenerate triangles, source/runtime walk-zone agreement, pavement clearance and the grade-separated junction exclusion. The first arrow triangulation had collinear triangles. It was corrected, then the generation completed with no unplaced markers. No application test was run by this package task.

The live Blender check must inspect text orientation, legibility, post/ground contact and route-arrow contact at all three dismount areas, the southwest junctions and the entrances. Preserve screenshots. The markers have estimated positions outside the riding surface; a numerical gap does not prove that a marker is visually suitable beside a tree, pedestrian path or steep bank.

In Unreal, approach each walk-bike start, stop, press E, traverse the walking section, stop at its end and remount. Verify that the visible boundary agrees with the controller transition. Follow each main-route continuation arrow. Verify that the 041 crossing has no misleading turn. Check the no-cycling guidance from the mapped inbound trail at each inland boundary. Retain failures and repeat the same checks after corrections.

The current controller enforces only `world.json` walk zones, based on nearest main-route chainage within 5 m. This package does not implement branch-direction enforcement or inland no-cycling enforcement. Those remain explicit integration decisions for the controller owner. The marker data does not silently enable a blocked graph edge or a bridge that lacks a valid surface.

Original marker meshes and text contain no copied City map art or report photographs. City route data retains Open Government Licence – Vancouver attribution. The OSM-derived inland restriction database retains ODbL and contributor attribution, together with its source graph.
