"""Focus an existing Blender viewport on a checked corridor review issue."""
import hashlib
import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
request = json.loads((ROOT / "tmp/corridor-focus.json").read_text(encoding="utf-8-sig"))
manifest_path = ROOT / "manifests/corridor-review.json"
if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != request["manifest_sha256"]:
    raise RuntimeError("Corridor review changed. Run focus-corridor again.")
manifest = json.loads(manifest_path.read_text())
origin = ROOT / manifest["origin_path"]
if hashlib.sha256(origin.read_bytes()).hexdigest() != manifest["origin_sha256"]:
    raise RuntimeError("Corridor review and scene origins differ")
issue = next(x for x in manifest["issues"] if x["issue_id"] == request["issue_id"])
if "StanleyPark_M1" not in bpy.data.scenes:
    raise RuntimeError("Open StanleyPark_Blockout.blend first")
bpy.context.window.scene = bpy.data.scenes["StanleyPark_M1"]
eye, target = Vector(issue["eye_local_m"]), Vector(issue["target_local_m"])
rotation = (target-eye).to_track_quat("-Z", "Y")
viewports = 0
for area in bpy.context.screen.areas:
    if area.type != "VIEW_3D":
        continue
    space = area.spaces.active
    space.clip_start = .1
    space.clip_end = 100000
    space.region_3d.view_perspective = "PERSP"
    space.region_3d.view_rotation = rotation
    space.region_3d.view_distance = (target-eye).length
    space.region_3d.view_location = target
    space.shading.color_type = "MATERIAL"
    viewports += 1
if not viewports:
    raise RuntimeError("The active Blender workspace has no 3D viewport")
result = dict(issue_id=issue["issue_id"], viewports=viewports,
              target_local_m=issue["target_local_m"], geometry_changed=False,
              acceptance="Navigation only; the issue remains open")
