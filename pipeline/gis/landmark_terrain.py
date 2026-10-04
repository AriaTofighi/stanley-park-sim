"""Replace coarse terrain inside measured landmark surface footprints."""
import hashlib
import json
import numpy as np
import shapely
from shapely.geometry import Polygon, shape


def registered_openings(root):
    """Read only explicit replacement footprints, with their source contracts."""
    features = []
    named = root / 'manifests/named-feature-terrain-cuts.json'
    if named.exists():
        for row in json.loads(named.read_text(encoding='utf8'))['cuts']:
            surface = root / row['visible_surface_mesh']
            if hashlib.sha256(surface.read_bytes()).hexdigest() != row['visible_surface_sha256']:
                raise ValueError(f"Changed terrain replacement: {surface}")
            features.append((row['name'], Polygon(row['polygon_local_xy_m']),
                             'Registered named-feature replacement; ' + row['collision_rule']))
    tunnels = root / 'data/derived/underpass-openings.geojson'
    if tunnels.exists():
        for row in json.loads(tunnels.read_text(encoding='utf8'))['features']:
            features.append((row['properties']['id'] + ' underpass', shape(row['geometry']),
                             'Active bicycle bay only; roof and exact floor shoulders supplied separately'))
    facilities=root/'data/derived/lumberman-facilities/replacement-footprints-local.geojson'
    if facilities.exists():
        data=json.loads(facilities.read_text(encoding='utf8'))
        footprint=shapely.union_all([shape(row['geometry']) for row in data['features']])
        features.append(('Lumberman lower facilities and road deck',footprint,
                         'Measured separate floor/road levels with explicit estimated building envelope'))
    for name, polygon, _ in features:
        if not isinstance(polygon, Polygon) or not polygon.is_valid or polygon.area <= 0:
            raise ValueError(f'Invalid terrain replacement polygon: {name}')
    return features

def cut_landmark_terrain(root,vertices,faces,colors):
    source=root/'manifests/coastal-landmark-blockouts.json'
    if not source.exists():return vertices,faces,colors,[]
    rock=next(row for row in json.loads(source.read_text())['landmarks'] if row['id']=='siwash-rock')
    features=[('Siwash Rock',Polygon(np.asarray(rock['rings'][0])[:,:2]),'Measured lowest stone section')]
    platform=root/'manifests/brockton-platform.json'
    if platform.exists():
        data=json.loads(platform.read_text())
        features.append(('Brockton walking platform',Polygon(data['footprint_local_m']),'Fitted low-return walking floor review outline'))
    features.extend(registered_openings(root))
    records=[]
    for name,footprint,method in features:
        vertices,faces,colors,record=_cut_footprint(vertices,faces,colors,footprint,name,method)
        records.append(record)
    return vertices,faces,colors,records

def _cut_footprint(vertices,faces,colors,footprint,name,method):
    polygons=shapely.polygons(vertices[faces,:2])
    ids=shapely.STRtree(polygons).query(footprint,predicate='intersects')
    keep=np.ones(len(faces),bool);keep[ids]=False
    extra_vertices,extra_faces,extra_colors=[],[],[]
    for i in ids:
        original=vertices[faces[i]]
        # Barycentric interpolation preserves the original plane and colors.
        transform=np.linalg.inv(np.column_stack((original[1,:2]-original[0,:2],original[2,:2]-original[0,:2])))
        remaining=polygons[i].difference(footprint)
        for part in shapely.get_parts(remaining):
            if not isinstance(part,Polygon) or part.area<1e-8:continue
            for tri in shapely.get_parts(shapely.constrained_delaunay_triangles(part)):
                xy=np.array(tri.exterior.coords)[:3]
                cross=np.cross(np.append(xy[1]-xy[0],0),np.append(xy[2]-xy[0],0))[2]
                if abs(cross)<1e-10:continue
                if cross<0:xy=xy[::-1]
                uv=(transform@(xy-original[0,:2]).T).T
                weights=np.column_stack((1-uv.sum(1),uv))
                z=weights@original[:,2]
                offset=len(vertices)+len(extra_vertices)
                extra_vertices.extend(np.column_stack((xy,z)).tolist())
                extra_colors.extend((weights@colors[faces[i]]).tolist())
                extra_faces.append([offset,offset+1,offset+2])
    final_v=np.vstack((vertices,extra_vertices)) if extra_vertices else vertices
    final_c=np.vstack((colors,extra_colors)) if extra_colors else colors
    final_f=np.vstack((faces[keep],extra_faces)).astype(np.int32) if extra_faces else faces[keep]
    record=dict(landmark=name,method='Exact triangle clipping: '+method,
        removed_source_faces=len(ids),replacement_boundary_faces=len(extra_faces),
        footprint_area_m2=footprint.area,footprint_local_m=list(footprint.exterior.coords),
        reason='The coarse DTM and detailed landmark must not occupy the same visible surface')
    return final_v,final_f,final_c,record
