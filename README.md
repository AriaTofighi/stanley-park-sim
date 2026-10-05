# Stanley Park Seawall

Explore Stanley Park in Vancouver on foot or by bicycle. Built with Unreal Engine 5.8 for Windows.

## Play

1. Download **StanleyPark-Windows-v0.5.1.zip** from the [release page](https://github.com/AriaTofighi/stanley-park-sim/releases/tag/v0.5.1).
2. Extract the complete ZIP.
3. Open **StanleyParkSim.exe**.

Unreal Editor and Blender are not required to play. Keep the extracted folders together.

**On foot:** WASD to move, Shift to run, Space to jump, mouse to look.  
**Bicycle:** Tab to switch, W to pedal, S to brake, A/D to steer, Shift to boost up to 80 km/h, Space to jump, P for autopilot.
**Other controls:** Q to reverse when stopped, R to recover, N for nature sounds, H for controls, F1 for ride settings, Esc to pause.

This update adds sunny lighting, a park minimap, improved bicycle movement, grounded trees, ground cover, visitors, and nature audio. See the [release notes](docs/release-notes.md).

This is an early preview. It uses historical terrain data and simplified scenery. It is not a navigation aid. The release was compiled and packaged without an agent-run gameplay test.

## Project

- [Player guide](docs/player-guide.md)
- [Build and edit](docs/building.md)
- [Data and credits](docs/data-and-credits.md)
- [Release notes and check limits](docs/release-notes.md)
- [License information](LICENSE.md)

The repository contains the code, configuration, and data-processing scripts. Large Unreal, Blender, and export assets are separate [release downloads](https://github.com/AriaTofighi/stanley-park-sim/releases/tag/v0.5.1). Run `scripts/restore-assets.ps1` in a clean checkout to restore them.
