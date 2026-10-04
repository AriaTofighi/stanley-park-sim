"""Coordinator stage for the finite public sites and two low water-park forms."""
from pathlib import Path
import hashlib,json
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OWNER='m1_site_completions_v1'
scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
collection=bpy.data.collections.get('SP_08_SiteCompletions')
if collection is None:collection=bpy.data.collections.new('SP_08_SiteCompletions');scene.collection.children.link(collection)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
records=[]
for relative in ['manifests/site-completion-blockouts.json','manifests/waterpark-low-forms.json']:
    path=ROOT/relative;record=json.loads(path.read_text(encoding='utf8'))
    for row in record['source_inputs']+record['terrain_inputs']+record['exclusion_mesh_inputs']+record['meshes']:
        if sha(ROOT/row['path'])!=row['sha256']:raise RuntimeError('Changed site source: '+row['path'])
    records.append((path,record))
for obj in list(collection.objects):
    if obj.get('pipeline_owner')==OWNER:
        data=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if data.users==0:bpy.data.meshes.remove(data)
created=[]
for path,record in records:
    for row in record['meshes']:
        with np.load(ROOT/row['path'])as p:v,f,anchor=p['vertices'],p['faces'],p['anchor']
        mesh=bpy.data.meshes.new(row['name']);mesh.from_pydata(v.tolist(),[],f.tolist());mesh.update()
        obj=bpy.data.objects.new(row['name'],mesh);collection.objects.link(obj);obj.location=anchor
        name='M_Site_'+row['material_role']+('_'+row['name']if row['material_role']=='play_form'else'')
        mat=bpy.data.materials.get(name)or bpy.data.materials.new(name);mat.use_nodes=True;mat.diffuse_color=row['material_color']
        bsdf=mat.node_tree.nodes['Principled BSDF'];bsdf.inputs['Base Color'].default_value=row['material_color'];bsdf.inputs['Roughness'].default_value=.35 if row['material_role']=='pond_water'else .9
        mesh.materials.append(mat)
        for key in ['component_id','feature_id','m1_group','material_role','contact_surface','visual_lift_m']:obj[key]=row[key]
        obj['pipeline_owner']=OWNER;obj['source_id']=json.dumps(row['source'],ensure_ascii=False)
        obj['source_manifest']=path.relative_to(ROOT).as_posix();obj['source_manifest_sha256']=sha(path);obj['source_mesh_sha256']=row['sha256']
        obj['licence']=record['licence'];obj['attribution']=json.dumps(record['attribution'],ensure_ascii=False)
        obj['collision']=row['collision']if isinstance(row['collision'],str)else'none'
        obj['release_accepted']=False;obj['absolute_accuracy_accepted']=False;created.append(obj.name)
links=json.loads((ROOT/'manifests/m1-existing-site-linkage.json').read_text(encoding='utf8'))
tagged=[];missing=[]
for link in links['links']:
    names=[r['name']for r in link.get('existing_terrain',[])]+[r['name']for r in link.get('existing_canopy',[])]+[r['object_name']for r in link.get('existing_building_candidates',[])]
    for name in names:
        obj=bpy.data.objects.get(name)
        if obj is None:missing.append(name);continue
        ids=json.loads(obj.get('m1_named_site_ids','[]'))
        if link['feature_id']not in ids:ids.append(link['feature_id'])
        obj['m1_named_site_ids']=json.dumps(ids);tagged.append(name)
bpy.context.view_layer.update();bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
target=ROOT/'evidence/site-completions/blender-stage.json';target.parent.mkdir(parents=True,exist_ok=True)
target.write_text(json.dumps(dict(mesh_objects=created,existing_objects_tagged=sorted(set(tagged)),missing_existing_objects=sorted(set(missing)),
    visual_inspection='pending',release_accepted=False),indent=2)+'\n',encoding='utf8')
