"""Separate seated visual form over the fixed measured boulder. No source edit."""
from pathlib import Path
import hashlib,json,runpy
import bpy,bmesh
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
OWNER='SP_M3WetsuitForm'
FORM_SOURCE='pipeline/blender/build_m3_shore_to_shore.py'
Form=runpy.run_path(str(ROOT/FORM_SOURCE),run_name='wetsuit_form_helpers')['Form']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def seated():
    # World offsets from the retained head centre. The legs bend over the west
    # boulder slope. No boulder points are moved to make room for the new form.
    g=Form();B=0
    g.ellipsoid((0,0,0),(.14,.145,.145),B,18,28)
    g.ellipsoid((-.105,.01,-.01),(.063,.045,.045),B,10,16)
    g.tube([(0,.005,-.16),(.015,.02,-.225)],[.069,.083],B,18)
    g.ellipsoid((.005,.025,-.28),(.20,.13,.16),B,18,26)
    g.ellipsoid((-.02,.08,-.41),(.19,.17,.13),B,16,24)
    # A thin mask and its strap stay on the forehead, all in bronze.
    for y in [-.06,.06]:g.ellipsoid((-.127,y,.055),(.026,.052,.037),B,10,16)
    g.tube([(-.125,-.11,.055),(.04,-.137,.055),(.14,0,.055),(.04,.137,.055),(-.125,.11,.055)],[.013]*5,B,10)
    chains=[([(-.09,-.025,-.39),(-.43,.30,-.43),(-.75,.61,-.78)],[.12,.105,.063]),
            ([(.10,.15,-.40),(-.25,.50,-.43),(-.57,.81,-.80)],[.12,.10,.063])]
    for points,radii in chains:
        g.tube(points,radii,B,22)
        x,y,z=points[-1]
        # Fin plate broadens away from the heel. Connected to the ankle.
        v=[(x+dx,y+dy,z+dz) for dz in [-.025,.025] for dx,dy in [(-.065,-.065),(.065,.035),(-.02,.46),(-.27,.29)]]
        g.part(v,[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],B)
    for points in [[(-.035,-.105,-.225),(-.24,-.08,-.36),(-.37,.24,-.40)],[(.04,.16,-.23),(-.09,.38,-.37),(-.24,.44,-.40)]]:
        g.tube(points,[.075,.062,.047],B,18);g.ellipsoid(points[-1],(.075,.06,.05),B,12,18)
    return g

def boulder_top(tri,xy):
    a=tri[:,0,:2];b=tri[:,1,:2]-a;c=tri[:,2,:2]-a;v=xy-a;det=b[:,0]*c[:,1]-b[:,1]*c[:,0];ok=abs(det)>1e-10
    u=np.divide(v[:,0]*c[:,1]-v[:,1]*c[:,0],det,out=np.zeros(len(tri)),where=ok);w=np.divide(b[:,0]*v[:,1]-b[:,1]*v[:,0],det,out=np.zeros(len(tri)),where=ok)
    hit=ok&(u>=-1e-7)&(w>=-1e-7)&(u+w<=1+1e-7);z=tri[:,0,2]+u*(tri[:,1,2]-tri[:,0,2])+w*(tri[:,2,2]-tri[:,0,2])
    return float(z[hit].max()) if hit.any() else None

