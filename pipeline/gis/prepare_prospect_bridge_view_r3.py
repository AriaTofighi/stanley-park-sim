"""Source-based terrace-to-bridge camera; no scene or application changes."""
import json
from pathlib import Path
import numpy as np
from shapely.geometry import Point, Polygon

from prepare_route_inspection_views_r3 import crown_clear, hashed, index_rows, read
from propose_ground_review_cameras import Rays, Surface, cover_triangles, in_bounds, mesh

ROOT=Path(__file__).resolve().parents[2]


def angular_extent(eye,target,points):
    forward=target-eye;forward/=np.linalg.norm(forward)
    right=np.cross(forward,[0.,0.,1.]);right/=np.linalg.norm(right)
    up=np.cross(right,forward)
    delta=points-eye;depth=delta@forward
    return dict(horizontal_degrees=float(2*np.degrees(np.arctan(np.max(abs(delta@right)/depth)))),
        vertical_degrees=float(2*np.degrees(np.arctan(np.max(abs(delta@up)/depth)))))


def main():
    bounds=[-150,1050,610,1830]
    bridge=read('manifests/lions-gate-blockout.json')
    axis=np.array(bridge['axis_unit']);origin=np.array(bridge['axis_origin_local_m'])
    sample_rows=[]
    for tower in bridge['towers']:
        sample_rows.append(dict(label='Tower top station '+str(tower['station_m']),point=[*(origin+axis*tower['station_m']),tower['top_m']]))
    for s in [0.,80.,236.,390.,bridge['tower_span_m']]:
        z=np.interp(s,bridge['stations_m'],bridge['deck_heights_m'])
        sample_rows.append(dict(label='Deck station '+str(s),point=[*(origin+axis*s),z+.3]))
    samples=np.array([r['point'] for r in sample_rows])
    index,replaced={},set()
    for path in (ROOT/'manifests').glob('*.json'):
        try:data=json.loads(path.read_text(encoding='utf-8-sig'))
        except (UnicodeError,json.JSONDecodeError):continue
        index_rows(data,index)
        if isinstance(data,dict):
            for feature in data.get('features',[]):replaced.update(feature.get('replace_cover_ids',[]))
    terrace=index['SM_ProspectLookout_TerraceSurvey']
    terrace_surface=Surface([terrace],bounds)
    surface=read('manifests/surface-model.json')
    ground=Surface(surface['terrain']+surface['pavement'],bounds)
    cover=read('data/derived/cover-blockout.json')
    zones={r['tile']:r['clusters'] for r in read('data/derived/canopy-zone-assignments.json')['assignments']}
    cover_mesh,crowns,buildings=cover_triangles(cover,zones,bounds,replaced)
    triangles=[ground.triangles,cover_mesh];inputs=list(ground.inputs)
    for asset in read('manifests/blender-export.json')['assets']:
        if not asset.get('place_in_level') or asset['name'] not in index:continue
        pos=np.array(asset['position_cm']);lo=(pos+asset['bounds_min_cm'])[[1,0]]/100;hi=(pos+asset['bounds_max_cm'])[[1,0]]/100
        if hi[0]<bounds[0] or hi[1]<bounds[1] or lo[0]>bounds[2] or lo[1]>bounds[3]:continue
        row=index[asset['name']];tri=mesh(row['path']);tri=tri[in_bounds(tri,bounds)]
        if len(tri):triangles.append(tri);inputs.append(hashed(row['path']))
    rays=Rays(np.concatenate(triangles));candidates=[]
    for x in [64.,67.,70.,73.,76.,78.]:
        for y in [1243.,1245.,1247.,1249.]:
            z=terrace_surface.height([x,y])
            if not np.isfinite(z):continue
            eye=np.array([x,y,z+1.7]);clear,margin=crown_clear(eye,crowns,zones)
            if not clear:continue
            sample_clear=[bool(rays.clear(eye,p)) for p in samples]
            if not all(sample_clear):continue
            # Aim between the two tower bearings, near deck level, so the
            # terrace parapet can remain in the wide view's lower foreground.
            unit=(samples[:2,:2]-eye[:2]);unit/=np.linalg.norm(unit,axis=1)[:,None]
            direction=unit.mean(0);direction/=np.linalg.norm(direction)
            target=np.r_[eye[:2]+direction*300,70.]
            extent=angular_extent(eye,target,samples)
            candidates.append(dict(eye=eye.tolist(),target=target.tolist(),camera_terrace_height_m=float(z),
                camera_height_above_terrace_m=1.7,camera_crown_section_clearance_m=margin,
                selected_samples_clear=sample_clear,required_sample_fov=extent))
    legacy=np.array([-55.,1520.,75.]);legacy_ground=ground.height(legacy[:2]);lc,lm=crown_clear(legacy,crowns,zones)
    result=dict(schema_version=1,coordinates='Local east/north/up metres; CGVD2013 vertical datum',
        scope='One actual Prospect terrace eye toward Lions Gate Bridge. Camera preparation only; no app or geometry edits.',
        source_inputs=[hashed(p) for p in ['manifests/lions-gate-blockout.json','pipeline/blender/build_lions_gate.py',
            'manifests/named-feature-blockouts.json','manifests/blender-export.json','manifests/surface-model.json',
            'data/derived/cover-blockout.json','data/derived/canopy-zone-assignments.json']],
        legacy_west_view=dict(eye=legacy.tolist(),target=[350.,1450.,58.],
            terrain_height_m=float(legacy_ground) if np.isfinite(legacy_ground) else None,
            crown_clear=lc,crown_section_clearance_m=lm,
            on_terrace=False,scope='Elevated west-side overview; not a position on the authored terrace.'),
        views={},clear_candidates=len(candidates))
    if candidates:
        chosen=min(candidates,key=lambda r:r['required_sample_fov']['horizontal_degrees'])
        chosen.update(purpose='View both source-positioned bridge towers and main deck from the actual Prospect lookout terrace.',
            inspection_horizontal_fov_degrees=80.,
            inspection_vertical_fov_degrees_at_16_10=float(np.degrees(2*np.arctan(np.tan(np.radians(40.))/1.6))),
            inspection_blender_lens_mm_for_36mm_sensor=float(18./np.tan(np.radians(40.))),
            lens_application_required='Existing inspect_m1_view helpers do not apply these fields. Root must set a wide inspection lens/FOV for this capture; a narrow default view cannot accept both towers.',
            source_bridge_samples=sample_rows,local_source_inputs=list({r['path']:r for r in inputs}.values()),
            live_review_status='pending',accepted=False,
            limits=['Bridge member self-occlusion is not checked because its live Blender meshes are generated directly from the bridge manifest; the near terrain, named forms and source canopy are checked.',
                'Width, member thickness and footing envelope retain the M1 limits in the bridge source manifest.',
                'Seven clear rays do not prove the complete viewport, terrace foreground or all bridge surfaces are visible.'])
        result['views']['prospect_terrace_to_bridge_r3']=chosen
    else:result['unresolved']='No actual terrace eye clears every selected bridge ray. Keep the visibility limit; do not remove canopy.'
    result['helper']=hashed('pipeline/gis/prepare_prospect_bridge_view_r3.py')
    (ROOT/'manifests/m1-prospect-bridge-inspection-view-r3.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(clear_candidates=len(candidates),views={k:dict(eye=v['eye'],target=v['target'],required_fov=v['required_sample_fov']) for k,v in result['views'].items()},unresolved=result.get('unresolved')),indent=2))


if __name__=='__main__':main()
