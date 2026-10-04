"""Small, project-specific tools for Epic's official editor MCP registry."""
import json
import hashlib
import runpy
from pathlib import Path
import unreal
import toolset_registry
from toolset_registry.registration import Registration

ROOT = Path(__file__).resolve().parents[2]

def require_park_editor():
    if unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world() is not None:
        raise RuntimeError("Stop the play session before changing generated content")
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name() != "/Game/Maps/StanleyPark.StanleyPark":
        raise RuntimeError("Open the Stanley Park map first")
    return world

@unreal.uclass()
class StanleyParkTools(unreal.ToolsetDefinition):
    """Import this project's checked Blender exports and inspect surface transfer."""

    @toolset_registry.tool_call
    @staticmethod
    def organize_seawall_assets() -> str:
        """Archive the saved Seawall map, remove retired hidden generated canopy actors,
        and refresh active Content Browser collections from the asset catalog.
        Does not run gameplay or change visible geometry, textures or lighting.
        """
        return json.dumps(runpy.run_path(str(ROOT/'pipeline/unreal/organize_seawall_assets.py'))['result'])

    @toolset_registry.tool_call
    @staticmethod
    def apply_m3_layer(layer: str) -> str:
        """Apply one prepared M3 authoring layer to the separate Seawall map.

        Args:
            layer: A named layer in manifests/seawall-m3-layer-scripts.json.
        Does not start Play or change the protected M1 map.
        """
        editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        if editor.get_game_world() is not None:
            raise RuntimeError('Stop Play before applying M3 content')
        if editor.get_editor_world().get_path_name() != '/Game/Maps/StanleyParkSeawall.StanleyParkSeawall':
            raise RuntimeError('Open the separate Seawall map')
        scripts = json.loads((ROOT/'manifests/seawall-m3-layer-scripts.json').read_text())
        if layer not in scripts:
            raise ValueError('Unknown M3 layer')
        script = (ROOT/'pipeline/unreal'/scripts[layer]).resolve()
        if script.parent != (ROOT/'pipeline/unreal').resolve() or script.suffix != '.py':
            raise ValueError('M3 layer must be a project Unreal authoring script')
        return json.dumps(runpy.run_path(str(script))['result'], default=str)

    @toolset_registry.tool_call
    @staticmethod
    def read_seawall_birds() -> str:
        """Read actual bird transforms and clearance counters in an active M2 Play session.

        Does not move actors or start a test. Returns live component telemetry.
        """
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
        if world is None or "StanleyParkSeawall" not in world.get_path_name():
            raise RuntimeError("Start the separate Seawall Play session first")
        values = []
        for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.SPWorldDirector):
            component = actor.get_component_by_class(unreal.SPSeawallBirds)
            if component:
                values.append(json.loads(component.get_review_snapshot()))
        if len(values) != 1:
            raise RuntimeError("Expected one Seawall bird component")
        return json.dumps(values[0])

    @toolset_registry.tool_call
    @staticmethod
    def configure_seawall_review(start_metres: float, record_video: bool, capture_fps: float) -> str:
        """Select the existing bounded F9 review without starting it.

        Args:
            start_metres: Initial route station from 0 to 9400 metres.
            record_video: Record the application viewport after the user starts F9.
            capture_fps: Requested recording rate from 1 to 30 frames per second.
        Returns: The configured values. F9 remains the explicit start action.
        """
        import math
        if not math.isfinite(start_metres) or not 0 <= start_metres <= 9400:
            raise ValueError("Invalid route station")
        if not math.isfinite(capture_fps) or not 1 <= capture_fps <= 30:
            raise ValueError("Invalid capture rate")
        editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        world = editor.get_game_world() or editor.get_editor_world()
        if "StanleyParkSeawall" not in world.get_path_name():
            raise RuntimeError("Open the separate seawall map")
        settings = {"sp.SeawallReview.StartMetres": start_metres,
                    "sp.SeawallReview.Record": int(record_video),
                    "sp.RideCapture.FPS": capture_fps}
        for name, value in settings.items():
            unreal.SystemLibrary.execute_console_command(world, name + " " + str(value))
        return json.dumps(settings)

    @toolset_registry.tool_call
    @staticmethod
    def prepare_seawall_map() -> str:
        """Open the separate seawall map, creating it from the M1 map if absent.

        Does not start gameplay or overwrite the original M1 map.
        Returns: the current map and whether a new map was created.
        """
        editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        if editor.get_game_world() is not None:
            raise RuntimeError("Stop the play session before editing the seawall map")
        subsystem = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
        target = "/Game/Maps/StanleyParkSeawall"
        created = not subsystem.does_asset_exist(target)
        if created:
            if editor.get_editor_world().get_path_name() != "/Game/Maps/StanleyPark.StanleyPark":
                raise RuntimeError("Open the unchanged M1 map before creating the seawall copy")
            duplicate = subsystem.duplicate_asset("/Game/Maps/StanleyPark", target)
            if duplicate is None or not subsystem.save_loaded_asset(duplicate):
                raise RuntimeError("Could not save the separate seawall map")
            # A live Python World wrapper prevents map-load garbage collection.
            # Release the duplicate before the editor switches worlds.
            del duplicate
            import gc
            gc.collect()
        levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if (editor.get_editor_world().get_path_name() != target + ".StanleyParkSeawall"
                and not levels.load_level(target)):
            raise RuntimeError("Could not open the seawall map")
        return json.dumps(dict(map=editor.get_editor_world().get_path_name(), created=created))

    @toolset_registry.tool_call
    @staticmethod
    def apply_seawall_layer(layer: str) -> str:
        """Apply one checked-in visual layer to the separate seawall map.

        Args:
            layer: water_sky, trees, bird_kit, or shore.
        Returns:
            The layer script result. This is authoring, not a gameplay test.
        """
        import os
        editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        if editor.get_game_world() is not None:
            raise RuntimeError("Stop the play session before changing visual layers")
        target = "/Game/Maps/StanleyParkSeawall"
        if editor.get_editor_world().get_path_name() != target + ".StanleyParkSeawall":
            raise RuntimeError("Open the separate seawall map first")
        scripts = {"water_sky": "apply_seawall_water_sky.py",
                   "trees": "import_seawall_trees.py", "bird_kit": "import_seawall_bird.py",
                   "shore": "apply_seawall_shore.py"}
        if layer not in scripts:
            raise ValueError("Unknown seawall layer")
        script = ROOT / "pipeline/unreal" / scripts[layer]
        if not script.is_file():
            raise RuntimeError("The layer script is not ready")
        old = os.environ.get("SP_SEAWALL_MAP_PATH")
        try:
            os.environ["SP_SEAWALL_MAP_PATH"] = target
            namespace = runpy.run_path(str(script))
        finally:
            if old is None:
                os.environ.pop("SP_SEAWALL_MAP_PATH", None)
            else:
                os.environ["SP_SEAWALL_MAP_PATH"] = old
        return json.dumps(namespace.get("result", {"layer": layer, "script_returned": True}), default=str)

    @toolset_registry.tool_call
    @staticmethod
    def inspect_m1_view(view_id: str) -> str:
        """Set one named editor view for source and lighting inspection.

        Args:
            view_id: ride_start, cliff_shadow, siwash, brockton, lions_gate_west, or forest_groups.

        Returns:
            The exact camera and target position. A view is not an interactive test.
        """
        require_park_editor()
        return json.dumps(runpy.run_path(str(ROOT/'pipeline/unreal/inspect_m1_view.py'))['inspect'](view_id))

    @toolset_registry.tool_call
    @staticmethod
    def import_animation_fixture() -> str:
        """Import and measure the project's fixed Blender animation fixture.

        Saves numerical poses to the evidence folder. Does not start a game.

        Returns:
            Animation transfer summary and saved asset paths.
        """
        require_park_editor()
        record=runpy.run_path(str(ROOT/'pipeline/unreal/import_animation_fixture.py'))['result']
        return json.dumps({key:record[key] for key in ['pass_','mesh','animation','maximum_position_error_cm','duration_error_seconds']})

    @toolset_registry.tool_call
    @staticmethod
    def import_generated_world() -> str:
        """Import the checked project export manifest and update its tagged actors.

        Preserves untagged actors. Saves assets and the current Stanley Park map.
        Uses only the fixed checked-in import script. No file or code arguments.

        Returns:
            JSON summary of the import checks and saved evidence.
        """
        require_park_editor()
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
        runpy.run_path(str(ROOT / "pipeline/unreal/import_world.py"))
        record = json.loads((ROOT / "evidence/unreal-import.json").read_text())
        return json.dumps(dict(success=record["success"], assets=len(record["assets"]),
            max_bounds_error_cm=max(x["bounds_error_cm"] for x in record["assets"]),
            evidence="evidence/unreal-import.json"))

    @toolset_registry.tool_call
    @staticmethod
    def check_surface_transfer() -> str:
        """Trace the imported terrain at fixed geometric control points.

        This is the plan's numerical export/collision check, not a bicycle ride.
        It saves hits, gaps and measured residuals to the project evidence folder.

        Returns:
            JSON summary of the numerical check.
        """
        world = require_park_editor()
        controls = json.loads((ROOT / "data/derived/surface-control-points.json").read_text())
        if controls["surface_manifest_sha256"] != hashlib.sha256((ROOT / "manifests/surface-model.json").read_bytes()).hexdigest():
            raise RuntimeError("Surface control points do not match the mesh manifest")
        rows = []
        for p in controls["points_local_m"]:
            start = unreal.Vector(p[1]*100, p[0]*100, p[2]*100+200)
            end = unreal.Vector(start.x, start.y, start.z-400)
            hit = unreal.SystemLibrary.line_trace_single(world, start, end,
                unreal.TraceTypeQuery.ECC_VISIBILITY, True, [], unreal.DrawDebugTrace.NONE, True)
            height = hit.to_dict()["location"].z / 100 if hit else None
            rows.append(dict(source_m=p, hit_height_m=height,
                             residual_m=height-p[2] if height is not None else None))
        residuals = [abs(r["residual_m"]) for r in rows if r["residual_m"] is not None]
        summary = dict(controls=len(rows), missing=len(rows)-len(residuals),
                       maximum_residual_m=max(residuals) if residuals else None,
                       tolerance_m=.01, acceptance="geometry transfer only")
        summary["pass"] = summary["missing"] == 0 and summary["maximum_residual_m"] <= .01
        (ROOT / "evidence/unreal-surface-transfer.json").write_text(json.dumps(
            dict(summary=summary, points=rows), indent=2), encoding="utf-8")
        return json.dumps(summary)

registration = Registration([StanleyParkTools])
registration.register()