def build():
    if Path(bpy.data.filepath).resolve()!=(ROOT/'blender/StanleyPark_Seawall.blend').resolve():raise RuntimeError('Open Seawall source')
    cfgpath='manifests/m3-wetsuit-form-settings.json';cfg=json.loads((ROOT/cfgpath).read_text());source=json.loads((ROOT/cfg['source_manifest']).read_text())
    rows=[r for r in source['assets'] if r['name'].startswith('SM_Wetsuit_')];rock=next(r for r in rows if r['name'].endswith('Boulder'));names=[r['name'] for r in rows if r!=rock]
    paths=[cfgpath,FORM_SOURCE,'pipeline/blender/build_m3_landmark_forms.py','pipeline/blender/build_m3_wetsuit_form.py','pipeline/blender/build_seawall_tree_library.py',cfg['source_manifest'],'evidence/m3-wetsuit-source-overlap.json']+[r['mesh_path'] for r in rows]
    inputs={p:sha(ROOT/p) for p in paths};version=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:12];folder=ROOT/'exports/m3-wetsuit-form'/version;manifest_path=folder/'manifest.json'
    if manifest_path.exists():raise RuntimeError('Immutable Wetsuit export exists')
    originals=[bpy.data.objects.get(n) for n in names]
    if any(o is None for o in originals):raise RuntimeError('Missing source body')
    scene=bpy.context.scene
    if abs(scene.unit_settings.scale_length-1)>1e-7:raise RuntimeError('Scene must use metres')
    collection=bpy.data.collections.new(OWNER+'_'+version);scene.collection.children.link(collection)
    helpers=runpy.run_path(str(ROOT/'pipeline/blender/build_seawall_tree_library.py'),run_name='wetsuit_export')
    m=bpy.data.materials.new('M_M3WetsuitForm_Bronze_'+version);m.use_nodes=True;m.diffuse_color=(*cfg['materials'][0]['rgb'],1)
    shader=m.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=m.diffuse_color;shader.inputs['Roughness'].default_value=.62;shader.inputs['Metallic'].default_value=.6
    g=seated();position=np.asarray(cfg['retained_head_centre_local_m']);d=np.load(ROOT/rock['mesh_path']);tri=d['vertices'][d['faces']]
    # Lift only skin that would still sit inside the source rock. This is a
    # small local fit of estimated anatomy; the measured head remains fixed.
    adjusted=0;maximum=0.
    for i,p in enumerate(g.vertices):
        world=np.asarray(p)+position;top=boulder_top(tri,world[:2]);lift=max(0,top+.015-world[2]) if top is not None else 0
        if lift>0:
            if p[2]>-.17:raise RuntimeError('Source head conflicts with boulder')
            adjusted+=1;maximum=max(maximum,lift);g.vertices[i]=(p[0],p[1],p[2]+lift)
    if maximum>.18:raise RuntimeError('Estimated pose requires excessive skin lift: '+str(maximum))
    obj=helpers['make_object']('SM_M3WetsuitForm_Seated_'+version,g,collection,[m],position.tolist());obj['pipeline_owner']=OWNER;obj['feature_id']='SP_girl_wetsuit';obj['collision']='none'
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    mod=obj.modifiers.new('Connected seated figure','REMESH');mod.mode='VOXEL';mod.voxel_size=.008;mod.use_smooth_shade=True;bpy.ops.object.modifier_apply(modifier=mod.name)
    mod=obj.modifiers.new('Bronze surface','SMOOTH');mod.factor=.4;mod.iterations=2;bpy.ops.object.modifier_apply(modifier=mod.name)
    mod=obj.modifiers.new('Figure budget','DECIMATE');mod.ratio=.4;bpy.ops.object.modifier_apply(modifier=mod.name)
    bm=bmesh.new();bm.from_mesh(obj.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));volume=bm.calc_volume(signed=True)
    if volume<=0:raise RuntimeError('Seated form has nonpositive volume')
    bm.to_mesh(obj.data);bm.free()
    for p in obj.data.polygons:p.material_index=0;p.use_smooth=True
    folder.mkdir(parents=True,exist_ok=True);item=helpers['export_object'](obj,folder,scene);item.update(feature_id='SP_girl_wetsuit',source_label='seated',position_local_m=position.tolist(),signed_volume_m3=volume)
    hidden=[dict(name=o.name,hide_render=o.hide_render,hide_viewport=o.hide_viewport,hide_set=o.hide_get()) for o in originals]
    manifest=dict(schema_version=1,owner=OWNER,version=version,input_hashes=inputs,settings=cfg,assets=[item],asset_root='/Game/StanleyPark/Seawall/WetsuitForm/v_'+version,hidden_originals=hidden,original_collision_unchanged=True,new_collision='none',skin_fit=dict(adjusted_vertices=adjusted,maximum_lift_m=maximum),visual_acceptance=False,geographic_accuracy_accepted=False)
    manifest_path.write_text(json.dumps(manifest,indent=2));(folder.parent/'latest.json').write_text(json.dumps(dict(manifest=manifest_path.relative_to(ROOT).as_posix(),sha256=sha(manifest_path)),indent=2))
    for obj in originals:obj.hide_render=True;obj.hide_set(True)
    return dict(version=version,forms=1,triangles=item['triangles'],manifest=str(manifest_path))
if __name__ in {'__main__','<run_path>'}:result=build()
