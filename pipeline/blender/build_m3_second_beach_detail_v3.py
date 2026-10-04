"""Second Beach detail v3: remove full envelope quads at the open canopy."""
from pathlib import Path
import hashlib
import json
import runpy
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[2]
OWNER='SP_M3SecondBeachDetail'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def inside(point,polygon):
    x,y=point;hit=False
    for a,b in zip(polygon,np.roll(polygon,-1,axis=0)):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:hit=not hit
    return hit

def beam(g,a,b,width,height,slot):
    a=np.array(a);b=np.array(b);d=b-a;d[2]=0;d/=np.linalg.norm(d);n=np.array([-d[1],d[0],0])*width/2
    z=np.array([0,0,height/2])
    g.part([a-n-z,a+n-z,b+n-z,b-n-z,a-n+z,a+n+z,b+n+z,b-n+z],
        [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],slot)

def build():
    if Path(bpy.data.filepath).resolve()!=(ROOT/'blender/StanleyPark_Seawall.blend').resolve():raise RuntimeError('Open separate Seawall source')
    scene=bpy.context.scene
    if abs(scene.unit_settings.scale_length-1)>1e-7:raise RuntimeError('Metre scene required')
    cfg=json.loads((ROOT/'manifests/m3-second-beach-detail-settings.json').read_text())
    source_names=cfg['source_walls']+[cfg['source_roof']]
    sources={name:bpy.data.objects.get(name) for name in source_names}
    if any(o is None or o.type!='MESH' for o in sources.values()):raise RuntimeError('Missing measured facility source')
    records=[]
    for name,obj in sources.items():
        vertices=np.array([tuple(obj.matrix_world@v.co) for v in obj.data.vertices],dtype='<f8');faces=[tuple(p.vertices) for p in obj.data.polygons]
        records.append(dict(name=name,sha256=hashlib.sha256(vertices.tobytes()+json.dumps(faces).encode()).hexdigest()))
    paths=['pipeline/blender/build_m3_second_beach_detail_v3.py','pipeline/blender/build_m3_landmark_forms.py',
        'pipeline/blender/build_seawall_tree_library.py','manifests/m3-second-beach-detail-settings.json',
        'manifests/named-building-blockouts.json','data/derived/paved-circuit-runtime.json']+cfg['reference_files']
    inputs={p:sha(ROOT/p) for p in paths}
    version=hashlib.sha256(json.dumps(dict(inputs=inputs,geometry=records),sort_keys=True).encode()).hexdigest()[:12]
    folder=ROOT/'exports/m3-second-beach-detail'/version
    if (folder/'manifest.json').exists():raise RuntimeError('Immutable facility detail export exists')
    Form=runpy.run_path(str(ROOT/'pipeline/blender/build_m3_landmark_forms.py'),run_name='second_beach_primitives')['Form']
    helpers=runpy.run_path(str(ROOT/'pipeline/blender/build_seawall_tree_library.py'),run_name='second_beach_export')
    roof=sources[cfg['source_roof']]
    rv=[tuple(roof.matrix_world@v.co) for v in roof.data.vertices];rf=[tuple(p.vertices) for p in roof.data.polygons]
    roof_tree=BVHTree.FromPolygons(rv,rf)
    gv=[];gf=[]
    for obj in scene.objects:
        if obj.type!='MESH' or not obj.name.startswith(('SM_Terrain_','SM_Pedestrian_')):continue
        points=np.array([tuple(obj.matrix_world@v.co) for v in obj.data.vertices])
        if np.any(points[:,:2].max(0)<[-600,-810]) or np.any(points[:,:2].min(0)>[-520,-725]):continue
        start=len(gv);gv.extend(points.tolist());gf.extend(tuple(start+i for i in p.vertices) for p in obj.data.polygons)
    ground=BVHTree.FromPolygons(gv,gf)
    curve=np.array(cfg['canopy_outer_curve_local_xy_m']);normals=[]
    for i,p in enumerate(curve):
        tangent=curve[min(i+1,len(curve)-1)]-curve[max(i-1,0)];tangent/=np.linalg.norm(tangent)
        normals.append(np.array([-tangent[1],tangent[0]]))
    normals=np.array(normals);inner=curve+normals*cfg['canopy_depth_m']
    # Source walls are estimated roof-boundary extrusions. Only the open canopy
    # strip is removed from new copies; measured roof data remain visible.
    cut=np.concatenate([curve-normals*1.2,(curve+normals*(cfg['canopy_depth_m']-.2))[::-1]])
    origin=np.array([-560.,-770.,0.]);pending=[];counts={};cut_groups_by_name={}
    for name in cfg['source_walls']:
        obj=sources[name];vertices=np.array([tuple(obj.matrix_world@v.co) for v in obj.data.vertices]);g=Form();kept=[];removed=0
        cut_groups=set()
        for p in obj.data.polygons:
            face=tuple(p.vertices);groups={i//4 for i in face}
            if len(groups)!=1:raise RuntimeError('Source envelope no longer has independent four-vertex wall quads')
            if inside(vertices[list(face),:2].mean(0),cut):cut_groups.update(groups)
        cut_groups_by_name[name]=cut_groups
        for p in obj.data.polygons:
            face=tuple(p.vertices)
            if face[0]//4 in cut_groups:removed+=1
            else:kept.append(face)
        g.part(vertices-origin,kept,0);pending.append((name.replace('SM_Named_SecondPoolFacilities_',''),g));counts[name]=dict(kept_polygons=len(kept),hidden_front_polygons=removed)
    g=Form();supports=[];tops=[]
    for i,p in enumerate(curve):
        hit,_,_,_=ground.ray_cast(Vector((float(p[0]),float(p[1]),30)),Vector((0,0,-1)),50)
        if hit is None:raise RuntimeError('Missing canopy ground support')
        supports.append(float(hit.z))
        sample=p+normals[i]*.55
        top,_,_,_=roof_tree.ray_cast(Vector((float(sample[0]),float(sample[1]),30)),Vector((0,0,-1)),50)
        if top is None:
            top,_,_,distance=roof_tree.find_nearest(Vector((float(sample[0]),float(sample[1]),7)),2.5)
            if top is None:raise RuntimeError('Missing measured canopy roof')
        height=float(top.z)
        if not 2.2<height-hit.z<5.5:raise RuntimeError('Canopy height outside photographed range')
        tops.append(height)
        foot=np.array([*p,hit.z-.025])-origin
        g.tube([foot,np.array([*p,height+.65])-origin],[cfg['column_radius_m']]*2,1,10)
        g.box(foot+[0,0,.08],(.38,.38,.16),0)
        outside=p-normals[i]*.6;back=inner[i]+normals[i]*.6
        beam(g,np.array([*outside,height])-origin,np.array([*back,height+.02])-origin,cfg['beam_width_m'],cfg['beam_height_m'],1)
    for i in range(len(curve)-1):
        # Curved front header and two light roof members follow the photo.
        for fraction in [.1,.58,.98]:
            a=curve[i]+normals[i]*cfg['canopy_depth_m']*fraction;b=curve[i+1]+normals[i+1]*cfg['canopy_depth_m']*fraction
            beam(g,np.array([*a,tops[i]-.16])-origin,np.array([*b,tops[i+1]-.16])-origin,.11,.13,1)
        # Blue-grey service wall is behind the open canopy. Door/window sizes
        # and exact bay allocation are estimates, rather than surveyed detail.
        a,b=inner[i],inner[i+1];bottom=(supports[i]+supports[i+1])/2;top=min(tops[i],tops[i+1])-.3
        g.part([np.array([*a,bottom])-origin,np.array([*b,bottom])-origin,np.array([*b,top])-origin,np.array([*a,top])-origin],[(0,1,2,3)],3)
        mid=(a+b)/2;out=-((normals[i]+normals[i+1])/2);mid+=out*.035
        tangent=b-a;length=np.linalg.norm(tangent);tangent/=length
        if 1<=i<=7:
            left=mid-tangent*length*.37;right=mid+tangent*length*.37;low=bottom+1.0;high=min(top-.3,low+1.15)
            g.part([np.array([*left,low])-origin,np.array([*right,low])-origin,np.array([*right,high])-origin,np.array([*left,high])-origin],[(0,1,2,3)],2)
            beam(g,np.array([*left,low])-origin,np.array([*right,low])-origin,.19,.10,1)
            beam(g,np.array([*left,high])-origin,np.array([*right,high])-origin,.06,.07,1)
        # A pale horizontal band remains visible at the service fascia.
        beam(g,np.array([*a,top-.12])-origin,np.array([*b,top-.12])-origin,.07,.13,1)
    # Fine vertical seams on the retained estimated outer wall segments.
    walls=sources[cfg['source_walls'][0]];wv=np.array([tuple(walls.matrix_world@v.co) for v in walls.data.vertices])
    for k in range(0,len(wv)-3,4):
        quad=wv[k:k+4];a,b=quad[0],quad[1]
        if k//4 in cut_groups_by_name[cfg['source_walls'][0]]:continue
        length=np.linalg.norm(b[:2]-a[:2])
        if length<.2:continue
        n=np.array([b[1]-a[1],a[0]-b[0],0]);n/=np.linalg.norm(n);n*=.012
        for f in np.arange(.10,length,.24)/length:
            top=a*(1-f)+b*f;bottom=quad[3]*(1-f)+quad[2]*f
            if top[2]-bottom[2]>.3:g.tube([bottom+n-origin,top+n-origin],[.007,.007],4,4)
    pending.append(('CanopyFacade',g))
    route=np.array(json.loads((ROOT/'data/derived/paved-circuit-runtime.json').read_text())['points_local_m'])
    route_gap=float(min(np.linalg.norm(route[:,:2]-p,axis=1).min() for p in curve)-cfg['column_radius_m'])
    if route_gap<5:raise RuntimeError('Canopy support too near cycling route')
    retired=[o for o in scene.objects if o.type=='MESH' and o.get('pipeline_owner')==OWNER]
    collection=bpy.data.collections.new(OWNER+'_'+version);scene.collection.children.link(collection);materials=[]
    for row in cfg['materials']:
        m=bpy.data.materials.new('M_M3SecondBeach_'+row['name']+'_'+version);m.diffuse_color=(*row['rgb'],1);m.use_nodes=True
        shader=m.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=m.diffuse_color;shader.inputs['Metallic'].default_value=row['metallic'];shader.inputs['Roughness'].default_value=row['roughness'];materials.append(m)
    folder.mkdir(parents=True);exports=[]
    compact_counts={}
    for name,form in pending:
        before_count=len(form.vertices)
        face_digest=hashlib.sha256(np.array([form.vertices[i] for face in form.faces for i in face],dtype='<f8').tobytes()).hexdigest()
        used=sorted({i for face in form.faces for i in face});index={old:new for new,old in enumerate(used)}
        form.vertices=[form.vertices[i] for i in used];form.uvs=[form.uvs[i] for i in used]
        form.faces=[tuple(index[i] for i in face) for face in form.faces]
        after_digest=hashlib.sha256(np.array([form.vertices[i] for face in form.faces for i in face],dtype='<f8').tobytes()).hexdigest()
        if face_digest!=after_digest:raise RuntimeError('Vertex compaction changed visible faces')
        compact_counts[name]=dict(before_vertices=before_count,exported_vertices=len(used),removed_unused_vertices=before_count-len(used),visible_face_sha256=face_digest,visible_faces_unchanged=True)
        obj=helpers['make_object']('SM_M3SecondBeach_'+name+'_'+version,form,collection,materials,origin)
        obj['pipeline_owner']=OWNER;obj['feature_id']='SP_second_pool';obj['collision']='none'
        for p in obj.data.polygons:p.use_smooth=False
        asset=helpers['export_object'](obj,folder,scene);asset.update(feature_id='SP_second_pool',position_local_m=origin.tolist(),source_label=name);exports.append(asset)
    hidden=[dict(name=n,hide_render=sources[n].hide_render,hide_viewport=sources[n].hide_viewport,hide_set=sources[n].hide_get()) for n in cfg['source_walls']]
    result=dict(version=version,owner=OWNER,input_hashes=inputs,source_geometry=records,settings=cfg,assets=exports,
        asset_root='/Game/StanleyPark/Seawall/SecondBeachDetail/v_'+version,hidden_originals=hidden,
        compact_vertices=compact_counts,retired_detail_objects=[o.name for o in retired],
        supersedes_export='exports/m3-second-beach-detail/9e3897e5c99e/manifest.json',
        wall_copy_counts=counts,column_ground_h_m=supports,canopy_roof_h_m=tops,cycling_route_centre_clearance_m=route_gap,
        original_geometry_placement_collision_unchanged=True,new_collision='none',visual_acceptance=False,geographic_accuracy_accepted=False)
    manifest=folder/'manifest.json';manifest.write_text(json.dumps(result,indent=2));(folder.parent/'latest.json').write_text(json.dumps(dict(manifest=manifest.relative_to(ROOT).as_posix(),sha256=sha(manifest)),indent=2))
    for name in cfg['source_walls']:sources[name].hide_render=True;sources[name].hide_set(True)
    for old in retired:old.hide_render=True;old.hide_set(True)
    return dict(version=version,assets=len(exports),triangles=sum(a['triangles'] for a in exports),route_clearance_m=route_gap,wall_copy_counts=counts)

if __name__ in {'__main__','<run_path>'}:result=build()
