"""Named, source-identified remaining building silhouettes, not generic roofs."""
import json
import numpy as np
import shapely
from shapely.geometry import Polygon,LineString
from scipy.spatial import Delaunay
import build_named_feature_blockouts as geom
from named_roof_planes import fit_major_planes,rebuild_planar_patches
from acquire_sources import save_json,digest

ROOT=geom.ROOT
CITY_MAP='https://vancouver.ca/files/cov/stanley-park-map-and-guide.pdf'
DEADMAN='https://www.pc.gc.ca/apps/dfhd/page_fhbro_eng.aspx?id=8202'
NAVY='https://www.canada.ca/en/navy/services/history/ships-histories/discovery.html'
RAIL='https://parkboardmeetings.vancouver.ca/2018/20181001/REPORT-ParkBoardConcessionStrategy-AFreshApproach-20181001.pdf'
ITEMS=[
    ('SP_deadman','DeadmanAdminDrill','HMCS Discovery administration building and drill hall',[(491000,5460000,9)],
     [DEADMAN,NAVY],'named-deadman-buildings','Northern prominent administration block with stepped wings and large attached rear drill hall; primary heritage description matches the measured roof composition. Exact facades remain unfinished.'),
    ('SP_deadman','DeadmanSouthHall','HMCS Discovery southern pitched building',[(491000,5460000,3)],
     [NAVY],'named-deadman-buildings','Distinct southern angled/hipped roof complex on the island. Site identity and separate measured form are verified; internal use is not assigned.'),
    ('SP_deadman','DeadmanSouthwestHall','HMCS Discovery southwest service hall',[(491000,5460000,2)],
     [NAVY],'named-deadman-buildings','Separate rectangular pitched roof southwest of the larger southern building, north of the helipad. Functional room identity remains unknown.'),
    ('SP_deadman','DeadmanGatehouse','HMCS Discovery causeway gatehouse',[(490000,5460000,17),(491000,5460000,4)],
     [DEADMAN,NAVY],'named-deadman-buildings','Roof group crosses the survey tile line. The small flat and hipped masses stand at the island end of the closed-access causeway; primary heritage source confirms a guardhouse.'),
    ('SP_deadman','DeadmanWestStore','HMCS Discovery western boat/store shed',[(491000,5460000,6),(491000,5460000,7)],
     [NAVY],'named-deadman-buildings','Long low west-side roof beside stored boats in the 2022 ortho. Canopy separates the classified roof patches; the gap is retained rather than filled.'),
    ('SP_train','RailwayCafe','Miniature Railway Cafe and visitor facilities',[(490000,5460000,37)],
     [RAIL,'https://vancouver.ca/parks-recreation-culture/stanley-park-train.aspx'],'named-train-buildings','Large visitor roof at the south edge of the railway plaza, beside the mapped Railway Cafe point. Distinct pitches and courtyard breaks are retained; this does not complete the station, Cob House or railway.'),
]


def step_closures(vertices,faces):
    """Close each oriented roof-patch edge, splitting crossing roof planes."""
    edges={}
    for face in faces:
        for i,j in zip(face,np.roll(face,-1)):
            a,b=vertices[[i,j]];key=tuple(sorted((tuple(np.round(a[:2],6)),tuple(np.round(b[:2],6)))))
            edges.setdefault(key,[]).append((a,b))
    vv=[];ff=[]
    for rows in edges.values():
        if len(rows)!=2:continue
        a,b=rows[0];d,c=rows[1]
        if np.linalg.norm(a[:2]-c[:2])>1e-5:c,d=d,c
        if max(abs(a[2]-c[2]),abs(b[2]-d[2]))<.05:continue
        sections=[(a,b,c,d)];da,db=a[2]-c[2],b[2]-d[2]
        if da*db<0:
            t=da/(da-db);ab=a+(b-a)*t;cd=c+(d-c)*t
            sections=[(a,ab,c,cd),(ab,b,cd,d)]
        for a,b,c,d in sections:
            for tri in [np.array([a,b,d]),np.array([a,d,c])]:
                if np.linalg.norm(np.cross(tri[1]-tri[0],tri[2]-tri[0]))<2e-8:continue
                k=len(vv);vv.extend(tri);ff.append((k,k+1,k+2))
    return np.array(vv),np.array(ff,dtype=int)


