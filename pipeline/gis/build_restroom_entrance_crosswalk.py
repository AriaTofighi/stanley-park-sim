"""Retain every OSM toilet tag and identify finite M1 coverage, not survey truth."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from pyproj import Transformer
from shapely.geometry import Point, Polygon, shape, LineString
from shapely import union_all
from acquire_sources import digest, save_json

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'data/routes/raw/osm/park-map-20260927.osm'


def main():
    tree = ET.parse(ROOT/SOURCE).getroot()
    nd = {e.attrib['id']: e for e in tree.findall('node')}
    tf = Transformer.from_crs(4326, 3157, always_xy=True)
    def point(n):
        return np.array(tf.transform(float(n.attrib['lon']), float(n.attrib['lat'])))-[489600,5461100]
    boundary = union_all([shape(f['geometry']) for f in json.loads((ROOT/'data/derived/park_boundary_utm.geojson').read_text())['features']])
    covers = json.loads((ROOT/'data/derived/cover-blockout.json').read_text())['buildings']
    polygons = [(r,Polygon(r['outline'])) for r in covers]
    named = {}
    for path in sorted((ROOT/'manifests').glob('*blockouts.json')):
        doc = json.loads(path.read_text(encoding='utf8'))
        for f in doc.get('features',[]):
            for cid in f.get('replace_cover_ids',[]):
                named[cid] = dict(manifest=path.relative_to(ROOT).as_posix(),feature_id=f['id'],name=f['name'])
    rt=json.loads((ROOT/'data/derived/paved-circuit-runtime.json').read_text())
    line=LineString(np.asarray(rt['points_local_m'])[:,:2])
    s=np.asarray(rt['chainage_source_m']);rp=np.asarray(rt['points_local_m'])
    toilets,barriers,outside=[],[],[]
    for el in tree:
        tags={e.attrib['k']:e.attrib['v'] for e in el.findall('tag')}
        if tags.get('amenity')!='toilets' and not tags.get('barrier'): continue
        if el.tag=='node': xy=point(el); geom=Point(xy)
        elif el.tag=='way':
            pp=[point(nd[e.attrib['ref']]) for e in el.findall('nd') if e.attrib['ref'] in nd]
            if not pp: continue
            geom=Polygon(pp) if len(pp)>3 and np.allclose(pp[0],pp[-1]) else LineString(pp)
            xy=np.array(geom.representative_point().coords[0])
        else: continue
        ident=f"{el.tag}{el.attrib['id']}"
        inside=boundary.covers(Point(xy+[489600,5461100]))
        if not inside:
            if tags.get('amenity')=='toilets':outside.append(ident)
            continue
        if tags.get('amenity')=='toilets':
            near=sorted([(p.distance(geom),r) for r,p in polygons],key=lambda v:v[0])[:3]
            r=dict(id=ident,source_tags=tags,local_xy_m=xy.tolist(),nearest_cover_candidates=[dict(id=a['id'],distance_m=d) for d,a in near],source_identity_verified=False)
            cid=near[0][1]['id'];r['nearest_named_candidate']=named.get(cid)
            if ident in ['node2709915129','node8370405353']:
                r.update(complex='Lumberman washrooms below Stanley Park Drive',coverage='new located underpass and facade package; root integration pending',package='manifests/lumberman-facility-blockouts.json',source_identity_verified=True,duplicate_policy='Separate male/female facility tags; same below-road complex, not duplicated building boxes')
            elif ident=='way74267954':
                r.update(complex='Lost Lagoon Nature House washroom',coverage='located below-deck structure package exists; live integration review remains',package='manifests/lagoon-structure-blockouts.json',feature_id='SP_nature_house',owner='m1_named_blockouts',duplicate_policy='No second building from the OSM toilet geometry. The source-located Nature House is near [378,-911]; this OSM tag is offset and is not a precise placement control.',source_identity_verified=False)
            elif ident=='way88279372':
                r.update(complex='Miniature railway public washroom',coverage='existing survey roof and wall mass',cover_id='lidar2022_490000_5461000_3',source_identity_verified=True,duplicate_policy='No new geometry; toilet polygon lies within existing roof',identity_basis='OSM toilet-building footprint inside the distinct 2022 classified roof; City map places WC at train visitor precinct')
            else:
                r.update(coverage='existing nearby named or generic survey mass; coarse form only',cover_id=cid,duplicate_policy='Every source tag retained. Candidate cover reuse is explicit; proximity alone does not establish room identity')
            toilets.append(r)
        else:
            distance=line.distance(geom)
            if distance<=15:
                k=int(np.argmin(np.linalg.norm(rp[:,:2]-xy,axis=1)))
                barriers.append(dict(id=ident,local_xy_m=xy.tolist(),tags=tags,distance_to_main_route_m=distance,nearest_source_station_m=float(s[k]),current_state='OSM tag snapshot only; no September 2026 visual certification'))
    nav=json.loads((ROOT/'data/routes/derived/navigation-details.json').read_text())
    entrances=[r for r in nav['markers'] if r['kind']=='entrance_connection']
    doc=dict(schema_version=1,source_path=SOURCE,source_sha256=digest(ROOT/SOURCE),date='2026-09-27',licence='ODbL-1.0',attribution='© OpenStreetMap contributors',origin=[489600,5461100],crs='EPSG:3157',toilet_tags_inside_park=len(toilets),outside_toilet_tags=outside,toilets=toilets,route_adjacent_barriers=barriers,entrance_markers=entrances,
        gates=dict(known_report_sites=['Lumberman’s Arch','Prospect Point','Third Beach'],primary_existing_condition_source='data/raw/corridor/maze-gates-2025.pdf',pages=[21,22,23],source_status='2024 existing-condition photos in the February 2025 consultant report. Proposed replacements seek 2027–2030 capital funding. No completion evidence found in one bounded City search on 2026-09-27.',blockout_rule='Keep existing-condition forms as dated provisional references; do not treat proposed planters or the lack of recent photos as proof that barriers were removed.',dimensions='No independent measured gate dimensions. Width estimates remain allowed by the user; current existence and opening state remain dated, not certified.'),
        limitations=['20 tags are not 20 unique restroom buildings. Male/female and building/entrance tags may share a complex.','Nearby roof coverage is a finite coarse-form check. It is not a room inventory, opening-hours verification, facade completion or independent location certification.','Physical gate state and collision passage still require root integration and in-application review.'],release_accepted=False)
    save_json(ROOT/'manifests/m1-restroom-entrance-crosswalk.json',doc)
    print(json.dumps(dict(toilets=len(toilets),outside=outside,route_barriers=len(barriers),entrances=len(entrances))))


if __name__=='__main__': main()
