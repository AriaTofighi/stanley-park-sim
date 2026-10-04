"""Author exact terrain/facility boundary skins. Run through live Blender MCP."""
import hashlib
import json
from pathlib import Path
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
manifest='manifests/lumberman-facility-closures.json'
data=json.loads((ROOT/manifest).read_text(encoding='utf8'))
for row in data['inputs']+data['meshes']:
    if hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest()!=row['sha256']:
        raise ValueError('Changed Lumberman closure input: '+row['path'])
scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
collection=bpy.data.collections.get('SP_06_LumbermanFacilityClosures')
if collection is None:
    collection=bpy.data.collections.new('SP_06_LumbermanFacilityClosures');scene.collection.children.link(collection)
owner='lumberman_facility_closures_v1'
for obj in list(collection.objects):
    if obj.get('pipeline_owner')==owner:
        mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
mat=bpy.data.materials.get('M_LumbermanFacility_BoundaryStone') or bpy.data.materials.new('M_LumbermanFacility_BoundaryStone')
mat.diffuse_color=(.39,.4,.35,1);mat.use_nodes=True
mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=mat.diffuse_color
mat.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.8
mat['sp_two_sided']=True;mat.use_backface_culling=False
created=[]
for row in data['meshes']:
    with np.load(ROOT/row['path']) as package:
        mesh=bpy.data.meshes.new(row['name']);mesh.from_pydata(package['vertices'].tolist(),[],package['faces'].tolist());mesh.update()
        obj=bpy.data.objects.new(row['name'],mesh);collection.objects.link(obj);obj.location=package['anchor']
    mesh.materials.append(mat)
    for key,value in dict(pipeline_owner=owner,collision=row['collision'],source_id=manifest,
        source_mesh_sha256=row['sha256'],release_accepted=False,
        scope='Exact exported terrain to source-derived structural intervals; development boundary closure').items():
        obj[key]=value
    created.append(obj.name)
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
result=dict(mesh_count=len(created),objects=created,geometry_checks=data['checks'],
    visual_acceptance=False,runtime_acceptance=False)
(ROOT/'evidence/blender-lumberman-closures-build.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
