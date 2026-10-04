"""Source-only ray attribution for retained M3 pixels. Does not run an editor."""
from pathlib import Path
import json, hashlib, math
import numpy as np
ROOT=Path(__file__).resolve().parents[2]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def trace(image, pixels):
    metadata=ROOT/image.replace('.png','.json')
    capture=json.loads(metadata.read_text())['viewport_capture']
    c=capture['cameraLocation']; r=capture['cameraRotation']; w,h=capture['decoded_png_dimensions_px']
    o=np.array([c['x'],c['y'],c['z']])/100
    pitch,yaw=np.radians([r['pitch'],r['yaw']])
    f=np.array([np.cos(pitch)*np.cos(yaw),np.cos(pitch)*np.sin(yaw),np.sin(pitch)])
    right=np.array([-np.sin(yaw),np.cos(yaw),0]); up=np.cross(f,right)
    out=[]
    for px,py in pixels:
        ray=f+right*((px+.5-w/2)/(w/2))*math.tan(math.radians(capture['cameraFOV']/2))-up*((py+.5-h/2)/(w/2))*math.tan(math.radians(capture['cameraFOV']/2))
        ray=ray[[1,0,2]]; ray/=np.linalg.norm(ray); origin=o[[1,0,2]]
        hits=[]
        for folder in ['data/derived/surface-meshes','data/routes/derived/pedestrian-meshes']:
            for path in (ROOT/folder).glob('*.npz'):
                mesh=np.load(path); verts=mesh['vertices']+mesh['anchor']; faces=mesh['faces']
                if 'Pedestrian' in path.name: pass
                a=verts[faces[:,0]]; e1=verts[faces[:,1]]-a; e2=verts[faces[:,2]]-a
                p=np.cross(np.broadcast_to(ray,e2.shape),e2); det=(e1*p).sum(1)
                inv=np.divide(1,det,out=np.zeros_like(det),where=np.abs(det)>1e-10)
                tv=origin-a; u=(tv*p).sum(1)*inv; q=np.cross(tv,e1); v=(q*ray).sum(1)*inv; t=(q*e2).sum(1)*inv
                good=(np.abs(det)>1e-10)&(u>=0)&(v>=0)&(u+v<=1)&(t>.001)
                if good.any():
                    distance=float(t[good].min()); hits.append(dict(name=path.stem,distance_m=distance,point_local_m=(origin+ray*distance).tolist(),source=path.relative_to(ROOT).as_posix(),sha256=sha(path)))
        hits.sort(key=lambda a:a['distance_m'])
        out.append(dict(pixel=[px,py],nearest_source_hits=hits[:4]))
    return dict(image=image,image_sha256=sha(ROOT/image),camera_record_sha256=sha(metadata),pixels=out)
if __name__=='__main__':
    rows=[trace('evidence/m3-views/m3-v1/midpoint/section_000.png',[(1100,592),(1435,822),(1000,535)]),trace('evidence/m3-views/m3-v1/midpoint/section_002.png',[(1250,800),(200,404)])]
    output=ROOT/'evidence/m3-edge-pixel-attribution.json'
    output.write_text(json.dumps(dict(method='Offline ray intersections with source NPZ; intended attribution requires live actor confirmation if geometry differs.',captures=rows),indent=2))
    print(json.dumps(rows,indent=2))
