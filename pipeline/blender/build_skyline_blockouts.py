"""Author the bounded skyline in the live Blender scene. Never launch an app."""
import hashlib
import json
from pathlib import Path

import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
manifest='manifests/skyline-blockouts.json'
data=json.loads((ROOT/manifest).read_text(encoding='utf8'))
manifest_hash=hashlib.sha256((ROOT/manifest).read_bytes()).hexdigest()
for item in data['inputs']+data['meshes']:
    if hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()!=item['sha256']:
        raise RuntimeError('Skyline source or mesh changed: '+item['path'])

scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
collection=bpy.data.collections.get('SP_10_DistantSkyline')
if collection is None:
    collection=bpy.data.collections.new('SP_10_DistantSkyline');scene.collection.children.link(collection)
owner='skyline_blockouts_v1'
for obj in list(collection.objects):
    if obj.get('pipeline_owner')==owner:
        old=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if old.users==0:bpy.data.meshes.remove(old)

created=[]
for item in data['meshes']:
    with np.load(ROOT/item['path']) as package:
        vertices,faces,anchor=package['vertices'],package['faces'],package['anchor']
    mesh=bpy.data.meshes.new(item['name']);mesh.from_pydata(vertices.tolist(),[],faces.tolist());mesh.update()
    obj=bpy.data.objects.new(item['name'],mesh);collection.objects.link(obj);obj.location=anchor
    mat_name='M_Skyline_'+item['material'];mat=bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
    mat.diffuse_color=tuple(item['color']);mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Base Color'].default_value=tuple(item['color'])
    bsdf.inputs['Roughness'].default_value=.38 if item['material']=='glass' else .8
    mat.use_backface_culling=not item['two_sided'];mat['sp_two_sided']=bool(item['two_sided']);mesh.materials.append(mat)
    obj['pipeline_owner']=owner;obj['collision']='none';obj['release_accepted']=False
    obj['source_manifest']=manifest;obj['source_manifest_sha256']=manifest_hash
    obj['source_mesh_sha256']=item['sha256'];obj['source_id']='Current OSM footprint/parts; mixed recorded dimensions; M1 distant skyline'
    obj['part_triangle_ranges']=json.dumps(item['parts']);obj['model_scope']='Distant silhouette only; no city simulation'
    obj['accuracy_status']='Current map geometry with tagged, historic and estimated heights; per-part provenance retained'
    created.append(obj.name)

bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
result=dict(mesh_count=len(created),objects=created,triangles=data['check_summary']['triangles'],
    visual_acceptance=False,runtime_acceptance=False,scope=data['scope'])
(ROOT/'evidence/blender-skyline-build.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
