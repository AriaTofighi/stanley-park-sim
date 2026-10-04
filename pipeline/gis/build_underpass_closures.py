"""Stitch underpass floor cuts to exact exported terrain, without longer roofs."""
import json
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, shape

from acquire_sources import ROOT, digest, save_json
from terrain_boundary_stitch import ExportedTerrainPatch


class MeshHeight:
    def __init__(self, items):
        triangles=[]
        for item in items:
            with np.load(ROOT/item['path']) as data:
                v=data['vertices']+data['anchor'];f=data['faces']
            normal=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]])
            triangles.append(v[f[normal[:,2]>1e-10]])
        self.triangles=np.concatenate(triangles)
        self.polygons=shapely.polygons(self.triangles[:,:,:2]);self.tree=shapely.STRtree(self.polygons)

    def height(self,xy):
        p=Point(xy);ids=self.tree.query(p.buffer(1e-5),predicate='intersects')
        ids=[i for i in ids if self.polygons[i].distance(p)<=1e-5]
        if not ids:raise ValueError(f'No exact replacement surface at {list(xy)}')
        tri=self.triangles[ids[0]]
        uv=np.linalg.solve(np.column_stack((tri[1,:2]-tri[0,:2],tri[2,:2]-tri[0,:2])),np.asarray(xy)-tri[0,:2])
        return float(tri[0,2]+uv@(tri[1:,2]-tri[0,2]))


def split_at_triangle_edges(line, surface):
    """Respect every plane change, rather than interpolating over a floor kink."""
    fractions=[]
    for index in surface.tree.query(line, predicate='intersects'):
        hits=line.intersection(surface.polygons[index].boundary)
        for hit in shapely.get_parts(hits):
            if hit.is_empty:continue
            if isinstance(hit,Point):
                fractions.append(line.project(hit)/line.length)
            elif isinstance(hit,LineString):
                fractions.extend(line.project(Point(p))/line.length for p in [hit.coords[0],hit.coords[-1]])
    return fractions


def add_panel(vertices,faces,a,b,bottom,top,toward):
    """Keep only the positive-height part and split its height-zero crossing."""
    a,b,bottom,top=map(lambda x:np.array(x,dtype=float,copy=True),(a,b,bottom,top))
    delta=top-bottom
    if max(delta)<=1e-7:return
    if min(delta)<0:
        alpha=delta[0]/(delta[0]-delta[1]);p=a+(b-a)*alpha
        lo=bottom[0]+alpha*(bottom[1]-bottom[0]);hi=top[0]+alpha*(top[1]-top[0])
        if delta[0]<0:a=p;bottom[0]=lo;top[0]=hi
        else:b=p;bottom[1]=lo;top[1]=hi
    corners=np.array([[*a,bottom[0]],[*b,bottom[1]],[*b,top[1]],[*a,top[0]]])
    for indices in ([0,1,2],[0,2,3]):
        tri=corners[indices]
        normal=np.cross(tri[1]-tri[0],tri[2]-tri[0])
        if np.linalg.norm(normal)<1e-9:continue
        if np.dot(normal[:2],toward)<0:tri=tri[::-1]
        start=len(vertices);vertices.extend(tri);faces.append([start,start+1,start+2])


