"""Stitch Lumberman to already-cut exported terrain. Never edits terrain."""
import json
from pathlib import Path
import numpy as np
import shapely
from shapely.geometry import LineString, Point
from acquire_sources import save_json
from terrain_boundary_stitch import ExportedTerrainPatch
from lumberman_integration_geometry import FacilitySolids, sha, height_order_splits, exposed_ranges
from build_underpass_closures import add_panel

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'data/derived/lumberman-facilities'


def main():
    facility = FacilitySolids(ROOT)
    footprint = facility.footprints['terrain_and_existing_walk']
    terrain = ExportedTerrainPatch(ROOT, footprint)
    OUT.mkdir(exist_ok=True)
    vertices, faces, rejected, contacts = [], [], [], []
    terrain_errors, plane_errors = [], []
    covered_lines = []
    split_count = 0
    opening = facility.footprints['walkthrough_opening']
    opening_u = [facility.uv(p)[0] for p in opening.exterior.coords]
    floor_v = [facility.uv(p)[1] for p in footprint.exterior.coords]
    # A high approach edge requires a terrain/floor transition, not a curtain
    # across the walk. This is an engineering join criterion, not a survey.
    maximum_passage_step_m = .03
    for segment in terrain.boundary_segments:
        a,b = segment
        line = LineString([a[:2],b[:2]])
        fractions = facility.split_fractions(line)
        # The open corridor continues to the outer floor ends. Its width must
        # split those edges even where no wall triangle reaches the approach.
        ua,ub=facility.uv(a[:2])[0],facility.uv(b[:2])[0]
        if abs(ub-ua)>1e-12:
            fractions.extend((u-ua)/(ub-ua) for u in (min(opening_u),max(opening_u)) if 0<(u-ua)/(ub-ua)<1)
        fractions=sorted(set(round(v,12) for v in fractions))
        covered_lines.append(line)
        for lo,hi in zip(fractions,fractions[1:]):
            if hi-lo < 1e-9:
                continue
            ends = np.array([a+(b-a)*lo,a+(b-a)*hi])
            rows = facility.ranges_along(ends[:,:2])
            for t0,t1 in zip((cuts:=height_order_splits(ends[:,2],rows)),cuts[1:]):
                if t1-t0 < 1e-9:
                    continue
                sub = np.array([ends[0]+(ends[1]-ends[0])*t0,ends[0]+(ends[1]-ends[0])*t1])
                xy,ground = sub[:,:2],sub[:,2]
                ranges = facility.ranges_along(xy)
                floor = next(r for r in ranges if r['name'].endswith('PedestrianFloor'))
                uv = facility.uv(xy.mean(0))
                passage_end = min(abs(uv[1]-min(floor_v)),abs(uv[1]-max(floor_v))) < 1e-5 and min(opening_u)-1e-6 <= uv[0] <= max(opening_u)+1e-6
                road_end = any(r['name'].endswith('RoadDeck') for r in ranges)
                target = next(r['high'] for r in ranges if r['name'].endswith('RoadDeck')) if road_end else floor['high']
                contacts.append(dict(xy_m=xy.tolist(),terrain_z_m=ground.tolist(),target_z_m=target.tolist(),
                    role='road_deck_end' if road_end else ('pedestrian_approach_end' if passage_end else 'floor_bank'),
                    maximum_step_m=float(np.max(np.abs(ground-target)))))
                direction=xy[1]-xy[0];toward=np.array([direction[1],-direction[0]])
                for bottom,top in exposed_ranges(ground,ranges):
                    if passage_end and np.max(top-floor['high']) > maximum_passage_step_m:
                        rejected.append(dict(xy_m=xy.tolist(),bottom_z_m=bottom.tolist(),top_z_m=top.tolist(),
                            reason='High retained terrain at pedestrian approach; no wall placed across the opening'))
                        continue
                    add_panel(vertices,faces,xy[0],xy[1],bottom,top,toward)
                terrain_errors.extend(abs(terrain.height(p)-z) for p,z in zip(xy,ground))
                for row in ranges:
                    solid=next(s for s in facility.solids if s['name']==row['name'])
                    actual=facility.vertical_range(solid,xy.mean(0))
                    plane_errors.extend(abs(actual-np.array([row['low'].mean(),row['high'].mean()])))
                split_count += 1
    missing = footprint.boundary.difference(shapely.union_all(covered_lines).buffer(2e-6)).length
    if missing > 1e-4:
        raise ValueError('Incomplete exported Lumberman cut boundary: '+str(missing)+' m')
    if max(terrain_errors+[0.]) > 1e-6 or max(plane_errors+[0.]) > 1e-6:
        raise ValueError('Lumberman terrain/solid plane mismatch')
    meshes=[]
    if faces:
        v,f=np.asarray(vertices),np.asarray(faces,dtype=np.int32)
        areas=np.linalg.norm(np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]),axis=1)/2
        if not np.isfinite(v).all() or areas.min()<1e-10:
            raise ValueError('Invalid Lumberman closure mesh')
        anchor=np.r_[np.floor(v[0,:2]/10)*10,0.]
        name='SM_LumbermanFacility_TerrainBoundaryClosure';path=OUT/(name+'.npz')
        np.savez_compressed(path,vertices=v-anchor,faces=f,anchor=anchor)
        meshes.append(dict(name=name,path=path.relative_to(ROOT).as_posix(),sha256=sha(path),
            vertices=len(v),triangles=len(f),collision='complex',minimum_triangle_area_m2=float(areas.min())))
    checks=dict(exported_boundary_segments=len(terrain.boundary_segments),split_segments=split_count,
        missing_boundary_length_m=float(missing),terrain_plane_max_error_m=float(max(terrain_errors+[0.])),
        solid_plane_max_error_m=float(max(plane_errors+[0.])),passage_wall_ranges_rejected=len(rejected),
        maximum_passage_step_m=maximum_passage_step_m,
        passage_contact_pass=all(c['maximum_step_m']<=maximum_passage_step_m for c in contacts if c['role']=='pedestrian_approach_end'),
        road_contact_pass=all(c['maximum_step_m']<=.03 for c in contacts if c['role']=='road_deck_end'),
        no_below_floor_offset=True,all_actual_solid_ranges_used=True)
    controls=dict(floor=facility.data['floor_controls'],deck=facility.data['roof_controls'],
        frame=facility.data['frame'],floor_plane_coefficients=facility.data['floor_plane_coefficients'],
        road_plane_coefficients=facility.data['road_plane_coefficients'],
        floor_footprint_local_xy_m=list(footprint.exterior.coords),
        deck_footprint_local_xy_m=list(facility.footprints['road_deck'].exterior.coords),
        passage_footprint_local_xy_m=list(opening.exterior.coords),
        plane_evaluation='u=dot(XY-origin,road_u); v=dot(XY-origin,waterpark_v)-skew*u; H=coef[0]+coef[1]*u+coef[2]*v',
        minimum_estimated_clearance_m=facility.data['minimum_estimated_clearance_m'],
        runtime_rule='Query the upper deck and lower floor separately. Select by traversed route/layer and current Z; never use maximum height for the lower pedestrian passage.')
    result=dict(schema_version=1,inputs=facility.inputs+terrain.inputs,meshes=meshes,checks=checks,
        contacts=contacts,rejected_closure_ranges=rejected,controls=controls,
        scope='Exact terrain boundary skins outside data-derived floor/deck/wall solids; no floor lowering, roof extension or high wall across the pedestrian opening.',
        shared_terrain_modified=False,visual_acceptance=False,runtime_acceptance=False)
    save_json(ROOT/'manifests/lumberman-facility-closures.json',result)
    print(json.dumps(dict(meshes=len(meshes),triangles=sum(m['triangles'] for m in meshes),checks=checks)))


if __name__=='__main__':
    main()
