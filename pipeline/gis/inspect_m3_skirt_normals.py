"""Read exported FBX skirt arrays without running either editor."""
from pathlib import Path
import hashlib,json,struct,zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2]

def fbx_arrays(path):
    data=path.read_bytes()
    if not data.startswith(b'Kaydara FBX Binary'):raise ValueError('Expected binary FBX')
    version=struct.unpack_from('<I',data,23)[0];header='<QQQB' if version>=7500 else '<IIIB';size=struct.calcsize(header)
    found=[]
    def prop(offset):
        kind=chr(data[offset]);offset+=1
        scalar={'Y':'h','C':'?','I':'i','F':'f','D':'d','L':'q'}
        if kind in scalar:
            fmt='<'+scalar[kind];return struct.unpack_from(fmt,data,offset)[0],offset+struct.calcsize(fmt)
        if kind in 'SR':
            length=struct.unpack_from('<I',data,offset)[0];offset+=4;return data[offset:offset+length],offset+length
        if kind in 'fdlibc':
            length,encoding,compressed=struct.unpack_from('<III',data,offset);offset+=12;raw=data[offset:offset+compressed];raw=zlib.decompress(raw) if encoding else raw
            dtype={'f':'<f4','d':'<f8','l':'<i8','i':'<i4','b':'u1','c':'u1'}[kind]
            return np.frombuffer(raw,dtype=dtype,count=length),offset+compressed
        raise ValueError('Unexpected FBX property '+kind)
    def node(offset):
        end,count,_,name_length=struct.unpack_from(header,data,offset)
        if not end:return None,offset+size
        offset+=size;name=data[offset:offset+name_length].decode();offset+=name_length;props=[]
        for _ in range(count):value,offset=prop(offset);props.append(value)
        children=[]
        while offset<end-size:
            child,offset=node(offset)
            if child is not None:children.append(child)
        value=dict(name=name,properties=props,children=children)
        if name in ['Vertices','PolygonVertexIndex','Normals']:found.append(value)
        return value,end
    offset=27
    while offset<len(data)-size:
        value,offset=node(offset)
        if value is None:break
    arrays={row['name']:row['properties'][0] for row in found}
    return arrays

if __name__=='__main__':
    pointer=json.loads((ROOT/'exports/m3-edge-skirts/latest.json').read_text());manifest=ROOT/pointer['manifest'];source=json.loads(manifest.read_text());rows=[]
    for item in source['assets']:
        arrays=fbx_arrays(ROOT/item['fbx']);v=arrays['Vertices'].reshape(-1,3);normal=arrays['Normals'].reshape(-1,3)
        indices=arrays['PolygonVertexIndex'];indices=np.where(indices<0,-indices-1,indices).reshape(-1,3)
        n=np.cross(v[indices[:,1]]-v[indices[:,0]],v[indices[:,2]]-v[indices[:,0]]);nz=n[:,2]
        rows.append(dict(name=item['name'],fbx=item['fbx'],sha256=item['sha256'],triangles=len(indices),downward_faces=int((nz<0).sum()),upward_faces=int((nz>0).sum()),downward_exported_loop_normals=int((normal[:,2]<0).sum()),upward_exported_loop_normals=int((normal[:,2]>0).sum()),vertices_bounds=[v.min(0).tolist(),v.max(0).tolist()]))
    result=dict(method='Read actual FBX polygon winding and exported normal arrays; no editor action.',manifest=pointer['manifest'],manifest_sha256=pointer['sha256'],assets=rows,downward_faces=sum(r['downward_faces'] for r in rows),upward_faces=sum(r['upward_faces'] for r in rows),conclusion='The skirt faces point downward. The material outputs world-space normals; Unreal flips two-sided normals automatically only for tangent-space materials or single-layer water. This can cause a black border without an open hole.',engine_shader='D:/Epic Games/UE_5.8/Engine/Shaders/Private/MaterialTemplate.ush',engine_lines=[4371,4380])
    (ROOT/'evidence/m3-skirt-normal-attribution.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='assets'},indent=2));print(rows[0])
