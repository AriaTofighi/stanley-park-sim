"""Clip extra named M1 grounds to current actual terrain; no app operations."""
import json
import numpy as np
import shapely
from shapely.geometry import Polygon, shape
from build_public_space_meshes import ROOT, digest, save, mesh_footprint, clip_patch, LIFT

OUT = ROOT/'data/derived/ground-spaces/meshes'
COLORS = {'golf_green':[.24,.39,.16,1], 'golf_tee':[.29,.39,.18,1],
    'garden_lawn':[.29,.38,.18,1], 'garden_understorey':[.24,.31,.15,1],
    'garden_bed':[.24,.19,.11,1], 'garden_path':[.50,.47,.38,1],
    'wetland':[.28,.34,.12,1], 'pond_water':[.14,.24,.25,1],
    'rail':[.29,.30,.28,1], 'track_bed':[.30,.28,.25,1],
    'public_lawn':[.30,.38,.18,1], 'public_concrete':[.50,.49,.45,1],
    'stream_bed':[.24,.27,.22,1], 'play_rubber':[.16,.17,.16,1]}


def above_level_polygon(triangle, level, above=True):
    """Exact linear triangle split at a stated water threshold."""
    result=[]
    for a,b in zip(triangle, np.roll(triangle,-1,axis=0)):
        ia=(a[2]>=level) if above else (a[2]<=level)
        ib=(b[2]>=level) if above else (b[2]<=level)
        if ia: result.append(a[:2])
        if ia != ib:
            t=(level-a[2])/(b[2]-a[2]);result.append((a+t*(b-a))[:2])
    return Polygon(result) if len(result)>=3 else Polygon()


