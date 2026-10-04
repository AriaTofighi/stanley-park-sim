"""Finite M1 grounds: retain source polygons and explicit image-picked estimates."""
from pathlib import Path
import json
import xml.etree.ElementTree as ET
import numpy as np
from pyproj import Transformer
import shapely
from shapely.geometry import Polygon, LineString, mapping, shape
from build_public_space_meshes import ROOT, digest, save

OUT = ROOT / 'data/derived/ground-spaces'
RAW = ROOT / 'data/routes/raw/osm/park-map-20260927.osm'


def main():
    tree = ET.parse(RAW).getroot()
    nodes = {int(n.get('id')): (float(n.get('lon')), float(n.get('lat'))) for n in tree.findall('node')}
    ways = {int(w.get('id')): w for w in tree.findall('way')}
    transform = Transformer.from_crs(4326, 3157, always_xy=True)
    features, references, inputs = [], [], [RAW]

    def add(component, feature, group, role, geom, source, **extra):
        if not geom.is_valid or geom.is_empty:
            raise ValueError(component)
        features.append({'type': 'Feature', 'properties': dict(component_id=component,
            feature_id=feature, m1_group=group, material_role=role, source=source,
            surveyed_boundary=False, absolute_accuracy_accepted=False, **extra), 'geometry': mapping(geom)})

    for wid, way in ways.items():
        tags = {t.get('k'): t.get('v') for t in way.findall('tag')}
        if tags.get('golf') not in ['green', 'tee']:
            continue
        ll = np.array([nodes[int(n.get('ref'))] for n in way.findall('nd')])
        e, n = transform.transform(ll[:, 0], ll[:, 1])
        geom = Polygon(np.column_stack((e - 489600, n - 5461100)))
        if not geom.intersects(Polygon([(-365,-1090),(55,-1090),(55,-780),(-365,-780)])):
            continue
        add('Golf_' + tags['golf'] + '_' + str(wid), 'SP_pitch_putt', 'M1-F08', 'golf_' + tags['golf'], geom,
            dict(type='OSM original polygon', way_id=wid, url=f'https://www.openstreetmap.org/way/{wid}',
                 timestamp=way.get('timestamp'), licence='ODbL-1.0'), priority=10)

    original = ROOT / 'data/derived/public-spaces/public-space-blockouts-local.geojson'
    inputs.append(original)
    original_features = json.loads(original.read_text(encoding='utf8'))['features']
    for f in original_features:
        p, geom = f['properties'], shape(f['geometry'])
        if p['material_role'] == 'garden':
            role = 'garden_lawn' if p['component_id'].startswith('Rose') else 'garden_understorey'
            add(p['component_id'] + '_Ground', p['feature_id'], p['m1_group'], role, geom,
                dict(type='OSM garden envelope', way_id=p['way_id'], url=p['source_url'], licence='ODbL-1.0'),
                priority=90, limit='Coarse ground cover only. Existing canopy and separate paths/beds remain. No individual species or flower display is represented.')
        if p['component_id'] == 'MalkinBowlGround':
            add('MalkinAudienceGround', p['feature_id'], p['m1_group'], 'garden_lawn', geom,
                dict(type='OSM event-space envelope', way_id=p['way_id'], licence='ODbL-1.0'), priority=90,
                limit='Coarse lawn around existing stage/building mass; individual audience equipment is deferred.')
        if p['component_id'] == 'NorthLagoonWetland':
            add('BiofilterWetlandGround', p['feature_id'], p['m1_group'], 'wetland', geom,
                dict(type='OSM wetland near official-map Biofiltration Pond', way_id=p['way_id'], licence='ODbL-1.0'),
                priority=30, water_mask=False, minimum_z=.8714010000228882,
                limit='Terrain-backed wetland rim only above the 2022 lagoon water level plus 5 cm. This is not an engineered basin boundary or current operating water level.')
        if p['material_role'] == 'rail_reference':
            if p['grade_separated']:
                references.append(dict(component_id=p['component_id'], feature_id='SP_train', source_way_id=p['way_id'],
                    reason='Bridge/tunnel requires independent vertical structure; not draped onto terrain', completed=False))
            else:
                # Gauge is measured between the inside rail faces. 30 mm is a stated M1 rail-width estimate.
                for side in [-1, 1]:
                    rail = shapely.offset_curve(geom, side * (.508 + .03) / 2).buffer(.015, cap_style='flat', join_style='mitre')
                    add(p['component_id'] + ('_L' if side < 0 else '_R'), 'SP_train', 'M1-F10', 'rail', rail,
                        dict(type='OSM miniature railway', way_id=p['way_id'], gauge_m=.508, licence='ODbL-1.0'), priority=5,
                        limit='At-grade rail strip. Gauge from OSM; 30 mm rail width is an M1 estimate. No operating railway is claimed.')
                add(p['component_id'] + '_Bed', 'SP_train', 'M1-F10', 'track_bed', geom.buffer(.55, cap_style='flat', join_style='mitre'),
                    dict(type='OSM miniature railway alignment', way_id=p['way_id'], licence='ODbL-1.0'), priority=40,
                    limit='1.10 m coarse ballast width is estimated. No collision or rail operations.')

    # Picks are saved in the viewed source-image coordinate system. They are not survey controls.
    def image_polygon(component, feature, group, role, image_name, pixels, display_size=None, **extra):
        metadata = ROOT / f'evidence/corridor/ortho-utm/{image_name}.json'
        image_path = metadata.with_suffix('.png')
        if metadata not in inputs: inputs.extend([metadata, image_path])
        meta = json.loads(metadata.read_text(encoding='utf8'))
        bounds = meta['local_bounds_m']
        size = display_size or meta['image_size']
        points = [(bounds[0] + x / size[0] * (bounds[2]-bounds[0]), bounds[3] - y / size[1] * (bounds[3]-bounds[1])) for x,y in pixels]
        add(component, feature, group, role, Polygon(points), dict(type='Manual coarse image trace',
            image=image_path.relative_to(ROOT).as_posix(), image_sha256=digest(image_path), metadata=metadata.relative_to(ROOT).as_posix(),
            capture_period=meta['capture_period'], pixels=pixels, picked_display_size=size, licence='Open Government Licence - Vancouver'),
            confidence='Approximate visible edge; canopy/season and coarse picks limit accuracy', priority=15, **extra)

    image_polygon('CommunityGardenPath', 'SP_community_garden', 'M1-F09', 'garden_path', 'm1-community-garden',
        [(292,510),(331,489),(424,466),(470,444),(548,434),(574,425),(613,428),(643,452),(647,469),(607,487),(557,486),(477,510),(398,548),(343,569),(306,559)], priority_override=20)
    beds = [ [(307,522),(327,518),(338,547),(316,548)], [(349,521),(435,487),(452,502),(357,544)],
             [(331,492),(412,472),(423,480),(341,510)], [(463,480),(532,454),(538,466),(474,493)],
             [(463,451),(521,442),(519,450),(470,465)], [(560,448),(583,432),(608,435),(629,455),(610,473),(576,471)] ]
    for i, picks in enumerate(beds,1):
        image_polygon(f'CommunityBed_{i:02}', 'SP_community_garden', 'M1-F09', 'garden_bed', 'm1-community-garden', picks,
            limit='Coarse bed group, not an exact plot/plant inventory.')
    rose_beds = [ [(389,1008),(407,996),(421,1008),(414,1032),(403,1048),(395,1043)],
                  [(449,957),(467,947),(477,962),(474,985),(463,1026),(451,1024)],
                  [(638,1049),(653,1045),(671,1063),(687,1083),(694,1118),(685,1127),(666,1120),(651,1098),(638,1076)],
                  [(392,1210),(408,1215),(413,1243),(394,1240)], [(389,1251),(409,1250),(405,1271),(386,1276)],
                  [(461,1214),(477,1213),(478,1238),(461,1239)] ]
    for i,picks in enumerate(rose_beds,1):
        image_polygon(f'RoseBedGroup_{i:02}', 'SP_rose_garden', 'M1-F09', 'garden_bed', 'm1-gardens-north', picks, [1600,1600],
            limit='Selected visible bed groups only; other beds and individual flowers remain deferred.')
    image_polygon('BiofilterVisiblePool', 'SP_biofiltration', 'M1-F07', 'pond_water', 'm1-biofilter',
        [(830,375),(852,369),(871,380),(891,383),(916,396),(929,413),(922,435),(891,445),(865,439),(839,448),(824,428),(822,401)],
        limit='Small open-water patch visible in 2022. Level uses adjoining lagoon flight-day median as an unmeasured local proxy.', water_mask=False, water_z=.8214010000228882)
    # This arboretum has no hard garden boundary in the primary City description.
    add('ShakespeareArboretumGround', 'SP_shakespeare', 'M1-F09', 'garden_understorey',
        Polygon([(461,-340),(516,-340),(517,-280),(498,-271),(467,-290)]),
        dict(type='Inferred finite arboretum envelope', url='https://vancouver.ca/parks-recreation-culture/gardens-in-stanley-park.aspx',
             corroborating_registry_point=[496.3070438692812,-288.70038378983736], licence='Project-authored approximate geometry; City context reference only'),
        priority=95, confidence='Approximate bounds under canopy, not a planted bed', limit='Between Rose Garden and forest; existing trees retained. Monument detail is not included.')
    for f in features:
        p=f['properties']
        if 'priority_override' in p:p['priority']=p.pop('priority_override')
    save(OUT/'ground-spaces-local.geojson', {'type':'FeatureCollection','features':features})
    save(ROOT/'manifests/ground-space-sources.json', dict(schema_version=1, authoring_geometry='data/derived/ground-spaces/ground-spaces-local.geojson',
        source_inputs=[{'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p)} for p in inputs],
        source_period='City imagery June 6–July 1 2022; OSM saved September 27 2026; official park map May 19 2026',
        references=references, unresolved=['Rock Garden finite extent and boulder forms', 'Painters Circle and Portrait Painters finite ground footprints',
            'Salmon Demonstration Stream local channel extent', 'Heron Colony habitat extent', 'Rail bridge and tunnel vertical forms'],
        licence='OSM source-derived polygons ODbL-1.0; City image traces OGL Vancouver; approximate project envelopes identified separately',
        full_m1_groups_complete=False, application_visual_check='pending'))
    print(json.dumps({'ground_components':len(features),'grade_separated_rail_references':len(references)}))


if __name__ == '__main__': main()
