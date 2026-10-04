"""Current OSM footprint geometry, kept separate from distant mass authoring."""
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import shapely
from shapely.geometry import Polygon, LineString, box
from shapely.ops import polygonize
from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[2]

def read_buildings():
    nodes,ways,relations={},{},{}
    for path in sorted((ROOT/'data/raw/skyline').glob('osm-*.osm')):
        for item in ET.parse(path).getroot():
            if item.tag=='node':nodes[item.attrib['id']]=(float(item.attrib['lon']),float(item.attrib['lat']))
            elif item.tag=='way':ways[item.attrib['id']]=item
            elif item.tag=='relation':relations[item.attrib['id']]=item
    project=Transformer.from_crs(4326,3157,always_xy=True)
    geographic=Transformer.from_crs(3157,4326,always_xy=True)
    def xy(item):
        refs=[r.attrib['ref'] for r in item.findall('nd')]
        if not all(r in nodes for r in refs):return None
        ll=np.array([nodes[r] for r in refs]);x,y=project.transform(ll[:,0],ll[:,1])
        return np.column_stack((x-489600,y-5461100))
    rows=[];member_ids=set()
    for kind,items in [('relation',relations),('way',ways)]:
        for key,item in items.items():
            tags={t.attrib['k']:t.attrib['v'] for t in item.findall('tag')}
            if not ('building' in tags or 'building:part' in tags):continue
            if tags.get('building') in ['no','construction','ruins'] or 'demolished:building' in tags:continue
            if kind=='way':
                if key in member_ids:continue
                coords=xy(item)
                if coords is None or len(coords)<4 or not np.allclose(coords[0],coords[-1]):continue
                shape=shapely.make_valid(Polygon(coords))
            else:
                if tags.get('type')!='multipolygon':continue
                outer,inner=[],[]
                for member in item.findall('member'):
                    if member.attrib['type']!='way' or member.attrib['ref'] not in ways:continue
                    coords=xy(ways[member.attrib['ref']])
                    if coords is None or len(coords)<2:continue
                    (inner if member.attrib.get('role')=='inner' else outer).append(LineString(coords))
                    member_ids.add(member.attrib['ref'])
                shape=shapely.union_all(list(polygonize(outer))).difference(shapely.union_all(list(polygonize(inner))))
            if shape.is_empty:continue
            lon,lat=geographic.transform(shape.centroid.x+489600,shape.centroid.y+5461100)
            if not (-123.150<=lon<=-123.097 and 49.274<=lat<=49.299):continue
            for index,poly in enumerate(shapely.get_parts(shape)):
                if poly.geom_type!='Polygon' or poly.area<10:continue
                rows.append(dict(id=f'{kind}_{key}_{index}',osm_type=kind,osm_id=key,
                    timestamp=item.attrib.get('timestamp'),tags=tags,polygon=poly))
    return rows

if __name__=='__main__':
    rows=read_buildings();print('Bounded building parts',len(rows))
    targets=['Butterfly','Paradox','Hyatt Vancouver','Canada Place','The Stack','Harbour Centre','Alberni by','Cardero','Landmark on Robson']
    for row in rows:
        if not any(t.lower() in row['tags'].get('name','').lower() for t in targets):continue
        if row['tags'].get('name') in ['Cardero Court','Casa Cardero','Villa Cardero','Cardero Cafe']:continue
        print(row['id'], row['tags'].get('name'),round(row['polygon'].area,1),list(row['polygon'].bounds))
        for part in rows:
            if 'building:part' not in part['tags']:continue
            if row['polygon'].covers(part['polygon'].representative_point()):
                print('  ',part['id'],round(part['polygon'].area,1),part['tags'])
