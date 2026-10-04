"""Author distant terminal forms in live Blender; never launches an app."""
import hashlib,json
from pathlib import Path
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
path=ROOT/'manifests/northshore-blockouts.json';data=json.loads(path.read_text(encoding='utf8'))
manifest_hash=hashlib.sha256(path.read_bytes()).hexdigest()
for item in data['inputs']+data['meshes']:
    if hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()!=item['sha256']:
        raise RuntimeError('North Shore source changed: '+item['path'])
scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
collection=bpy.data.collections.get('SP_11_NorthShoreIndustry')
if collection is None:
    collection=bpy.data.collections.new('SP_11_NorthShoreIndustry');scene.collection.children.link(collection)
owner='northshore_blockouts_v1'
for obj in list(collection.objects):
    if obj.get('pipeline_owner')==owner:
        old=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if old.users==0:bpy.data.meshes.remove(old)
created=[]
for item in data['meshes']:
    with np.load(ROOT/item['path']) as package:v,f,anchor=package['vertices'],package['faces'],package['anchor']
    mesh=bpy.data.meshes.new(item['name']);mesh.from_pydata(v.tolist(),[],f.tolist());mesh.update()
    obj=bpy.data.objects.new(item['name'],mesh);collection.objects.link(obj);obj.location=anchor
    name='M_NorthShore_'+item['material'];mat=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color=tuple(item['color']);mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Base Color'].default_value=tuple(item['color']);bsdf.inputs['Roughness'].default_value=.8
    mesh.materials.append(mat);obj['pipeline_owner']=owner;obj['collision']='none';obj['release_accepted']=False
    obj['source_manifest']='manifests/northshore-blockouts.json';obj['source_manifest_sha256']=manifest_hash
    obj['source_mesh_sha256']=item['sha256'];obj['source_id']='OSM mapped terminal forms plus recorded primary dimensions and M1 estimates'
    obj['part_triangle_ranges']=json.dumps(item['parts']);obj['accuracy_status']='Distant blockout; shared terrain base and estimated members/poses'
    created.append(obj.name)
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
result=dict(objects=created,mesh_count=len(created),triangles=data['check_summary']['triangles'],
    visual_acceptance=False,runtime_acceptance=False,collision='none')
(ROOT/'evidence/blender-northshore-build.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
