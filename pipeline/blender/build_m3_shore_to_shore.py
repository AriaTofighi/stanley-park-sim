"""Separate three-person visual layer. Run only in the serial Blender slot.

Old source mesh coordinates and collision are untouched. The caller saves.
"""
from pathlib import Path
import hashlib, json, math, runpy
import bpy
import bmesh
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OWNER='SP_M3ShoreToShore'
BASE='pipeline/blender/build_m3_landmark_forms.py'
BaseForm=runpy.run_path(str(ROOT/BASE),run_name='shore_form_geometry')['Form']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

class Form(BaseForm):
    def part(self,vertices,faces,slot):
        # Each helper part is closed. Choose outward winding from signed volume
        # about its own centre, before any translation or voxel union.
        vertices=np.asarray(vertices,float);local=vertices-vertices.mean(0)
        volume=0.
        for face in faces:
            for i in range(1,len(face)-1):
                a,b,c=local[[face[0],face[i],face[i+1]]]
                volume+=float(np.dot(a,np.cross(b,c)))/6
        if abs(volume)<1e-10:raise RuntimeError('Degenerate closed body part')
        if volume<0:faces=[tuple(reversed(f)) for f in faces]
        super().part(vertices,faces,slot)

def person(garment,index):
    g=Form();B=0
    for side in [-1,1]:
        g.ellipsoid((side*.16,-.045,.10),(.13,.24,.105),B,12,20)
        g.tube([(side*.16,0,.13),(side*.15,0,.56),(side*.14,0,1.02)],[.105,.12,.15],B,18)
    g.ellipsoid((0,0,1.03),(.30,.22,.24),B,14,24)
    g.ellipsoid((0,0,1.38),(.31,.22,.38),B,14,24)
    if garment=='long':
        # A continuous flared garment joins the hips and covers the upper legs.
        g.tube([(0,0,.26),(0,0,.54),(0,0,.86),(0,0,1.12)],[.32,.30,.265,.255],B,32)
    else:
        g.box((0,.035,.98),(.58,.33,.66),B,.87)
        for s in [-1,1]:g.tube([(s*.22,-.16,1.66),(s*.08,-.225,1.31),(s*.15,-.22,1.15)],[.03,.035,.025],B,10)
    g.tube([(0,0,1.60),(0,0,1.80)],[.105,.105],B,18)
    g.ellipsoid((0,-.005,1.89),(.16,.145,.19),B,16,24)
    g.ellipsoid((0,-.13,1.875),(.055,.06,.06),B,12,18)
    for s in [-1,1]:
        g.ellipsoid((s*.145,0,1.89),(.035,.03,.055),B,10,16)
        shoulder=(s*.275,0,1.55);elbow=(s*.39,-.065,1.25)
        hand=(s*.095,-.275,1.16+(index==1 and s==1)*.13)
        g.ellipsoid(shoulder,(.145,.15,.16),B,12,20)
        g.tube([shoulder,elbow,hand],[.13,.10,.065],B,18)
        g.ellipsoid(hand,(.085,.065,.08),B,12,20)
    return g

