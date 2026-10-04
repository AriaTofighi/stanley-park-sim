"""Stage editable M1 grounds. The coordinator runs and inspects this in Blender."""
from pathlib import Path
import hashlib
import json
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OWNER='m1_ground_spaces_v1'
path=ROOT/'manifests/ground-space-blockouts.json'
record=json.loads(path.read_text(encoding='utf8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for row in record['source_inputs']+record['terrain_inputs']+record['exclusion_mesh_inputs']+record['meshes']:
    if sha(ROOT/row['path'])!=row['sha256']:
        raise RuntimeError('Ground-space source changed; regenerate: '+row['path'])
scene=bpy.data.scenes['StanleyPark_M1']
bpy.context.window.scene=scene
collection=bpy.data.collections.get('SP_08_NamedGroundSpaces')
if collection is None:
    collection=bpy.data.collections.new('SP_08_NamedGroundSpaces');scene.collection.children.link(collection)
for obj in list(collection.objects):
    if obj.get('pipeline_owner')==OWNER:
        data=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if data.users==0:bpy.data.meshes.remove(data)
created=[]
for row in record['meshes']:
    with np.load(ROOT/row['path']) as package:
        v,f,anchor=package['vertices'],package['faces'],package['anchor']
    if not np.isfinite(v).all() or f.min()<0 or f.max()>=len(v):raise ValueError(row['name'])
    mesh=bpy.data.meshes.new(row['name']);mesh.from_pydata(v.tolist(),[],f.tolist());mesh.update()
    obj=bpy.data.objects.new(row['name'],mesh);collection.objects.link(obj);obj.location=anchor
    name='M_Ground_'+row['material_role']
    material=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes=True;material.diffuse_color=row['material_color']
    bsdf=material.node_tree.nodes['Principled BSDF'];bsdf.inputs['Base Color'].default_value=row['material_color']
    bsdf.inputs['Roughness'].default_value=.32 if row['material_role']=='pond_water' else .9
    mesh.materials.append(material)
    for key in ['component_id','feature_id','m1_group','material_role','contact_surface','visual_lift_m']:obj[key]=row[key]
    obj['pipeline_owner']=OWNER;obj['collision']='none'
    obj['source_id']=json.dumps(row['source'],ensure_ascii=False)
    obj['source_manifest']=path.relative_to(ROOT).as_posix();obj['source_manifest_sha256']=sha(path)
    obj['source_mesh_sha256']=row['sha256'];obj['licence']=record['licence']
    obj['attribution']=json.dumps(record['attribution'],ensure_ascii=False)
    obj['absolute_accuracy_accepted']=False;obj['release_accepted']=False
    created.append(obj.name)
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
(ROOT/'evidence/ground-spaces/blender-stage.json').write_text(json.dumps(dict(mesh_objects=created,
    triangles=sum(r['triangles'] for r in record['meshes']),visual_inspection='pending',collision='none',
    full_m1_groups_complete=False,release_accepted=False),indent=2)+'\n',encoding='utf8')
