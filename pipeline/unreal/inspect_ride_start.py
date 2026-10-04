"""Editor view at the route start. A still view is not a bicycle ride test."""
from pathlib import Path
import json
import runpy
import unreal

root = Path(__file__).resolve().parents[2]
runpy.run_path(str(root / "pipeline/unreal/adjust_inspection_lighting.py"))
data = json.loads((root / "unreal/Content/WorldData/world.json").read_text(encoding="utf-8"))
position = list(data["spawn"])
position[2] += 165
unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(
    unreal.Vector(*position), unreal.Rotator(pitch=-5, yaw=data["spawn_yaw"], roll=0))