def build():
    if Path(bpy.data.filepath).resolve()!=(ROOT/'blender/StanleyPark_Seawall.blend').resolve():raise RuntimeError('Open the Seawall source')
    settings='manifests/m3-shore-to-shore-settings.json';cfg=json.loads((ROOT/settings).read_text())
    source=json.loads((ROOT/cfg['source_manifest']).read_text());assets={r['name']:r for r in source['assets']}
    names=['SM_ShoreToShore_'+part+'_'+str(i) for i in range(3) for part in ['FigureHead','FigureBody']]
    paths=[BASE,'pipeline/blender/build_m3_shore_to_shore.py','pipeline/blender/build_seawall_tree_library.py',settings,cfg['source_manifest'],'manifests/named-totem-sculptures-survey.json']+[assets[n]['mesh_path'] for n in names]
    inputs={p:sha(ROOT/p) for p in paths};version=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:12]
    folder=ROOT/'exports/m3-shore-to-shore'/version;manifest_path=folder/'manifest.json'
    if manifest_path.exists():raise RuntimeError('Immutable Shore to Shore export exists')
    originals=[bpy.data.objects.get(n) for n in names]
    if any(o is None for o in originals):raise RuntimeError('Missing source figure')
    scene=bpy.context.scene
    if abs(scene.unit_settings.scale_length-1)>1e-7:raise RuntimeError('Scene must use metres')
    helpers=runpy.run_path(str(ROOT/'pipeline/blender/build_seawall_tree_library.py'),run_name='shore_export')
    collection=bpy.data.collections.new(OWNER+'_'+version);scene.collection.children.link(collection)
    m=bpy.data.materials.new('M_M3ShoreToShore_Bronze_'+version);m.use_nodes=True;m.diffuse_color=(*cfg['materials'][0]['rgb'],1)
    shader=m.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=m.diffuse_color;shader.inputs['Roughness'].default_value=.64;shader.inputs['Metallic'].default_value=.6
    folder.mkdir(parents=True,exist_ok=True);exports=[]
    centre=np.asarray(next(f['measured']['centre_local_m'] for f in source['features'] if f['id']=='SP_shore_to_shore'))
    for spec in cfg['figures']:
        i=spec['index'];r=assets['SM_ShoreToShore_FigureHead_'+str(i)];head=(np.asarray(r['bounds_min_m'])+r['bounds_max_m'])/2
        g=person(spec['garment'],i);outward=head[:2]-centre;angle=math.atan2(outward[1],outward[0])+math.pi/2;c,s=math.cos(angle),math.sin(angle)
        g.vertices=[(x*c-y*s,x*s+y*c,z) for x,y,z in g.vertices];position=[float(head[0]),float(head[1]),float(head[2]-1.89)]
        obj=helpers['make_object']('SM_M3ShoreToShore_Figure'+str(i)+'_'+version,g,collection,[m],position)
        obj['pipeline_owner']=OWNER;obj['feature_id']='SP_shore_to_shore';obj['collision']='none'
        bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
        mod=obj.modifiers.new('Connected bronze body','REMESH');mod.mode='VOXEL';mod.voxel_size=.016;mod.use_smooth_shade=True;bpy.ops.object.modifier_apply(modifier=mod.name)
        mod=obj.modifiers.new('Bronze surface','SMOOTH');mod.factor=.5;mod.iterations=2;bpy.ops.object.modifier_apply(modifier=mod.name)
        mod=obj.modifiers.new('Body budget','DECIMATE');mod.ratio=.35;bpy.ops.object.modifier_apply(modifier=mod.name)
        bm=bmesh.new();bm.from_mesh(obj.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));volume=bm.calc_volume(signed=True)
        if volume<=0:raise RuntimeError('Body has nonpositive signed volume')
        bm.to_mesh(obj.data);bm.free()
        for p in obj.data.polygons:p.material_index=0;p.use_smooth=True
        item=helpers['export_object'](obj,folder,scene);item.update(feature_id='SP_shore_to_shore',source_label='figure_'+str(i),position_local_m=position,signed_volume_m3=volume,source_head_centre_local_m=head.tolist());exports.append(item)
    hidden=[dict(name=o.name,hide_render=o.hide_render,hide_viewport=o.hide_viewport,hide_set=o.hide_get()) for o in originals]
    manifest=dict(schema_version=1,owner=OWNER,version=version,input_hashes=inputs,settings=cfg,assets=exports,asset_root='/Game/StanleyPark/Seawall/ShoreToShore/v_'+version,hidden_originals=hidden,original_collision_unchanged=True,new_collision='none',visual_acceptance=False,geographic_accuracy_accepted=False)
    manifest_path.write_text(json.dumps(manifest,indent=2));(folder.parent/'latest.json').write_text(json.dumps(dict(manifest=manifest_path.relative_to(ROOT).as_posix(),sha256=sha(manifest_path)),indent=2))
    for obj in originals:obj.hide_render=True;obj.hide_set(True)
    return dict(version=version,forms=len(exports),triangles=sum(a['triangles'] for a in exports),manifest=str(manifest_path))
if __name__ in {'__main__','<run_path>'}:result=build()
