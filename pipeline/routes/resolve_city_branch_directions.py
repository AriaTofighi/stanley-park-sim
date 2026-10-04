"""Resolve three City OW records from the City's cardinal facility fields.

This only reads saved public sources and writes evidence/permission sidecars.
It does not infer travel order from GeoJSON storage order or change geometry.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]
IDS = (188, 1160, 3306)


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf8'))


def main():
    paths = ['data/routes/raw/city_bikeways_metadata.json',
             'data/routes/raw/city_bikeways.geojson',
             'data/routes/derived/city-branch-junctions.json',
             'manifests/world-origin.json']
    meta, raw, branches, origin = [read(p) for p in paths]
    fields = {v['name']: v['description'] for v in meta['fields']}
    # Fail closed if the saved primary schema has changed meaning.
    assert 'West- or Northbound' in fields['w_n_bound_type']
    assert 'East- or Southbound' in fields['e_s_bound_type']
    assert 'NS means North-South' in fields['overall_direction']
    project = Transformer.from_crs(4326, origin['horizontal_crs'], always_xy=True)
    source = {int(f['properties']['object_id']): f for f in raw['features']}
    branch = {b['source_object_id']: b for b in branches['branches']}
    overrides = read('manifests/branch-direction-overrides.json')
    results = []
    for object_id in IDS:
        feature, item = source[object_id], branch[object_id]
        props = feature['properties']
        assert props['status'] == 'Active' and props['bikeway_direction'] == 'OW'
        assert props['overall_direction'] == 'NS'
        assert props['w_n_bound_type'] and not props['e_s_bound_type']
        assert feature['geometry']['type'] == 'LineString'
        lonlat = np.asarray(feature['geometry']['coordinates'])
        east, north = project.transform(lonlat[:, 0], lonlat[:, 1])
        xy = np.column_stack((east-origin['easting'], north-origin['northing']))
        assert xy.shape == np.asarray(item['coordinates_local_xy_m']).shape
        source_match = float(np.abs(xy-item['coordinates_local_xy_m']).max())
        assert source_match < 1e-5, 'Derived City geometry differs from primary source'
        delta = xy[-1]-xy[0]
        # The three reviewed NS segments have an unambiguous net northing change.
        assert delta[1] > 10 and abs(delta[1]) > abs(delta[0])
        reason = ('The City labels this Active one-way North-South facility. Its '
                  'northbound facility field is populated and its southbound '
                  'field is empty. Source-forward geometry has positive net '
                  'Northing. Thus forward is the permitted northbound order. '
                  'This resolves City record order; it does not survey current '
                  'signs, lane boundaries, or the identity of a nearby OSM path.')
        evidence = dict(edge_id=item['edge_id'], source_object_id=object_id,
                        permitted_direction='forward_relative_to_city_geometry',
                        source_fields={k: props[k] for k in ['status', 'overall_direction',
                            'bikeway_direction', 'w_n_bound_type', 'e_s_bound_type',
                            'street_name', 'subtype', 'surface_type']},
                        source_start_local_xy_m=xy[0].tolist(),
                        source_end_local_xy_m=xy[-1].tolist(),
                        net_easting_northing_m=delta.tolist(),
                        primary_to_derived_max_coordinate_error_m=source_match,
                        decision=reason,
                        conflicting_osm_tags_preserved_in='data/routes/derived/city-branch-connections-reviewed.json',
                        current_physical_sign_surveyed=False, accuracy_accepted=False)
        results.append(evidence)
        overrides['overrides'][item['edge_id']] = dict(
            permitted_direction=evidence['permitted_direction'],
            resolution_class='City_OW_plus_primary_cardinal_facility_metadata',
            source_ids=['city_bikeways_metadata', 'city_bikeways'],
            reason=reason, evidence='manifests/branch-cardinal-direction-evidence.json',
            retained_conflict='Nearby OSM two-way tags do not widen the City OW permission. Some may describe a separate facility.',
            accuracy_accepted=False)
    result = dict(schema_version=1, review_date='2026-09-27',
        inputs=[dict(path=p, sha256=hashlib.sha256((ROOT/p).read_bytes()).hexdigest()) for p in paths],
        source_urls=['https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/bikeways',
                     'https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/bikeways/exports/geojson'],
        source_capture_utc='2026-09-26T22:01:37Z',
        attribution='Contains information licensed under the Open Government Licence - Vancouver.',
        checks=dict(resolved_record_count=len(results), primary_geometry_reproduced=True,
                    cardinal_field_semantics_checked=True), records=results)
    for path, data in [('manifests/branch-direction-overrides.json', overrides),
                       ('manifests/branch-cardinal-direction-evidence.json', result)]:
        (ROOT/path).write_text(json.dumps(data, indent=2)+'\n', encoding='utf8')
    print(json.dumps(result['checks']))


if __name__ == '__main__':
    main()
