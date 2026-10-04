"""Select contact panels without adding unmeasured collision boxes.

Run after all three named geometry stages, before audit and Blender authoring.
Panels that intersect source path corridors remain visual only for M1 review.
The corridor comparison is conservative and is not an interactive test.
"""
import json
from pathlib import Path
import numpy as np
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.ops import unary_union
from acquire_sources import digest, save_json

ROOT=Path(__file__).resolve().parents[2]
PACKAGES=['named-feature-blockouts','named-building-blockouts','named-waterfront-blockouts']

def record_mesh(asset,vertices,faces,path):
    np.savez_compressed(path,vertices=vertices,faces=faces)
    asset.update(mesh_path=path.relative_to(ROOT).as_posix(),sha256=digest(path),vertices=len(vertices),triangles=len(faces),
                 bounds_min_m=vertices.min(0).tolist(),bounds_max_m=vertices.max(0).tolist())

def main():
    runtime=json.loads((ROOT/'data/derived/paved-circuit-runtime.json').read_text())
    cycle=LineString(np.asarray(runtime['points_local_m'])[:,:2]).buffer(runtime['development_width_m']/2+.35)
    branches=json.loads((ROOT/'data/routes/derived/park_routes.json').read_text())
    main_ids={x['edge_id'] for x in branches['main_circuit']['ordered_edges']}
    corridors=[cycle]
    for edge in branches['edges']:
        if edge['edge_id'] in main_ids:continue
        xy=edge['coordinates_local_xy_m']
        if len(xy)>1:corridors.append(LineString(xy).buffer(1.85))
    pedestrians=json.loads((ROOT/'data/routes/derived/pedestrian-network.json').read_text())
    for edge in pedestrians['edges']:
        if not edge['render_candidate']:continue
        xy=edge['coordinates_local_xy_m']
        if len(xy)>1:corridors.append(LineString(xy).buffer(edge['width_m']/2+.3))
    legal_corridors=unary_union(corridors)
    audit=[]
    def light_override(data):
        for asset in data['assets']:
            if asset['name']!='SM_ProspectLight_LowerWhite':continue
            # Site-specific source review supersedes the generic safety margin.
            # The measured pavement itself is clear by 0.083786 m; the player's
            # capsule must still respond to the solid structure beside it.
            asset['collision']='complex'
            asset['collision_reason']='Site-specific source review found 0.083786 m gap from the exact paved mesh; solid collision is required. The generic 0.35 m screening margin is not an actual overlap. Test narrow path-edge riding in runtime.'
            asset['collision_review']='evidence/named-features/prospect-light-route-review.json'
            for item in data.get('collision_panel_review',[]):
                if item['asset']==asset['name']:
                    item.update(contact_enabled=True,exact_pavement_gap_m=.083786,margin_screening_override=True,interactive_check=False)
    for package in PACKAGES:
        path=ROOT/f'manifests/{package}.json';data=json.loads(path.read_text())
        if data.get('collision_policy_revision')=='named-contact-r1':
            light_override(data);save_json(path,data)
            audit.extend(data['collision_panel_review']);continue
        extra=[]
        for asset in data['assets']:
            file=ROOT/asset['mesh_path'];p=np.load(file);v=p['vertices'];f=p['faces'];name=asset['name']
            reason='Roof or minor upper detail; ground-based walking contact is handled by facade or posts'
            if asset['feature_id']=='SP_yacht_club':
                reason='Private marina is observed from the public seawall. Floating dock level and private access geometry remain unverified; no public traversal is claimed.'
            elif 'WallsReview' in name:
                panels=v.reshape(-1,4,3);clear=[];conflict=[]
                for k,panel in enumerate(panels):
                    edge=LineString(panel[:2,:2])
                    (conflict if legal_corridors.intersects(edge) else clear).append(k)
                def subset(indices):
                    vv=panels[indices].reshape(-1,3)
                    # Preserve two adjacent triangles per panel for the normal audit.
                    ff=np.array([tri for i in range(0,len(vv),4) for tri in [(i+3,i+2,i+1),(i+3,i+1,i)]],dtype=np.int32)
                    return vv,ff
                if clear and conflict:
                    original=dict(asset);vv,ff=subset(clear);record_mesh(asset,vv,ff,file)
                    visual=dict(original);visual['name']=name+'_PathConflict';vv,ff=subset(conflict)
                    record_mesh(visual,vv,ff,file.with_name(visual['name']+'.npz'));visual['collision']='none'
                    visual['collision_reason']='Survey roof extrusion overlaps a mapped path corridor. This may be an eave or doorway; do not place inferred solid collision across it.';extra.append(visual)
                asset['collision']='complex' if clear else 'none'
                reason='Per-triangle measured-roof facade panels extend to terrain. Panels intersecting mapped path corridors are withheld; no inferred collision box is used.' if clear else 'All facade panels intersect a mapped path corridor; source ambiguity must be checked before collision.'
                audit.append(dict(asset=name,total_panels=len(panels),contact_panels=len(clear),withheld_panels=len(conflict),
                                  nearest_cycle_ribbon_m=float(MultiLineString([p[:2,:2] for p in panels]).distance(cycle)),interactive_check=False))
            elif name=='SM_ProspectLookout_TerraceSurvey':
                asset['collision']='complex';reason='Walkable survey TIN. Requires terrain replacement and a boundary/stair contact check before M1 acceptance.'
            elif name=='SM_SecondPool_CopingSurvey':
                asset['collision']='complex';reason='Low coping ribbon uses ground returns. Pool interior remains outside the public traversal scope and water stays non-colliding.'
            elif name.startswith('SM_NineClockGun_Post_') or name.startswith('SM_NineClockGun_Rail_') or name.startswith('SM_NineClockGun_EndRail_') or name=='SM_ProspectLight_LowerWhite':
                footprint=Polygon(v[:,:2]).convex_hull
                clear=not legal_corridors.intersects(footprint)
                asset['collision']='complex' if clear else 'none'
                reason='Closed solid blockout; direct triangles preserve the open surrounding space. XY footprint does not intersect the source path corridors.' if clear else 'Footprint intersects a mapped path corridor; contact withheld pending close alignment review.'
                audit.append(dict(asset=name,contact_enabled=clear,nearest_cycle_ribbon_m=float(footprint.distance(cycle)),interactive_check=False))
            elif name=='SM_SecondPool_SurfaceReview':
                reason='Water surface, not a solid floor. Pool was closed after 7 September 2026. Basin/fence and current fill state remain unresolved; no pool-interior traversal is claimed.'
            asset['collision_reason']=reason
        data['assets'].extend(extra);data['collision_policy_revision']='named-contact-r1';data['collision_panel_review']=[x for x in audit if x['asset'] in {a['name'] for a in data['assets']}]
        light_override(data)
        save_json(path,data)
    save_json(ROOT/'evidence/named-blockout-collision-policy.json',dict(revision='named-contact-r1',
        cycle_path_sha256=digest(ROOT/'data/derived/paved-circuit-runtime.json'),pedestrian_network_sha256=digest(ROOT/'data/routes/derived/pedestrian-network.json'),
        rule='Exact facade panel XY segments compared to displayed width plus clearance; not collision boxes; no runtime test performed',items=audit))
    print(json.dumps(audit,indent=2))

if __name__=='__main__':main()
