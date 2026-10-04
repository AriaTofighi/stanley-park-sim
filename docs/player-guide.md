# Player guide

## Install

Download `StanleyPark-Windows-v0.4.0.zip` from the [v0.4.0 release](https://github.com/AriaTofighi/stanley-park-sim/releases/tag/v0.4.0). Extract all files, then open `StanleyParkSim.exe` in the extracted folder.

This build is for 64-bit Windows and a DirectX 12 graphics device. Unreal Editor and Blender are not required. If Windows reports a missing Microsoft C++ runtime, use the prerequisite installer included under `Engine/Extras/Redist/en-us`.

## Controls

| Action | Key |
| --- | --- |
| Walk | WASD |
| Run | Shift |
| Jump | Space |
| Look | Mouse |
| Switch between on foot and bicycle | Tab |
| Pedal | W |
| Brake | S |
| Steer | A / D |
| Push or remount the bicycle when stopped | E |
| Change bicycle camera | C |
| Bicycle bell | B |
| Recover to safe ground | R |
| Ride and graphics settings while cycling | F1 |
| Show controls | H |
| Pause | Esc |

## Graphics

The graphics presets are Performance, Balanced, and Quality. All use a 60 FPS limit. Balanced is the default. Settings are saved between starts.

## Scope

The scene contains the Seawall route, nearby terrain, coarse landmarks, a visible explorer, and a bicycle rider. You can leave the path where terrain collision permits. Deep-water entry returns the player to a dry safe position; swimming is not included.

The scene uses historical measured data and authored estimates. It does not represent current route access, construction, forest treatment, or tides. Read the [release notes](release-notes.md) for known limits and the [player terms](legal/PLAYER-TERMS.txt) before use.
