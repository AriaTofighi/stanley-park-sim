"""Extract layer files in background Blender; never run in an interactive session.

The original saved source is read again for each layer and is never overwritten.
Use save_as_mainfile: libraries.write crashes on this source in Blender 5.2.1.
"""
from pathlib import Path
import json
import bpy
import faulthandler
faulthandler.enable()

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'blender/StanleyPark_Seawall.blend'
OUT = ROOT / 'blender/modules'
ASSEMBLY = ROOT / 'blender/StanleyPark_Assembly.blend'

def run():
    if not bpy.app.background:
        raise RuntimeError('Run in background Blender, not the interactive session')
    if Path(bpy.data.filepath).resolve() != SOURCE.resolve():
        raise RuntimeError('Open the original Seawall source first')
    if ASSEMBLY.exists():
        raise RuntimeError('Assembly already exists. Edit its modules; do not overwrite them.')
    OUT.mkdir(exist_ok=True)
    bpy.context.preferences.filepaths.file_preview_type = 'NONE'
    source_scene = bpy.data.scenes['StanleyPark_M1']
    before = SOURCE.stat().st_size
    groups = {}
    for collection in source_scene.collection.children:
        name = collection.name
        if collection.hide_render and collection.hide_viewport:
            group = 'Retired_Reference'
        elif any(t in name for t in ('CrownRepair', 'SeawallTrees', 'M3Forest')):
            # Keep each authored vegetation layer independently editable.
            group = name.removeprefix('SP_')
        elif any(t in name for t in ('Terrain', 'Water', 'SurveyCover', 'VegetationZone')):
            group = 'Terrain_Water'
        elif any(t in name for t in ('RouteBlockout', 'PedestrianSurfaces', 'PhysicalGates', 'Underpasses')):
            group = 'Routes_Ground'
        elif any(t in name for t in ('SeawallShore', 'M3Edges', 'EdgeSkirts')):
            group = 'Shore_Edges'
        else:
            group = 'Sites_Details'
        groups.setdefault(group, []).append(collection.name)
    rows = []
    for group, names in groups.items():
        print('SPLIT preparing ' + group, flush=True)
        if rows:
            bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
        bpy.context.preferences.filepaths.file_preview_type = 'NONE'
        scene = bpy.data.scenes['StanleyPark_M1']
        if bpy.context.window:
            bpy.context.window.scene = scene
        for other in list(bpy.data.scenes):
            if other != scene:
                bpy.data.scenes.remove(other)
        scene.name = 'EDIT_' + group
        root = bpy.data.collections.new('MODULE_' + group)
        scene.collection.children.link(root)
        for collection in list(scene.collection.children):
            if collection == root:
                continue
            if collection.name in names:
                root.children.link(collection)
            scene.collection.children.unlink(collection)
        bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
        # Bounding-box display reduces forest draw cost without changing exports.
        foliage = any(t in group for t in ('CrownRepair', 'SeawallTrees', 'M3Forest'))
        if foliage:
            for obj in root.all_objects:
                if obj.type == 'MESH':
                    obj.display_type = 'BOUNDS'
        path = OUT / (group + '.blend')
        print('SPLIT writing ' + str(path), flush=True)
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    area.spaces.active.shading.type = 'SOLID'
                    area.spaces.active.shading.color_type = 'MATERIAL'
        bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=True, relative_remap=True)
        print('SPLIT written ' + group, flush=True)
        rows.append(dict(file=path.relative_to(ROOT).as_posix(), collection=root.name,
                         objects=len(root.all_objects), foliage=foliage,
                         excluded=foliage or group == 'Retired_Reference', bytes=path.stat().st_size))
    # Build the assembly in an independent background process. The original
    # in-memory scene is retained until the new file is complete.
    record = dict(source=str(SOURCE.relative_to(ROOT)), source_before_bytes=before,
                  source_after_bytes=SOURCE.stat().st_size, assembly=str(ASSEMBLY.relative_to(ROOT)), modules=rows)
    (ROOT/'manifests/blender-modules.json').write_text(json.dumps(record, indent=2))
    return record

result = run()
