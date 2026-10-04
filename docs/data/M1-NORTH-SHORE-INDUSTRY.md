> Historical source note from the development baseline. See [current release notes](../release-notes.md) for the public release. File paths below are relative to the project root. Raw inspection media remain in the local archive.

# M1 North Shore industrial silhouettes

This is the finite North Shore part of M1-F12. It adds the main industrial forms that can be seen across Burrard Inlet. It is a distant blockout, with no collision, interiors, terminal operations, vessel traffic, or detailed equipment simulation. It does not establish that all M1-F12 views pass.

## Authored scope

The package has seven source-bounded sites, 282 parts, 17 meshes grouped by site and material, and 13,570 triangles. The current OSM snapshot was acquired on 2026-09-27. Current feature footprints determine XY positions. Per-feature OSM edit dates are retained; an edit date is not a survey date.

| Site | Forms included | Height basis and limits |
| --- | --- | --- |
| Vancouver Wharves | Large covered stores, mapped tanks/silos and conveyors | Operator confirms the terminal functions. All individual form heights are explicit estimates. |
| Fibreco | Six northern pellet silos, 15 southern grain silos, central shed and other large mapped structures | Operator confirms the silo counts and grain facility completion in 2021. Silo and shed heights are estimates. |
| Seaspan | Large shops and Big Blue gantry crane | Owner and contractor state 80 m height and 76 m width. The mapped crane polygon is a travel envelope, not a solid building. The crane is placed at an estimated position along that envelope. Beam sizes, leg spread and parked position are estimates. |
| Richardson | Old storage, workhouse and 28 current annex silo footprints | The 2012 project report gives approximate 50 m annex height and differences that imply 73 m workhouse and 45 m old storage. A 2016 announcement confirms annex completion. These are design dimensions, not an as-built survey. The workhouse subdivision is inferred from the project photograph and current footprint. |
| Cargill | 21 mapped silos, large storage buildings and a workhouse form | Current OSM, the port map and operator location list establish the site. Heights and the workhouse assignment are estimates. |
| Neptune | Two large potash sheds, other mapped structures and long conveyors | Operator confirms two covered potash sheds. Roof dimensions are estimates. The current Berth Two loader is omitted because a multi-year replacement project makes its September 2026 form uncertain. Variable coal stockpiles are also omitted. |
| G3 | 48 silos, cleaning tower, conveyors and three coarse shiploaders | Construction sources give about 42.6 m silo bodies, an 81 m cleaning facility and three loaders. A supplier states 64 m including conveyors; that conflict remains open. The galleries, loader members and parked positions are estimates. |

Each terminal uses one shared base from the existing near/far CGVD2013 terrain. Most terminal bases come from the 80 m far grid. They are not measured slab elevations. This avoids different grid samples lifting adjacent silos to different heights. No City 2009 building footprint is imported.

## Sources and permitted use

The full URL, date, use, licence and limitations register is `manifests/northshore-reference-sources.json`. Downloads and their SHA-256 values are in `manifests/northshore-source-acquisition.json`. OSM geometry is incorporated under ODbL with OpenStreetMap contributor attribution and a source offer. Primary operator and contractor material is reference only. Do not include its PDFs or rendered pages in the game or open-data source bundle.

The primary evidence includes the [Port of Vancouver berth map](https://www.portvancouver.com/sites/default/files/2024-10/2024-VFPA-berth-soundings-map-EN-Oct-31_0.pdf), [Fibreco operations](https://fibreco.com/terminal-operations/), [Seaspan crane contractor sheet](https://www.supremehm.com/wp-content/uploads/2015/07/SST-Project-Sheet-Seaspan-Goliath.pdf), [Richardson project report](https://www.richardson.ca/wp-content/uploads/2015/12/Richardson-Vancouver-TerminalGrain-Storage-Project-Proj.pdf), [Neptune operations](https://www.neptuneterminals.com/about/operations), and the [G3 construction account](https://www.clac.ca/Your-voice/Article/project-profile-g3-terminal). Their dimensions have the limits stated above and in the register.

The Richardson report photograph/render on physical PDF page 5 and Seaspan contractor sheet page 1 were rendered locally and inspected. This does not verify the current appearance of each terminal. Remote image links that were returned without viewable image content were not treated as inspected images. An old Fibreco project URL returned a domain-sale HTML page and was rejected. The attempted G3 reference PDF download failed; no local image review is claimed for it.

## Reproduction and live integration

Run these GIS steps with `pipeline/gis/.venv/Scripts/python.exe` from the repository root:

1. `pipeline/gis/acquire_northshore_sources.py` acquires bounded raw data. Existing files are cached.
2. `pipeline/gis/build_northshore_blockouts.py` reads the current data and settings, then writes grouped NPZ meshes and the part manifest.
3. `pipeline/gis/inspect_northshore_blockouts.py` checks the data and creates the static preview and suggested cameras.

Editable parameters are in `manifests/northshore-authoring-settings.json`. The builder retains original feature tags, source URLs, height method, shared base, triangle ranges and source hashes for each part. It subtracts contained silo polygons from general building footprints so that parent building forms do not cover the silo outlines. The crane has open space below its girder; the mapped travel envelope is not extruded as a building.

Root must run `pipeline/blender/build_northshore_blockouts.py` through the live Blender MCP connection. It verifies source and mesh hashes before it replaces its own objects in `SP_11_NorthShoreIndustry`. It saves the editable main `.blend` file. The authoring stage has not been run by this agent. Root must add that collection to the scene export/import set, retain its material groups and disable collision.

Use only the derived mesh paths listed by `manifests/northshore-blockouts.json` in a game/source package. Raw OSM files, the transform scripts, settings and the derived site bounds are the reproducible source offer. Reference-only downloads and screenshots are excluded.

## Checks and remaining acceptance

`evidence/northshore-numerical-review.json` records successful offline checks for input and mesh hashes, finite vertices, valid indices, unique part IDs, solid individual parts, shared terminal bases, exact authored 80 m crane height, 48 G3 silos, 21 Fibreco silos, and the 25,000-triangle package budget. No selected site has missing OSM relation members. No selected part was silently excluded.

The first Richardson workhouse split made a zero-width cap sliver. The builder now intersects each side with the same independent half-plane boundary. The mesh check passed after this correction. This is recorded here as a geometry failure and repeat, not a source change.

`evidence/northshore-blockout-shapes.png` was opened and inspected. The preview shows separate silo forms, pitched storage roofs, an open crane and distinct Richardson storage/workhouse levels. It checks generated shapes only. It cannot prove scene placement, water/terrain alignment, real visibility, lighting, export or runtime frame time.

Live acceptance remains false. The numerical report contains route-derived camera eyes and targets for all seven sites. The western sites use runtime chainage 3299.67 m with eye `[859.87, 138.15, 4.99]`; the eastern sites use chainage 2050.05 m with eye `[1861.73, -220.13, 11.05]`. Coordinates are local east, north, CGVD2013 height in metres. Eye height is route surface plus 1.7 m. The suggested horizontal field of view is 70 degrees. Unreal conversion is X=north*100, Y=east*100, Z=height*100.

Root must check those views in Blender and the running application. Confirm terminal order, relative height, shoreline placement, view obstruction, no floating bases at the coast, and sensible silhouettes at normal cycling field of view. Retain route screenshots and the scene/export manifest hashes. Resolve or record any failure before M1-F12 acceptance. No application test was performed by this agent.
