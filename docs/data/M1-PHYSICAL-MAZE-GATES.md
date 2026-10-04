> Historical source note from the development baseline. See [current release notes](../release-notes.md) for the public release. File paths below are relative to the project root. Raw inspection media remain in the local archive.

# M1 physical maze gates

Status: authored data package; live Blender and application review pending. The package has 26 original steel-frame meshes with physical collision. It depicts the three dated existing-condition sites in the City2025 report. It does not depict the proposed replacement planters.

| Site | Source station | Form | Walking approach start |
|---|---:|---|---:|
| Lumberman's Arch | 3181.931 m | Two offset rows | 3173.931 m |
| Prospect Point | 4703.897 m | Original OSM longitudinal divider and an estimated short inner return | 4689.897 m |
| Third Beach | 6682.854 m | Two offset rows at the north entrance | 6674.854 m |

Stations are along the unchanged source chain, not cumulative distance through the new walking curves. The Third Beach north location matches the 2022 image and the City2024 existing-condition diagram. OSM node8047538220 lies about19 m farther south; it is retained as conflicting evidence, not added as another maze. The chosen north node is9044369084. Canopy obscures the Lumberman frame endpoints. Its pose remains an estimate near node245809598. Prospect retains both original coordinates from railing way1227211750.

Posts are1.05 m high, 0.075 m wide; rails are0.065 m wide at0.46/1.01 m. Double-row spacing is an estimated3 m. Estimated clear gaps are1.10 m at Lumberman and Prospect and1.05 m at Third Beach. These dimensions are not surveyed. They preserve a narrow walking passage for the current0.64 m contact width, while the overlapping rows remain an obstacle. Adaptive/long bicycles are not claimed to fit.

`manifests/maze-gate-settings.json` records estimates and source dates. `pipeline/gis/build_maze_gate_blockouts.py` builds frames first, then checks a dense walking path against their fixed collision envelopes and actual exported pavement triangles. It does not move or remove frames to satisfy the walking check. Post bottoms are measured from those triangles; they embed0.04 m. Two identical shared posts in the first divider draft were consolidated to prevent duplicate faces.

The first attempt found an outer post0.0843 m off the authored pavement because route-normal interpolation differed from the actual bend edge. The repeat uses the actual cross-section for post placement. The next check found a walking-contact edge conflict at Lumberman. A path-only correction of at most0.1202 m fixed it. Both failures are retained in `evidence/facilities/`. The final minimum margins beyond the0.32 m capsule radius are0.0988 m at Lumberman,0.2247 m at Prospect and0.2009 m at Third Beach. This is a geometric pass, not a controller or steering pass.

The manifest `sites[].walking_path` provides dense source stations and local XYZ. Every height comes from actual pavement triangles. Root must integrate this path into the live walking/diagnostic route, keep collision on, and shift the estimated walking starts earlier than the physical approach. The current Third Beach6684 m and Prospect4698 m starts are too late. Do not change barrier collision or let the diagnostic bypass the frames to get a pass.

Run `pipeline/blender/build_maze_gate_blockouts.py` after the matching pavement stage. Inspect frame placement and gap shape in Blender. In the application, stop, dismount, pass through every gap and resume riding after the permitted end. Retain contact/steering evidence and repeat each failure. Both directions can be used for local recovery inspection, but the legal circuit direction remains unchanged.

The [City report](https://parkboardmeetings.vancouver.ca/2025/20250310/REPORT-EnhancedAccessibilityonSeawallCyclingPath-ReportBack-20250310.pdf), pages21–23, contains 2024 existing-condition photos. The February2025 report proposes seeking replacement funding in the2027–2030 capital plan. One bounded City search on27 September2026 found no completed replacement. Thus current physical state remains unverified; the package records a dated reconstruction. No report image or PDF is redistributed. Source XML and the adapted geometry are included under ODbL1.0, with separate City2022 pavement provenance.
