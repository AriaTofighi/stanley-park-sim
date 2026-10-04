"""Close terrain replacements before the live integration stage cuts terrain.

The pool safety depth is an explicit gameplay blockout estimate, not bathymetry.
"""
import json
import numpy as np
import build_named_feature_blockouts as geom
from acquire_sources import save_json

ROOT=geom.ROOT

def add(data,name,vertices,faces,material,fid,reason):
    geom.mesh(name,vertices,faces,material,fid,collision='complex')
    asset=geom.ASSETS[-1];asset['collision_reason']=reason
    data['assets']=[a for a in data['assets'] if a['name']!=name]+[asset]
    return asset

def main():
    path=ROOT/'manifests/named-feature-blockouts.json';data=json.loads(path.read_text());geom.OUT=ROOT/'data/derived/named-features'
    terrace=next(a for a in data['assets'] if a['name']=='SM_ProspectLookout_TerraceSurvey');p=np.load(ROOT/terrace['mesh_path']);v=p['vertices'];f=p['faces']
    counts={};directions={}
    for tri in f:
        for a,b in zip(tri,np.roll(tri,-1)):
            key=tuple(sorted((int(a),int(b))));counts[key]=counts.get(key,0)+1;directions[key]=(int(a),int(b))
    vv=[];ff=[];delta=[]
    for key,count in counts.items():
        if count!=1:continue
        a,b=directions[key];p0,p1=v[a],v[b];h=geom.HEIGHT([[p0[1],p0[0]],[p1[1],p1[0]]]);delta.extend([p0[2]-h[0],p1[2]-h[1]])
        if not np.isfinite(h).all():raise ValueError('Terrace terrain closure lacks source height')
        # Split where the terrace crosses terrain height. This avoids a twisted
        # vertical quad when the source DTM is alternately higher and lower.
        sections=[(p0,p1,h[0],h[1])];d0,d1=p0[2]-h[0],p1[2]-h[1]
        if d0*d1<0:
            t=d0/(d0-d1);mid=p0+(p1-p0)*t;hm=h[0]+(h[1]-h[0])*t
            sections=[(p0,mid,h[0],hm),(mid,p1,hm,h[1])]
        for a0,b0,ha,hb in sections:
            verts=np.array([a0,[a0[0],a0[1],ha],[b0[0],b0[1],hb],b0])
            for indices in [(0,1,3),(1,2,3)]:
                tri=verts[list(indices)]
                if np.linalg.norm(np.cross(tri[1]-tri[0],tri[2]-tri[0]))<2e-8:continue
                n=len(vv);vv.extend(tri);ff.append((n,n+1,n+2))
    asset=add(data,'SM_ProspectLookout_TerrainBoundaryClosure',vv,ff,'stone','SP_prospect_lookout',
        'Stitch between the measured terrace boundary and City DTM. This closes the exact terrain cut; numerical geometry is not proof of safe walking transitions.')
    feature=next(x for x in data['features'] if x['id']=='SP_prospect_lookout');feature['terrain_closure_mesh']=asset['name']
    feature['terrain_boundary_height_difference_m']=[float(min(delta)),float(max(delta))]
    save_json(path,data)

    path=ROOT/'manifests/named-waterfront-blockouts.json';data=json.loads(path.read_text());geom.OUT=ROOT/'data/derived/named-waterfront'
    water=next(a for a in data['assets'] if a['name']=='SM_SecondPool_SurfaceReview');p=np.load(ROOT/water['mesh_path']);v=p['vertices'].copy();f=p['faces'];level=float(v[0,2]);floor=level-.5;v[:,2]=floor
    geom.COLORS['pool_floor']=[.50,.57,.55]
    asset=add(data,'SM_SecondPool_SyntheticSafetyFloor',v,f,'pool_floor','SP_second_pool',
        'Explicit flat safety floor 0.5 m below the 2022 water proxy. This prevents fall-through after terrain removal; it is not a measured pool depth or public access permission.')
    feature=next(x for x in data['features'] if x['id']=='SP_second_pool');xy=np.array(feature['measured']['outline_local_m']);coping=next(a for a in data['assets'] if a['name']=='SM_SecondPool_CopingSurvey')
    cp=np.load(ROOT/coping['mesh_path'])['vertices'].reshape(-1,4,3);vv=[];ff=[]
    for k,a in enumerate(xy):
        b=xy[(k+1)%len(xy)];n=len(vv);vv.extend([[*a,cp[k,0,2]],[*b,cp[k,1,2]],[*b,floor],[*a,floor]])
        # The traced outline is clockwise. These normals face into the basin.
        ff.extend([(n+3,n+2,n+1),(n+3,n+1,n)])
    add(data,'SM_SecondPool_BasinContainmentReview',vv,ff,'pool_floor','SP_second_pool',
        'Vertical side closure to the synthetic safety floor. Basin wall shape and depth are provisional; keep the closed facility outside public navigation.')
    feature['estimates']['synthetic_safety_floor_m']=floor
    feature['terrain_cut_target_height_m']=floor-.15
    feature['safety_floor_mesh']='SM_SecondPool_SyntheticSafetyFloor';feature['containment_mesh']='SM_SecondPool_BasinContainmentReview'
    feature['limits']+=' A synthetic floor and vertical basin sides prevent fall-through; these do not assert measured pool depth. No perimeter fence model exists yet.'
    save_json(path,data)
    print(json.dumps(dict(terrace_delta_m=[min(delta),max(delta)],pool_safety_floor_m=floor,water_m=level)))

if __name__=='__main__':main()
