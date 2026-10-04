"""Read only the acquired North Shore OSM subset, preserving source geometry."""
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import shapely
from shapely.geometry import Point,Polygon,LineString
from shapely.ops import polygonize
from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[2]
SITES={'Fibreco':'way_1172875700','Seaspan':'way_709281886','VancouverWharves':'relation_15847617',
       'Richardson':'relation_15803613','Cargill':'relation_15803612','Neptune':'way_564571990','G3':'relation_15823540'}


def read_sources():
    objects={};nodes={}
    for path in sorted((ROOT/'data/raw/northshore').glob('osm-*.osm')):
        for item in ET.parse(path).getroot():
            if item.tag not in ['node','way','relation']:continue
            key=item.tag+'_'+item.attrib['id'];objects[key]=item
            if item.tag=='node':nodes[item.attrib['id']]=(float(item.attrib['lon']),float(item.attrib['lat']))
    project=Transformer.from_crs(4326,3157,always_xy=True)
    def coords(item):
        refs=[x.attrib['ref'] for x in item.findall('nd')]
        if not refs or any(k not in nodes for k in refs):return None
        points=np.array([nodes[k] for k in refs]);x,y=project.transform(points[:,0],points[:,1])
        return np.column_stack((x-489600,y-5461100))
    rows={};failures=[]
    for key,item in objects.items():
        tags={x.attrib['k']:x.attrib['v'] for x in item.findall('tag')}
        if not tags:continue
        geometry=None
        if item.tag=='node':
            lon,lat=nodes[item.attrib['id']];x,y=project.transform(lon,lat);geometry=Point(x-489600,y-5461100)
        elif item.tag=='way':
            xy=coords(item)
            if xy is None:continue
            geometry=shapely.make_valid(Polygon(xy)) if len(xy)>3 and np.allclose(xy[0],xy[-1]) else LineString(xy)
        elif tags.get('type')=='multipolygon':
            outer,inner=[],[];missing=[]
            for member in item.findall('member'):
                if member.attrib['type']!='way':continue
                part=objects.get('way_'+member.attrib['ref']);xy=coords(part) if part is not None else None
                if xy is None:missing.append(member.attrib['ref']);continue
                (inner if member.attrib.get('role')=='inner' else outer).append(LineString(xy))
            if missing:
                failures.append(dict(id=key,missing_members=missing));continue
            geometry=shapely.union_all(list(polygonize(outer))).difference(shapely.union_all(list(polygonize(inner))))
        if geometry is None or geometry.is_empty:continue
        rows[key]=dict(id=key,osm_type=item.tag,osm_id=item.attrib['id'],timestamp=item.attrib.get('timestamp'),
            version=item.attrib.get('version'),source_url=f'https://www.openstreetmap.org/{item.tag}/{item.attrib["id"]}',tags=tags,geometry=geometry)
    sites={k:rows[v] for k,v in SITES.items()}
    return rows,sites,failures


if __name__=='__main__':
    import json
    rows,sites,failures=read_sources()
    for name,site in sites.items():
        poly=site['geometry'];selected=[]
        for row in rows.values():
            tags=row['tags'];g=row['geometry']
            if not poly.covers(g.representative_point()):continue
            if any(k in tags for k in ['building','building:part']) or tags.get('man_made') in ['silo','storage_tank','crane','goods_conveyor','pier']:
                selected.append(dict(id=row['id'],kind=g.geom_type,area=round(g.area),tags=tags,xy=[round(g.centroid.x,1),round(g.centroid.y,1)]))
        print(name,site['id'],'bounds',list(poly.bounds),'count',len(selected))
        print(json.dumps(selected,ensure_ascii=True))
    print('source_relation_failures',len(failures))
