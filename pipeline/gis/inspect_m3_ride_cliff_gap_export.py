"""Check actual exported gap faces against exact pre-repair editor image rays."""
from pathlib import Path
import importlib.util
import json
import math
import numpy as np

ROOT=Path(__file__).resolve().parents[2]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def run():
    ray_module=module('ride_gap_rays','pipeline/gis/inspect_m3_ride_cliff_gaps.py')
    fbx=module('ride_gap_fbx','pipeline/gis/inspect_m3_skirt_normals.py')
    pointer=json.loads((ROOT/'exports/m3-ride-cliff-gaps/latest.json').read_text())
    manifest=json.loads((ROOT/pointer['manifest']).read_text())
    meshes=[]
    for name in ['SM_Terrain_05_01','SM_PavementSupport_030','SM_Terrain_01_03','SM_PavementSupport_048']:
        path=ROOT/'data/derived/surface-meshes'/(name+'.npz')
        data=np.load(path)
        meshes.append((name,path,data['vertices']+data['anchor'],data['faces']))
    patches=[]
    for item in manifest['assets']:
        path=ROOT/item['fbx']
        arrays=fbx.fbx_arrays(path)
        v=arrays['Vertices'].reshape(-1,3)
        v=np.c_[-v[:,1],v[:,0],v[:,2]]/100+item['anchor_local_m']
        faces=arrays['PolygonVertexIndex']
        faces=np.where(faces<0,-faces-1,faces).reshape(-1,3)
        patches.append((item['name'],path,v,faces))
    rows=[]
    cases=[('008764',[(204,208),(568,471)]),('008767',[(369,527)]),('013765',[(1423,581)])]
    for ident,pixels in cases:
        path=ROOT/'evidence/m3-views/m3-v4-ride-gaps-before/route'/('cliff_gap_route_frame_'+ident+'.png')
        metadata=path.with_suffix('.json')
        record=json.loads(metadata.read_text())
        capture=record['viewport_capture']
        c=capture['cameraLocation'];r=capture['cameraRotation']
        origin=np.array([c['y'],c['x'],c['z']])/100
        pitch,yaw=np.radians([r['pitch'],r['yaw']])
        forward=np.array([np.cos(pitch)*np.cos(yaw),np.cos(pitch)*np.sin(yaw),np.sin(pitch)])
        right=np.array([-np.sin(yaw),np.cos(yaw),0.]);up=np.cross(forward,right)
        w,h=capture['decoded_png_dimensions_px']
        row=dict(image=path.relative_to(ROOT).as_posix(),image_sha256=ray_module.sha(path),metadata_sha256=ray_module.sha(metadata),pixels=[])
        for x,y in pixels:
            ray=forward+right*((x+.5-w/2)/(w/2))*math.tan(math.radians(capture['cameraFOV']/2))-up*((y+.5-h/2)/(w/2))*math.tan(math.radians(capture['cameraFOV']/2))
            ray=ray[[1,0,2]];ray/=np.linalg.norm(ray)
            source_hits=ray_module.ray_hits(origin,ray,meshes)
            patch_hits=ray_module.ray_hits(origin,ray,patches)
            row['pixels'].append(dict(pixel=[x,y],source_hits=source_hits,exported_patch_hits=patch_hits,patch_closes_ray=bool(patch_hits and not any(q['front_facing'] and q['distance_m']<patch_hits[0]['distance_m']-.005 for q in source_hits))))
        rows.append(row)
    output=dict(scope='Offline ray intersections with source NPZ and actual saved FBX for pixels in opened exact-camera editor images. This supports source attribution; it does not replace post-import image or ride review.',manifest=pointer['manifest'],manifest_sha256=pointer['sha256'],all_selected_gap_rays_closed=all(p['patch_closes_ray'] for r in rows for p in r['pixels']),frames=rows)
    path=ROOT/'evidence/m3-ride-cliff-gap-export-ray-check.json'
    path.write_text(json.dumps(output,indent=2)+'\n')
    return output


if __name__=='__main__':
    result=run()
    print('All selected gap rays closed:',result['all_selected_gap_rays_closed'])
    for row in result['frames']:
        print(row['image'])
        for pixel in row['pixels']:
            print(pixel['pixel'],[(h['name'],h['face_index'],round(h['distance_m'],3)) for h in pixel['exported_patch_hits'][:2]])