def main(source_relative='manifests/ground-space-sources.json', output_relative='manifests/ground-space-blockouts.json',
         mesh_directory='data/derived/ground-spaces/meshes', evidence_relative='evidence/ground-spaces/mesh-checks.json', prefix='SM_Ground_'):
    source_path=ROOT/source_relative
    out=ROOT/mesh_directory
    source=json.loads(source_path.read_text(encoding='utf8'))
    geometry_path=ROOT/source['authoring_geometry']
    features=json.loads(geometry_path.read_text(encoding='utf8'))['features']
    surface_path=ROOT/'manifests/surface-model.json'
    surface=json.loads(surface_path.read_text(encoding='utf8'))
    walking_path=ROOT/'data/routes/derived/pedestrian-surfaces.json'
    walk=json.loads(walking_path.read_text(encoding='utf8'))
    previous_path=ROOT/'data/derived/public-spaces/public-space-meshes.json'
    previous=json.loads(previous_path.read_text(encoding='utf8'))
    inputs=[source_path,geometry_path,surface_path,walking_path,previous_path]
    mask_inputs=[]
    masks={
        'main_pavement':mesh_footprint([r for r in surface['pavement'] if r['role']=='pavement'],mask_inputs).buffer(.025),
        'road_and_branch':mesh_footprint(surface['routes'],mask_inputs).buffer(.025),
        'walking':mesh_footprint(walk['meshes'],mask_inputs).buffer(.025),
        'existing_public_spaces':mesh_footprint(previous['meshes'],mask_inputs).buffer(.005)}
    for key,path in [('water','data/derived/lake-surfaces.geojson'),('underpass_holes','data/derived/underpass-openings.geojson')]:
        p=ROOT/path;inputs.append(p)
        masks[key]=shapely.union_all([shape(f['geometry']) for f in json.loads(p.read_text(encoding='utf8'))['features']])
    cover_path=ROOT/'data/derived/cover-blockout.json';inputs.append(cover_path)
    cover=json.loads(cover_path.read_text(encoding='utf8'))
    masks['building_roofs']=shapely.union_all([shapely.make_valid(Polygon(r['outline'])) for r in cover['buildings']]).buffer(.025)
    masks['replacement_cuts']=shapely.union_all([Polygon(r['footprint_local_m']) for r in surface['landmark_cuts'] if 'footprint_local_m'in r])
    all_mask=shapely.union_all(list(masks.values()))
    no_water=shapely.union_all([v for k,v in masks.items() if k!='water'])
    rows={f['properties']['component_id']:f['properties'] for f in features}
    patches={};occupied=shapely.GeometryCollection();summaries=[]
    for f in sorted(features,key=lambda f:f['properties']['priority']):
        p=f['properties'];original=shape(f['geometry']);mask=all_mask if p.get('water_mask',True) else no_water
        if p.get('internal_play_surface'):
            mask=shapely.union_all([v for k,v in masks.items() if k!='existing_public_spaces'])
        patch=original.difference(mask)
        if not p.get('source_basin_underlay'):patch=patch.difference(occupied)
        patches[p['component_id']]=patch;occupied=occupied.union(patch)
        summaries.append(dict(component_id=p['component_id'],feature_id=p['feature_id'],source_area_m2=original.area,
            authoring_area_m2=patch.area,rendered_area_m2=0.,minimum_terrain_z_m=None,maximum_terrain_z_m=None,
            masked_area_m2=original.area-patch.area,exclusion_overlap_m2=patch.intersection(mask).area))
    by_id={r['component_id']:r for r in summaries}
    meshes=[];terrain_inputs=[];maximum_error=0.
    out.mkdir(parents=True,exist_ok=True)
    for terrain in surface['terrain']:
        path=ROOT/terrain['path']
        if digest(path)!=terrain['sha256']:raise ValueError('Terrain changed; repeat: '+str(path))
        with np.load(path) as pack:
            anchor=pack['anchor'].astype(float);triangles=(pack['vertices'].astype(float)+anchor)[pack['faces']]
        polygons=shapely.polygons(triangles[:,:,:2]);tree=shapely.STRtree(polygons)
        for key,footprint in patches.items():
            p=rows[key];indices=tree.query(footprint,predicate='intersects')
            if not len(indices):continue
            z=triangles[indices,:,2]
            summary=by_id[key]
            lo,hi=float(z.min()),float(z.max())
            summary['minimum_terrain_z_m']=lo if summary['minimum_terrain_z_m']is None else min(lo,summary['minimum_terrain_z_m'])
            summary['maximum_terrain_z_m']=hi if summary['maximum_terrain_z_m']is None else max(hi,summary['maximum_terrain_z_m'])
            if 'minimum_z'in p:
                footprint=footprint.intersection(shapely.union_all([above_level_polygon(t,p['minimum_z']) for t in triangles[indices]]))
            if 'water_z'in p:
                footprint=footprint.intersection(shapely.union_all([above_level_polygon(t,p['water_z'],False) for t in triangles[indices]]))
            v,f,error,_=clip_patch(triangles,polygons,tree,footprint,anchor)
            if not len(f):continue
            maximum_error=max(maximum_error,error)
            if 'water_z'in p:v[:,2]=p['water_z']+.025-anchor[2]
            if p.get('internal_play_surface'):v[:,2]+=.025
            name=prefix+key+'_'+path.stem.removeprefix('SM_Terrain_')
            target=out/(name+'.npz');color=COLORS[p['material_role']]
            np.savez_compressed(target,vertices=v,faces=f,anchor=anchor,colors=np.tile(color,(len(v),1)).astype(np.float32))
            area=float(shapely.area(shapely.polygons((v+anchor)[f,:2])).sum());summary['rendered_area_m2']+=area
            meshes.append(dict(name=name,path=target.relative_to(ROOT).as_posix(),sha256=digest(target),
                component_id=key,feature_id=p['feature_id'],m1_group=p['m1_group'],material_role=p['material_role'],material_color=color,
                vertices=len(v),triangles=len(f),area_xy_m2=area,contact_surface=terrain['path'],visual_lift_m=.025 if 'water_z'in p else LIFT+(.025 if p.get('internal_play_surface') else 0),
                collision=False,source=p['source'],limit=p.get('limit'),absolute_accuracy_accepted=False,release_accepted=False))
        terrain_inputs.append({'path':terrain['path'],'sha256':terrain['sha256']})
    record=dict(schema_version=1,source_manifest=source_path.relative_to(ROOT).as_posix(),source_manifest_sha256=digest(source_path),
        source_inputs=[{'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p)} for p in inputs],exclusion_mesh_inputs=mask_inputs,terrain_inputs=terrain_inputs,
        meshes=meshes,components=summaries,unresolved=source['unresolved'],reference_only=source['references'],
        attribution=['© OpenStreetMap contributors','Contains information licensed under the Open Government Licence - Vancouver.'],
        licence=source['licence'],application_visual_check='pending',full_m1_groups_complete=False,release_accepted=False)
    save(ROOT/output_relative,record)
    checks=dict(kind='Source mesh numerical construction check; not an application test',meshes=len(meshes),components=len(summaries),
        triangles=sum(m['triangles'] for m in meshes),maximum_terrain_offset_error_m=maximum_error,
        exclusion_overlap_m2=sum(r['exclusion_overlap_m2'] for r in summaries),
        empty_components=[r['component_id'] for r in summaries if r['rendered_area_m2']<1e-8],
        special_water_components=[r for r in summaries if r['component_id'].startswith('Biofilter')],
        numerical_pass=maximum_error<1e-7 and sum(r['exclusion_overlap_m2'] for r in summaries)<1e-7,visual_check='pending')
    save(ROOT/evidence_relative,checks);print(json.dumps(checks,indent=2))


if __name__=='__main__':main()
