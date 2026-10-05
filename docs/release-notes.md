# v0.5.1 — Public Seawall preview

- Hold Shift while pedalling to raise the bicycle limit to 80 km/h. Pedal force ramps smoothly; releasing Shift coasts down to the regular limit.
- Bicycle jumps do not display an airborne notification.
- Space adds a bicycle jump using the existing swept collision and gravity. Rider, wheels and bicycle stay together; repeated jumps require landing.
- P toggles a player-facing Seawall autopilot. It follows the full loop, slows before bends and gates, uses physical walking guides through the gates, and repeats the loop. Manual steering, braking, jumping, recovery, dismounting and settings cancel it. It stops if it cannot follow the route or an obstacle prevents travel.
- The minimap label is now the complete route length of 9.46 km in both travel modes.
- A clear blue sky, visible sun, warm directional lighting, lighter haze and nearby object shadows replace the cloudy lighting. Coarse terrain and shore components receive shadows without casting the overlapping relief shadows identified in the earlier release.

- The forest floor now has continuous green cover with small dry leaf flecks. Large brown noise patches are removed.
- A north-up minimap at bottom left shows the whole park, the Seawall ride, and the player's live position and heading. It uses the existing boundary, route and water data.
- Speed is a small readout at top left, including on foot. The cycling/walking state label is removed.
- Bicycle motion uses an Unreal movement component for overlap recovery, swept steps over low edges, and sliding around corners. Ground contacts no longer trigger repeated speed multiplication; blocking obstacles still stop travel.

The prior contact changes have positive player feedback. This release includes a fresh Shipping build and matching editable assets. Compilation, cooking, input hashes, and archive checks are recorded separately from gameplay. No agent-run application test or full-tour runtime acceptance was performed for this release.

## Other changes since v0.4.0

These changes address player feedback from 4 October 2026 and are included in v0.5.1.

- Interface scale reduced by 20% at common viewport sizes, with a smaller enlargement cap.
- Bicycle top speed defaults to 50 km/h, acceleration to 4.2 m/s², and steering to 18°. Steering input is smoothed and reduced with speed; turn rate is capped.
- Ground motion can slide along grazing contacts, traverse small curbs, and resolve initial overlap. Retired hidden scenery no longer retains collision.
- Recovery checks spaced safe positions and nearby route positions for dry ground, floor support, and capsule clearance. It returns to cycling. Q provides slow reverse travel from a stop.
- The old offset crown/support layers are replaced with complete upright trees grounded to the existing terrain. Nearby tree samples are spaced away from paths and other trunks.
- Original grass, sword fern, salal, and illustrative flower meshes form varied ground cover. Six original picnic groups add seated people, blankets, and baskets.
- 48 animated walkers and 24 cyclists travel along the main circuit. They yield to the player and have no blocking collision. Clothing and skin colors vary.
- Gulls use six coastal flight zones, up from two. Warm directional fill, a brighter cloud sky, ambient occlusion, and a moss/soil/grass ground shader add visual detail.
- A CC0 forest loop by TinyWorlds adds quiet nature ambience. N toggles it and saves the preference. See [audio provenance](../manifests/nature-audio.json).

Compilation, cooking, asset import, and offline source/archive checks are recorded separately from gameplay. No v0.5.1 application test or runtime visual/performance acceptance is claimed. The earlier 42 Development checks below apply to their earlier build. The new vegetation and crowds can change performance.

## v0.4.0 — Public Seawall preview

Released 4 October 2026 for Windows 64-bit.

## Included

- Seawall scenery, nearby terrain, and coarse Vancouver landmarks.
- Walking, running, jumping, and a visible explorer.
- Bicycle riding, pushing, a visible rider, and animated pedals.
- Movement animation blending and first/third-person bicycle cameras.
- Recovery from deep water to a dry safe position.
- Saved Performance, Balanced, and Quality graphics presets.
- Editable assets, source databases, and attribution notices.

## Recorded checks

The earlier Development build passed 42 native checks across nine short cases: explorer/bicycle controls, one off-road strip, explicit ocean recovery, a downhill sequence, three gates, and two selected path joins.

Four 30-second stationary samples at 2560 × 1440 on an i7-11700K / RTX 3070 computer recorded 7,200 frame intervals, with no interval over 50 ms. They used a 60 FPS cap. These results do not establish minimum hardware requirements or performance along the complete route.

The public package is a fresh Shipping build. It uses the same gameplay source and scene assets, with public packaging configuration and editor-only services disabled. It was compiled, cooked, and checked as an archive. No new application session was run for the publication task, so the earlier Development results are not a new runtime acceptance of the Shipping binary.

## Known limits

- No new full-route check, as requested for the release work.
- No separate clean-computer or long-session check.
- The off-road and water cases cover specific locations, not every slope or shoreline.
- Some recorded camera views hide hand, pedal, wheel, and barrier contact.
- One Development session lost its audio device and continued without sound. One off-road update logged a movement step limit warning.
- The retained Insights analysis has memory-tag and GPU-order warnings; those analyses are not used to approve memory or full-route performance.
- Interior spaces, crowds, dynamic weather, tides, and swimming are not included.

The large local test recordings and machine logs are not published. A compact record of the public build inputs and archive hashes accompanies the release.