def main():
    geom.OUT=ROOT/'data/derived/harbour-interior-buildings';geom.OUT.mkdir(exist_ok=True);geom.ASSETS.clear();geom.FEATURES.clear()
    cover={x['id']:x for x in json.loads((ROOT/'data/derived/cover-blockout.json').read_text())['buildings']};cache={};feature_records={}
    ped=json.loads((ROOT/'data/routes/derived/pedestrian-network.json').read_text());corridors=shapely.union_all([LineString(e['coordinates_local_xy_m']).buffer(e['width_m']/2) for e in ped['edges'] if e['render_candidate']])
    for fid,tag,name,groups,urls,ortho,note in ITEMS:
        selected=[];ids=[]
        for e,n,k in groups:
            key=f'{e}_{n}';cid=f'lidar2022_{key}_{k}';ids.append(cid);poly=Polygon(cover[cid]['outline']).buffer(.05)
            if key not in cache:cache[key]=np.load(ROOT/f'data/derived/lidar2022_{key}.npz')['buildings'][:,:3].astype(float)
            q=cache[key];selected.append(q[shapely.contains_xy(poly,q[:,0],q[:,1])])
        q=np.vstack(selected);poly=shapely.union_all([Polygon(cover[k]['outline']).buffer(.05) for k in ids])
        cells=np.floor(q[:,:2]/.6).astype(int);keys,inv=np.unique(cells,axis=0,return_inverse=True);v=np.array([np.median(q[inv==k],axis=0) for k in range(len(keys))])
        v,review,labels=fit_major_planes(v,min_support=25,max_planes=20);f=Delaunay(v[:,:2]).simplices
        edges=np.linalg.norm(v[f,:2]-np.roll(v[f,:2],1,axis=1),axis=2)
        centres=v[f,:2].mean(1);f=f[(edges.max(1)<2.)&shapely.contains_xy(poly,centres[:,0],centres[:,1])]
        v,f,sv,sf,boundary=rebuild_planar_patches(v,f,labels,review)
        sv,sf=step_closures(v,f)
        geom.mesh(f'SM_{tag}_RoofSurvey',v,f,'roof',fid)
        if len(sf):geom.mesh(f'SM_{tag}_RoofStepClosures',sv,sf,'wall',fid)
        panels=[]
        for a,b in boundary:
            h=geom.HEIGHT(np.array([a,b])[:,[1,0]]);h=np.minimum(h,np.array([a[2],b[2]])-.2)
            panels.append(np.array([a,b,[*b[:2],h[1]],[*a[:2],h[0]]]))
        clear=[];conflict=[]
        for p in panels:(conflict if corridors.intersects(LineString(p[:2,:2])) else clear).append(p)
        for part,suffix in [(clear,''),(conflict,'_PathConflict')]:
            if not part:continue
            vv=np.array(part).reshape(-1,3);ff=[tri for n in range(0,len(vv),4) for tri in [(n+3,n+2,n+1),(n+3,n+1,n)]]
            contact='complex' if fid!='SP_deadman' and not suffix else 'none'
            geom.mesh(f'SM_{tag}_WallsReview'+suffix,vv,ff,'wall',fid,collision=contact)
            if tag=='DeadmanGatehouse' and not suffix:
                geom.ASSETS[-1]['expected_coincident_facade_edges']=1
                geom.ASSETS[-1]['contact_topology_limit']='One four-panel vertical junction at East 1410.508057, North -848.661987 is shared by independent roof-edge facade sheets. This public-view facade has no collision and is not a watertight building.'
        sub=dict(name=name,source_roof_ids=ids,source_returns=len(q),centre_local_m=v[:,:2].mean(0).tolist(),roof_bounds_local_m=[v.min(0).tolist(),v.max(0).tolist()],roof_plane_review=review,identity_note=note)
        feature_records.setdefault(fid,[]).append(sub)
        print(name,len(q),len(f),len(review['planes']),flush=True)
    for fid,forms in feature_records.items():
        items=[x for x in ITEMS if x[0]==fid];urls=list(dict.fromkeys([CITY_MAP,*[url for x in items for url in x[4]],*[f'evidence/corridor/ortho-utm/{x[5]}.json' for x in items]]))
        ids=[k for form in forms for k in form['source_roof_ids']]
        geom.feature(fid,'Deadman Island / HMCS Discovery public-view massing' if fid=='SP_deadman' else 'Miniature Railway visitor building massing',urls,
            dict(centre_local_m=np.mean([x['centre_local_m'] for x in forms],axis=0).tolist(),individually_identified_forms=forms,source_roof_ids=ids),
            dict(facades='Roof-edge extrusion to City DTM; eaves and exact wall openings remain unresolved'),
            'Measured major roof planes with individually checked identities and orthophoto placement. No interior model. No independent accuracy or live acceptance. '+('The island is closed to public access; these roofs are public-view silhouettes and do not provide navigation or building contact.' if fid=='SP_deadman' else 'This only identifies the Cafe/visitor roof; the separate Cob House, station and waiting shelter need their own forms.'),ids)
    for a in geom.ASSETS:
        a['collision_reason']='Private island silhouette only; City 2026 map excludes public access. No roof/facade navigation is created.' if a['feature_id']=='SP_deadman' else ('Source roof-edge facade clear of mapped pedestrian paths; per-triangle contact without inferred boxes.' if a['collision']=='complex' else 'Upper roof detail or a facade across a mapped public path; do not infer a solid obstacle at an unresolved eave/opening.')
    result=dict(schema_version=1,revision='harbour-interior-m1-r1',assets=geom.ASSETS,features=geom.FEATURES,acceptance=False,source_period='City 2022 survey and ortho; primary identity documents',target_period='September 2026',reference_rights='City survey/ortho derivatives OGL-Vancouver. Heritage/operator documents reference only.',input_hashes={f'data/derived/lidar2022_{k}.npz':digest(ROOT/f'data/derived/lidar2022_{k}.npz') for k in cache})
    save_json(ROOT/'manifests/harbour-interior-building-blockouts.json',result)


if __name__=='__main__':main()
