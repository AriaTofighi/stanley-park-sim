"""Add a separate, source-supported north viaduct and coastal gap layer.

Run in the coordinator's serial Blender slot. Never rebuild M1 bridge objects.
"""
from pathlib import Path
import hashlib,json,math,shutil
import bpy
import numpy as np
from mathutils import Matrix,Vector

ROOT=Path(__file__).resolve().parents[2]
OWNER='m3_north_approach'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))

def original_geometry(scene):
    rows=[]
    for obj in sorted(scene.objects,key=lambda o:o.name):
        if obj.type!='MESH' or not obj.name.startswith('SM_') or obj.get('pipeline_owner')==OWNER:continue
        points=np.asarray([tuple(obj.matrix_world@v.co) for v in obj.data.vertices],dtype='<f8')
        faces=[tuple(p.vertices) for p in obj.data.polygons]
        rows.append(dict(name=obj.name,sha256=hashlib.sha256(points.tobytes()+json.dumps(faces).encode()).hexdigest()))
    return rows

class Parts:
    def __init__(self,origin,axis,normal):self.vertices=[];self.faces=[];self.origin=origin;self.axis=axis;self.normal=normal
    def xyz(self,p):return self.origin+self.axis*p[0]+self.normal*p[1]+np.array([0.,0.,p[2]])
    def rings(self,rows):
        start=len(self.vertices);count=len(rows[0]);self.vertices.extend([self.xyz(p).tolist() for row in rows for p in row])
        self.faces.append(tuple(start+i for i in range(count-1,-1,-1)))
        for r in range(len(rows)-1):
            for i in range(count):
                j=(i+1)%count;self.faces.append((start+r*count+i,start+r*count+j,start+(r+1)*count+j,start+(r+1)*count+i))
        self.faces.append(tuple(start+(len(rows)-1)*count+i for i in range(count)))
    def beam(self,a,b,width,depth=None,sides=4):
        a,b=Vector(a),Vector(b);t=(b-a).normalized();reference=Vector((1,0,0)) if abs(t.x)<.8 else Vector((0,1,0));u=t.cross(reference).normalized();v=t.cross(u).normalized()
        offsets=[u*x*width*.5+v*y*(depth or width)*.5 for x,y in [(-1,-1),(1,-1),(1,1),(-1,1)]] if sides==4 else [(u*math.cos(t)+v*math.sin(t))*width*.5 for t in np.arange(sides)*2*math.pi/sides]
        self.rings([[list(p+o) for o in offsets] for p in [a,b]])
    def box(self,s0,s1,t0,t1,z0,z1):self.rings([[[s,t0,z0],[s,t1,z0],[s,t1,z1],[s,t0,z1]] for s in [s0,s1]])


