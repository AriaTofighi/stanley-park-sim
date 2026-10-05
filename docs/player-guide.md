# Player guide

## Install

Download `StanleyPark-Windows-v0.5.1.zip` from the [v0.5.1 release](https://github.com/AriaTofighi/stanley-park-sim/releases/tag/v0.5.1). Extract all files, then open `StanleyParkSim.exe` in the extracted folder.

This build is for 64-bit Windows and a DirectX 12 graphics device. Unreal Editor and Blender are not required. If Windows reports a missing Microsoft C++ runtime, use the prerequisite installer included under `Engine/Extras/Redist/en-us`.

## Controls

The bottom-left map shows the whole park with north at the top. The pale arrow is your position and heading; the gold line is the Seawall ride. Its 9.46 km label is the total route length, including while on foot. Speed is at top left.

| Action | Key |
| --- | --- |
| Walk | WASD |
| Run | Shift |
| Jump | Space |
| Look | Mouse |
| Switch between on foot and bicycle | Tab |
| Pedal | W |
| Boost the bicycle up to 80 km/h while pedalling | Hold Shift |
| Jump with the bicycle | Space |
| Toggle Seawall autopilot | P |
| Brake | S |
| Back the bicycle away when stopped | Hold Q |
| Steer | A / D |
| Push or remount the bicycle when stopped | E |
| Change bicycle camera | C |
| Bicycle bell | B |
| Toggle nature sounds | N |
| Recover to safe ground | R |
| Ride and graphics settings while cycling | F1 |
| Show controls | H |
| Pause | Esc |

## Graphics

The graphics presets are Performance, Balanced, and Quality. All use a 60 FPS limit. Balanced is the default. Settings are saved between starts.

In v0.5.1, the interface is smaller. The new bicycle defaults are 50 km/h top speed, 4.2 m/s² acceleration, and 18° steering range. Steering becomes gentler as speed increases. F1 retains the adjustable controls and Relaxed pace preset. Old values left at the v0.4 defaults are upgraded once; other custom values remain saved.

If you meet an obstacle, release W and hold Q to back away. R searches for clear dry ground and returns the bicycle to riding mode. Nature sounds start at a low volume; N switches them off or on, and saves that choice.

Hold W and Shift for bicycle boost. Extra pedal force rises gradually. Release Shift to coast down to your ordinary speed limit. Space makes a short jump while riding; you must land before jumping again.

Press P near the Seawall route for autopilot. It follows the complete loop from your current position and repeats until you switch it off. It slows before bends, pushes the bicycle through the physical gate guides, and remounts afterward. Hold Shift for a higher cruise speed on clear straight sections; bends and gates still limit speed. Press P, steer, brake, back up, jump, switch to walking, recover, or open ride settings to take control. If route tracking is lost or an obstacle prevents movement, autopilot stops. It does not teleport past obstacles. No agent-run full-tour check was performed for this release.

## Scope

The scene contains the Seawall route, nearby terrain, coarse landmarks, a visible explorer, and a bicycle rider. You can leave the path where terrain collision permits. Deep-water entry returns the player to a dry safe position; swimming is not included.

The scene uses historical measured data and authored estimates. It does not represent current route access, construction, forest treatment, or tides. Read the [release notes](release-notes.md) for known limits and the [player terms](legal/PLAYER-TERMS.txt) before use.
