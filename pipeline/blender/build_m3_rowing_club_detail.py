"""Separate source-bounded Rowing Club visual layer; run in a serial editor slot."""
from pathlib import Path
import hashlib,json,math,runpy,shutil
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OWNER='SP_M3RowingClubDetail'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

class Form:
    def __init__(self):self.vertices=[];self.faces=[];self.slots=[];self.uvs=[]
    def part(self,vertices,faces,slot):
        start=len(self.vertices);self.vertices.extend(tuple(v) for v in vertices);self.uvs.extend((0,0) for _ in vertices)
        self.faces.extend(tuple(start+i for i in f) for f in faces);self.slots.extend(slot for _ in faces)
    def beam(self,a,b,width,slot):
        a=np.asarray(a,float);b=np.asarray(b,float);d=b-a;d/=np.linalg.norm(d)
        u=np.cross(d,[0,0,1] if abs(d[2])<.9 else [0,1,0]);u/=np.linalg.norm(u);v=np.cross(d,u);u*=width/2;v*=width/2
        self.part([p+x*u+y*v for p in [a,b] for x,y in [(-1,-1),(1,-1),(1,1),(-1,1)]],[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],slot)

def geometry_forms(cfg):
    """Pure source geometry preparation, also available for offline inspection."""
    origin=np.asarray(cfg['origin_local_m']);u=np.asarray(cfg['roof_axis_xy']);u/=np.linalg.norm(u);v=np.array([-u[1],u[0]])
    def xyz(a,b,z):return np.array([*(origin[:2]+a*u+b*v),z])-origin
    def local(p):return np.asarray(p)-origin
    roofdata=np.load(ROOT/'data/derived/named-buildings/SM_Named_RowingClub_RoofSurvey.npz');rv=roofdata['vertices'];rf=roofdata['faces']
    walldata=np.load(ROOT/'data/derived/named-buildings/SM_Named_RowingClub_WallsReview.npz');wv=walldata['vertices'];wf=walldata['faces']
    deck=Form();walls=Form();roof=Form();details=Form()
    # Keep the low measured planes exactly. Remove unused vertices on export.
    low=[tuple(f) for f in rf if rv[f,2].max()<7.05]
    deck.part(rv-origin,low,4)
    # New render copy of the estimated envelope; originals remain untouched.
    copy=wv.copy();copy[:,2]=np.minimum(copy[:,2],cfg['eave_height_m'])
    walls.part(copy-origin,[tuple(f) for f in wf],0)
    a,b=cfg['roof_u_extent_m'];c,d=cfg['roof_v_extent_m'];ra,rb=cfg['ridge_u_extent_m'];e=cfg['eave_height_m'];h=cfg['ridge_height_m']
    roof.part([xyz(a,c,e),xyz(b,c,e),xyz(b,d,e),xyz(a,d,e),xyz(ra,0,h),xyz(rb,0,h)],[(0,1,5,4),(1,2,5),(2,3,4,5),(3,0,4)],1)
    for p,q in [((a,c,e),(b,c,e)),((b,c,e),(b,d,e)),((b,d,e),(a,d,e)),((a,d,e),(a,c,e))]:details.beam(xyz(*p),xyz(*q),.16,0)
    # Gables intersect the continuous hip. Each visible front is a closed
    # triangle with dark timber battens, not a vertical roof-step closure.
    for row in cfg['cross_gables']:
        x=row['u_m'];w=row['half_width_m'];front=row['front_v_m'];back=row['back_v_m'];peak=row['front_peak_m'];rear=row['back_peak_m']
        left=xyz(x-w,front,e);right=xyz(x+w,front,e);top=xyz(x,front,peak)
        rfaces=[(0,2,5,3),(2,1,4,5)]
        if front>back:rfaces=[tuple(reversed(f)) for f in rfaces]
        roof.part([left,right,top,xyz(x-w,back,e),xyz(x+w,back,e),xyz(x,back,rear)],rfaces,1)
        walls.part([left,right,top],[(0,1,2) if front<back else (2,1,0)],2)
        for p,q in [(left,right),(left,top),(right,top)]:details.beam(p,q,.17,0)
        for xx in np.arange(x-w+.55,x+w,.65):
            z=e+(peak-e)*(1-abs(xx-x)/w)
            if z>e+.2:
                outside=front+(.025 if front>back else -.025)
                details.beam(xyz(xx,outside,e),xyz(xx,outside,z),.105,0)
    # Repeat simple white window surrounds on the source boundary walls.
    # Bays are visual estimates, placed against the actual boundary quads.
    rails=[]
    for k in range(0,len(copy)-3,4):
        quad=copy[k:k+4];p,q=quad[0].copy(),quad[1].copy();length=np.linalg.norm(q[:2]-p[:2])
        if length<2:continue
        tangent=(q-p);tangent[2]=0;tangent/=np.linalg.norm(tangent)
        centre=(p+q)/2;out=centre[:2]-origin[:2];out/=max(np.linalg.norm(out),1e-9);normal=np.array([*out,0])*.035
        top=min(p[2],q[2]);bottom=max(2.2,min(quad[2,2],quad[3,2]));height=top-bottom
        if height>2.4:
            for f in np.arange(1.3,length-1,3.3)/length:
                mid=p*(1-f)+q*f+normal;left=mid-tangent*.58;right=mid+tangent*.58;lo=top-2.3;hi=top-.85
                left[2]=lo;right[2]=lo;lt=left.copy();rt=right.copy();lt[2]=rt[2]=hi
                walls.part([local(left),local(right),local(rt),local(lt)],[(0,1,2,3)],3)
                for r,s in [(left,right),(right,rt),(rt,lt),(lt,left)]:details.beam(local(r),local(s),.10,2)
                mb=(left+right)/2;mt=(lt+rt)/2;details.beam(local(mb),local(mt),.06,2)
        # White rails sit slightly inside the retained upper deck boundary.
        inward=(origin[:2]-centre[:2]);inward/=max(np.linalg.norm(inward),1e-9)
        p[:2]+=inward*.18;q[:2]+=inward*.18;p[2]=q[2]=top+.07
        steps=max(1,int(math.ceil(length/2.1)));points=[p+(q-p)*f for f in np.linspace(0,1,steps+1)]
        for r in points:details.beam(local(r),local(r+[0,0,1.0]),.09,2)
        for r,s in zip(points,points[1:]):
            details.beam(local(r+[0,0,1]),local(s+[0,0,1]),.085,2)
            details.beam(local(r+[0,0,.14]),local(s+[0,0,.14]),.065,2)
            details.beam(local(r+[0,0,.18]),local(s+[0,0,.95]),.055,2)
            details.beam(local(r+[0,0,.95]),local(s+[0,0,.18]),.055,2)
        rails.append(dict(source_quad=k//4,post_count=len(points)))
    return [('MeasuredDeck',deck),('WallsGables',walls),('ContinuousRoof',roof),('TimberWindowsRails',details)],dict(retained_low_roof_faces=len(low),estimated_wall_height_clamp_m=e,rail_segments=rails),rv,rf

def build():
    import bpy
    if Path(bpy.data.filepath).resolve()!=(ROOT/'blender/StanleyPark_Seawall.blend').resolve():raise RuntimeError('Open separate Seawall source')
    scene=bpy.context.scene
    if abs(scene.unit_settings.scale_length-1)>1e-7:raise RuntimeError('Metre scene required')
    guard=runpy.run_path(str(ROOT/'pipeline/blender/build_m3_support_gap_patches_refined.py'),run_name='rowing_guard')['geometry']
    baseline=guard(scene);cfg=json.loads((ROOT/'manifests/m3-rowing-club-detail-settings.json').read_text());sources={n:bpy.data.objects[n] for n in cfg['source_names']}
    records=[]
    for name,o in sources.items():
        if o.type!='MESH' or o.get('collision')!='none':raise RuntimeError('Expected decorative source '+name)
        points=np.asarray([tuple(o.matrix_world@x.co) for x in o.data.vertices]);data=np.load(ROOT/('data/derived/named-buildings/'+name+'.npz'))
        if points.shape!=data['vertices'].shape or np.max(abs(points-data['vertices']))>.002:raise RuntimeError('Live source differs '+name)
        records.append(dict(name=name,geometry_sha256=hashlib.sha256(points.astype('<f8').tobytes()).hexdigest(),hide_render=o.hide_render,hide_viewport=o.hide_viewport,hide_set=o.hide_get()))
    paths=['pipeline/blender/build_m3_rowing_club_detail.py','manifests/m3-rowing-club-detail-settings.json','pipeline/blender/build_seawall_tree_library.py','pipeline/blender/build_m3_support_gap_patches_refined.py','evidence/m3-baseline-20261003/blender-original-geometry.json','manifests/named-building-blockouts.json','data/derived/paved-circuit-runtime.json']+cfg['reference_files']+['data/derived/named-buildings/'+n+'.npz' for n in cfg['source_names']]
    inputs={p:sha(ROOT/p) for p in paths};version=hashlib.sha256(json.dumps(dict(inputs=inputs,source_geometry=records),sort_keys=True).encode()).hexdigest()[:12];folder=ROOT/'exports/m3-rowing-club-detail'/version
    if (folder/'manifest.json').exists():raise RuntimeError('Immutable Rowing Club export exists')
    pending,counts,rv,rf=geometry_forms(cfg);origin=np.asarray(cfg['origin_local_m']);helpers=runpy.run_path(str(ROOT/'pipeline/blender/build_seawall_tree_library.py'),run_name='rowing_export')
    # Guard the measured envelope. A small rail thickness tolerance is explicit.
    used_points=np.concatenate([np.asarray(g.vertices)[sorted({i for f in g.faces for i in f})]+origin for _,g in pending]);source_min=rv.min(0);source_max=rv.max(0)
    if np.any(used_points[:,:2].min(0)<source_min[:2]-.15) or np.any(used_points[:,:2].max(0)>source_max[:2]+.15) or used_points[:,2].max()>source_max[2]+.01:raise RuntimeError('New visual form exceeds source envelope')
    # All newly estimated roof vertices must lie inside an actual roof triangle.
    triangles=rv[rf,:2];inside=[]
    for p in np.asarray(dict(pending)['ContinuousRoof'].vertices)[:,:2]+origin[:2]:
        a=triangles[:,0];b=triangles[:,1]-a;c=triangles[:,2]-a;w=p-a;det=b[:,0]*c[:,1]-b[:,1]*c[:,0];ok=abs(det)>1e-9;ix=np.flatnonzero(ok);s=(w[ix,0]*c[ix,1]-w[ix,1]*c[ix,0])/det[ix];t=(b[ix,0]*w[ix,1]-b[ix,1]*w[ix,0])/det[ix];inside.append(bool(((s>=-1e-6)&(t>=-1e-6)&(s+t<=1+1e-6)).any()))
    if not all(inside):raise RuntimeError('Estimated roof leaves source footprint')
    archive_source=ROOT/'blender/StanleyPark_Seawall.blend';digest=sha(archive_source);archive=ROOT/'blender/archives'/('StanleyPark_Seawall_'+digest[:12]+'.blend');archive.parent.mkdir(exist_ok=True)
    if not archive.exists():shutil.copy2(archive_source,archive)
    if sha(archive)!=digest:raise RuntimeError('Archive differs')
    visibility_before={o.name:(o.hide_render,o.hide_viewport,o.hide_get()) for o in scene.objects};collection=bpy.data.collections.new(OWNER+'_'+version);scene.collection.children.link(collection);materials=[]
    for row in cfg['materials']:
        m=bpy.data.materials.new('M_M3RowingClub_'+row['name']+'_'+version);m.diffuse_color=(*row['rgb'],1);m.use_nodes=True;node=m.node_tree.nodes.get('Principled BSDF');node.inputs['Base Color'].default_value=m.diffuse_color;node.inputs['Roughness'].default_value=row['roughness'];materials.append(m)
    folder.mkdir(parents=True);assets=[]
    for label,g in pending:
        used=sorted({i for f in g.faces for i in f});indices={v:i for i,v in enumerate(used)};g.vertices=[g.vertices[i] for i in used];g.uvs=[g.uvs[i] for i in used];g.faces=[tuple(indices[i] for i in f) for f in g.faces]
        obj=helpers['make_object']('SM_M3RowingClub_'+label+'_'+version,g,collection,materials,origin);obj['pipeline_owner']=OWNER;obj['feature_id']='SP_rowing_club';obj['collision']='none'
        for p in obj.data.polygons:p.use_smooth=False
        item=helpers['export_object'](obj,folder,scene);item.update(feature_id='SP_rowing_club',position_local_m=origin.tolist(),source_label=label);assets.append(item)
    for o in sources.values():o.hide_render=True;o.hide_set(True)
    for name,state in visibility_before.items():
        o=bpy.data.objects[name];expected=(True,state[1],True) if name in sources else state
        if (o.hide_render,o.hide_viewport,o.hide_get())!=expected:raise RuntimeError('Unexpected source visibility change '+name)
    if guard(scene)!=baseline:raise RuntimeError('Protected source geometry changed')
    result=dict(schema_version=1,version=version,owner=OWNER,input_hashes=inputs,settings=cfg,assets=assets,asset_root='/Game/StanleyPark/Seawall/RowingClubDetail/v_'+version,hidden_originals=records,archive=archive.relative_to(ROOT).as_posix(),archive_sha256=digest,counts=counts,source_bounds_min_m=source_min.tolist(),source_bounds_max_m=source_max.tolist(),new_bounds_min_m=used_points.min(0).tolist(),new_bounds_max_m=used_points.max(0).tolist(),estimated_roof_vertices_inside_source_footprint=True,original_geometry_placement_collision_unchanged=True,original_visibility_changes=list(sources),new_collision='none',visual_acceptance=False,geographic_accuracy_accepted=False)
    manifest=folder/'manifest.json';manifest.write_text(json.dumps(result,indent=2)+'\n');bpy.ops.wm.save_as_mainfile(filepath=str(archive_source));(folder.parent/'latest.json').write_text(json.dumps(dict(manifest=manifest.relative_to(ROOT).as_posix(),sha256=sha(manifest)),indent=2)+'\n')
    return dict(version=version,manifest=str(manifest),assets=len(assets),triangles=sum(x['triangles'] for x in assets))

if __name__ in {'__main__','<run_path>'}:result=build()
