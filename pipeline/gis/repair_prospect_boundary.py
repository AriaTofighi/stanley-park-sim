"""Stitch the stable terrace to the actual clipped terrain, not a height grid."""
import json
import numpy as np
import shapely
from shapely.geometry import Polygon, LineString, Point
import build_named_feature_blockouts as geom
from repair_prospect_terrace import profile
from terrain_boundary_stitch import ExportedTerrainPatch
from acquire_sources import save_json

ROOT=geom.ROOT

def main():
    path=ROOT/'manifests/named-feature-blockouts.json';d=json.loads(path.read_text());feature=next(x for x in d['features'] if x['id']=='SP_prospect_lookout')
    poly=Polygon(feature['terrain_cut_polygon_local_m']);terrain=ExportedTerrainPatch(ROOT,poly)
    params=np.array(feature['stable_floor_review']['parameters']);breaks=[params[0],params[0]+params[1],params[2],params[2]+params[3]]
    vertices=[];faces=[];deltas=[];seams=[]
    for original in terrain.boundary_segments:
        a,b=original[::-1].copy() # terrace interior on left
        sa,sb=a[:2].sum(),b[:2].sum();fractions=[0.,1.]
        if abs(sb-sa)>1e-9:fractions+=list((s-sa)/(sb-sa) for s in breaks if 0<(s-sa)/(sb-sa)<1)
        fractions=sorted(fractions)
        for fa,fb in zip(fractions[:-1],fractions[1:]):
            grounda=a+(b-a)*fa;groundb=a+(b-a)*fb
            topa=grounda.copy();topb=groundb.copy();topa[2]=float(profile(params,topa[:2])+.025);topb[2]=float(profile(params,topb[:2])+.025)
            da,db=topa[2]-grounda[2],topb[2]-groundb[2];deltas.extend([da,db]);sections=[(topa,topb,grounda,groundb)]
            if da*db<0:
                t=da/(da-db);top=topa+(topb-topa)*t;ground=grounda+(groundb-grounda)*t
                sections=[(topa,top,grounda,ground),(top,topb,ground,groundb)]
            for ta,tb,ga,gb in sections:
                for tri in [np.array([ta,ga,tb]),np.array([ga,gb,tb])]:
                    if np.linalg.norm(np.cross(tri[1]-tri[0],tri[2]-tri[0]))<2e-8:continue
                    n=len(vertices);vertices.extend(tri);faces.append((n,n+1,n+2))
                seams.append(dict(top=[ta.tolist(),tb.tolist()],terrain=[ga.tolist(),gb.tolist()]))
    name='SM_ProspectLookout_TerrainBoundaryClosure'
    d['assets']=[a for a in d['assets'] if a['name']!=name]
    if faces:
        geom.mesh(name,vertices,faces,'stone','SP_prospect_lookout',collision='complex');asset=geom.ASSETS[-1]
        asset['collision_reason']='Exact vertical stitch from each actual clipped terrain boundary segment to the stable terrace profile; crossing-zero panels split. This does not assert surveyed retaining wall form.'
        d['assets'].append(asset);feature['terrain_closure_mesh']=name
    else:
        feature['terrain_closure_mesh']=None
    floor_asset=next(a for a in d['assets'] if a['name']=='SM_ProspectLookout_TerraceSurvey');p=np.load(ROOT/floor_asset['mesh_path']);v=p['vertices'];f=p['faces'];triangles=v[f];polygons=shapely.polygons(triangles[:,:,:2]);tree=shapely.STRtree(polygons)
    max_floor=0.;max_terrain=0.
    for seam in seams:
        for point in seam['top']:
            xy=np.array(point[:2]);hits=tree.query(Point(xy).buffer(1e-6),predicate='intersects');hits=[k for k in hits if polygons[k].distance(Point(xy))<1e-6]
            if not hits:raise ValueError(f'Closure top has no terrace surface at {xy}')
            tri=triangles[hits[0]];uv=np.linalg.solve(np.column_stack((tri[1,:2]-tri[0,:2],tri[2,:2]-tri[0,:2])),xy-tri[0,:2]);h=tri[0,2]+uv@(tri[1:,2]-tri[0,2]);max_floor=max(max_floor,abs(h-point[2]))
        for point in seam['terrain']:max_terrain=max(max_terrain,abs(terrain.height(point[:2])-point[2]))
    lines=shapely.unary_union([LineString(e[:,:2]) for e in terrain.boundary_segments]);missing=poly.boundary.difference(lines.buffer(1e-6)).length
    review=dict(terrain_inputs=terrain.inputs,ignored_degenerate_terrain_triangles=terrain.ignored_degenerate_triangles,
        terrain_boundary_segments=len(terrain.boundary_segments),stitch_segments=len(seams),
        uncovered_boundary_length_m=missing,max_surface_endpoint_gap_m=float(max_floor),max_terrain_endpoint_gap_m=float(max_terrain),
        height_difference_m=[float(min(deltas)),float(max(deltas))],closure_triangles=len(faces),numerical_pass=missing<1e-5 and max_floor<1e-5 and max_terrain<1e-5,
        terrain_form_review_needed=bool(max(abs(np.array(deltas)))>2),
        live_acceptance=False,method='Actual exported cut-boundary segments plus every floor-profile break intersection; no raster-height extrapolation',
        limitation='This measures the join to the authored floor, not independent survey accuracy. Exact stair treads and parapet architecture remain unfinished. Live contact and rendering are not accepted.')
    if not review['numerical_pass']:raise ValueError(review)
    feature['exact_terrain_closure_review']=review;feature['terrain_boundary_height_difference_m']=review['height_difference_m']
    save_json(path,d);save_json(ROOT/'evidence/prospect-terrace-boundary-repair.json',review)
    print(json.dumps(review,indent=2))

if __name__=='__main__':main()
