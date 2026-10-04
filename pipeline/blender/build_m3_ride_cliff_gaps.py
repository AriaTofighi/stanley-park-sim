"""Export separate decorative fills for two ride-visible terrain/support seams."""
from pathlib import Path
import hashlib
import json
import math
import shutil
import bpy
import numpy as np
from mathutils import Matrix

ROOT=Path(__file__).resolve().parents[2]
OWNER='m3_ride_cliff_gaps'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def original_geometry():
    baseline=json.loads((ROOT/'evidence/m3-baseline-20261003/blender-original-geometry.json').read_text())
    result=[]
    for row in baseline:
        obj=bpy.data.objects[row['name']]
        coordinates=np.empty(len(obj.data.vertices)*3,dtype=np.float32)
        obj.data.vertices.foreach_get('co',coordinates)
        indices=np.empty(len(obj.data.loops),dtype=np.int32)
        obj.data.loops.foreach_get('vertex_index',indices)
        result.append(dict(name=obj.name,geometry_sha256=hashlib.sha256(coordinates.tobytes()+indices.tobytes()).hexdigest(),matrix=[list(r) for r in obj.matrix_world],collision=obj.get('collision')))
    if result!=baseline:
        raise RuntimeError('Protected original geometry differs from its baseline')
    return result


def verify_live_source(name):
    data=np.load(ROOT/'data/derived/surface-meshes'/(name+'.npz'))
    expected=data['vertices'].astype(float)+data['anchor']
    obj=bpy.data.objects[name]
    coordinates=np.empty(len(obj.data.vertices)*3,dtype=np.float32)
    obj.data.vertices.foreach_get('co',coordinates)
    transform=np.asarray(obj.matrix_world,dtype=float)
    actual=coordinates.reshape(-1,3)@transform[:3,:3].T+transform[:3,3]
    if actual.shape!=expected.shape or np.linalg.norm(actual-expected,axis=1).max()>.001:
        raise RuntimeError('Saved source points differ from live original mesh: '+name)
    return obj


def build():
    expected=ROOT/'blender/StanleyPark_Seawall.blend'
    if Path(bpy.data.filepath).resolve()!=expected.resolve():
        raise RuntimeError('Open the separate Seawall source')
    if bpy.context.mode!='OBJECT':
        raise RuntimeError('Use Object mode before this authoring step')
    scene=bpy.data.scenes['StanleyPark_M1']
    bpy.context.window.scene=scene
    if scene.unit_settings.scale_length!=1:
        raise RuntimeError('Expected metre source')
    before=original_geometry()
    pointer=json.loads((ROOT/'data/derived/m3-ride-cliff-gaps/latest.json').read_text())
    source_path=ROOT/pointer['source']
    if sha(source_path)!=pointer['sha256']:
        raise RuntimeError('Prepared gap source changed')
    source=json.loads(source_path.read_text())
    for path,digest in source['input_hashes'].items():
        if sha(ROOT/path)!=digest:
            raise RuntimeError('Prepared input changed: '+path)
    for asset in source['assets']:
        for name in [asset['source_support'],asset['source_terrain']]:
            verify_live_source(name)
    inputs=dict(source['input_hashes'])
    for path in [pointer['source'],'pipeline/blender/build_m3_ride_cliff_gaps.py','evidence/m3-baseline-20261003/blender-original-geometry.json']:
        inputs[path]=sha(ROOT/path)
    inputs['scene_geometry_digest']=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()
    version=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:12]
    folder=ROOT/'exports/m3-ride-cliff-gaps'/version
    if (folder/'manifest.json').exists():
        raise RuntimeError('Immutable export version already exists')
    bpy.ops.wm.save_as_mainfile(filepath=str(expected))
    digest=sha(expected)
    archive=ROOT/'blender/archive'/('StanleyPark_Seawall_'+digest[:12]+'.blend')
    archive.parent.mkdir(exist_ok=True)
    if not archive.exists():
        shutil.copy2(expected,archive)
    if sha(archive)!=digest:
        raise RuntimeError('Source archive differs')
    collection=bpy.data.collections.new('SP_M3RideCliffGaps_'+version)
    scene.collection.children.link(collection)
    folder.mkdir(parents=True,exist_ok=True)
    assets=[]
    rotation=Matrix.Rotation(-math.pi/2,4,'Z')
    for item in source['assets']:
        values=np.asarray(item['vertices_local_m'])
        anchor=(values.min(0)+values.max(0))*.5
        local=values-anchor
        name=item['name']
        mesh=bpy.data.meshes.new(name+'_'+version)
        mesh.from_pydata(local.tolist(),[],item['triangles'])
        mesh.update()
        original=bpy.data.objects[item['source_support']]
        if original.data.materials:
            mesh.materials.append(original.data.materials[0])
        authored=bpy.data.objects.new(name+'_'+version,mesh)
        collection.objects.link(authored)
        authored.location=anchor
        authored['pipeline_owner']=OWNER
        authored['collision']='none'
        temporary_mesh=mesh.copy()
        temporary_mesh.transform(rotation)
        temporary=bpy.data.objects.new('Export_'+name,temporary_mesh)
        scene.collection.objects.link(temporary)
        bpy.ops.object.select_all(action='DESELECT')
        temporary.select_set(True)
        bpy.context.view_layer.objects.active=temporary
        path=folder/(name+'.fbx')
        try:
            bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH'},use_mesh_modifiers=True,mesh_smooth_type='FACE',use_triangles=True,use_space_transform=False,axis_forward='Y',axis_up='Z',global_scale=1.,apply_unit_scale=True,apply_scale_options='FBX_SCALE_NONE',bake_space_transform=True,bake_anim=False,add_leaf_bones=False,path_mode='STRIP',use_custom_props=False,colors_type='LINEAR')
        finally:
            bpy.data.objects.remove(temporary,do_unlink=True)
            bpy.data.meshes.remove(temporary_mesh)
        exported=local[:,[1,0,2]]*100
        assets.append(dict(name=name,blender_object=authored.name,fbx=path.relative_to(ROOT).as_posix(),sha256=sha(path),anchor_local_m=anchor.tolist(),bounds_min_cm=exported.min(0).tolist(),bounds_max_cm=exported.max(0).tolist(),triangles=len(item['triangles']),section_id=item['section_id'],source_terrain=item['source_terrain'],source_support=item['source_support'],patches=item['patches'],finding=item['finding']))
    if before!=original_geometry():
        raise RuntimeError('Protected source geometry changed')
    manifest=dict(schema_version=1,version=version,input_hashes=inputs,prepared_source=pointer['source'],asset_root='/Game/StanleyPark/Seawall/RideCliffGaps/v_'+version,assets=assets,counts=dict(assets=len(assets),gap_spans=sum(len(a['patches']) for a in assets),prisms=sum(p['prisms'] for a in assets for p in a['patches'])),archive=archive.relative_to(ROOT).as_posix(),archive_sha256=digest,collision='none',source_geometry_unchanged=True,visual_acceptance=False,scope=source['scope'])
    path=folder/'manifest.json'
    path.write_text(json.dumps(manifest,indent=2)+'\n')
    bpy.ops.wm.save_as_mainfile(filepath=str(expected))
    (ROOT/'exports/m3-ride-cliff-gaps/latest.json').write_text(json.dumps(dict(manifest=path.relative_to(ROOT).as_posix(),sha256=sha(path)),indent=2)+'\n')
    return dict(version=version,manifest=path.relative_to(ROOT).as_posix(),assets=len(assets),triangles=sum(a['triangles'] for a in assets))


if __name__ in {'__main__','<run_path>'}:
    result=build()
