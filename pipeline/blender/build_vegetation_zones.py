"""Keep dated vegetation boundaries editable and inspectable in Blender.

These reference curves are hidden by default and are not exported to Unreal.
Canopy materials/forms use the same zone assignment manifest.
"""
import json
from pathlib import Path
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
collection=bpy.data.collections.get('SP_06_VegetationZoneReferences')
if collection is None:
    collection=bpy.data.collections.new('SP_06_VegetationZoneReferences')
    scene.collection.children.link(collection)
for obj in list(collection.objects):
    if obj.get('pipeline_owner')=='vegetation_zones':
        curve=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if curve.users==0:bpy.data.curves.remove(curve)
grid=np.load(ROOT/'data/derived/terrain_2022_park.npz')
data=json.loads((ROOT/'data/derived/vegetation-zones-local.geojson').read_text())
created=[]
for feature in data['features']:
    props=feature['properties'];geom=feature['geometry']
    polygons=geom['coordinates'] if geom['type']=='MultiPolygon' else [geom['coordinates']]
    curve=bpy.data.curves.new('REF_'+props['id'],'CURVE');curve.dimensions='3D'
    for polygon in polygons:
        for ring in polygon:
            points=np.asarray(ring)[:,:2]
            # Reference outlines follow nearest measured terrain samples only.
            xi=np.clip(np.searchsorted(grid['x'],points[:,0]),0,len(grid['x'])-1)
            yi=np.clip(np.searchsorted(grid['y'],points[:,1]),0,len(grid['y'])-1)
            height=grid['z'][yi,xi]
            height=np.where(np.isfinite(height),height,0)+.5
            spline=curve.splines.new('POLY');spline.points.add(len(points)-1)
            spline.points.foreach_set('co',np.column_stack((points,height,np.ones(len(points)))).ravel())
            spline.use_cyclic_u=True
    obj=bpy.data.objects.new('REF_'+props['id'],curve);collection.objects.link(obj)
    obj['pipeline_owner']='vegetation_zones';obj['source_id']='BC VRI: '+props['id']
    obj['reference_date']=props['reference_date'] or 'Unknown'
    obj['interpretation_date']=props['interpretation_date'] or 'Unknown'
    obj['projected_date']=props['projected_date'] or 'Unknown'
    obj['primary_cover_code']=props['primary_cover_code']
    obj['species_groups']=json.dumps(props['species'])
    obj['accepted_2026_condition']=False
    obj['display_height_note']='Terrain-following review line, +0.5 m; not measured vegetation height'
    obj.hide_render=True;obj.hide_set(True);created.append(obj.name)
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
result=dict(reference_curves=len(created),names=created,exported_to_engine=False)