def main():
    manifest_path='data/derived/underpass-blockouts.json'
    data=json.loads((ROOT/manifest_path).read_text(encoding='utf8'))
    footprints=json.loads((ROOT/data['openings_path']).read_text(encoding='utf8'))
    out=ROOT/'data/derived/underpasses';items=[];inputs={};checks=[]

    def store(name,site,role,vertices,faces):
        if not faces:return
        v,f=np.asarray(vertices),np.asarray(faces,dtype=np.int32)
        normal=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]])
        area=np.linalg.norm(normal,axis=1)*.5
        if not np.isfinite(v).all() or area.min()<1e-10:raise ValueError('Invalid underpass terrain stitch')
        anchor=np.r_[np.floor(v[0,:2]/10)*10,0.];path=out/(name+'.npz')
        np.savez_compressed(path,vertices=v-anchor,faces=f,anchor=anchor)
        items.append(dict(name=name,site=site,role=role,path=path.relative_to(ROOT).as_posix(),sha256=digest(path),
                          vertices=len(v),triangles=len(f),collision='complex',reference_only=False,
                          checks=dict(finite=True,minimum_triangle_area_m2=float(area.min()),horizontal_normals=int((abs(normal[:,2])<1e-8).sum()),
                                      method='Open vertical boundary stitch, not an invented watertight structure')))

    for feature in footprints['features']:
        name=feature['properties']['id'];polygon=shape(feature['geometry'])
        site=next(s for s in data['sites'] if s['id']==name)
        terrain=ExportedTerrainPatch(ROOT,polygon)
        inputs.update({i['path']:i for i in terrain.inputs})
        source=[m for m in data['meshes'] if m['site']==name and not m['reference_only']]
        floors=MeshHeight([m for m in source if m['role'].startswith('FloorExtension')])
        deck_item=next(m for m in source if m['role']=='Deck');deck=MeshHeight([deck_item])
        with np.load(ROOT/deck_item['path']) as p:
            v=(p['vertices']+p['anchor']).reshape(-1,4,3)
        roof=Polygon(np.vstack((v[:,0,:2],v[::-1,1,:2])))
        vertices,faces=[],[];floor_error=[];terrain_error=[];covered=0
        for segment in terrain.boundary_segments:
            a,b=segment;line=LineString([a[:2],b[:2]])
            # Split at actual roof footprint intersections before deciding which
            # vertical range is already occupied by the roof/sidewall solids.
            fractions=[0.,1.]
            hits=line.intersection(roof.boundary)
            for hit in shapely.get_parts(hits):
                if isinstance(hit,Point):fractions.append(line.project(hit)/line.length)
            fractions.extend(split_at_triangle_edges(line, floors))
            fractions.extend(split_at_triangle_edges(line, deck))
            fractions=sorted(set(round(x,12) for x in fractions))
            for lo,hi in zip(fractions,fractions[1:]):
                if hi-lo<1e-9:continue
                ends=np.stack((a+(b-a)*lo,a+(b-a)*hi));xy=ends[:,:2]
                floor=np.array([floors.height(p) for p in xy]);ground=ends[:,2]
                floor_error.append(abs(floors.height(xy.mean(0))-floor.mean()))
                under_roof=roof.covers(Point(xy.mean(0)))
                solid_top=np.array([deck.height(p) for p in xy]) if under_roof else floor
                solid_bottom=floor-(.2 if under_roof else .15)
                direction=xy[1]-xy[0];toward=np.array([direction[1],-direction[0]])
                # Terrain's directed boundary has terrain on the left and the
                # cavity on the right. All new faces point into that cavity.
                add_panel(vertices,faces,xy[0],xy[1],solid_top,ground,toward)
                add_panel(vertices,faces,xy[0],xy[1],ground,solid_bottom,toward)
                covered+=1
                terrain_error.extend(abs(terrain.height(p)-z) for p,z in zip(xy,ground))
        store(f'SM_Underpass_{name}_TerrainBoundaryClosure',name,'TerrainBoundaryClosure',vertices,faces)

        # A thick wall can extend beyond the cavity into a low DTM bank. Close
        # any exposed gap below its outside face; the riding bay is unchanged.
        foundation_count=0
        for side,outer_index in (('Right',0),('Left',1)):
            wall=next(m for m in source if m['role']=='Wall'+side)
            with np.load(ROOT/wall['path']) as p:
                rows=(p['vertices']+p['anchor']).reshape(-1,4,3)
            vertices,faces=[],[]
            outer=rows[:,outer_index]
            for a,b in zip(outer,outer[1:]):
                ground=np.array([terrain.height(a[:2]),terrain.height(b[:2])])
                direction=b[:2]-a[:2]
                toward=np.array([direction[1],-direction[0]])*(1 if side=='Right' else -1)
                add_panel(vertices,faces,a[:2],b[:2],ground,np.array([a[2],b[2]]),toward)
            # End caps span the existing wall thickness, not the open bicycle bay.
            for k in (0,-1):
                a,b=rows[k,0],rows[k,1]
                ground=np.array([terrain.height(a[:2]),terrain.height(b[:2])])
                direction=b[:2]-a[:2]
                toward=np.array([direction[1],-direction[0]])*(1 if k==0 else -1)
                add_panel(vertices,faces,a[:2],b[:2],ground,np.array([a[2],b[2]]),toward)
            foundation_count+=len(faces)
            store(f'SM_Underpass_{name}_WallFoundation{side}',name,'WallFoundation'+side,vertices,faces)
        if max(floor_error)>1e-6:
            raise ValueError(f'Floor boundary plane mismatch at {name}: {max(floor_error)}')
        if max(terrain_error)>1e-6:
            raise ValueError(f'Terrain boundary plane mismatch at {name}: {max(terrain_error)}')
        checks.append(dict(site=name,exported_terrain_boundary_segments=len(terrain.boundary_segments),
                           split_boundary_segments=covered,terrain_plane_max_error_m=float(max(terrain_error)),
                           floor_midpoint_max_error_m=float(max(floor_error)),
                           foundation_triangles=foundation_count,roof_span_changed=False,bay_width_changed=False,
                           floor_coverage_changed=False,source='Exact clipped terrain vertices and authored underpass floor/solid surfaces',
                           visual_acceptance=False))
    record=dict(schema_version=1,underpass_manifest=manifest_path,underpass_sha256=digest(ROOT/manifest_path),
                inputs=list(inputs.values()),meshes=items,site_checks=checks,
                scope='Terrain-to-floor stitches and outer wall foundations. Development retaining closures, not surveyed structural details.',
                shared_terrain_modified=False,visual_acceptance=False,runtime_acceptance=False)
    save_json(ROOT/'data/derived/underpass-closures.json',record)
    print(json.dumps(dict(meshes=len(items),triangles=sum(m['triangles'] for m in items),checks=checks)))


if __name__=='__main__':main()
