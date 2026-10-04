"""Two principal source-located play-form envelopes, no working equipment."""
import json
import os
from pathlib import Path
os.environ['MPLCONFIGDIR']=str(Path(__file__).resolve().parents[2]/'evidence/mpl-cache')
import numpy as np
import shapely
from shapely.geometry import Polygon,LineString
from scipy.spatial import cKDTree
from build_public_space_meshes import ROOT,save,digest
from review_siwash_approach import TerrainQuery

OUT=ROOT/'data/derived/waterpark-low-forms'


def main():
    p=ROOT/'data/derived/named-lumberman-arch-survey.npz'
    with np.load(p)as data:q=data['xyz'].astype(float);cl=data['classification']
    image_meta=ROOT/'evidence/corridor/ortho-utm/m1-waterpark.json';meta=json.loads(image_meta.read_text());b=meta['local_bounds_m']
    def xy(pixels):return np.array([[b[0]+x*.1,b[3]-y*.1]for x,y in pixels])
    terrain=TerrainQuery([947,36,975,65]);assets=[];reviews=[]
    def emit(name,vertices,faces,color,source,limit):
        v=np.asarray(vertices);f=np.asarray(faces,dtype=np.int32);anchor=np.floor(v.mean(0)/10)*10
        if not np.isfinite(v).all():raise ValueError(name)
        area=np.linalg.norm(np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]),axis=1)*.5
        if np.any(area<1e-8):raise ValueError('Degenerate '+name)
        path=OUT/(name+'.npz');np.savez_compressed(path,vertices=v-anchor,faces=f,anchor=anchor,colors=np.tile(color,(len(v),1)))
        assets.append(dict(name=name,path=path.relative_to(ROOT).as_posix(),sha256=digest(path),feature_id='SP_water_park',m1_group='M1-F05',
            component_id=name,material_role='play_form',material_color=color,contact_surface='Current terrain / measured 2022 envelope',visual_lift_m=0.,
            vertices=len(v),triangles=len(f),collision='complex',source=source,limit=limit))
    OUT.mkdir(parents=True,exist_ok=True)
    # The climbing outcrop is irregular. Retain its visible coarse perimeter and measured upper-return relief.
    picks=[(849,810),(870,795),(908,813),(944,868),(948,923),(922,959),(898,950),(878,929),(845,892)]
    outline=xy(picks);poly=Polygon(outline)
    inside=shapely.contains_xy(poly,q[:,0],q[:,1]);candidate=q[inside&np.isin(cl,[1,2])&(q[:,2]<7.0)]
    cells=np.floor(candidate[:,:2]/.5).astype(int);unique=np.unique(cells,axis=0);tops=[]
    for cell in unique:
        subset=candidate[np.all(cells==cell,axis=1)];tops.append([*(cell*.5+.25),float(np.percentile(subset[:,2],85))])
    tops=np.array(tops);tree=cKDTree(tops[:,:2])
    # Constrained triangulation of a dense top footprint preserves the irregular outline.
    grid=np.mgrid[poly.bounds[0]:poly.bounds[2]:.7,poly.bounds[1]:poly.bounds[3]:.7].reshape(2,-1).T
    grid=grid[shapely.contains_xy(poly,grid[:,0],grid[:,1])]
    from scipy.spatial import Delaunay
    points=np.vstack((outline,grid));faces=Delaunay(points).simplices
    tri=shapely.polygons(points[faces]);keep=np.array([poly.covers(t) for t in tri]);faces=faces[keep]
    _,index=tree.query(points,k=min(5,len(tops)));heights=np.median(tops[index,2],axis=1)
    bottom=np.array([terrain.height(v) for v in points])-.04
    heights=np.maximum(heights,bottom+.08)
    v=np.vstack((np.c_[points,heights],np.c_[points,bottom]));n=len(points);f=[]
    for face in faces:
        a,b_,c=face
        if np.linalg.det(np.column_stack((points[b_]-points[a],points[c]-points[a])))<0:b_,c=c,b_
        f.extend([[a,b_,c],[n+a,n+c,n+b_]])
    for i in range(len(outline)):
        j=(i+1)%len(outline);f.extend([[i,j,n+j],[i,n+j,n+i]])
    emit('SM_WaterPark_ClimbingOutcrop',v,f,[.48,.46,.38,1],dict(type='City2022 visible outline plus low raw returns',survey=p.relative_to(ROOT).as_posix(),
        retained_returns=len(candidate),height_samples=len(tops),image_picks=picks,upper_return_percentile=85,maximum_retained_z_m=7.0),
        'Coarse visible rock/play envelope. Canopy classes excluded; railings, stairs, recesses, slides and spray are later detail. Terrain contact is retained; not a certified climbing structure.')
    # The boat-shaped feature has a visible open horseshoe rim; do not replace it with a filled box.
    picks=[(787,741),(763,742),(743,751),(738,767),(749,779),(769,785),(789,784),(811,778),(819,764),(815,749),(804,741)]
    line=xy(picks);footprint=LineString(line).buffer(.18,cap_style='flat',join_style='round')
    nearby=q[shapely.contains_xy(footprint.buffer(.3),q[:,0],q[:,1])&np.isin(cl,[1,2])]
    ground=np.median([terrain.height(a)for a in line]);height=float(np.percentile(nearby[:,2],95));height=max(ground+.65,min(height,ground+1.55))
    vertices=[];faces=[]
    for part in shapely.get_parts(footprint):
        for tri in shapely.get_parts(shapely.constrained_delaunay_triangles(part)):
            a=np.array(tri.exterior.coords)[:3]
            if np.linalg.det(np.column_stack((a[1]-a[0],a[2]-a[0])))<0:a=a[::-1]
            k=len(vertices);low=np.array([terrain.height(x)for x in a])-.03
            vertices.extend(np.c_[a,np.full(3,height)].tolist());vertices.extend(np.c_[a,low].tolist())
            faces.extend([[k,k+1,k+2],[k+3,k+5,k+4]])
        ring=np.array(part.exterior.coords)[:-1]
        for a,b_ in zip(ring,np.roll(ring,-1,axis=0)):
            k=len(vertices);vertices.extend([[*a,height],[*b_,height],[*b_,terrain.height(b_)-.03],[*a,terrain.height(a)-.03]])
            faces.extend([[k,k+1,k+2],[k,k+2,k+3]])
    emit('SM_WaterPark_BoatOpenRim',vertices,faces,[.49,.13,.10,1],dict(type='City2022 visible boat rim and low-return height envelope',survey=p.relative_to(ROOT).as_posix(),
        image_picks=picks,nearby_returns=len(nearby),top_z_m=height,ground_m=float(ground),wall_width_estimate_m=.36),
        'Open horseshoe rim only. Rim width and regularized hidden faces are explicit M1 estimates; no detailed deck, steering wheel or interactive apparatus.')
    result=dict(schema_version=1,meshes=assets,source_inputs=[dict(path=x.relative_to(ROOT).as_posix(),sha256=digest(x))for x in [p,image_meta]],
        terrain_inputs=terrain.inputs,exclusion_mesh_inputs=[],source_manifest='manifests/lumberman-facility-blockouts.json',
        attribution=['Contains information licensed under the Open Government Licence - Vancouver.'],licence='OGL Vancouver survey and image-derived geometry',
        scope='Two principal low play-form envelopes only; no detailed equipment or seasonal operation',application_visual_check='pending',release_accepted=False)
    save(ROOT/'manifests/waterpark-low-forms.json',result);print(json.dumps(dict(meshes=len(assets),triangles=sum(r['triangles']for r in assets),retained_rock_returns=len(candidate))))


if __name__=='__main__':main()
