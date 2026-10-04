"""Prepare source-bound north approach and coastal gap data without editor calls."""
from pathlib import Path
import hashlib,json
import numpy as np
import shapely
from shapely.geometry import shape,box,Polygon
from shapely.ops import triangulate

ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))

def prepare():
    paths=['pipeline/gis/prepare_m3_north_approach.py','manifests/m3-north-approach-settings.json','manifests/lions-gate-blockout.json','manifests/geospatial-terrain_surroundings.json','manifests/world-origin.json','pipeline/blender/build_blockout.py','data/derived/terrain_surroundings.npz','data/derived/terrain_park.npz','data/derived/regional-ocean-mask.npz','data/derived/ocean_mask.geojson','data/raw/landmarks/lions-gate-north-foundations-2002.pdf']
    inputs={p:sha(ROOT/p) for p in paths}; version=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:12]
    folder=ROOT/'data/derived/m3-north-approach'/version
    if (folder/'source.json').exists():raise RuntimeError('Prepared source version already exists')
    cfg=read(ROOT/'manifests/m3-north-approach-settings.json'); bridge=read(ROOT/'manifests/lions-gate-blockout.json')
    grid=np.load(ROOT/'data/derived/terrain_surroundings.npz'); mask=np.load(ROOT/'data/derived/regional-ocean-mask.npz'); near=np.load(ROOT/'data/derived/terrain_park.npz')
    x,y,z=grid['x'][::2],grid['y'][::2],grid['z'][::2,::2]
    if not(np.array_equal(grid['x'],mask['x']) and np.array_equal(grid['y'],mask['y'])):raise RuntimeError('Terrain and ocean grid differ')
    valid=np.isfinite(z)&~mask['ocean'][::2,::2]
    xx,yy=np.meshgrid(x,y)
    valid&=~((xx>near['x'][0]+100)&(xx<near['x'][-1]-100)&(yy>near['y'][0]+100)&(yy<near['y'][-1]-100))
    ocean=shape(read(ROOT/'data/derived/ocean_mask.geojson')['features'][0]['geometry'])
    extent=box(*cfg['foreshore_patch_extent_local_m']); land=extent.difference(ocean)
    vertices=[];faces=[];pieces=[];sources=[];existing_area=0.;patch_area=0.
    for j in range(len(y)-1):
        if y[j+1]<extent.bounds[1] or y[j]>extent.bounds[3]:continue
        for i in range(len(x)-1):
            if x[i+1]<extent.bounds[0] or x[i]>extent.bounds[2]:continue
            for ids in [[(j,i),(j,i+1),(j+1,i)],[(j,i+1),(j+1,i+1),(j+1,i)]]:
                xy=np.array([[x[c],y[r]] for r,c in ids]); zz=np.array([z[r,c] for r,c in ids])
                polygon=Polygon(xy); clipped=polygon.intersection(land)
                if clipped.is_empty or clipped.area<1e-6:continue
                if all(valid[r,c] for r,c in ids):existing_area+=clipped.area;continue
                if not np.isfinite(zz).all():raise RuntimeError('Missing height at coastal gap')
                coeff=np.linalg.solve(np.c_[xy,np.ones(3)],zz)
                geoms=[clipped] if clipped.geom_type=='Polygon' else [p for p in clipped.geoms if p.geom_type=='Polygon']
                added=0.
                for geom in geoms:
                    # Delaunay candidates are retained only if fully inside the clipped land polygon.
                    for tri in triangulate(geom):
                        if not geom.covers(tri) or tri.area<1e-7:continue
                        points=np.asarray(tri.exterior.coords)[:3,:2]; start=len(vertices)
                        heights=np.c_[points,np.ones(3)]@coeff
                        vertices.extend(np.c_[points,heights].tolist());faces.append((start,start+1,start+2));added+=tri.area
                if abs(added-clipped.area)>max(.001,clipped.area*1e-8):raise RuntimeError('Coastal triangulation leaves a gap')
                patch_area+=added;sources.append(dict(grid_row=j,grid_col=i,source_indices=ids,area_m2=added))
    if not vertices:raise RuntimeError('No regional coastal gaps found')
    def ground(xy):
        i=int(np.searchsorted(x,xy[0])-1);j=int(np.searchsorted(y,xy[1])-1)
        if not(0<=i<len(x)-1 and 0<=j<len(y)-1):raise RuntimeError('Ground sample outside source')
        u=(xy[0]-x[i])/(x[i+1]-x[i]);v=(xy[1]-y[j])/(y[j+1]-y[j])
        ids=[(j,i),(j,i+1),(j+1,i)] if u+v<=1 else [(j,i+1),(j+1,i+1),(j+1,i)]
        points=np.array([[x[c],y[r],z[r,c]] for r,c in ids]); coeff=np.linalg.solve(np.c_[points[:,:2],np.ones(3)],points[:,2])
        if ocean.covers(shapely.Point(*xy)):raise RuntimeError('Bridge support sample lies in source ocean')
        return float(np.dot([*xy,1],coeff))
    origin=np.array(bridge['axis_origin_local_m']);axis=np.array(bridge['axis_unit']);normal=np.array(bridge['transverse_unit'])
    first=float(bridge['stations_m'][-1]);last=first+cfg['viaduct_length_m']; h0=float(bridge['deck_heights_m'][-1]); h1=ground(origin+axis*last)+cfg['north_embankment_height_m']
    m0=float((bridge['deck_heights_m'][-1]-bridge['deck_heights_m'][-2])/(bridge['stations_m'][-1]-bridge['stations_m'][-2]));transition=cfg['profile_transition_m'];m1=(h1-h0-m0*transition*.5)/(cfg['viaduct_length_m']-transition*.5)
    if max(abs(m0),abs(m1))>.05:raise RuntimeError('Estimated north grade exceeds source five percent maximum')
    def height(s):
        d=s-first
        if d<=transition:return h0+m0*d+(m1-m0)*(d**3/transition**2-d**4/(2*transition**3))
        return h0+(m0+m1)*transition*.5+m1*(d-transition)
    weights=np.array(cfg['span_weights_estimate'],dtype=float);spans=weights*cfg['viaduct_length_m']/weights.sum()
    bent_stations=first+np.r_[0,np.cumsum(spans)]
    if len(spans)!=cfg['span_count'] or abs(bent_stations[-1]-last)>1e-7:raise RuntimeError('North span count or length differs')
    profile_stations=np.unique(np.r_[np.arange(first,last,cfg['deck_sample_m']),bent_stations,last])
    profile=[]
    for s in profile_stations:
        t=np.clip((s-first)/transition,0,1);smooth=t*t*(3-2*t)
        left=(1-smooth)*bridge['deck_edges_transverse_m'][0]+smooth*(-cfg['deck_total_width_m']*.5)
        right=(1-smooth)*bridge['deck_edges_transverse_m'][1]+smooth*(cfg['deck_total_width_m']*.5)
        profile.append(dict(station_m=float(s),height_m=height(s),left_m=float(left),right_m=float(right)))
    supports=[]
    for i,s in enumerate(bent_stations[:-1]):
        feet=[]
        for sign in [-1,1]:
            t=sign*cfg['footing_transverse_centres_m']*.5;xy=origin+axis*s+normal*t
            feet.append(dict(transverse_m=t,position_local_m=[*xy.tolist(),ground(xy)],source='Original regional triangle plane, source FWA land checked'))
        supports.append(dict(index=i,kind='cable_bent' if i==0 else 'ordinary_bent',station_m=float(s),deck_height_m=height(s),feet=feet))
    # A terminal embankment apron follows the documented side slope. Its length
    # is an explicit visual estimate; it adds no road network beyond this layer.
    apron=[]
    half=cfg['deck_total_width_m']*.5;extension=cfg['embankment_apron_length_estimate_m']
    for d in np.linspace(0,extension,21):
        s=last+d;u=d/extension;rise=cfg['north_embankment_height_m']*(1-u*u*(3-2*u))
        base=ground(origin+axis*s);top=base+rise;run=rise*cfg['embankment_side_run_per_rise']
        # A 2 cm sink at the last row prevents a detached terminal edge.
        apron.append(dict(station_m=float(s),top_m=float(top-.02),toe_left_m=-(half+run),toe_right_m=half+run,
             left_ground_m=ground(origin+axis*s-normal*(half+run))-.02,right_ground_m=ground(origin+axis*s+normal*(half+run))-.02))
    folder.mkdir(parents=True,exist_ok=True)
    terrain_path=folder/'foreshore.npz';np.savez_compressed(terrain_path,vertices=np.asarray(vertices),faces=np.asarray(faces,dtype=np.int32))
    result=dict(schema_version=1,version=version,input_hashes=inputs,settings=cfg,source_bridge_manifest='manifests/lions-gate-blockout.json',origin_local_m=origin.tolist(),axis_unit=axis.tolist(),transverse_unit=normal.tolist(),start_station_m=first,end_station_m=last,profile=profile,span_lengths_m=spans.tolist(),supports=supports,embankment_apron=apron,deck_grade_m_per_m=dict(start=m0,main=m1),foreshore=dict(path=terrain_path.relative_to(ROOT).as_posix(),sha256=sha(terrain_path),vertices=len(vertices),triangles=len(faces),patch_area_m2=patch_area,retained_existing_area_m2=existing_area,source_grid_triangles=sources,no_original_triangle_footprint_overlap=True,no_source_ocean_overlap=True,source_resolution_m=80,rendered_original_grid_m=160),visual_acceptance=False)
    out=folder/'source.json';out.write_text(json.dumps(result,indent=2))
    (ROOT/'data/derived/m3-north-approach/latest.json').write_text(json.dumps(dict(source=out.relative_to(ROOT).as_posix(),sha256=sha(out)),indent=2))
    print(json.dumps(dict(version=version,source=str(out),foreshore_triangles=len(faces),foreshore_area_m2=patch_area,deck_start=h0,deck_end=h1,grade=m1,span_range_m=[float(spans.min()),float(spans.max())])))

if __name__=='__main__':prepare()
