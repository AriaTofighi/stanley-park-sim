"""Archive the source, then remove retired generated layers and review scenes.

Run through Blender's authoring bridge. Does not render or run an application test.
Current meshes, materials, transforms, LODs and visibility remain unchanged.
"""
import hashlib
import json
import shutil
from pathlib import Path
import bpy

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'blender/StanleyPark_Seawall.blend'


def inventory():
    return dict(scenes=len(bpy.data.scenes), objects=len(bpy.data.objects),
                meshes=len(bpy.data.meshes), images=len(bpy.data.images),
                bytes=SOURCE.stat().st_size)


def organize():
    if Path(bpy.data.filepath).resolve() != SOURCE.resolve():
        raise RuntimeError('Open the Seawall working source first')
    scene = bpy.data.scenes['StanleyPark_M1']
    pointer = json.loads((ROOT/'exports/seawall-trees/latest.json').read_text())
    current = json.loads((ROOT/pointer['manifest']).read_text())['version']
    active_name = 'SP_SeawallTrees_' + current
    if active_name not in scene.collection.children:
        raise RuntimeError('The current tree collection is missing')
    retired = [c for c in scene.collection.children
               if c.name.startswith('SP_SeawallTrees_') and c.name != active_name]
    if any(not c.hide_viewport or not c.hide_render for c in retired):
        raise RuntimeError('A retired tree collection is still visible; leave it intact')
    archive = ROOT/'blender/archive'
    archive.mkdir(exist_ok=True)
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    original = archive / ('StanleyPark_Seawall_' + digest[:12] + '.blend')
    if not original.exists():
        shutil.copy2(SOURCE, original)
    if hashlib.sha256(original.read_bytes()).hexdigest() != digest:
        raise RuntimeError('Archive copy does not match the source')
    # Keep unsaved user work as well as the exact on-disk milestone source.
    if bpy.data.is_dirty:
        bpy.ops.wm.save_as_mainfile(filepath=str(archive/'StanleyPark_Seawall_before_cleanup.blend'), copy=True)
    before = inventory()
    removed_collections = [c.name for c in retired]
    removed_scenes = [s.name for s in bpy.data.scenes
                      if s.name in {'Scene', 'SP_AnimationFixture'} or s.name.startswith(
                          ('SP_SeawallReview_', 'SP_ShoreReview_', 'SP_TreeFarBake_', 'SP_TreeTextureReview_'))]
    for window in bpy.context.window_manager.windows:
        window.scene = scene
    for name in removed_scenes:
        bpy.data.scenes.remove(bpy.data.scenes[name])
    for collection in retired:
        bpy.data.collections.remove(collection)
    # Only unreferenced datablocks are removed. Shared live geometry is retained.
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
    # Relative texture paths make the project folder portable. Packed images stay packed.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=str(SOURCE), compress=False)
    result = dict(schema_version=1, source=SOURCE.relative_to(ROOT).as_posix(),
                  archive=original.relative_to(ROOT).as_posix(), archive_sha256=digest,
                  before=before, after=inventory(), removed_collections=removed_collections,
                  removed_scenes=removed_scenes, application_tests_run=False)
    (ROOT/'evidence/seawall-blender-organization.json').write_text(json.dumps(result, indent=2))
    return result


result = organize()