def build():
    expected=ROOT/'blender/StanleyPark_Seawall.blend'
    if Path(bpy.data.filepath).resolve()!=expected.resolve():raise RuntimeError('Open the separate Seawall source')
    scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
    if scene.unit_settings.scale_length!=1:raise RuntimeError('Expected metre source')
    if bpy.context.object and bpy.context.object.mode!='OBJECT':raise RuntimeError('Leave edit mode')
    pointer=read(ROOT/'data/derived/m3-north-approach/latest.json');path=ROOT/pointer['source']
    if sha(path)!=pointer['sha256']:raise RuntimeError('North source manifest changed')
    source=read(path);cfg=source['settings'];bridge=read(ROOT/source['source_bridge_manifest']);dim=cfg['visual_member_estimates']
    for name,digest in source['input_hashes'].items():
        if sha(ROOT/name)!=digest:raise RuntimeError('North source changed: '+name)
    if sha(ROOT/source['foreshore']['path'])!=source['foreshore']['sha256']:raise RuntimeError('Foreshore source changed')
    before=original_geometry(scene)
    inputs={p:sha(ROOT/p) for p in ['pipeline/blender/build_m3_north_approach.py','data/derived/m3-north-approach/latest.json',pointer['source']]}
    inputs['scene_geometry_digest']=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()
    version=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:12];folder=ROOT/'exports/m3-north-approach'/version
    if (folder/'manifest.json').exists():raise RuntimeError('Immutable north approach export already exists')
    origin=np.array([*source['origin_local_m'],0.]);axis=np.array([*source['axis_unit'],0.]);normal=np.array([*source['transverse_unit'],0.])
    profile=source['profile'];stations=np.array([p['station_m'] for p in profile]);heights=np.array([p['height_m'] for p in profile])
    h=lambda s:float(np.interp(s,stations,heights))
    road=bpy.data.objects.get('SM_LionsGate_Road')
    if road is None:raise RuntimeError('Protected bridge road is absent')
    current=np.asarray([tuple(road.matrix_world@v.co) for v in road.data.vertices]);ss=(current-origin)@axis;end=ss.max();top=current[np.abs(ss-end)<.02,2].max()
    if abs(end-source['start_station_m'])>.02 or abs(top-heights[0])>.02:raise RuntimeError('Protected bridge endpoint differs from source')
    parts={k:Parts(origin,axis,normal) for k in ['Road','WalkWest','WalkEast','Steel','Concrete','Cables','Embankment','Foreshore']}
    road_half=cfg['roadway_width_m']*.5
    for kind,side in [('Road',0),('WalkWest',-1),('WalkEast',1)]:
        rows=[]
        for p in profile:
            s,z=p['station_m'],p['height_m'];left,right=(-road_half,road_half) if side==0 else (p['left_m'],-road_half) if side<0 else (road_half,p['right_m'])
            rows.append([[s,left,z-dim['deck_thickness_m']],[s,right,z-dim['deck_thickness_m']],[s,right,z],[s,left,z]])
        parts[kind].rings(rows)
    steel=parts['Steel'];concrete=parts['Concrete'];cables=parts['Cables']
    for t in [-cfg['footing_transverse_centres_m']*.5,cfg['footing_transverse_centres_m']*.5]:
        width=dim['girder_width_m'];rows=[]
        for p in profile:
            s,z=p['station_m'],p['height_m']-dim['deck_thickness_m'];rows.append([[s,t-width*.5,z-dim['girder_depth_m']],[s,t+width*.5,z-dim['girder_depth_m']],[s,t+width*.5,z],[s,t-width*.5,z]])
        steel.rings(rows)
    cable_fit=bridge['cable_fits'][-1];cable_start=float(cable_fit['end_m']);cable_top=float(np.polyval(cable_fit['polynomial'],cable_start))
    # Cable bent plus 24 source-count ordinary bents. Fine member dimensions
    # and individual bent stations are explicit visual estimates.
    for row in source['supports']:
        s=row['station_m'];deck=row['deck_height_m'];top=cable_top if row['index']==0 else deck-dim['deck_thickness_m']-dim['girder_depth_m']
        floors=[]
        for foot in row['feet']:
            t=foot['transverse_m'];ground=foot['position_local_m'][2];floors.append(ground+.4)
            concrete.box(s-cfg['footing_length_estimate_m']*.5,s+cfg['footing_length_estimate_m']*.5,t-cfg['footing_width_m']*.5,t+cfg['footing_width_m']*.5,ground-cfg['footing_embedment_m'],ground+.4)
            steel.beam([s,t,ground+.35],[s,t,top],dim['column_width_m'])
        bottom=max(floors);levels=np.linspace(bottom,top,max(2,int(math.ceil((top-bottom)/dim['bent_level_max_m']))+1))
        half=cfg['footing_transverse_centres_m']*.5
        for z in levels:steel.beam([s,-half,z],[s,half,z],.38)
        for lo,hi in zip(levels[:-1],levels[1:]):
            for sign in [-1,1]:steel.beam([s,sign*half,lo],[s,-sign*half,hi],dim['brace_width_m'])
        # Crosshead seats the two plate girders.
        steel.beam([s,-half-.7,deck-dim['deck_thickness_m']-dim['girder_depth_m']],[s,half+.7,deck-dim['deck_thickness_m']-dim['girder_depth_m']],.6)
    for a,b in cfg['double_bent_pairs_1based']:
        ra,rb=source['supports'][a],source['supports'][b];sa,sb=ra['station_m'],rb['station_m'];bottom=max(f['position_local_m'][2] for row in [ra,rb] for f in row['feet'])+.4;top=min(ra['deck_height_m'],rb['deck_height_m'])-2.1
        levels=np.linspace(bottom,top,max(2,int(math.ceil((top-bottom)/dim['bent_level_max_m']))+1))
        for sign in [-1,1]:
            t=sign*cfg['footing_transverse_centres_m']*.5
            for z in levels:steel.beam([sa,t,z],[sb,t,z],.3)
            for lo,hi in zip(levels[:-1],levels[1:]):
                steel.beam([sa,t,lo],[sb,t,hi],dim['brace_width_m']);steel.beam([sa,t,hi],[sb,t,lo],dim['brace_width_m'])
    # Low north anchorage joins the source cable endpoints to the source-shown
    # anchor area between ordinary bents 3 and 4.
    anchor_a,anchor_b=source['supports'][3],source['supports'][4];anchor_s=(anchor_a['station_m']+anchor_b['station_m'])*.5
    anchor_ground=min(f['position_local_m'][2] for row in [anchor_a,anchor_b] for f in row['feet']);anchor_top=anchor_ground+dim['anchor_block_height_m']
    concrete.box(anchor_a['station_m']-3,anchor_b['station_m']+3,-dim['anchor_block_width_m']*.5,dim['anchor_block_width_m']*.5,anchor_ground-1.5,anchor_top)
    for sign in [-1,1]:
        t=sign*bridge['cable_half_width_m'];line=np.linspace(cable_start,anchor_s,32)
        for a,b in zip(line[:-1],line[1:]):
            za=cable_top+(anchor_top-cable_top)*(a-cable_start)/(anchor_s-cable_start);zb=cable_top+(anchor_top-cable_top)*(b-cable_start)/(anchor_s-cable_start)
            cables.beam([a,t,za],[b,t,zb],bridge['simplified_dimensions']['cable_radius_m']*2,sides=6)
    # Simplified source-width edge rails. Original bridge rails are untouched.
    for side in ['left_m','right_m']:
        for a,b in zip(profile[:-1],profile[1:]):
            for lift in [.55,dim['railing_height_m']]:steel.beam([a['station_m'],a[side],a['height_m']+lift],[b['station_m'],b[side],b['height_m']+lift],dim['rail_width_m'])
        for s in np.arange(stations[0],stations[-1]+.001,dim['post_spacing_m']):
            t=float(np.interp(s,stations,[p[side] for p in profile]));steel.beam([s,t,h(s)],[s,t,h(s)+dim['railing_height_m']],dim['rail_width_m'])
    # North abutment and bounded source-height embankment apron.
    end=source['end_station_m'];end_ground=heights[-1]-cfg['north_embankment_height_m'];half=cfg['deck_total_width_m']*.5
    concrete.box(end-.8,end+.8,-half,half,end_ground-.2,heights[-1]-.03)
    apron=source['embankment_apron'];embank=parts['Embankment'];rows=[]
    for row in apron:
        s=row['station_m'];rows.append([[s,row['toe_left_m'],row['left_ground_m']],[s,-half,row['top_m']],[s,half,row['top_m']],[s,row['toe_right_m'],row['right_ground_m']]])
    for a,b in zip(rows[:-1],rows[1:]):
        start=len(embank.vertices);embank.vertices.extend([embank.xyz(v).tolist() for v in a+b])
        for j in range(3):embank.faces.append((start+j,start+j+4,start+j+5,start+j+1))
    terrain=np.load(ROOT/source['foreshore']['path']);parts['Foreshore'].vertices=terrain['vertices'].tolist();parts['Foreshore'].faces=[tuple(f) for f in terrain['faces']]
    bpy.ops.wm.save_as_mainfile(filepath=str(expected));digest=sha(expected);archive=ROOT/'blender/archive'/('StanleyPark_Seawall_'+digest[:12]+'.blend');archive.parent.mkdir(exist_ok=True)
    if not archive.exists():shutil.copy2(expected,archive)
    if sha(archive)!=digest:raise RuntimeError('Blender archive differs')
    collection=bpy.data.collections.new('SP_M3NorthApproach_'+version);scene.collection.children.link(collection);folder.mkdir(parents=True,exist_ok=True)
    palette={'Road':(.15,.16,.16),'WalkWest':(.48,.48,.44),'WalkEast':(.48,.48,.44),'Steel':(.09,.26,.20),'Concrete':(.45,.42,.35),'Cables':(.40,.44,.42),'Embankment':(.17,.24,.23),'Foreshore':(.17,.24,.23)}
    reference={'Road':'SM_LionsGate_Road','WalkWest':'SM_LionsGate_WalkWest','WalkEast':'SM_LionsGate_WalkEast','Steel':'SM_LionsGate_Towers','Concrete':'SM_LionsGate_NorthFootingReview','Cables':'SM_LionsGate_MainCables','Embankment':'SM_Region_','Foreshore':'SM_Region_'}
    assets=[];rotation=Matrix.Rotation(-math.pi/2,4,'Z')
    for kind,part in parts.items():
        values=np.asarray(part.vertices);anchor=(values.min(0)+values.max(0))*.5;local=values-anchor;name='SM_M3NorthViaduct_'+kind
        mesh=bpy.data.meshes.new(name+'_'+version);mesh.from_pydata(local.tolist(),[],part.faces);mesh.update()
        mat=bpy.data.materials.new('M_M3NorthPreview_'+kind+'_'+version);mat.diffuse_color=(*palette[kind],1);mesh.materials.append(mat)
        if kind in ['Embankment','Foreshore']:
            colors=mesh.color_attributes.new(name='Color',type='FLOAT_COLOR',domain='POINT');colors.data.foreach_set('color',np.tile([*palette[kind],1],(len(local),1)).astype(np.float32).ravel())
            for poly in mesh.polygons:poly.use_smooth=True
        obj=bpy.data.objects.new(name+'_'+version,mesh);collection.objects.link(obj);obj.location=anchor;obj['pipeline_owner']=OWNER;obj['collision']='none';obj['representation']='Source-supported visual interpretation; dimensions and limits in manifest'
        temp_mesh=mesh.copy();temp_mesh.transform(rotation);temporary=bpy.data.objects.new('Export_'+name,temp_mesh);scene.collection.objects.link(temporary)
        bpy.ops.object.select_all(action='DESELECT');temporary.select_set(True);bpy.context.view_layer.objects.active=temporary;fbx=folder/(name+'.fbx')
        try:
            bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},use_mesh_modifiers=True,mesh_smooth_type='FACE',use_triangles=True,use_space_transform=False,axis_forward='Y',axis_up='Z',global_scale=1.0,apply_unit_scale=True,apply_scale_options='FBX_SCALE_NONE',bake_space_transform=True,bake_anim=False,add_leaf_bones=False,path_mode='STRIP',use_custom_props=False,colors_type='LINEAR')
        finally:bpy.data.objects.remove(temporary,do_unlink=True);bpy.data.meshes.remove(temp_mesh)
        converted=local[:,[1,0,2]]*100
        assets.append(dict(name=name,kind=kind,blender_object=obj.name,fbx=fbx.relative_to(ROOT).as_posix(),sha256=sha(fbx),anchor_local_m=anchor.tolist(),bounds_min_cm=converted.min(0).tolist(),bounds_max_cm=converted.max(0).tolist(),triangles=sum(len(f)-2 for f in part.faces),material_reference_actor=reference[kind],vertex_colors=kind in ['Embankment','Foreshore']))
    for old in bpy.data.collections:
        if old!=collection and old.name.startswith('SP_M3NorthApproach_'):old.hide_viewport=old.hide_render=True
    if before!=original_geometry(scene):raise RuntimeError('Original scene geometry changed')
    manifest=dict(schema_version=1,version=version,input_hashes=inputs,prepared_source=pointer['source'],prepared_source_sha256=pointer['sha256'],asset_root='/Game/StanleyPark/Seawall/NorthApproach/v_'+version,assets=assets,source_geometry=before,archive=archive.relative_to(ROOT).as_posix(),archive_sha256=digest,source_length_m=cfg['viaduct_length_m'],span_count=cfg['span_count'],ordinary_bents=cfg['ordinary_bents'],cable_bents=1,profile_endpoint_check=dict(source_station_m=source['start_station_m'],source_height_m=heights[0],actual_station_m=float(ss.max()),actual_height_m=float(current[np.abs(ss-ss.max())<.02,2].max())),source_settings=cfg,foreshore=source['foreshore'],collision='none',source_geometry_unchanged=True,visual_acceptance=False)
    out=folder/'manifest.json';out.write_text(json.dumps(manifest,indent=2))
    bpy.ops.wm.save_as_mainfile(filepath=str(expected));(ROOT/'exports/m3-north-approach/latest.json').write_text(json.dumps(dict(manifest=out.relative_to(ROOT).as_posix(),sha256=sha(out)),indent=2))
    return dict(version=version,manifest=str(out),assets=len(assets),triangles=sum(a['triangles'] for a in assets),length_m=cfg['viaduct_length_m'],ordinary_bents=24,cable_bents=1)

if __name__ in {'__main__','<run_path>'}:result=build()
