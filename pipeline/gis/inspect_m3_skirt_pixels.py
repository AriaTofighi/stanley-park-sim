"""Attribute reviewed dark pixels to unchanged source meshes or actual skirt FBX."""
from pathlib import Path
import importlib.util,json,math,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
fbx=module('fbx_arrays','pipeline/gis/inspect_m3_skirt_normals.py')
original=module('original_pixels','pipeline/gis/inspect_m3_edge_pixels.py')

def run():
    pointer=json.loads((ROOT/'exports/m3-edge-skirts/latest.json').read_text());source=json.loads((ROOT/pointer['manifest']).read_text());meshes=[]
    for item in source['assets']:
        arrays=fbx.fbx_arrays(ROOT/item['fbx']);v=arrays['Vertices'].reshape(-1,3);v=np.c_[-v[:,1],v[:,0],v[:,2]]/100+item['anchor_local_m'];f=arrays['PolygonVertexIndex'];f=np.where(f<0,-f-1,f).reshape(-1,3);a=v[f[:,0]];meshes.append((item,a,v[f[:,1]]-a,v[f[:,2]]-a))
    cases=[('midpoint','017',[(725,562),(741,547),(557,745)]),('midpoint','028',[(1052,674),(1050,665),(847,592),(922,566)]),('boundary','028',[(451,781),(1073,837)]),('boundary','020',[(700,645)]),('midpoint','011',[(529,715),(532,700)])]
    exported_names={a['name'] for a in json.loads((ROOT/'manifests/blender-export.json').read_text())['assets']}
    rows=[]
    for kind,number,pixels in cases:
        image=f'evidence/m3-views/m3-v2-priority/{kind}/section_{number}.png';row=original.trace(image,pixels);capture=json.loads((ROOT/image.replace('.png','.json')).read_text())['viewport_capture'];c=capture['cameraLocation'];r=capture['cameraRotation'];w,h=capture['decoded_png_dimensions_px'];o=np.array([c['y'],c['x'],c['z']])/100;pitch,yaw=np.radians([r['pitch'],r['yaw']]);forward=np.array([np.cos(pitch)*np.cos(yaw),np.cos(pitch)*np.sin(yaw),np.sin(pitch)]);right=np.array([-np.sin(yaw),np.cos(yaw),0]);up=np.cross(forward,right)
        for pixel in row['pixels']:
            pixel['excluded_unexported_source_hits']=[h for h in pixel['nearest_source_hits'] if h['name'] not in exported_names]
            pixel['nearest_source_hits']=[h for h in pixel['nearest_source_hits'] if h['name'] in exported_names]
            px,py=pixel['pixel'];ray=forward+right*((px+.5-w/2)/(w/2))*math.tan(math.radians(capture['cameraFOV']/2))-up*((py+.5-h/2)/(w/2))*math.tan(math.radians(capture['cameraFOV']/2));ray=ray[[1,0,2]];ray/=np.linalg.norm(ray);hits=[]
            for item,a,e1,e2 in meshes:
                p=np.cross(np.broadcast_to(ray,e2.shape),e2);det=(e1*p).sum(1);inv=np.divide(1,det,out=np.zeros_like(det),where=np.abs(det)>1e-10);tv=o-a;u=(tv*p).sum(1)*inv;q=np.cross(tv,e1);v=(q*ray).sum(1)*inv;t=(q*e2).sum(1)*inv;good=(np.abs(det)>1e-10)&(u>=0)&(v>=0)&(u+v<=1)&(t>.001)
                if good.any():
                    index=int(np.flatnonzero(good)[t[good].argmin()]);distance=float(t[index]);normal=np.cross(e1[index],e2[index]);normal/=np.linalg.norm(normal);hits.append(dict(name=item['name'],distance_m=distance,point_local_m=(o+ray*distance).tolist(),normal_z=float(normal[2]),ray_dot_normal=float(np.dot(ray,normal)),source=item['fbx'],sha256=item['sha256'],rendering='Two-sided material'))
            pixel['nearest_skirt_hits']=sorted(hits,key=lambda x:x['distance_m'])[:2]
            ordered=sorted(pixel['nearest_source_hits']+pixel['nearest_skirt_hits'],key=lambda x:x['distance_m']);pixel['nearest_surface']=ordered[0] if ordered else None
        rows.append(row)
    output=dict(source_presence_filter='Only names in manifests/blender-export.json are included. Retired main-route NPZ files are excluded.',method='Source NPZ and actual versioned FBX ray intersections for pixels selected from opened paired views; no editor action.',captures=rows,scope='Surface attribution only. Does not replace repeat image review after correction.')
    (ROOT/'evidence/m3-v2-edge-pixel-attribution.json').write_text(json.dumps(output,indent=2))
    for row in rows:
        print(row['image'])
        for pixel in row['pixels']:print(pixel['pixel'],pixel['nearest_surface']['name'] if pixel['nearest_surface'] else None,pixel['nearest_surface'].get('normal_z') if pixel['nearest_surface'] else None)
if __name__=='__main__':run()
