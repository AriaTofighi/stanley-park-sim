# v0.4.0 — Seawall preview

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
