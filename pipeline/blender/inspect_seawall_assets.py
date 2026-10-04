"""Capture actual authored meshes in a Blender viewport; never accept them here."""
import hashlib
import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]


def inspect(kind, capture_id):
    if kind not in {"birds", "trees"} or not capture_id.replace('-', '').isalnum():
        raise ValueError("Use birds/trees and a simple capture ID")
    output = ROOT / "evidence" / (capture_id + ".png")
    if output.exists():
        raise FileExistsError(output)
    prior_scene = bpy.context.window.scene
    review = bpy.data.scenes.new("SP_SeawallReview_" + capture_id)
    review.unit_settings.system = "METRIC"
    review.unit_settings.scale_length = 1.0
    if kind == "birds":
        for name, offset in [("SM_GullBody", (0, 0, 0)),
                             ("SM_GullWingLeft", (-.09, 0, .03)),
                             ("SM_GullWingRight", (.09, 0, .03))]:
            source = bpy.data.objects[name]
            obj = bpy.data.objects.new("Review_" + name, source.data)
            review.collection.objects.link(obj)
            obj.location = offset
        eye, target = Vector((1.35, 1.8, 1.05)), Vector((0, 0, 0))
    else:
        pointer = json.loads((ROOT / "exports/seawall-trees/latest.json").read_text())
        manifest = json.loads((ROOT / pointer["manifest"]).read_text())
        for index, tree in enumerate(manifest["trees"]):
            source = bpy.data.objects[tree["lods"][0]["name"]]
            obj = bpy.data.objects.new("Review_" + source.name, source.data)
            review.collection.objects.link(obj)
            obj.location = ((index % 3) * 18, (index // 3) * 26, 0)
        eye, target = Vector((70, -95, 43)), Vector((18, 11, 10))
    bpy.context.window.scene = review
    area = next(a for a in bpy.context.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    viewport = area.spaces.active
    viewport.region_3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    viewport.region_3d.view_location = target
    viewport.region_3d.view_distance = (target - eye).length
    viewport.region_3d.view_perspective = 'PERSP'
    viewport.lens = 50
    viewport.clip_start = .01 if kind == "birds" else .1
    viewport.clip_end = 5000
    viewport.shading.type = 'SOLID'
    viewport.shading.color_type = 'MATERIAL'
    viewport.shading.light = 'STUDIO'
    viewport.shading.show_shadows = True
    viewport.shading.show_cavity = True
    viewport.overlay.show_overlays = False
    review.render.filepath = str(output)
    review.render.resolution_x = 1600
    review.render.resolution_y = 1000
    review.render.resolution_percentage = 100
    try:
        with bpy.context.temp_override(area=area, region=region):
            bpy.ops.render.opengl(write_still=True, view_context=True)
    finally:
        bpy.context.window.scene = prior_scene
    record = dict(kind=kind, source_blend=bpy.data.filepath, review_scene=review.name,
                  image=output.relative_to(ROOT).as_posix(),
                  image_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                  method="Actual Blender viewport via official MCP", inspected=False,
                  scope="Mesh appearance and assembled rest pose only; no runtime or motion test")
    output.with_suffix('.json').write_text(json.dumps(record, indent=2), encoding='utf8')
    return record
